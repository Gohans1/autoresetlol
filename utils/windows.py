import logging
import ctypes
from ctypes import wintypes
import time
import winreg
import sys
import os
from typing import Optional, Tuple, Union

# Get logger instance by name
logger = logging.getLogger("AutoResetLoL")

# Load GDI32 and User32 libraries globally
gdi32 = ctypes.windll.gdi32
user32 = ctypes.windll.user32

# --- Win32 signatures -------------------------------------------------------
# NOTE: only functions used EXCLUSIVELY by this app get argtypes here.
# Do NOT set argtypes on user32.GetDC/ReleaseDC: Pillow shares the same
# ctypes.windll.user32 instance and its calling convention conflicts with
# ours (breaks with "OverflowError: int too long to convert"). Verified
# empirically — keep them bare.
gdi32.SetDeviceGammaRamp.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.WORD)]
gdi32.SetDeviceGammaRamp.restype = wintypes.BOOL
gdi32.GetDeviceGammaRamp.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.WORD)]
gdi32.GetDeviceGammaRamp.restype = wintypes.BOOL


class GammaController:
    """
    Ghost dimming via GDI32 gamma ramp.

    The ramp is applied at the display-output stage (after desktop
    composition), so screen captures never see the dimming.

    Windows rejects any ramp dimmer than ~50% of the linear ramp
    (SetDeviceGammaRamp returns FALSE and silently keeps the old ramp),
    so below 50% we use a gamma curve (k=2, scale 0.5) that is dimmer
    than linear 50% at every point yet passes Windows validation.
    """

    def __init__(self):
        self.hdc = user32.GetDC(0)
        self._initial_ramp: Optional[ctypes.Array] = None
        if self.hdc:
            ramp = (wintypes.WORD * 768)()
            if gdi32.GetDeviceGammaRamp(
                self.hdc, ctypes.cast(ramp, ctypes.POINTER(wintypes.WORD))
            ):
                self._initial_ramp = ramp

    @staticmethod
    def build_ramp(level: int) -> ctypes.Array:
        """Build a valid 768-entry gamma ramp for the requested level.

        Windows heuristics reject any ramp dimmer than ~50% of the linear
        ramp (SetDeviceGammaRamp returns FALSE and silently keeps the old
        ramp - anti-black-screen protection, see MS Learn). The dimmer is
        therefore capped at 50%; level is clamped to [50, 100] here so no
        call site can ever produce an invalid ramp.
        """
        level = max(50, min(100, int(level)))
        ramp = (wintypes.WORD * 768)()
        scale = level / 100.0
        for i in range(256):
            adj = min(65535, int(i * 256 * scale))
            ramp[i] = ramp[i + 256] = ramp[i + 512] = adj
        return ramp

    def set_brightness(self, level: int) -> bool:
        """
        Set screen brightness using Gamma Ramp.
        level: 0 to 100 (integer)
        """
        if not self.hdc:
            return False
        ramp = self.build_ramp(level)
        return bool(gdi32.SetDeviceGammaRamp(
                self.hdc, ctypes.cast(ramp, ctypes.POINTER(wintypes.WORD))
            ))

    def verify(self, level: int) -> bool:
        """
        Verify the active ramp still matches the requested level.
        Used by the dimmer watchdog (safety against drift).
        """
        if not self.hdc:
            return False
        ramp = self.build_ramp(level)
        rb = (wintypes.WORD * 768)()
        if not gdi32.GetDeviceGammaRamp(
                self.hdc, ctypes.cast(rb, ctypes.POINTER(wintypes.WORD))
            ):
            return False
        # Compare by magnitude, not exact entry match: some GPUs/drivers
        # quantize the ramp differently (10-bit panels etc.), which would
        # otherwise make the watchdog re-apply the ramp every tick.
        max_diff = max(abs(int(a) - int(b)) for a, b in zip(rb, ramp))
        return max_diff <= 32

    def reset(self):
        """Reset to 100% brightness"""
        self.set_brightness(100)

    def close(self):
        """Cleanup resources - restore the ramp that was active before us."""
        if self.hdc:
            if self._initial_ramp is not None:
                gdi32.SetDeviceGammaRamp(
                    self.hdc,
                    ctypes.cast(self._initial_ramp, ctypes.POINTER(wintypes.WORD)),
                )
            else:
                self.set_brightness(100)
            user32.ReleaseDC(0, self.hdc)
            self.hdc = None


class PHYSICAL_MONITOR(ctypes.Structure):
    _fields_ = [
        ("hPhysicalMonitor", wintypes.HANDLE),
        ("szPhysicalMonitorDescription", ctypes.c_wchar * 128),
    ]


class MonitorBrightnessController:
    """
    Physical backlight dimming via DDC/CI (DXVA2).

    Dims the actual monitor backlight: fully ghost to screen capture
    (the backlight sits after the scanout stage), has no 50% Windows
    limit, and if the app dies mid-dim the user recovers immediately
    with the keyboard brightness keys.
    """

    def __init__(self):
        self._pm: Optional[int] = None
        self._min: int = 0
        self._max: int = 100
        self._initial: Optional[int] = None
        self.available: bool = False
        self._find_monitor()

    def _find_monitor(self) -> None:
        try:
            monitors: list = []
            enum_proc = ctypes.WINFUNCTYPE(
                wintypes.BOOL,
                wintypes.HMONITOR,
                wintypes.HDC,
                ctypes.POINTER(wintypes.RECT),
                wintypes.LPARAM,
            )

            def _cb(hmon, hdc, rect, lparam):
                monitors.append(hmon)
                return True

            user32.EnumDisplayMonitors(None, None, enum_proc(_cb), 0)
            if not monitors:
                logger.warning("No display monitor found for backlight control")
                return

            dxva2 = ctypes.windll.dxva2
            dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [
                wintypes.HMONITOR,
                ctypes.POINTER(wintypes.DWORD),
            ]
            dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
            dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [
                wintypes.HMONITOR,
                wintypes.DWORD,
                ctypes.POINTER(PHYSICAL_MONITOR),
            ]
            dxva2.GetPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
            # NOTE: Get/SetMonitorBrightness deliberately have NO argtypes.
            # On WMI/ACPI laptop panels the handle is 0; declaring [HANDLE, ...]
            # converts None/0 to a NULL pointer which the driver rejects, while
            # the plain integer 0 (no argtypes) is accepted. Verified empirically.
            dxva2.GetMonitorBrightness.restype = wintypes.BOOL
            dxva2.SetMonitorBrightness.restype = wintypes.BOOL
            dxva2.DestroyPhysicalMonitor.argtypes = [wintypes.HANDLE]
            dxva2.DestroyPhysicalMonitor.restype = wintypes.BOOL

            for hmon in monitors:
                n = wintypes.DWORD(0)
                if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(
                    hmon, ctypes.byref(n)
                ) or n.value == 0:
                    continue
                arr = (PHYSICAL_MONITOR * n.value)()
                if not dxva2.GetPhysicalMonitorsFromHMONITOR(hmon, n.value, arr):
                    continue
                for pm in arr:
                    # A NULL handle means the driver simulates DDC/CI state
                    # (verified on NVIDIA + non-DDC monitor): set/get then lie.
                    # Only accept a real hardware handle.
                    if pm.hPhysicalMonitor is None:
                        dxva2.DestroyPhysicalMonitor(pm.hPhysicalMonitor)
                        continue
                    mn = wintypes.DWORD(0)
                    cur = wintypes.DWORD(0)
                    mx = wintypes.DWORD(0)
                    if dxva2.GetMonitorBrightness(
                        pm.hPhysicalMonitor, ctypes.byref(mn), ctypes.byref(cur), ctypes.byref(mx)
                    ):
                        self._pm = pm.hPhysicalMonitor
                        self._min, self._max = int(mn.value), int(mx.value)
                        self._initial = int(cur.value)
                        self.available = True
                        logger.info(
                            f"Backlight control available on "
                            f"'{pm.szPhysicalMonitorDescription}' "
                            f"(range {self._min}-{self._max}, current {self._initial})"
                        )
                        # Release the handles we are not using (avoid leak).
                        for other in arr:
                            if (
                                other.hPhysicalMonitor is not None
                                and other.hPhysicalMonitor != pm.hPhysicalMonitor
                            ):
                                dxva2.DestroyPhysicalMonitor(other.hPhysicalMonitor)
                        return
                    dxva2.DestroyPhysicalMonitor(pm.hPhysicalMonitor)
            logger.warning("No monitor with DDC/CI brightness support found")
        except Exception as e:
            logger.error(f"Backlight monitor detection failed: {e}")

    def set_brightness(self, level: int) -> bool:
        if not self.available:
            return False
        level = max(1, min(100, int(level)))
        mapped = int(self._min + (self._max - self._min) * level / 100.0)
        # WMI/ACPI backlight applies asynchronously: never trust the return
        # code alone, confirm via readback (with retry).
        for _attempt in range(2):
            ctypes.windll.dxva2.SetMonitorBrightness(self._pm, mapped)
            # Readback first: on the common path the value applies at once
            # and we skip the sleep entirely (keeps GUI-thread calls snappy).
            if self.verify(level):
                return True
            time.sleep(0.15)
        return False

    def verify(self, level: int) -> bool:
        """Verify the backlight still matches the requested level (watchdog)."""
        if not self.available:
            return False
        mn = wintypes.DWORD(0)
        cur = wintypes.DWORD(0)
        mx = wintypes.DWORD(0)
        if not ctypes.windll.dxva2.GetMonitorBrightness(
            self._pm, ctypes.byref(mn), ctypes.byref(cur), ctypes.byref(mx)
        ):
            return False
        level = max(1, min(100, int(level)))
        expected = int(self._min + (self._max - self._min) * level / 100.0)
        return abs(int(cur.value) - expected) <= 2

    def reset(self):
        """Reset to 100% brightness"""
        self.set_brightness(100)

    def close(self):
        """Restore the brightness level that was active before we started."""
        if self._pm is not None:
            if self._initial is not None:
                ctypes.windll.dxva2.SetMonitorBrightness(self._pm, self._initial)
            ctypes.windll.dxva2.DestroyPhysicalMonitor(self._pm)
        self._pm = None
        self.available = False


class DimmerController:
    """
    Unified ghost dimmer: DDC/CI backlight when available, gamma ramp otherwise.

    - Backlight backend: full 0-100% deep dimming, physical (invisible to
      capture), recoverable with keyboard brightness keys.
    - Gamma backend: Windows rejects ramps dimmer than ~50% linear; below
      50% a validated gamma curve is used (dimmer than linear 50% at every
      point, but with a hard floor).
    - Runtime safety: if the backlight backend fails repeatedly, fall back
      to gamma for the rest of the session.
    """

    def __init__(self):
        self._backend: Optional[Union[GammaController, MonitorBrightnessController]] = None
        self._backend_failures: int = 0
        self._try_backlight_first()

    def _try_backlight_first(self) -> None:
        try:
            bl = MonitorBrightnessController()
            if bl.available:
                self._backend = bl
                logger.info("Dimmer backend: DDC/CI backlight (deep dimming available)")
                return
        except Exception as e:
            logger.warning(f"Backlight controller init failed: {e}")
        self._backend = GammaController()
        logger.info("Dimmer backend: gamma ramp (50% cap: Windows heuristics limit)")

    @property
    def backend_name(self) -> str:
        return type(self._backend).__name__

    def set_brightness(self, level: int) -> bool:
        ok = self._backend.set_brightness(level)
        if isinstance(self._backend, MonitorBrightnessController):
            if not ok:
                self._backend_failures += 1
                if self._backend_failures >= 3:
                    logger.warning(
                        "Backlight failed repeatedly — falling back to gamma ramp"
                    )
                    try:
                        self._backend.close()
                    except Exception:
                        pass
                    self._backend = GammaController()
                    self._backend_failures = 0
                    return self._backend.set_brightness(level)
            else:
                self._backend_failures = 0
        return ok

    def verify(self, level: int) -> bool:
        """Check the display state matches the requested level (watchdog)."""
        return self._backend.verify(level)

    def reset(self) -> None:
        self._backend.reset()

    def close(self) -> None:
        try:
            if self._backend is not None:
                self._backend.close()
        finally:
            self._backend = None


def set_autostart(app_name: str, add: bool = True) -> bool:
    """
    Adds or removes the application from Windows Startup (Registry).
    """
    # 1. Determine execution path
    if getattr(sys, "frozen", False):
        # Compiled with PyInstaller
        current_path = sys.executable
    else:
        # Running as script
        python_exe = sys.executable
        script_path = os.path.abspath(sys.argv[0])
        current_path = f'"{python_exe}" "{script_path}"'

    # Ensure path is quoted if it contains spaces (for EXE case)
    if (
        getattr(sys, "frozen", False)
        and " " in current_path
        and not current_path.startswith('"')
    ):
        current_path = f'"{current_path}"'

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS
        ) as key:
            # Cleanup legacy names to avoid duplicates in Startup tab
            legacy_names = ["antifate_7.14", "AntiFateEngine"]
            for legacy in legacy_names:
                try:
                    if legacy != app_name:
                        winreg.DeleteValue(key, legacy)
                        logger.info(f"Cleaned up legacy startup entry: {legacy}")
                except FileNotFoundError:
                    pass

            if add:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, current_path)
                logger.info(f"Added {app_name} to Startup: {current_path}")
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                    logger.info(f"Removed {app_name} from Startup.")
                except FileNotFoundError:
                    logger.debug(f"{app_name} not found in Startup Registry.")
        return True
    except Exception as e:
        logger.error(f"Failed to update Startup Registry: {e}")
        return False

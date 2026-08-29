import logging
import ctypes
from ctypes import wintypes
import time
import winreg
import sys
import os
from typing import Any, Dict, Optional, Tuple, Union

# Get logger instance by name
logger = logging.getLogger("AutoResetLoL")

_STARTUP_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_STARTUP_APPROVAL_KEY_PATH = (
    r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
)
_STARTUP_ENABLED_STATE = b"\x02" + b"\x00" * 11
_STARTUP_LEGACY_NAMES = ("antifate_7.14", "AntiFateEngine")

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
    so this controller clamps gamma brightness to the safe [50, 100] range.
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
            dxva2.GetMonitorBrightness.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(wintypes.DWORD),
                ctypes.POINTER(wintypes.DWORD),
                ctypes.POINTER(wintypes.DWORD),
            ]
            dxva2.GetMonitorBrightness.restype = wintypes.BOOL
            dxva2.SetMonitorBrightness.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
            ]
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
                    if not pm.hPhysicalMonitor:
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
    - Gamma backend: Windows rejects ramps dimmer than ~50% linear, so the
      gamma controller clamps brightness to the safe [50, 100] range.
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


def _read_startup_value(
    key_path: str, app_name: str
) -> Optional[Tuple[Any, int]]:
    """Read one value as the `(data, type)` tuple returned by winreg."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            key_path,
            0,
            winreg.KEY_READ,
        ) as key:
            return winreg.QueryValueEx(key, app_name)
    except FileNotFoundError:
        return None


def _restore_startup_value(
    key_path: str,
    app_name: str,
    value: Optional[Tuple[Any, int]],
    access: int,
) -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            key_path,
            0,
            access,
        ) as key:
            if value is None:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            else:
                value_data, value_type = value
                winreg.SetValueEx(key, app_name, 0, value_type, value_data)
        return True
    except FileNotFoundError:
        return value is None
    except Exception as e:
        logger.error(f"Failed to restore Startup Registry state: {e}")
        return False


def get_autostart_snapshot(app_name: str) -> Optional[Dict[str, Any]]:
    """Capture the Startup values that an update can change."""
    try:
        return {
            "app_name": app_name,
            "run": _read_startup_value(_STARTUP_RUN_KEY_PATH, app_name),
            "approval": _read_startup_value(_STARTUP_APPROVAL_KEY_PATH, app_name),
            "legacy": {
                legacy: _read_startup_value(_STARTUP_RUN_KEY_PATH, legacy)
                for legacy in _STARTUP_LEGACY_NAMES
                if legacy != app_name
            },
        }
    except OSError as e:
        logger.error(f"Failed to read Startup Registry state: {e}")
        return None


def restore_autostart_snapshot(snapshot: Dict[str, Any]) -> bool:
    """Restore the exact Startup values captured before an update."""
    app_name = snapshot.get("app_name", "Anti-Fate Engine")
    restored = _restore_startup_value(
        _STARTUP_RUN_KEY_PATH,
        app_name,
        snapshot.get("run"),
        winreg.KEY_ALL_ACCESS,
    )
    restored = (
        _restore_startup_value(
            _STARTUP_APPROVAL_KEY_PATH,
            app_name,
            snapshot.get("approval"),
            winreg.KEY_SET_VALUE,
        )
        and restored
    )
    for legacy, value in (snapshot.get("legacy") or {}).items():
        restored = (
            _restore_startup_value(
                _STARTUP_RUN_KEY_PATH,
                legacy,
                value,
                winreg.KEY_ALL_ACCESS,
            )
            and restored
        )
    return restored


def get_autostart_state(app_name: str) -> Optional[bool]:
    """Return the effective Startup state, or None when Windows denies the read."""
    try:
        run_value = _read_startup_value(_STARTUP_RUN_KEY_PATH, app_name)
    except OSError as e:
        logger.warning(f"Failed to read Startup Registry entry: {e}")
        return None
    if run_value is None:
        return False

    try:
        approval_value = _read_startup_value(
            _STARTUP_APPROVAL_KEY_PATH,
            app_name,
        )
    except OSError as e:
        logger.warning(f"Failed to read Startup approval state: {e}")
        return None
    if approval_value is None:
        return True

    raw_state, value_type = approval_value
    if (
        value_type != winreg.REG_BINARY
        or not isinstance(raw_state, (bytes, bytearray))
        or len(raw_state) != len(_STARTUP_ENABLED_STATE)
    ):
        return None
    if raw_state[0] == 2:
        return True
    if raw_state[0] in (3, 7):
        return False
    return None


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

    key_path = _STARTUP_RUN_KEY_PATH
    approval_key_path = _STARTUP_APPROVAL_KEY_PATH
    startup_enabled_state = _STARTUP_ENABLED_STATE
    legacy_names = _STARTUP_LEGACY_NAMES
    snapshot = get_autostart_snapshot(app_name)
    if snapshot is None:
        return False

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS
        ) as key:
            # Cleanup legacy names to avoid duplicates in Startup tab
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

        if add:
            # Also clear a previous manual disable in Windows Startup apps.
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                approval_key_path,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.SetValueEx(
                    key,
                    app_name,
                    0,
                    winreg.REG_BINARY,
                    startup_enabled_state,
                )
        else:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    approval_key_path,
                    0,
                    winreg.KEY_SET_VALUE,
                ) as key:
                    winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        effective_state = get_autostart_state(app_name)
        if effective_state is not bool(add):
            raise OSError(
                f"Startup Registry read-back mismatch: expected {bool(add)}"
            )
        return True
    except Exception as e:
        restore_autostart_snapshot(snapshot)
        logger.error(f"Failed to update Startup Registry: {e}")
        return False

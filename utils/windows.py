import logging
import ctypes
from ctypes import wintypes
import time
import win32gui
import win32con
import win32com.client
import winreg
import sys
import os
from typing import Optional, Tuple

# Get logger instance by name
logger = logging.getLogger("AutoResetLoL")

# Load GDI32 and User32 libraries globally
gdi32 = ctypes.windll.gdi32
user32 = ctypes.windll.user32


def find_window_by_title(title: str) -> int:
    """Finds a window handle by its title."""
    try:
        return win32gui.FindWindow(None, title)
    except Exception as e:
        logger.error(f"Error finding window '{title}': {e}")
        return 0


def is_window_foreground(hwnd: int) -> bool:
    """Checks if the given window handle is currently in the foreground."""
    try:
        fg_hwnd = win32gui.GetForegroundWindow()
        return fg_hwnd == hwnd
    except Exception as e:
        logger.error(f"Error checking foreground window: {e}")
        return False


def get_foreground_window_title() -> str:
    """Returns the title of the current foreground window."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        return win32gui.GetWindowText(hwnd)
    except Exception as e:
        logger.error(f"Error getting foreground window title: {e}")
        return ""


def force_focus_window(hwnd: int) -> bool:
    """
    Attempts to force focus a window using the Alt-key trick to bypass
    Windows foreground locking.
    """
    try:
        if is_window_foreground(hwnd):
            return True

        logger.info(f"Forcing focus to window handle: {hwnd}")

        # Trick to bypass Windows Foreground Lock
        shell = win32com.client.Dispatch("WScript.Shell")
        shell.SendKeys("%")  # Sends a harmless ALT key press

        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)  # Restore if minimized
        win32gui.SetForegroundWindow(hwnd)  # Bring to front

        # Wait slightly for window to process
        time.sleep(0.5)

        return is_window_foreground(hwnd)
    except Exception as e:
        logger.error(f"Force focus failed: {e}")
        return False


class GammaController:
    """
    Controls screen brightness using GDI32 Gamma Ramp.
    """

    def __init__(self):
        self.hdc = user32.GetDC(None)

    def set_brightness(self, level: int) -> bool:
        """
        Set screen brightness using Gamma Ramp.
        level: 0 to 100 (integer)
        """
        if not self.hdc:
            return False

        # Clamp level to 1-100
        level = max(1, min(100, int(level)))

        ramp = (wintypes.WORD * 768)()

        for i in range(256):
            val = i * 256
            adjusted_val = int(val * (level / 100.0))
            adjusted_val = min(65535, adjusted_val)

            ramp[i] = adjusted_val  # Red
            ramp[i + 256] = adjusted_val  # Green
            ramp[i + 512] = adjusted_val  # Blue

        success = gdi32.SetDeviceGammaRamp(self.hdc, ctypes.byref(ramp))
        return bool(success)

    def reset(self):
        """Reset to 100% brightness"""
        self.set_brightness(100)

    def close(self):
        """Cleanup resources"""
        if self.hdc:
            self.reset()
            user32.ReleaseDC(None, self.hdc)
            self.hdc = None


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

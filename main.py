import sys
import os

from constants import RESOURCE_DIR
from gui import AntiFateApp
from logger import logger

# Change working directory to resource directory to avoid issues with relative paths
# when started from Windows Startup (Registry) where CWD might be System32
os.chdir(RESOURCE_DIR)


# --- Single instance guard ------------------------------------------------
# Two instances would fight over the display gamma ramp (each watchdog
# re-applies its own level) -> visible brightness flicker. A named mutex is
# released by the OS when the process dies, so no stale lock can block a
# later launch after a crash. The handle MUST stay referenced for the whole
# app lifetime (that reference IS the mutex).
_SINGLE_INSTANCE_MUTEX = None


def _enforce_single_instance() -> bool:
    """Create the single-instance mutex.

    Returns True when this process is the first/only instance.
    Shows a message box and returns False otherwise.
    """
    global _SINGLE_INSTANCE_MUTEX
    import ctypes
    import time

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [
        ctypes.c_void_p,  # lpMutexAttributes (NULL)
        ctypes.c_int,     # bInitialOwner (False)
        ctypes.c_wchar_p,  # lpName
    ]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int

    # --restart: instance kế tiếp do _restart_app (đổi UI scale) sinh ra —
    # cha chưa thoát hẳn khi con import nên mutex vẫn bị giữ. KHÔNG bỏ mutex
    # (mất bảo vệ single-instance → 2 app đánh nhau gamma ramp) — thử lại
    # trong ~5s cho cha thoát, hết thời gian mới báo lỗi.
    max_tries = 10 if "--restart" in sys.argv else 1
    for attempt in range(max_tries):
        _SINGLE_INSTANCE_MUTEX = kernel32.CreateMutexW(
            None, 0, "AntiFateEngine_SingleInstance"
        )
        if ctypes.get_last_error() != 183:  # not ERROR_ALREADY_EXISTS
            return True
        # Close handle vừa mở (bản sao của mutex đang tồn tại) trước khi retry
        if _SINGLE_INSTANCE_MUTEX:
            kernel32.CloseHandle(_SINGLE_INSTANCE_MUTEX)
            _SINGLE_INSTANCE_MUTEX = None
        if attempt == 0:
            logger.info("Waiting for previous instance to exit...")
        time.sleep(0.5)

    ctypes.windll.user32.MessageBoxW(
        None,
        "Anti-Fate Engine is already running.\n"
        "Only one instance is allowed - two instances fight over "
        "screen brightness and cause flickering.",
        "Anti-Fate Engine",
        0x10,  # MB_ICONERROR
    )
    return False


def main() -> None:
    # MUST run before any GUI/dimmer init: a second instance would fight
    # over the gamma ramp with the first one (flickering screen).
    if not _enforce_single_instance():
        sys.exit(1)
    logger.info("Initializing Application...")
    app = AntiFateApp()
    app.mainloop()
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Critical Application Error: {e}", exc_info=True)

import sys
import os
from constants import RESOURCE_DIR
from gui import AntiFateApp
from logger import logger

# Change working directory to resource directory to avoid issues with relative paths
# when started from Windows Startup (Registry) where CWD might be System32
os.chdir(RESOURCE_DIR)

# Explicit imports to force PyInstaller to include them
import pyscreeze  # type: ignore
import PIL  # type: ignore
import pyautogui  # type: ignore


def main() -> None:
    logger.info("Initializing Application...")
    app = AntiFateApp()
    app.mainloop()
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Critical Application Error: {e}", exc_info=True)

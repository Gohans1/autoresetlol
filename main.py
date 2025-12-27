import sys
from gui import AntiFateApp
from logger import logger

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

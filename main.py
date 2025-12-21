from gui import AntiFateApp

# Explicit imports to force PyInstaller to include them
import pyscreeze
import PIL
import pyautogui


def main():
    app = AntiFateApp()
    app.mainloop()


if __name__ == "__main__":
    main()

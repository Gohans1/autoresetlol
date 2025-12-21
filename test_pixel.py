import pyautogui
import sys

try:
    print("Testing pyautogui pixel()...")
    # Lấy thử pixel ở vị trí 0,0
    color = pyautogui.pixel(0, 0)
    print(f"Pixel at (0,0): {color}")
    print("SUCCESS: Pillow is working correctly with PyAutoGUI.")
except Exception as e:
    print(f"FAILURE: {e}")
    sys.exit(1)

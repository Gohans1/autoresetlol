import time
import pyautogui
import keyboard
import os
import sys


def main():
    print("=" * 50)
    print("     GOHANSGPT - COORDINATE & COLOR PICKER")
    print("=" * 50)
    print("[-] Di chuyển chuột đến vị trí cần lấy.")
    print("[-] Nhấn phím 'S' để LƯU tọa độ và màu hiện tại.")
    print("[-] Nhấn 'Q' để THOÁT.")
    print("=" * 50)

    saved_items = []

    try:
        while True:
            # Get current mouse position
            x, y = pyautogui.position()

            # Get color at current position
            try:
                # pyautogui.pixel might fail on some multi-monitor setups or locked screens
                r, g, b = pyautogui.pixel(x, y)
            except Exception:
                r, g, b = (0, 0, 0)

            # Clear line and print current status (dynamic update)
            # using \r to overwrite the line
            status = f"Current: X={x}, Y={y} | RGB=({r}, {g}, {b})"
            print(f"\r{status.ljust(60)}", end="")

            if keyboard.is_pressed("s"):
                # Debounce
                time.sleep(0.2)
                print(f"\n[+] SAVED: X={x}, Y={y}, RGB=[{r}, {g}, {b}]")
                print("-" * 30)
                saved_items.append({"pos": [x, y], "color": [r, g, b]})

            if keyboard.is_pressed("q"):
                print("\n\n[!] Exiting...")
                break

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\n[!] Interrupted.")

    if saved_items:
        print("\n" + "=" * 50)
        print("SUMMARY OF SAVED POINTS:")
        for idx, item in enumerate(saved_items):
            print(f"Point {idx + 1}:")
            print(f'  "pixel_pos": {item["pos"]},')
            print(f'  "pixel_color": {item["color"]}')
        print("=" * 50)
        input("Press Enter to close...")


if __name__ == "__main__":
    main()

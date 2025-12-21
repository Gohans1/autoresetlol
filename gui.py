import tkinter as tk
from tkinter import messagebox
import pyautogui
from config import config_manager
import time
from bot import AntiFateBot


class AntiFateApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Anti-Fate Engine")
        self.geometry("300x250")
        self.resizable(False, False)
        self.attributes("-topmost", True)  # Always on top
        self.bot = None

        self.create_widgets()
        self.load_settings()

    def create_widgets(self):
        # Status Label
        self.status_label = tk.Label(
            self, text="Status: Ready", font=("Arial", 10, "bold"), fg="gray"
        )
        self.status_label.pack(pady=10)

        # Reset Time Input
        input_frame = tk.Frame(self)
        input_frame.pack(pady=5)

        tk.Label(input_frame, text="Reset Time (s):").pack(side=tk.LEFT, padx=5)

        self.reset_time_var = tk.StringVar()
        self.reset_time_entry = tk.Entry(
            input_frame, textvariable=self.reset_time_var, width=10
        )
        self.reset_time_entry.pack(side=tk.LEFT)

        # Buttons Frame
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=15)

        self.start_btn = tk.Button(
            btn_frame,
            text="START",
            width=10,
            bg="#4CAF50",
            fg="white",
            command=self.start_bot,
        )
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = tk.Button(
            btn_frame,
            text="STOP",
            width=10,
            bg="#f44336",
            fg="white",
            state=tk.DISABLED,
            command=self.stop_bot,
        )
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # Calibration Button
        self.calib_btn = tk.Button(
            self, text="Calibrate Coordinates", width=20, command=self.calibrate
        )
        self.calib_btn.pack(pady=10)

        # Footer
        tk.Label(self, text="v1.0 - Anti-Autofill", font=("Arial", 8), fg="#999").pack(
            side=tk.BOTTOM, pady=5
        )

    def load_settings(self):
        # Load reset time from config
        saved_time = config_manager.get("reset_time")
        self.reset_time_var.set(str(saved_time))

    def update_status(self, text, color="black"):
        self.status_label.config(text=text, fg=color)

    def on_bot_stop(self, status, color):
        self.update_status(status, color)
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.reset_time_entry.config(state=tk.NORMAL)
        self.bot = None

    def start_bot(self):
        print("Bot Started")

        # Save current reset time setting
        try:
            new_time = int(self.reset_time_var.get())
            config_manager.set("reset_time", new_time)
        except ValueError:
            messagebox.showerror("Error", "Invalid Reset Time! Must be an integer.")
            return

        self.status_label.config(text="Status: Starting...", fg="green")
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.reset_time_entry.config(state=tk.DISABLED)

        # Start Thread
        self.bot = AntiFateBot(
            update_status_callback=self.update_status, on_stop_callback=self.on_bot_stop
        )
        self.bot.start()

    def stop_bot(self):
        print("Bot Stopping...")
        if self.bot:
            self.bot.stop()
        # on_bot_stop will be called by the thread eventually,
        # but for instant UI feedback we can disable Stop btn now
        self.stop_btn.config(state=tk.DISABLED)

    def calibrate(self):
        messagebox.showinfo(
            "Calibration",
            "Sau khi đóng hộp thoại này, bạn có 3 giây để di chuột đến vị trí cần lấy tọa độ.\n\n"
            "Tool sẽ tự động lấy tọa độ và màu sắc tại đó.",
        )

        # Countdown 3s using after() to prevent freezing UI
        self.status_label.config(text="Calibrating in 3...", fg="blue")
        self.after(1000, lambda: self.status_label.config(text="Calibrating in 2..."))
        self.after(2000, lambda: self.status_label.config(text="Calibrating in 1..."))
        self.after(3000, self.perform_calibration)

    def perform_calibration(self):
        try:
            # 1. Capture Position first
            x, y = pyautogui.position()

            # 2. Move mouse away to remove hover effect (Anti-Hover Tech)
            # Move to (10, 10) - safe corner usually
            pyautogui.moveTo(10, 10)

            # 3. Wait for UI to update (fade out animation)
            self.status_label.config(text="Waiting for hover reset...", fg="orange")
            self.update()  # Force UI update
            time.sleep(1.0)  # 1s should be enough for any animation

            # 4. Capture Color at original Position
            # pixel() might fail on some systems/multi-monitor setups without Pillow adjustments
            # but usually fine on Windows main monitor
            r, g, b = pyautogui.pixel(x, y)

            result_text = f"Pos: [{x}, {y}]\nColor: [{r}, {g}, {b}]"

            # Copy to clipboard for convenience
            self.clipboard_clear()
            self.clipboard_append(result_text)
            self.update()  # Keep clipboard content after window close if needed

            self.status_label.config(text="Captured!", fg="blue")

            # 5. Move mouse back to original pos (optional, but nice UX)
            pyautogui.moveTo(x, y)

            messagebox.showinfo(
                "Result (Copied to Clipboard)",
                f"Tọa độ và Màu sắc (Đã khử Hover):\n\n{result_text}\n\n"
                "Giá trị này đã được copy vào clipboard. Hãy dán vào config.json nếu cần.",
            )

        except Exception as e:
            messagebox.showerror("Error", f"Failed to get pixel info:\n{e}")

        finally:
            self.status_label.config(text="Status: Ready", fg="gray")

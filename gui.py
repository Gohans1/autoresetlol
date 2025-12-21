import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import pyautogui
from config import config_manager
import time
from bot import AntiFateBot
import threading

# Set Theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")  # We will override colors manually for Shadcn look


class AntiFateApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window Setup
        self.title("Anti-Fate Engine")
        self.geometry("340x300")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        # Shadcn Zinc-950 background (Approximate, CTk uses its own dark gray by default)
        # We can try to set it, but usually standard dark is fine.
        # Let's keep standard dark for better consistency with title bar.

        self.bot = None

        self.create_widgets()
        self.load_settings()

    def create_widgets(self):
        # Main Layout: Single column, centered with padding
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure((0, 1, 2, 3, 4), weight=1)

        # 1. Header / Status
        self.status_label = ctk.CTkLabel(
            self,
            text="Status: Ready",
            font=("Inter", 14, "bold"),
            text_color="#a1a1aa",  # Zinc-400
        )
        self.status_label.pack(pady=(25, 15))

        # 2. Reset Time Input
        input_frame = ctk.CTkFrame(self, fg_color="transparent")
        input_frame.pack(pady=10)

        ctk.CTkLabel(
            input_frame,
            text="Reset Timer (s):",
            font=("Inter", 12),
            text_color="#e4e4e7",  # Zinc-200
        ).pack(side="left", padx=(0, 10))

        self.reset_time_var = tk.StringVar()
        self.reset_time_entry = ctk.CTkEntry(
            input_frame,
            textvariable=self.reset_time_var,
            width=60,
            font=("Inter", 12),
            fg_color="#18181b",  # Zinc-900
            border_color="#3f3f46",  # Zinc-700
            text_color="#fafafa",  # Zinc-50
            justify="center",
        )
        self.reset_time_entry.pack(side="left")

        # 3. Action Buttons (Start / Stop)
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=15)

        # Primary Button (Start) - White bg, Black text
        self.start_btn = ctk.CTkButton(
            btn_frame,
            text="START",
            font=("Inter", 12, "bold"),
            width=100,
            height=32,
            fg_color="#fafafa",  # Zinc-50
            text_color="#18181b",  # Zinc-900
            hover_color="#d4d4d8",  # Zinc-300
            corner_radius=6,
            command=self.start_bot,
        )
        self.start_btn.pack(side="left", padx=5)

        # Destructive Button (Stop) - Muted Red
        self.stop_btn = ctk.CTkButton(
            btn_frame,
            text="STOP",
            font=("Inter", 12, "bold"),
            width=100,
            height=32,
            fg_color="#7f1d1d",  # Red-900
            text_color="#fecaca",  # Red-200
            hover_color="#991b1b",  # Red-800
            corner_radius=6,
            state="disabled",
            command=self.stop_bot,
        )
        self.stop_btn.pack(side="left", padx=5)

        # 4. Secondary Action (Calibrate) - Outline Style
        self.calib_btn = ctk.CTkButton(
            self,
            text="Calibrate Coordinates",
            font=("Inter", 12),
            width=210,
            height=32,
            fg_color="transparent",
            border_width=1,
            border_color="#3f3f46",  # Zinc-700
            text_color="#a1a1aa",  # Zinc-400
            hover_color="#27272a",  # Zinc-800
            corner_radius=6,
            command=self.calibrate,
        )
        self.calib_btn.pack(pady=10)

        # 5. Footer
        ctk.CTkLabel(
            self,
            text="v6.0 • Anti-Autofill",
            font=("Inter", 10),
            text_color="#52525b",  # Zinc-600
        ).pack(side="bottom", pady=10)

    def load_settings(self):
        saved_time = config_manager.get("reset_time")
        self.reset_time_var.set(str(saved_time))

    def update_status(self, text, color=None):
        # Map logical colors to Shadcn palette
        # Green -> Emerald-400 (#34d399)
        # Red -> Rose-400 (#fb7185)
        # Blue -> Sky-400 (#38bdf8)
        # Orange -> Amber-400 (#fbbf24)
        # Default/Gray -> Zinc-400 (#a1a1aa)

        color_map = {
            "green": "#34d399",
            "red": "#fb7185",
            "blue": "#38bdf8",
            "orange": "#fbbf24",
            "black": "#a1a1aa",  # Default in dark mode
            "gray": "#a1a1aa",
        }

        final_color = color_map.get(str(color).lower(), "#a1a1aa")
        self.status_label.configure(text=text, text_color=final_color)

    def on_bot_stop(self, status, color):
        self.update_status(status, color)
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.reset_time_entry.configure(state="normal")
        self.bot = None

    def start_bot(self):
        print("Bot Started")
        try:
            new_time = int(self.reset_time_var.get())
            config_manager.set("reset_time", new_time)
        except ValueError:
            messagebox.showerror("Error", "Invalid Reset Time! Must be an integer.")
            return

        self.update_status("Status: Running...", "green")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.reset_time_entry.configure(state="disabled")

        self.bot = AntiFateBot(
            update_status_callback=self.update_status, on_stop_callback=self.on_bot_stop
        )
        self.bot.start()

    def stop_bot(self):
        print("Bot Stopping...")
        if self.bot:
            self.bot.stop()
        self.stop_btn.configure(state="disabled")

    def calibrate(self):
        messagebox.showinfo(
            "Calibration",
            "After closing this, you have 3 seconds to hover over the target.\n\n"
            "Tool will auto-capture pos & color (Anti-Hover enabled).",
        )

        self.update_status("Calibrating in 3...", "blue")
        self.after(1000, lambda: self.update_status("Calibrating in 2...", "blue"))
        self.after(2000, lambda: self.update_status("Calibrating in 1...", "blue"))
        self.after(3000, self.perform_calibration)

    def perform_calibration(self):
        def _calib_task():
            try:
                x, y = pyautogui.position()

                # Anti-Hover: Move away
                pyautogui.moveTo(10, 10)

                # Update UI from thread? No, use after() or simple wait
                # Here we are in a thread (if using threading) or main thread.
                # Since perform_calibration is called by after(), it's in main thread.
                # Blocking main thread for 1s is 'okay' for simple tool, but better to force update.

                # Since we can't sleep in main thread without freezing UI,
                # we should use another after() sequence or just accept a micro-freeze.
                # But for smoother UX, let's use a small helper or just sleep.
                # Given the requirements, a 1s freeze is acceptable for "Wait for hover reset".

                self.after(
                    0,
                    lambda: self.update_status("Waiting for hover reset...", "orange"),
                )
                time.sleep(1.0)

                r, g, b = pyautogui.pixel(x, y)
                result_text = f"Pos: [{x}, {y}]\nColor: [{r}, {g}, {b}]"

                # Copy to clipboard
                self.clipboard_clear()
                self.clipboard_append(result_text)

                self.after(0, lambda: self.update_status("Captured!", "blue"))

                # Move back
                pyautogui.moveTo(x, y)

                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Result (Copied)",
                        f"Captured (Anti-Hover):\n\n{result_text}\n\nCopied to clipboard.",
                    ),
                )

                self.after(0, lambda: self.update_status("Status: Ready", "gray"))

            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", f"Failed: {e}"))

        # Run calibration in a separate thread to avoid freezing the "Waiting" UI update
        threading.Thread(target=_calib_task, daemon=True).start()

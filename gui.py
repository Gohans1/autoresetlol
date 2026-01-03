import customtkinter as ctk  # type: ignore
import tkinter as tk
from tkinter import messagebox
import pyautogui
import time
import threading
from typing import Optional, Dict

from config import config_manager
from bot import AntiFateBot
from utils.windows import GammaController, set_autostart
from constants import AppConfig, Colors, UIStatus
from logger import logger

# Set Theme
ctk.set_appearance_mode(AppConfig.THEME_MODE)
ctk.set_default_color_theme(AppConfig.THEME_COLOR)


class CardFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=Colors.CARD,
            border_color=Colors.BORDER,
            border_width=1,
            corner_radius=8,
            **kwargs,
        )


class AntiFateApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window Setup
        self.title(AppConfig.APP_NAME)
        self.geometry(AppConfig.GEOMETRY)
        self.resizable(False, False)
        self.configure(fg_color=Colors.BG)

        self.bot: Optional[AntiFateBot] = None
        self.dimmer = GammaController()

        # Variables
        self.reset_time_var = tk.StringVar()
        self.reset_time_var.trace_add("write", self._on_time_changed)
        self.dimmer_enabled_var = ctk.BooleanVar(value=True)
        self.reset_sound_enabled_var = ctk.BooleanVar(value=True)
        self.auto_startup_enabled_var = ctk.BooleanVar(value=False)

        self.create_widgets()
        self.load_settings()

        # Handle Window Close to reset gamma
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self) -> None:
        # Main Layout: Use a scrollable or fixed container with padding
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=20)

        # 1. Status Card
        status_card = CardFrame(main_container)
        status_card.pack(fill="x", pady=(0, 15))

        self.status_label = ctk.CTkLabel(
            status_card,
            text=UIStatus.READY,
            font=(AppConfig.FONT_FAMILY, 14, "bold"),
            text_color=Colors.MUTED_FG,
        )
        self.status_label.pack(pady=15)

        # 2. Settings Card
        settings_card = CardFrame(main_container)
        settings_card.pack(fill="x", pady=(0, 15))

        # Timer Section
        timer_row = ctk.CTkFrame(settings_card, fg_color="transparent")
        timer_row.pack(fill="x", padx=15, pady=(15, 10))

        ctk.CTkLabel(
            timer_row,
            text="Reset Threshold",
            font=(AppConfig.FONT_FAMILY, 12, "bold"),
            text_color=Colors.FG,
        ).pack(side="left")

        self.reset_time_entry = ctk.CTkEntry(
            timer_row,
            textvariable=self.reset_time_var,
            width=60,
            height=28,
            font=(AppConfig.FONT_FAMILY, 12),
            fg_color=Colors.SECONDARY,
            border_color=Colors.BORDER,
            text_color=Colors.PRIMARY,
            justify="center",
            corner_radius=4,
        )
        self.reset_time_entry.pack(side="right")

        ctk.CTkLabel(
            timer_row,
            text="sec",
            font=(AppConfig.FONT_FAMILY, 12),
            text_color=Colors.MUTED_FG,
        ).pack(side="right", padx=5)

        # Separator (Subtle line)
        ctk.CTkFrame(settings_card, fg_color=Colors.BORDER, height=1).pack(
            fill="x", padx=15, pady=5
        )

        # Dimmer Control
        dimmer_row = ctk.CTkFrame(settings_card, fg_color="transparent")
        dimmer_row.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(
            dimmer_row,
            text="Ghost Dimmer",
            font=(AppConfig.FONT_FAMILY, 12),
            text_color=Colors.FG,
        ).pack(side="left")

        self.dimmer_switch = ctk.CTkSwitch(
            dimmer_row,
            text="",
            width=40,
            variable=self.dimmer_enabled_var,
            command=self.toggle_dimmer,
            progress_color=Colors.GREEN,
            fg_color=Colors.SECONDARY,
        )
        self.dimmer_switch.pack(side="right")

        self.dimmer_slider = ctk.CTkSlider(
            settings_card,
            from_=0,
            to=100,
            number_of_steps=100,
            command=self.change_brightness,
            fg_color=Colors.SECONDARY,
            progress_color=Colors.PRIMARY,
            button_color=Colors.PRIMARY,
            button_hover_color=Colors.FG,
            height=16,
        )
        self.dimmer_slider.set(100)
        self.dimmer_slider.pack(fill="x", padx=15, pady=(0, 15))

        # 3. Preferences Card
        pref_card = CardFrame(main_container)
        pref_card.pack(fill="x", pady=(0, 15))

        # Sound Toggle
        sound_row = ctk.CTkFrame(pref_card, fg_color="transparent")
        sound_row.pack(fill="x", padx=15, pady=(12, 6))

        ctk.CTkLabel(
            sound_row,
            text="Sound Notification",
            font=(AppConfig.FONT_FAMILY, 12),
            text_color=Colors.FG,
        ).pack(side="left")

        self.sound_switch = ctk.CTkSwitch(
            sound_row,
            text="",
            width=40,
            variable=self.reset_sound_enabled_var,
            command=self.toggle_sound,
            progress_color=Colors.GREEN,
            fg_color=Colors.SECONDARY,
        )
        self.sound_switch.pack(side="right")

        # Startup Toggle
        startup_row = ctk.CTkFrame(pref_card, fg_color="transparent")
        startup_row.pack(fill="x", padx=15, pady=(6, 12))

        ctk.CTkLabel(
            startup_row,
            text="Launch on Startup",
            font=(AppConfig.FONT_FAMILY, 12),
            text_color=Colors.FG,
        ).pack(side="left")

        self.startup_switch = ctk.CTkSwitch(
            startup_row,
            text="",
            width=40,
            variable=self.auto_startup_enabled_var,
            command=self.toggle_startup,
            progress_color=Colors.GREEN,
            fg_color=Colors.SECONDARY,
        )
        self.startup_switch.pack(side="right")

        # 4. Action Buttons
        btn_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        btn_frame.pack(fill="x", side="bottom")

        self.start_btn = ctk.CTkButton(
            btn_frame,
            text="START BOT",
            font=(AppConfig.FONT_FAMILY, 13, "bold"),
            height=40,
            fg_color=Colors.PRIMARY,
            text_color=Colors.PRIMARY_FG,
            hover_color=Colors.FG,
            corner_radius=8,
            command=self.start_bot,
        )
        self.start_btn.pack(fill="x", pady=(0, 10))

        self.stop_btn = ctk.CTkButton(
            btn_frame,
            text="STOP",
            font=(AppConfig.FONT_FAMILY, 13, "bold"),
            height=40,
            fg_color=Colors.RED,
            text_color=Colors.PRIMARY_FG,
            hover_color="#e57373",  # Brighter red on hover
            corner_radius=8,
            state="disabled",
            command=self.stop_bot,
        )
        self.stop_btn.pack(fill="x")

        # 5. Footer
        ctk.CTkLabel(
            self,
            text=f"{AppConfig.VERSION} • Anti-Fate Engine",
            font=(AppConfig.FONT_FAMILY, 10),
            text_color=Colors.MUTED_FG,
        ).pack(side="bottom", pady=5)

    def _on_time_changed(self, var, index, mode) -> None:
        """Auto-save reset time when user types."""
        val = self.reset_time_var.get()
        if val.isdigit():
            config_manager.set("reset_time", int(val))

    def load_settings(self) -> None:
        # Load Reset Time
        saved_time = config_manager.get("reset_time")
        self.reset_time_var.set(str(saved_time))

        # Load Dimmer Settings
        dimmer_val = config_manager.get("dimmer_value") or 100
        dimmer_enabled = config_manager.get("dimmer_enabled")
        if dimmer_enabled is None:
            dimmer_enabled = True

        self.dimmer_slider.set(float(dimmer_val))
        self.dimmer_enabled_var.set(dimmer_enabled)

        # Load Sound Settings
        saved_sound = config_manager.get("reset_sound_enabled")
        if saved_sound is None:
            saved_sound = True
        self.reset_sound_enabled_var.set(saved_sound)

        # Load Startup Settings
        saved_startup = config_manager.get("auto_startup_enabled")
        if saved_startup is None:
            saved_startup = False
        self.auto_startup_enabled_var.set(saved_startup)

        # Apply settings immediately
        self.toggle_dimmer(save=False)

    def toggle_sound(self) -> None:
        is_enabled = self.reset_sound_enabled_var.get()
        config_manager.set("reset_sound_enabled", is_enabled)
        logger.info(f"Sound alert toggled: {is_enabled}")

    def toggle_startup(self) -> None:
        is_enabled = self.auto_startup_enabled_var.get()
        config_manager.set("auto_startup_enabled", is_enabled)
        set_autostart(AppConfig.APP_NAME, add=is_enabled)
        logger.info(f"Auto Startup toggled: {is_enabled}")

    def toggle_dimmer(self, save: bool = True) -> None:
        is_enabled = self.dimmer_enabled_var.get()
        current_val = self.dimmer_slider.get()

        if save:
            config_manager.set("dimmer_enabled", is_enabled)

        if is_enabled:
            self.dimmer_slider.configure(state="normal", button_color=Colors.PRIMARY)

            # Smooth Step Down
            if current_val < 90:
                temp_val = 90
                while temp_val > current_val:
                    self.dimmer.set_brightness(int(temp_val))
                    temp_val -= 20
                    time.sleep(0.015)

            # Final set
            self.dimmer.set_brightness(int(current_val))
        else:
            self.dimmer_slider.configure(
                state="disabled", button_color=Colors.SECONDARY
            )
            self.dimmer.set_brightness(100)

    def change_brightness(self, value: float) -> None:
        # Only apply if enabled
        if self.dimmer_enabled_var.get():
            self.dimmer.set_brightness(int(value))
            config_manager.set("dimmer_value", int(value))

    def update_status(self, text: str, color: Optional[str] = None) -> None:
        # Map logical colors to constants
        color_map: Dict[str, str] = {
            "green": Colors.STATUS_GREEN,
            "red": Colors.STATUS_RED,
            "blue": Colors.STATUS_BLUE,
            "orange": Colors.STATUS_ORANGE,
            "gray": Colors.STATUS_GRAY,
            "purple": Colors.PURPLE,  # Updated
        }
        final_color = color_map.get(str(color).lower(), Colors.STATUS_GRAY)

        # Thread-safe update
        self.after(
            0, lambda: self.status_label.configure(text=text, text_color=final_color)
        )

    def on_bot_stop(self, status: str, color: str) -> None:
        def _update_ui():
            self.update_status(status, color)
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            self.reset_time_entry.configure(state="normal")
            self.bot = None

        self.after(0, _update_ui)

    def reset_dimmer(self) -> None:
        """Force reset dimmer to 100% (Success callback)."""
        logger.info("Bot success confirmed. Resetting dimmer to 100%.")
        self.after(0, lambda: self.dimmer_slider.set(100))
        self.after(0, lambda: self.dimmer.set_brightness(100))

    def start_bot(self) -> None:
        logger.info("Starting bot...")
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
            update_status_callback=self.update_status,
            on_stop_callback=self.on_bot_stop,
            on_success_callback=self.reset_dimmer,
        )
        self.bot.start()

    def stop_bot(self) -> None:
        logger.info("Bot Stopping...")
        if self.bot:
            self.bot.stop()
        self.stop_btn.configure(state="disabled")

    def on_closing(self) -> None:
        """Cleanup before closing"""
        logger.info("Closing application...")
        try:
            if self.bot:
                # Disable callback to avoid updating destroyed widgets
                self.bot.on_stop_callback = None
                self.bot.stop()

            if self.dimmer:
                # Reset brightness to 100% before exit
                self.dimmer.close()

            self.destroy()
            # Explicitly exit to ensure all threads are killed
            import sys

            sys.exit(0)
        except Exception as e:
            logger.error(f"Error during closing: {e}")
            import os

            os._exit(0)

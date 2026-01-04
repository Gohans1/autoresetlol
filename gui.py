import customtkinter as ctk  # type: ignore
import tkinter as tk
from tkinter import messagebox
import webbrowser
import pyautogui
import time
import threading
import os
from typing import Optional, Dict
from PIL import Image, ImageTk, ImageDraw

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


class InfoModal(ctk.CTkToplevel):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.title("Information")
        self.geometry("300x200")
        self.resizable(False, False)
        self.configure(fg_color=Colors.BG)

        # Center over parent
        self.update_idletasks()
        parent_x = master.winfo_x()
        parent_y = master.winfo_y()
        parent_w = master.winfo_width()
        parent_h = master.winfo_height()

        x = parent_x + (parent_w // 2) - (300 // 2)
        y = parent_y + (parent_h // 2) - (200 // 2)
        self.geometry(f"+{x}+{y}")

        self.attributes("-topmost", True)
        self.focus_set()

        # UI Elements
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            container,
            text="RESOLUTION DISCLAIMER",
            font=(AppConfig.FONT_FAMILY, 14, "bold"),
            text_color=Colors.PRIMARY,
        ).pack(pady=(0, 10))

        ctk.CTkLabel(
            container,
            text="This engine is specifically tuned for League client at these resolutions:",
            font=(AppConfig.FONT_FAMILY, 11),
            text_color=Colors.MUTED_FG,
            wraplength=250,
        ).pack(pady=(0, 15))

        badge_frame = ctk.CTkFrame(
            container, fg_color=Colors.SECONDARY, corner_radius=6
        )
        badge_frame.pack(pady=(0, 20))

        ctk.CTkLabel(
            badge_frame,
            text="1920x1080 • 1600x900",
            font=("JetBrains Mono", 12, "bold"),
            text_color=Colors.BLUE,
            padx=12,
            pady=4,
        ).pack()

        ctk.CTkButton(
            container,
            text="ACKNOWLEDGE",
            font=(AppConfig.FONT_FAMILY, 11, "bold"),
            height=32,
            fg_color=Colors.CARD,
            border_color=Colors.BORDER,
            border_width=1,
            text_color=Colors.FG,
            hover_color=Colors.SECONDARY,
            command=self.destroy,
        ).pack(fill="x")


class AntiFateApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        # self.withdraw()  # Temporarily disabled to debug visibility

        # Load geometry from config
        saved_geo = config_manager.get("window_geometry")
        if saved_geo:
            try:
                self.geometry(saved_geo)
            except Exception as e:
                logger.error(f"Failed to apply saved geometry: {e}")
                self.geometry(AppConfig.GEOMETRY)
        else:
            self.geometry(AppConfig.GEOMETRY)

        self.minsize(360, 540)
        self.resizable(True, True)  # Allow resizing
        self.configure(fg_color=Colors.BG)

        # Window Setup
        self.title(AppConfig.APP_NAME)

        # Animation state
        self.pulse_val = 0.0
        self.pulse_dir = 1
        self.pulse_speed = 0.05
        self.current_state_color = Colors.STATUS_GRAY
        self.current_state_color_name = "gray"
        self.is_animating = True
        self._geo_save_timer = None

        # Set Window Icon
        try:
            # For Taskbar and Titlebar
            if os.path.exists(AppConfig.APP_ICON):
                self.iconbitmap(AppConfig.APP_ICON)

                # Use AppID to force Windows to show the correct icon on the taskbar
                import ctypes

                myappid = "sisyphus.autoresetlol.antifate.v7"
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception as e:
            logger.error(f"Could not set window icon: {e}")

        self.bot: Optional[AntiFateBot] = None
        self.dimmer = GammaController()
        self._info_modal: Optional[ctk.CTkToplevel] = None

        # Variables
        self.reset_time_var = tk.StringVar()
        self.reset_time_var.trace_add("write", self._on_time_changed)
        self.dimmer_enabled_var = ctk.BooleanVar(value=True)
        self.reset_sound_enabled_var = ctk.BooleanVar(value=True)
        self.auto_startup_enabled_var = ctk.BooleanVar(value=False)
        self.sound_volume_var = tk.IntVar(value=50)

        self._setup_icons()
        self.create_widgets()
        self.load_settings()

        # Final show
        self.update_idletasks()
        # self.deiconify() # Disabled with withdraw

        # Bind events
        self.bind("<Configure>", self._on_window_configure)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _setup_icons(self) -> None:
        """Initialize all state icons using PIL and Load Avatar."""
        self.icons = {}
        icon_colors = {
            "gray": Colors.MUTED_FG,
            "blue": Colors.BLUE,
            "green": Colors.GREEN,
            "purple": Colors.PURPLE,
            "red": Colors.RED,
            "orange": Colors.ORANGE,
        }

        # Load Avatar for the heartbeat base
        try:
            avatar_img = Image.open(AppConfig.APP_AVATAR).convert("RGBA")
            # Create a circular mask for the avatar
            mask = Image.new("L", avatar_img.size, 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0) + avatar_img.size, fill=255)

            # Apply mask
            circular_avatar = Image.new("RGBA", avatar_img.size, (0, 0, 0, 0))
            circular_avatar.paste(avatar_img, (0, 0), mask=mask)
            self.avatar_base = circular_avatar
        except Exception as e:
            logger.error(f"Could not load avatar: {e}")
            self.avatar_base = Image.new("RGBA", (100, 100), Colors.SECONDARY)

        for name, color in icon_colors.items():
            # Create a 64x64 image for the status display
            size = 64
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Draw glow/aura
            padding = 4
            draw.ellipse(
                [padding, padding, size - padding - 1, size - padding - 1],
                outline=color,
                width=2,
            )

            # Draw symbol in center
            center = size // 2
            s = 10
            if name == "green":
                draw.line(
                    [center - s, center, center - 2, center + s - 4],
                    fill="white",
                    width=4,
                )
                draw.line(
                    [center - 2, center + s - 4, center + s, center - s + 2],
                    fill="white",
                    width=4,
                )
            elif name == "blue":
                draw.arc(
                    [center - s, center - s, center + s, center + s],
                    start=45,
                    end=315,
                    fill="white",
                    width=4,
                )
            elif name == "purple":
                draw.ellipse(
                    [center - s, center - s, center + s, center + s],
                    outline="white",
                    width=3,
                )
                draw.line(
                    [center, center, center, center - s + 2], fill="white", width=2
                )
                draw.line(
                    [center, center, center + s - 4, center], fill="white", width=2
                )
            elif name == "red" or name == "orange":
                draw.line(
                    [center, center - s, center, center + 2], fill="white", width=4
                )
                draw.ellipse(
                    [center - 2, center + s - 2, center + 2, center + s + 2],
                    fill="white",
                )

                draw.ellipse(
                    [center - 2, center + s - 2, center + 2, center + s + 2],
                    fill="white",
                )
            elif name == "gray":
                draw.ellipse(
                    [center - 4, center - 4, center + 4, center + 4], fill="white"
                )

            self.icons[name] = ctk.CTkImage(
                light_image=img, dark_image=img, size=(64, 64)
            )

    def create_widgets(self) -> None:
        # 5. Footer (Pack FIRST with side=bottom to pin it at the very bottom)
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=24, pady=(0, 15))

        # Author Link
        author_frame = ctk.CTkFrame(footer, fg_color="transparent")
        author_frame.pack(side="left")

        ctk.CTkLabel(
            author_frame,
            text="Created by ",
            font=(AppConfig.FONT_FAMILY, 11),
            text_color=Colors.MUTED_FG,
        ).pack(side="left")

        self.author_link = ctk.CTkLabel(
            author_frame,
            text="Gohans",
            font=(AppConfig.FONT_FAMILY, 11, "bold"),
            text_color=Colors.MUTED_FG,
            cursor="hand2",
        )
        self.author_link.pack(side="left")
        self.author_link.bind(
            "<Enter>", lambda e: self.author_link.configure(text_color=Colors.PRIMARY)
        )
        self.author_link.bind(
            "<Leave>", lambda e: self.author_link.configure(text_color=Colors.MUTED_FG)
        )
        self.author_link.bind(
            "<Button-1>", lambda e: webbrowser.open("https://x.com/GohansVN")
        )

        # Resolution Badge
        self.badge_frame = ctk.CTkFrame(
            footer,
            fg_color=Colors.SECONDARY,
            corner_radius=4,
            border_width=1,
            border_color=Colors.BORDER,
            cursor="hand2",
        )
        self.badge_frame.pack(side="right")

        self.badge_label = ctk.CTkLabel(
            self.badge_frame,
            text="1080p | 1600x900",
            font=("JetBrains Mono", 10, "bold"),
            text_color=Colors.MUTED_FG,
            padx=8,
            pady=2,
        )
        self.badge_label.pack()

        # Add interactions to badge
        for widget in [self.badge_frame, self.badge_label]:
            widget.bind(
                "<Enter>",
                lambda e: self.badge_frame.configure(border_color=Colors.PRIMARY),
            )
            widget.bind(
                "<Leave>",
                lambda e: self.badge_frame.configure(border_color=Colors.BORDER),
            )
            widget.bind("<Button-1>", lambda e: self.show_info_modal())

        # Main Layout (Pack SECOND with expand=True to fill remaining space)
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=24, pady=(24, 0))

        # 1. Status Heartbeat Card
        self.status_card = CardFrame(main_container)
        self.status_card.pack(fill="x", pady=(0, 15))

        # Status Label (Secondary)
        self.status_label = ctk.CTkLabel(
            self.status_card,
            text=UIStatus.READY.upper(),
            font=(AppConfig.FONT_FAMILY, 11, "bold"),
            text_color=Colors.MUTED_FG,
        )
        self.status_label.pack(pady=(24, 0))

        # Giant Timer (Hero)
        self.timer_label = ctk.CTkLabel(
            self.status_card,
            text="0 / 0",
            font=("JetBrains Mono", 64, "bold"),
            text_color=Colors.PRIMARY,
        )
        self.timer_label.pack(pady=(0, 10))

        # Info Button (Top Right)
        self.info_btn = ctk.CTkButton(
            self.status_card,
            text="i",
            width=20,
            height=20,
            corner_radius=10,
            fg_color="transparent",
            text_color=Colors.MUTED_FG,
            hover_color=Colors.SECONDARY,
            font=(AppConfig.FONT_FAMILY, 12, "italic", "bold"),
            command=self.show_info_modal,
        )
        self.info_btn.place(relx=0.96, rely=0.08, anchor="ne")

        # Hidden overlay icon
        self.status_icon = ctk.CTkLabel(
            self.status_card, text="", image=self.icons["gray"]
        )

        # Dynamic Progress Bar
        self.status_progress = ctk.CTkProgressBar(
            self.status_card,
            height=2,
            fg_color=Colors.SECONDARY,
            progress_color=Colors.BLUE,
        )
        self.status_progress.set(0)
        self.status_progress.pack(fill="x", padx=40, pady=(0, 24))

        # Volume Slider Row
        volume_row = ctk.CTkFrame(main_container, fg_color="transparent")
        volume_row.pack(fill="x", pady=(0, 15), padx=5)

        self.volume_icon = ctk.CTkLabel(
            volume_row, text="🔊", font=(AppConfig.FONT_FAMILY, 14)
        )
        self.volume_icon.pack(side="left", padx=(0, 10))

        self.volume_slider = ctk.CTkSlider(
            volume_row,
            from_=0,
            to=100,
            number_of_steps=100,
            variable=self.sound_volume_var,
            command=self._on_volume_changed,
            fg_color=Colors.SECONDARY,
            progress_color=Colors.BLUE,
            button_color=Colors.PRIMARY,
            height=16,
        )
        self.volume_slider.pack(side="left", fill="x", expand=True)

        self.volume_label = ctk.CTkLabel(
            volume_row, text="50%", font=(AppConfig.FONT_FAMILY, 11, "bold"), width=40
        )
        self.volume_label.pack(side="right", padx=(5, 0))

        # Start animation
        self.animate_heartbeat()

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

        # Separator
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
        self.stop_btn.pack(fill="x", pady=(0, 20))

    def _on_time_changed(self, var, index, mode) -> None:
        """Auto-save reset time when user types."""
        val = self.reset_time_var.get()
        if val.isdigit():
            config_manager.set("reset_time", int(val))
            self.update_status(
                self.status_label.cget("text"), self.current_state_color_name
            )

    def _on_volume_changed(self, value: float) -> None:
        """Update volume setting and label."""
        vol = int(value)
        self.volume_label.configure(text=f"{vol}%")
        config_manager.set("sound_volume", vol)

    def _on_window_configure(self, event) -> None:
        """Capture window resize/move with debounce."""
        if event.widget == self:
            if self.state() == "normal":
                if self._geo_save_timer:
                    self.after_cancel(self._geo_save_timer)
                self._geo_save_timer = self.after(500, self._save_geometry)

    def _save_geometry(self) -> None:
        """Save current window geometry to config."""
        if self.state() == "normal":
            new_geo = self.geometry()
            config_manager.set("window_geometry", new_geo)
            logger.info(f"Window geometry saved: {new_geo}")

    def load_settings(self) -> None:
        # Load Reset Time
        saved_time = config_manager.get("reset_time")
        self.reset_time_var.set(str(saved_time))

        # Load Volume
        saved_vol = config_manager.get("sound_volume") or 50
        self.sound_volume_var.set(saved_vol)
        self.volume_label.configure(text=f"{saved_vol}%")

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

    def show_info_modal(self) -> None:
        """Trigger the professional info modal (Singleton pattern)."""
        if self._info_modal is not None and self._info_modal.winfo_exists():
            self._info_modal.focus_set()
            self._info_modal.attributes("-topmost", True)
            return
        self._info_modal = InfoModal(self)

    def animate_heartbeat(self) -> None:
        """Dynamic pulsing animation for the status card."""
        if not self.is_animating:
            return

        # Update pulse value
        self.pulse_val += self.pulse_speed * self.pulse_dir
        if self.pulse_val >= 1.0:
            self.pulse_val = 1.0
            self.pulse_dir = -1
        elif self.pulse_val <= 0.0:
            self.pulse_val = 0.0
            self.pulse_dir = 1

        # Apply pulse to border color and shadow effect
        alpha = int(25 + (self.pulse_val * 50))  # Range 25-75 for subtle pulse

        # We can't easily do hex alpha in CTk border_color without issues on some platforms,
        # but we can alternate between the status color and a muted version.
        try:
            # Simple pulsing logic: interpolate between status color and BG
            # For simplicity in this env, we'll just toggle border width or a slightly different color
            if self.pulse_dir == 1:
                self.status_card.configure(border_color=self.current_state_color)
            else:
                self.status_card.configure(border_color=Colors.BORDER)
        except:
            pass

        self.after(50, self.animate_heartbeat)

    def update_status(self, text: str, color: Optional[str] = None) -> None:
        # Map logical colors to constants
        color_map: Dict[str, str] = {
            "green": Colors.STATUS_GREEN,
            "red": Colors.STATUS_RED,
            "blue": Colors.STATUS_BLUE,
            "orange": Colors.STATUS_ORANGE,
            "gray": Colors.STATUS_GRAY,
            "purple": Colors.PURPLE,
        }
        color_str = str(color).lower()
        final_color = color_map.get(color_str, Colors.STATUS_GRAY)
        self.current_state_color = final_color
        self.current_state_color_name = color_str

        # Adjust animation speed based on state
        if color_str == "blue":  # Searching
            self.pulse_speed = 0.04
        elif color_str == "purple":  # Verifying
            self.pulse_speed = 0.1
        elif color_str == "red":  # Resetting/Dodge
            self.pulse_speed = 0.15
        elif color_str == "green":  # Match Found / Standby
            self.pulse_speed = 0.02
        else:
            self.pulse_speed = 0.02

        # Parse progress and timer if searching
        progress = 0.0
        timer_text = "0 / 0"
        status_text = text.upper()
        text_lower = text.lower()

        if "searching" in text_lower:
            try:
                # Extract (elapsed/threshold)
                parts = text.split("(")[1].split(")")[0].split("/")
                current = int(parts[0])
                total = int(parts[1])
                progress = min(1.0, current / total)
                timer_text = f"{current} / {total}"
                status_text = "SEARCHING..."
            except:
                pass
        elif "ready" in text_lower:
            timer_text = "0 / " + str(config_manager.get("reset_time"))
            status_text = "READY"
        elif "stopped" in text_lower:
            timer_text = "OFF"
            status_text = "STOPPED"
        elif "verifying" in text_lower:
            try:
                # Extract remaining seconds
                val = text.split("... ")[1].replace("s", "")
                timer_text = f"FIXING {val}"
                status_text = "VERIFYING..."
            except:
                timer_text = "CONFIRM"

        # Thread-safe update
        self.after(
            0,
            lambda: [
                self.status_label.configure(
                    text=status_text, text_color=Colors.MUTED_FG
                ),
                self.timer_label.configure(text=timer_text, text_color=final_color),
                self.status_progress.set(progress),
                self.status_progress.configure(progress_color=final_color),
            ],
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

        self.update_status("Status: Running...", "blue")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.reset_time_entry.configure(state="disabled")

        self.bot = AntiFateBot(
            update_status_callback=self.update_status,
            on_stop_callback=self.on_bot_stop,
            on_success_callback=self.reset_dimmer,
        )
        if self.bot:
            self.bot.start()

    def stop_bot(self) -> None:
        logger.info("Bot Stopping...")
        if self.bot:
            self.bot.stop()
        self.stop_btn.configure(state="disabled")

    def on_closing(self) -> None:
        """Cleanup before closing"""
        logger.info("Closing application...")
        self.is_animating = False
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

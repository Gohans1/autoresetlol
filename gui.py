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
from constants import AppConfig, Colors, UIStatus, SOUND_OPTIONS, RESOURCE_DIR
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


class SettingsModal(ctk.CTkToplevel):
    """Advanced Settings Modal for coordinate/color configuration and profile management."""

    # Coordinate settings: (config_key, label)
    COORD_SETTINGS = [
        ("find_match_button_pos", "Find Match Button"),
        ("cancel_button_pos", "Cancel Button"),
        ("minimize_btn_pos", "Minimize Button"),
        ("in_queue_pixel_pos", "Queue Detection Pixel"),
        ("accept_match_pixel_pos", "Accept Button Pixel"),
        ("champ_select_pixel_pos", "Champ Select Pixel"),
    ]

    # Color settings: (config_key, label)
    COLOR_SETTINGS = [
        ("in_queue_pixel_color", "Queue Detection Color"),
        ("accept_match_pixel_color", "Accept Button Color"),
        ("champ_select_pixel_color", "Champ Select Color"),
    ]

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.master_app = master
        self.title("Advanced Settings")
        self.geometry("520x650")
        self.resizable(False, True)
        self.configure(fg_color=Colors.BG)

        # Center over parent
        self.update_idletasks()
        parent_x = master.winfo_x()
        parent_y = master.winfo_y()
        parent_w = master.winfo_width()
        parent_h = master.winfo_height()

        x = parent_x + (parent_w // 2) - (520 // 2)
        y = parent_y + (parent_h // 2) - (650 // 2)
        self.geometry(f"+{x}+{y}")

        self.attributes("-topmost", True)
        self.focus_set()

        # Storage for entry widgets
        self.coord_entries: Dict[str, tuple] = {}  # key -> (x_entry, y_entry)
        self.color_entries: Dict[
            str, tuple
        ] = {}  # key -> (r_entry, g_entry, b_entry, preview_frame)

        # Pick mode state
        self._pick_mode_active = False
        self._pick_target_key: Optional[str] = None
        self._pick_overlay: Optional[tk.Toplevel] = None

        self._create_widgets()
        self._load_current_values()

    def _create_widgets(self) -> None:
        """Build the modal UI."""
        # Header with title and close button
        header = ctk.CTkFrame(self, fg_color=Colors.SECONDARY, height=50)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text="⚙️ Advanced Settings",
            font=(AppConfig.FONT_FAMILY, 16, "bold"),
            text_color=Colors.PRIMARY,
        ).pack(side="left", padx=15, pady=10)

        close_btn = ctk.CTkButton(
            header,
            text="✕",
            width=30,
            height=30,
            corner_radius=6,
            fg_color="transparent",
            text_color=Colors.MUTED_FG,
            hover_color=Colors.RED,
            font=(AppConfig.FONT_FAMILY, 14, "bold"),
            command=self.destroy,
        )
        close_btn.pack(side="right", padx=10)

        # Main scrollable container
        main_scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=Colors.BORDER,
            scrollbar_button_hover_color=Colors.RING,
        )
        main_scroll.pack(fill="both", expand=True, padx=15, pady=15)

        # === Profile Section ===
        self._create_profile_section(main_scroll)

        # Separator
        ctk.CTkFrame(main_scroll, fg_color=Colors.BORDER, height=1).pack(
            fill="x", pady=15
        )

        # === Coordinates Section ===
        self._create_coordinates_section(main_scroll)

        # Separator
        ctk.CTkFrame(main_scroll, fg_color=Colors.BORDER, height=1).pack(
            fill="x", pady=15
        )

        # === Color Section ===
        self._create_color_section(main_scroll)

        # Separator
        ctk.CTkFrame(main_scroll, fg_color=Colors.BORDER, height=1).pack(
            fill="x", pady=15
        )

        # NOTE: Auto Dimmer Switch Toggle moved to main UI in v1.11
        # self._create_auto_dimmer_section(main_scroll)

        # Footer
        footer = ctk.CTkFrame(self, fg_color=Colors.SECONDARY, height=50)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        ctk.CTkButton(
            footer,
            text="Save & Close",
            font=(AppConfig.FONT_FAMILY, 12, "bold"),
            height=35,
            fg_color=Colors.GREEN,
            text_color=Colors.BG,
            hover_color="#6b7f2e",
            corner_radius=6,
            command=self._save_and_close,
        ).pack(side="right", padx=15, pady=8)

        ctk.CTkLabel(
            footer,
            text="Changes auto-save on pick",
            font=(AppConfig.FONT_FAMILY, 10),
            text_color=Colors.MUTED_FG,
        ).pack(side="left", padx=15, pady=8)

    def _create_profile_section(self, parent) -> None:
        """Create profile management section."""
        section = CardFrame(parent)
        section.pack(fill="x", pady=(0, 5))

        # Section header
        ctk.CTkLabel(
            section,
            text="📁 Profile Management",
            font=(AppConfig.FONT_FAMILY, 12, "bold"),
            text_color=Colors.PRIMARY,
        ).pack(anchor="w", padx=15, pady=(10, 5))

        # Profile selection row
        select_row = ctk.CTkFrame(section, fg_color="transparent")
        select_row.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(
            select_row,
            text="Current:",
            font=(AppConfig.FONT_FAMILY, 11),
            text_color=Colors.FG,
        ).pack(side="left", padx=(0, 10))

        self.profile_dropdown = ctk.CTkOptionMenu(
            select_row,
            values=config_manager.get_profile_names(),
            command=self._on_profile_changed,
            font=(AppConfig.FONT_FAMILY, 11),
            fg_color=Colors.SECONDARY,
            button_color=Colors.BORDER,
            button_hover_color=Colors.RING,
            dropdown_fg_color=Colors.CARD,
            dropdown_hover_color=Colors.SECONDARY,
            text_color=Colors.FG,
            dropdown_text_color=Colors.FG,
            corner_radius=6,
            width=150,
            height=28,
        )
        self.profile_dropdown.set(config_manager.get_current_profile())
        self.profile_dropdown.pack(side="left", fill="x", expand=True)

        # Action buttons row
        btn_row = ctk.CTkFrame(section, fg_color="transparent")
        btn_row.pack(fill="x", padx=15, pady=(5, 10))

        ctk.CTkButton(
            btn_row,
            text="✏️ Rename",
            width=80,
            height=28,
            corner_radius=6,
            fg_color=Colors.SECONDARY,
            text_color=Colors.FG,
            hover_color=Colors.BORDER,
            font=(AppConfig.FONT_FAMILY, 10),
            command=self._rename_profile,
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_row,
            text="➕ New",
            width=70,
            height=28,
            corner_radius=6,
            fg_color=Colors.BLUE,
            text_color=Colors.FG,
            hover_color="#3a7ab0",
            font=(AppConfig.FONT_FAMILY, 10),
            command=self._create_new_profile,
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_row,
            text="🗑️ Delete",
            width=75,
            height=28,
            corner_radius=6,
            fg_color=Colors.RED,
            text_color=Colors.FG,
            hover_color="#c4493f",
            font=(AppConfig.FONT_FAMILY, 10),
            command=self._delete_profile,
        ).pack(side="left")

    def _create_coordinates_section(self, parent) -> None:
        """Create coordinates configuration section."""
        section = CardFrame(parent)
        section.pack(fill="x", pady=5)

        # Section header
        ctk.CTkLabel(
            section,
            text="📍 Coordinates",
            font=(AppConfig.FONT_FAMILY, 12, "bold"),
            text_color=Colors.PRIMARY,
        ).pack(anchor="w", padx=15, pady=(10, 5))

        # Column headers
        header_row = ctk.CTkFrame(section, fg_color="transparent")
        header_row.pack(fill="x", padx=15, pady=2)

        ctk.CTkLabel(
            header_row,
            text="Setting",
            font=(AppConfig.FONT_FAMILY, 9, "bold"),
            text_color=Colors.MUTED_FG,
            width=140,
            anchor="w",
        ).pack(side="left")

        ctk.CTkLabel(
            header_row,
            text="X",
            font=(AppConfig.FONT_FAMILY, 9, "bold"),
            text_color=Colors.MUTED_FG,
            width=60,
        ).pack(side="left", padx=5)

        ctk.CTkLabel(
            header_row,
            text="Y",
            font=(AppConfig.FONT_FAMILY, 9, "bold"),
            text_color=Colors.MUTED_FG,
            width=60,
        ).pack(side="left", padx=5)

        # Coordinate entries
        for config_key, label in self.COORD_SETTINGS:
            row = ctk.CTkFrame(section, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=3)

            ctk.CTkLabel(
                row,
                text=label,
                font=(AppConfig.FONT_FAMILY, 10),
                text_color=Colors.FG,
                width=140,
                anchor="w",
            ).pack(side="left")

            x_entry = ctk.CTkEntry(
                row,
                width=60,
                height=26,
                font=("JetBrains Mono", 10),
                fg_color=Colors.SECONDARY,
                border_color=Colors.BORDER,
                text_color=Colors.PRIMARY,
                justify="center",
                corner_radius=4,
            )
            x_entry.pack(side="left", padx=5)

            y_entry = ctk.CTkEntry(
                row,
                width=60,
                height=26,
                font=("JetBrains Mono", 10),
                fg_color=Colors.SECONDARY,
                border_color=Colors.BORDER,
                text_color=Colors.PRIMARY,
                justify="center",
                corner_radius=4,
            )
            y_entry.pack(side="left", padx=5)

            pick_btn = ctk.CTkButton(
                row,
                text="📍 Pick",
                width=60,
                height=26,
                corner_radius=4,
                fg_color=Colors.BLUE,
                text_color=Colors.FG,
                hover_color="#3a7ab0",
                font=(AppConfig.FONT_FAMILY, 10),
                command=lambda k=config_key: self._start_pick_mode(k),
            )
            pick_btn.pack(side="left", padx=(10, 0))

            self.coord_entries[config_key] = (x_entry, y_entry)

        # Add padding at bottom
        ctk.CTkFrame(section, fg_color="transparent", height=5).pack()

    def _create_color_section(self, parent) -> None:
        """Create color configuration section."""
        section = CardFrame(parent)
        section.pack(fill="x", pady=5)

        # Section header
        ctk.CTkLabel(
            section,
            text="🎨 Colors",
            font=(AppConfig.FONT_FAMILY, 12, "bold"),
            text_color=Colors.PRIMARY,
        ).pack(anchor="w", padx=15, pady=(10, 5))

        # Column headers
        header_row = ctk.CTkFrame(section, fg_color="transparent")
        header_row.pack(fill="x", padx=15, pady=2)

        ctk.CTkLabel(
            header_row,
            text="Setting",
            font=(AppConfig.FONT_FAMILY, 9, "bold"),
            text_color=Colors.MUTED_FG,
            width=130,
            anchor="w",
        ).pack(side="left")

        for lbl in ["R", "G", "B"]:
            ctk.CTkLabel(
                header_row,
                text=lbl,
                font=(AppConfig.FONT_FAMILY, 9, "bold"),
                text_color=Colors.MUTED_FG,
                width=40,
            ).pack(side="left", padx=2)

        # Color entries
        for config_key, label in self.COLOR_SETTINGS:
            row = ctk.CTkFrame(section, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=3)

            ctk.CTkLabel(
                row,
                text=label,
                font=(AppConfig.FONT_FAMILY, 10),
                text_color=Colors.FG,
                width=130,
                anchor="w",
            ).pack(side="left")

            r_entry = ctk.CTkEntry(
                row,
                width=40,
                height=26,
                font=("JetBrains Mono", 10),
                fg_color=Colors.SECONDARY,
                border_color=Colors.BORDER,
                text_color=Colors.RED,
                justify="center",
                corner_radius=4,
            )
            r_entry.pack(side="left", padx=2)

            g_entry = ctk.CTkEntry(
                row,
                width=40,
                height=26,
                font=("JetBrains Mono", 10),
                fg_color=Colors.SECONDARY,
                border_color=Colors.BORDER,
                text_color=Colors.GREEN,
                justify="center",
                corner_radius=4,
            )
            g_entry.pack(side="left", padx=2)

            b_entry = ctk.CTkEntry(
                row,
                width=40,
                height=26,
                font=("JetBrains Mono", 10),
                fg_color=Colors.SECONDARY,
                border_color=Colors.BORDER,
                text_color=Colors.BLUE,
                justify="center",
                corner_radius=4,
            )
            b_entry.pack(side="left", padx=2)

            # Color preview square
            preview = ctk.CTkFrame(
                row,
                width=26,
                height=26,
                corner_radius=4,
                fg_color=Colors.SECONDARY,
                border_color=Colors.BORDER,
                border_width=1,
            )
            preview.pack(side="left", padx=(5, 5))
            preview.pack_propagate(False)

            pick_btn = ctk.CTkButton(
                row,
                text="📍 Pick",
                width=60,
                height=26,
                corner_radius=4,
                fg_color=Colors.BLUE,
                text_color=Colors.FG,
                hover_color="#3a7ab0",
                font=(AppConfig.FONT_FAMILY, 10),
                command=lambda k=config_key: self._start_pick_mode(k),
            )
            pick_btn.pack(side="left", padx=(5, 0))

            self.color_entries[config_key] = (r_entry, g_entry, b_entry, preview)

            # Bind entry changes to update preview
            for entry in (r_entry, g_entry, b_entry):
                entry.bind(
                    "<KeyRelease>",
                    lambda e, k=config_key: self._update_color_preview(k),
                )

        # Add padding at bottom
        ctk.CTkFrame(section, fg_color="transparent", height=5).pack()

    def _create_auto_dimmer_section(self, parent) -> None:
        """Create auto dimmer switch toggle section."""
        section = CardFrame(parent)
        section.pack(fill="x", pady=5)

        row = ctk.CTkFrame(section, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(
            row,
            text="🎮 Auto switch to Gaming mode on Champ Select",
            font=(AppConfig.FONT_FAMILY, 11),
            text_color=Colors.FG,
        ).pack(side="left")

        self.auto_dimmer_switch_var = ctk.BooleanVar(
            value=config_manager.get("auto_dimmer_switch_enabled") or True
        )

        self.auto_dimmer_switch = ctk.CTkSwitch(
            row,
            text="",
            width=40,
            variable=self.auto_dimmer_switch_var,
            command=self._on_auto_dimmer_switch_changed,
            progress_color=Colors.GREEN,
            fg_color=Colors.SECONDARY,
        )
        self.auto_dimmer_switch.pack(side="right")

    def _load_current_values(self) -> None:
        """Load current config values into entries."""
        # Load coordinates
        for config_key, (x_entry, y_entry) in self.coord_entries.items():
            pos = config_manager.get(config_key)
            if pos and len(pos) >= 2:
                x_entry.delete(0, "end")
                x_entry.insert(0, str(pos[0]))
                y_entry.delete(0, "end")
                y_entry.insert(0, str(pos[1]))

        # Load colors
        for config_key, (
            r_entry,
            g_entry,
            b_entry,
            preview,
        ) in self.color_entries.items():
            color = config_manager.get(config_key)
            if color and len(color) >= 3:
                r_entry.delete(0, "end")
                r_entry.insert(0, str(color[0]))
                g_entry.delete(0, "end")
                g_entry.insert(0, str(color[1]))
                b_entry.delete(0, "end")
                b_entry.insert(0, str(color[2]))
                self._update_color_preview(config_key)

    def _update_color_preview(self, config_key: str) -> None:
        """Update the color preview square based on RGB entries."""
        if config_key not in self.color_entries:
            return

        r_entry, g_entry, b_entry, preview = self.color_entries[config_key]
        try:
            r = int(r_entry.get() or 0)
            g = int(g_entry.get() or 0)
            b = int(b_entry.get() or 0)
            # Clamp values
            r = max(0, min(255, r))
            g = max(0, min(255, g))
            b = max(0, min(255, b))
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            preview.configure(fg_color=hex_color)
        except ValueError:
            preview.configure(fg_color=Colors.SECONDARY)

    def _on_profile_changed(self, profile_name: str) -> None:
        """Handle profile selection change."""
        config_manager.switch_profile(profile_name)
        self._load_current_values()
        logger.info(f"Switched to profile: {profile_name}")

    def _refresh_profile_dropdown(self) -> None:
        """Refresh the profile dropdown with current profiles."""
        profiles = config_manager.get_profile_names()
        self.profile_dropdown.configure(values=profiles)
        self.profile_dropdown.set(config_manager.get_current_profile())

    def _rename_profile(self) -> None:
        """Open dialog to rename current profile."""
        current = config_manager.get_current_profile()

        dialog = ctk.CTkInputDialog(
            text=f"New name for '{current}':",
            title="Rename Profile",
        )
        new_name = dialog.get_input()

        if new_name and new_name.strip() and new_name != current:
            if config_manager.rename_profile(current, new_name.strip()):
                self._refresh_profile_dropdown()
                messagebox.showinfo("Success", f"Profile renamed to '{new_name}'")
            else:
                messagebox.showerror(
                    "Error", "Failed to rename profile. Name may already exist."
                )

    def _create_new_profile(self) -> None:
        """Create a new profile."""
        # Generate next profile number
        existing = config_manager.get_profile_names()
        num = len(existing) + 1
        new_name = f"Profile {num}"

        # Ensure unique name
        while new_name in existing:
            num += 1
            new_name = f"Profile {num}"

        if config_manager.create_profile(
            new_name, copy_from=config_manager.get_current_profile()
        ):
            config_manager.switch_profile(new_name)
            self._refresh_profile_dropdown()
            self._load_current_values()
            messagebox.showinfo("Success", f"Created profile '{new_name}'")

    def _delete_profile(self) -> None:
        """Delete current profile with confirmation."""
        current = config_manager.get_current_profile()
        profiles = config_manager.get_profile_names()

        if len(profiles) <= 1:
            messagebox.showwarning("Cannot Delete", "Cannot delete the last profile.")
            return

        if messagebox.askyesno(
            "Confirm Delete", f"Delete profile '{current}'?\nThis cannot be undone."
        ):
            if config_manager.delete_profile(current):
                self._refresh_profile_dropdown()
                self._load_current_values()
                messagebox.showinfo("Deleted", f"Profile '{current}' deleted.")

    def _on_auto_dimmer_switch_changed(self) -> None:
        """Handle auto dimmer switch toggle."""
        is_enabled = self.auto_dimmer_switch_var.get()
        config_manager.set("auto_dimmer_switch_enabled", is_enabled)
        logger.info(f"Auto dimmer switch toggled: {is_enabled}")

    def _start_pick_mode(self, config_key: str) -> None:
        """Start the screen pick mode for a coordinate/color."""
        self._pick_target_key = config_key
        self._pick_mode_active = True

        # Hide this modal
        self.withdraw()

        # Create a fullscreen transparent overlay for pick mode
        self._pick_overlay = tk.Toplevel()
        self._pick_overlay.attributes("-fullscreen", True)
        self._pick_overlay.attributes("-topmost", True)
        self._pick_overlay.attributes("-alpha", 0.01)  # Nearly invisible
        self._pick_overlay.configure(cursor="crosshair")
        self._pick_overlay.bind("<Button-1>", self._on_pick_click)
        self._pick_overlay.bind("<Escape>", self._cancel_pick_mode)

        # Focus the overlay
        self._pick_overlay.focus_force()

    def _on_pick_click(self, event) -> None:
        """Handle click during pick mode."""
        if not self._pick_mode_active:
            return

        try:
            # Get mouse position
            x, y = pyautogui.position()

            # Get pixel color at position
            try:
                pixel = pyautogui.pixel(x, y)
                r, g, b = pixel
            except Exception:
                r, g, b = 0, 0, 0

            # Determine if this is a coord-only or coord+color pick
            config_key = self._pick_target_key

            if config_key in self.coord_entries:
                # Update coordinate entries
                x_entry, y_entry = self.coord_entries[config_key]
                x_entry.delete(0, "end")
                x_entry.insert(0, str(x))
                y_entry.delete(0, "end")
                y_entry.insert(0, str(y))

                # Save to config
                config_manager.set(config_key, [x, y])

            # For pixel detection settings, also update associated color
            # Map coord key to color key
            coord_to_color_map = {
                "in_queue_pixel_pos": "in_queue_pixel_color",
                "accept_match_pixel_pos": "accept_match_pixel_color",
                "champ_select_pixel_pos": "champ_select_pixel_color",
            }

            if config_key in coord_to_color_map:
                color_key = coord_to_color_map[config_key]
                if color_key in self.color_entries:
                    r_entry, g_entry, b_entry, preview = self.color_entries[color_key]
                    r_entry.delete(0, "end")
                    r_entry.insert(0, str(r))
                    g_entry.delete(0, "end")
                    g_entry.insert(0, str(g))
                    b_entry.delete(0, "end")
                    b_entry.insert(0, str(b))
                    self._update_color_preview(color_key)

                    # Save color to config
                    config_manager.set(color_key, [r, g, b])

            # Also handle if picking from color section directly
            if config_key in self.color_entries:
                r_entry, g_entry, b_entry, preview = self.color_entries[config_key]
                r_entry.delete(0, "end")
                r_entry.insert(0, str(r))
                g_entry.delete(0, "end")
                g_entry.insert(0, str(g))
                b_entry.delete(0, "end")
                b_entry.insert(0, str(b))
                self._update_color_preview(config_key)

                # Save color to config
                config_manager.set(config_key, [r, g, b])

                # Also update associated coord if exists
                color_to_coord_map = {
                    "in_queue_pixel_color": "in_queue_pixel_pos",
                    "accept_match_pixel_color": "accept_match_pixel_pos",
                    "champ_select_pixel_color": "champ_select_pixel_pos",
                }
                if config_key in color_to_coord_map:
                    coord_key = color_to_coord_map[config_key]
                    if coord_key in self.coord_entries:
                        x_entry, y_entry = self.coord_entries[coord_key]
                        x_entry.delete(0, "end")
                        x_entry.insert(0, str(x))
                        y_entry.delete(0, "end")
                        y_entry.insert(0, str(y))
                        config_manager.set(coord_key, [x, y])

            logger.info(
                f"Picked: {config_key} -> pos=({x}, {y}), color=({r}, {g}, {b})"
            )

        except Exception as e:
            logger.error(f"Error during pick: {e}")

        finally:
            self._end_pick_mode()

    def _cancel_pick_mode(self, event=None) -> None:
        """Cancel pick mode on Escape."""
        self._end_pick_mode()

    def _end_pick_mode(self) -> None:
        """End pick mode and restore modal."""
        self._pick_mode_active = False
        self._pick_target_key = None

        if self._pick_overlay:
            self._pick_overlay.destroy()
            self._pick_overlay = None

        # Show modal again
        self.deiconify()
        self.attributes("-topmost", True)
        self.focus_force()

    def _save_and_close(self) -> None:
        """Save all current entry values to config and close."""
        try:
            # Save all coordinates
            for config_key, (x_entry, y_entry) in self.coord_entries.items():
                try:
                    x = int(x_entry.get() or 0)
                    y = int(y_entry.get() or 0)
                    config_manager.set(config_key, [x, y])
                except ValueError:
                    pass

            # Save all colors
            for config_key, (
                r_entry,
                g_entry,
                b_entry,
                _,
            ) in self.color_entries.items():
                try:
                    r = int(r_entry.get() or 0)
                    g = int(g_entry.get() or 0)
                    b = int(b_entry.get() or 0)
                    config_manager.set(config_key, [r, g, b])
                except ValueError:
                    pass

            logger.info("Settings saved successfully.")

        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            messagebox.showerror("Error", f"Failed to save settings: {e}")

        self.destroy()


class AntiFateApp(ctk.CTk):
    def __init__(self):
        # Apply UI scaling BEFORE super().__init__() for clean initialization
        saved_scale = config_manager.get("ui_scale") or 1.0
        saved_scale = max(0.8, min(1.5, float(saved_scale)))  # Clamp to valid range
        ctk.set_widget_scaling(saved_scale)
        ctk.set_window_scaling(saved_scale)
        self._current_scale = saved_scale

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
        self._settings_modal: Optional[ctk.CTkToplevel] = None

        # Variables
        self.reset_time_var = tk.StringVar()
        self.reset_time_var.trace_add("write", self._on_time_changed)
        self.dimmer_enabled_var = ctk.BooleanVar(value=True)
        self.reset_sound_enabled_var = ctk.BooleanVar(value=True)
        self.auto_startup_enabled_var = ctk.BooleanVar(value=False)
        self.auto_accept_enabled_var = ctk.BooleanVar(value=True)
        self.auto_reset_enabled_var = ctk.BooleanVar(value=True)
        self.sound_volume_var = tk.IntVar(value=50)
        self.dimmer_mode_var = tk.StringVar(value="browsing")  # "gaming" or "browsing"
        self.selected_sound_var = tk.StringVar(value="notify")
        self._skip_dimmer_save = False  # Flag to prevent double-save in auto-switch

        self._setup_icons()
        self.create_widgets()
        self.load_settings()

        # Final show
        self.update_idletasks()
        # self.deiconify() # Disabled with withdraw

        # Bind events
        self.bind("<Configure>", self._on_window_configure)
        self.bind("<FocusOut>", self._on_focus_out)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Bind zoom hotkeys (browser-like: Ctrl+Plus, Ctrl+Minus, Ctrl+0)
        self.bind("<Control-plus>", lambda e: self._zoom_in())
        self.bind("<Control-minus>", lambda e: self._zoom_out())
        self.bind("<Control-0>", lambda e: self._zoom_reset())
        # Also bind Ctrl+= for keyboards where + requires Shift
        self.bind("<Control-equal>", lambda e: self._zoom_in())

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

        # Settings Button (Top Left) - symmetrical to info button
        self.settings_btn = ctk.CTkButton(
            self.status_card,
            text="⚙️",
            width=20,
            height=20,
            corner_radius=10,
            fg_color="transparent",
            text_color=Colors.MUTED_FG,
            hover_color=Colors.SECONDARY,
            font=(AppConfig.FONT_FAMILY, 12),
            command=self.show_settings_modal,
        )
        self.settings_btn.place(relx=0.04, rely=0.08, anchor="nw")

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
        volume_row.pack(fill="x", pady=(0, 10), padx=5)

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
        self.volume_label.pack(side="left", padx=(5, 5))

        # Sound Test Button
        self.sound_test_btn = ctk.CTkButton(
            volume_row,
            text="▶",
            width=28,
            height=28,
            corner_radius=6,
            fg_color=Colors.SECONDARY,
            hover_color=Colors.BORDER,
            text_color=Colors.FG,
            font=(AppConfig.FONT_FAMILY, 12),
            command=self._play_test_sound,
        )
        self.sound_test_btn.pack(side="right")

        # Sound Selection Row
        sound_select_row = ctk.CTkFrame(main_container, fg_color="transparent")
        sound_select_row.pack(fill="x", pady=(0, 15), padx=5)

        ctk.CTkLabel(
            sound_select_row,
            text="🔔",
            font=(AppConfig.FONT_FAMILY, 14),
        ).pack(side="left", padx=(0, 10))

        # Build sound options list
        sound_display_names = [v[0] for v in SOUND_OPTIONS.values()]
        self.sound_key_map = {v[0]: k for k, v in SOUND_OPTIONS.items()}

        self.sound_option_menu = ctk.CTkOptionMenu(
            sound_select_row,
            values=sound_display_names,
            command=self._on_sound_selected,
            font=(AppConfig.FONT_FAMILY, 11),
            fg_color=Colors.SECONDARY,
            button_color=Colors.BORDER,
            button_hover_color=Colors.RING,
            dropdown_fg_color=Colors.CARD,
            dropdown_hover_color=Colors.SECONDARY,
            text_color=Colors.FG,
            dropdown_text_color=Colors.FG,
            corner_radius=6,
            height=28,
        )
        self.sound_option_menu.pack(side="left", fill="x", expand=True)

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

        # Dimmer Mode Toggle (Gaming/Browsing)
        dimmer_mode_row = ctk.CTkFrame(settings_card, fg_color="transparent")
        dimmer_mode_row.pack(fill="x", padx=15, pady=(0, 5))

        self.dimmer_mode_segment = ctk.CTkSegmentedButton(
            dimmer_mode_row,
            values=["🎮 Gaming", "🌐 Browsing"],
            variable=self.dimmer_mode_var,
            command=self._on_dimmer_mode_changed,
            font=(AppConfig.FONT_FAMILY, 10),
            fg_color=Colors.SECONDARY,
            selected_color=Colors.BLUE,
            selected_hover_color=Colors.BLUE,
            unselected_color=Colors.SECONDARY,
            unselected_hover_color=Colors.BORDER,
            text_color=Colors.FG,
            corner_radius=6,
            height=28,
        )
        self.dimmer_mode_segment.pack(fill="x")

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
        self.dimmer_slider.pack(fill="x", padx=15, pady=(0, 10))

        # Auto Dimmer Switch Toggle (moved from SettingsModal in v1.11)
        auto_dimmer_row = ctk.CTkFrame(settings_card, fg_color="transparent")
        auto_dimmer_row.pack(fill="x", padx=15, pady=(0, 15))

        ctk.CTkLabel(
            auto_dimmer_row,
            text="Auto switch on Champ Select",
            font=(AppConfig.FONT_FAMILY, 11),
            text_color=Colors.FG,
        ).pack(side="left")

        self.auto_dimmer_switch_var = ctk.BooleanVar(
            value=config_manager.get("auto_dimmer_switch_enabled") or True
        )

        self.auto_dimmer_switch = ctk.CTkSwitch(
            auto_dimmer_row,
            text="",
            width=40,
            variable=self.auto_dimmer_switch_var,
            command=self._toggle_auto_dimmer_switch,
            progress_color=Colors.GREEN,
            fg_color=Colors.SECONDARY,
        )
        self.auto_dimmer_switch.pack(side="right")

        # 3. Preferences Card
        pref_card = CardFrame(main_container)
        pref_card.pack(fill="x", pady=(0, 15))

        # Auto Accept Toggle (NEW)
        accept_row = ctk.CTkFrame(pref_card, fg_color="transparent")
        accept_row.pack(fill="x", padx=15, pady=(12, 6))

        ctk.CTkLabel(
            accept_row,
            text="Auto Accept Match",
            font=(AppConfig.FONT_FAMILY, 12),
            text_color=Colors.FG,
        ).pack(side="left")

        self.auto_accept_switch = ctk.CTkSwitch(
            accept_row,
            text="",
            width=40,
            variable=self.auto_accept_enabled_var,
            command=self.toggle_auto_accept,
            progress_color=Colors.GREEN,
            fg_color=Colors.SECONDARY,
        )
        self.auto_accept_switch.pack(side="right")

        # Auto Reset Toggle (NEW)
        reset_toggle_row = ctk.CTkFrame(pref_card, fg_color="transparent")
        reset_toggle_row.pack(fill="x", padx=15, pady=(6, 6))

        ctk.CTkLabel(
            reset_toggle_row,
            text="Auto Reset Queue",
            font=(AppConfig.FONT_FAMILY, 12),
            text_color=Colors.FG,
        ).pack(side="left")

        self.auto_reset_switch = ctk.CTkSwitch(
            reset_toggle_row,
            text="",
            width=40,
            variable=self.auto_reset_enabled_var,
            command=self.toggle_auto_reset,
            progress_color=Colors.GREEN,
            fg_color=Colors.SECONDARY,
        )
        self.auto_reset_switch.pack(side="right")

        # Separator
        ctk.CTkFrame(pref_card, fg_color=Colors.BORDER, height=1).pack(
            fill="x", padx=15, pady=6
        )

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

    def _on_dimmer_mode_changed(self, mode: str) -> None:
        """Handle dimmer mode switch between Gaming and Browsing."""
        # Save current slider value to the current mode before switching
        current_slider_val = int(self.dimmer_slider.get())
        old_mode = config_manager.get("dimmer_mode")

        # Map display name to internal key
        if "Gaming" in mode:
            new_mode = "gaming"
        else:
            new_mode = "browsing"

        # Save current value to the OLD mode (skip if called from switch_to_gaming_mode)
        if not self._skip_dimmer_save:
            if old_mode == "gaming":
                config_manager.set("dimmer_gaming_value", current_slider_val)
            else:
                config_manager.set("dimmer_browsing_value", current_slider_val)

        # Reset skip flag
        self._skip_dimmer_save = False

        # Switch mode
        config_manager.set("dimmer_mode", new_mode)

        # Load and apply value for the NEW mode
        if new_mode == "gaming":
            new_val = config_manager.get("dimmer_gaming_value")
            if new_val is None:
                new_val = 100
        else:
            new_val = config_manager.get("dimmer_browsing_value")
            if new_val is None:
                new_val = 100

        self.dimmer_slider.set(float(new_val))
        if self.dimmer_enabled_var.get():
            self.dimmer.set_brightness(int(new_val))
        config_manager.set("dimmer_value", int(new_val))
        logger.info(f"Dimmer mode switched to: {new_mode} (brightness: {new_val}%)")

    def _play_test_sound(self) -> None:
        """Play the currently selected notification sound for testing."""
        import threading
        import ctypes

        def _play():
            try:
                selected_key = config_manager.get("selected_sound") or "notify"
                if selected_key in SOUND_OPTIONS:
                    rel_path = SOUND_OPTIONS[selected_key][1]
                    file_path = os.path.join(RESOURCE_DIR, rel_path)
                else:
                    file_path = AppConfig.NOTIFY_SOUND

                volume = config_manager.get("sound_volume") or 50

                # Use Windows MCI for playback
                mci = ctypes.windll.winmm.mciSendStringW
                alias = "test_sound"
                mci(f"close {alias}", None, 0, 0)
                mci(f'open "{file_path}" type mpegvideo alias {alias}', None, 0, 0)
                mci(f"setaudio {alias} volume to {int(volume * 10)}", None, 0, 0)
                mci(f"play {alias} wait", None, 0, 0)
                mci(f"close {alias}", None, 0, 0)
            except Exception as e:
                logger.error(f"Failed to play test sound: {e}")

        threading.Thread(target=_play, daemon=True).start()

    def _on_sound_selected(self, display_name: str) -> None:
        """Handle sound selection change."""
        sound_key = self.sound_key_map.get(display_name, "notify")
        config_manager.set("selected_sound", sound_key)
        logger.info(f"Sound changed to: {sound_key} ({display_name})")

    def switch_to_gaming_mode(self) -> None:
        """Callback to switch to Gaming dimmer mode (called by bot on champ select)."""
        # Check if auto dimmer switch is enabled
        if not config_manager.get("auto_dimmer_switch_enabled"):
            return

        current_mode = config_manager.get("dimmer_mode")
        if current_mode != "gaming":
            logger.info("Champ select detected - switching to Gaming dimmer mode")

            # FIX: Save current browsing value BEFORE switching to prevent race condition
            current_slider_val = int(self.dimmer_slider.get())
            if current_mode == "browsing":
                config_manager.set("dimmer_browsing_value", current_slider_val)
                logger.info(f"Saved browsing dimmer value: {current_slider_val}%")

            # Set flag to prevent _on_dimmer_mode_changed from re-saving (would save wrong value)
            self._skip_dimmer_save = True
            self.after(0, lambda: self.dimmer_mode_segment.set("🎮 Gaming"))
            self.after(10, lambda: self._on_dimmer_mode_changed("🎮 Gaming"))

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

    def _on_focus_out(self, event) -> None:
        """Handle window losing focus - auto minimize."""
        # Only process if the event is for the main window
        if event.widget != self:
            return

        # Skip if disabled in config
        if not config_manager.get("minimize_on_focus_loss"):
            return

        # CRITICAL: Skip if pick mode is active in settings modal
        if self._settings_modal and hasattr(self._settings_modal, "_pick_mode_active"):
            if self._settings_modal._pick_mode_active:
                return

        # Use after() to defer check - prevents race conditions
        self.after(100, self._check_and_minimize)

    def _check_and_minimize(self) -> None:
        """Deferred minimize check."""
        # Re-check pick mode after delay
        if self._settings_modal and hasattr(self._settings_modal, "_pick_mode_active"):
            if self._settings_modal._pick_mode_active:
                return

        # Check if any of our modals now have focus
        try:
            focused = self.focus_get()
            if focused is not None:
                # Focus returned to our hierarchy
                return
        except Exception:
            pass

        # Check if modals are visible
        if self._settings_modal and self._settings_modal.winfo_exists():
            try:
                if self._settings_modal.winfo_viewable():
                    return
            except Exception:
                pass

        if self._info_modal and self._info_modal.winfo_exists():
            try:
                if self._info_modal.winfo_viewable():
                    return
            except Exception:
                pass

        # Safe to minimize
        self.iconify()

    # === UI Scaling (Browser-like Ctrl+/- zoom) ===

    def _zoom_in(self) -> None:
        """Increase UI scale by 0.1 (max 1.5)."""
        new_scale = min(1.5, self._current_scale + 0.1)
        self._apply_scale(new_scale)

    def _zoom_out(self) -> None:
        """Decrease UI scale by 0.1 (min 0.8)."""
        new_scale = max(0.8, self._current_scale - 0.1)
        self._apply_scale(new_scale)

    def _zoom_reset(self) -> None:
        """Reset UI scale to 1.0."""
        self._apply_scale(1.0)

    def _apply_scale(self, scale: float) -> None:
        """Apply new UI scale and persist to config."""
        if scale == self._current_scale:
            return

        self._current_scale = round(scale, 1)
        ctk.set_widget_scaling(self._current_scale)
        ctk.set_window_scaling(self._current_scale)
        config_manager.set("ui_scale", self._current_scale)
        logger.info(f"UI scale changed to {self._current_scale}")

    def load_settings(self) -> None:
        # Load Reset Time
        saved_time = config_manager.get("reset_time")
        self.reset_time_var.set(str(saved_time))

        # Load Volume
        saved_vol = config_manager.get("sound_volume") or 50
        self.sound_volume_var.set(saved_vol)
        self.volume_label.configure(text=f"{saved_vol}%")

        # Load Selected Sound
        saved_sound_key = config_manager.get("selected_sound") or "notify"
        if saved_sound_key in SOUND_OPTIONS:
            display_name = SOUND_OPTIONS[saved_sound_key][0]
            self.sound_option_menu.set(display_name)
        self.selected_sound_var.set(saved_sound_key)

        # Load Dimmer Settings
        dimmer_val = config_manager.get("dimmer_value") or 100
        dimmer_enabled = config_manager.get("dimmer_enabled")
        if dimmer_enabled is None:
            dimmer_enabled = True

        # Load Dimmer Mode
        dimmer_mode = config_manager.get("dimmer_mode") or "browsing"
        if dimmer_mode == "gaming":
            self.dimmer_mode_segment.set("🎮 Gaming")
            dimmer_val = config_manager.get("dimmer_gaming_value")
            if dimmer_val is None:
                dimmer_val = 100
        else:
            self.dimmer_mode_segment.set("🌐 Browsing")
            dimmer_val = config_manager.get("dimmer_browsing_value")
            if dimmer_val is None:
                dimmer_val = 100

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

        # Load Auto Accept Settings
        saved_auto_accept = config_manager.get("auto_accept_enabled")
        if saved_auto_accept is None:
            saved_auto_accept = True
        self.auto_accept_enabled_var.set(saved_auto_accept)

        # Load Auto Reset Settings
        saved_auto_reset = config_manager.get("auto_reset_enabled")
        if saved_auto_reset is None:
            saved_auto_reset = True
        self.auto_reset_enabled_var.set(saved_auto_reset)

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

    def toggle_auto_accept(self) -> None:
        is_enabled = self.auto_accept_enabled_var.get()
        config_manager.set("auto_accept_enabled", is_enabled)
        logger.info(f"Auto Accept Match toggled: {is_enabled}")

    def toggle_auto_reset(self) -> None:
        is_enabled = self.auto_reset_enabled_var.get()
        config_manager.set("auto_reset_enabled", is_enabled)
        logger.info(f"Auto Reset Queue toggled: {is_enabled}")

    def _toggle_auto_dimmer_switch(self) -> None:
        """Handle auto dimmer switch toggle (auto-switch to Gaming mode on champ select)."""
        is_enabled = self.auto_dimmer_switch_var.get()
        config_manager.set("auto_dimmer_switch_enabled", is_enabled)
        logger.info(f"Auto dimmer switch toggled: {is_enabled}")

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

            # Also save to the current mode's specific value
            current_mode = config_manager.get("dimmer_mode") or "browsing"
            if current_mode == "gaming":
                config_manager.set("dimmer_gaming_value", int(value))
            else:
                config_manager.set("dimmer_browsing_value", int(value))

    def show_info_modal(self) -> None:
        """Trigger the professional info modal (Singleton pattern)."""
        if self._info_modal is not None and self._info_modal.winfo_exists():
            self._info_modal.focus_set()
            self._info_modal.attributes("-topmost", True)
            return
        self._info_modal = InfoModal(self)

    def show_settings_modal(self) -> None:
        """Trigger the advanced settings modal (Singleton pattern)."""
        if self._settings_modal is not None and self._settings_modal.winfo_exists():
            self._settings_modal.focus_set()
            self._settings_modal.attributes("-topmost", True)
            return
        self._settings_modal = SettingsModal(self)

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
            on_champ_select_callback=self.switch_to_gaming_mode,
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

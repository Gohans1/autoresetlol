import customtkinter as ctk  # type: ignore
import tkinter as tk
from tkinter import messagebox
import webbrowser
import os
import winsound  # beep khi app minimize (toast vô hình lúc đó)
from typing import Optional, List, Tuple
from PIL import Image, ImageDraw

from config import config_manager, normalize_ui_scale
from bot import AntiFateBot
from gui_arena import ArenaUiMixin
from gui_arena_suggestions import ArenaSuggestionsMixin
from gui_components import CardFrame
from gui_dimmer import DimmerUiMixin
from gui_lifecycle import LifecycleUiMixin
from gui_status import StatusUiMixin
from lcu_watcher import LcuWatcher
from utils.windows import DimmerController
from constants import (
    AppConfig,
    Colors,
    DefaultConfig,
    DISCORD_NOTIFICATION_SPECS,
    UIStatus,
)
from logger import logger
from notifications import HermesNotifier


# Set Theme
ctk.set_appearance_mode(AppConfig.THEME_MODE)
ctk.set_default_color_theme(AppConfig.THEME_COLOR)


class AntiFateApp(
    DimmerUiMixin,
    ArenaUiMixin,
    ArenaSuggestionsMixin,
    LifecycleUiMixin,
    StatusUiMixin,
    ctk.CTk,
):
    def __init__(self):
        try:
            self._initialize()
        except Exception:
            self._cleanup_partial_initialization()
            raise

    def _initialize(self):
        # Apply UI scaling BEFORE super().__init__() for clean initialization
        # Default to 1.25x (~16px effective) for readability; user can change
        # via footer dropdown (persisted to config).
        saved_scale = config_manager.get("ui_scale")
        if saved_scale is None:
            saved_scale = DefaultConfig.UI_SCALE
            config_manager.set("ui_scale", saved_scale)
        saved_scale = normalize_ui_scale(saved_scale)
        ctk.set_widget_scaling(saved_scale)
        ctk.set_window_scaling(saved_scale)

        super().__init__()
        # Build the complete widget tree off-screen, then reveal one stable frame.
        self.withdraw()

        # Load geometry from config — migrate from old narrow layout if needed
        saved_geo = config_manager.get("window_geometry")
        if saved_geo:
            try:
                self.geometry(saved_geo)
            except Exception as e:
                logger.error(f"Failed to apply saved geometry: {e}")
                self.geometry(AppConfig.GEOMETRY)
        else:
            self.geometry(AppConfig.GEOMETRY)

        # Enforce new wide minimum: old configs saved narrow geometry
        self.minsize(720, 520)
        self.resizable(True, True)  # Allow resizing
        self.configure(fg_color=Colors.BG)

        # Window Setup
        self.title(AppConfig.APP_NAME)

        # Activity beacon state is rendered in the fixed top dock.
        self._geo_save_timer = None
        self._beacon_color = Colors.MUTED_FG
        self._beacon_pulse_active = False
        self._beacon_pulse_visible = True
        self._beacon_pulse_id = None

        # Set Window Icon
        try:
            # For Taskbar and Titlebar
            if os.path.exists(AppConfig.APP_ICON):
                self.iconbitmap(AppConfig.APP_ICON)

                # Use AppID to force Windows to show the correct icon on the taskbar
                import ctypes

                myappid = f"sisyphus.autoresetlol.antifate.{AppConfig.VERSION}"
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception as e:
            logger.error(f"Could not set window icon: {e}")

        self.bot: Optional[AntiFateBot] = None
        self._bot_generation = 0
        self._bot_stopping = False
        self._ui_callbacks_enabled = True
        self._arena_automation_enabled = False
        self._arena_live_events: List[Tuple[str, str, str]] = []
        self.notifier = HermesNotifier()
        self.dimmer = DimmerController()
        self._dimmer_watchdog_id = None
        self._dimmer_save_after_id = None
        self._dimmer_save_dirty = False
        self._arena_save_dirty = False
        self._watchdog_drift_count = 0
        # Variables
        self.dimmer_enabled_var = ctk.BooleanVar(value=True)
        self.auto_startup_enabled_var = ctk.BooleanVar(value=False)
        self.auto_accept_enabled_var = ctk.BooleanVar(value=True)
        self.discord_notify_ban_var = ctk.BooleanVar(value=False)
        self.discord_notify_pick_var = ctk.BooleanVar(value=False)
        self.discord_notify_in_game_var = ctk.BooleanVar(value=False)
        self.dimmer_mode_var = tk.StringVar(value="browsing")  # "gaming" or "browsing"
        self._skip_dimmer_save = False  # Flag to prevent double-save in auto-switch
        self._dimmer_reset_visual = (
            False  # Flag to prevent config override after visual reset
        )

        self._setup_icons()
        self.create_widgets()
        self.load_settings()

        # Safety watchdog: keeps the dimmer in sync with the slider
        self._start_dimmer_watchdog()

        # Setup scroll speed after all widgets are created
        self._setup_native_scroll_speed(self.main_container)

        # Bind events
        self.bind("<Configure>", self._on_window_configure)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.bind_all("<ButtonRelease-1>", self._on_suggest_global_click, add="+")
        self.bind_all("<MouseWheel>", self._on_suggest_scroll, add="+")

        # LCU watcher — dimmer auto-switch + arena ban/pick (luôn chạy nền).
        # Khởi động sau khi UI đã dựng xong (callback cần widget tồn tại).
        self.arena_watcher = LcuWatcher(
            update_status_callback=lambda text, color: self._post_to_ui(
                self.update_status, text, color
            ),
            on_gaming_callback=lambda: self._post_to_ui(self.switch_to_gaming_mode),
            on_browsing_callback=lambda: self._post_to_ui(self.switch_to_browsing_mode),
            arena_event_callback=lambda text, color: self._post_to_ui(
                self.update_arena_live, text, color
            ),
            connection_callback=lambda connected: self._post_to_ui(
                self._on_arena_connection_changed, connected
            ),
            notification_callback=self.notifier.notify,
            roster_callback=lambda owned: self._post_to_ui(
                self._on_arena_roster_update, owned
            ),
        )
        self._show_ready_window()

    def _show_ready_window(self) -> None:
        """Complete hidden-window initialization before watcher activity."""
        self.update()
        self.deiconify()
        self.arena_watcher.start()

    def _post_to_ui(self, callback, *args) -> bool:
        """Run a callback on Tk's thread and ignore callbacks after shutdown."""
        if not self.__dict__.get("_ui_callbacks_enabled", True):
            return False

        def invoke() -> None:
            if self.__dict__.get("_ui_callbacks_enabled", True):
                callback(*args)

        try:
            self.after(0, invoke)
        except (RuntimeError, tk.TclError) as error:
            logger.debug("UI callback skipped: %s", error)
            return False
        return True

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

    # ================= Arena — Tự ban / chọn tướng (dời từ SettingsModal) =================



    # ================= Toast =================

    def _show_toast(self, text: str, color: str) -> None:
        """Toast nhỏ góc trên phải, tự biến mất sau 3.5s.

        - WS_EX_NOACTIVATE: không steal focus (user đang gõ app khác)
        - App minimize → toast vô hình (owned window) → bíp cho nghe thấy
        """
        try:
            if self.state() != "normal":
                # Toast không hiện khi minimize — bíp thay thế
                try:
                    winsound.MessageBeep(winsound.MB_OK)
                except Exception:
                    pass
                return
            if getattr(self, "_toast_win", None) and self._toast_win.winfo_exists():
                self._toast_win.destroy()
            win = tk.Toplevel(self)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.configure(bg=Colors.BG)
            frame = ctk.CTkFrame(
                win,
                fg_color=Colors.SECONDARY,
                corner_radius=8,
                border_width=1,
                border_color=color,
            )
            frame.pack(padx=1, pady=1)
            ctk.CTkLabel(
                frame,
                text=text,
                font=(AppConfig.FONT_FAMILY, 13, "bold"),
                text_color=color,
            ).pack(padx=14, pady=8)
            win.update_idletasks()
            x = max(0, self.winfo_rootx() + self.winfo_width() - win.winfo_width() - 12)
            y = self.winfo_rooty() + 8
            win.geometry(f"+{x}+{y}")
            # Không cho toast nhận focus/activation (Windows) — user đang gõ
            # app khác không bị nuốt phím
            try:
                import ctypes

                GWL_EXSTYLE = -20
                WS_EX_NOACTIVATE = 0x08000000
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOZORDER = 0x0004
                SWP_FRAMECHANGED = 0x0020
                user32 = ctypes.windll.user32
                hwnd = win.winfo_id()
                ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE)
                user32.SetWindowPos(
                    hwnd, 0, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
                )
            except Exception:
                pass
            self._toast_win = win
            win.after(
                3500,
                lambda: win.destroy() if win.winfo_exists() else None,
            )
        except Exception:
            pass  # toast là phụ — hỏng thì bỏ qua, không crash app

    # ================= UI Scale (footer) =================

    def _create_ui_scale_widget(self, parent) -> None:
        """UI Scale dropdown — đặt ở footer (setting cửa sổ, không phải feature)."""
        scale_frame = ctk.CTkFrame(parent, fg_color="transparent")
        scale_frame.pack(side="right")

        ctk.CTkLabel(
            scale_frame,
            text="🔍 UI Scale",
            font=(AppConfig.FONT_FAMILY, 12),
            text_color=Colors.MUTED_FG,
        ).pack(side="left", padx=(0, 4))

        scale_options = [
            "80%",
            "90%",
            "100%",
            "110%",
            "120%",
            "125%",
            "130%",
            "140%",
            "150%",
            "160%",
            "175%",
            "200%",
        ]
        current_scale = config_manager.get("ui_scale")
        if current_scale is None:
            current_scale = DefaultConfig.UI_SCALE
        current_scale = normalize_ui_scale(current_scale)
        current_display = f"{int(current_scale * 100)}%"
        if current_display not in scale_options:
            current_display = "125%"

        self.scale_dropdown = ctk.CTkOptionMenu(
            scale_frame,
            values=scale_options,
            command=self._on_scale_changed,
            width=90,
            height=28,
            fg_color=Colors.SECONDARY,
            button_color=Colors.BORDER,
            button_hover_color=Colors.RING,
            dropdown_fg_color=Colors.CARD,
            dropdown_hover_color=Colors.SECONDARY,
            font=(AppConfig.FONT_FAMILY, 12),
        )
        self.scale_dropdown.set(current_display)
        self.scale_dropdown.pack(side="left")

    def _on_scale_changed(self, choice: str) -> None:
        """Đổi UI scale → hỏi xác nhận rồi restart."""
        new_scale = int(choice.replace("%", "")) / 100.0
        current_scale = normalize_ui_scale(config_manager.get("ui_scale"))
        if new_scale == current_scale:
            return

        result = messagebox.askyesno(
            "Restart Required",
            f"Changing UI scale to {choice} requires restarting the app.\n\n"
            "Do you want to restart now?",
            parent=self,
        )
        if result:
            if not config_manager.set("ui_scale", new_scale):
                self.scale_dropdown.set(f"{int(current_scale * 100)}%")
                logger.error("UI scale save failed; keeping the previous state")
                return
            logger.info(f"UI scale changed to {new_scale}")
            self._restart_app()
        else:
            current_display = f"{int(current_scale * 100)}%"
            self.scale_dropdown.set(current_display)

    def create_widgets(self) -> None:
        # --- Footer (pinned bottom) ---
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=24, pady=(0, 15))

        # Author Link
        author_frame = ctk.CTkFrame(footer, fg_color="transparent")
        author_frame.pack(side="left")

        ctk.CTkLabel(
            author_frame,
            text="Created by ",
            font=(AppConfig.FONT_FAMILY, 13),
            text_color=Colors.MUTED_FG,
        ).pack(side="left")

        self.author_link = ctk.CTkLabel(
            author_frame,
            text="Gohans",
            font=(AppConfig.FONT_FAMILY, 13, "bold"),
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

        # Version badge + UI Scale
        ctk.CTkLabel(
            footer,
            text="v2.0",
            font=("JetBrains Mono", 12, "bold"),
            text_color=Colors.MUTED_FG,
        ).pack(side="right", padx=(0, 8))
        self._create_ui_scale_widget(footer)

        # Compact LCU status badge (footer — click to reload champion names)
        self._footer_lcu_badge = ctk.CTkLabel(
            footer,
            text="LCU: chưa kết nối",
            width=130,
            height=22,
            corner_radius=5,
            fg_color=Colors.RED,
            text_color=Colors.BG,
            font=(AppConfig.FONT_FAMILY, 11, "bold"),
        )
        self._footer_lcu_badge.pack(side="right", padx=(0, 8))

        # Click LCU badge → reload champions
        self._footer_lcu_badge.bind(
            "<Button-1>", lambda e: self._reload_owned_champions()
        )

        # Fixed top dock stays outside the scroll container.
        self.top_dock = ctk.CTkFrame(
            self,
            fg_color=Colors.SECONDARY,
            border_color=Colors.BORDER,
            border_width=1,
            corner_radius=8,
        )
        self.top_dock.pack(fill="x", padx=24, pady=(24, 0))
        self._create_activity_beacon(self.top_dock)
        self._create_action_buttons(self.top_dock)

        # --- Main Layout: 2-column grid ---
        # Left column (65%): Arena champion-select controls
        # Right column (35%): Status, Dimmer, LCU Automation, Action buttons
        self.main_container = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=Colors.BORDER,
            scrollbar_button_hover_color=Colors.RING,
        )
        self.main_container.pack(fill="both", expand=True, padx=24, pady=(12, 0))

        # --- Main Layout: 2-column grid + full-width bottom row ---
        # grid_row 0: left_column (Arena, 65%) | right_column (Status/Dimmer/LCU, 35%)
        # grid_row 1: bottom_row (full-width live events)
        # NOTE: CTkScrollableFrame internally uses pack — grid must be on a
        # CTkFrame wrapper packed into it.
        self._grid_wrapper = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self._grid_wrapper.pack(fill="both", expand=True)
        self._grid_wrapper.grid_columnconfigure(0, weight=65)
        self._grid_wrapper.grid_columnconfigure(1, weight=35)

        self.bottom_row = ctk.CTkFrame(self._grid_wrapper, fg_color="transparent")

        # Left column — Arena (rộng hơn)
        self.left_column = ctk.CTkFrame(self._grid_wrapper, fg_color="transparent")
        self.left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        # Right column — Status, Settings, LCU, Actions
        self.right_column = ctk.CTkFrame(self._grid_wrapper, fg_color="transparent")
        self.right_column.grid(row=0, column=1, sticky="nsew")

        self._create_arena_section(self.left_column)
        self._create_right_side(self.right_column)

        self.bottom_row.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        self._grid_wrapper.grid_rowconfigure(0, weight=1)

        # Live Arena events log (full-width, inside the single scroll area).
        self._create_live_events(self.bottom_row)

        # Setup scroll speed after all widgets are created
        self._setup_native_scroll_speed(self.main_container)

    def _create_live_events(self, parent) -> None:
        """Create the live events log frame (bottom, full-width)."""
        self.arena_live_frame = ctk.CTkFrame(
            parent,
            fg_color=Colors.SECONDARY,
            border_color=Colors.BORDER,
            border_width=1,
            corner_radius=6,
        )
        self.arena_live_frame.pack(fill="x", pady=(0, 0))
        log_header = ctk.CTkFrame(self.arena_live_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=8, pady=(7, 4))
        ctk.CTkLabel(
            log_header,
            text="Hoạt động gần đây",
            anchor="w",
            font=(AppConfig.FONT_FAMILY, 12, "bold"),
            text_color=Colors.FG,
        ).pack(side="left")
        self.arena_live_count_label = ctk.CTkLabel(
            log_header,
            text="Chưa có hoạt động",
            anchor="e",
            font=(AppConfig.FONT_FAMILY, 11, "bold"),
            text_color=Colors.MUTED_FG,
        )
        self.arena_live_count_label.pack(side="right")
        self.arena_live_rows = ctk.CTkFrame(
            self.arena_live_frame,
            fg_color="transparent",
        )
        self.arena_live_rows.pack(fill="x", padx=6, pady=(0, 6))
        ctk.CTkLabel(
            self.arena_live_rows,
            text="Chưa có hoạt động.",
            anchor="w",
            font=(AppConfig.FONT_FAMILY, 12),
            text_color=Colors.MUTED_FG,
        ).pack(fill="x", padx=4, pady=(0, 2))

    def _create_right_side(self, parent) -> None:
        """Right column: Dimmer settings, LCU Automation toggles, and action buttons."""
        # --- Settings Card (Dimmer) ---
        settings_card = CardFrame(parent)
        settings_card.pack(fill="x", pady=(0, 15))

        # Dimmer Control
        dimmer_row = ctk.CTkFrame(settings_card, fg_color="transparent")
        dimmer_row.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(
            dimmer_row,
            text="Ghost Dimmer",
            font=(AppConfig.FONT_FAMILY, 14),
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
            font=(AppConfig.FONT_FAMILY, 12),
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

        # Floor is 50: Windows rejects gamma ramps dimmer than ~50% linear
        # (SetDeviceGammaRamp heuristics), and curves below 50 look bad.
        self.dimmer_slider = ctk.CTkSlider(
            settings_card,
            from_=50,
            to=100,
            number_of_steps=50,
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
            text="Auto switch to Gaming mode",
            font=(AppConfig.FONT_FAMILY, 13),
            text_color=Colors.FG,
        ).pack(side="left")

        # Lấy giá trị config, mặc định True nếu không có
        config_val = config_manager.get("auto_dimmer_switch_enabled")
        if config_val is None:
            config_val = True
        self.auto_dimmer_switch_var = ctk.BooleanVar(value=config_val)

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

        # --- LCU Automation Card ---
        pref_card = CardFrame(parent)
        pref_card.pack(fill="x", pady=(0, 15))

        header = ctk.CTkFrame(pref_card, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(12, 2))
        ctk.CTkLabel(
            header,
            text="🤖 LCU Automation",
            font=(AppConfig.FONT_FAMILY, 15, "bold"),
            text_color=Colors.PRIMARY,
        ).pack(side="left")

        # Auto Accept Toggle (NEW)
        accept_row = ctk.CTkFrame(pref_card, fg_color="transparent")
        accept_row.pack(fill="x", padx=15, pady=(6, 6))

        ctk.CTkLabel(
            accept_row,
            text="Auto Accept Match",
            font=(AppConfig.FONT_FAMILY, 14),
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

        # Startup Toggle
        startup_row = ctk.CTkFrame(pref_card, fg_color="transparent")
        startup_row.pack(fill="x", padx=15, pady=(6, 4))

        ctk.CTkLabel(
            startup_row,
            text="Launch on Startup",
            font=(AppConfig.FONT_FAMILY, 14),
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

        for index, spec in enumerate(DISCORD_NOTIFICATION_SPECS):
            variable = getattr(self, f"{spec.config_key}_var")
            row = ctk.CTkFrame(pref_card, fg_color="transparent")
            row.pack(
                fill="x",
                padx=15,
                pady=(6 if index == 0 else 2, 12 if index == 2 else 2),
            )
            ctk.CTkLabel(
                row,
                text=spec.label,
                font=(AppConfig.FONT_FAMILY, 14),
                text_color=Colors.FG,
            ).pack(side="left")
            ctk.CTkSwitch(
                row,
                text="",
                width=40,
                variable=variable,
                command=lambda current_spec=spec, var=variable: self._toggle_discord_notification(
                    current_spec, var
                ),
                progress_color=Colors.GREEN,
                fg_color=Colors.SECONDARY,
            ).pack(side="right")

    def _create_activity_beacon(self, parent) -> None:
        """Create a compact, high-signal runtime status beacon."""
        self.activity_beacon = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )
        self.activity_beacon.pack(fill="x", padx=12, pady=(10, 0))

        self.status_beacon_dot = ctk.CTkLabel(
            self.activity_beacon,
            text="●",
            width=22,
            anchor="w",
            font=(AppConfig.FONT_FAMILY, 18, "bold"),
            text_color=Colors.MUTED_FG,
        )
        self.status_beacon_dot.pack(side="left")

        self.status_label = ctk.CTkLabel(
            self.activity_beacon,
            text=UIStatus.READY,
            anchor="w",
            font=(AppConfig.FONT_FAMILY, 14, "bold"),
            text_color=Colors.FG,
        )
        self.status_label.pack(side="left", fill="x", expand=True, padx=(4, 8))
        self._beacon_pulse_id = self.after(600, self._activity_beacon_tick)

    def _activity_beacon_tick(self) -> None:
        """Pulse only while the bot is actively processing a phase."""
        try:
            if self._beacon_pulse_active:
                self._beacon_pulse_visible = not self._beacon_pulse_visible
                dot_color = (
                    self._beacon_color
                    if self._beacon_pulse_visible
                    else Colors.BORDER
                )
                self.status_beacon_dot.configure(text_color=dot_color)
            else:
                self._beacon_pulse_visible = True
                self.status_beacon_dot.configure(text_color=self._beacon_color)
        except Exception:
            return
        self._beacon_pulse_id = self.after(600, self._activity_beacon_tick)

    def _create_action_buttons(self, parent) -> None:
        """Create fixed START/STOP actions outside the scroll container."""
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=(8, 10))
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        self.start_btn = ctk.CTkButton(
            btn_frame,
            text="START BOT",
            font=(AppConfig.FONT_FAMILY, 15, "bold"),
            height=40,
            fg_color=Colors.PRIMARY,
            text_color=Colors.PRIMARY_FG,
            hover_color=Colors.FG,
            corner_radius=8,
            command=self.start_bot,
        )
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        self.stop_btn = ctk.CTkButton(
            btn_frame,
            text="STOP",
            font=(AppConfig.FONT_FAMILY, 15, "bold"),
            height=40,
            fg_color=Colors.RED,
            text_color=Colors.PRIMARY_FG,
            hover_color="#e57373",  # Brighter red on hover
            corner_radius=8,
            state="disabled",
            command=self.stop_bot,
        )
        self.stop_btn.grid(row=0, column=1, sticky="ew", padx=(5, 0))



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

    # === Native Scroll Speed ===

    def _get_os_scroll_lines(self) -> int:
        """Get the number of lines to scroll from Windows settings."""
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop")
            value, _ = winreg.QueryValueEx(key, "WheelScrollLines")
            winreg.CloseKey(key)
            return int(value)
        except Exception:
            return 3  # Windows default

    def _setup_native_scroll_speed(self, scrollable_frame) -> None:
        """Override scroll speed to match OS settings."""
        scroll_lines = self._get_os_scroll_lines()

        # Get the internal canvas from CTkScrollableFrame
        canvas = scrollable_frame._parent_canvas

        def on_mousewheel(event):
            self._on_suggest_scroll(event)
            # delta is typically 120 per notch on Windows
            # Canvas units use the same line count as the Windows setting.
            scroll_amount = -1 * (event.delta // 120) * scroll_lines
            canvas.yview_scroll(scroll_amount, "units")
            return "break"  # Prevent default handling

        def bind_recursive(widget):
            """Bind mousewheel to widget and all its descendants."""
            try:
                widget.bind("<MouseWheel>", on_mousewheel)
            except (NotImplementedError, tk.TclError):
                pass  # Some widgets don't support bind
            for child in widget.winfo_children():
                bind_recursive(child)

        # Bind now and also after widget updates
        bind_recursive(scrollable_frame)

        # Re-bind after idle to catch dynamically added children
        def rebind():
            bind_recursive(scrollable_frame)

        scrollable_frame.after(100, rebind)

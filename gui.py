import customtkinter as ctk  # type: ignore
import tkinter as tk
from tkinter import messagebox
import webbrowser
import time
import threading
import os
import winsound  # beep khi app minimize (toast vô hình lúc đó)
from typing import Optional, Dict, List, Tuple
from PIL import Image, ImageDraw

from arena_config import (
    NOT_SET_LABEL,
    NO_PICK_LABEL,
    OPTIONAL_PICK_FIELDS,
    ArenaConfigIssue,
    champion_id,
    validate_arena_config,
)
from config import config_manager
from bot import AntiFateBot
from lcu_watcher import LcuWatcher
from utils.windows import DimmerController, set_autostart
from utils.lcu import lcu
from constants import (
    AppConfig,
    Colors,
    DefaultConfig,
    DISCORD_NOTIFICATION_SPECS,
    NotificationSpec,
    UIStatus,
)
from logger import logger
from notifications import HermesNotifier


ARENA_FIELD_LABELS = {
    "ban": "Tướng cần ban",
    "main": "Tướng chính",
    "b1": "Dự bị 1",
    "b2": "Dự bị 2",
    "b3": "Dự bị 3",
}

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
        # Apply UI scaling BEFORE super().__init__() for clean initialization
        # Default to 1.25x (~16px effective) for readability; user can change
        # via footer dropdown (persisted to config).
        saved_scale = config_manager.get("ui_scale")
        if saved_scale is None:
            saved_scale = DefaultConfig.UI_SCALE
            config_manager.set("ui_scale", saved_scale)
        saved_scale = max(0.8, min(2.0, float(saved_scale)))  # Wider range for 16px+
        ctk.set_widget_scaling(saved_scale)
        ctk.set_window_scaling(saved_scale)

        super().__init__()
        # self.withdraw()  # Temporarily disabled to debug visibility

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
        self._arena_automation_enabled = False
        self._arena_live_events: List[Tuple[str, str, str]] = []
        self.notifier = HermesNotifier()
        self.dimmer = DimmerController()
        self._dimmer_watchdog_id = None
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

        # Final show
        self.update_idletasks()
        # self.deiconify() # Disabled with withdraw

        # Bind events
        self.bind("<Configure>", self._on_window_configure)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.bind_all("<ButtonRelease-1>", self._on_suggest_global_click, add="+")
        self.bind_all("<MouseWheel>", self._on_suggest_scroll, add="+")

        # LCU watcher — dimmer auto-switch + arena ban/pick (luôn chạy nền).
        # Khởi động sau khi UI đã dựng xong (callback cần widget tồn tại).
        self.arena_watcher = LcuWatcher(
            update_status_callback=self.update_status,
            on_gaming_callback=self.switch_to_gaming_mode,
            on_browsing_callback=self.switch_to_browsing_mode,
            arena_event_callback=self.update_arena_live,
            connection_callback=self._on_arena_connection_changed,
            notification_callback=self.notifier.notify,
        )
        self.arena_watcher.start()

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

    def _create_arena_section(self, parent) -> None:
        """Arena champ select: toggle ban/pick + chọn tướng (main/dự bị/ban).

        Danh sách tướng lấy từ LCU (owned-champions-minimal) ở background —
        không block UI. Tướng lưu theo championId (ổn định hơn tên).
        """
        section = CardFrame(parent)
        section.pack(fill="x", pady=(0, 5))

        header = ctk.CTkFrame(section, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(12, 2))
        ctk.CTkLabel(
            header,
            text="🧙 Arena — Tự ban / chọn tướng",
            font=(AppConfig.FONT_FAMILY, 15, "bold"),
            text_color=Colors.PRIMARY,
        ).pack(side="left")
        ctk.CTkLabel(
            header,
            text="chỉ chạy khi chơi Arena",
            font=(AppConfig.FONT_FAMILY, 12),
            text_color=Colors.MUTED_FG,
        ).pack(side="right")

        body = ctk.CTkFrame(section, fg_color="transparent")
        body.pack(fill="x", padx=14, pady=(0, 12))

        # Toggles — mặc định TẮT, user bật từng cái để test dần.
        # Mỗi toggle nằm NGAY TRÊN combo của nó: ban ↔ "Tướng cần ban",
        # pick ↔ "Tướng chính + dự bị 1-3" (không tách lẻ).
        self.auto_ban_var = ctk.BooleanVar(
            value=bool(config_manager.get("auto_ban_enabled"))
        )
        self.auto_pick_var = ctk.BooleanVar(
            value=bool(config_manager.get("auto_pick_enabled"))
        )

        # Comboboxes tướng
        self._arena_owned: List[dict] = []
        self._arena_client_connected = False
        self._arena_roster_known = False
        self._arena_roster_loading = True
        self._arena_roster_error = False
        self._arena_display_to_id: Dict[str, int] = {}
        self._arena_display_to_id_normalized: Dict[str, int] = {}
        self._arena_id_to_display: Dict[int, str] = {}
        self._arena_owned_ids: set[int] = set()
        self._arena_cached_names = self._normalize_arena_champion_names(
            config_manager.get("arena_champion_names")
        )
        self._refresh_arena_name_maps()
        self.arena_combos: Dict[str, ctk.CTkComboBox] = {}
        self.arena_field_status: Dict[str, ctk.CTkLabel] = {}
        self._arena_field_error_visible: Dict[str, bool] = {
            key: False for key in ("ban", "main", "b1", "b2", "b3")
        }
        # MRU — 5 tướng chọn gần nhất mỗi field (gợi ý lên đầu)
        recent = config_manager.get("arena_recent")
        if not isinstance(recent, dict):  # config.json sửa tay hỏng — an toàn
            recent = {}
        self._arena_recent: Dict[str, List[int]] = {}
        for k in ("ban", "main", "b1", "b2", "b3"):
            normalized_recent: List[int] = []
            for raw_id in recent.get(k) or []:
                cid = champion_id(raw_id)
                if cid > 0 and cid not in normalized_recent:
                    normalized_recent.append(cid)
                if len(normalized_recent) >= 5:
                    break
            self._arena_recent[k] = normalized_recent
        # Fetch generation — spam nút ⟳ có nhiều thread fetch chồng nhau;
        # chỉ kết quả của generation MỚI NHẤT được áp dụng.
        self._arena_fetch_gen: int = 0
        self._arena_validation_after_id = None

        chain = list(config_manager.get("arena_pick_chain") or [0, 0, 0, 0])
        while len(chain) < 4:
            chain.append(0)
        self._arena_loaded_ids = {
            "ban": champion_id(config_manager.get("arena_ban_champ") or 0),
            "main": champion_id(chain[0]),
            "b1": champion_id(chain[1]),
            "b2": champion_id(chain[2]),
            "b3": champion_id(chain[3]),
        }
        self._arena_draft_keys: set[str] = set()

        def make_combo_row(parent, key, label) -> None:
            """1 hàng: label + combo tướng (indent theo toggle chủ)."""
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", pady=3, padx=(20, 0))
            ctk.CTkLabel(
                row,
                text=label,
                width=110,
                anchor="w",
                font=(AppConfig.FONT_FAMILY, 13),
                text_color=Colors.FG,
            ).pack(side="left")
            empty_label = (
                NO_PICK_LABEL if key in OPTIONAL_PICK_FIELDS else NOT_SET_LABEL
            )
            combo = ctk.CTkComboBox(
                row,
                values=[empty_label],
                width=200,
                # CTkComboBox gọi command(value) — nhận value vào _v, giữ key
                command=lambda _v, k=key: self._on_arena_combo(k),
            )
            combo.pack(side="left", fill="x", expand=True)
            self.arena_combos[key] = combo
            field_status = ctk.CTkLabel(
                parent,
                text="Chưa chọn",
                anchor="w",
                font=(AppConfig.FONT_FAMILY, 12),
                text_color=Colors.MUTED_FG,
            )
            field_status.pack(fill="x", padx=(130, 0), pady=(0, 1))
            self.arena_field_status[key] = field_status
            # Gõ chữ → gợi ý HIỆN NGAY dưới ô (max 5); ↑↓ chọn; Enter xác nhận;
            # Esc đóng; click entry → gõ sửa trực tiếp; mũi tên ▾ → 10 tướng
            try:
                combo._entry.bind(
                    "<KeyRelease>",
                    lambda e, k=key: self._on_arena_combo_key(k, e),
                )
                for virtual_event in (
                    "<<Paste>>",
                    "<<Cut>>",
                    "<<Clear>>",
                    "<<Undo>>",
                    "<<Redo>>",
                ):
                    combo._entry.bind(
                        virtual_event,
                        lambda _e, k=key: self._on_arena_virtual_edit(k),
                        add="+",
                    )
                combo._entry.bind(
                    "<Button-1>",
                    lambda e, k=key: self._on_arena_combo_click(k),
                )
                combo._entry.bind(
                    "<Down>",
                    lambda e, k=key: self._suggest_nav(k, 1),
                )
                combo._entry.bind(
                    "<Up>",
                    lambda e, k=key: self._suggest_nav(k, -1),
                )
                combo._entry.bind(
                    "<Return>",
                    lambda e, k=key: self._suggest_enter(k),
                )
                combo._entry.bind(
                    "<Escape>",
                    lambda e: self._suggest_escape(),
                )
                combo._entry.bind(
                    "<FocusOut>",
                    lambda e, k=key: self.after(
                        150, lambda: self._on_arena_combo_focus_out(k)
                    ),
                )
                # Thay handler mũi tên CTk (tag_bind nội bộ _clicked) bằng
                # tag_unbind + widget bind — mở danh sách rộng (max 10) 1 lần
                # duy nhất, không double-fire
                try:
                    combo._canvas.tag_unbind("dropdown_arrow", "<Button-1>")
                    combo._canvas.tag_unbind("right_parts", "<Button-1>")
                except Exception:
                    pass
                combo._canvas.bind(
                    "<Button-1>",
                    lambda e, k=key: self._on_arena_combo_arrow(k),
                )
            except Exception as e:
                logger.warning(f"Combo bind failed ({key}): {e}")

        # --- Ban: toggle + nhóm field có thể thu gọn ---
        self.auto_ban_switch = ctk.CTkSwitch(
            body,
            text="Auto ban tướng",
            variable=self.auto_ban_var,
            command=self._on_auto_ban_toggle,
        )
        self.auto_ban_switch.pack(anchor="w", pady=(0, 2))
        self.arena_ban_fields_frame = ctk.CTkFrame(
            body,
            fg_color="transparent",
        )
        self.arena_ban_fields_frame.pack(fill="x", pady=(0, 2))
        make_combo_row(self.arena_ban_fields_frame, "ban", "Tướng cần ban")

        # --- Pick: toggle + nhóm field có thể thu gọn ---
        self.auto_pick_switch = ctk.CTkSwitch(
            body,
            text="Auto chọn tướng (main → dự bị, không khóa)",
            variable=self.auto_pick_var,
            command=self._on_auto_pick_toggle,
        )
        self.auto_pick_switch.pack(anchor="w", pady=(10, 2))
        self.arena_pick_fields_frame = ctk.CTkFrame(
            body,
            fg_color="transparent",
        )
        self.arena_pick_fields_frame.pack(fill="x")
        for key, label in [
            ("main", "Tướng chính"),
            ("b1", "Dự bị 1"),
            ("b2", "Dự bị 2"),
            ("b3", "Dự bị 3"),
        ]:
            make_combo_row(self.arena_pick_fields_frame, key, label)

        # Compact Arena loadout strip: config state + bot state.
        self.arena_summary_frame = ctk.CTkFrame(
            section,
            fg_color=Colors.SECONDARY,
            corner_radius=6,
        )
        self.arena_summary_frame.pack(
            fill="x",
            padx=14,
            pady=(0, 8),
            before=body,
        )

        summary_header = ctk.CTkFrame(
            self.arena_summary_frame,
            fg_color="transparent",
        )
        summary_header.pack(fill="x", padx=10, pady=(7, 2))
        self.arena_summary_badge = ctk.CTkLabel(
            summary_header,
            text="Đang tải",
            width=108,
            height=22,
            corner_radius=5,
            fg_color=Colors.BORDER,
            text_color=Colors.MUTED_FG,
            font=(AppConfig.FONT_FAMILY, 11, "bold"),
        )
        self.arena_summary_badge.pack(side="left")

        self.arena_summary_rows = ctk.CTkFrame(
            self.arena_summary_frame,
            fg_color="transparent",
        )
        self.arena_summary_rows.pack(fill="x", padx=10, pady=(0, 2))
        self.arena_summary_value_labels: Dict[str, ctk.CTkLabel] = {}
        self.arena_summary_tag_labels: Dict[str, ctk.CTkLabel] = {}

        def create_summary_row(key: str, label: str) -> None:
            row = ctk.CTkFrame(self.arena_summary_rows, fg_color="transparent")
            row.pack(fill="x", pady=(0, 2))
            ctk.CTkLabel(
                row,
                text=label,
                width=72,
                anchor="w",
                font=(AppConfig.FONT_FAMILY, 12, "bold"),
                text_color=Colors.MUTED_FG,
            ).pack(side="left")
            tag = ctk.CTkLabel(
                row,
                text="Tắt",
                width=52,
                height=20,
                corner_radius=4,
                fg_color=Colors.BORDER,
                text_color=Colors.MUTED_FG,
                font=(AppConfig.FONT_FAMILY, 11, "bold"),
            )
            tag.pack(side="right")
            value = ctk.CTkLabel(
                row,
                text="Chưa chọn",
                anchor="w",
                justify="left",
                wraplength=360,
                font=(AppConfig.FONT_FAMILY, 12),
                text_color=Colors.FG,
            )
            value.pack(side="left", fill="x", expand=True, padx=(4, 6))
            self.arena_summary_value_labels[key] = value
            self.arena_summary_tag_labels[key] = tag

        create_summary_row("ban", "🛡 CẤM")
        create_summary_row("pick", "🎯 CHỌN")

        self.arena_summary_note = ctk.CTkLabel(
            self.arena_summary_frame,
            text="",
            anchor="w",
            justify="left",
            wraplength=360,
            font=(AppConfig.FONT_FAMILY, 12),
            text_color=Colors.MUTED_FG,
        )
        self.arena_summary_note.pack(fill="x", padx=10, pady=(2, 7))

        for key, combo in self.arena_combos.items():
            combo.set(
                self._arena_display_for_id(self._arena_loaded_ids.get(key, 0), key)
            )
        self._refresh_arena_field_visibility()
        self._refresh_arena_validation()
        self._reload_owned_champions()

    def _reload_owned_champions(self) -> None:
        """Fetch lại roster; connection và roster result được theo dõi riêng."""
        self._arena_fetch_gen += 1
        gen = self._arena_fetch_gen
        self._arena_roster_loading = True
        self._arena_roster_error = False
        try:
            self._refresh_arena_validation()
        except Exception:
            pass
        threading.Thread(
            target=self._load_owned_champions, args=(gen,), daemon=True
        ).start()

    def _load_owned_champions(self, gen: int) -> None:
        try:
            phase = lcu.gameflow_phase()
        except Exception:
            phase = None
        try:
            roster = lcu.owned_champions_result()
        except Exception:
            roster = None
        connected = phase is not None or roster is not None
        owned = roster or []
        roster_loaded = roster is not None
        try:
            self.after(
                0,
                lambda: self._apply_owned_champions(
                    owned, gen, connected, roster_loaded
                ),
            )
        except Exception:
            pass  # app đang thoát — bỏ qua

    @staticmethod
    def _normalize_arena_champion_names(value: object) -> Dict[int, str]:
        """Return cached champion names from config."""
        if not isinstance(value, dict):
            return {}
        names: Dict[int, str] = {}
        for raw_id, raw_name in value.items():
            try:
                cid = champion_id(raw_id)
            except (TypeError, ValueError):
                continue
            if cid <= 0 or not isinstance(raw_name, str):
                continue
            name = raw_name.strip()
            if name:
                names[cid] = name
        return names

    def _refresh_arena_name_maps(self) -> None:
        """Build lookup maps from saved names plus live client names."""
        names = dict(self._arena_cached_names)
        for champion in self._arena_owned:
            cid = champion_id(champion.get("id"))
            name = str(champion.get("name") or "").strip()
            if cid > 0 and name:
                names[cid] = name
        self._arena_id_to_display = names
        self._arena_display_to_id = {name: cid for cid, name in names.items()}
        self._arena_display_to_id_normalized = {
            name.casefold(): cid for name, cid in self._arena_display_to_id.items()
        }

    def _save_arena_champion_names(self) -> None:
        """Persist champion names so the next app start can show labels offline."""
        data = {
            str(cid): name
            for cid, name in sorted(self._arena_cached_names.items())
            if cid > 0 and name
        }
        if data != config_manager.get("arena_champion_names"):
            config_manager.set("arena_champion_names", data)

    def _remember_arena_champion(self, champion_id_value: object, name: object) -> None:
        cid = champion_id(champion_id_value)
        label = str(name or "").strip()
        if cid <= 0 or not label:
            return
        if label in (NO_PICK_LABEL, NOT_SET_LABEL, "Đang kiểm tra tướng đã lưu"):
            return
        if label == "Tướng không còn trong trò chơi":
            return
        if self._arena_cached_names.get(cid) == label:
            return
        self._arena_cached_names[cid] = label
        self._refresh_arena_name_maps()
        self._save_arena_champion_names()

    def _apply_owned_champions(
        self,
        owned: List[dict],
        gen: int,
        connected: bool,
        roster_loaded: bool,
    ) -> None:
        if gen != self._arena_fetch_gen:
            return  # kết quả cũ (user đã bấm ⟳ lần nữa) — bỏ qua
        try:
            self._arena_client_connected = connected
            self._arena_roster_known = roster_loaded
            self._arena_roster_loading = False
            self._arena_roster_error = not roster_loaded
            self._arena_owned = sorted(owned, key=lambda c: c["name"].lower())
            self._arena_owned_ids = {
                champion_id(champion.get("id"))
                for champion in self._arena_owned
                if champion_id(champion.get("id")) > 0
            }
            cache_changed = False
            for champion in self._arena_owned:
                cid = champion_id(champion.get("id"))
                name = str(champion.get("name") or "").strip()
                if cid > 0 and name and self._arena_cached_names.get(cid) != name:
                    self._arena_cached_names[cid] = name
                    cache_changed = True
            self._refresh_arena_name_maps()
            if cache_changed:
                self._save_arena_champion_names()
            for key, combo in self.arena_combos.items():
                # Values = gợi ý 5 tướng (MRU + A-Z) — không đổ 160+ vào dropdown
                combo.configure(
                    values=[
                        NO_PICK_LABEL if key in OPTIONAL_PICK_FIELDS else NOT_SET_LABEL
                    ]
                    + self._recent_names(key, 5)
                )
                # Không ghi đè nếu user đã gõ/chọn gì đó trong lúc fetch
                if not self._arena_field_is_draft(key):
                    cid = self._arena_loaded_ids.get(key, 0)
                    combo.set(self._arena_display_for_id(cid, key))

            self._set_arena_client_status(self._arena_client_connected)
            self._refresh_arena_validation()
        except Exception:
            pass  # app đang thoát — bỏ qua

    def _on_arena_connection_changed(self, connected: bool) -> None:
        """Keep LCU badge current even when the client starts after the app."""
        def _update() -> None:
            try:
                self._arena_client_connected = bool(connected)
                if not connected and not self._arena_roster_known:
                    self._arena_roster_loading = False
                    self._arena_roster_error = False
                self._set_arena_client_status(self._arena_client_connected)
                self._refresh_arena_validation()
                if (
                    connected
                    and not self._arena_roster_known
                    and not self._arena_roster_loading
                ):
                    self._reload_owned_champions()
            except Exception:
                pass

        try:
            self.after(0, _update)
        except Exception:
            pass

    def _set_arena_client_status(self, connected: bool) -> None:
        """Show LCU connection; roster loading is a separate state."""
        if connected:
            badge_text = "LCU: đã kết nối"
            badge_color = Colors.GREEN
        else:
            badge_text = "LCU: chưa kết nối"
            badge_color = Colors.RED
        try:
            self._footer_lcu_badge.configure(
                text=badge_text,
                fg_color=badge_color,
                text_color=Colors.BG,
            )
        except Exception:
            pass

    def _arena_display_for_id(self, value: object, key: Optional[str] = None) -> str:
        """Display a saved id using the field's empty-value label."""
        cid = champion_id(value)
        if cid == 0:
            return NO_PICK_LABEL if key in OPTIONAL_PICK_FIELDS else NOT_SET_LABEL
        name = self._arena_id_to_display.get(cid) or self._arena_cached_names.get(cid)
        if name:
            return name
        if self._arena_roster_known:
            return "Tướng không còn trong trò chơi"
        return "Tướng đã lưu"

    def _arena_field_is_draft(self, key: str) -> bool:
        """Return True only while the user has unconfirmed text in the field."""
        return key in self._arena_draft_keys

    def _arena_feature_enabled_for_field(self, key: str) -> bool:
        """Return whether the feature owning this field is enabled."""
        if key == "ban":
            return bool(self.auto_ban_var.get())
        return bool(self.auto_pick_var.get())

    def _arena_config_issues(self) -> List[ArenaConfigIssue]:
        owned_ids = None
        if self._arena_roster_known:
            owned_ids = self._arena_owned_ids
        return validate_arena_config(
            auto_ban_enabled=bool(self.auto_ban_var.get()),
            auto_pick_enabled=bool(self.auto_pick_var.get()),
            ban_champion_id=self._arena_loaded_ids.get("ban", 0),
            pick_chain=[self._arena_loaded_ids.get(key, 0) for key in ("main", "b1", "b2", "b3")],
            owned_ids=owned_ids,
        )

    def _arena_draft_issues(self) -> List[ArenaConfigIssue]:
        issues: List[ArenaConfigIssue] = []
        for key in self.arena_combos:
            if (
                self._arena_feature_enabled_for_field(key)
                and self._arena_field_is_draft(key)
            ):
                issues.append(
                    ArenaConfigIssue(
                        "draft",
                        (key,),
                        f"{ARENA_FIELD_LABELS[key]} đang nhập nhưng chưa xác nhận.",
                    )
                )
        return issues

    def _arena_issue_text(self, issue: ArenaConfigIssue) -> str:
        fields = ", ".join(ARENA_FIELD_LABELS[key] for key in issue.fields)
        if issue.code == "ban_pick_conflict":
            pick_fields = [
                ARENA_FIELD_LABELS[key] for key in issue.fields if key != "ban"
            ]
            picks = ", ".join(pick_fields) or "tướng chọn"
            champ = self._arena_display_for_id(self._arena_loaded_ids.get("ban", 0), "ban")
            if champ in (NOT_SET_LABEL, "Tướng đã lưu", "Tướng không còn trong trò chơi"):
                champ = "Tướng cần ban"
            return f"{champ} đang ở cả Tướng cần ban và {picks}. Chọn tướng khác cho một bên."
        if issue.code == "duplicate_pick":
            champ = self._arena_display_for_id(
                self._arena_loaded_ids.get(issue.fields[0], 0), issue.fields[0]
            )
            if champ in (NOT_SET_LABEL, "Tướng đã lưu", "Tướng không còn trong trò chơi"):
                return f"Các ô chọn tướng đang bị trùng: {fields}. Mỗi ô phải là một tướng khác."
            return f"{champ} đang được chọn ở {fields}. Mỗi ô phải là một tướng khác."
        messages = {
            "draft": "Xác nhận tướng đã chọn bằng phím Enter.",
            "missing_ban": "Chọn tướng cần cấm.",
            "missing_main": "Chọn tướng chính.",
            "ban_not_owned": "Tướng cấm không còn trong trò chơi.",
            "pick_not_owned": "Tướng chọn không còn trong trò chơi.",
        }
        message = messages.get(issue.code, issue.message)
        if issue.code == "draft":
            return message
        return f"{fields}: {message}"

    def _arena_field_issue_text(
        self, key: str, issues: List[ArenaConfigIssue]
    ) -> str:
        if any(issue.code in ("missing_ban", "missing_main") for issue in issues):
            return "Cần chọn tướng này."
        for issue in issues:
            if issue.code == "ban_pick_conflict":
                if key == "ban":
                    pick_fields = [
                        ARENA_FIELD_LABELS[field]
                        for field in issue.fields
                        if field != "ban"
                    ]
                    picks = ", ".join(pick_fields) or "tướng chọn"
                    return f"Đang trùng với {picks}."
                return "Đang trùng với tướng cần ban."
            if issue.code == "duplicate_pick":
                other_fields = [
                    ARENA_FIELD_LABELS[field]
                    for field in issue.fields
                    if field != key
                ]
                others = ", ".join(other_fields) or "ô chọn khác"
                return f"Đang trùng với {others}."
            if issue.code in ("ban_not_owned", "pick_not_owned"):
                return "Tướng này không còn trong trò chơi."
        return "Kiểm tra lại tướng đã chọn."

    def _arena_summary_value(self, key: str) -> str:
        combo = self.arena_combos[key]
        if self._arena_field_is_draft(key):
            if not self._arena_feature_enabled_for_field(key):
                return "Chưa chọn"
            return "Đang xác nhận"
        if key in OPTIONAL_PICK_FIELDS and champion_id(
            self._arena_loaded_ids.get(key, 0)
        ) == 0:
            return ARENA_FIELD_LABELS[key]
        return self._arena_display_for_id(
            self._arena_loaded_ids.get(key, 0), key
        )

    def _set_arena_field_visual(
        self, key: str, issues: List[ArenaConfigIssue]
    ) -> None:
        combo = self.arena_combos[key]
        field_issues = [issue for issue in issues if key in issue.fields]
        draft = self._arena_field_is_draft(key)
        cid = champion_id(self._arena_loaded_ids.get(key, 0))

        if not self._arena_feature_enabled_for_field(key):
            border = Colors.BORDER
            text_color = Colors.MUTED_FG
            text = "Tính năng này đang tắt."
            try:
                combo.configure(border_color=border)
                self.arena_field_status[key].configure(
                    text=text,
                    text_color=text_color,
                )
            except Exception:
                pass
            return

        if draft:
            if self._arena_field_error_visible.get(key, False):
                border = Colors.RED
                text_color = Colors.RED
                text = "Chưa xác nhận. Chọn tướng hoặc nhấn Enter."
            else:
                border = Colors.BLUE
                text_color = Colors.BLUE
                text = "Đang nhập. Nhấn Enter để xác nhận."
        elif field_issues:
            is_missing = any(
                issue.code in ("missing_ban", "missing_main")
                for issue in field_issues
            )
            border = Colors.ORANGE if is_missing else Colors.RED
            text_color = border
            text = self._arena_field_issue_text(key, field_issues)
        elif cid > 0 and self._arena_roster_known and cid not in self._arena_owned_ids:
            is_active = (
                (key == "ban" and self.auto_ban_var.get())
                or (key != "ban" and self.auto_pick_var.get())
            )
            border = Colors.RED if is_active else Colors.ORANGE
            text_color = border
            text = (
                "Tướng này không còn trong trò chơi."
                if is_active
                else "Tướng đã lưu không còn trong trò chơi."
            )
        elif cid > 0:
            border = Colors.GREEN
            text_color = Colors.GREEN
            text = f"Đã chọn: {self._arena_display_for_id(cid, key)}"
        elif key == "ban" and self.auto_ban_var.get():
            border = Colors.ORANGE
            text_color = Colors.ORANGE
            text = "Cần chọn tướng cần cấm."
        elif key == "main" and self.auto_pick_var.get():
            border = Colors.ORANGE
            text_color = Colors.ORANGE
            text = "Cần chọn tướng chính."
        else:
            border = Colors.BORDER
            text_color = Colors.MUTED_FG
            text = "Chưa chọn" if key in ("ban", "main") else "Tùy chọn"

        try:
            combo.configure(border_color=border)
            self.arena_field_status[key].configure(
                text=text,
                text_color=text_color,
            )
        except Exception:
            pass

    def _schedule_arena_validation(self) -> None:
        """Debounce draft validation while the user is typing."""
        if self._arena_validation_after_id:
            try:
                self.after_cancel(self._arena_validation_after_id)
            except Exception:
                pass

        def _refresh() -> None:
            self._arena_validation_after_id = None
            self._refresh_arena_validation()

        self._arena_validation_after_id = self.after(180, _refresh)

    def _refresh_arena_validation(
        self, force_errors: bool = False
    ) -> List[ArenaConfigIssue]:
        """Refresh fields and the final ban/pick configuration summary."""
        issues = self._arena_draft_issues() + self._arena_config_issues()
        if force_errors:
            for issue in issues:
                for key in issue.fields:
                    self._arena_field_error_visible[key] = True

        for key in self.arena_combos:
            self._set_arena_field_visual(key, issues)

        auto_ban = bool(self.auto_ban_var.get())
        auto_pick = bool(self.auto_pick_var.get())
        has_active_saved_ids = any(
            champion_id(self._arena_loaded_ids.get(key, 0)) > 0
            for key in self.arena_combos
            if self._arena_feature_enabled_for_field(key)
        )
        if issues:
            badge_text = "Cần chỉnh sửa"
            summary_color = Colors.RED
        elif has_active_saved_ids and not self._arena_client_connected:
            badge_text = "Chờ LCU"
            summary_color = Colors.ORANGE
        elif has_active_saved_ids and self._arena_roster_loading:
            badge_text = "Đang tải"
            summary_color = Colors.ORANGE
        elif has_active_saved_ids and self._arena_roster_error:
            badge_text = "Chưa xác minh"
            summary_color = Colors.ORANGE
        elif not auto_ban and not auto_pick:
            badge_text = "Chưa bật"
            summary_color = Colors.MUTED_FG
        else:
            badge_text = "Sẵn sàng"
            summary_color = Colors.GREEN

        try:
            self.arena_summary_badge.configure(
                text=badge_text,
                fg_color=summary_color,
                text_color=Colors.BG if summary_color != Colors.MUTED_FG else Colors.FG,
            )

            scale = config_manager.get("ui_scale") or 1.0
            wraplength = int(360 / max(0.8, float(scale)))
            pick_values = " → ".join(
                self._arena_summary_value(key) for key in ("main", "b1", "b2", "b3")
            )
            summary_values = {
                "ban": self._arena_summary_value("ban"),
                "pick": pick_values,
            }
            summary_states = {
                "ban": ("Bật" if auto_ban else "Tắt", Colors.GREEN if auto_ban else Colors.BORDER),
                "pick": ("Bật" if auto_pick else "Tắt", Colors.GREEN if auto_pick else Colors.BORDER),
            }
            for key, value in summary_values.items():
                self.arena_summary_value_labels[key].configure(
                    text=value,
                    wraplength=wraplength,
                )
                tag, tag_color = summary_states[key]
                self.arena_summary_tag_labels[key].configure(
                    text=tag,
                    fg_color=tag_color,
                    text_color=(
                        Colors.BG if tag_color != Colors.BORDER else Colors.MUTED_FG
                    ),
                )

            notes = []
            if has_active_saved_ids:
                if not self._arena_client_connected:
                    notes.append("Chưa kết nối League of Legends để xác minh tướng đã lưu.")
                elif self._arena_roster_loading:
                    notes.append("Đang tải danh sách tướng từ League of Legends.")
                elif self._arena_roster_error:
                    notes.append("Chưa tải được danh sách tướng. Bấm badge LCU để thử lại.")
            if issues:
                notes.append(
                    "Cần hoàn thành:\n"
                    + "\n".join(f"• {self._arena_issue_text(issue)}" for issue in issues)
                )
            self.arena_summary_note.configure(
                text="\n".join(notes),
                text_color=summary_color if notes else Colors.MUTED_FG,
            )
        except Exception:
            pass
        return issues

    def _on_arena_combo_focus_out(self, key: str) -> None:
        self._commit_empty_optional_picks()
        self._hide_suggest()
        self._arena_field_error_visible[key] = True
        self._refresh_arena_validation()

    def _refresh_arena_field_visibility(self) -> None:
        """Hide inactive config groups without clearing their saved values."""
        if self.auto_ban_var.get():
            self.arena_ban_fields_frame.pack(
                fill="x",
                pady=(0, 2),
                before=self.auto_pick_switch,
            )
        else:
            self.arena_ban_fields_frame.pack_forget()

        if self.auto_pick_var.get():
            self.arena_pick_fields_frame.pack(fill="x")
        else:
            self.arena_pick_fields_frame.pack_forget()

    def _on_auto_ban_toggle(self) -> None:
        config_manager.set("auto_ban_enabled", self.auto_ban_var.get())
        self._refresh_arena_field_visibility()
        self._refresh_arena_validation()

    def _on_auto_pick_toggle(self) -> None:
        config_manager.set("auto_pick_enabled", self.auto_pick_var.get())
        self._refresh_arena_field_visibility()
        self._refresh_arena_validation()

    def _on_arena_combo(self, key: str) -> None:
        """User chọn tướng từ dropdown → lưu championId + cập nhật MRU."""
        combo = self.arena_combos[key]
        disp = combo.get().strip()
        if disp == NOT_SET_LABEL or (
            key in OPTIONAL_PICK_FIELDS and disp in ("", NO_PICK_LABEL)
        ):
            cid = 0
        else:
            cid = self._arena_display_to_id_normalized.get(disp.casefold())
            if cid is None:
                self._arena_field_error_visible[key] = True
                self._refresh_arena_validation()
                return  # text gõ tay không khớp tướng nào → không lưu
        if key == "ban":
            config_manager.set("arena_ban_champ", cid)
        else:
            order = {"main": 0, "b1": 1, "b2": 2, "b3": 3}
            chain = list(config_manager.get("arena_pick_chain") or [0, 0, 0, 0])
            while len(chain) < 4:
                chain.append(0)
            chain[order[key]] = cid
            config_manager.set("arena_pick_chain", chain)
        self._arena_loaded_ids[key] = cid
        self._arena_draft_keys.discard(key)
        self._arena_field_error_visible[key] = False
        if cid == 0 and disp in ("", NO_PICK_LABEL, NOT_SET_LABEL):
            combo.set(NO_PICK_LABEL if key in OPTIONAL_PICK_FIELDS else NOT_SET_LABEL)

        # MRU: tướng vừa chọn đẩy lên đầu (tối đa 5/field) — lần sau gợi ý trước
        if cid > 0:
            self._remember_arena_champion(
                cid,
                self._arena_id_to_display.get(cid) or disp,
            )
            recent = [cid] + [c for c in self._arena_recent.get(key, []) if c != cid]
            self._arena_recent[key] = recent[:5]
            config_manager.set("arena_recent", self._arena_recent)
        # Values = gợi ý 5 mới (không để lại list 25/full)
        try:
            combo.configure(
                values=[
                    NO_PICK_LABEL if key in OPTIONAL_PICK_FIELDS else NOT_SET_LABEL
                ]
                + self._recent_names(key, 5)
            )
        except Exception:
            pass
        self._refresh_arena_validation()

    def _commit_empty_optional_picks(self) -> None:
        """Treat empty backup fields as an explicit clear, not an unconfirmed draft."""
        for key in OPTIONAL_PICK_FIELDS:
            combo = self.arena_combos[key]
            text = combo.get().strip()
            saved_id = champion_id(self._arena_loaded_ids.get(key, 0))
            if text in ("", NOT_SET_LABEL) or (text == NO_PICK_LABEL and saved_id > 0):
                self._on_arena_combo(key)

    def _recent_names(self, key: str, limit: int) -> List[str]:
        """Tên tướng ưu tiên MRU (chọn gần nhất lên đầu) + bù A-Z, tối đa `limit`."""
        names: List[str] = []
        seen: set = set()
        for cid in self._arena_recent.get(key, []):
            name = self._arena_id_to_display.get(cid)
            if name and name not in seen:
                names.append(name)
                seen.add(name)
        for champ in self._arena_owned:  # đã sort A-Z trong _apply_owned_champions
            name = champ["name"]
            if name not in seen:
                names.append(name)
                seen.add(name)
                if len(names) >= limit:
                    break
        return names[:limit]

    # ================= Autocomplete tự chế — gõ đến đâu hiện đến đó =================
    # CTk dropdown là tk.Menu (post → grab bàn phím → nuốt chữ gõ tiếp).
    # Thay bằng Toplevel + Listbox KHÔNG grab: entry vẫn gõ, list hiện ngay.

    def _ensure_suggest(self) -> tk.Toplevel:
        """Tạo (lazy) cửa sổ gợi ý dùng chung cho mọi combo."""
        win = getattr(self, "_suggest_win", None)
        if win is not None and win.winfo_exists():
            return win
        win = tk.Toplevel(self)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=Colors.BORDER)
        lb = tk.Listbox(
            win,
            font=(AppConfig.FONT_FAMILY, 13),
            bg=Colors.SECONDARY,
            fg=Colors.FG,
            selectbackground=Colors.BLUE,
            selectforeground=Colors.BG,
            highlightthickness=0,
            borderwidth=1,
            activestyle="none",
            exportselection=False,
        )
        lb.pack(fill="both", expand=True)
        lb.bind("<Button-1>", self._suggest_pick)
        lb.bind("<Motion>", self._suggest_motion)
        self._suggest_win = win
        self._suggest_listbox = lb
        self._suggest_key: Optional[str] = None
        self._suggest_items: List[str] = []
        return win

    def _suggest_visible(self) -> bool:
        win = getattr(self, "_suggest_win", None)
        return win is not None and win.winfo_exists() and win.state() != "withdrawn"

    def _hide_suggest(self) -> None:
        win = getattr(self, "_suggest_win", None)
        if win is not None and win.winfo_exists():
            win.withdraw()
        self._suggest_key = None

    def _suggest_index(self) -> int:
        lb = self._suggest_listbox
        sel = lb.curselection()
        return sel[0] if sel else 0

    def _show_suggest(self, key: str, items: List[str], select_index: int = 0) -> None:
        """Hiện gợi ý ngay dưới ô đang gõ; optional backup đã gồm Không."""
        try:
            combo = self.arena_combos[key]
            if not items:
                self._hide_suggest()
                return
            win = self._ensure_suggest()
            lb = self._suggest_listbox
            self._suggest_key = key
            self._suggest_items = items
            lb.delete(0, tk.END)
            for it in items:
                lb.insert(tk.END, it)
            idx = max(0, min(select_index, len(items) - 1))
            lb.selection_clear(0, tk.END)
            lb.selection_set(idx)
            lb.activate(idx)
            lb.see(idx)
            # Định vị ngay dưới entry của combo
            x = combo.winfo_rootx()
            y = combo.winfo_rooty() + combo.winfo_height() + 2
            width = max(combo.winfo_width(), 190)
            lb.configure(width=max(22, width // 8))
            height = min(len(items), 6) * 22 + 6
            win.geometry(f"{width}x{height}+{x}+{y}")
            win.deiconify()
            win.lift()
        except Exception:
            pass

    def _update_suggest(self, key: str) -> None:
        """Lọc theo chữ đang gõ (max 5, ưu tiên MRU) + hiện ngay."""
        combo = self.arena_combos[key]
        typed = combo.get().lower().strip()
        all_names = [c["name"] for c in self._arena_owned]
        if typed:
            matches = [n for n in all_names if typed in n.lower()]
            recent = [n for n in self._recent_names(key, 25) if n in matches]
            final: List[str] = []
            for n in recent + matches:
                if n not in final:
                    final.append(n)
                    if len(final) >= 5:
                        break
        else:
            final = self._recent_names(key, 5)
        if key in OPTIONAL_PICK_FIELDS:
            final = [NO_PICK_LABEL] + [name for name in final if name != NO_PICK_LABEL]
            final = final[:5]
        self._show_suggest(key, final)

    def _on_arena_combo_key(self, key: str, event=None) -> None:
        """Gõ chữ → gợi ý HIỆN NGAY dưới ô (tối đa 5)."""
        try:
            if event is not None and getattr(event, "keysym", "") in {
                "Up",
                "Down",
                "Left",
                "Right",
                "Return",
                "Escape",
            }:
                # Navigation key handlers already changed the list selection.
                # Re-filtering here would reset it to index zero.
                return
            self._arena_field_error_visible[key] = False
            self._arena_draft_keys.add(key)
            if key in OPTIONAL_PICK_FIELDS and not self.arena_combos[key].get().strip():
                self._on_arena_combo(key)
            self._update_suggest(key)
            self._schedule_arena_validation()
        except Exception:
            pass

    def _on_arena_virtual_edit(self, key: str) -> None:
        """Mark clipboard/IME edits as draft even without a KeyRelease."""
        self._on_arena_combo_key(key)

    def _on_arena_combo_click(self, key: str) -> None:
        """Click vào ô → chỉ để gõ sửa (gợi ý tự hiện khi gõ ký tự đầu)."""
        try:
            self.arena_combos[key]._entry.focus_set()
        except Exception:
            pass

    def _suggest_nav(self, key: str, delta: int) -> str:
        """↑↓ → di chuyển lựa chọn trong list gợi ý."""
        if not self._suggest_visible():
            self._update_suggest(key)  # chưa hiện → mở luôn
            return "break"
        lb = self._suggest_listbox
        n = lb.size()
        if n == 0:
            return "break"
        idx = self._suggest_index() + delta
        idx = max(0, min(n - 1, idx))
        lb.selection_clear(0, tk.END)
        lb.selection_set(idx)
        lb.activate(idx)
        lb.see(idx)
        return "break"  # chặn di chuyển cursor trong entry

    def _suggest_enter(self, key: str) -> str:
        """Enter → chọn mục đang highlight; không có gợi ý → gõ tay đúng tên lưu luôn."""
        if self._suggest_visible() and self._suggest_items:
            idx = self._suggest_index()
            if 0 <= idx < len(self._suggest_items):
                name = self._suggest_items[idx]
                self.arena_combos[key].set(name)
                self._hide_suggest()
                self._on_arena_combo(key)
                return "break"
        self._on_arena_combo_enter(key)
        return "break"

    def _suggest_escape(self) -> str:
        self._hide_suggest()
        return "break"

    def _on_suggest_global_click(self, event) -> None:
        """Dismiss suggestions after a click outside the active field/list."""
        if not self._suggest_visible():
            return
        widget = getattr(event, "widget", None)
        if widget is self._suggest_listbox:
            return
        key = self._suggest_key
        combo = self.arena_combos.get(key) if key else None
        if combo is not None and any(
            widget is allowed
            for allowed in (
                combo,
                getattr(combo, "_entry", None),
                getattr(combo, "_canvas", None),
            )
        ):
            return
        self._hide_suggest()

    def _on_suggest_scroll(self, _event=None) -> None:
        """Dismiss suggestions when the user scrolls the settings view."""
        if self._suggest_visible():
            self._hide_suggest()

    def _suggest_motion(self, event) -> None:
        """Hover → highlight mục dưới chuột."""
        try:
            lb = self._suggest_listbox
            idx = lb.nearest(event.y)
            if 0 <= idx < lb.size():
                lb.selection_clear(0, tk.END)
                lb.selection_set(idx)
                lb.activate(idx)
        except Exception:
            pass

    def _suggest_pick(self, event=None) -> None:
        """Click mục → chọn luôn (như chọn từ dropdown)."""
        key = self._suggest_key
        if key is None:
            return
        try:
            lb = self._suggest_listbox
            idx = lb.nearest(event.y) if event is not None else self._suggest_index()
            if 0 <= idx < len(self._suggest_items):
                name = self._suggest_items[idx]
                self.arena_combos[key].set(name)
                self._hide_suggest()
                self._on_arena_combo(key)
        except Exception:
            pass

    def _on_arena_combo_enter(self, key: str) -> None:
        """Enter với text gõ tay: khớp tên thật thì lưu như chọn từ dropdown."""
        try:
            combo = self.arena_combos[key]
            disp = combo.get().strip()
            if (
                disp == NOT_SET_LABEL
                or (key in OPTIONAL_PICK_FIELDS and disp in ("", NO_PICK_LABEL))
                or disp.casefold() in self._arena_display_to_id_normalized
            ):
                if disp.casefold() in self._arena_display_to_id_normalized:
                    combo.set(
                        self._arena_id_to_display[
                            self._arena_display_to_id_normalized[disp.casefold()]
                        ]
                    )
                self._on_arena_combo(key)
            else:
                self._arena_field_error_visible[key] = True
                self._refresh_arena_validation()
        except Exception:
            pass

    def _on_arena_combo_arrow(self, key: str) -> None:
        """Bấm mũi tên → danh sách rộng hơn (TỐI ĐA 10 — MRU + A-Z)."""
        items = self._recent_names(key, 10)
        if key in OPTIONAL_PICK_FIELDS:
            items = [NO_PICK_LABEL] + [name for name in items if name != NO_PICK_LABEL]
            items = items[:10]
        self._show_suggest(key, items)

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
        current_scale = max(0.8, min(2.0, float(current_scale)))
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
        current_scale = config_manager.get("ui_scale") or 1.0
        if new_scale == current_scale:
            return

        result = messagebox.askyesno(
            "Restart Required",
            f"Changing UI scale to {choice} requires restarting the app.\n\n"
            "Do you want to restart now?",
            parent=self,
        )
        if result:
            config_manager.set("ui_scale", new_scale)
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

    def _on_dimmer_mode_changed(self, mode: str, automatic: bool = False) -> None:
        """Handle dimmer mode switch between Gaming and Browsing."""
        if automatic and not self._automatic_dimmer_allowed():
            return
        # Save current slider value to the current mode before switching
        current_slider_val = int(self.dimmer_slider.get())
        old_mode = config_manager.get("dimmer_mode")

        # Map display name to internal key
        if "Gaming" in mode:
            new_mode = "gaming"
        else:
            new_mode = "browsing"

        # Save current value to the OLD mode (skip if called from switch_to_gaming_mode
        # OR if dimmer was visually reset to 100% by reset_dimmer())
        if not self._skip_dimmer_save and not self._dimmer_reset_visual:
            if old_mode == "gaming":
                config_manager.set("dimmer_gaming_value", current_slider_val)
            else:
                config_manager.set("dimmer_browsing_value", current_slider_val)

        # Reset flags
        self._skip_dimmer_save = False
        self._dimmer_reset_visual = False

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

        new_val = int(max(50, min(100, int(new_val))))
        self.dimmer_slider.set(float(new_val))
        if self.dimmer_enabled_var.get():
            self.dimmer.set_brightness(new_val)
        config_manager.set("dimmer_value", new_val)
        logger.info(f"Dimmer mode switched to: {new_mode} (brightness: {new_val}%)")

    def _automatic_dimmer_allowed(self) -> bool:
        """Single gate for every automatic dimmer write."""
        return (
            config_manager.get("auto_dimmer_switch_enabled") is True
            and self.dimmer_enabled_var.get() is True
        )

    def _apply_automatic_mode(self, mode: str) -> None:
        """Apply a deferred automatic mode change only if gates still allow it."""
        if not self._automatic_dimmer_allowed():
            self._skip_dimmer_save = False
            return
        self.dimmer_mode_segment.set(mode)
        self._on_dimmer_mode_changed(mode, automatic=True)

    def _apply_automatic_brightness(self, level: int) -> None:
        """Apply deferred automatic brightness only if gates still allow it."""
        if not self._automatic_dimmer_allowed():
            self._dimmer_reset_visual = False
            return
        self.dimmer_slider.set(float(level))
        self.dimmer.set_brightness(level)

    def switch_to_gaming_mode(self) -> None:
        """Callback to switch to Gaming dimmer mode (called by bot on champ select)."""
        if not self._automatic_dimmer_allowed():
            return

        current_mode = config_manager.get("dimmer_mode")
        if current_mode != "gaming":
            logger.info("Champ select detected - switching to Gaming dimmer mode")

            # FIX (v1.15): save browsing from CONFIG, NOT from the slider.
            # reset_dimmer() runs first (same bot tick) and queues a visual
            # slider.set(100) via after(0); by the time this callback reads
            # the slider the main thread may have applied it, overwriting the
            # real browsing value with 100 (race - reproduced in logs:
            # "Saved browsing dimmer value: 100%").
            if current_mode == "browsing":
                browsing_val = config_manager.get("dimmer_browsing_value")
                if browsing_val is None:
                    browsing_val = 100
                config_manager.set("dimmer_browsing_value", int(browsing_val))
                logger.info(f"Saved browsing dimmer value: {int(browsing_val)}%")

            # Set flag to prevent _on_dimmer_mode_changed from re-saving (would save wrong value)
            self._skip_dimmer_save = True
            self.after(10, lambda: self._apply_automatic_mode("🎮 Gaming"))
        else:
            # FIX (v1.15 review): mode is already gaming - re-apply the
            # configured gaming value anyway. reset_dimmer() (success
            # callback of the previous match) set the slider AND the real
            # brightness to 100; without this re-apply the screen would
            # stay at 100% from the second match onward (dimmer silently
            # dead - reproduced in the user's logs).
            gv = config_manager.get("dimmer_gaming_value")
            if gv is None:
                gv = 100
            gv = int(max(50, min(100, int(gv))))
            self._dimmer_reset_visual = False
            self.after(0, lambda: self._apply_automatic_brightness(gv))
            logger.info(
                f"Champ select detected - re-applying Gaming dimmer "
                f"(already in gaming mode, {gv}%)"
            )

    def switch_to_browsing_mode(self) -> None:
        """Callback từ LCU watcher — hết trận/trở về phòng chờ → Browsing."""
        if not self._automatic_dimmer_allowed():
            return

        current_mode = config_manager.get("dimmer_mode")
        if current_mode != "browsing":
            logger.info("Match ended - switching to Browsing dimmer mode")

            # Lưu gaming value từ CONFIG (không đọc slider — tránh race
            # với reset_dimmer đang set slider về 100).
            if current_mode == "gaming":
                gaming_val = config_manager.get("dimmer_gaming_value")
                if gaming_val is None:
                    gaming_val = 100
                config_manager.set("dimmer_gaming_value", int(gaming_val))

            self._skip_dimmer_save = True
            self.after(10, lambda: self._apply_automatic_mode("🌐 Browsing"))
        else:
            # Đã ở browsing — re-apply giá trị (phòng reset_dimmer đã set 100)
            bv = config_manager.get("dimmer_browsing_value")
            if bv is None:
                bv = 100
            bv = int(max(50, min(100, int(bv))))
            self._dimmer_reset_visual = False
            self.after(0, lambda: self._apply_automatic_brightness(bv))
            logger.info(f"Match ended - re-applying Browsing dimmer ({bv}%)")

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
            # Scroll by OS-configured number of lines (each line ~20 pixels)
            pixels_per_line = 20
            scroll_amount = -1 * (event.delta // 120) * scroll_lines * pixels_per_line
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

    # === UI Scaling ===

    def _restart_app(self) -> None:
        """Restart the application to apply UI scale cleanly."""
        import sys
        import subprocess

        # Clean up before restart
        if self.bot:
            self.bot.stop()
        self.dimmer.close()

        # Get the executable path
        if getattr(sys, "frozen", False):
            # Running as compiled exe
            exe_path = sys.executable
        else:
            # Running as script
            exe_path = sys.executable
            script_path = os.path.abspath(sys.argv[0])
            # --restart: child bỏ qua single-instance mutex (cha chưa thoát
            # hẳn khi child import — nếu không sẽ chết vì mutex, app biến mất)
            subprocess.Popen([exe_path, script_path, "--restart"])
            self.destroy()
            return

        subprocess.Popen([exe_path, "--restart"])
        self.destroy()

    def load_settings(self) -> None:
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

        try:
            dimmer_val = int(dimmer_val)
        except (TypeError, ValueError):
            dimmer_val = 100  # config.json hỏng — fallback an toàn
        self.dimmer_slider.set(float(max(50, min(100, dimmer_val))))
        self.dimmer_enabled_var.set(dimmer_enabled)
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

        for spec in DISCORD_NOTIFICATION_SPECS:
            variable = getattr(self, f"{spec.config_key}_var")
            variable.set(bool(config_manager.get(spec.config_key)))
            self.notifier.set_event_enabled(spec.event_name, variable.get())

        # Apply settings immediately
        self.toggle_dimmer(save=False)
        logger.info(f"Dimmer backend active: {self.dimmer.backend_name}")

    def toggle_startup(self) -> None:
        is_enabled = self.auto_startup_enabled_var.get()
        config_manager.set("auto_startup_enabled", is_enabled)
        set_autostart(AppConfig.APP_NAME, add=is_enabled)
        logger.info(f"Auto Startup toggled: {is_enabled}")

    def toggle_auto_accept(self) -> None:
        is_enabled = self.auto_accept_enabled_var.get()
        config_manager.set("auto_accept_enabled", is_enabled)
        logger.info(f"Auto Accept Match toggled: {is_enabled}")

    def _toggle_discord_notification(
        self,
        spec: NotificationSpec,
        variable,
    ) -> None:
        is_enabled = bool(variable.get())
        config_manager.set(spec.config_key, is_enabled)
        self.notifier.set_event_enabled(spec.event_name, is_enabled)
        logger.info(f"Discord notification toggled: {spec.event_name}={is_enabled}")

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
            # Batch config updates into a single file write (slider drags
            # fire dozens of events per second - one write per event made
            # the UI janky and hammered the disk).
            config_manager.set("dimmer_value", int(value), save=False)

            # Clear visual reset flag when user actively drags slider
            # This means user is now manually setting brightness
            self._dimmer_reset_visual = False

            # Also save to the current mode's specific value
            current_mode = config_manager.get("dimmer_mode") or "browsing"
            if current_mode == "gaming":
                config_manager.set("dimmer_gaming_value", int(value), save=False)
            else:
                config_manager.set("dimmer_browsing_value", int(value), save=False)
            config_manager.save_config()
            logger.debug(
                f"Slider changed to {int(value)}% ({current_mode} mode) - "
                f"gaming={config_manager.get('dimmer_gaming_value')} "
                f"browsing={config_manager.get('dimmer_browsing_value')}"
            )

    def _status_update_allowed(
        self, generation: Optional[int], allow_stopping: bool = False
    ) -> bool:
        if generation is None:
            return True
        if generation != self._bot_generation:
            return False
        return allow_stopping or not self._bot_stopping

    def update_status(
        self,
        text: str,
        color: Optional[str] = None,
        generation: Optional[int] = None,
        allow_stopping: bool = False,
    ) -> None:
        """Update the fixed activity beacon with the current bot state."""
        if not self._status_update_allowed(generation, allow_stopping):
            return

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
        display_text = self._friendly_status_text(text)
        self._beacon_color = final_color
        self._beacon_pulse_active = color_str in {"blue", "purple", "orange"}
        self._beacon_pulse_visible = True

        # Toast cho sự kiện quan trọng — user biết ngay thành công / lỗi.
        toast = None
        if "thất bại" in display_text.lower() or "không đặt được" in display_text.lower():
            toast = (display_text, Colors.STATUS_RED)
        elif display_text == UIStatus.CHAMP_SELECT:
            toast = ("Đã vào màn hình chọn tướng.", Colors.STATUS_GREEN)
        elif "Trận bị hủy" in display_text:
            toast = (display_text, Colors.STATUS_ORANGE)

        def _render() -> None:
            if not self._status_update_allowed(generation, allow_stopping):
                return
            try:
                self.status_beacon_dot.configure(text_color=final_color)
                self.status_label.configure(
                    text=display_text,
                    text_color=Colors.FG,
                )
            except Exception:
                pass

        # Thread-safe update — beacon stays outside the scroll container.
        self.after(0, _render)
        if toast:
            self.after(
                0,
                lambda: self._show_toast(*toast)
                if self._status_update_allowed(generation, allow_stopping)
                else None,
            )

    @staticmethod
    def _friendly_status_text(text: str) -> str:
        clean = str(text).strip().lstrip("⚠️").strip()
        replacements = {
            "Không kết nối được client LoL": "Chưa kết nối được với League of Legends",
            "LCU: chưa kết nối được client": "Chưa kết nối được với League of Legends",
        }
        if clean.startswith("Error:"):
            return "Đã xảy ra lỗi. Hãy thử lại."
        return replacements.get(clean, clean)

    @staticmethod
    def _arena_log_parts(text: str, color: str) -> Tuple[str, str]:
        normalized = " ".join(str(text).replace("\n", " ").split())
        lower = normalized.casefold()
        color = str(color).lower()

        if lower.startswith("ban:"):
            if "verified" in lower or "đã được xác minh" in lower:
                return "Cấm tướng", "Đã chọn tướng cấm."
            if "retry" in lower or "không được xác minh" in lower:
                return "Cấm tướng", "Chưa chọn được tướng cấm. Đang thử lại."
            if "client chưa tạo" in lower or "action chưa mở" in lower:
                return "Cấm tướng", "Đang chờ đến lượt cấm."
            if "bị chặn" in lower or "chưa đặt" in lower:
                return "Cấm tướng", "Chưa chọn tướng cấm."
            return "Cấm tướng", "Đang xử lý tướng cấm."

        if lower.startswith("pick:"):
            if "chưa đọc được danh sách" in lower or "danh sách ban chưa" in lower:
                return "Chọn tướng", "Chưa cập nhật được danh sách tướng bị cấm."
            if "client chưa tạo" in lower or "action chưa mở" in lower:
                return "Chọn tướng", "Đang chờ đến lượt chọn tướng."
            if "verified" in lower or "đã được xác minh" in lower:
                return "Chọn tướng", "Đã chọn tướng."
            if "retry" in lower or "không được xác minh" in lower:
                return "Chọn tướng", "Chưa chọn được tướng. Đang thử lại."
            if "fail" in lower or "bị chặn" in lower or "dừng" in lower or "chưa đặt" in lower:
                return "Chọn tướng", "Tự động chọn tướng đã dừng."
            return "Chọn tướng", "Đang xử lý tướng."

        # Câu chi tiết có tên tướng — watcher đã gửi sẵn tiếng người.
        if lower.startswith(("đã cấm:", "đang cấm:", "các tướng bị cấm:")):
            return "Cấm tướng", normalized
        if lower.startswith(("đã chọn:", "đang chọn:")):
            return "Chọn tướng", normalized
        if lower.startswith(("bạn đã tự chọn:", "bạn đã tự cấm:")):
            return "Chọn tướng", normalized
        if "bị cấm → chọn:" in lower or "bị lấy → chọn:" in lower or "bị lấy → chuyển" in lower:
            return "Chọn tướng", normalized
        if "chưa thành công — thử lại" in lower:
            if lower.startswith("cấm"):
                return "Cấm tướng", normalized
            return "Chọn tướng", normalized
        if lower.startswith("không cấm được:"):
            return "Cần chú ý", normalized

        if "champ select mở" in lower:
            return "Arena", "Đã vào màn hình chọn tướng."
        if "rời champ select" in lower:
            if "inprogress" in lower:
                return "Arena", "Đã vào trận."
            if "matchmaking" in lower or "lobby" in lower:
                return "Arena", "Đang tìm trận mới."
            return "Arena", "Đã rời màn hình chọn tướng."
        if "chưa kết nối" in lower:
            return "Kết nối", "Chưa kết nối được với League of Legends."
        if "đang tìm" in lower:
            return "Trận", "Đang tìm trận."
        if "có trận" in lower or "ready-check" in lower:
            return "Trận", "Có trận mới — đang chờ xác nhận."
        if "đang chờ champ-select" in lower:
            return "Arena", "Đang chờ màn hình chọn tướng."
        if "không phải arena" in lower:
            return "Arena", "Đây không phải chế độ Arena."
        if "bạn đã tự chọn tướng" in lower:
            return "Chọn tướng", "Bạn đã tự chọn — bot dừng."
        if "bị người khác lấy" in lower:
            return "Chọn tướng", "Tướng đã chọn bị lấy — đang chọn tướng khác."
        if "automation" in lower:
            return "Arena", "Tự động chọn tướng đã dừng."
        if "bị chặn" in lower:
            return "Cần chú ý", "Cấu hình chưa sẵn sàng. Kiểm tra lại cài đặt."
        if color == "red":
            return "Cần chú ý", "Đã xảy ra lỗi. Kiểm tra lại cài đặt."
        if color == "orange":
            return "Đang chờ", "Đang cập nhật thông tin."
        return "Arena", normalized

    def _render_arena_live(self) -> None:
        for child in self.arena_live_rows.winfo_children():
            child.destroy()

        self.arena_live_count_label.configure(
            text=f"{len(self._arena_live_events)} mục"
            if self._arena_live_events
            else "Chưa có hoạt động"
        )
        if not self._arena_live_events:
            ctk.CTkLabel(
                self.arena_live_rows,
                text="Chưa có hoạt động.",
                anchor="w",
                font=(AppConfig.FONT_FAMILY, 12),
                text_color=Colors.MUTED_FG,
            ).pack(fill="x", padx=4, pady=(0, 2))
            return

        scale = config_manager.get("ui_scale") or 1.0
        wraplength = int(300 / max(0.8, float(scale)))
        color_map: Dict[str, str] = {
            "green": Colors.GREEN,
            "red": Colors.RED,
            "blue": Colors.BLUE,
            "orange": Colors.ORANGE,
            "gray": Colors.MUTED_FG,
        }
        for timestamp, text, logical_color in self._arena_live_events:
            badge, body = self._arena_log_parts(text, logical_color)
            event_color = color_map.get(logical_color, Colors.MUTED_FG)
            body = " ".join(body.split())
            if len(body) > 96:
                body = body[:93].rstrip() + "..."
            row = ctk.CTkFrame(
                self.arena_live_rows,
                fg_color=Colors.CARD,
                corner_radius=4,
            )
            row.pack(fill="x", pady=(0, 2))
            ctk.CTkLabel(
                row,
                text=timestamp,
                width=50,
                anchor="w",
                font=(AppConfig.FONT_FAMILY, 11),
                text_color=Colors.MUTED_FG,
            ).pack(side="left", padx=(6, 0))
            ctk.CTkLabel(
                row,
                text=badge,
                width=82,
                height=20,
                corner_radius=4,
                fg_color=event_color,
                text_color=Colors.BG,
                font=(AppConfig.FONT_FAMILY, 11, "bold"),
            ).pack(side="left", padx=(2, 6))
            ctk.CTkLabel(
                row,
                text=body,
                anchor="w",
                justify="left",
                wraplength=wraplength,
                font=(AppConfig.FONT_FAMILY, 12),
                text_color=Colors.FG,
            ).pack(side="left", fill="x", expand=True, padx=(0, 6))

    def update_arena_live(self, text: str, color: str = "gray") -> None:
        """Render compact Arena events without stealing focus."""
        logical_color = str(color).lower()
        timestamp = time.strftime("%H:%M:%S")

        def _update() -> None:
            try:
                self._arena_live_events.insert(0, (timestamp, text, logical_color))
                self._arena_live_events = self._arena_live_events[:7]
                self._render_arena_live()
            except Exception:
                pass  # app đang thoát — bỏ qua callback nền

        try:
            self.after(0, _update)
        except Exception:
            pass

    def _on_bot_status(self, generation: int, text: str, color: str) -> None:
        """Accept status only from the current, non-stopping bot thread."""
        if generation != self._bot_generation or self._bot_stopping:
            return
        self.update_status(text, color, generation=generation)

    def _on_bot_success(self, generation: int) -> None:
        if generation == self._bot_generation and not self._bot_stopping:
            self.reset_dimmer()

    def _on_bot_champ_select(self, generation: int) -> None:
        if generation == self._bot_generation and not self._bot_stopping:
            self.switch_to_gaming_mode()

    def on_bot_stop(
        self, status: str, color: str, generation: Optional[int] = None
    ) -> None:
        def _update_ui():
            if generation is not None and generation != self._bot_generation:
                return
            self.update_status(
                status,
                color,
                generation=generation,
                allow_stopping=True,
            )
            self._bot_stopping = False
            self.bot = None
            if status == UIStatus.CHAMP_SELECT and self._arena_automation_enabled:
                # Auto Accept đã xong, nhưng Arena hover-only vẫn cần giữ gate
                # cho đến khi user bấm STOP.
                self.start_btn.configure(state="disabled")
                self.stop_btn.configure(state="normal")
            else:
                self._set_arena_automation_enabled(False)
                self.start_btn.configure(state="normal")
                self.stop_btn.configure(state="disabled")

        self.after(0, _update_ui)

    def _start_dimmer_watchdog(self) -> None:
        """Periodically verify the dimmer state matches the slider (safety).

        Guards against drift caused by Windows adaptive brightness or a
        partially failed set. Re-applies the target when it detects a gap.
        """
        self._dimmer_watchdog_id = self.after(5000, self._dimmer_watchdog_tick)

    def _dimmer_watchdog_tick(self) -> None:
        try:
            if self._automatic_dimmer_allowed():
                target = int(self.dimmer_slider.get())
                if not self.dimmer.verify(target):
                    # Re-apply only after 2 consecutive drifts (~10s): a
                    # single mismatch can be transient (or a Night Light
                    # style colour filter) - don't fight it immediately.
                    self._watchdog_drift_count += 1
                    if self._watchdog_drift_count >= 2:
                        logger.info(
                            f"Dimmer watchdog: display drifted from {target}% - "
                            f"re-applying ({self.dimmer.backend_name})"
                        )
                        self._apply_automatic_brightness(target)
                else:
                    self._watchdog_drift_count = 0
        except Exception as e:
            logger.error(f"Dimmer watchdog error: {e}")
        self._start_dimmer_watchdog()

    def reset_dimmer(self) -> None:
        """Force reset dimmer to 100% (Success callback).

        This is a VISUAL-ONLY reset. The slider shows 100% but config values
        are NOT overwritten. This prevents browsing/gaming values from being
        lost when mode switches after a reset.
        """
        if not self._automatic_dimmer_allowed():
            return
        logger.info("Bot success confirmed. Resetting dimmer to 100% (visual only).")
        # Set flag to prevent _on_dimmer_mode_changed from saving this fake 100 value
        self._dimmer_reset_visual = True
        self.after(0, lambda: self._apply_automatic_brightness(100))

    def _set_arena_automation_enabled(self, enabled: bool) -> None:
        """Set the master gate for Arena ban/pick actions."""
        self._arena_automation_enabled = bool(enabled)
        watcher = getattr(self, "arena_watcher", None)
        if watcher is not None:
            watcher.set_automation_enabled(self._arena_automation_enabled)
        self._refresh_arena_validation()

    def start_bot(self) -> None:
        logger.info("Starting bot...")

        self._commit_empty_optional_picks()
        issues = self._refresh_arena_validation(force_errors=True)
        if issues:
            self._set_arena_automation_enabled(False)
            self._show_toast(
                "Không thể bắt đầu. Kiểm tra lại Cấu hình Arena.",
                Colors.STATUS_RED,
            )
            return

        # Guard: never run two bots at once (Stop does not kill the thread
        # instantly - it may still be winding down).
        if self.bot and self.bot.is_alive():
            messagebox.showwarning(
                "Tác vụ đang dừng",
                "Tác vụ trước vẫn đang dừng. Hãy chờ một chút rồi thử lại.",
            )
            return

        self._set_arena_automation_enabled(True)
        self._bot_generation += 1
        generation = self._bot_generation
        self._bot_stopping = False
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        self.bot = AntiFateBot(
            update_status_callback=lambda text, color, g=generation: self._on_bot_status(
                g, text, color
            ),
            on_stop_callback=lambda status, color, g=generation: self.on_bot_stop(
                status, color, g
            ),
            on_success_callback=lambda g=generation: self._on_bot_success(g),
            on_champ_select_callback=lambda g=generation: self._on_bot_champ_select(g),
        )
        self.bot.start()

    def stop_bot(self) -> None:
        logger.info("Bot Stopping...")
        self._bot_stopping = True
        self._set_arena_automation_enabled(False)
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="disabled")
        self.update_status("Đang dừng...", "orange")
        if self.bot:
            self.bot.stop()
        else:
            self._bot_stopping = False
            self.update_status(UIStatus.STOPPED, "gray")

    def on_closing(self) -> None:
        """Cleanup before closing"""
        logger.info("Closing application...")
        if self._beacon_pulse_id:
            self.after_cancel(self._beacon_pulse_id)
            self._beacon_pulse_id = None
        if self._arena_validation_after_id:
            self.after_cancel(self._arena_validation_after_id)
            self._arena_validation_after_id = None
        if self._dimmer_watchdog_id:
            self.after_cancel(self._dimmer_watchdog_id)
            self._dimmer_watchdog_id = None
        try:
            self._bot_stopping = True
            self._set_arena_automation_enabled(False)
            if self.bot:
                # Disable callback to avoid updating destroyed widgets
                self.bot.on_stop_callback = None
                self.bot.stop()
            self.arena_watcher.stop()
            self.notifier.close()

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

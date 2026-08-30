"""Status and Arena live-event rendering for the main window."""

from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

import customtkinter as ctk

from config import config_manager, normalize_ui_scale
from constants import AppConfig, Colors, UIStatus


class StatusUiMixin:
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
        self._post_to_ui(_render)
        if toast:
            self._post_to_ui(
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

        scale = normalize_ui_scale(config_manager.get("ui_scale"))
        wraplength = int(300 / scale)
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

        self._post_to_ui(_update)

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

        self._post_to_ui(_update_ui)

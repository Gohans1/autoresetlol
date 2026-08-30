"""Arena settings and suggestion UI mixin."""

from __future__ import annotations

import threading
from typing import Dict, List, Optional, Tuple

import customtkinter as ctk  # type: ignore

from arena_config import (
    NOT_SET_LABEL,
    NO_PICK_LABEL,
    OPTIONAL_PICK_FIELDS,
    ArenaConfigIssue,
    champion_id,
    validate_arena_config,
)
from config import config_manager, normalize_ui_scale
from constants import AppConfig, Colors
from gui_components import CardFrame
from logger import logger
from utils.lcu import lcu


ARENA_FIELD_LABELS = {
    "ban": "Tướng cần ban",
    "main": "Tướng chính",
    "b1": "Dự bị 1",
    "b2": "Dự bị 2",
    "b3": "Dự bị 3",
}


class ArenaUiMixin:
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
        self._arena_field_visual_state: Dict[str, Tuple[str, str, str]] = {}
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
        self._arena_fetch_lock = threading.Lock()
        self._arena_fetch_thread: Optional[threading.Thread] = None
        self._arena_fetch_pending = False
        self._arena_fetch_cancel = threading.Event()
        self._arena_roster_reload_after_id = None
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
        self._schedule_initial_arena_roster_reload()

    def _schedule_initial_arena_roster_reload(self) -> None:
        """Schedule the first roster fetch after Tk can process callbacks."""
        try:
            self._arena_roster_reload_after_id = self.after_idle(
                self._run_initial_arena_roster_reload
            )
        except Exception as error:
            self._arena_roster_loading = False
            logger.debug("Initial Arena roster reload scheduling failed: %s", error)

    def _run_initial_arena_roster_reload(self) -> None:
        self._arena_roster_reload_after_id = None
        self._reload_owned_champions()

    def _reload_owned_champions(self) -> None:
        """Fetch lại roster; connection và roster result được theo dõi riêng."""
        self._arena_fetch_gen += 1
        gen = self._arena_fetch_gen
        self._arena_roster_loading = True
        self._arena_roster_error = False
        try:
            self._refresh_arena_validation()
        except Exception as error:
            logger.debug("Arena validation refresh failed during roster reload: %s", error)
        with self._arena_fetch_lock:
            current = self._arena_fetch_thread
            if current is not None and current.is_alive():
                self._arena_fetch_pending = True
                return
            self._arena_fetch_cancel.clear()
            fetch_thread = threading.Thread(
                target=self._load_owned_champions, args=(gen,), daemon=True
            )
            self._arena_fetch_thread = fetch_thread
        try:
            fetch_thread.start()
        except Exception:
            with self._arena_fetch_lock:
                if self._arena_fetch_thread is fetch_thread:
                    self._arena_fetch_thread = None
            raise

    def _stop_arena_roster_fetch(self) -> None:
        """Cancel the roster fetch and wait briefly before teardown."""
        cancel = self.__dict__.get("_arena_fetch_cancel")
        lock = self.__dict__.get("_arena_fetch_lock")
        if cancel is None or lock is None:
            return
        cancel.set()
        with lock:
            self._arena_fetch_pending = False
            fetch_thread = self._arena_fetch_thread
        if fetch_thread is None or fetch_thread is threading.current_thread():
            return
        fetch_thread.join(timeout=1.0)
        with lock:
            if self._arena_fetch_thread is fetch_thread and not fetch_thread.is_alive():
                self._arena_fetch_thread = None

    def _load_owned_champions(self, gen: int) -> None:
        cancel = self._arena_fetch_cancel
        try:
            phase = None
            if not cancel.is_set():
                try:
                    phase = lcu.gameflow_phase()
                except Exception as error:
                    logger.debug(
                        "Arena phase lookup failed during roster reload: %s", error
                    )

            roster = None
            if not cancel.is_set():
                try:
                    roster = lcu.owned_champions_result()
                except Exception as error:
                    logger.debug("Arena roster lookup failed: %s", error)

            if not cancel.is_set():
                connected = phase is not None or roster is not None
                owned = roster or []
                roster_loaded = roster is not None
                try:
                    posted = self._post_to_ui(
                        self._apply_owned_champions,
                        owned,
                        gen,
                        connected,
                        roster_loaded,
                    )
                except Exception as error:
                    logger.debug("Arena roster UI callback skipped: %s", error)
                    posted = False
                if not posted:
                    with self._arena_fetch_lock:
                        if gen == self._arena_fetch_gen:
                            self._arena_roster_loading = False
        finally:
            with self._arena_fetch_lock:
                if self._arena_fetch_thread is threading.current_thread():
                    self._arena_fetch_thread = None
                rerun = self._arena_fetch_pending and not cancel.is_set()
                self._arena_fetch_pending = False
            if rerun:
                try:
                    self._post_to_ui(self._reload_owned_champions)
                except Exception as error:
                    logger.debug("Arena roster reload callback skipped: %s", error)

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

    def _save_arena_champion_names(self, save: bool = True) -> bool:
        """Persist champion names so the next app start can show labels offline."""
        data = {
            str(cid): name
            for cid, name in sorted(self._arena_cached_names.items())
            if cid > 0 and name
        }
        if data == config_manager.get("arena_champion_names"):
            return True
        if not config_manager.set("arena_champion_names", data, save=save):
            self._arena_save_dirty = True
            logger.error("Arena champion-name save failed; keeping pending value")
            return False
        self._arena_save_dirty = not save
        return True

    def _flush_pending_arena_save(self) -> bool:
        """Retry a failed Arena configuration save before teardown."""
        if not self.__dict__.get("_arena_save_dirty", False):
            return True
        if config_manager.save_config():
            self._arena_save_dirty = False
            return True
        logger.error("Arena config save failed; keeping pending value")
        return False

    def _remember_arena_champion(
        self, champion_id_value: object, name: object, save: bool = True
    ) -> None:
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
        self._save_arena_champion_names(save=save)

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
        except Exception as error:
            logger.error("Arena roster UI update failed: %s", error)

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
            self._post_to_ui(_update)
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

    def _apply_arena_field_visual(
        self, key: str, border: str, text_color: str, text: str
    ) -> None:
        state = (border, text_color, text)
        if self._arena_field_visual_state.get(key) == state:
            return
        try:
            self.arena_combos[key].configure(border_color=border)
            self.arena_field_status[key].configure(
                text=text,
                text_color=text_color,
            )
        except Exception:
            return
        self._arena_field_visual_state[key] = state

    def _set_arena_field_visual(
        self, key: str, issues: List[ArenaConfigIssue]
    ) -> None:
        field_issues = [issue for issue in issues if key in issue.fields]
        draft = self._arena_field_is_draft(key)
        cid = champion_id(self._arena_loaded_ids.get(key, 0))

        if not self._arena_feature_enabled_for_field(key):
            border = Colors.BORDER
            text_color = Colors.MUTED_FG
            text = "Tính năng này đang tắt."
            self._apply_arena_field_visual(key, border, text_color, text)
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

        self._apply_arena_field_visual(key, border, text_color, text)

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

            scale = normalize_ui_scale(config_manager.get("ui_scale"))
            wraplength = int(360 / scale)
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
        enabled = bool(self.auto_ban_var.get())
        previous = config_manager.get("auto_ban_enabled")
        if not config_manager.set("auto_ban_enabled", enabled):
            self.auto_ban_var.set(
                bool(previous) if previous is not None else not enabled
            )
            logger.error("Auto Ban save failed; keeping the previous state")
        self._refresh_arena_field_visibility()
        self._refresh_arena_validation()

    def _on_auto_pick_toggle(self) -> None:
        enabled = bool(self.auto_pick_var.get())
        previous = config_manager.get("auto_pick_enabled")
        if not config_manager.set("auto_pick_enabled", enabled):
            self.auto_pick_var.set(
                bool(previous) if previous is not None else not enabled
            )
            logger.error("Auto Pick save failed; keeping the previous state")
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
            updated = config_manager.set("arena_ban_champ", cid, save=False)
        else:
            order = {"main": 0, "b1": 1, "b2": 2, "b3": 3}
            chain = list(config_manager.get("arena_pick_chain") or [0, 0, 0, 0])
            while len(chain) < 4:
                chain.append(0)
            chain[order[key]] = cid
            updated = config_manager.set("arena_pick_chain", chain, save=False)
        if not updated:
            self._arena_save_dirty = True
            logger.error("Arena selection update failed; keeping pending value")
            return
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
                save=False,
            )
            recent = [cid] + [c for c in self._arena_recent.get(key, []) if c != cid]
            self._arena_recent[key] = recent[:5]
            config_manager.set("arena_recent", self._arena_recent, save=False)
        self._arena_save_dirty = True
        if config_manager.save_config():
            self._arena_save_dirty = False
        else:
            logger.error("Arena config save failed; keeping pending value")
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

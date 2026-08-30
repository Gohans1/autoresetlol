"""Champion suggestion behavior for the Arena controls."""

from __future__ import annotations

import tkinter as tk
from typing import List, Optional

from arena_config import NOT_SET_LABEL, NO_PICK_LABEL, OPTIONAL_PICK_FIELDS
from constants import AppConfig, Colors


class ArenaSuggestionsMixin:
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
        # Widget bindings fire before the Entry class binding, so the entry
        # still holds PRE-paste text here. Defer past it: the handler must
        # read the post-mutation text, or an empty optional field would
        # auto-commit 0 ("Không") on top of the incoming paste.
        self.after_idle(lambda: self._on_arena_combo_key(key))

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

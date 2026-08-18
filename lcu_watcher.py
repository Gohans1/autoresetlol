"""LCU watcher — chạy nền cả vòng đời app (poll 1s).

Làm 2 việc, đều đọc trạng thái thật từ LCU API:

1. **Dimmer tự bật/tắt đúng lúc** (nếu auto_dimmer_switch_enabled):
   - ChampSelect / InProgress → chế độ Gaming
   - Lobby / Matchmaking / EndOfGame → chế độ Browsing
   (thay cho kiểu cũ chỉ nhìn pixel champ select, không bao giờ quay về)

2. **Arena ban/pick tự động** (chỉ khi gameMode = ARENA + toggle bật):
   - Set ĐÚNG 1 LẦN khi màn chọn tướng mở, chỉ HOVER (PATCH championId),
     KHÔNG bao giờ complete/lock — hết giờ client tự khóa, user đổi được.
   - User đã tự chọn (action có championId hoặc đã complete) → tôn trọng.
   - Chuỗi chọn: main → dự bị 1..3, con đầu tiên sở hữu + chưa bị ban.
     Chờ bans được lộ ra mới chọn (Arena ban ẩn, lộ khi mọi người khóa).
   - Danh sách ban không lộ đúng hạn → không PATCH để tránh chọn nhầm tướng.
   - Hết sạch (main + dự bị đều bị ban) → đứng im + báo động (beep + status).
     KHÔNG bao giờ tự random.
   - Rời champ select → reset trạng thái, session sau set lại.
"""

import threading
import time
import winsound
from typing import Dict, Optional

from arena_config import validate_arena_config
from config import config_manager
from logger import logger
from utils.lcu import lcu

# Arena: thời gian chờ bans lộ tối đa trước khi fallback chọn theo chain
_BANS_REVEAL_TIMEOUT = 40
# LCU request timeout is 3s; allow one slow state propagation window without
# trusting the PATCH response by itself.
_ACTION_VERIFY_TIMEOUT = 2.0
_ACTION_VERIFY_INTERVAL = 0.1

_STATUS_ALERT = (
    "⚠️ PICK bị dừng: Tướng chính và toàn bộ tướng dự bị đã bị ban — "
    "hãy chọn tướng."
)
_STATUS_BANS_UNKNOWN = (
    "⚠️ PICK bị dừng: chưa đọc được danh sách tướng đã bị ban. "
    "Bot không tự PICK để tránh chọn nhầm tướng đã bị ban — hãy tự chọn tướng."
)


class LcuWatcher(threading.Thread):
    def __init__(
        self,
        update_status_callback=None,
        on_gaming_callback=None,
        on_browsing_callback=None,
        arena_event_callback=None,
        connection_callback=None,
    ):
        super().__init__(daemon=True)
        self.update_status_callback = update_status_callback
        self.on_gaming_callback = on_gaming_callback
        self.on_browsing_callback = on_browsing_callback
        self.arena_event_callback = arena_event_callback
        self.connection_callback = connection_callback
        self._last_connection_state: Optional[bool] = None
        self.running: bool = False
        # START BOT controls Arena ban/pick. Dimmer monitoring remains active.
        self.automation_enabled: bool = False
        # Dimmer state
        self._gaming_state: bool = False
        # Arena session state
        self._owned_cache: set = set()
        self._owned_names: Dict[int, str] = {}
        self._owned_cache_at: float = 0.0
        self._in_champ_select: bool = False
        self._champ_select_since: float = 0.0
        self._ban_handled: bool = False
        self._pick_handled: bool = False
        self._ban_fail_count: int = 0
        self._pick_fail_count: int = 0
        self._alerted: bool = False
        # Theo dõi tướng bot đã hover (phát hiện team lấy mất / user tự đổi)
        self._pick_picked_id: int = 0
        self._pick_attempted_ids: set[int] = set()
        # 1-slot đệm tránh spam log khi _handle_pick chạy lại mỗi giây
        self._pick_wait_logged: bool = False
        self._last_arena_event: tuple[str, str] | None = None
        self._arena_event_last_at: dict[str, float] = {}

    # ---- vòng đời ----

    def stop(self) -> None:
        self.running = False
        self.automation_enabled = False

    def set_automation_enabled(self, enabled: bool) -> None:
        """Enable or disable Arena ban/pick without stopping dimmer monitoring."""
        enabled = bool(enabled)
        if enabled == self.automation_enabled:
            return
        self.automation_enabled = enabled
        if not self.automation_enabled:
            self._reset_session_state()
            self._arena_event(
                "Automation: đã dừng — Arena watcher không thao tác",
                "gray",
                force=True,
            )

    def run(self) -> None:
        self.running = True
        while self.running:
            try:
                self._tick()
            except Exception as e:
                logger.error(f"LcuWatcher error: {e}")
            time.sleep(1)

    # ---- vòng lặp chính ----

    def _tick(self) -> None:
        phase = lcu.gameflow_phase()
        connected = phase is not None
        if connected != self._last_connection_state:
            self._last_connection_state = connected
            if self.connection_callback:
                try:
                    self.connection_callback(connected)
                except Exception as e:
                    logger.error(f"LCU connection callback failed: {e}")

        if phase is None:
            self._arena_event("LCU: chưa kết nối được client", "red")
        elif phase != "ChampSelect" and self._in_champ_select:
            self._arena_event(f"Arena: rời Champ Select → phase {phase}", "gray")

        # 1) Dimmer auto-switch theo trạng thái trận
        self._auto_dimmer(phase)

        # 2) Arena ban/pick
        if phase != "ChampSelect":
            self._reset_session_state()
            return

        mode = lcu.game_mode()
        if mode != "ARENA":
            self._arena_event(
                f"Champ Select: mode {mode or '(không xác định)'} — không phải Arena",
                "gray",
            )
            return  # chế độ khác: không đụng vào gì

        session = lcu.champ_select_session()
        if not session:
            self._arena_event("Arena: đang chờ champ-select session", "orange")
            return

        if not self.automation_enabled:
            self._reset_session_state()
            self._arena_event(
                "Arena: đã dừng — chưa bật tự động",
                "gray",
            )
            return

        # Do not act on a configuration that became invalid after START.
        # The UI reports the exact reason; the watcher fails closed here.
        config_issues = self._arena_config_issues()
        if config_issues:
            self._arena_event(
                "Arena: bị chặn — "
                + "; ".join(issue.message for issue in config_issues),
                "red",
            )
            return

        if not self._in_champ_select:
            self._in_champ_select = True
            self._champ_select_since = time.time()
            self._arena_event(
                "Arena: Champ Select mở — đang theo dõi ban/pick",
                "blue",
                force=True,
            )

        self._handle_ban(session)
        self._handle_pick(session)

    # ---- dimmer ----

    def _auto_dimmer(self, phase: Optional[str]) -> None:
        """Chuyển dimmer Gaming/Browsing theo phase (nếu toggle bật)."""
        if not config_manager.get("auto_dimmer_switch_enabled"):
            return
        if config_manager.get("dimmer_enabled") is False:
            return
        in_game = phase in ("ChampSelect", "InProgress")
        if in_game and not self._gaming_state:
            self._gaming_state = True
            if self.on_gaming_callback:
                try:
                    self.on_gaming_callback()
                except Exception as e:
                    logger.error(f"Dimmer gaming callback failed: {e}")
        elif not in_game and self._gaming_state:
            self._gaming_state = False
            if self.on_browsing_callback:
                try:
                    self.on_browsing_callback()
                except Exception as e:
                    logger.error(f"Dimmer browsing callback failed: {e}")

    # ---- arena helpers ----

    def _reset_session_state(self) -> None:
        if (
            self._in_champ_select
            or self._ban_handled
            or self._pick_handled
            or self._alerted
        ):
            self._in_champ_select = False
            self._champ_select_since = 0.0
            self._ban_handled = False
            self._pick_handled = False
            self._ban_fail_count = 0
            self._pick_fail_count = 0
            self._alerted = False
            self._pick_picked_id = 0
            self._pick_attempted_ids = set()
            self._pick_wait_logged = False

    @staticmethod
    def _action_is_in_progress(action: object) -> bool:
        """Return True only when LCU explicitly marks an action active."""
        return isinstance(action, dict) and action.get("isInProgress") is True

    @staticmethod
    def _my_actions(session: dict, action_type: str) -> list:
        """Action ban/pick CỦA MÌNH, đang in-progress (chưa complete)."""
        return [
            a
            for a in LcuWatcher._all_my_actions(session, action_type)
            if LcuWatcher._action_is_in_progress(a)
        ]

    @staticmethod
    def _all_my_actions(session: dict, action_type: str) -> list:
        """MỌI action ban/pick của mình CHƯA complete — kể cả chưa in-progress.

        Arena xử lý tuần tự: ban → lộ ban → pick. Trong phase ban, action
        pick TỒN TẠI nhưng chưa isInProgress — không được coi là "user đã
        khóa tay" khi pick phase chưa mở (bug cũ: auto-pick chết im lặng).
        """
        try:
            local = session["localPlayerCellId"]
        except (KeyError, TypeError):
            return []
        out = []
        for group in session.get("actions") or []:
            for a in group:
                if (
                    a.get("type") == action_type
                    and a.get("actorCellId") == local
                    and not a.get("completed")
                ):
                    out.append(a)
        return out

    @staticmethod
    def _has_my_completed_action(session: dict, action_type: str) -> bool:
        """Return True when the user already completed an action."""
        try:
            local = session["localPlayerCellId"]
        except (KeyError, TypeError):
            return False
        for group in session.get("actions") or []:
            for action in group:
                if (
                    action.get("type") == action_type
                    and action.get("actorCellId") == local
                    and action.get("completed")
                    and isinstance(action.get("championId"), int)
                    and action.get("championId", 0) > 0
                ):
                    return True
        return False

    @staticmethod
    def _pick_phase_actions(session: dict) -> list:
        """Return local pick actions after the local ban action group.

        Arena exposes a Pick Intent group before the Ban group. Flattening all
        pick actions loses that boundary and can select the intent action.
        """
        try:
            local = session["localPlayerCellId"]
        except (KeyError, TypeError):
            return []
        groups = session.get("actions") or []
        ban_group_indices = [
            index
            for index, group in enumerate(groups)
            if any(
                action.get("type") == "ban"
                and action.get("actorCellId") == local
                for action in group
            )
        ]
        if not ban_group_indices:
            return []
        last_ban_group = max(ban_group_indices)
        picks = []
        for group in groups[last_ban_group + 1 :]:
            for action in group:
                if (
                    action.get("type") == "pick"
                    and action.get("actorCellId") == local
                    and not action.get("completed")
                ):
                    picks.append(action)
        return picks

    @staticmethod
    def _real_pick_open(session: dict) -> bool:
        return any(
            LcuWatcher._action_is_in_progress(action)
            for action in LcuWatcher._pick_phase_actions(session)
        )

    @staticmethod
    def _revealed_banned_ids(session: dict) -> tuple[bool, set[int]]:
        """Return ban IDs after summaries or the real Pick phase is visible."""
        bans = session.get("bans") if isinstance(session, dict) else None
        if not isinstance(bans, dict):
            return False, set()
        my_bans = bans.get("myTeamBans")
        their_bans = bans.get("theirTeamBans")
        if not isinstance(my_bans, list) or not isinstance(their_bans, list):
            return False, set()

        revealed = {
            value
            for value in [*my_bans, *their_bans]
            if isinstance(value, int) and not isinstance(value, bool) and value > 0
        }
        if revealed:
            return True, revealed

        # Some client builds keep the summary empty but populate the ban
        # actions before opening the real Pick group. Use that only when a
        # post-ban local Pick action is explicitly active.
        ban_action_ids = {
            action.get("championId")
            for group in (session.get("actions") or [])
            for action in group
            if action.get("type") == "ban"
            and isinstance(action.get("championId"), int)
            and action.get("championId") > 0
        }
        if ban_action_ids and LcuWatcher._real_pick_open(session):
            return True, ban_action_ids
        return False, set()

    @staticmethod
    def _picked_by_others_ids(session: dict) -> set:
        """IDs tướng đang thuộc về NGƯỜI KHÁC (đã pick trên bảng).

        Arena: mỗi tướng chỉ một người dùng được — kể cả đồng đội lẫn đối
        thủ. Dùng để loại tướng bị "lấy mất" khỏi chuỗi main → dự bị.
        """
        picked: set[int] = set()
        if not isinstance(session, dict):
            return picked
        try:
            local = session["localPlayerCellId"]
        except (KeyError, TypeError):
            return picked
        for group in session.get("actions") or []:
            for action in group:
                if action.get("type") != "pick":
                    continue
                if action.get("actorCellId") == local:
                    continue  # action của mình/bot — không tính
                cid = action.get("championId")
                if isinstance(cid, int) and not isinstance(cid, bool) and cid > 0:
                    picked.add(cid)
        return picked

    @staticmethod
    def _chain_ids() -> list:
        """Chuỗi main → dự bị từ config (tối đa 4 — khớp GUI), bỏ số 0."""
        chain = [
            c
            for c in (config_manager.get("arena_pick_chain") or [])
            if isinstance(c, int) and c > 0
        ]
        return chain[:4]

    def _owned_ids(self) -> set:
        """Id tướng đã sở hữu (cache 10s — tick 1s không nên fetch lại)."""
        now = time.time()
        if self._owned_cache_at and now - self._owned_cache_at < 10:
            return self._owned_cache
        try:
            champions = lcu.owned_champions()
            ids = {c["id"] for c in champions if c.get("id", 0) > 0}
            names = {
                c["id"]: str(c["name"]).strip()
                for c in champions
                if c.get("id", 0) > 0 and str(c.get("name") or "").strip()
            }
        except Exception:
            ids = set()
            names = {}
        self._owned_cache = ids
        self._owned_names = names
        self._owned_cache_at = now
        return ids

    def _champ_name(self, cid: int) -> str:
        """Tên tướng theo client; fallback \"Tướng #id\" khi chưa biết tên."""
        name = self._owned_names.get(cid)
        if name:
            return name
        return f"Tướng #{cid}"

    @staticmethod
    def _live_action(action_type: str, action_id: int) -> tuple[bool, Optional[dict]]:
        """Re-read one action immediately before PATCH.

        Returns ``(False, None)`` when the client response is unknown. In that
        case callers must not write. This closes the user-hover race window.
        """
        try:
            live_session = lcu.champ_select_session()
        except Exception:
            return False, None
        if not isinstance(live_session, dict):
            return False, None
        try:
            local = live_session["localPlayerCellId"]
        except (KeyError, TypeError):
            return False, None
        for group in live_session.get("actions") or []:
            for action in group:
                if (
                    action.get("type") == action_type
                    and action.get("actorCellId") == local
                    and action.get("id") == action_id
                ):
                    return True, action
        return True, None

    def _set_action_champion_verified(
        self, action_type: str, action_id: int, champion_id: int
    ) -> bool:
        """PATCH one action and verify the LCU state changed to that champion."""
        if not lcu.set_action_champion(action_id, champion_id):
            self._arena_event(
                f"{action_type.capitalize()}: LCU từ chối PATCH — đang thử lại",
                "orange",
            )
            return False

        deadline = time.monotonic() + _ACTION_VERIFY_TIMEOUT
        last_reason = "chưa đọc được action"
        while time.monotonic() < deadline:
            known, live = self._live_action(action_type, action_id)
            if not known:
                last_reason = "không đọc được session live"
            elif live is None:
                last_reason = "action đã biến mất"
            else:
                observed = live.get("championId", 0)
                last_reason = f"client vẫn báo championId={observed}"
                if observed == champion_id:
                    return True
            time.sleep(_ACTION_VERIFY_INTERVAL)

        logger.warning(
            f"Arena {action_type} action {action_id}: PATCH accepted, "
            f"read-back failed ({last_reason})"
        )
        self._arena_event(
            f"{action_type.capitalize()}: PATCH đã nhận nhưng chưa xác minh — "
            "đang thử lại",
            "orange",
        )
        return False

    @staticmethod
    def _arena_config_issues() -> list:
        return validate_arena_config(
            auto_ban_enabled=bool(config_manager.get("auto_ban_enabled")),
            auto_pick_enabled=bool(config_manager.get("auto_pick_enabled")),
            ban_champion_id=config_manager.get("arena_ban_champ"),
            pick_chain=config_manager.get("arena_pick_chain"),
        )

    def _status(self, text: str, color: str = "blue") -> None:
        if self.update_status_callback:
            try:
                self.update_status_callback(text, color)
            except Exception:
                pass

    def _arena_event(
        self, text: str, color: str = "blue", force: bool = False
    ) -> None:
        """Publish one deduplicated Arena state to log and UI."""
        event = (text, color)
        now = time.monotonic()
        if not force:
            if event == self._last_arena_event:
                return
            if now - self._arena_event_last_at.get(text, 0.0) < 3.0:
                return
        self._last_arena_event = event
        self._arena_event_last_at[text] = now
        if color in ("red", "orange"):
            logger.warning(f"Arena live: {text}")
        else:
            logger.info(f"Arena live: {text}")
        if self.arena_event_callback:
            try:
                self.arena_event_callback(text, color)
            except Exception as e:
                logger.error(f"Arena event callback failed: {e}")

    def _alert(self, reason: str) -> None:
        logger.warning(reason)
        self._status(reason, "red")

        def _beep() -> None:
            for _ in range(3):
                try:
                    winsound.MessageBeep(winsound.MB_ICONHAND)
                except Exception as e:
                    logger.error(f"Alert beep failed: {e}")
                    return
                time.sleep(0.35)

        threading.Thread(target=_beep, daemon=True).start()

    # ---- ban ----

    def _handle_ban(self, session: dict) -> None:
        if not config_manager.get("auto_ban_enabled"):
            return
        if self._ban_handled:
            return
        target = config_manager.get("arena_ban_champ")
        if not isinstance(target, int) or target <= 0:
            self._arena_event("Ban: bị chặn — chưa chọn tướng cấm", "red")
            self._ban_handled = True  # chưa cấu hình → không làm gì
            return

        all_bans = self._all_my_actions(session, "ban")
        for action in all_bans:
            if action.get("championId", 0) > 0:
                # User đã tự chọn, hoặc PATCH đã được client giữ lại nhưng
                # read-after-write không bắt kịp. Không ghi đè.
                self._arena_event(
                    f"Ban: action đã có tướng {self._champ_name(action.get('championId', 0))} — không ghi đè",
                    "gray",
                )
                self._ban_handled = True
                return

        if self._ban_fail_count > 0 and self._real_pick_open(session):
            self._alert(
                "⚠️ Không xác minh được tướng cấm trước khi vào Pick — hãy tự chọn.",
            )
            self._ban_handled = True
            return

        if not all_bans:
            if self._has_my_completed_action(session, "ban"):
                self._arena_event("Ban: user đã khóa tướng — không ghi đè", "gray")
                self._ban_handled = True
            else:
                self._arena_event(
                    "BAN: client chưa tạo action — đang chờ phase ban", "orange"
                )
            return
        actions = [a for a in all_bans if self._action_is_in_progress(a)]
        if not actions:
            self._arena_event("Ban: action chưa mở — đang chờ phase ban", "orange")
            return  # ban phase chưa mở — chờ, không đánh dấu handled

        for a in actions:
            if a.get("championId", 0) > 0:
                # User đã tự chọn ban → tôn trọng, không ghi đè
                self._arena_event(
                    f"Bạn đã tự cấm: {self._champ_name(a.get('championId', 0))} — không ghi đè",
                    "gray",
                )
                self._ban_handled = True
                return

            known, live = self._live_action("ban", a["id"])
            if not known:
                self._arena_event("Ban: chưa đọc được action live — không PATCH", "orange")
                return
            if live is None or live.get("championId", 0) > 0:
                # Action đã biến mất hoặc user vừa tự chọn → tôn trọng.
                self._arena_event(
                    "Ban: action đã đổi hoặc user vừa chọn — không ghi đè",
                    "gray",
                )
                self._ban_handled = True
                return
            if not self._action_is_in_progress(live):
                self._arena_event("Ban: action chưa tới lượt — đang chờ", "orange")
                return

            owned = self._owned_ids()
            if owned and target not in owned:
                self._arena_event(
                    f"Không cấm được: {self._champ_name(target)} không còn trong trò chơi",
                    "red",
                )
                self._alert("⚠️ Tướng ban không còn trong client — hãy tự chọn.")
                self._ban_handled = True
                return

            if not self.automation_enabled:
                self._arena_event("Ban: automation đã dừng trước PATCH", "gray")
                return
            self._arena_event(
                f"Đang cấm: {self._champ_name(target)}",
                "blue",
            )
            if self._set_action_champion_verified("ban", a["id"], target):
                self._arena_event(
                    f"Đã cấm: {self._champ_name(target)}",
                    "green",
                )
                self._ban_handled = True
                self._ban_fail_count = 0
                return
            # PATCH fail — giữ action chưa handled; retry đến khi action
            # đóng hoặc chuyển sang Pick thật.
            self._ban_fail_count += 1
            self._arena_event(
                f"Cấm {self._champ_name(target)} chưa thành công — thử lại "
                f"(lần {self._ban_fail_count})",
                "orange",
            )
            return

    # ---- pick ----

    def _handle_pick(self, session: dict) -> None:
        if not config_manager.get("auto_pick_enabled"):
            return
        if self._pick_handled:
            # Đã hover xong (hoặc đã dừng vì lý do khác) — theo dõi xem
            # tướng bot chọn có bị team lấy mất hay không.
            if self._pick_picked_id > 0:
                self._pick_watch(session)
            return
        all_picks = self._pick_phase_actions(session)
        if not all_picks:
            if self._has_my_completed_action(session, "pick"):
                self._arena_event(
                    "Pick: user đã khóa tướng — không ghi đè",
                    "gray",
                )
                self._pick_handled = True
            else:
                # Arena can omit future pick actions while the ban phase is
                # active. Keep polling until the client creates the action.
                self._arena_event(
                    "Pick: client chưa tạo action — đang chờ phase pick",
                    "orange",
                )
            return
        actions = [a for a in all_picks if self._action_is_in_progress(a)]
        if not actions:
            self._arena_event("Pick: action chưa mở — đang chờ phase pick", "orange")
            return  # pick phase chưa mở (đang ban phase) — CHỜ, không handled
        action = actions[0]
        if (
            action.get("championId", 0) > 0
            and action.get("championId", 0) not in self._pick_attempted_ids
        ):
            # User đã tự hover tướng → tôn trọng, không ghi đè
            self._arena_event(
                f"Bạn đã tự chọn: {self._champ_name(action.get('championId', 0))} — không ghi đè",
                "gray",
            )
            self._pick_handled = True
            return

        bans_revealed, banned = self._revealed_banned_ids(session)
        picked_others = self._picked_by_others_ids(session)
        if not bans_revealed:
            if time.time() - self._champ_select_since < _BANS_REVEAL_TIMEOUT:
                # Pick Intent is not the real pick phase. Wait for the client
                # to reveal the ban summaries after the ban phase.
                self._arena_event(
                    "Pick Intent: đang chờ phase ban kết thúc", "orange"
                )
                return
            # Fail closed: an empty or missing ban summary is unknown data,
            # not proof that the configured main champion is available.
            self._arena_event(
                "Pick: chưa đọc được danh sách tướng bị cấm sau khi chờ — "
                "không tự chọn",
                "red",
            )
            if not self._alerted:
                self._alert(_STATUS_BANS_UNKNOWN)
                self._alerted = True
            self._pick_handled = True
            return

        names = ", ".join(self._champ_name(cid) for cid in sorted(banned))
        self._arena_event(f"Các tướng bị cấm: {names}", "gray")

        owned = self._owned_ids()
        unavailable = banned | picked_others | (self._pick_attempted_ids - {0})
        chain = self._chain_ids()
        available = [
            cid
            for cid in chain
            if cid not in unavailable and (not owned or cid in owned)
        ]

        if not available:
            self._arena_event(
                "Pick: bị chặn — không còn tướng hợp lệ trong chuỗi",
                "red",
            )
            if not self._alerted:
                self._alert(_STATUS_ALERT)
                self._alerted = True
            self._pick_handled = True
            return

        if not self._pick_wait_logged:
            self._pick_wait_logged = True
            chosen = available[0]
            if chain and chain[0] not in available and chain[0] in banned:
                self._arena_event(
                    f"{self._champ_name(chain[0])} bị cấm → chọn: {self._champ_name(chosen)}",
                    "orange",
                    force=True,
                )
            elif chain and chain[0] not in available and chain[0] in picked_others:
                self._arena_event(
                    f"{self._champ_name(chain[0])} bị lấy → chọn: {self._champ_name(chosen)}",
                    "orange",
                    force=True,
                )
        known, live = self._live_action("pick", action["id"])
        if not known:
            self._arena_event("Pick: chưa đọc được action live — không PATCH", "orange")
            return
        live_hover = live.get("championId", 0) if live else 0
        if live is None or (
            live_hover > 0 and live_hover not in self._pick_attempted_ids
        ):
            # Action đã biến mất hoặc user vừa tự chọn → tôn trọng.
            self._arena_event(
                "Pick: action đã đổi hoặc user vừa chọn — không ghi đè",
                "gray",
            )
            self._pick_handled = True
            return
        if not self._action_is_in_progress(live):
            self._arena_event("Pick: action chưa tới lượt — đang chờ", "orange")
            return

        if not self.automation_enabled:
            self._arena_event("Pick: automation đã dừng trước PATCH", "gray")
            return

        self._arena_event(
            f"Đang chọn: {self._champ_name(available[0])}",
            "blue",
        )
        if self._set_action_champion_verified("pick", action["id"], available[0]):
            self._pick_picked_id = available[0]
            self._pick_wait_logged = False
            self._arena_event(
                f"Đã chọn: {self._champ_name(available[0])}",
                "green",
            )
            self._pick_handled = True
            self._pick_fail_count = 0
            return

        # PATCH fail — thử lại; sau 5 lần liên tiếp thì báo + dừng
        self._pick_fail_count += 1
        self._arena_event(
            f"Chọn {self._champ_name(available[0])} chưa thành công — thử lại "
            f"({self._pick_fail_count}/5)",
            "orange",
        )
        if self._pick_fail_count >= 5:
            self._alert("⚠️ Không đặt được tướng tự động — hãy chọn.")
            self._pick_handled = True
    # ---- theo dõi tướng đã hover ----

    @staticmethod
    def _pick_holders(session: dict, cid: int) -> list:
        """Actor khác đang giữ tướng ``cid`` trên bảng (mình loại trừ)."""
        holders: list = []
        if not isinstance(session, dict) or cid <= 0:
            return holders
        try:
            local = session["localPlayerCellId"]
        except (KeyError, TypeError):
            return holders
        for group in session.get("actions") or []:
            for action in group:
                if action.get("type") != "pick":
                    continue
                if action.get("actorCellId") == local:
                    continue
                if action.get("championId") == cid:
                    holders.append(action.get("actorCellId"))
        return holders

    def _pick_lost(self, session: dict) -> None:
        """Tướng bot đang hover bị người khác lấy → nhảy tướng kế tiếp."""
        lost_id = self._pick_picked_id
        self._pick_picked_id = 0
        self._pick_handled = False
        if lost_id > 0:
            self._pick_attempted_ids.add(lost_id)
        self._pick_wait_logged = True
        self._arena_event(
            f"{self._champ_name(lost_id)} bị lấy → chuyển tướng khác",
            "orange",
            force=True,
        )

    def _pick_watch(self, session: dict) -> None:
        """Mỗi giây kiểm tra tướng bot đã hover còn là của mình không."""
        mine = [
            action
            for action in self._pick_phase_actions(session)
            if self._action_is_in_progress(action)
        ]
        if not mine:
            # Action biến mất: chờ đến khi client tạo lại, không tự ý làm gì.
            if self._pick_holders(session, self._pick_picked_id):
                self._pick_lost(session)
            return
        current = mine[0].get("championId", 0)
        if current == self._pick_picked_id:
            self._pick_wait_logged = False
            return  # vẫn đang giữ đúng tướng — ổn
        if self._pick_holders(session, self._pick_picked_id):
            self._pick_lost(session)
            return
        # Tướng cũ không còn ai giữ và action của mình đã đổi
        # → không phải team lấy — là BẠN TỰ đổi. Tôn trọng, dừng hẳn.
        self._pick_picked_id = 0
        self._pick_handled = True
        self._arena_event(
            f"Bạn đã tự chọn: {self._champ_name(current)} — bot dừng",
            "gray",
            force=True,
        )

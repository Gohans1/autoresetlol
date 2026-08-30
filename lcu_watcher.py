"""LCU watcher — chạy nền cả vòng đời app (poll 1s).

Làm 2 việc, đều đọc trạng thái thật từ LCU API:

1. **Dimmer tự bật/tắt đúng lúc** (nếu auto_dimmer_switch_enabled):
   - ChampSelect / InProgress → chế độ Gaming
   - Lobby / Matchmaking / EndOfGame → chế độ Browsing
   (thay cho kiểu cũ chỉ nhìn pixel champ select, không bao giờ quay về)

2. **Arena ban/pick tự động** (chỉ khi gameMode = ARENA + toggle bật):
   - PATCH đúng action Ban/Pick đang active, đọc lại đúng action đó và chỉ
     xác nhận khi client giữ đúng tướng; nếu state cập nhật chậm thì retry
     theo phase. Chỉ HOVER, KHÔNG bao giờ complete/lock — user đổi được.
   - User đã tự chọn (action có championId hoặc đã complete) → tôn trọng.
   - Chuỗi chọn: main → dự bị 1..3, con đầu tiên sở hữu + chưa bị ban.
     Chờ bans được lộ ra mới chọn (Arena ban ẩn, lộ khi mọi người khóa).
   - Danh sách ban không lộ đúng hạn → không PATCH để tránh chọn nhầm tướng.
   - Hết sạch (main + dự bị đều bị ban) → đứng im + báo động (beep + status).
     KHÔNG bao giờ tự random.
   - Rời champ select → reset trạng thái, session sau set lại.
"""

from dataclasses import dataclass, field
import threading
import time
import winsound
from typing import Callable, Dict, Optional

from arena_config import champion_id, validate_arena_config
from config import config_manager
from constants import DISCORD_EVENT_BAN, DISCORD_EVENT_IN_GAME, DISCORD_EVENT_PICK
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


@dataclass
class ArenaSessionState:
    in_champ_select: bool = False
    champ_select_since: float = 0.0
    ban_handled: bool = False
    pick_handled: bool = False
    ban_fail_count: int = 0
    ban_pending_action: Optional[tuple[int, int]] = None
    pick_fail_count: int = 0
    pick_pending_action: Optional[tuple[int, int]] = None
    alerted: bool = False
    pick_picked_id: int = 0
    pick_attempted_ids: set[int] = field(default_factory=set)
    pick_wait_logged: bool = False

    def reset(self) -> None:
        self.in_champ_select = False
        self.champ_select_since = 0.0
        self.ban_handled = False
        self.pick_handled = False
        self.ban_fail_count = 0
        self.ban_pending_action = None
        self.pick_fail_count = 0
        self.pick_pending_action = None
        self.alerted = False
        self.pick_picked_id = 0
        self.pick_attempted_ids.clear()
        self.pick_wait_logged = False


class LcuWatcher(threading.Thread):
    def __init__(
        self,
        update_status_callback=None,
        on_gaming_callback=None,
        on_browsing_callback=None,
        arena_event_callback=None,
        connection_callback=None,
        notification_callback=None,
    ):
        super().__init__(daemon=True)
        self.update_status_callback = update_status_callback
        self.on_gaming_callback = on_gaming_callback
        self.on_browsing_callback = on_browsing_callback
        self.arena_event_callback = arena_event_callback
        self.connection_callback = connection_callback
        self.notification_callback = notification_callback
        self._last_connection_state: Optional[bool] = None
        self._stop_event = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self.running: bool = False
        # START BOT controls Arena ban/pick. Dimmer monitoring remains active.
        self.automation_enabled: bool = False
        self._automation_lock = threading.RLock()
        self._automation_cancelled = threading.Event()
        self._automation_generation: int = 0
        # Dimmer state
        self._gaming_state: bool = False
        # Arena session state
        self._owned_cache: Optional[set[int]] = None
        self._owned_names: Dict[int, str] = {}
        self._owned_cache_at: float = 0.0
        self._arena_state = ArenaSessionState()
        self._arena_session_generation: int = 0
        # Theo dõi tướng bot đã hover (phát hiện team lấy mất / user tự đổi)
        self._last_arena_event: tuple[str, str] | None = None
        self._arena_event_last_at: dict[str, float] = {}

    # ---- vòng đời ----

    def stop(self) -> None:
        with self._lifecycle_lock:
            with self._automation_lock:
                self._stop_event.set()
                self._automation_cancelled.set()
                self.running = False
                self.automation_enabled = False
                self._automation_generation += 1
                self._arena_state.reset()
        if threading.current_thread() is not self and self.is_alive():
            self.join(timeout=1)

    def set_automation_enabled(self, enabled: bool) -> None:
        """Enable or disable Arena ban/pick without stopping dimmer monitoring."""
        enabled = bool(enabled)
        with self._automation_lock:
            if enabled:
                self._automation_cancelled.clear()
            else:
                self._automation_cancelled.set()
            if enabled == self.automation_enabled:
                return
            self.automation_enabled = enabled
            self._automation_generation += 1
        if not enabled:
            with self._automation_lock:
                self._arena_state.reset()
            self._arena_event(
                "Automation: đã dừng — Arena watcher không thao tác",
                "gray",
                force=True,
            )

    def _automation_snapshot(self) -> Optional[int]:
        """Return the current action generation when Arena writes are allowed."""
        with self._automation_lock:
            return (
                self._automation_generation
                if self._automation_current_locked(self._automation_generation)
                else None
            )

    def _automation_current_locked(self, generation: int) -> bool:
        return (
            not self._stop_event.is_set()
            and not self._automation_cancelled.is_set()
            and self.running
            and self.automation_enabled
            and self._automation_generation == generation
        )

    def _automation_current(self, generation: int) -> bool:
        """Check that a long-running Arena action still owns its generation."""
        with self._automation_lock:
            return self._automation_current_locked(generation)

    def _automation_state_update(
        self, generation: int, update: Callable[[], None]
    ) -> bool:
        """Apply a state mutation only while its automation lease is current."""
        with self._automation_lock:
            if not self._automation_current_locked(generation):
                return False
            update()
            return True

    def _automation_state_event(
        self,
        generation: int,
        text: str,
        color: str,
        update: Callable[[], None],
        force: bool = False,
    ) -> bool:
        """Publish an event and mutate state under one automation lease."""
        with self._automation_lock:
            if not self._automation_current_locked(generation):
                return False
            self._arena_event(text, color, force=force)
            if not self._automation_current_locked(generation):
                return False
            update()
            return True

    def _automation_write(
        self, generation: int, write: Callable[[], bool]
    ) -> Optional[bool]:
        """Serialize cancellation with one LCU write and drop stale results."""
        with self._automation_lock:
            if not self._automation_current_locked(generation):
                return None
            result = write()
            if not self._automation_current_locked(generation):
                return None
            return result

    def _commit_verified_action(
        self,
        generation: int,
        action_type: str,
        action_id: int,
        target: int,
        after_retry: bool = False,
    ) -> bool:
        """Commit a verified action and its notification atomically."""
        target = champion_id(target)
        known, live, live_session = self._live_action_snapshot(action_type, action_id)
        if not known or live is None:
            return False
        if self._action_champion_id(live) != target:
            return False
        if not self._action_is_usable(live):
            return False
        if (
            action_type == "pick"
            and live_session is not None
            and self._pick_holders(live_session, target)
        ):
            return False
        with self._automation_lock:
            if not self._automation_current_locked(generation):
                return False
            name = self._champ_name(target)
            if action_type == "ban":
                self._arena_state.ban_handled = True
                self._arena_state.ban_fail_count = 0
                self._arena_state.ban_pending_action = None
                text = (
                    f"Đã cấm: {name} — xác minh sau retry"
                    if after_retry
                    else f"Đã cấm: {name}"
                )
                event = DISCORD_EVENT_BAN
                message = f"BAN đã xác minh: {name}"
            else:
                self._arena_state.pick_picked_id = target
                self._arena_state.pick_pending_action = None
                self._arena_state.pick_wait_logged = False
                self._arena_state.pick_handled = True
                self._arena_state.pick_fail_count = 0
                text = f"Đã chọn: {name}"
                event = DISCORD_EVENT_PICK
                message = f"PICK đã xác minh: {name}"
            self._arena_event(text, "green")
            if not self._automation_current_locked(generation):
                return False
            self._notify_external(
                event,
                message,
                self._arena_notification_key(
                    "ban_verified" if action_type == "ban" else "pick_verified",
                    action_id,
                    target,
                ),
            )
            return self._automation_current_locked(generation)

    def _commit_pending_user_ban(self, generation: int, champion: int) -> bool:
        """Commit a user-owned Ban action without external notification."""
        with self._automation_lock:
            if not self._automation_current_locked(generation):
                return False
            self._arena_event(
                f"Bạn đã tự cấm: {self._champ_name(champion)} — không ghi đè",
                "gray",
            )
            if not self._automation_current_locked(generation):
                return False
            self._arena_state.ban_pending_action = None
            self._arena_state.ban_fail_count = 0
            self._arena_state.ban_handled = True
            return True

    def _record_action_retry(
        self, generation: int, action_type: str, target: int
    ) -> bool:
        """Record a failed action only while its lease is still current."""
        with self._automation_lock:
            if not self._automation_current_locked(generation):
                return False
            if action_type == "ban":
                self._arena_state.ban_fail_count += 1
                count = self._arena_state.ban_fail_count
                text = (
                    f"Cấm {self._champ_name(target)} chưa thành công — thử lại "
                    f"(lần {count})"
                )
            else:
                self._arena_state.pick_fail_count += 1
                count = self._arena_state.pick_fail_count
                text = (
                    f"Chọn {self._champ_name(target)} chưa thành công — thử lại "
                    f"({count}/5)"
                )
            self._arena_event(text, "orange")
            if not self._automation_current_locked(generation):
                return False
            if action_type == "pick" and count >= 5:
                self._arena_state.pick_pending_action = None
                self._alert("⚠️ Không đặt được tướng tự động — hãy chọn.")
                if not self._automation_current_locked(generation):
                    return False
                self._arena_state.pick_handled = True
            return True

    def _prepare_pending_pick(self, session: dict, generation: int) -> bool:
        """Resolve a delayed Pick update before checking for user input."""
        pending = self._arena_state.pick_pending_action
        if pending is None:
            return False
        action_id, target = pending
        target = champion_id(target)
        known, live, live_session = self._live_action_snapshot("pick", action_id)
        if not known:
            return False
        if live is None:
            current_action = self._find_my_action(session, "pick", action_id)
            other_action = any(
                other_id is not None and other_id != action_id
                for action in self._pick_phase_actions(session)
                if (other_id := LcuWatcher._action_id(action)) is not None
            )
            completed_user_pick = (
                current_action is None
                and self._has_my_completed_post_ban_pick(session)
            )
            if other_action or completed_user_pick:
                self._automation_state_update(
                    generation,
                    lambda: setattr(self._arena_state, "pick_pending_action", None),
                )
            return False

        observed = self._action_champion_id(live)
        if observed == target and self._action_is_usable(live):
            if live_session is not None and self._pick_holders(live_session, target):
                self._pick_lost(session, generation, target)
                return True
            self._commit_verified_action(
                generation,
                "pick",
                action_id,
                target,
                after_retry=True,
            )
            return True
        if observed > 0 and observed != target:
            def mark_user_pick() -> None:
                self._arena_state.pick_pending_action = None
                self._arena_state.pick_handled = True

            self._automation_state_event(
                generation,
                f"Bạn đã tự chọn: {self._champ_name(observed)} — không ghi đè",
                "gray",
                mark_user_pick,
            )
            return True
        return False

    def run(self) -> None:
        with self._lifecycle_lock:
            with self._automation_lock:
                if self._stop_event.is_set():
                    self.running = False
                    return
                self.running = True
        try:
            while self.running and not self._stop_event.is_set():
                try:
                    self._tick()
                except Exception as e:
                    logger.error(f"LcuWatcher error: {e}")
                if self._stop_event.wait(1):
                    break
        finally:
            with self._lifecycle_lock:
                with self._automation_lock:
                    self.running = False

    # ---- vòng lặp chính ----

    def _tick(self) -> None:
        if self._stop_event.is_set() or not self.running:
            return
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
        elif phase != "ChampSelect" and self._arena_state.in_champ_select:
            if phase == "GameStart":
                self._arena_event("Arena: đang vào trận → phase GameStart", "gray")
            else:
                self._arena_event(f"Arena: rời Champ Select → phase {phase}", "gray")
            if phase == "InProgress":
                self._notify_external(
                    DISCORD_EVENT_IN_GAME,
                    "Đã vào trận Arena",
                    self._arena_notification_key("in_progress"),
                )

        # 1) Dimmer auto-switch theo trạng thái trận
        self._auto_dimmer(phase)

        # 2) Arena ban/pick
        if phase != "ChampSelect":
            if phase == "GameStart" and self._arena_state.in_champ_select:
                return
            self._reset_session_state()
            return

        mode = lcu.game_mode()
        if mode != "ARENA":
            self._arena_event(
                f"Champ Select: mode {mode or '(không xác định)'} — không phải Arena",
                "gray",
            )
            return  # chế độ khác: không đụng vào gì

        if not self.automation_enabled:
            self._reset_session_state()
            self._arena_event(
                "Arena: đã dừng — chưa bật tự động",
                "gray",
            )
            return

        generation = self._automation_snapshot()
        if generation is None:
            return

        session = lcu.champ_select_session()
        if not session:
            self._arena_event("Arena: đang chờ champ-select session", "orange")
            return
        if not self._automation_current(generation):
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

        if not self._automation_current(generation):
            return
        with self._automation_lock:
            if not self._automation_current_locked(generation):
                return
            if not self._arena_state.in_champ_select:
                self._arena_state.in_champ_select = True
                self._arena_state.champ_select_since = time.time()
                self._arena_session_generation += 1
                self._arena_event(
                    "Arena: Champ Select mở — đang theo dõi ban/pick",
                    "blue",
                    force=True,
                )
                if not self._automation_current_locked(generation):
                    return

        self._handle_ban(session, generation)
        self._handle_pick(session, generation)

    # ---- dimmer ----

    def _auto_dimmer(self, phase: Optional[str]) -> None:
        """Chuyển dimmer Gaming/Browsing theo phase (nếu toggle bật)."""
        if self._stop_event.is_set() or not self.running:
            return
        if config_manager.get("auto_dimmer_switch_enabled") is not True:
            self._gaming_state = False
            return
        if config_manager.get("dimmer_enabled") is not True:
            self._gaming_state = False
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
        with self._automation_lock:
            self._arena_state.reset()

    @staticmethod
    def _action_is_in_progress(action: object) -> bool:
        """Return True only when LCU explicitly marks an action active."""
        return isinstance(action, dict) and action.get("isInProgress") is True

    @staticmethod
    def _action_groups(session: object) -> list[list[dict]]:
        """Return only well-formed action groups and action objects."""
        if not isinstance(session, dict):
            return []
        groups = session.get("actions")
        if not isinstance(groups, list):
            return []
        return [
            [action for action in group if isinstance(action, dict)]
            for group in groups
            if isinstance(group, list)
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
        for group in LcuWatcher._action_groups(session):
            for a in group:
                if (
                    a.get("type") == action_type
                    and a.get("actorCellId") == local
                    and LcuWatcher._action_completed(a) is False
                ):
                    out.append(a)
        return out

    @staticmethod
    def _action_champion_id(action: object) -> int:
        """Return one action's canonical champion ID."""
        if not isinstance(action, dict):
            return 0
        return champion_id(action.get("championId", 0))

    @staticmethod
    def _action_id(action: object) -> Optional[int]:
        """Return one action's validated positive integer ID."""
        if not isinstance(action, dict):
            return None
        value = action.get("id")
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return None
        return value

    @staticmethod
    def _action_completed(action: object) -> Optional[bool]:
        """Return completion only for an exact boolean LCU value."""
        if not isinstance(action, dict):
            return None
        value = action.get("completed")
        if value is True:
            return True
        if value is False:
            return False
        return None

    @staticmethod
    def _action_is_pending(action: object) -> bool:
        """Return True only for an exact uncompleted active action."""
        return (
            LcuWatcher._action_completed(action) is False
            and LcuWatcher._action_is_in_progress(action)
        )

    @staticmethod
    def _action_is_usable(action: object) -> bool:
        """Return True only for an exact completed or pending action."""
        return (
            LcuWatcher._action_completed(action) is True
            or LcuWatcher._action_is_pending(action)
        )

    @staticmethod
    def _find_my_action(
        session: dict, action_type: str, action_id: int
    ) -> Optional[dict]:
        """Find one local action, including completed actions."""
        try:
            local = session["localPlayerCellId"]
        except (KeyError, TypeError):
            return None
        for group in LcuWatcher._action_groups(session):
            for action in group:
                if (
                    action.get("type") == action_type
                    and action.get("actorCellId") == local
                    and LcuWatcher._action_id(action) == action_id
                ):
                    return action
        return None

    @staticmethod
    def _has_my_completed_action(session: dict, action_type: str) -> bool:
        """Return True when the user already completed an action."""
        try:
            local = session["localPlayerCellId"]
        except (KeyError, TypeError):
            return False
        for group in LcuWatcher._action_groups(session):
            for action in group:
                if (
                    action.get("type") == action_type
                    and action.get("actorCellId") == local
                    and LcuWatcher._action_completed(action) is True
                    and LcuWatcher._action_champion_id(action) > 0
                ):
                    return True
        return False

    @staticmethod
    def _post_ban_groups(session: dict) -> list:
        """Action groups after the last local Ban group (real Pick zone)."""
        try:
            local = session["localPlayerCellId"]
        except (KeyError, TypeError):
            return []
        groups = LcuWatcher._action_groups(session)
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
        return groups[max(ban_group_indices) + 1 :]

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
        picks = []
        for group in LcuWatcher._post_ban_groups(session):
            for action in group:
                if (
                    action.get("type") == "pick"
                    and action.get("actorCellId") == local
                    and LcuWatcher._action_completed(action) is False
                ):
                    picks.append(action)
        return picks

    @staticmethod
    def _has_my_completed_post_ban_pick(session: dict) -> bool:
        """Return True only for a completed local Pick AFTER the Ban group.

        The pre-ban Pick Intent group is not the real pick: a completed intent
        must not stop auto-pick once the real Pick phase opens.
        """
        try:
            local = session["localPlayerCellId"]
        except (KeyError, TypeError):
            return False
        for group in LcuWatcher._post_ban_groups(session):
            for action in group:
                if (
                    action.get("type") == "pick"
                    and action.get("actorCellId") == local
                    and LcuWatcher._action_completed(action) is True
                    and LcuWatcher._action_champion_id(action) > 0
                ):
                    return True
        return False

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

        my_revealed = {
            champion_id(value)
            for value in my_bans
            if champion_id(value) > 0
        }
        their_revealed = {
            champion_id(value)
            for value in their_bans
            if champion_id(value) > 0
        }
        # Một phía có dữ liệu vẫn là trạng thái reveal dở — phải đủ hai phía.
        if my_revealed and their_revealed:
            return True, my_revealed | their_revealed
        if my_bans or their_bans:
            return False, set()

        # Some client builds keep the summary empty but populate the ban
        # actions before opening the real Pick group. Use that only when a
        # post-ban local Pick action is explicitly active.
        ban_action_ids = {
            LcuWatcher._action_champion_id(action)
            for group in LcuWatcher._action_groups(session)
            for action in group
            if action.get("type") == "ban"
            and LcuWatcher._action_champion_id(action) > 0
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
        for group in LcuWatcher._action_groups(session):
            for action in group:
                if action.get("type") != "pick":
                    continue
                if action.get("actorCellId") == local:
                    continue  # action của mình/bot — không tính
                cid = LcuWatcher._action_champion_id(action)
                if cid > 0:
                    picked.add(cid)
        return picked

    @staticmethod
    def _chain_ids() -> list:
        """Chuỗi main → dự bị từ config (tối đa 4 — khớp GUI), bỏ số 0."""
        chain = [
            champion_id(c)
            for c in (config_manager.get("arena_pick_chain") or [])
            if champion_id(c) > 0
        ]
        return chain[:4]

    def _owned_ids(self) -> Optional[set[int]]:
        """Id tướng đã sở hữu (cache 10s — tick 1s không nên fetch lại)."""
        now = time.time()
        if self._owned_cache_at and now - self._owned_cache_at < 10:
            return self._owned_cache
        try:
            champions = lcu.owned_champions()
            if champions is None:
                self._owned_cache = None
                self._owned_names = {}
                self._owned_cache_at = now
                return None
            ids = set()
            names = {}
            for champion in champions:
                if not isinstance(champion, dict):
                    continue
                cid = champion_id(champion.get("id"))
                name = str(champion.get("name") or "").strip()
                if cid > 0:
                    ids.add(cid)
                    if name:
                        names[cid] = name
        except Exception:
            self._owned_cache = None
            self._owned_names = {}
            self._owned_cache_at = now
            return None
        self._owned_cache = ids
        self._owned_names = names
        self._owned_cache_at = now
        return ids

    def _champ_name(self, cid: int) -> str:
        """Tên tướng theo client; fallback \"Tướng #id\" khi chưa biết tên."""
        cid = champion_id(cid)
        name = self._owned_names.get(cid)
        if name:
            return name
        return f"Tướng #{cid}"

    @staticmethod
    def _live_session() -> tuple[bool, Optional[dict]]:
        """Read one complete live session or report unknown data."""
        try:
            live_session = lcu.champ_select_session()
        except Exception:
            return False, None
        if not isinstance(live_session, dict):
            return False, None
        return True, live_session

    @staticmethod
    def _live_action_snapshot(
        action_type: str, action_id: int
    ) -> tuple[bool, Optional[dict], Optional[dict]]:
        """Read an exact local action and keep its session for related checks."""
        known, live_session = LcuWatcher._live_session()
        if not known or live_session is None:
            return known, None, None
        action = LcuWatcher._find_my_action(live_session, action_type, action_id)
        return True, action, live_session

    @staticmethod
    def _live_action(action_type: str, action_id: int) -> tuple[bool, Optional[dict]]:
        """Re-read one exact local action immediately before a state decision."""
        known, action, _live_session = LcuWatcher._live_action_snapshot(
            action_type, action_id
        )
        return known, action

    def _set_action_champion_verified(
        self,
        action_type: str,
        action_id: int,
        champion_id_value: int,
        generation: int,
    ) -> Optional[bool]:
        """PATCH one action and verify the active action holds that champion."""
        target = champion_id(champion_id_value)
        if target <= 0:
            return False
        with self._automation_lock:
            if not self._automation_current_locked(generation):
                return None
        known, live = self._live_action(action_type, action_id)
        if not known or live is None:
            return None
        observed = self._action_champion_id(live)
        if not self._action_is_pending(live):
            return None
        if observed > 0:
            if action_type != "pick":
                return None
            known, live_session = self._live_session()
            if not known or live_session is None:
                return None
            if (
                observed not in self._arena_state.pick_attempted_ids
                or not self._pick_holders(live_session, observed)
            ):
                return None
        if action_type == "pick":
            known, live_session = self._live_session()
            if not known or live_session is None:
                return None
            if self._pick_holders(live_session, target):
                return None
        patched = self._automation_write(
            generation,
            lambda: lcu.set_action_champion(action_id, target),
        )
        if patched is None:
            return None
        if not patched:
            if not self._automation_current(generation):
                return None
            self._arena_event(
                f"{action_type.capitalize()}: LCU từ chối PATCH — đang thử lại",
                "orange",
            )
            return False

        # Keep provenance when the client updates the action after this method
        # returns. A later completed action can be confirmed only when it is
        # same action and still has the same canonical target.
        pending_field = (
            "ban_pending_action" if action_type == "ban" else "pick_pending_action"
        )
        if not self._automation_state_update(
            generation,
            lambda: setattr(
                self._arena_state, pending_field, (action_id, target)
            ),
        ):
            return None

        deadline = time.monotonic() + _ACTION_VERIFY_TIMEOUT
        last_reason = "chưa đọc được action"
        while time.monotonic() < deadline:
            if not self._automation_current(generation):
                return None
            known, live = self._live_action(action_type, action_id)
            if not known:
                last_reason = "không đọc được session live"
            elif live is None:
                last_reason = "action đã biến mất"
            else:
                raw_observed = live.get("championId", 0)
                observed = self._action_champion_id(live)
                last_reason = (
                    f"client báo championId={raw_observed} "
                    f"(ID chuẩn={observed})"
                )
                active = self._action_is_pending(live)
                if observed == target and active:
                    return True if self._automation_current(generation) else None
                if observed == target:
                    last_reason += "; action chưa còn active"
            time.sleep(_ACTION_VERIFY_INTERVAL)

        if not self._automation_current(generation):
            return None
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
            except Exception as error:
                logger.error(f"Status callback failed: {error}")

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

    def _notify_external(
        self,
        event: str,
        message: str,
        dedupe_key: Optional[str] = None,
    ) -> None:
        """Publish a verified action for external notification transports."""
        if self._stop_event.is_set() or not self.notification_callback:
            return
        try:
            self.notification_callback(event, message, dedupe_key)
        except Exception as e:
            logger.error(f"External notification callback failed: {e}")

    def _arena_notification_key(self, event: str, *parts: object) -> str:
        values = [
            "arena",
            str(self._arena_session_generation),
            event,
            *(str(part) for part in parts),
        ]
        return ":".join(values)

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

    def _confirm_pending_ban(
        self, session: dict, generation: Optional[int] = None
    ) -> bool:
        """Confirm only the exact Ban action that this watcher patched."""
        if generation is None:
            generation = self._automation_snapshot()
        if generation is None:
            return False
        pending = self._arena_state.ban_pending_action
        if pending is None:
            return False
        action_id, target = pending
        target = champion_id(target)
        known, action = self._live_action("ban", action_id)
        if not known or action is None:
            return False
        if action.get("type") != "ban" or LcuWatcher._action_id(action) != action_id:
            return False
        observed = self._action_champion_id(action)
        action_active = self._action_is_usable(action)
        if not action_active:
            return False

        if observed == target:
            return self._commit_verified_action(
                generation, "ban", action_id, target, after_retry=True
            )

        if observed > 0:
            return self._commit_pending_user_ban(generation, observed)
        return False

    def _handle_ban(
        self, session: dict, generation: Optional[int] = None
    ) -> None:
        if not config_manager.get("auto_ban_enabled"):
            return
        if self._arena_state.ban_handled:
            return
        if generation is None:
            generation = self._automation_snapshot()
        if generation is None:
            return
        target = champion_id(config_manager.get("arena_ban_champ"))
        if target <= 0:
            self._automation_state_event(
                generation,
                "Ban: bị chặn — chưa chọn tướng cấm",
                "red",
                lambda: setattr(self._arena_state, "ban_handled", True),
            )
            return

        if self._confirm_pending_ban(session, generation):
            return

        all_bans = self._all_my_actions(session, "ban")
        for action in all_bans:
            existing_id = self._action_champion_id(action)
            if existing_id > 0:
                # Không có pending action của bot → đây là lựa chọn của user.
                self._commit_pending_user_ban(generation, existing_id)
                return

        if self._arena_state.ban_fail_count > 0 and self._real_pick_open(session):
            self._alert(
                "⚠️ Không xác minh được tướng cấm trước khi vào Pick — hãy tự chọn.",
            )
            self._automation_state_update(
                generation,
                lambda: setattr(self._arena_state, "ban_handled", True),
            )
            return

        if not all_bans:
            if self._has_my_completed_action(session, "ban"):
                self._automation_state_event(
                    generation,
                    "Ban: user đã khóa tướng — không ghi đè",
                    "gray",
                    lambda: setattr(self._arena_state, "ban_handled", True),
                )
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
            if self._action_champion_id(a) > 0:
                # User đã tự chọn ban → tôn trọng, không ghi đè
                self._commit_pending_user_ban(
                    generation, self._action_champion_id(a)
                )
                return

            action_id = self._action_id(a)
            if action_id is None:
                self._arena_event("Ban: action thiếu ID — không PATCH", "orange")
                return
            known, live = self._live_action("ban", action_id)
            if not known:
                self._arena_event("Ban: chưa đọc được action live — không PATCH", "orange")
                return
            if live is None or self._action_champion_id(live) > 0:
                # Action đã biến mất hoặc user vừa tự chọn → tôn trọng.
                self._automation_state_event(
                    generation,
                    "Ban: action đã đổi hoặc user vừa chọn — không ghi đè",
                    "gray",
                    lambda: setattr(self._arena_state, "ban_handled", True),
                )
                return
            if not self._action_is_in_progress(live):
                self._arena_event("Ban: action chưa tới lượt — đang chờ", "orange")
                return

            owned = self._owned_ids()
            if owned is None:
                self._arena_event("Ban: chưa đọc được roster — không PATCH", "orange")
                return
            if target not in owned:
                self._arena_event(
                    f"Không cấm được: {self._champ_name(target)} không còn trong trò chơi",
                    "red",
                )
                self._alert("⚠️ Tướng ban không còn trong client — hãy tự chọn.")
                self._automation_state_update(
                    generation,
                    lambda: setattr(self._arena_state, "ban_handled", True),
                )
                return

            self._arena_event(
                f"Đang cấm: {self._champ_name(target)}",
                "blue",
            )
            result = self._set_action_champion_verified(
                "ban", action_id, target, generation
            )
            if result is None:
                return
            if result:
                self._commit_verified_action(generation, "ban", action_id, target)
                return
            # PATCH fail — giữ action chưa handled; retry đến khi action
            # đóng hoặc chuyển sang Pick thật.
            self._record_action_retry(generation, "ban", target)
            return

    # ---- pick ----

    def _handle_pick(
        self, session: dict, generation: Optional[int] = None
    ) -> None:
        if not config_manager.get("auto_pick_enabled"):
            return
        if generation is None:
            generation = self._automation_snapshot()
        if generation is None:
            return
        pending = self._arena_state.pick_pending_action
        pending_target = (
            champion_id(pending[1]) if pending is not None else 0
        )
        if pending_target > 0 and self._pick_holders(session, pending_target):
            self._pick_lost(session, generation, pending_target)
        elif self._prepare_pending_pick(session, generation):
            return
        if self._arena_state.pick_handled:
            # Đã hover xong (hoặc đã dừng vì lý do khác) — theo dõi xem
            # tướng bot chọn có bị team lấy mất hay không.
            if self._arena_state.pick_picked_id > 0:
                if not self._pick_watch(session, generation):
                    return
                live_mine = [
                    action
                    for action in self._pick_phase_actions(session)
                    if self._action_is_in_progress(action)
                ]
                if not live_mine or self._action_champion_id(live_mine[0]) == 0:
                    return
            else:
                return
        all_picks = self._pick_phase_actions(session)
        if not all_picks:
            if self._has_my_completed_post_ban_pick(session):
                self._automation_state_event(
                    generation,
                    "Pick: user đã khóa tướng — không ghi đè",
                    "gray",
                    lambda: setattr(self._arena_state, "pick_handled", True),
                )
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
        action_id = self._action_id(action)
        if action_id is None:
            self._arena_event("Pick: action thiếu ID — không PATCH", "orange")
            return
        pending = self._arena_state.pick_pending_action
        pending_target = (
            champion_id(pending[1])
            if pending is not None and pending[0] == action_id
            else 0
        )

        bans_revealed, banned = self._revealed_banned_ids(session)
        picked_others = self._picked_by_others_ids(session)
        if not bans_revealed:
            if time.time() - self._arena_state.champ_select_since < _BANS_REVEAL_TIMEOUT:
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
            if not self._arena_state.alerted:
                if not self._automation_state_update(
                    generation,
                    lambda: setattr(self._arena_state, "alerted", True),
                ):
                    return
                self._alert(_STATUS_BANS_UNKNOWN)
            self._automation_state_update(
                generation,
                lambda: setattr(self._arena_state, "pick_handled", True),
            )
            return

        names = ", ".join(self._champ_name(cid) for cid in sorted(banned))
        self._arena_event(f"Các tướng bị cấm: {names}", "gray")

        owned = self._owned_ids()
        if owned is None:
            self._arena_event("Pick: chưa đọc được roster — không tự chọn", "orange")
            return
        unavailable = banned | picked_others | (self._arena_state.pick_attempted_ids - {0})
        chain = self._chain_ids()
        available = [
            cid
            for cid in chain
            if cid not in unavailable and cid in owned
        ]

        if not available:
            self._arena_event(
                "Pick: bị chặn — không còn tướng hợp lệ trong chuỗi",
                "red",
            )
            if not self._arena_state.alerted:
                if not self._automation_state_update(
                    generation,
                    lambda: setattr(self._arena_state, "alerted", True),
                ):
                    return
                self._alert(_STATUS_ALERT)
            self._automation_state_update(
                generation,
                lambda: setattr(self._arena_state, "pick_handled", True),
            )
            return

        if not self._arena_state.pick_wait_logged:
            if not self._automation_state_update(
                generation,
                lambda: setattr(self._arena_state, "pick_wait_logged", True),
            ):
                return
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
        known, live = self._live_action("pick", action_id)
        if not known:
            self._arena_event("Pick: chưa đọc được action live — không PATCH", "orange")
            return
        live_hover = self._action_champion_id(live) if live else 0
        if (
            live is not None
            and pending_target > 0
            and pending_target in picked_others
        ):
            self._pick_lost(session, generation, pending_target)
            pending_target = 0
        if live is None and pending_target > 0:
            self._arena_event(
                "Pick: chưa đọc được action đang chờ — tiếp tục theo dõi",
                "orange",
            )
            return
        if pending_target > 0 and live_hover == 0:
            self._arena_event(
                "Pick: lựa chọn bot đang chờ client cập nhật",
                "orange",
            )
            return
        lost_owned_hover = (
            live_hover > 0
            and live_hover in picked_others
            and live_hover in self._arena_state.pick_attempted_ids
        )
        def mark_user_pick() -> None:
            self._arena_state.pick_pending_action = None
            self._arena_state.pick_handled = True

        user_changed = live_hover > 0 and (
            pending_target > 0
            and live_hover != pending_target
            or pending_target == 0
        )
        if live is None or (user_changed and not lost_owned_hover):
            # Action đã biến mất hoặc user vừa tự chọn → tôn trọng.
            self._automation_state_event(
                generation,
                "Pick: action đã đổi hoặc user vừa chọn — không ghi đè",
                "gray",
                mark_user_pick,
            )
            return
        if pending_target > 0 and live_hover == pending_target:
            if self._action_is_usable(live):
                self._commit_verified_action(
                    generation,
                    "pick",
                    action_id,
                    pending_target,
                    after_retry=True,
                )
                return
        if not self._action_is_in_progress(live):
            self._arena_event("Pick: action chưa tới lượt — đang chờ", "orange")
            return

        self._arena_event(
            f"Đang chọn: {self._champ_name(available[0])}",
            "blue",
        )
        result = self._set_action_champion_verified(
            "pick", action_id, available[0], generation
        )
        if result is None:
            return
        if result:
            self._commit_verified_action(
                generation, "pick", action_id, available[0]
            )
            return

        # PATCH fail — thử lại; sau 5 lần liên tiếp thì báo + dừng
        self._record_action_retry(generation, "pick", available[0])
    # ---- theo dõi tướng đã hover ----

    @staticmethod
    def _pick_holders(session: dict, cid: int) -> list:
        """Actor khác đang giữ tướng ``cid`` trên bảng (mình loại trừ)."""
        holders: list = []
        if not isinstance(session, dict) or champion_id(cid) <= 0:
            return holders
        cid = champion_id(cid)
        try:
            local = session["localPlayerCellId"]
        except (KeyError, TypeError):
            return holders
        for group in LcuWatcher._action_groups(session):
            for action in group:
                if action.get("type") != "pick":
                    continue
                if action.get("actorCellId") == local:
                    continue
                if LcuWatcher._action_champion_id(action) == cid:
                    holders.append(action.get("actorCellId"))
        return holders

    def _pick_lost(
        self,
        session: dict,
        generation: int,
        lost_id: Optional[int] = None,
    ) -> None:
        """Tướng bot đang hover bị người khác lấy → nhảy tướng kế tiếp."""
        with self._automation_lock:
            if not self._automation_current_locked(generation):
                return
            if lost_id is None:
                lost_id = self._arena_state.pick_picked_id
            self._arena_state.pick_picked_id = 0
            self._arena_state.pick_pending_action = None
            self._arena_state.pick_handled = False
            if lost_id > 0:
                self._arena_state.pick_attempted_ids.add(lost_id)
            self._arena_state.pick_wait_logged = True
            self._arena_event(
                f"{self._champ_name(lost_id)} bị lấy → chuyển tướng khác",
                "orange",
                force=True,
            )

    def _pick_watch(
        self, session: dict, generation: Optional[int] = None
    ) -> bool:
        """Mỗi giây kiểm tra tướng bot đã hover còn là của mình không."""
        if generation is None:
            generation = self._automation_snapshot()
        if generation is None:
            return False
        mine = [
            action
            for action in self._pick_phase_actions(session)
            if self._action_is_in_progress(action)
        ]
        if not mine:
            # Action biến mất: chờ đến khi client tạo lại, không tự ý làm gì.
            if self._pick_holders(session, self._arena_state.pick_picked_id):
                self._pick_lost(session, generation)
                return True
            return False
        current = self._action_champion_id(mine[0])
        if self._pick_holders(session, self._arena_state.pick_picked_id):
            self._pick_lost(session, generation)
            return True
        if current == self._arena_state.pick_picked_id:
            self._automation_state_update(
                generation,
                lambda: setattr(self._arena_state, "pick_wait_logged", False),
            )
            return False  # vẫn đang giữ đúng tướng — ổn
        if current == 0:
            # Hover bị client xóa (championId=0) mà KHÔNG AI giữ tướng cũ:
            # trạng thái CHƯA BIẾT, không kết luận "bạn đã tự chọn".
            def hover_cleared() -> None:
                self._arena_state.pick_picked_id = 0
                self._arena_state.pick_handled = False
                self._arena_state.pick_wait_logged = True

            self._automation_state_event(
                generation,
                "Pick: hover bị xóa — bot chọn lại",
                "orange",
                hover_cleared,
            )
            return False
        # Tướng cũ không còn ai giữ và action của mình đã đổi
        # → không phải team lấy — là BẠN TỰ đổi. Tôn trọng, dừng hẳn.

        def mark_user_changed() -> None:
            self._arena_state.pick_picked_id = 0
            self._arena_state.pick_handled = True

        self._automation_state_event(
            generation,
            f"Bạn đã tự chọn: {self._champ_name(current)} — bot dừng",
            "gray",
            mark_user_changed,
            force=True,
        )
        return False

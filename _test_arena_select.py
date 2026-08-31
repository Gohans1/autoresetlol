"""
Test mô phỏng ArenaSelectWatcher (auto ban/pick arena qua LCU).

Không cần client LoL thật - mock toàn bộ LCU + winsound + config.
Chạy: .venv/Scripts/python.exe _test_arena_select.py
"""
import sys
import threading
import time
import types
import copy
from typing import Optional

# --- Mock utils.lcu TRƯỚC khi import arena_select ---
class FakeLCU:
    session: Optional[dict] = None
    mode: Optional[str] = "ARENA"

    def __init__(self):
        self.phase = "Lobby"
        self.mode = "ARENA"
        self.session = None
        self.owned = [
            {"id": 1, "name": "Aatrox"},
            {"id": 2, "name": "Yasuo"},
            {"id": 3, "name": "Zed"},
            {"id": 4, "name": "Garen"},
            {"id": 99, "name": "TestBan"},
            {"id": 60053, "name": "Blitzcrank"},
        ]
        self.patches = []  # (action_id, champion_id)
        self.patch_ok = True
        self.apply_patch_to_session = True
        self.owned_raises = False
        self.session_reads = 0
        self.mutate_pick_on_second_read = False
        self.patch_state_champion_id = None
        self.patch_entered: Optional[threading.Event] = None
        self.patch_release: Optional[threading.Event] = None
        self.before_patch = None

    def gameflow_phase(self):
        return self.phase

    def game_mode(self):
        return self.mode

    def champ_select_session(self):
        self.session_reads += 1
        if self.mutate_pick_on_second_read and self.session_reads == 2 and self.session:
            for group in self.session.get("actions") or []:
                for current_action in group:
                    if current_action.get("type") == "pick":
                        current_action["championId"] = 4
            self.mutate_pick_on_second_read = False
        return self.session

    def set_action_champion(self, action_id, champion_id):
        if self.before_patch is not None:
            hook = self.before_patch
            self.before_patch = None
            hook()
        if self.patch_entered is not None:
            self.patch_entered.set()
            if self.patch_release is not None:
                self.patch_release.wait(2)
        if not self.patch_ok:
            return False
        self.patches.append((action_id, champion_id))
        if self.apply_patch_to_session and self.session:
            for group in self.session.get("actions") or []:
                for current_action in group:
                    if current_action.get("id") == action_id:
                        current_action["championId"] = (
                            self.patch_state_champion_id
                            if self.patch_state_champion_id is not None
                            else champion_id
                        )
        return True

    def owned_champions(self):
        if self.owned_raises:
            raise RuntimeError("client down")
        return list(self.owned)


fake_lcu = FakeLCU()
lcu_module = types.ModuleType("utils.lcu")
setattr(lcu_module, "lcu", fake_lcu)
sys.modules["utils.lcu"] = lcu_module

# --- Mock winsound ---
winsound_mock = types.ModuleType("winsound")
setattr(winsound_mock, "MessageBeep", lambda *a, **k: None)
setattr(winsound_mock, "MB_ICONHAND", 0x10)
sys.modules["winsound"] = winsound_mock

import lcu_watcher  # noqa: E402
from config import config_manager  # noqa: E402

# Tests must not pollute the runtime log used for live diagnostics.
lcu_watcher.logger.disabled = True
# --- Mock config_manager ---
fake_config = {
    "auto_ban_enabled": False,
    "auto_pick_enabled": False,
    "arena_ban_champ": 0,
    "arena_pick_chain": [0, 0, 0, 0],
}
config_manager.get = lambda key, default=None: fake_config.get(key, default)
config_manager.set = lambda key, value, save=True: fake_config.__setitem__(key, value)


def action(aid, atype, actor=0, completed=False, champion_id=0, in_progress=True):
    return {
        "id": aid,
        "type": atype,
        "actorCellId": actor,
        "completed": completed,
        "championId": champion_id,
        "isInProgress": in_progress,
    }


def make_session(local_cell=0, actions=None, bans_my=None, bans_their=None):
    return {
        "localPlayerCellId": local_cell,
        "actions": copy.deepcopy(actions or []),
        "bans": {
            "myTeamBans": bans_my or [],
            "theirTeamBans": bans_their or [],
        },
    }


FAILURES = []
STATUS_LOG = []
ARENA_EVENTS = []
NOTIFICATIONS = []


def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def make_watcher():
    STATUS_LOG.clear()
    ARENA_EVENTS.clear()
    NOTIFICATIONS.clear()
    fake_lcu.patches.clear()
    fake_lcu.patch_ok = True
    fake_lcu.apply_patch_to_session = True
    fake_lcu.session_reads = 0
    fake_lcu.mutate_pick_on_second_read = False
    fake_lcu.patch_state_champion_id = None
    fake_lcu.patch_entered = None
    fake_lcu.patch_release = None
    fake_lcu.before_patch = None
    w = lcu_watcher.LcuWatcher(
        update_status_callback=lambda t, c: STATUS_LOG.append((t, c)),
        arena_event_callback=lambda t, c: ARENA_EVENTS.append((t, c)),
        notification_callback=lambda *args: NOTIFICATIONS.append(args),
    )
    w.running = True
    w.set_automation_enabled(True)
    return w


def reset_state():
    fake_config.update(
        {
            "auto_ban_enabled": False,
            "auto_pick_enabled": False,
            "arena_ban_champ": 0,
            "arena_pick_chain": [0, 0, 0, 0],
        }
    )
    fake_lcu.phase = "Lobby"
    fake_lcu.mode = "ARENA"
    fake_lcu.session = None


BAN_ACTION = action(10, "ban", actor=0)
PICK_ACTION = action(20, "pick", actor=0)

# ============ T1: không champ select → không làm gì ============
reset_state()
w = make_watcher()
fake_lcu.phase = "Lobby"
w._tick()
check("T1: Lobby → không PATCH nào", fake_lcu.patches == [], str(fake_lcu.patches))

# ============ T2: ChampSelect nhưng CLASSIC → không làm gì ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.mode = "CLASSIC"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]])
fake_config["auto_ban_enabled"] = True
w._tick()
check("T2: CLASSIC → không PATCH nào", fake_lcu.patches == [], str(fake_lcu.patches))

# ============ T3: ban bật + cấu hình → PATCH ban đúng 1 lần ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]])
fake_config["auto_ban_enabled"] = True
fake_config["arena_ban_champ"] = 99
w._tick()
check("T3a: PATCH ban (10, 99)", fake_lcu.patches == [(10, 99)], str(fake_lcu.patches))
w._tick()
check("T3b: tick 2 không PATCH lại (1 lần duy nhất)", fake_lcu.patches == [(10, 99)], str(fake_lcu.patches))
check(
    "T3c: ban log có tên tướng",
    any(
        text == "Đã cấm: TestBan" and color == "green"
        for text, color in ARENA_EVENTS
    ),
    str(ARENA_EVENTS),
)
check(
    "T3 notification: ban verified",
    any(
        event == "arena.ban_verified"
        and message == "BAN đã xác minh: TestBan"
        and key
        for event, message, key in NOTIFICATIONS
    ),
    str(NOTIFICATIONS),
)

# ============ T3c2: vào game Arena chỉ báo một lần ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session()
w._tick()
fake_lcu.phase = "GameStart"
w._tick()
fake_lcu.phase = "InProgress"
w._tick()
w._tick()
check(
    "T3c2: vào game Arena chỉ báo một lần",
    [event for event, _message, key in NOTIFICATIONS]
    == ["arena.in_progress"]
    and NOTIFICATIONS[0][2],
    str(NOTIFICATIONS),
)

# ============ T3c3: Classic vào game không báo Arena ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.mode = "CLASSIC"
fake_lcu.session = make_session()
w._tick()
fake_lcu.phase = "InProgress"
w._tick()
check(
    "T3c3: Classic không gửi Arena notification",
    NOTIFICATIONS == [],
    str(NOTIFICATIONS),
)

# ============ T3d: Arena ID 60053 phải xác minh với action ID 53 ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]])
fake_config["auto_ban_enabled"] = True
fake_config["arena_ban_champ"] = 60053
fake_lcu.patch_state_champion_id = 53
w._tick()
check(
    "T3d: alias Blitzcrank → PATCH ID chuẩn 53",
    fake_lcu.patches == [(10, 53)],
    str(fake_lcu.patches),
)
check(
    "T3e: alias Blitzcrank → Ban được xác minh",
    any(
        text == "Đã cấm: Blitzcrank" and color == "green"
        for text, color in ARENA_EVENTS
    ),
    str(ARENA_EVENTS),
)

# ============ T4: user tự hover ban → tôn trọng, không ghi đè ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[[action(10, "ban", champion_id=42)], [PICK_ACTION]]
)
fake_config["auto_ban_enabled"] = True
fake_config["arena_ban_champ"] = 99
w._tick()
check("T4: user tự chọn ban → không PATCH", fake_lcu.patches == [], str(fake_lcu.patches))

# ============ T5: user đã complete ban → tôn trọng ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[[action(10, "ban", completed=True)], [PICK_ACTION]]
)
fake_config["auto_ban_enabled"] = True
w._tick()
check("T5: ban đã complete → không PATCH", fake_lcu.patches == [], str(fake_lcu.patches))

# ============ T5b: completed action không có champion → chưa user đã ban ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[[action(10, "ban", completed=True, champion_id=0)], [PICK_ACTION]]
)
fake_config["auto_ban_enabled"] = True
fake_config["arena_ban_champ"] = 99
w._tick()
check("T5b: completed champion=0 → chưa đánh dấu ban", w._arena_state.ban_handled is False)
check("T5b: completed champion=0 → không PATCH", fake_lcu.patches == [], str(fake_lcu.patches))

# ============ T6: pick — main bị ban → dự bị ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[[BAN_ACTION], [PICK_ACTION]],
    bans_my=[84],
    bans_their=[1],
)
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]  # main=1 (bị ban) → Yasuo=2
w._tick()
check("T6: main bị ban → pick dự bị (20, 2)", fake_lcu.patches == [(20, 2)], str(fake_lcu.patches))
check(
    "T6 notification: pick verified",
    any(
        event == "arena.pick_verified"
        and message == "PICK đã xác minh: Yasuo"
        and key
        for event, message, key in NOTIFICATIONS
    ),
    str(NOTIFICATIONS),
)

# ============ T7: hết sạch dự bị → alert 1 lần, không PATCH ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[1, 2], bans_their=[84])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._tick()
check("T7a: hết dự bị → không PATCH", fake_lcu.patches == [], str(fake_lcu.patches))
check(
    "T7b: alert đỏ được báo",
    len(STATUS_LOG) == 1 and STATUS_LOG[0][1] == "red" and "bị ban" in STATUS_LOG[0][0],
    str(STATUS_LOG),
)
w._tick()
check(
    "T7c: alert chỉ 1 lần/session",
    len(STATUS_LOG) == 1,
    str(STATUS_LOG),
)

# ============ T8: pick chờ bans lộ mới hành động ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]])  # bans trống
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._tick()
check("T8a: bans chưa lộ → không PATCH", fake_lcu.patches == [], str(fake_lcu.patches))
# bans lộ ra
fake_lcu.session["bans"]["myTeamBans"] = [84]
fake_lcu.session["bans"]["theirTeamBans"] = [3]  # Zed bị ban, main Aatrox còn
w._tick()
check("T8b: bans lộ → pick main (20, 1)", fake_lcu.patches == [(20, 1)], str(fake_lcu.patches))

# ============ T8c: ban action có dữ liệu nhưng summary chưa lộ ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[
        [action(5, "pick", in_progress=True)],  # Pick Intent
        [action(10, "ban", completed=False, champion_id=1)],
        [action(30, "pick", in_progress=False)],  # Pick thật chưa mở
    ]
)
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._tick()
check(
    "T8c: Pick Intent → không chọn tạm thời",
    fake_lcu.patches == [],
    str(fake_lcu.patches),
)
check("T8c2: vẫn chờ phase Pick thật", w._arena_state.pick_handled is False, str(w._arena_state.pick_handled))
fake_lcu.session["actions"][2][0]["isInProgress"] = True
w._tick()
check(
    "T8d: Pick thật, summary rỗng → dùng ban action và chọn fallback (30, 2)",
    fake_lcu.patches == [(30, 2)],
    str(fake_lcu.patches),
)

# ============ T9: toggle tắt → không làm gì ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[1], bans_their=[84])
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._tick()
check("T9: toggle tắt → không PATCH", fake_lcu.patches == [], str(fake_lcu.patches))

# ============ T10: PATCH fail → tick sau thử lại ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[1], bans_their=[84])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [2, 0, 0, 0]
fake_lcu.patch_ok = False
w._tick()
check("T10a: PATCH fail → chưa handled, không PATCH ghi nhận", fake_lcu.patches == [], str(fake_lcu.patches))
fake_lcu.patch_ok = True
w._tick()
check("T10b: tick sau thành công (20, 2)", fake_lcu.patches == [(20, 2)], str(fake_lcu.patches))

# ============ T11: rời champ select → reset, session sau làm lại ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[1], bans_their=[84])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [2, 0, 0, 0]
w._tick()
check("T11a: session 1 pick (20, 2)", fake_lcu.patches == [(20, 2)], str(fake_lcu.patches))
fake_lcu.phase = "Lobby"
w._tick()  # reset
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[1], bans_their=[84])
w._tick()
check(
    "T11b: session 2 pick lại (2 lần PATCH)",
    fake_lcu.patches == [(20, 2), (20, 2)],
    str(fake_lcu.patches),
)

# ============ T12: user tự hover pick → tôn trọng ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[[BAN_ACTION], [action(20, "pick", champion_id=5)]], bans_my=[1], bans_their=[84]
)
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [2, 0, 0, 0]
w._tick()
check("T12: user tự hover → không ghi đè", fake_lcu.patches == [], str(fake_lcu.patches))

# ============ T13: tướng không sở hữu trong chain → bỏ qua ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[2], bans_their=[84])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [999, 1, 0, 0]  # 999 không sở hữu → Aatrox=1
w._tick()
check("T13: bỏ tướng không sở hữu → pick (20, 1)", fake_lcu.patches == [(20, 1)], str(fake_lcu.patches))

# ============ T14: ban PATCH fail → thử lại tick sau ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[[BAN_ACTION], [action(20, "pick", in_progress=False)]]
)
fake_config["auto_ban_enabled"] = True
fake_config["arena_ban_champ"] = 99
fake_lcu.patch_ok = False
w._tick()
check("T14a: ban fail → chưa handled", fake_lcu.patches == [], str(fake_lcu.patches))
fake_lcu.patch_ok = True
w._tick()
check("T14b: ban tick sau thành công (10, 99)", fake_lcu.patches == [(10, 99)], str(fake_lcu.patches))

# ============ T14c: HTTP PATCH OK nhưng state không đổi → không báo thành công ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[[BAN_ACTION], [action(20, "pick", in_progress=False)]]
)
fake_config["auto_ban_enabled"] = True
fake_config["arena_ban_champ"] = 99
fake_lcu.apply_patch_to_session = False
w._tick()
check(
    "T14c: PATCH không được xác minh → ban chưa handled",
    fake_lcu.patches == [(10, 99)] and w._arena_state.ban_handled is False,
    str(fake_lcu.patches),
)
fake_lcu.apply_patch_to_session = True
w._tick()
check(
    "T14d: verify fail → tick sau retry và thành công",
    fake_lcu.patches == [(10, 99), (10, 99)] and w._arena_state.ban_handled is True,
    str(fake_lcu.patches),
)

# ============ T14e: ban fail kéo dài nhưng action còn mở → tiếp tục chờ ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[[BAN_ACTION], [action(20, "pick", in_progress=False)]]
)
fake_config["auto_ban_enabled"] = True
fake_config["arena_ban_champ"] = 99
fake_lcu.patch_ok = False
for _ in range(6):
    w._tick()
check("T14e: quá 5 lần fail nhưng chưa kết thúc phase", w._arena_state.ban_handled is False)
fake_lcu.session["actions"][0][0]["championId"] = 99
w._tick()
check(
    "T14f: PATCH bị từ chối rồi user chọn → tôn trọng lựa chọn",
    w._arena_state.ban_handled is True
    and ARENA_EVENTS[-1][0].startswith("Bạn đã tự cấm:")
    and ARENA_EVENTS[-1][1] == "gray",
    str(ARENA_EVENTS[-1]),
)

# ============ T14g: action bot đặt rồi mới completed → không gắn nhãn user ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[[BAN_ACTION], [action(20, "pick", in_progress=False)]]
)
fake_config["auto_ban_enabled"] = True
fake_config["arena_ban_champ"] = 99
fake_lcu.apply_patch_to_session = False
w._tick()
fake_lcu.session["actions"][0][0]["championId"] = 99
fake_lcu.session["actions"][0][0]["completed"] = True
fake_lcu.session["actions"][0][0]["isInProgress"] = False
w._tick()
check(
    "T14g: completed action cùng target → xác minh sau retry",
    w._arena_state.ban_handled is True
    and ARENA_EVENTS[-1][0].startswith("Đã cấm:")
    and "xác minh sau retry" in ARENA_EVENTS[-1][0]
    and ARENA_EVENTS[-1][1] == "green",
    str(ARENA_EVENTS[-1]),
)

# ============ T15: game_mode() trả None → không làm gì, không crash ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.mode = None
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[1], bans_their=[84])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
w._tick()
check("T15: game_mode None → không PATCH", fake_lcu.patches == [], str(fake_lcu.patches))

# ============ T16: roster unknown → fail-closed, không pick ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3], bans_their=[84])
fake_lcu.owned_raises = True
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
w._tick()
check("T16: owned fail → không pick theo chain", fake_lcu.patches == [], str(fake_lcu.patches))
check("T16b: owned fail → vẫn chờ roster", w._arena_state.pick_handled is False)
fake_lcu.owned_raises = False

# ============ T16c: roster rỗng hợp lệ → không pick ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3], bans_their=[84])
owned_backup = fake_lcu.owned
fake_lcu.owned = []
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
w._tick()
check("T16c: owned rỗng → không pick", fake_lcu.patches == [], str(fake_lcu.patches))
fake_lcu.owned = owned_backup

# ============ T17: session thiếu key actions → không crash ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=None, bans_my=[1], bans_their=[84])
del fake_lcu.session["actions"]
fake_config["auto_ban_enabled"] = True
fake_config["auto_pick_enabled"] = True
fake_config["arena_ban_champ"] = 99
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
w._tick()
check("T17: thiếu actions → không crash, không PATCH", fake_lcu.patches == [], str(fake_lcu.patches))

# ============ T18: nhiều ban action → dùng action đầu tiên ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[[action(10, "ban"), action(11, "ban")], [PICK_ACTION]]
)
fake_config["auto_ban_enabled"] = True
fake_config["arena_ban_champ"] = 99
w._tick()
check("T18: nhiều ban action → PATCH action đầu (10, 99)", fake_lcu.patches == [(10, 99)], str(fake_lcu.patches))

# ============ T19: pick PATCH fail 5 lần liên tiếp → alert + dừng ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3], bans_their=[84])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
fake_lcu.patch_ok = False
for _ in range(4):
    w._tick()
check("T19a: 4 tick fail → chưa alert", len(STATUS_LOG) == 0, str(STATUS_LOG))
w._tick()  # lần 5
check(
    "T19b: tick 5 → alert + dừng",
    len(STATUS_LOG) == 1 and "Không đặt được tướng" in STATUS_LOG[0][0],
    str(STATUS_LOG),
)
fake_lcu.patch_ok = True
w._tick()
check("T19c: sau alert → không PATCH nữa", fake_lcu.patches == [], str(fake_lcu.patches))

# ============ T20: bans không lộ quá 40s → fail-closed, không PATCH ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]])  # bans trống
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
w._tick()
check("T20a: bans trống, mới vào → chờ, không PATCH", fake_lcu.patches == [], str(fake_lcu.patches))
w._arena_state.champ_select_since = time.time() - 45  # giả lập đã chờ lâu
w._tick()
check("T20b: quá 40s → không PATCH khi bans chưa biết", fake_lcu.patches == [], str(fake_lcu.patches))
check(
    "T20c: quá 40s → báo không đọc được bans",
    len(STATUS_LOG) == 1
    and "PICK bị dừng" in STATUS_LOG[0][0]
    and "không tự PICK" in STATUS_LOG[0][0],
    str(STATUS_LOG),
)

# ============ T21: pick action chưa isInProgress (đang ban phase) → CHỜ, không handled ============
# Bug cũ: early-exit "không có action → user đã khóa" làm auto-pick chết ở trận thật.
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[
        [action(10, "ban", completed=True)],  # ban xong
        [action(20, "pick", in_progress=False)],  # pick chưa mở
    ],
    bans_my=[3],
    bans_their=[84],
)
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
w._tick()
check("T21a: pick chưa mở → chờ, KHÔNG PATCH", fake_lcu.patches == [], str(fake_lcu.patches))
check("T21b: chưa đánh dấu handled (vẫn chờ)", w._arena_state.pick_handled is False, str(w._arena_state.pick_handled))
# Tick sau: pick phase mở → pick thành công
w._tick()
check("T21c: pick phase vẫn chưa mở → vẫn chờ", fake_lcu.patches == [], str(fake_lcu.patches))
fake_lcu.session = make_session(
    actions=[
        [action(10, "ban", completed=True)],
        [action(20, "pick", in_progress=True)],
    ],
    bans_my=[3],
    bans_their=[84],
)
w._tick()
check("T21d: pick mở → PATCH (20, 1)", fake_lcu.patches == [(20, 1)], str(fake_lcu.patches))

# ============ T21e: pick action chưa tồn tại trong ban phase → CHỜ ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION]], bans_my=[3], bans_their=[84])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._tick()
check("T21e: chưa có pick action → không đánh dấu handled", w._arena_state.pick_handled is False)
fake_lcu.session = make_session(
    actions=[[BAN_ACTION], [PICK_ACTION]],
    bans_my=[3],
    bans_their=[84],
)
w._tick()
check("T21f: pick action xuất hiện sau đó → PATCH (20, 1)", fake_lcu.patches == [(20, 1)], str(fake_lcu.patches))

# ============ T22: ban action chưa in-progress → chờ, không handled ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[[action(10, "ban", in_progress=False)], [PICK_ACTION]]
)
fake_config["auto_ban_enabled"] = True
fake_config["arena_ban_champ"] = 99
w._tick()
check("T22a: ban chưa mở → chờ, KHÔNG PATCH", fake_lcu.patches == [], str(fake_lcu.patches))
check("T22b: chưa handled", w._arena_state.ban_handled is False, str(w._arena_state.ban_handled))
fake_lcu.session = make_session(
    actions=[[action(10, "ban", in_progress=True)], [PICK_ACTION]]
)
w._tick()
check("T22c: ban mở → PATCH (10, 99)", fake_lcu.patches == [(10, 99)], str(fake_lcu.patches))

# ============ T23: master gate tắt → không PATCH ============
reset_state()
w = make_watcher()
w.set_automation_enabled(False)
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3], bans_their=[84])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
w._tick()
check("T23a: automation tắt → không PATCH", fake_lcu.patches == [], str(fake_lcu.patches))
w.set_automation_enabled(True)
w._tick()
check("T23b: bật lại → PATCH pick", fake_lcu.patches == [(20, 1)], str(fake_lcu.patches))

# ============ T24: user hover giữa read và PATCH → không ghi đè ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3], bans_their=[84])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
fake_lcu.mutate_pick_on_second_read = True
w._tick()
check("T24a: user hover race → không PATCH", fake_lcu.patches == [], str(fake_lcu.patches))
check(
    "T24b: giữ lựa chọn user",
    fake_lcu.session["actions"][1][0]["championId"] == 4,
    str(fake_lcu.session),
)

# ============ T25: live event dedupe ============
ARENA_EVENTS.clear()
event_watcher = lcu_watcher.LcuWatcher(
    arena_event_callback=lambda t, c: ARENA_EVENTS.append((t, c))
)
event_watcher._arena_event("same state", "gray")
event_watcher._arena_event("same state", "gray")
check("T25a: event giống nhau không spam", len(ARENA_EVENTS) == 1, str(ARENA_EVENTS))
event_watcher._arena_event("same state", "gray", force=True)
check("T25b: force event vẫn hiển thị", len(ARENA_EVENTS) == 2, str(ARENA_EVENTS))

# ============ T26: automation toggle idempotent ============
ARENA_EVENTS.clear()
toggle_watcher = lcu_watcher.LcuWatcher(
    arena_event_callback=lambda t, c: ARENA_EVENTS.append((t, c))
)
toggle_watcher.set_automation_enabled(False)
toggle_watcher.set_automation_enabled(False)
toggle_watcher.set_automation_enabled(True)
toggle_watcher.set_automation_enabled(False)
check("T26: disable lặp không phát event lặp", len(ARENA_EVENTS) == 1, str(ARENA_EVENTS))

# ============ T27: team pick mất tướng sau khi bot đã hover → nhảy dự bị ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3], bans_their=[84])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._tick()
check("T27a: bot hover main (20, 1)", fake_lcu.patches == [(20, 1)], str(fake_lcu.patches))
check("T27b: nhớ tướng đang giữ", w._arena_state.pick_picked_id == 1, str(w._arena_state.pick_picked_id))
# Teammate (actor 9) lấy mất tướng 1, mình bị reset về rỗng
fake_lcu.session = make_session(
    actions=[
        [BAN_ACTION],
        [PICK_ACTION],
        [action(21, "pick", actor=9, champion_id=1)],
    ],
    bans_my=[3],
    bans_their=[84],
)
w._tick()
check("T27c: phát hiện bị lấy", w._arena_state.pick_picked_id == 0 and w._arena_state.pick_handled is False, str((w._arena_state.pick_picked_id, w._arena_state.pick_handled)))
check(
    "T27d: ghi nhớ tướng đã thử để không chọn lại",
    1 in w._arena_state.pick_attempted_ids,
    str(w._arena_state.pick_attempted_ids),
)
w._tick()
check("T27e: nhảy sang dự bị (20, 2)", fake_lcu.patches[-1] == (20, 2), str(fake_lcu.patches))

# ============ T28: user tự đổi sau khi bot hover → tôn trọng, dừng hẳn ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3], bans_their=[84])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._tick()
check("T28a: bot hover main (20, 1)", fake_lcu.patches == [(20, 1)], str(fake_lcu.patches))
# User tự đổi sang tướng 4 (không ai giữ tướng 1) → bot dừng
fake_lcu.session = make_session(
    actions=[[BAN_ACTION], [action(20, "pick", champion_id=4)]],
    bans_my=[3],
    bans_their=[84],
)
w._tick()
check("T28b: dừng hẳn, không giành lại", w._arena_state.pick_handled is True and w._arena_state.pick_picked_id == 0, str((w._arena_state.pick_handled, w._arena_state.pick_picked_id)))
before = list(fake_lcu.patches)
w._tick()
check("T28c: không PATCH thêm", fake_lcu.patches == before, str(fake_lcu.patches))

# ============ T29: teammate pick sẵn từ đầu → bot né ngay, chọn dự bị ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[
        [BAN_ACTION],
        [PICK_ACTION],
        [action(21, "pick", actor=9, champion_id=1)],
    ],
    bans_my=[3],
    bans_their=[84],
)
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._tick()
check("T29a: né tướng bị lấy, chọn dự bị (20, 2)", fake_lcu.patches == [(20, 2)], str(fake_lcu.patches))
check(
    "T29b: picked_by_others trả đúng id đối thủ đang giữ",
    lcu_watcher.LcuWatcher._picked_by_others_ids(fake_lcu.session) == {1},
    str(lcu_watcher.LcuWatcher._picked_by_others_ids(fake_lcu.session)),
)

# ============ T30: log pick/ban hiện TÊN tướng ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3], bans_their=[84])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._tick()
check(
    "T30a: log pick có tên (Aatrox)",
    any(
        text == "Đã chọn: Aatrox" and color == "green"
        for text, color in ARENA_EVENTS
    ),
    str(ARENA_EVENTS),
)
# Main bị cấm → log rõ lý do + tên dự bị
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[1], bans_their=[84])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._tick()
check(
    "T30b: main bị cấm → log rõ lý do + tên dự bị",
    any(
        text == "Aatrox bị cấm → chọn: Yasuo" and color == "orange"
        for text, color in ARENA_EVENTS
    ),
    str(ARENA_EVENTS),
)
check(
    "T30c: fallback cũng log tên",
    any(
        text == "Đã chọn: Yasuo" and color == "green"
        for text, color in ARENA_EVENTS
    ),
    str(ARENA_EVENTS),
)
# Roster unknown → fail-closed, không tự chọn
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3], bans_their=[84])
fake_lcu.owned_raises = True
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._tick()
check(
    "T30d: roster unknown → không tự chọn",
    fake_lcu.patches == [],
    str(ARENA_EVENTS),
)
fake_lcu.owned_raises = False

# ============ T30e: disable giữa PATCH và read-back không commit state ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3], bans_their=[84])
generation = w._automation_snapshot()
if generation is None:
    raise AssertionError("automation generation must be active in the race test")
original_session_reader = fake_lcu.champ_select_session


def disable_during_readback():
    w.set_automation_enabled(False)
    return fake_lcu.session


fake_lcu.champ_select_session = disable_during_readback
try:
    result = w._set_action_champion_verified("ban", 10, 99, generation)
finally:
    fake_lcu.champ_select_session = original_session_reader
check("T30e1: disable giữa read-back hủy kết quả", result is None, str(result))
check(
    "T30e2: disable giữa read-back không giữ pending state",
    w._arena_state.ban_pending_action is None
    and w._arena_state.ban_handled is False
    and NOTIFICATIONS == [],
    str((w._arena_state.ban_pending_action, w._arena_state.ban_handled, NOTIFICATIONS)),
)

# ============ T30g: disable không chờ PATCH network ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3], bans_their=[84])
generation = w._automation_snapshot()
if generation is None:
    raise AssertionError("automation generation must be active in the blocked PATCH test")
assert generation is not None
patch_entered = threading.Event()
patch_release = threading.Event()
fake_lcu.patch_entered = patch_entered
fake_lcu.patch_release = patch_release
result_holder = []


def blocked_patch():
    result_holder.append(w._set_action_champion_verified("ban", 10, 99, generation))


patch_thread = threading.Thread(target=blocked_patch)
patch_thread.start()
check("T30g1: PATCH đã vào điểm chặn", patch_entered.wait(1))
disable_done = threading.Event()


def disable_while_patch_blocked():
    w.set_automation_enabled(False)
    disable_done.set()


disable_thread = threading.Thread(target=disable_while_patch_blocked)
disable_thread.start()
check("T30g2: disable chờ PATCH", not disable_done.wait(0.1))
patch_release.set()
patch_thread.join(timeout=2)
disable_thread.join(timeout=2)
check(
    "T30g2a: race threads đã kết thúc",
    not patch_thread.is_alive() and not disable_thread.is_alive(),
)
fake_lcu.patch_entered = None
fake_lcu.patch_release = None
check("T30g3: PATCH stale bị hủy", result_holder == [None], str(result_holder))
check(
    "T30g4: PATCH stale không commit state/notification",
    w._arena_state.ban_pending_action is None and NOTIFICATIONS == [],
    str((w._arena_state.ban_pending_action, NOTIFICATIONS)),
)

# ============ T30h: stop từ event callback chặn notification ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3], bans_their=[84])
generation = w._automation_snapshot()
if generation is None:
    raise AssertionError("automation generation must be active in callback stop test")


def stop_on_verified_event(text, _color):
    if text.startswith("Đã cấm:"):
        w.stop()


w.arena_event_callback = stop_on_verified_event
result = w._commit_verified_action(generation, "ban", 10, 99)
check("T30h1: callback STOP hủy commit", result is False, str(result))
check(
    "T30h2: callback STOP không gửi notification",
    w._arena_state.ban_handled is False and NOTIFICATIONS == [],
    str((w._arena_state.ban_handled, NOTIFICATIONS)),
)

# ============ T30f: watcher STOP trước khi run không poll ============
early_watcher = lcu_watcher.LcuWatcher()
early_ticks = []
early_watcher._tick = lambda: early_ticks.append("tick")
early_watcher.stop()
early_watcher.start()
early_watcher.join(timeout=2)
check("T30f: watcher STOP sớm không chạy tick", early_ticks == [], str(early_ticks))

# ============ T31: Pick Intent completed KHÔNG chặn auto-pick thật ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
INTENT_DONE = action(5, "pick", completed=True, champion_id=7)
fake_lcu.session = make_session(actions=[[INTENT_DONE], [BAN_ACTION]])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
w._tick()
check(
    "T31a: intent hoàn tất không khóa pick_handled",
    w._arena_state.pick_handled is False,
    str(w._arena_state),
)
check("T31b: chưa có pick thật → chưa PATCH", fake_lcu.patches == [], str(fake_lcu.patches))
# Ban xong → lộ ban summary + pick THẬT mở sau nhóm ban
fake_lcu.session = make_session(
    actions=[
        [INTENT_DONE],
        [action(10, "ban", champion_id=3)],
        [PICK_ACTION],
    ],
    bans_my=[3],
    bans_their=[84],
)
w._tick()
check(
    "T31c: pick thật mở → PATCH chuỗi bình thường",
    fake_lcu.patches == [(20, 1)],
    str(fake_lcu.patches),
)

# ============ T32: hover bị client xóa (cid=0) → chọn lại, không dừng ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
fake_lcu.session = make_session(
    actions=[[action(10, "ban", champion_id=3)], [action(20, "pick", champion_id=1)]],
    bans_my=[3],
    bans_their=[84],
)
w._tick()
w._arena_state.pick_picked_id = 1
w._arena_state.pick_handled = True
# Client xóa hover: action còn nhưng championId=0, không ai giữ tướng 1
fake_lcu.session = make_session(
    actions=[[action(10, "ban", champion_id=3)], [action(20, "pick")]],
    bans_my=[3],
    bans_their=[84],
)
w._tick()
check(
    "T32a: hover bị xóa là unknown → không kết luận 'tự chọn' và không dừng",
    w._arena_state.pick_handled is False,
    str(w._arena_state),
)
w._tick()
check(
    "T32b: tick sau bot chọn lại tướng đầu chuỗi",
    fake_lcu.patches == [(20, 1)],
    str(fake_lcu.patches),
)

# ============ T33: automation chết giữa tick → không phát event hover-cleared ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
fake_lcu.session = make_session(
    actions=[[action(10, "ban", champion_id=3)], [action(20, "pick", champion_id=1)]],
    bans_my=[3],
    bans_their=[84],
)
w._tick()
w._arena_state.pick_picked_id = 1
w._arena_state.pick_handled = True
fake_lcu.session = make_session(
    actions=[[action(10, "ban", champion_id=3)], [action(20, "pick")]],
    bans_my=[3],
    bans_their=[84],
)
real_holders = lcu_watcher.LcuWatcher._pick_holders


def holders_then_stop(session, cid):
    # Lease chết NGAY TRƯỚC nhánh hover-cleared. Set event trực tiếp thay vì
    # stop() vì stop() tự reset arena state theo thiết kế → không phân biệt được.
    w._stop_event.set()
    return real_holders(session, cid)


w._pick_holders = holders_then_stop
ARENA_EVENTS.clear()
w._pick_watch(fake_lcu.session)
check(
    "T33: lease chết giữa tick → không event 'bot chọn lại'",
    ARENA_EVENTS == [],
    str(ARENA_EVENTS),
)
check(
    "T33b: state không đổi khi lease chết",
    w._arena_state.pick_handled is True and w._arena_state.pick_picked_id == 1,
    str(w._arena_state),
)

# ============ T34: delayed Pick read-back belongs to the bot ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.apply_patch_to_session = False
fake_lcu.session = make_session(
    actions=[
        [action(10, "ban", champion_id=3)],
        [action(20, "pick")],
    ],
    bans_my=[3],
    bans_their=[84],
)
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._tick()
check(
    "T34a: delayed PATCH read-back keeps Pick pending",
    fake_lcu.patches == [(20, 1)] and w._arena_state.pick_handled is False,
    str(w._arena_state),
)
fake_lcu.session["actions"][1][0]["championId"] = 1
w._tick()
check(
    "T34b: delayed bot Pick verifies instead of becoming a user choice",
    w._arena_state.pick_handled is True
    and w._arena_state.pick_picked_id == 1
    and fake_lcu.patches == [(20, 1)]
    and any(
        text == "Đã chọn: Aatrox" and color == "green"
        for text, color in ARENA_EVENTS
    ),
    str(ARENA_EVENTS),
)

# ============ T34c: pending Pick does not PATCH again while client is empty ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.apply_patch_to_session = False
fake_lcu.session = make_session(
    actions=[[action(10, "ban", champion_id=3, completed=True, in_progress=False)], [action(20, "pick")]],
    bans_my=[3],
    bans_their=[84],
)
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
w._tick()
w._tick()
check(
    "T34c: empty delayed Pick does not duplicate PATCH",
    fake_lcu.patches == [(20, 1)]
    and w._arena_state.pick_pending_action == (20, 1)
    and w._arena_state.pick_handled is False,
    str((fake_lcu.patches, w._arena_state)),
)

# ============ T35: delayed Pick action may disappear briefly ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.apply_patch_to_session = False
fake_lcu.session = make_session(
    actions=[[action(10, "ban", champion_id=3, completed=True, in_progress=False)], [action(20, "pick")]],
    bans_my=[3],
    bans_their=[84],
)
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
w._tick()
fake_lcu.session["actions"][1].clear()
w._tick()
check(
    "T35a: absent delayed Pick keeps provenance",
    w._arena_state.pick_pending_action == (20, 1)
    and w._arena_state.pick_handled is False
    and fake_lcu.patches == [(20, 1)],
    str(w._arena_state),
)
fake_lcu.session["actions"][1].append(action(20, "pick", champion_id=1))
w._tick()
check(
    "T35b: reappearing delayed Pick commits without PATCH",
    w._arena_state.pick_handled is True
    and w._arena_state.pick_picked_id == 1
    and fake_lcu.patches == [(20, 1)],
    str(ARENA_EVENTS),
)

# ============ T36: delayed completed Pick sends one notification ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.apply_patch_to_session = False
fake_lcu.session = make_session(
    actions=[[action(10, "ban", champion_id=3, completed=True, in_progress=False)], [action(20, "pick")]],
    bans_my=[3],
    bans_their=[84],
)
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
w._tick()
fake_lcu.session["actions"][1][0].update(
    {"championId": 1, "completed": True, "isInProgress": False}
)
w._tick()
check(
    "T36a: completed delayed Pick commits once",
    w._arena_state.pick_handled is True
    and fake_lcu.patches == [(20, 1)],
    str(w._arena_state),
)
check(
    "T36b: completed delayed Pick notifies once",
    [event for event, _message, _key in NOTIFICATIONS]
    == ["arena.pick_verified"],
    str(NOTIFICATIONS),
)

# ============ T37: stale Pick snapshot cannot confirm the bot ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.apply_patch_to_session = False
fake_lcu.session = make_session(
    actions=[[action(10, "ban", champion_id=3, completed=True, in_progress=False)], [action(20, "pick")]],
    bans_my=[3],
    bans_their=[84],
)
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
w._tick()
fake_lcu.session["actions"][1][0].update(
    {"championId": 1, "completed": True, "isInProgress": False}
)
fake_lcu.session_reads = 0
fake_lcu.mutate_pick_on_second_read = True
w._tick()
check(
    "T37: stale completed Pick snapshot respects live user choice",
    w._arena_state.pick_handled is True
    and w._arena_state.pick_picked_id == 0
    and fake_lcu.patches == [(20, 1)]
    and any(text.startswith("Bạn đã tự chọn: Garen") for text, _color in ARENA_EVENTS),
    str(ARENA_EVENTS),
)

# ============ T38: user may reselect a champion the bot attempted earlier ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
fake_lcu.session = make_session(
    actions=[[action(10, "ban", champion_id=3, completed=True, in_progress=False)], [action(20, "pick")]],
    bans_my=[3],
    bans_their=[84],
)
w._tick()
check("T38a: bot first pick", fake_lcu.patches == [(20, 1)], str(fake_lcu.patches))
fake_lcu.session = make_session(
    actions=[
        [action(10, "ban", champion_id=3, completed=True, in_progress=False)],
        [action(20, "pick")],
        [action(21, "pick", actor=9, champion_id=1)],
    ],
    bans_my=[3],
    bans_their=[84],
)
w._tick()
check("T38b: teammate takes first pick", 1 in w._arena_state.pick_attempted_ids, str(w._arena_state))
fake_lcu.session = make_session(
    actions=[[action(10, "ban", champion_id=3, completed=True, in_progress=False)], [action(20, "pick", champion_id=1)]],
    bans_my=[3],
    bans_their=[84],
)
w._tick()
check(
    "T38c: user reselects attempted champion without overwrite",
    fake_lcu.patches == [(20, 1)]
    and w._arena_state.pick_handled is True
    and w._arena_state.pick_picked_id == 0,
    str((fake_lcu.patches, w._arena_state)),
)

# ============ T39: pending Pick lost to another player falls back ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.apply_patch_to_session = False
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
fake_lcu.session = make_session(
    actions=[[action(10, "ban", champion_id=3, completed=True, in_progress=False)], [action(20, "pick")]],
    bans_my=[3],
    bans_their=[84],
)
w._tick()
check(
    "T39a: delayed Pick has pending provenance",
    w._arena_state.pick_pending_action == (20, 1),
    str(w._arena_state),
)
fake_lcu.session = make_session(
    actions=[
        [action(10, "ban", champion_id=3, completed=True, in_progress=False)],
        [action(20, "pick")],
        [action(21, "pick", actor=9, champion_id=1)],
    ],
    bans_my=[3],
    bans_their=[84],
)
w._tick()
check(
    "T39b: teammate takes pending Pick and bot falls back",
    fake_lcu.patches == [(20, 1), (20, 2)]
    and 1 in w._arena_state.pick_attempted_ids
    and w._arena_state.pick_pending_action == (20, 2),
    str((fake_lcu.patches, w._arena_state)),
)

# ============ T40: session snapshot is bound to the automation generation ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
stale_session = make_session(
    actions=[[action(10, "ban", champion_id=3, completed=True, in_progress=False)], [action(20, "pick")]],
    bans_my=[84],
    bans_their=[3],
)
fresh_session = make_session(
    actions=[[action(10, "ban", champion_id=3, completed=True, in_progress=False)], [action(20, "pick")]],
    bans_my=[84],
    bans_their=[1],
)
fake_lcu.session = fresh_session
original_session_reader = fake_lcu.champ_select_session
try:
    def read_stale_then_fresh():
        fake_lcu.session_reads += 1
        if fake_lcu.session_reads == 1:
            w.set_automation_enabled(False)
            w.set_automation_enabled(True)
            return stale_session
        return fresh_session

    fake_lcu.champ_select_session = read_stale_then_fresh
    w._tick()
    stale_tick_patches = list(fake_lcu.patches)
    w._tick()
finally:
    fake_lcu.champ_select_session = original_session_reader
check(
    "T40: generation change rejects stale session snapshot",
    stale_tick_patches == []
    and fake_lcu.patches == [(20, 2)]
    and w._arena_state.pick_picked_id == 2,
    str(fake_lcu.patches),
)

# ============ T41: pending Ban phải đọc lại action live ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.apply_patch_to_session = False
fake_lcu.session = make_session(
    actions=[[action(10, "ban", actor=0)], [action(20, "pick", in_progress=False)]]
)
fake_config["auto_ban_enabled"] = True
fake_config["arena_ban_champ"] = 99
w._tick()
stale_session = copy.deepcopy(fake_lcu.session)
stale_session["actions"][0][0]["championId"] = 99
fake_lcu.session = make_session(
    actions=[[action(10, "ban", actor=0, champion_id=4)], [action(20, "pick", in_progress=False)]]
)
w._handle_ban(stale_session)
check(
    "T41: stale pending Ban snapshot respects live user choice",
    w._arena_state.ban_handled is True
    and ARENA_EVENTS[-1][0].startswith("Bạn đã tự cấm:")
    and NOTIFICATIONS == [],
    str(ARENA_EVENTS[-1:]),
)

# ============ T42: không xác minh Pick khi đồng đội cũng giữ tướng ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[
        [action(10, "ban", champion_id=3, completed=True, in_progress=False)],
        [
            action(20, "pick", actor=0, champion_id=1),
            action(21, "pick", actor=9, champion_id=1),
        ],
    ],
    bans_my=[3],
    bans_their=[84],
)
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._arena_state.pick_pending_action = (20, 1)
w._handle_pick(fake_lcu.session)
check(
    "T42a: pending Pick holder race uses fallback",
    fake_lcu.patches == [(20, 2)]
    and 1 in w._arena_state.pick_attempted_ids
    and w._arena_state.pick_picked_id == 2
    and NOTIFICATIONS[-1][0] == lcu_watcher.DISCORD_EVENT_PICK,
    str((fake_lcu.patches, w._arena_state.pick_attempted_ids)),
)

reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[
        [action(10, "ban", champion_id=3, completed=True, in_progress=False)],
        [
            action(20, "pick", actor=0, champion_id=1),
            action(21, "pick", actor=9, champion_id=1),
        ],
    ],
    bans_my=[3],
    bans_their=[84],
)
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._arena_state.pick_handled = True
w._arena_state.pick_picked_id = 1
w._handle_pick(fake_lcu.session)
check(
    "T42b: Pick watch checks teammate holder before early return",
    fake_lcu.patches == [(20, 2)]
    and 1 in w._arena_state.pick_attempted_ids
    and w._arena_state.pick_picked_id == 2,
    str((fake_lcu.patches, w._arena_state.pick_attempted_ids)),
)

# ============ T43: action đổi trước PATCH thì không được ghi đè ============
def set_live_action_champion(action_id, champion_id_value):
    for group in fake_lcu.session.get("actions") or []:
        for current_action in group:
            if current_action.get("id") == action_id:
                current_action["championId"] = champion_id_value


reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[[action(10, "ban")], [action(20, "pick", in_progress=False)]]
)
stale_session = copy.deepcopy(fake_lcu.session)
original_session_reader = fake_lcu.champ_select_session
session_read_count = [0]


def read_stale_then_live_ban():
    session_read_count[0] += 1
    return stale_session if session_read_count[0] == 1 else fake_lcu.session


fake_lcu.champ_select_session = read_stale_then_live_ban
fake_config["auto_ban_enabled"] = True
fake_config["arena_ban_champ"] = 99
original_live_action = w._live_action


def live_ban_then_user(action_type, action_id):
    result = original_live_action(action_type, action_id)
    snapshot = copy.deepcopy(result) if result is not None else result
    if action_type == "ban":
        set_live_action_champion(10, 4)
    return snapshot


w._live_action = live_ban_then_user
try:
    w._tick()
finally:
    fake_lcu.champ_select_session = original_session_reader
check(
    "T43: Ban live action changes before PATCH",
    fake_lcu.patches == []
    and w._arena_state.ban_handled is False
    and NOTIFICATIONS == [],
    str((fake_lcu.patches, w._arena_state)),
)

reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[
        [action(10, "ban", champion_id=3, completed=True, in_progress=False)],
        [action(20, "pick")],
    ],
    bans_my=[3],
    bans_their=[84],
)
stale_session = copy.deepcopy(fake_lcu.session)
original_session_reader = fake_lcu.champ_select_session
session_read_count = [0]


def read_stale_then_live_pick():
    session_read_count[0] += 1
    return stale_session if session_read_count[0] == 1 else fake_lcu.session


fake_lcu.champ_select_session = read_stale_then_live_pick
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
original_live_action = w._live_action


def live_pick_then_user(action_type, action_id):
    result = original_live_action(action_type, action_id)
    snapshot = copy.deepcopy(result) if result is not None else result
    if action_type == "pick":
        set_live_action_champion(20, 4)
    return snapshot


w._live_action = live_pick_then_user
try:
    w._tick()
finally:
    fake_lcu.champ_select_session = original_session_reader
check(
    "T44: Pick live action changes before PATCH",
    fake_lcu.patches == []
    and w._arena_state.pick_handled is False
    and NOTIFICATIONS == [],
    str((fake_lcu.patches, w._arena_state)),
)

# ============ T45: action đổi sau read-back thì không commit bot ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[[action(10, "ban")], [action(20, "pick", in_progress=False)]]
)
fake_config["auto_ban_enabled"] = True
fake_config["arena_ban_champ"] = 99
original_verify = w._set_action_champion_verified


def verify_then_user_ban(*args, **kwargs):
    result = original_verify(*args, **kwargs)
    if result:
        set_live_action_champion(10, 4)
    return result


w._set_action_champion_verified = verify_then_user_ban
w._tick()
check(
    "T45: Ban read-back race does not commit bot result",
    fake_lcu.patches == [(10, 99)]
    and w._arena_state.ban_handled is False
    and NOTIFICATIONS == [],
    str((fake_lcu.patches, w._arena_state, NOTIFICATIONS)),
)

reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[
        [action(10, "ban", champion_id=3, completed=True, in_progress=False)],
        [action(20, "pick")],
    ],
    bans_my=[3],
    bans_their=[84],
)
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
original_verify = w._set_action_champion_verified


def verify_then_user_pick(*args, **kwargs):
    result = original_verify(*args, **kwargs)
    if result:
        set_live_action_champion(20, 4)
    return result


w._set_action_champion_verified = verify_then_user_pick
w._tick()
check(
    "T46: Pick read-back race does not commit bot result",
    fake_lcu.patches == [(20, 1)]
    and w._arena_state.pick_handled is False
    and NOTIFICATIONS == [],
    str((fake_lcu.patches, w._arena_state, NOTIFICATIONS)),
)

reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
stale_pick_session = make_session(
    actions=[
        [action(10, "ban", champion_id=3, completed=True, in_progress=False)],
        [action(20, "pick")],
    ],
    bans_my=[3],
    bans_their=[84],
)
fake_lcu.session = make_session(
    actions=[
        [action(10, "ban", champion_id=3, completed=True, in_progress=False)],
        [
            action(20, "pick", actor=0, champion_id=1),
            action(21, "pick", actor=9, champion_id=1),
        ],
    ],
    bans_my=[3],
    bans_their=[84],
)
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._arena_state.pick_pending_action = (20, 1)
w._handle_pick(stale_pick_session)
check(
    "T47: pending Pick live holder race does not verify bot result",
    fake_lcu.patches == []
    and w._arena_state.pick_picked_id == 0
    and w._arena_state.pick_handled is False
    and 1 in w._arena_state.pick_attempted_ids
    and NOTIFICATIONS == [],
    str((fake_lcu.patches, w._arena_state, NOTIFICATIONS)),
)

reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[
        [action(10, "ban", champion_id=3, completed=True, in_progress=False)],
        [action(20, "pick")],
    ],
    bans_my=[3],
    bans_their=[84],
)
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]


def add_live_pick_holder():
    fake_lcu.session["actions"][1].append(
        action(21, "pick", actor=9, champion_id=1)
    )


fake_lcu.before_patch = add_live_pick_holder
w._tick()
check(
    "T48: Pick holder race after PATCH does not notify bot success",
    fake_lcu.patches == [(20, 1)]
    and w._arena_state.pick_handled is False
    and w._arena_state.pick_pending_action == (20, 1)
    and NOTIFICATIONS == [],
    str((fake_lcu.patches, w._arena_state, NOTIFICATIONS)),
)

reset_state()
w = make_watcher()
fake_config.update(
    {
        "auto_dimmer_switch_enabled": True,
        "dimmer_enabled": True,
    }
)
dimmer_transitions = []
w.on_gaming_callback = lambda: dimmer_transitions.append("gaming")
w.on_browsing_callback = lambda: dimmer_transitions.append("browsing")
w._auto_dimmer("ChampSelect")
w._auto_dimmer("InProgress")
w._auto_dimmer("Lobby")
check(
    "T49: auto dimmer đổi một lần theo phase",
    dimmer_transitions == ["gaming", "browsing"]
    and w._gaming_state is False,
    str((dimmer_transitions, w._gaming_state)),
)
fake_config["dimmer_enabled"] = False
w._auto_dimmer("ChampSelect")
check(
    "T49b: dimmer tắt → không đổi mode",
    dimmer_transitions == ["gaming", "browsing"]
    and w._gaming_state is False,
    str((dimmer_transitions, w._gaming_state)),
)
fake_config["dimmer_enabled"] = True
fake_config["auto_dimmer_switch_enabled"] = False
w._auto_dimmer("ChampSelect")
check(
    "T49c: auto switch tắt → không đổi mode",
    dimmer_transitions == ["gaming", "browsing"]
    and w._gaming_state is False,
    str((dimmer_transitions, w._gaming_state)),
)
reset_state()
w = make_watcher()
fake_config.update(
    {
        "auto_dimmer_switch_enabled": True,
        "dimmer_enabled": True,
    }
)
dimmer_transitions = []
w.on_gaming_callback = lambda: dimmer_transitions.append("gaming")
w._auto_dimmer("ChampSelect")
fake_config["auto_dimmer_switch_enabled"] = False
w._auto_dimmer("Lobby")
fake_config["auto_dimmer_switch_enabled"] = True
w._auto_dimmer("ChampSelect")
check(
    "T49d: bật lại auto switch sẽ áp dụng lại mode hiện tại",
    dimmer_transitions == ["gaming", "gaming"]
    and w._gaming_state is True,
    str((dimmer_transitions, w._gaming_state)),
)
check(
    "T50: action thiếu isInProgress phải chờ",
    lcu_watcher.LcuWatcher._action_is_in_progress(
        {"type": "pick", "completed": False}
    )
    is False,
)

partial_bans = make_session(bans_my=[53], bans_their=[])
partial_revealed, partial_ids = lcu_watcher.LcuWatcher._revealed_banned_ids(partial_bans)
check(
    "T52: ban một phía chưa được coi là đã lộ",
    partial_revealed is False and partial_ids == set(),
    str((partial_revealed, partial_ids)),
)
complete_bans = make_session(bans_my=[53], bans_their=[84])
complete_revealed, complete_ids = lcu_watcher.LcuWatcher._revealed_banned_ids(complete_bans)
check(
    "T52b: ban hai phía đã lộ được chấp nhận",
    complete_revealed is True and complete_ids == {53, 84},
    str((complete_revealed, complete_ids)),
)
malformed_actions = make_session(actions=[[None, "bad"], None])
check(
    "T53: action LCU sai kiểu bị bỏ qua an toàn",
    lcu_watcher.LcuWatcher._all_my_actions(malformed_actions, "ban") == []
    and lcu_watcher.LcuWatcher._find_my_action(malformed_actions, "ban", 1) is None
    and lcu_watcher.LcuWatcher._post_ban_groups(malformed_actions) == []
    and lcu_watcher.LcuWatcher._pick_phase_actions(malformed_actions) == []
    and lcu_watcher.LcuWatcher._picked_by_others_ids(malformed_actions) == set()
    and lcu_watcher.LcuWatcher._pick_holders(malformed_actions, 53) == []
    and lcu_watcher.LcuWatcher._revealed_banned_ids(malformed_actions) == (False, set()),
    str(malformed_actions),
)

reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(
    actions=[
        [{"type": "ban", "actorCellId": 0, "isInProgress": True}],
        [action(20, "pick")],
    ],
    bans_my=[3],
    bans_their=[84],
)
fake_config.update(
    {
        "auto_ban_enabled": True,
        "arena_ban_champ": 99,
        "auto_pick_enabled": False,
    }
)
missing_id_error = None
try:
    w._tick()
except Exception as error:
    missing_id_error = type(error).__name__
check(
    "T54: action thiếu ID không làm watcher crash",
    missing_id_error is None and fake_lcu.patches == [],
    str((missing_id_error, fake_lcu.patches)),
)

malformed_completion = make_session(
    actions=[
        [action(60, "ban", completed="false", champion_id=53)],
        [action(61, "pick", completed=None, in_progress=True)],
    ]
)
check(
    "T55: completed sai kiểu không được coi là đã hoàn tất",
    lcu_watcher.LcuWatcher._has_my_completed_action(malformed_completion, "ban")
    is False,
    str(malformed_completion),
)
check(
    "T55b: completed thiếu giá trị không được coi là action đang chờ",
    lcu_watcher.LcuWatcher._all_my_actions(malformed_completion, "ban") == []
    and lcu_watcher.LcuWatcher._pick_phase_actions(malformed_completion) == [],
    str(malformed_completion),
)
bool_id_action = action(True, "ban", in_progress=True)
bool_id_session = make_session(actions=[[bool_id_action]])
check(
    "T56: bool action ID không khớp ID số",
    lcu_watcher.LcuWatcher._find_my_action(bool_id_session, "ban", 1) is None,
    str(bool_id_session),
)


reset_state()
w = make_watcher()
fake_lcu.session = make_session(
    actions=[[action(70, "ban", completed="false", in_progress=True)]]
)
generation = w._automation_snapshot()
live_patch_result = w._set_action_champion_verified("ban", 70, 99, generation)
check(
    "T57a: completed malformed chặn PATCH live",
    live_patch_result is None and fake_lcu.patches == [],
    str((live_patch_result, fake_lcu.patches)),
)

reset_state()
w = make_watcher()
fake_lcu.session = make_session(
    actions=[[action(71, "pick", completed="false", champion_id=1, in_progress=True)]]
)
generation = w._automation_snapshot()
live_commit_result = w._commit_verified_action(generation, "pick", 71, 1)
check(
    "T57b: completed malformed chặn commit live",
    live_commit_result is False and w._arena_state.pick_handled is False,
    str((live_commit_result, w._arena_state.pick_handled)),
)


def test_owned_ids_cache_expiry_and_error_state() -> None:
    reset_state()
    original_time = lcu_watcher.time.time
    original_owned = fake_lcu.owned
    original_raises = fake_lcu.owned_raises
    now = [100.0]
    try:
        lcu_watcher.time.time = lambda: now[0]
        fake_lcu.owned_raises = False
        fake_lcu.owned = [{"id": 60053, "name": "Blitzcrank"}]
        watcher = make_watcher()
        first = watcher._owned_ids()
        fake_lcu.owned = [{"id": 2, "name": "Yasuo"}]
        now[0] = 105.0
        cached = watcher._owned_ids()
        now[0] = 111.0
        refreshed = watcher._owned_ids()
        check("T51a: roster cache giữ dữ liệu trong TTL", cached == {53}, str(cached))
        check("T51b: roster cache hết TTL thì refresh", refreshed == {2}, str(refreshed))

        fake_lcu.owned_raises = True
        now[0] = 122.0
        failed = watcher._owned_ids()
        fake_lcu.owned_raises = False
        fake_lcu.owned = [{"id": 3, "name": "Zed"}]
        now[0] = 123.0
        blocked = watcher._owned_ids()
        now[0] = 133.0
        recovered = watcher._owned_ids()
        check("T51c: roster lỗi trả unknown", failed is None)
        check("T51d: roster lỗi không trả roster cũ", blocked is None, str(blocked))
        check("T51e: roster sau TTL thì hồi phục", recovered == {3}, str(recovered))
        check("T51f: first roster dùng alias canonical", first == {53}, str(first))
    finally:
        lcu_watcher.time.time = original_time
        fake_lcu.owned = original_owned
        fake_lcu.owned_raises = original_raises


test_owned_ids_cache_expiry_and_error_state()


def test_owned_ids_notifies_roster_callback() -> None:
    reset_state()
    fake_lcu.owned_raises = False
    fake_lcu.owned = [{"id": 1, "name": "Aatrox"}]
    updates = []
    watcher = lcu_watcher.LcuWatcher(
        roster_callback=lambda roster: updates.append(roster),
    )
    result = watcher._owned_ids()
    check(
        "T58: roster watcher báo dữ liệu mới cho giao diện",
        result == {1}
        and len(updates) == 1
        and updates[0] == [{"id": 1, "name": "Aatrox"}],
        str((result, updates)),
    )


test_owned_ids_notifies_roster_callback()

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} test thất bại: {FAILURES}")
    sys.exit(1)
print("ALL TESTS PASSED")

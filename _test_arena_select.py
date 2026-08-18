"""
Test mô phỏng ArenaSelectWatcher (auto ban/pick arena qua LCU).

Không cần client LoL thật - mock toàn bộ LCU + winsound + config.
Chạy: .venv/Scripts/python.exe _test_arena_select.py
"""
import sys
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
        ]
        self.patches = []  # (action_id, champion_id)
        self.patch_ok = True
        self.apply_patch_to_session = True
        self.owned_raises = False
        self.session_reads = 0
        self.mutate_pick_on_second_read = False

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
        if not self.patch_ok:
            return False
        self.patches.append((action_id, champion_id))
        if self.apply_patch_to_session and self.session:
            for group in self.session.get("actions") or []:
                for current_action in group:
                    if current_action.get("id") == action_id:
                        current_action["championId"] = champion_id
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


def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def make_watcher():
    STATUS_LOG.clear()
    ARENA_EVENTS.clear()
    fake_lcu.patches.clear()
    fake_lcu.patch_ok = True
    fake_lcu.apply_patch_to_session = True
    fake_lcu.session_reads = 0
    fake_lcu.mutate_pick_on_second_read = False
    w = lcu_watcher.LcuWatcher(
        update_status_callback=lambda t, c: STATUS_LOG.append((t, c)),
        arena_event_callback=lambda t, c: ARENA_EVENTS.append((t, c)),
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
check("T5b: completed champion=0 → chưa đánh dấu ban", w._ban_handled is False)
check("T5b: completed champion=0 → không PATCH", fake_lcu.patches == [], str(fake_lcu.patches))

# ============ T6: pick — main bị ban → dự bị ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_their=[1])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]  # main=1 (bị ban) → Yasuo=2
w._tick()
check("T6: main bị ban → pick dự bị (20, 2)", fake_lcu.patches == [(20, 2)], str(fake_lcu.patches))

# ============ T7: hết sạch dự bị → alert 1 lần, không PATCH ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[1, 2])
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
check("T8c2: vẫn chờ phase Pick thật", w._pick_handled is False, str(w._pick_handled))
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
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[1])
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._tick()
check("T9: toggle tắt → không PATCH", fake_lcu.patches == [], str(fake_lcu.patches))

# ============ T10: PATCH fail → tick sau thử lại ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[1])
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
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[1])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [2, 0, 0, 0]
w._tick()
check("T11a: session 1 pick (20, 2)", fake_lcu.patches == [(20, 2)], str(fake_lcu.patches))
fake_lcu.phase = "Lobby"
w._tick()  # reset
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[1])
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
    actions=[[BAN_ACTION], [action(20, "pick", champion_id=5)]], bans_my=[1]
)
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [2, 0, 0, 0]
w._tick()
check("T12: user tự hover → không ghi đè", fake_lcu.patches == [], str(fake_lcu.patches))

# ============ T13: tướng không sở hữu trong chain → bỏ qua ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[2])
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
    fake_lcu.patches == [(10, 99)] and w._ban_handled is False,
    str(fake_lcu.patches),
)
fake_lcu.apply_patch_to_session = True
w._tick()
check(
    "T14d: verify fail → tick sau retry và thành công",
    fake_lcu.patches == [(10, 99), (10, 99)] and w._ban_handled is True,
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
check("T14e: quá 5 lần fail nhưng chưa kết thúc phase", w._ban_handled is False)
fake_lcu.session["actions"][0][0]["championId"] = 99
w._tick()
check(
    "T14f: action đã có champion → xác nhận Ban sau retry",
    w._ban_handled is True
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
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[1])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
w._tick()
check("T15: game_mode None → không PATCH", fake_lcu.patches == [], str(fake_lcu.patches))

# ============ T16: owned_champions raise → fail-open, vẫn pick main ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3])
fake_lcu.owned_raises = True
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
w._tick()
check("T16: owned fail → vẫn pick theo chain (20, 1)", fake_lcu.patches == [(20, 1)], str(fake_lcu.patches))
fake_lcu.owned_raises = False

# ============ T17: session thiếu key actions → không crash ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=None, bans_my=[1])
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
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3])
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
w._champ_select_since = time.time() - 45  # giả lập đã chờ lâu
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
)
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 0, 0, 0]
w._tick()
check("T21a: pick chưa mở → chờ, KHÔNG PATCH", fake_lcu.patches == [], str(fake_lcu.patches))
check("T21b: chưa đánh dấu handled (vẫn chờ)", w._pick_handled is False, str(w._pick_handled))
# Tick sau: pick phase mở → pick thành công
w._tick()
check("T21c: pick phase vẫn chưa mở → vẫn chờ", fake_lcu.patches == [], str(fake_lcu.patches))
fake_lcu.session = make_session(
    actions=[
        [action(10, "ban", completed=True)],
        [action(20, "pick", in_progress=True)],
    ],
    bans_my=[3],
)
w._tick()
check("T21d: pick mở → PATCH (20, 1)", fake_lcu.patches == [(20, 1)], str(fake_lcu.patches))

# ============ T21e: pick action chưa tồn tại trong ban phase → CHỜ ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION]], bans_my=[3])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._tick()
check("T21e: chưa có pick action → không đánh dấu handled", w._pick_handled is False)
fake_lcu.session = make_session(
    actions=[[BAN_ACTION], [PICK_ACTION]],
    bans_my=[3],
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
check("T22b: chưa handled", w._ban_handled is False, str(w._ban_handled))
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
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3])
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
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3])
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
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._tick()
check("T27a: bot hover main (20, 1)", fake_lcu.patches == [(20, 1)], str(fake_lcu.patches))
check("T27b: nhớ tướng đang giữ", w._pick_picked_id == 1, str(w._pick_picked_id))
# Teammate (actor 9) lấy mất tướng 1, mình bị reset về rỗng
fake_lcu.session = make_session(
    actions=[
        [BAN_ACTION],
        [PICK_ACTION],
        [action(21, "pick", actor=9, champion_id=1)],
    ],
    bans_my=[3],
)
w._tick()
check("T27c: phát hiện bị lấy", w._pick_picked_id == 0 and w._pick_handled is False, str((w._pick_picked_id, w._pick_handled)))
check(
    "T27d: ghi nhớ tướng đã thử để không chọn lại",
    1 in w._pick_attempted_ids,
    str(w._pick_attempted_ids),
)
w._tick()
check("T27e: nhảy sang dự bị (20, 2)", fake_lcu.patches[-1] == (20, 2), str(fake_lcu.patches))

# ============ T28: user tự đổi sau khi bot hover → tôn trọng, dừng hẳn ============
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3])
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._tick()
check("T28a: bot hover main (20, 1)", fake_lcu.patches == [(20, 1)], str(fake_lcu.patches))
# User tự đổi sang tướng 4 (không ai giữ tướng 1) → bot dừng
fake_lcu.session = make_session(
    actions=[[BAN_ACTION], [action(20, "pick", champion_id=4)]],
    bans_my=[3],
)
w._tick()
check("T28b: dừng hẳn, không giành lại", w._pick_handled is True and w._pick_picked_id == 0, str((w._pick_handled, w._pick_picked_id)))
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
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3])
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
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[1])
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
# Client chưa biết tên (owned_raises) → fallback "Tướng #id"
reset_state()
w = make_watcher()
fake_lcu.phase = "ChampSelect"
fake_lcu.session = make_session(actions=[[BAN_ACTION], [PICK_ACTION]], bans_my=[3])
fake_lcu.owned_raises = True
fake_config["auto_pick_enabled"] = True
fake_config["arena_pick_chain"] = [1, 2, 0, 0]
w._tick()
check(
    "T30d: chưa biết tên → hiện Tướng #id",
    any(
        text == "Đã chọn: Tướng #1" and color == "green"
        for text, color in ARENA_EVENTS
    ),
    str(ARENA_EVENTS),
)
fake_lcu.owned_raises = False

# ============ KẾT LUẬN ============
print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} test thất bại: {FAILURES}")
    sys.exit(1)
print("ALL TESTS PASSED")

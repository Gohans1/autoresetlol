"""
Test mô phỏng AntiFateBot LCU (v2.0) — accept + dodge detect qua API.

Không cần client LoL thật - mock toàn bộ utils.lcu + config.
Chạy: .venv/Scripts/python.exe _test_bot_lcu.py
"""
import sys
import time
import types
from typing import Optional

# --- Mock utils.lcu TRƯỚC khi import bot ---
class FakeLCU:
    phase: Optional[str] = "Lobby"
    ready_state: Optional[str] = None
    search_active_state: Optional[bool] = False
    accept_ok: bool = True
    accept_calls: int = 0

    def gameflow_phase(self):
        return self.phase

    def search_active(self):
        return self.search_active_state

    def ready_check(self):
        if self.ready_state is None:
            return None
        return {"state": self.ready_state}

    def accept_match(self):
        self.accept_calls += 1
        return self.accept_ok


fake_lcu = FakeLCU()
lcu_module = types.ModuleType("utils.lcu")
setattr(lcu_module, "lcu", fake_lcu)
sys.modules["utils.lcu"] = lcu_module

import bot  # noqa: E402
from config import config_manager  # noqa: E402

# Tests must not pollute the runtime log used for live diagnostics.
bot.logger.disabled = True

# --- Mock config_manager ---
fake_config = {"auto_accept_enabled": True}
config_manager.get = lambda key, default=None: fake_config.get(key, default)
config_manager.set = lambda key, value, save=True: fake_config.__setitem__(key, value)

FAILURES = []
STATUS_LOG = []


def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def make_bot():
    STATUS_LOG.clear()
    fake_lcu.accept_calls = 0
    fake_lcu.accept_ok = True
    fake_lcu.ready_state = None
    fake_lcu.search_active_state = False
    fake_lcu.phase = "Lobby"
    return bot.AntiFateBot(
        update_status_callback=lambda t, c: STATUS_LOG.append((t, c)),
        on_stop_callback=lambda t, c: STATUS_LOG.append((t, c)),
        on_success_callback=lambda: None,
        on_champ_select_callback=lambda: None,
    )


# ============ T1: chưa có trận → chờ, không accept ============
b = make_bot()
b.running = True
b._tick()
check("T1: không có ready-check → 0 accept", fake_lcu.accept_calls == 0, str(fake_lcu.accept_calls))
check(
    "T1: chưa bấm tìm trận → không báo đang tìm trận",
    STATUS_LOG[-1][0] == bot.UIStatus.READY,
    str(STATUS_LOG[-1]),
)

# ============ T1b: LCU xác nhận đang tìm trận ============
b = make_bot()
b.running = True
fake_lcu.search_active_state = True
b._tick()
check("T1b: search.isActive=True → đang tìm trận", STATUS_LOG[-1][0] == bot.UIStatus.SEARCHING, str(STATUS_LOG[-1]))

# ============ T2: có trận → accept → VERIFYING ============
b = make_bot()
b.running = True
fake_lcu.ready_state = "InProgress"
b._tick()
check("T2a: accept đúng 1 lần", fake_lcu.accept_calls == 1, str(fake_lcu.accept_calls))
check("T2b: chuyển sang trạng thái accepting", b._accepting is True)
b._tick()
check("T2c: không accept lần 2 khi đang verify", fake_lcu.accept_calls == 1, str(fake_lcu.accept_calls))

# ============ T3: vào champ select → báo success nhưng vẫn chạy ============
b = make_bot()
b.running = True
fake_lcu.phase = "ChampSelect"
b._tick()
check("T3a: bot vẫn chạy sau Champ Select", b.running is True)
check("T3b: status champ select", STATUS_LOG[-1][0] == bot.UIStatus.CHAMP_SELECT, str(STATUS_LOG[-1]))
champ_select_status_count = sum(1 for text, _ in STATUS_LOG if text == bot.UIStatus.CHAMP_SELECT)
b._tick()
check(
    "T3c: không lặp callback Champ Select mỗi tick",
    sum(1 for text, _ in STATUS_LOG if text == bot.UIStatus.CHAMP_SELECT) == champ_select_status_count,
)

# ============ T4: trong trận → tiếp tục chờ trận kế ============
b = make_bot()
b.running = True
fake_lcu.phase = "InProgress"
b._tick()
check("T4: in game → bot vẫn chạy", b.running is True)
check("T4: status trong trận", STATUS_LOG[-1][0] == bot.UIStatus.IN_GAME, str(STATUS_LOG[-1]))

# ============ T5: dodge sau grace → quay lại chờ, KHÔNG click gì ============
b = make_bot()
b.running = True
fake_lcu.ready_state = "InProgress"
b._tick()  # accept
check("T5a: accept xong", b._accepting is True)
b.verify_start_time = time.time() - (bot.VERIFY_GRACE + 2)  # qua grace
fake_lcu.phase = "Matchmaking"  # quay lại queue = dodge
b._tick()
check("T5b: phát hiện dodge → hết accepting", b._accepting is False)
check("T5c: bot vẫn chạy (chờ accept tiếp)", b.running is True)
check(
    "T5d: status dodge",
    STATUS_LOG[-1][0] == bot.UIStatus.DODGED,
    str(STATUS_LOG[-1]),
)

# ============ T5e: dodge sau Champ Select → nhận trận mới ============
b = make_bot()
b.running = True
fake_lcu.phase = "ChampSelect"
b._tick()
check("T5e: vào Champ Select không dừng bot", b.running is True)
fake_lcu.phase = "Matchmaking"
fake_lcu.ready_state = "InProgress"
b._tick()
check("T5f: dodge sau Champ Select → accept trận mới", fake_lcu.accept_calls == 1, str(fake_lcu.accept_calls))
check("T5g: trận mới chuyển sang verify", b._accepting is True)

# ============ T6: trong grace, phase Matchmaking là BÌNH THƯỜNG ============
b = make_bot()
b.running = True
fake_lcu.ready_state = "InProgress"
b._tick()
b.verify_start_time = time.time() - 1  # chưa qua grace
fake_lcu.phase = "Matchmaking"
b._tick()
check("T6: trong grace → KHÔNG coi là dodge", b._accepting is True, str(b._accepting))

# ============ T7: verify timeout (phase kẹt lạ) → dừng an toàn ============
b = make_bot()
b.running = True
fake_lcu.ready_state = "InProgress"
b._tick()
b.verify_start_time = time.time() - (bot.AppConfig.VERIFY_TIMEOUT + 5)
fake_lcu.phase = "EndOfGame"  # phase không khớp dodge (Matchmaking/Lobby) → timeout
b._tick()
check("T7: timeout → bot dừng", b.running is False)
check("T7: stop status lưu đúng", b._stop_status == ("Verify Timeout", "orange"), str(b._stop_status))

# ============ T8: accept fail → báo lỗi, vẫn chờ ============
b = make_bot()
b.running = True
fake_lcu.ready_state = "InProgress"
fake_lcu.accept_ok = False
b._tick()
check("T8a: accept thất bại → không accepting", b._accepting is False)
check("T8b: status lỗi", "xác nhận" in STATUS_LOG[-1][0], str(STATUS_LOG[-1]))

# ============ T9: auto_accept tắt → không accept ============
b = make_bot()
b.running = True
fake_config["auto_accept_enabled"] = False
fake_lcu.ready_state = "InProgress"
b._tick()
check("T9: toggle tắt → 0 accept", fake_lcu.accept_calls == 0, str(fake_lcu.accept_calls))
fake_config["auto_accept_enabled"] = True

# ============ T10: không kết nối được client → báo lỗi ============
b = make_bot()
b.running = True
fake_lcu.phase = None
b._tick()
check("T10: không kết nối → status đỏ", "kết nối" in STATUS_LOG[-1][0], str(STATUS_LOG[-1]))

# ============ T11: stop callback chỉ phát sau khi worker kết thúc ============
stop_events = []
stop_bot = bot.AntiFateBot(
    update_status_callback=lambda _text, _color: None,
    on_stop_callback=lambda status, color: stop_events.append((status, color)),
)
stop_bot._tick = lambda: setattr(stop_bot, "running", False)
stop_bot.start()
stop_bot.join(timeout=2)
check("T11a: worker đã kết thúc", not stop_bot.is_alive())
check("T11b: callback dừng đúng 1 lần", len(stop_events) == 1, str(stop_events))
check(
    "T11c: callback dừng đúng trạng thái",
    stop_events == [(bot.UIStatus.STOPPED, "gray")],
    str(stop_events),
)

# ============ KẾT LUẬN ============
print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} test thất bại: {FAILURES}")
    sys.exit(1)
print("ALL TESTS PASSED")

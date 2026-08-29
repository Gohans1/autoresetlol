"""Tests for the background Hermes Discord notification sender."""

import threading

import notifications
from notifications import HERMES_SEND_COMMAND, HermesNotifier
from constants import (
    DISCORD_EVENT_BAN,
    DISCORD_EVENT_IN_GAME,
    DISCORD_EVENT_PICK,
    DISCORD_NOTIFICATION_SPECS,
)

notifications.logger.disabled = True


FAILURES = []


def check(name, condition, detail=""):
    tag = "PASS" if condition else "FAIL"
    print(f"[{tag}] {name}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


check(
    "T0: notification registry giữ đủ ba loại",
    [(spec.config_key, spec.event_name) for spec in DISCORD_NOTIFICATION_SPECS]
    == [
        ("discord_notify_ban", DISCORD_EVENT_BAN),
        ("discord_notify_pick", DISCORD_EVENT_PICK),
        ("discord_notify_in_game", DISCORD_EVENT_IN_GAME),
    ],
)


check(
    "T1: dùng hermes send tới Discord home channel",
    HERMES_SEND_COMMAND == ("hermes", "send", "--to", "discord", "--quiet"),
    str(HERMES_SEND_COMMAND),
)

# ============ T1b: Hermes subprocess dùng UTF-8 và không bật console phụ ============
captured_run = {}
original_popen = notifications.subprocess.Popen


class FakeProcess:
    returncode = 0

    def communicate(self, input=None, timeout=None):
        captured_run["input"] = input
        captured_run["timeout"] = timeout
        return "", ""

    def poll(self):
        return self.returncode

    def terminate(self):
        return None

    def kill(self):
        return None


def fake_subprocess_popen(command, **kwargs):
    captured_run["command"] = command
    captured_run["kwargs"] = kwargs
    return FakeProcess()


notifications.subprocess.Popen = fake_subprocess_popen
try:
    check(
        "T1b: Hermes send runner chạy được",
        notifications._run_hermes_send("Đã chọn tướng"),
    )
finally:
    notifications.subprocess.Popen = original_popen

if hasattr(notifications.subprocess, "CREATE_NO_WINDOW"):
    check(
        "T1c: không mở console phụ trên Windows",
        captured_run["kwargs"].get("creationflags")
        == notifications.subprocess.CREATE_NO_WINDOW,
        str(captured_run),
    )
check(
    "T1d: message Unicode dùng UTF-8",
    captured_run["kwargs"].get("encoding") == "utf-8",
    str(captured_run),
)
check(
    "T1e: giữ nguyên message Unicode",
    captured_run["input"] == "Đã chọn tướng",
    str(captured_run),
)

# ============ T2: retry hữu hạn rồi thành công ============
calls = []
sent = threading.Event()


def retry_runner(message):
    calls.append(message)
    if len(calls) == 3:
        sent.set()
        return True
    return False


notifier = HermesNotifier(
    runner=retry_runner,
    max_retries=3,
    retry_delay=0,
)
check("T2a: đưa event vào queue không block", notifier.notify("test.retry", "hello"))
check("T2b: retry rồi gửi thành công", sent.wait(2), str(calls))
check("T2c: đúng 3 lần thử", calls == ["hello", "hello", "hello"], str(calls))
notifier.close()

# ============ T2d: runner lỗi không làm chết worker ============
exception_calls = []
exception_done = threading.Event()


def exception_runner(_message):
    exception_calls.append(True)
    if len(exception_calls) == 2:
        exception_done.set()
    raise RuntimeError("fake sender failure")


notifier = HermesNotifier(
    runner=exception_runner,
    max_retries=2,
    retry_delay=0,
)
notifier.notify("test.exception", "ignored")
check("T2d: runner exception vẫn retry hữu hạn", exception_done.wait(2))
check("T2e: exception retry đúng số lần", len(exception_calls) == 2, str(exception_calls))
notifier.close()

# ============ T3: dedup key chặn event trùng ============
calls = []
sent = threading.Event()


def dedupe_runner(message):
    calls.append(message)
    sent.set()
    return True


notifier = HermesNotifier(runner=dedupe_runner, retry_delay=0)
check(
    "T3a: event đầu được nhận",
    notifier.notify("test.dedupe", "first", dedupe_key="session:1"),
)
check(
    "T3b: event trùng bị bỏ qua",
    not notifier.notify("test.dedupe", "duplicate", dedupe_key="session:1"),
)
check("T3c: chỉ gửi một lần", sent.wait(2) and calls == ["first"], str(calls))
notifier.close()

# ============ T3d: tắt event loại bỏ cả event đang chờ ============
filter_calls = []
active_started = threading.Event()
active_finished = threading.Event()
release_active = threading.Event()


def filter_runner(message):
    filter_calls.append(message)
    active_started.set()
    release_active.wait(2)
    active_finished.set()
    return True


notifier = HermesNotifier(runner=filter_runner, retry_delay=0, queue_size=4)
notifier.notify("test.filter", "active")
check("T3d1: event đang chạy", active_started.wait(2))
notifier.notify("test.filter", "pending")
notifier.set_event_enabled("test.filter", False)
release_active.set()
check("T3d2: event đang chạy kết thúc", active_finished.wait(2))
notifier.close()
check("T3d: tắt event chặn event mới", not notifier.notify("test.filter", "off"))
check("T3e: tắt event bỏ event đang chờ", filter_calls == ["active"], str(filter_calls))

notifier = HermesNotifier(runner=lambda _message: True, retry_delay=0)
notifier.set_event_enabled("test.reenable", False)
check(
    "T3f: event tắt không được queue",
    not notifier.notify("test.reenable", "blocked", dedupe_key="same"),
)
notifier.set_event_enabled("test.reenable", True)
check(
    "T3g: bật lại cho phép queue lại",
    notifier.notify("test.reenable", "allowed", dedupe_key="same"),
)
notifier.close()

# ============ T4: close chặn event mới ============
notifier = HermesNotifier(runner=lambda _message: True, retry_delay=0)
notifier.close()
check("T4: sau close không nhận event", not notifier.notify("test.closed", "ignored"))

# ============ T4b: close không bị kẹt trong retry delay ============
retry_started = threading.Event()


def always_fail_runner(_message):
    retry_started.set()
    return False


notifier = HermesNotifier(
    runner=always_fail_runner,
    max_retries=3,
    retry_delay=1,
)
notifier.notify("test.shutdown", "ignored")
check("T4b1: retry worker đã chạy", retry_started.wait(2))
notifier.close(timeout=0.1)
check("T4b: close dừng worker đang retry", not notifier._thread.is_alive())

# ============ T4c: close trong runner lỗi, retry_delay=0 ============
zero_delay_calls = []
zero_delay_started = threading.Event()
zero_delay_release = threading.Event()


def zero_delay_fail_runner(message):
    zero_delay_calls.append(message)
    zero_delay_started.set()
    zero_delay_release.wait(2)
    return False


notifier = HermesNotifier(
    runner=zero_delay_fail_runner,
    max_retries=4,
    retry_delay=0,
)
notifier.notify("test.shutdown.zero", "ignored")
check("T4c1: runner retry không delay đã chạy", zero_delay_started.wait(2))
notifier.close(timeout=0.1)
zero_delay_release.set()
notifier._thread.join(timeout=2)
check(
    "T4c2: worker kết thúc sau runner release",
    not notifier._thread.is_alive(),
)
check(
    "T4c3: close chặn retry dù retry_delay=0",
    zero_delay_calls == ["ignored"],
    str(zero_delay_calls),
)

# ============ KẾT LUẬN ============
notifications.logger.disabled = True
if FAILURES:
    print(f"\nFAILED: {', '.join(FAILURES)}")
    raise SystemExit(1)
print("\nALL TESTS PASSED")

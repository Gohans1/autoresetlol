"""Regression checks for bounded Arena roster reload work."""
from __future__ import annotations

import threading

import gui_arena
import gui_status
from gui import AntiFateApp

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    tag = "PASS" if condition else "FAIL"
    print(f"[{tag}] {name}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


class FakeThread:
    created: list["FakeThread"] = []
    started: list["FakeThread"] = []

    def __init__(self, target, args=(), daemon=False):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.join_calls: list[float | None] = []
        self.created.append(self)

    def start(self) -> None:
        self.started.append(self)

    def is_alive(self) -> bool:
        return self in self.started and not self.join_calls

    def join(self, timeout=None) -> None:
        self.join_calls.append(timeout)


def test_reload_coalesces_in_flight_fetches() -> None:
    app = AntiFateApp.__new__(AntiFateApp)
    app._arena_fetch_gen = 0
    app._arena_fetch_lock = threading.Lock()
    app._arena_fetch_thread = None
    app._arena_fetch_pending = False
    app._arena_fetch_cancel = threading.Event()
    app._arena_roster_loading = False
    app._arena_roster_error = False
    app._refresh_arena_validation = lambda: None
    original_thread = gui_arena.threading.Thread
    FakeThread.created = []
    FakeThread.started = []
    gui_arena.threading.Thread = FakeThread
    try:
        app._reload_owned_champions()
        app._reload_owned_champions()
    finally:
        gui_arena.threading.Thread = original_thread
    check(
        "T1: reload chồng nhau chỉ chạy một fetch",
        len(FakeThread.started) == 1,
        str(len(FakeThread.started)),
    )


def test_stop_cancels_and_joins_roster_fetch() -> None:
    app = AntiFateApp.__new__(AntiFateApp)
    app._arena_fetch_lock = threading.Lock()
    app._arena_fetch_cancel = threading.Event()
    app._arena_fetch_pending = True
    thread = FakeThread(lambda: None)
    app._arena_fetch_thread = thread
    gui_arena.ArenaUiMixin._stop_arena_roster_fetch(app)
    check(
        "T2: teardown hủy và join roster fetch",
        app._arena_fetch_cancel.is_set()
        and app._arena_fetch_pending is False
        and thread.join_calls == [1.0],
        str((app._arena_fetch_cancel.is_set(), app._arena_fetch_pending, thread.join_calls)),
    )


def test_initial_roster_reload_is_deferred() -> None:
    app = AntiFateApp.__new__(AntiFateApp)
    callbacks = []
    app.after_idle = lambda callback: callbacks.append(callback) or "idle-id"
    app._arena_roster_reload_after_id = None
    schedule = getattr(
        gui_arena.ArenaUiMixin,
        "_schedule_initial_arena_roster_reload",
        None,
    )
    if schedule is not None:
        schedule(app)
    check(
        "T3: roster đầu tiên chờ mainloop",
        len(callbacks) == 1
        and app._arena_roster_reload_after_id == "idle-id",
        str((callbacks, app._arena_roster_reload_after_id)),
    )


def test_failed_roster_post_retries_on_connection() -> None:
    app = AntiFateApp.__new__(AntiFateApp)
    app._arena_fetch_lock = threading.Lock()
    app._arena_fetch_thread = None
    app._arena_fetch_pending = False
    app._arena_fetch_cancel = threading.Event()
    app._arena_fetch_gen = 1
    app._arena_roster_loading = True
    app._arena_roster_error = False
    app._arena_roster_known = False
    app._arena_client_connected = False
    app._refresh_arena_validation = lambda: None
    app._set_arena_client_status = lambda _connected: None
    app.after = lambda _delay, callback: callback()
    reload_calls = []
    app._reload_owned_champions = lambda: reload_calls.append(True)
    post_calls = [0]

    def post_to_ui(callback, *args):
        post_calls[0] += 1
        if post_calls[0] == 1:
            return False
        callback(*args)
        return True

    app._post_to_ui = post_to_ui
    original_phase = gui_arena.lcu.gameflow_phase
    original_owned = gui_arena.lcu.owned_champions_result
    gui_arena.lcu.gameflow_phase = lambda: "ChampSelect"
    gui_arena.lcu.owned_champions_result = lambda: [{"id": 1, "name": "Aatrox"}]
    try:
        gui_arena.ArenaUiMixin._load_owned_champions(app, 1)
        gui_arena.ArenaUiMixin._on_arena_connection_changed(app, True)
    finally:
        gui_arena.lcu.gameflow_phase = original_phase
        gui_arena.lcu.owned_champions_result = original_owned
    check(
        "T4: post roster lỗi vẫn reload khi connection tới",
        app._arena_roster_loading is False and reload_calls == [True],
        str((app._arena_roster_loading, reload_calls, post_calls[0])),
    )


def test_watcher_roster_update_clears_stale_ui_error() -> None:
    app = AntiFateApp.__new__(AntiFateApp)
    app._arena_fetch_gen = 4
    app._arena_client_connected = True
    app._arena_roster_known = False
    app._arena_roster_loading = False
    app._arena_roster_error = True
    app._arena_owned = []
    app._arena_owned_ids = set()
    app._arena_cached_names = {}
    app._arena_loaded_ids = {}
    app._arena_display_to_id = {}
    app._arena_display_to_id_normalized = {}
    app.arena_combos = {}
    setattr(app, "_set_arena_client_status", lambda connected: None)
    setattr(app, "_refresh_arena_validation", lambda force_errors=False: [])
    setattr(app, "_save_arena_champion_names", lambda save=True: True)

    gui_arena.ArenaUiMixin._on_arena_roster_update(
        app,
        [{"id": 1, "name": "Aatrox"}],
    )
    check(
        "T5: watcher roster mới xóa lỗi roster giao diện",
        app._arena_roster_known
        and app._arena_roster_loading is False
        and app._arena_roster_error is False
        and app._arena_owned_ids == {1},
        str(
            (
                app._arena_roster_known,
                app._arena_roster_loading,
                app._arena_roster_error,
                app._arena_owned_ids,
            )
        ),
    )


def test_chained_ui_callbacks_stop_after_shutdown() -> None:
    app = AntiFateApp.__new__(AntiFateApp)
    app._ui_callbacks_enabled = False
    app.after_calls = []
    app.after = lambda *args: app.after_calls.append(args)
    app._arena_roster_known = False
    app._arena_roster_loading = False
    app._set_arena_client_status = lambda _connected: None
    app._refresh_arena_validation = lambda: None
    reload_calls = []
    app._reload_owned_champions = lambda: reload_calls.append(True)
    gui_arena.ArenaUiMixin._on_arena_connection_changed(app, True)
    check(
        "T5: connection callback bị chặn sau shutdown",
        app.after_calls == [] and reload_calls == [],
        str((app.after_calls, reload_calls)),
    )

    app.after_calls = []
    gui_status.StatusUiMixin.on_bot_stop(app, "stopped", "gray")
    check(
        "T6: bot callback bị chặn sau shutdown",
        app.after_calls == [],
        str(app.after_calls),
    )

    app.after_calls = []
    gui_status.StatusUiMixin.update_status(app, "status", "gray")
    gui_status.StatusUiMixin.update_arena_live(app, "arena", "gray")
    check(
        "T7: status callback bị chặn sau shutdown",
        app.after_calls == [],
        str(app.after_calls),
    )


test_reload_coalesces_in_flight_fetches()
test_stop_cancels_and_joins_roster_fetch()
test_initial_roster_reload_is_deferred()
test_failed_roster_post_retries_on_connection()
test_watcher_roster_update_clears_stale_ui_error()
test_chained_ui_callbacks_stop_after_shutdown()

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} test thất bại: {FAILURES}")
    raise SystemExit(1)
print("ALL TESTS PASSED")

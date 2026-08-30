"""Regression check for the hidden CustomTkinter startup window bug."""

import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "gui.py"


class ToggleVariable:
    def __init__(self, value: bool) -> None:
        self.value = value

    def get(self) -> bool:
        return self.value

    def set(self, value: bool) -> None:
        self.value = value


class FakeNotifier:
    def __init__(self) -> None:
        self.events: list[tuple[str, bool]] = []

    def set_event_enabled(self, event_name: str, enabled: bool) -> None:
        self.events.append((event_name, enabled))


class FakeCombo:
    def __init__(self, value: str) -> None:
        self.value = value
        self.configurations: list[dict[str, object]] = []

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value

    def configure(self, **kwargs: object) -> None:
        self.configurations.append(kwargs)


def call_name(node: ast.Call) -> str:
    parts = []
    value = node.func
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if isinstance(value, ast.Name):
        parts.append(value.id)
    return ".".join(reversed(parts))


def test_failed_feature_toggles_restore_runtime_state() -> None:
    import gui

    app = gui.AntiFateApp.__new__(gui.AntiFateApp)
    app.auto_ban_var = ToggleVariable(True)
    app.auto_pick_var = ToggleVariable(True)
    app.auto_accept_enabled_var = ToggleVariable(True)
    app.auto_dimmer_switch_var = ToggleVariable(True)
    app.discord_notify_ban_var = ToggleVariable(True)
    app.notifier = FakeNotifier()
    app._refresh_arena_field_visibility = lambda: None
    app._refresh_arena_validation = lambda: None
    config = {
        "auto_ban_enabled": False,
        "auto_pick_enabled": False,
        "auto_accept_enabled": False,
        "auto_dimmer_switch_enabled": False,
        "discord_notify_ban": False,
    }
    original_get = gui.config_manager.get
    original_set = gui.config_manager.set
    try:
        gui.config_manager.get = lambda key, default=None: config.get(key, default)
        gui.config_manager.set = lambda *_args, **_kwargs: False

        app._on_auto_ban_toggle()
        app._on_auto_pick_toggle()
        app.toggle_auto_accept()
        app._toggle_auto_dimmer_switch()
        app._toggle_discord_notification(
            gui.DISCORD_NOTIFICATION_SPECS[0], app.discord_notify_ban_var
        )
    finally:
        gui.config_manager.get = original_get
        gui.config_manager.set = original_set

    assert app.auto_ban_var.get() is False
    assert app.auto_pick_var.get() is False
    assert app.auto_accept_enabled_var.get() is False
    assert app.auto_dimmer_switch_var.get() is False
    assert app.discord_notify_ban_var.get() is False
    assert app.notifier.events[-1] == (
        gui.DISCORD_NOTIFICATION_SPECS[0].event_name,
        False,
    )


def test_failed_arena_selection_save_stays_dirty_for_retry() -> None:
    import gui

    app = gui.AntiFateApp.__new__(gui.AntiFateApp)
    app.arena_combos = {"main": FakeCombo("Aatrox")}
    app._arena_display_to_id_normalized = {"aatrox": 1}
    app._arena_id_to_display = {1: "Aatrox"}
    app._arena_cached_names = {}
    app._arena_owned = []
    app._arena_recent = {"main": []}
    app._arena_loaded_ids = {"main": 0}
    app._arena_draft_keys = set()
    app._arena_field_error_visible = {"main": False}
    app._arena_save_dirty = False
    app._refresh_arena_validation = lambda: []
    config = {
        "arena_pick_chain": [0, 0, 0, 0],
        "arena_champion_names": {},
        "arena_recent": {"main": []},
    }
    save_results = iter([False, True])
    save_calls: list[bool] = []
    original_get = gui.config_manager.get
    original_set = gui.config_manager.set
    original_save = gui.config_manager.save_config
    try:
        gui.config_manager.get = lambda key, default=None: config.get(key, default)

        def set_config(key, value, save=True):
            config[key] = value
            return True

        def save_config() -> bool:
            save_calls.append(True)
            return next(save_results)

        gui.config_manager.set = set_config
        gui.config_manager.save_config = save_config
        app._on_arena_combo("main")
        assert app._arena_save_dirty is True
        assert save_calls == [True]
        app._flush_pending_arena_save()
    finally:
        gui.config_manager.get = original_get
        gui.config_manager.set = original_set
        gui.config_manager.save_config = original_save

    assert save_calls == [True, True]
    assert app._arena_save_dirty is False
    assert config["arena_pick_chain"][0] == 1


def test_startup_lifecycle_reveals_window_before_watcher_start() -> None:
    import gui

    events: list[str] = []
    app = SimpleNamespace(
        update=lambda: events.append("update"),
        deiconify=lambda: events.append("deiconify"),
        arena_watcher=SimpleNamespace(
            start=lambda: events.append("watcher.start")
        ),
    )

    gui.AntiFateApp._show_ready_window(app)

    assert events == ["update", "deiconify", "watcher.start"]


def test_mutex_creation_failure_is_not_single_instance() -> None:
    import ctypes
    import main as app_main

    if not hasattr(ctypes, "WinDLL"):
        return

    last_error = [5]

    class FakeFunction:
        def __init__(self, callback):
            self.callback = callback

        def __call__(self, *args):
            return self.callback(*args)

    class FakeKernel:
        def __init__(self):
            self.CreateMutexW = FakeFunction(self._create_mutex)
            self.CloseHandle = FakeFunction(lambda _handle: 1)

        def _create_mutex(self, *_args):
            last_error[0] = 5
            return None

    kernel = FakeKernel()
    original_win_dll = ctypes.WinDLL
    original_get_last_error = ctypes.get_last_error
    original_set_last_error = ctypes.set_last_error
    original_argv = app_main.sys.argv
    original_mutex = app_main._SINGLE_INSTANCE_MUTEX
    try:
        ctypes.WinDLL = lambda *_args, **_kwargs: kernel
        ctypes.get_last_error = lambda: last_error[0]
        ctypes.set_last_error = lambda value: last_error.__setitem__(0, value)
        app_main.sys.argv = ["main.py"]
        app_main._SINGLE_INSTANCE_MUTEX = None
        assert app_main._enforce_single_instance() is False
        assert app_main._SINGLE_INSTANCE_MUTEX is None
    finally:
        ctypes.WinDLL = original_win_dll
        ctypes.get_last_error = original_get_last_error
        ctypes.set_last_error = original_set_last_error
        app_main.sys.argv = original_argv
        app_main._SINGLE_INSTANCE_MUTEX = original_mutex


def test_startup_exception_returns_nonzero() -> None:
    import main as app_main

    messages: list[tuple[str, dict[str, object]]] = []
    original_main = app_main.main
    original_critical = app_main.logger.critical

    def fail_main() -> None:
        raise RuntimeError("startup failed")

    try:
        app_main.main = fail_main
        app_main.logger.critical = lambda message, **kwargs: messages.append(
            (message, kwargs)
        )
        assert app_main._run() == 1
    finally:
        app_main.main = original_main
        app_main.logger.critical = original_critical

    assert messages == [
        ("Critical Application Error: startup failed", {"exc_info": True})
    ]


def test_restart_retries_mutex_until_previous_instance_exits() -> None:
    import ctypes
    import time
    import main as app_main

    last_error = [183]
    attempts: list[int] = []
    closed: list[int] = []
    sleeps: list[float] = []

    class FakeFunction:
        def __init__(self, callback):
            self.callback = callback

        def __call__(self, *args):
            return self.callback(*args)

    class FakeKernel:
        def __init__(self):
            self.CreateMutexW = FakeFunction(self._create_mutex)
            self.CloseHandle = FakeFunction(
                lambda handle: closed.append(handle) or 1
            )

        def _create_mutex(self, *_args):
            attempts.append(len(attempts) + 1)
            if len(attempts) == 1:
                last_error[0] = 183
                return 1
            last_error[0] = 0
            return 2

    kernel = FakeKernel()
    original_win_dll = ctypes.WinDLL
    original_get_last_error = ctypes.get_last_error
    original_set_last_error = ctypes.set_last_error
    original_sleep = time.sleep
    original_argv = app_main.sys.argv
    original_mutex = app_main._SINGLE_INSTANCE_MUTEX
    try:
        ctypes.WinDLL = lambda *_args, **_kwargs: kernel
        ctypes.get_last_error = lambda: last_error[0]
        ctypes.set_last_error = lambda value: last_error.__setitem__(0, value)
        time.sleep = lambda delay: sleeps.append(delay)
        app_main.sys.argv = ["main.py", "--restart"]
        app_main._SINGLE_INSTANCE_MUTEX = None
        assert app_main._enforce_single_instance() is True
        assert app_main._SINGLE_INSTANCE_MUTEX == 2
    finally:
        ctypes.WinDLL = original_win_dll
        ctypes.get_last_error = original_get_last_error
        ctypes.set_last_error = original_set_last_error
        time.sleep = original_sleep
        app_main.sys.argv = original_argv
        app_main._SINGLE_INSTANCE_MUTEX = original_mutex

    assert attempts == [1, 2]
    assert closed == [1]
    assert sleeps == [0.5]


def test_native_scroll_uses_os_lines_as_canvas_units() -> None:
    import gui

    scroll_calls: list[tuple[int, str]] = []

    class FakeCanvas:
        def yview_scroll(self, amount: int, units: str) -> None:
            scroll_calls.append((amount, units))

    class FakeScrollable:
        def __init__(self) -> None:
            self._parent_canvas = FakeCanvas()
            self.handler = None

        def bind(self, _event_name: str, handler) -> None:
            self.handler = handler

        def winfo_children(self) -> list[object]:
            return []

        def after(self, _delay: int, _callback) -> None:
            return None

    app = gui.AntiFateApp.__new__(gui.AntiFateApp)
    app._get_os_scroll_lines = lambda: 3
    app._on_suggest_scroll = lambda _event: None
    scrollable = FakeScrollable()
    gui.AntiFateApp._setup_native_scroll_speed(app, scrollable)

    scrollable.handler(SimpleNamespace(delta=120))

    assert scroll_calls == [(-3, "units")]


def test_partial_initialization_closes_runtime_resources() -> None:
    import gui

    class Closeable:
        def __init__(self, name: str) -> None:
            self.name = name
            self.closed = False

        def close(self) -> None:
            self.closed = True

        def stop(self) -> None:
            self.closed = True

    app = gui.AntiFateApp.__new__(gui.AntiFateApp)
    app.bot = None
    app.dimmer = Closeable("dimmer")
    app.notifier = Closeable("notifier")
    app.arena_watcher = Closeable("watcher")
    app._set_arena_automation_enabled = lambda _enabled: None

    app._cleanup_partial_initialization()

    assert app.dimmer.closed
    assert app.notifier.closed
    assert app.arena_watcher.closed


def main() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    app_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "AntiFateApp"
    )
    mixin_classes = []
    for path in (
        ROOT / "gui_arena.py",
        ROOT / "gui_arena_suggestions.py",
        ROOT / "gui_dimmer.py",
        ROOT / "gui_lifecycle.py",
        ROOT / "gui_status.py",
    ):
        mixin_tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        mixin_classes.extend(
            node for node in mixin_tree.body if isinstance(node, ast.ClassDef)
        )
    all_classes = [app_class, *mixin_classes]
    constructor = next(
        node
        for node in app_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    constructor_calls = {
        call_name(node)
        for node in ast.walk(constructor)
        if isinstance(node, ast.Call)
    }
    assert "self._initialize" in constructor_calls
    init = next(
        node
        for node in app_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "_initialize"
    )
    calls = [
        (index, call_name(node.value))
        for index, node in enumerate(init.body)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
    ]
    positions = {name: index for index, name in calls}

    required = ("self._show_ready_window",)
    missing = [name for name in required if name not in positions]
    assert not missing, f"missing startup calls: {missing}"
    assert "self.deiconify" not in positions
    assert "self.arena_watcher.start" not in positions

    def method_calls(name: str) -> set[str]:
        method = next(
            node
            for app_type in all_classes
            for node in app_type.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
        return {
            call_name(node)
            for node in ast.walk(method)
            if isinstance(node, ast.Call)
        }

    ready_method = next(
        node
        for node in app_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "_show_ready_window"
    )
    ready_calls = [
        call_name(node.value)
        for node in ready_method.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
    ]
    assert ready_calls == [
        "self.update",
        "self.deiconify",
        "self.arena_watcher.start",
    ]

    assert "normalize_ui_scale" in method_calls("_create_ui_scale_widget")
    assert "normalize_ui_scale" in method_calls("_refresh_arena_validation")
    assert "normalize_ui_scale" in method_calls("_render_arena_live")
    restart_method = next(
        node
        for app_type in all_classes
        for node in app_type.body
        if isinstance(node, ast.FunctionDef) and node.name == "_restart_app"
    )
    restart_attributes = {
        node.attr
        for node in ast.walk(restart_method)
        if isinstance(node, ast.Attribute)
    }
    assert "_flush_pending_dimmer_save" in restart_attributes
    import gui

    app = gui.AntiFateApp.__new__(gui.AntiFateApp)
    app.scale_dropdown = SimpleNamespace(set=lambda value: setattr(app, "scale_value", value))
    app.scale_value = "125%"
    app.restarted = False
    app._restart_app = lambda: setattr(app, "restarted", True)
    original_get = gui.config_manager.get
    original_set = gui.config_manager.set
    original_ask = gui.messagebox.askyesno
    try:
        gui.config_manager.get = lambda _key: 1.25
        gui.config_manager.set = lambda *_args, **_kwargs: False
        gui.messagebox.askyesno = lambda *_args, **_kwargs: True
        app._on_scale_changed("150%")
        assert not getattr(app, "restarted", False)
        assert app.scale_value == "125%"
    finally:
        gui.config_manager.get = original_get
        gui.config_manager.set = original_set
        gui.messagebox.askyesno = original_ask
    test_failed_feature_toggles_restore_runtime_state()
    test_failed_arena_selection_save_stays_dirty_for_retry()
    test_startup_lifecycle_reveals_window_before_watcher_start()
    test_mutex_creation_failure_is_not_single_instance()
    test_startup_exception_returns_nonzero()
    test_restart_retries_mutex_until_previous_instance_exits()
    test_native_scroll_uses_os_lines_as_canvas_units()
    test_partial_initialization_closes_runtime_resources()
    print("startup visibility order: PASS")
    print("startup safety helpers: PASS")
    print("toggle save rollback: PASS")
    print("Arena save retry: PASS")


if __name__ == "__main__":
    main()

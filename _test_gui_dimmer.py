"""Regression checks for the dimmer settings save path."""

from __future__ import annotations

import gui
import subprocess
from types import SimpleNamespace


class FakeVariable:
    def __init__(self, value: bool) -> None:
        self.value = value

    def get(self) -> bool:
        return self.value


class FakeDimmer:
    def __init__(self) -> None:
        self.values: list[int] = []

    def set_brightness(self, value: int) -> None:
        self.values.append(value)


class FakeSlider:
    def __init__(self, value: float) -> None:
        self.value = value
        self.configurations: list[dict[str, object]] = []

    def get(self) -> float:
        return self.value

    def set(self, value: float) -> None:
        self.value = value

    def configure(self, **kwargs: object) -> None:
        self.configurations.append(kwargs)


def test_brightness_save_is_debounced() -> None:
    app = gui.AntiFateApp.__new__(gui.AntiFateApp)
    app.dimmer_enabled_var = FakeVariable(True)
    app.dimmer = FakeDimmer()
    app._dimmer_reset_visual = True
    app._dimmer_save_after_id = None
    scheduled: list[tuple[int, object]] = []
    cancelled: list[object] = []
    saves: list[bool] = []
    config_writes: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def after(delay: int, callback: object) -> str:
        timer_id = f"timer-{len(scheduled) + 1}"
        scheduled.append((delay, callback))
        return timer_id

    app.after = after
    app.after_cancel = lambda timer_id: cancelled.append(timer_id)

    original_set = gui.config_manager.set
    original_get = gui.config_manager.get
    original_save = gui.config_manager.save_config
    try:
        gui.config_manager.set = lambda *args, **kwargs: config_writes.append(
            (args, kwargs)
        )
        gui.config_manager.get = lambda key, default=None: {
            "dimmer_mode": "browsing",
            "dimmer_gaming_value": 100,
            "dimmer_browsing_value": 70,
        }.get(key, default)
        gui.config_manager.save_config = lambda: saves.append(True) or True

        app.change_brightness(60)
        app.change_brightness(55)

        assert saves == []
        assert cancelled == ["timer-1"]
        assert scheduled[-1][0] == 250
        assert app.dimmer.values == [60, 55]
        assert (("dimmer_value", 55), {"save": False}) in config_writes
        assert (("dimmer_browsing_value", 55), {"save": False}) in config_writes

        callback = scheduled[-1][1]
        callback()
        assert saves == [True]
    finally:
        gui.config_manager.set = original_set
        gui.config_manager.get = original_get
        gui.config_manager.save_config = original_save


def test_failed_debounced_save_stays_dirty_for_later_retry() -> None:
    app = gui.AntiFateApp.__new__(gui.AntiFateApp)
    app.dimmer_enabled_var = FakeVariable(True)
    app.dimmer = FakeDimmer()
    app._dimmer_reset_visual = False
    app._dimmer_save_after_id = None
    scheduled: list[tuple[int, object]] = []
    cancelled: list[object] = []
    save_results = iter([False, True])
    saves: list[bool] = []
    app.after = lambda delay, callback: scheduled.append((delay, callback)) or "timer-1"
    app.after_cancel = lambda timer_id: cancelled.append(timer_id)

    original_set = gui.config_manager.set
    original_get = gui.config_manager.get
    original_save = gui.config_manager.save_config
    try:
        gui.config_manager.set = lambda *args, **kwargs: None
        gui.config_manager.get = lambda key, default=None: {
            "dimmer_mode": "browsing",
        }.get(key, default)

        def save_config() -> bool:
            saves.append(True)
            return next(save_results)

        gui.config_manager.save_config = save_config
        app.change_brightness(55)
        scheduled[-1][1]()
        assert saves == [True]
        assert app._dimmer_save_dirty is True
        assert app._dimmer_save_after_id is None

        app._flush_pending_dimmer_save()
        assert saves == [True, True]
        assert app._dimmer_save_dirty is False
    finally:
        gui.config_manager.set = original_set
        gui.config_manager.get = original_get
        gui.config_manager.save_config = original_save


def test_automatic_mode_save_failure_is_not_reported_as_saved() -> None:
    app = gui.AntiFateApp.__new__(gui.AntiFateApp)
    app.dimmer_enabled_var = FakeVariable(True)
    app.dimmer = FakeDimmer()
    app._dimmer_save_dirty = False
    app._skip_dimmer_save = False
    app._dimmer_reset_visual = False
    app.after = lambda delay, callback: "timer-1"
    config = {
        "auto_dimmer_switch_enabled": True,
        "dimmer_mode": "browsing",
        "dimmer_browsing_value": 70,
        "dimmer_gaming_value": 90,
    }
    infos: list[str] = []

    original_set = gui.config_manager.set
    original_get = gui.config_manager.get
    original_save = gui.config_manager.save_config
    original_info = gui.logger.info
    try:
        gui.config_manager.set = lambda key, value, save=True: (
            config.__setitem__(key, value) or True
        )
        gui.config_manager.get = lambda key, default=None: config.get(key, default)
        gui.config_manager.save_config = lambda: False
        gui.logger.info = lambda message: infos.append(message)

        app.switch_to_gaming_mode()
        assert app._dimmer_save_dirty is True
        assert not any(
            message.startswith("Saved browsing dimmer value") for message in infos
        )
    finally:
        gui.config_manager.set = original_set
        gui.config_manager.get = original_get
        gui.config_manager.save_config = original_save
        gui.logger.info = original_info


def test_mode_save_failure_stays_dirty_for_later_retry() -> None:
    app = gui.AntiFateApp.__new__(gui.AntiFateApp)
    app.dimmer_enabled_var = FakeVariable(True)
    app.dimmer = FakeDimmer()
    app.dimmer_slider = FakeSlider(70)
    app._skip_dimmer_save = False
    app._dimmer_reset_visual = False
    app._dimmer_save_after_id = None
    app.after = lambda delay, callback: "timer-1"
    config = {
        "dimmer_mode": "browsing",
        "dimmer_browsing_value": 70,
        "dimmer_gaming_value": 90,
        "dimmer_value": 70,
    }
    saves = iter([False, True])
    save_calls: list[bool] = []

    original_set = gui.config_manager.set
    original_get = gui.config_manager.get
    original_save = gui.config_manager.save_config
    try:
        def set_config(key, value, save=True):
            if save:
                return False
            config[key] = value
            return True

        gui.config_manager.set = set_config
        gui.config_manager.get = lambda key, default=None: config.get(key, default)

        def save_config() -> bool:
            save_calls.append(True)
            return next(saves)

        gui.config_manager.save_config = save_config
        app._on_dimmer_mode_changed("🎮 Gaming")
        assert config["dimmer_mode"] == "gaming"
        assert app.dimmer_slider.value == 90
        assert app.dimmer.values == [90]
        assert app._dimmer_save_dirty is True
        assert save_calls == [True]

        app._flush_pending_dimmer_save()
        assert save_calls == [True, True]
        assert app._dimmer_save_dirty is False
    finally:
        gui.config_manager.set = original_set
        gui.config_manager.get = original_get
        gui.config_manager.save_config = original_save


def test_gaming_brightness_updates_gaming_value() -> None:
    app = gui.AntiFateApp.__new__(gui.AntiFateApp)
    app.dimmer_enabled_var = FakeVariable(True)
    app.dimmer = FakeDimmer()
    app._dimmer_reset_visual = False
    app._dimmer_save_after_id = None
    scheduled: list[tuple[int, object]] = []
    app.after = lambda delay, callback: scheduled.append((delay, callback)) or "timer-1"

    original_set = gui.config_manager.set
    original_get = gui.config_manager.get
    writes: list[tuple[tuple[object, ...], dict[str, object]]] = []
    try:
        gui.config_manager.set = lambda *args, **kwargs: writes.append((args, kwargs))
        gui.config_manager.get = lambda key, default=None: {
            "dimmer_mode": "gaming",
            "dimmer_gaming_value": 90,
            "dimmer_browsing_value": 70,
        }.get(key, default)
        app.change_brightness(64)
        assert (("dimmer_value", 64), {"save": False}) in writes
        assert (("dimmer_gaming_value", 64), {"save": False}) in writes
        assert scheduled
    finally:
        gui.config_manager.set = original_set
        gui.config_manager.get = original_get


def test_toggle_save_failure_stays_dirty_for_later_retry() -> None:
    app = gui.AntiFateApp.__new__(gui.AntiFateApp)
    app.dimmer_enabled_var = FakeVariable(False)
    app.dimmer = FakeDimmer()
    app.dimmer_slider = FakeSlider(70)
    app._dimmer_save_after_id = None
    app._dimmer_save_dirty = False
    config = {"dimmer_enabled": True}
    saves = iter([False, True])
    save_calls: list[bool] = []

    original_set = gui.config_manager.set
    original_get = gui.config_manager.get
    original_save = gui.config_manager.save_config
    try:
        def set_config(key, value, save=True):
            if save:
                return False
            config[key] = value
            return True

        gui.config_manager.set = set_config
        gui.config_manager.get = lambda key, default=None: config.get(key, default)

        def save_config() -> bool:
            save_calls.append(True)
            return next(saves)

        gui.config_manager.save_config = save_config
        app.toggle_dimmer()
        assert config["dimmer_enabled"] is False
        assert app.dimmer.values == [100]
        assert app.dimmer_slider.configurations[-1]["state"] == "disabled"
        assert app._dimmer_save_dirty is True
        assert save_calls == [True]

        app._flush_pending_dimmer_save()
        assert save_calls == [True, True]
        assert app._dimmer_save_dirty is False
    finally:
        gui.config_manager.set = original_set
        gui.config_manager.get = original_get
        gui.config_manager.save_config = original_save


def test_disabled_dimmer_does_not_schedule_or_write() -> None:
    app = gui.AntiFateApp.__new__(gui.AntiFateApp)
    app.dimmer_enabled_var = FakeVariable(False)
    app.dimmer = FakeDimmer()
    app._dimmer_save_after_id = None
    app.after = lambda *_args: (_ for _ in ()).throw(
        AssertionError("disabled dimmer scheduled a save")
    )
    original_set = gui.config_manager.set
    writes: list[object] = []
    try:
        gui.config_manager.set = lambda *args, **kwargs: writes.append(args)
        app.change_brightness(64)
        assert writes == []
        assert app.dimmer.values == []
    finally:
        gui.config_manager.set = original_set


def test_restart_flushes_pending_brightness_before_destroy() -> None:
    app = gui.AntiFateApp.__new__(gui.AntiFateApp)
    app.bot = None
    app._dimmer_save_after_id = "timer-1"
    events: list[object] = []

    class RestartDimmer:
        def close(self) -> None:
            events.append("dimmer.close")

    app.dimmer = RestartDimmer()
    app.after_cancel = lambda timer_id: events.append(("cancel", timer_id))
    app.destroy = lambda: events.append("destroy")
    original_save = gui.config_manager.save_config
    original_popen = subprocess.Popen
    try:
        gui.config_manager.save_config = lambda: events.append("save") or True
        subprocess.Popen = lambda *args, **kwargs: events.append("popen")
        app._restart_app()
    finally:
        gui.config_manager.save_config = original_save
        subprocess.Popen = original_popen

    assert events.index("save") < events.index("dimmer.close")
    assert events.index("save") < events.index("destroy")
    assert events.count("save") == 1


def test_watchdog_reapplies_after_two_display_drifts() -> None:
    app = gui.AntiFateApp.__new__(gui.AntiFateApp)
    app.dimmer_slider = FakeSlider(60)
    app.dimmer = FakeDimmer()
    app.dimmer.backend_name = "fake"
    app.dimmer.verify = lambda _value: False
    app._watchdog_drift_count = 0
    app._automatic_dimmer_allowed = lambda: True
    applied: list[int] = []
    scheduled: list[bool] = []
    app._apply_automatic_brightness = lambda value: applied.append(value)
    app._start_dimmer_watchdog = lambda: scheduled.append(True)

    app._dimmer_watchdog_tick()
    assert app._watchdog_drift_count == 1
    assert applied == []
    assert scheduled == [True]

    app._dimmer_watchdog_tick()
    assert app._watchdog_drift_count == 2
    assert applied == [60]
    assert scheduled == [True, True]

    app.dimmer.verify = lambda _value: True
    app._dimmer_watchdog_tick()
    assert app._watchdog_drift_count == 0
    assert applied == [60]


def test_closing_flushes_and_stops_runtime_components() -> None:
    app = gui.AntiFateApp.__new__(gui.AntiFateApp)
    events: list[object] = []
    app._beacon_pulse_id = "beacon"
    app._arena_validation_after_id = "validation"
    app._dimmer_watchdog_id = "watchdog"
    app.after_cancel = lambda timer_id: events.append(("cancel", timer_id))
    app._flush_pending_dimmer_save = lambda: events.append("flush dimmer")
    app._flush_pending_arena_save = lambda: events.append("flush arena")
    app._set_arena_automation_enabled = lambda enabled: events.append(
        ("automation", enabled)
    )
    app.bot = SimpleNamespace(on_stop_callback=lambda: None, stop=lambda: events.append("bot"))
    app.arena_watcher = SimpleNamespace(stop=lambda: events.append("watcher"))
    app.notifier = SimpleNamespace(close=lambda: events.append("notifier"))
    app.dimmer = SimpleNamespace(close=lambda: events.append("dimmer"))
    app.destroy = lambda: events.append("destroy")

    try:
        app.on_closing()
    except SystemExit as error:
        assert error.code == 0
    else:
        raise AssertionError("on_closing must stop with exit code 0")

    assert events == [
        ("cancel", "beacon"),
        ("cancel", "validation"),
        ("cancel", "watchdog"),
        "flush dimmer",
        "flush arena",
        ("automation", False),
        "bot",
        "watcher",
        "notifier",
        "dimmer",
        "destroy",
    ]
    assert app.bot.on_stop_callback is None


def main() -> None:
    test_brightness_save_is_debounced()
    test_failed_debounced_save_stays_dirty_for_later_retry()
    test_automatic_mode_save_failure_is_not_reported_as_saved()
    test_mode_save_failure_stays_dirty_for_later_retry()
    test_toggle_save_failure_stays_dirty_for_later_retry()
    test_gaming_brightness_updates_gaming_value()
    test_disabled_dimmer_does_not_schedule_or_write()
    test_restart_flushes_pending_brightness_before_destroy()
    test_watchdog_reapplies_after_two_display_drifts()
    test_closing_flushes_and_stops_runtime_components()
    print("dimmer save debounce: PASS")
    print("dimmer mode writes: PASS")
    print("dimmer disabled guard: PASS")
    print("restart save flush: PASS")
    print("shutdown lifecycle: PASS")


if __name__ == "__main__":
    main()

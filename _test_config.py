"""Regression checks for configuration validation and safe persistence."""

from __future__ import annotations

import json
from pathlib import Path
import threading
import tempfile

import config as config_module
from config import BotConfig, ConfigManager
from constants import DefaultConfig


def test_ui_scale_normalization() -> None:
    invalid = BotConfig.from_dict({"ui_scale": "oops"})
    assert invalid.ui_scale == DefaultConfig.UI_SCALE

    nan_value = BotConfig.from_dict({"ui_scale": "nan"})
    assert nan_value.ui_scale == DefaultConfig.UI_SCALE

    huge_value = BotConfig.from_dict({"ui_scale": 10**10000})
    assert huge_value.ui_scale == DefaultConfig.UI_SCALE

    assert BotConfig.from_dict({"ui_scale": 0.1}).ui_scale == 0.8
    assert BotConfig.from_dict({"ui_scale": 4.0}).ui_scale == 2.0
    assert BotConfig.from_dict({"ui_scale": True}).ui_scale == DefaultConfig.UI_SCALE
    assert BotConfig.from_dict({"ui_scale": False}).ui_scale == DefaultConfig.UI_SCALE


def test_persisted_boolean_values_are_normalized() -> None:
    defaults = {
        "dimmer_enabled": DefaultConfig.DIMMER_ENABLED,
        "auto_dimmer_switch_enabled": DefaultConfig.AUTO_DIMMER_SWITCH_ENABLED,
        "auto_startup_enabled": DefaultConfig.AUTO_STARTUP_ENABLED,
        "auto_accept_enabled": DefaultConfig.AUTO_ACCEPT_ENABLED,
        "auto_ban_enabled": DefaultConfig.AUTO_BAN_ENABLED,
        "auto_pick_enabled": DefaultConfig.AUTO_PICK_ENABLED,
        "discord_notify_ban": DefaultConfig.DISCORD_NOTIFY_BAN,
        "discord_notify_pick": DefaultConfig.DISCORD_NOTIFY_PICK,
        "discord_notify_in_game": DefaultConfig.DISCORD_NOTIFY_IN_GAME,
    }

    disabled = BotConfig.from_dict({key: " false " for key in defaults})
    assert all(
        type(getattr(disabled, key)) is bool and getattr(disabled, key) is False
        for key in defaults
    )

    enabled = BotConfig.from_dict({key: " TRUE " for key in defaults})
    assert all(
        type(getattr(enabled, key)) is bool and getattr(enabled, key) is True
        for key in defaults
    )

    malformed = BotConfig.from_dict({key: "maybe" for key in defaults})
    assert {key: getattr(malformed, key) for key in defaults} == defaults


def test_config_set_normalizes_boolean_values() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        manager = ConfigManager(str(Path(temp_dir) / "config.json"))
        assert manager.set("auto_ban_enabled", "false", save=False) is True
        assert manager.get("auto_ban_enabled") is False
        assert manager.set("auto_pick_enabled", "true", save=False) is True
        assert manager.get("auto_pick_enabled") is True


def test_save_keeps_previous_file_when_replace_fails() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "config.json"
        manager = ConfigManager(str(path))
        manager.set("dimmer_value", 80)
        manager.set("dimmer_value", 55, save=False)

        original_replace = config_module.os.replace
        try:
            config_module.os.replace = lambda *_args: (_ for _ in ()).throw(
                OSError("replace failed")
            )
            manager.save_config()
        finally:
            config_module.os.replace = original_replace

        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["dimmer_value"] == 80
        assert not list(Path(temp_dir).glob("*.tmp"))


def test_failed_set_restores_memory_and_disk_state() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "config.json"
        manager = ConfigManager(str(path))
        assert manager.set("dimmer_value", 80) is True

        original_replace = config_module.os.replace
        try:
            config_module.os.replace = lambda *_args: (_ for _ in ()).throw(
                OSError("replace failed")
            )
            assert manager.set("dimmer_value", 55) is False
        finally:
            config_module.os.replace = original_replace

        assert manager.get("dimmer_value") == 80
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["dimmer_value"] == 80


def test_get_waits_for_transactional_set() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "config.json"
        manager = ConfigManager(str(path))
        assert manager.set("dimmer_value", 80) is True

        replace_started = threading.Event()
        release_replace = threading.Event()
        reader_done = threading.Event()
        setter_result = []
        reader_result = []
        original_replace = config_module.os.replace

        def blocked_replace(*_args):
            replace_started.set()
            release_replace.wait(2)
            raise OSError("replace failed")

        def save_value() -> None:
            setter_result.append(manager.set("dimmer_value", 55))

        def read_value() -> None:
            reader_result.append(manager.get("dimmer_value"))
            reader_done.set()

        setter = threading.Thread(target=save_value)
        reader = threading.Thread(target=read_value)
        try:
            config_module.os.replace = blocked_replace
            setter.start()
            assert replace_started.wait(2)
            reader.start()
            assert not reader_done.wait(0.1)
        finally:
            release_replace.set()
            setter.join(2)
            reader.join(2)
            config_module.os.replace = original_replace

        assert setter_result == [False]
        assert reader_result == [80]


def main() -> None:
    test_ui_scale_normalization()
    test_persisted_boolean_values_are_normalized()
    test_config_set_normalizes_boolean_values()
    test_save_keeps_previous_file_when_replace_fails()
    test_failed_set_restores_memory_and_disk_state()
    test_get_waits_for_transactional_set()
    print("config validation: PASS")
    print("boolean config normalization: PASS")
    print("atomic config save: PASS")
    print("config set rollback: PASS")
    print("config read lock: PASS")


if __name__ == "__main__":
    main()

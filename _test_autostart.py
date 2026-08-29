"""Regression check for Windows Startup approval synchronization."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVAL_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
)
APP_NAME = "Anti-Fate Engine"


class FakeKey:
    def __init__(self, registry: "FakeWinreg", path: str) -> None:
        self.registry = registry
        self.path = path

    def __enter__(self) -> "FakeKey":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class FakeWinreg:
    HKEY_CURRENT_USER = object()
    KEY_ALL_ACCESS = 0xF003F
    KEY_READ = 0x20019
    KEY_SET_VALUE = 0x0002
    REG_BINARY = 3
    REG_SZ = 1

    def __init__(self) -> None:
        self.values = {RUN_KEY: {}, APPROVAL_KEY: {}}
        self.created_keys: list[str] = []
        self.fail_approval = False
        self.approval_after_write: object = None

    def OpenKey(
        self,
        _root: object,
        path: str,
        _reserved: int = 0,
        _access: int = 0,
    ) -> FakeKey:
        if path not in self.values:
            raise FileNotFoundError(path)
        return FakeKey(self, path)

    def CreateKeyEx(
        self,
        _root: object,
        path: str,
        _reserved: int = 0,
        _access: int = 0,
    ) -> FakeKey:
        self.values.setdefault(path, {})
        self.created_keys.append(path)
        return FakeKey(self, path)

    def SetValueEx(
        self,
        key: FakeKey,
        name: str,
        _reserved: int,
        value_type: int,
        value: object,
    ) -> None:
        if self.fail_approval and key.path == APPROVAL_KEY:
            self.fail_approval = False
            raise PermissionError("approval write denied")
        self.values[key.path][name] = (value_type, value)
        if key.path == APPROVAL_KEY and self.approval_after_write is not None:
            self.values[key.path][name] = (value_type, self.approval_after_write)

    def QueryValueEx(self, key: FakeKey, name: str) -> tuple[object, object]:
        try:
            value_type, value = self.values[key.path][name]
            return value, value_type
        except KeyError as exc:
            raise FileNotFoundError(name) from exc

    def DeleteValue(self, key: FakeKey, name: str) -> None:
        try:
            del self.values[key.path][name]
        except KeyError as exc:
            raise FileNotFoundError(name) from exc


def main() -> None:
    from utils import windows

    fake_winreg = FakeWinreg()
    original_winreg = windows.winreg
    original_executable = windows.sys.executable
    original_argv = windows.sys.argv
    try:
        windows.winreg = fake_winreg
        windows.sys.executable = r"C:\Python\pythonw.exe"
        windows.sys.argv = [r"C:\autoresetlol\main.py"]
        assert windows.set_autostart(APP_NAME, add=True)

        run_value = fake_winreg.values[RUN_KEY][APP_NAME]
        assert run_value[0] == fake_winreg.REG_SZ
        assert run_value[1] == (
            r'"C:\Python\pythonw.exe" "C:\autoresetlol\main.py"'
        )

        approval_value = fake_winreg.values[APPROVAL_KEY][APP_NAME]
        assert approval_value == (
            fake_winreg.REG_BINARY,
            b"\x02" + b"\x00" * 11,
        )
        assert APPROVAL_KEY in fake_winreg.created_keys
        assert windows.get_autostart_state(APP_NAME) is True

        fake_winreg.values[RUN_KEY][APP_NAME] = (
            fake_winreg.REG_SZ,
            "custom command",
        )
        fake_winreg.values[APPROVAL_KEY][APP_NAME] = (
            fake_winreg.REG_BINARY,
            b"\x03" + b"\x00" * 11,
        )
        fake_winreg.values[RUN_KEY]["AntiFateEngine"] = (
            fake_winreg.REG_SZ,
            "custom legacy command",
        )
        startup_snapshot = windows.get_autostart_snapshot(APP_NAME)
        fake_winreg.values[RUN_KEY][APP_NAME] = (
            fake_winreg.REG_SZ,
            "new command",
        )
        fake_winreg.values[APPROVAL_KEY][APP_NAME] = (
            fake_winreg.REG_BINARY,
            b"\x02" + b"\x00" * 11,
        )
        del fake_winreg.values[RUN_KEY]["AntiFateEngine"]
        assert startup_snapshot is not None
        assert windows.restore_autostart_snapshot(startup_snapshot)
        assert fake_winreg.values[RUN_KEY][APP_NAME] == (
            fake_winreg.REG_SZ,
            "custom command",
        )
        assert fake_winreg.values[APPROVAL_KEY][APP_NAME] == (
            fake_winreg.REG_BINARY,
            b"\x03" + b"\x00" * 11,
        )
        assert fake_winreg.values[RUN_KEY]["AntiFateEngine"] == (
            fake_winreg.REG_SZ,
            "custom legacy command",
        )

        readback_registry = FakeWinreg()
        readback_registry.approval_after_write = b"\x03" + b"\x00" * 11
        windows.winreg = readback_registry
        assert windows.set_autostart(APP_NAME, add=True) is False
        assert APP_NAME not in readback_registry.values[RUN_KEY]
        assert APP_NAME not in readback_registry.values[APPROVAL_KEY]
        windows.winreg = fake_winreg

        fake_winreg.values[APPROVAL_KEY][APP_NAME] = (
            fake_winreg.REG_BINARY,
            b"\x03" + b"\x00" * 11,
        )
        assert windows.get_autostart_state(APP_NAME) is False
        fake_winreg.values[APPROVAL_KEY][APP_NAME] = (
            fake_winreg.REG_BINARY,
            b"\x02",
        )
        assert windows.get_autostart_state(APP_NAME) is None
        fake_winreg.values[APPROVAL_KEY][APP_NAME] = (
            fake_winreg.REG_SZ,
            b"\x02" + b"\x00" * 11,
        )
        assert windows.get_autostart_state(APP_NAME) is None
        del fake_winreg.values[APPROVAL_KEY][APP_NAME]
        assert windows.get_autostart_state(APP_NAME) is True

        failed_registry = FakeWinreg()
        failed_registry.fail_approval = True
        failed_registry.values[RUN_KEY][APP_NAME] = (
            failed_registry.REG_SZ,
            "old command",
        )
        failed_registry.values[APPROVAL_KEY][APP_NAME] = (
            failed_registry.REG_BINARY,
            b"\x03" + b"\x00" * 11,
        )
        failed_registry.values[RUN_KEY]["antifate_7.14"] = (
            failed_registry.REG_SZ,
            "old legacy command",
        )
        failed_registry.values[RUN_KEY]["AntiFateEngine"] = (
            failed_registry.REG_SZ,
            "old engine command",
        )
        windows.winreg = failed_registry
        assert windows.set_autostart(APP_NAME, add=True) is False
        assert failed_registry.values[RUN_KEY][APP_NAME] == (
            failed_registry.REG_SZ,
            "old command",
        )
        assert failed_registry.values[APPROVAL_KEY][APP_NAME] == (
            failed_registry.REG_BINARY,
            b"\x03" + b"\x00" * 11,
        )
        assert failed_registry.values[RUN_KEY]["antifate_7.14"] == (
            failed_registry.REG_SZ,
            "old legacy command",
        )
        assert failed_registry.values[RUN_KEY]["AntiFateEngine"] == (
            failed_registry.REG_SZ,
            "old engine command",
        )
        windows.winreg = fake_winreg

        assert windows.set_autostart(APP_NAME, add=False)
        assert APP_NAME not in fake_winreg.values[RUN_KEY]
        assert APP_NAME not in fake_winreg.values[APPROVAL_KEY]
        assert windows.get_autostart_state(APP_NAME) is False
    finally:
        windows.winreg = original_winreg
        windows.sys.executable = original_executable
        windows.sys.argv = original_argv

    import gui

    class FakeVariable:
        def __init__(self, value: bool) -> None:
            self.value = value

        def get(self) -> bool:
            return self.value

        def set(self, value: bool) -> None:
            self.value = value

    app = gui.AntiFateApp.__new__(gui.AntiFateApp)
    app.auto_startup_enabled_var = FakeVariable(True)
    config_writes: list[tuple[object, object]] = []
    original_set = gui.config_manager.set
    original_autostart = gui.set_autostart
    original_snapshot = gui.get_autostart_snapshot
    try:
        gui.config_manager.set = lambda *args, **kwargs: config_writes.append(args)
        gui.set_autostart = lambda *args, **kwargs: False
        gui.get_autostart_snapshot = lambda _app_name: object()
        app.toggle_startup()
        assert config_writes == []
        assert app.auto_startup_enabled_var.get() is False
    finally:
        gui.config_manager.set = original_set
        gui.set_autostart = original_autostart
        gui.get_autostart_snapshot = original_snapshot

    app = gui.AntiFateApp.__new__(gui.AntiFateApp)
    app.auto_startup_enabled_var = FakeVariable(True)
    original_set = gui.config_manager.set
    original_autostart = gui.set_autostart
    original_snapshot = gui.get_autostart_snapshot
    original_restore = gui.restore_autostart_snapshot
    autostart_calls: list[dict[str, object]] = []
    restore_calls: list[object] = []
    startup_snapshot = object()
    try:
        gui.config_manager.set = lambda *args, **kwargs: False
        gui.set_autostart = lambda *args, **kwargs: (
            autostart_calls.append(kwargs) or True
        )
        gui.get_autostart_snapshot = lambda _app_name: startup_snapshot
        gui.restore_autostart_snapshot = lambda snapshot: (
            restore_calls.append(snapshot) or True
        )
        app.toggle_startup()
        assert autostart_calls == [{"add": True}]
        assert restore_calls == [startup_snapshot]
        assert app.auto_startup_enabled_var.get() is False
    finally:
        gui.config_manager.set = original_set
        gui.set_autostart = original_autostart
        gui.get_autostart_snapshot = original_snapshot
        gui.restore_autostart_snapshot = original_restore

    app = gui.AntiFateApp.__new__(gui.AntiFateApp)
    app.dimmer_mode_segment = SimpleNamespace(set=lambda _value: None)
    app.dimmer_slider = SimpleNamespace(set=lambda _value: None)
    app.dimmer_enabled_var = FakeVariable(False)
    app.auto_startup_enabled_var = FakeVariable(False)
    app.auto_accept_enabled_var = FakeVariable(False)
    app.dimmer = SimpleNamespace(backend_name="fake")
    app.notifier = SimpleNamespace(set_event_enabled=lambda *_args: None)
    for spec in gui.DISCORD_NOTIFICATION_SPECS:
        setattr(app, f"{spec.config_key}_var", FakeVariable(False))
    app.toggle_dimmer = lambda save=True: None
    config_values = {
        "dimmer_value": 80,
        "dimmer_enabled": False,
        "dimmer_mode": "browsing",
        "dimmer_browsing_value": 80,
        "dimmer_gaming_value": 70,
        "auto_startup_enabled": False,
        "auto_accept_enabled": False,
    }
    original_get = gui.config_manager.get
    original_set = gui.config_manager.set
    original_state = gui.get_autostart_state
    state_sync: list[tuple[tuple[object, ...], dict[str, object]]] = []
    try:
        gui.config_manager.get = lambda key: config_values.get(key)
        gui.config_manager.set = lambda *args, **kwargs: (
            state_sync.append((args, kwargs)) or True
        )
        gui.get_autostart_state = lambda _app_name: True
        app.load_settings()
        assert app.auto_startup_enabled_var.get() is True
        assert state_sync == [
            (("auto_startup_enabled", True), {"save": False})
        ]
    finally:
        gui.config_manager.get = original_get
        gui.config_manager.set = original_set
        gui.get_autostart_state = original_state

    print("startup effective-state load: PASS")
    print("startup approval synchronization: PASS")
    print("startup readback: PASS")
    print("startup failure does not persist enabled state: PASS")
    print("startup config rollback: PASS")


if __name__ == "__main__":
    main()

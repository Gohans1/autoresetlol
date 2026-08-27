"""Regression check for Windows Startup approval synchronization."""

from __future__ import annotations

import sys
from pathlib import Path


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
    KEY_SET_VALUE = 0x0002
    REG_BINARY = 3
    REG_SZ = 1

    def __init__(self) -> None:
        self.values = {RUN_KEY: {}, APPROVAL_KEY: {}}
        self.created_keys: list[str] = []

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
        self.values[key.path][name] = (value_type, value)

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

        assert windows.set_autostart(APP_NAME, add=False)
        assert APP_NAME not in fake_winreg.values[RUN_KEY]
        assert APP_NAME not in fake_winreg.values[APPROVAL_KEY]
    finally:
        windows.winreg = original_winreg
        windows.sys.executable = original_executable
        windows.sys.argv = original_argv

    print("startup approval synchronization: PASS")


if __name__ == "__main__":
    main()

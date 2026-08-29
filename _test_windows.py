"""Regression checks for pointer-sized DXVA2 monitor handles."""

from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess
import sys

import utils.windows as windows


SOURCE = Path(__file__).resolve().parent / "utils" / "windows.py"


def test_monitor_brightness_prototypes_are_declared() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    prototypes: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr == "argtypes"
                and isinstance(target.value, ast.Attribute)
                and target.value.attr in {
                    "GetMonitorBrightness",
                    "SetMonitorBrightness",
                }
                and isinstance(node.value, ast.List)
            ):
                prototypes[target.value.attr] = [
                    ast.unparse(item) for item in node.value.elts
                ]

    expected = {
        "GetMonitorBrightness": [
            "wintypes.HANDLE",
            "ctypes.POINTER(wintypes.DWORD)",
            "ctypes.POINTER(wintypes.DWORD)",
            "ctypes.POINTER(wintypes.DWORD)",
        ],
        "SetMonitorBrightness": ["wintypes.HANDLE", "wintypes.DWORD"],
    }
    assert prototypes == expected


def test_windows_module_imports_cleanly() -> None:
    interpreters = [sys.executable]
    system_python = shutil.which("python")
    if system_python and Path(system_python).resolve() != Path(sys.executable).resolve():
        interpreters.append(system_python)
    for executable in interpreters:
        result = subprocess.run(
            [executable, "-c", "import utils.windows"],
            cwd=SOURCE.parent.parent,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"{executable}: {result.stderr}"


def test_gamma_ramp_clamps_to_safe_range() -> None:
    dim = windows.GammaController.build_ramp(0)
    dim_floor = windows.GammaController.build_ramp(50)
    full = windows.GammaController.build_ramp(150)
    full_ceiling = windows.GammaController.build_ramp(100)

    assert len(dim) == 768
    assert list(dim) == list(dim_floor)
    assert list(full) == list(full_ceiling)
    assert dim[1] == dim[257] == dim[513]
    assert full[255] == full[511] == full[767]


def test_dimmer_falls_back_after_three_backlight_failures() -> None:
    class FakeBacklight:
        instances: list["FakeBacklight"] = []

        def __init__(self) -> None:
            self.available = True
            self.values: list[int] = []
            self.closed = False
            self.__class__.instances.append(self)

        def set_brightness(self, value: int) -> bool:
            self.values.append(value)
            return False

        def close(self) -> None:
            self.closed = True

    class FakeGamma:
        instances: list["FakeGamma"] = []

        def __init__(self) -> None:
            self.values: list[int] = []
            self.__class__.instances.append(self)

        def set_brightness(self, value: int) -> bool:
            self.values.append(value)
            return True

        def verify(self, _value: int) -> bool:
            return True

        def reset(self) -> None:
            pass

        def close(self) -> None:
            pass

    original_backlight = windows.MonitorBrightnessController
    original_gamma = windows.GammaController
    try:
        windows.MonitorBrightnessController = FakeBacklight
        windows.GammaController = FakeGamma
        controller = windows.DimmerController()

        assert controller.backend_name == "FakeBacklight"
        assert controller.set_brightness(35) is False
        assert controller.set_brightness(35) is False
        assert controller.set_brightness(35) is True
        assert FakeBacklight.instances[0].values == [35, 35, 35]
        assert FakeBacklight.instances[0].closed is True
        assert FakeGamma.instances[0].values == [35]
        controller.close()
    finally:
        windows.MonitorBrightnessController = original_backlight
        windows.GammaController = original_gamma


def main() -> None:
    test_monitor_brightness_prototypes_are_declared()
    test_windows_module_imports_cleanly()
    test_gamma_ramp_clamps_to_safe_range()
    test_dimmer_falls_back_after_three_backlight_failures()
    print("DXVA2 handle prototypes: PASS")
    print("dimmer runtime fallback: PASS")


if __name__ == "__main__":
    main()

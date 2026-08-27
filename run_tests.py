"""Run the repository's focused checks in one deterministic command."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CHECKS = (
    ("bot LCU", ("_test_bot_lcu.py",)),
    ("Arena select", ("_test_arena_select.py",)),
    ("LCU client", ("_test_lcu.py",)),
    ("Arena config", ("_test_arena_config.py",)),
    ("notifications", ("_test_notifications.py",)),
    ("startup", ("_test_autostart.py",)),
    ("startup visibility", ("_test_gui_startup.py",)),
    (
        "compile",
        (
            "-m",
            "py_compile",
            "gui.py",
            "constants.py",
            "config.py",
            "bot.py",
            "lcu_watcher.py",
            "arena_config.py",
            "notifications.py",
            "utils/lcu.py",
            "utils/windows.py",
            "main.py",
        ),
    ),
)


def main() -> int:
    for label, args in CHECKS:
        print(f"\n== {label} ==")
        result = subprocess.run([sys.executable, *args], cwd=ROOT)
        if result.returncode:
            print(f"FAILED: {label} (exit {result.returncode})")
            return result.returncode
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

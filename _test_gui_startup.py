"""Regression check for the hidden CustomTkinter startup window bug."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "gui.py"


def call_name(node: ast.Call) -> str:
    parts = []
    value = node.func
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if isinstance(value, ast.Name):
        parts.append(value.id)
    return ".".join(reversed(parts))


def main() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    app_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "AntiFateApp"
    )
    init = next(
        node
        for node in app_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    calls = [
        (index, call_name(node.value))
        for index, node in enumerate(init.body)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
    ]
    positions = {name: index for index, name in calls}

    required = ("self.update", "self.deiconify", "self.arena_watcher.start")
    missing = [name for name in required if name not in positions]
    assert not missing, f"missing startup calls: {missing}"
    assert (
        positions["self.update"]
        < positions["self.deiconify"]
        < positions["self.arena_watcher.start"]
    ), f"bad startup order: {positions}"
    assert "self.update_idletasks" not in positions, (
        "__init__ must use full update() so CTk marks the root initialized"
    )
    print("startup visibility order: PASS")


if __name__ == "__main__":
    main()

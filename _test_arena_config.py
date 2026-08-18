"""Focused tests for Arena configuration validation."""
import sys
from typing import Any

from arena_config import NO_PICK_LABEL, NOT_SET_LABEL, validate_arena_config
import gui
from gui import AntiFateApp


FAILURES = []


def check(name, condition, detail=""):
    tag = "PASS" if condition else "FAIL"
    print(f"[{tag}] {name}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


issues = validate_arena_config(
    auto_ban_enabled=False,
    auto_pick_enabled=False,
    ban_champion_id=0,
    pick_chain=[0, 0, 0, 0],
)
check("T1: tính năng tắt → không lỗi", not issues, str(issues))

issues = validate_arena_config(
    auto_ban_enabled=True,
    auto_pick_enabled=False,
    ban_champion_id=0,
    pick_chain=[0, 0, 0, 0],
)
check("T2: thiếu tướng ban → lỗi đúng field", [i.code for i in issues] == ["missing_ban"])

issues = validate_arena_config(
    auto_ban_enabled=False,
    auto_pick_enabled=True,
    ban_champion_id=0,
    pick_chain=[0, 2, 0, 0],
)
check("T3: chỉ có dự bị → thiếu main", [i.code for i in issues] == ["missing_main"])

issues = validate_arena_config(
    auto_ban_enabled=True,
    auto_pick_enabled=True,
    ban_champion_id=7,
    pick_chain=[7, 7, 0, 0],
    owned_ids={7},
)
check(
    "T4: trùng pick + ban/pick conflict",
    {i.code for i in issues} == {"duplicate_pick", "ban_pick_conflict"},
    str(issues),
)
conflict_issue = next(i for i in issues if i.code == "ban_pick_conflict")
app = AntiFateApp.__new__(AntiFateApp)
app._arena_loaded_ids = {"ban": 7, "main": 7, "b1": 7, "b2": 0, "b3": 0}
app._arena_cached_names = {7: "Bard"}
app._arena_id_to_display = {7: "Bard"}
app._arena_roster_known = False
check(
    "T4b: lỗi ban/pick nói rõ ô bị trùng",
    AntiFateApp._arena_issue_text(app, conflict_issue)
    == "Bard đang ở cả Tướng cần ban và Tướng chính, Dự bị 1. Chọn tướng khác cho một bên.",
)
check(
    "T4c: ô ban nói rõ đang trùng với pick",
    AntiFateApp._arena_field_issue_text(app, "ban", [conflict_issue])
    == "Đang trùng với Tướng chính, Dự bị 1.",
)
check(
    "T4d: ô pick nói rõ đang trùng với ban",
    AntiFateApp._arena_field_issue_text(app, "main", [conflict_issue])
    == "Đang trùng với tướng cần ban.",
)
check(
    "T4e: khi client chưa kết nối vẫn hiện tên đã lưu",
    AntiFateApp._arena_display_for_id(app, 7, "main") == "Bard",
)

issues = validate_arena_config(
    auto_ban_enabled=True,
    auto_pick_enabled=True,
    ban_champion_id=99,
    pick_chain=[1, 2, 0, 0],
    owned_ids={1, 2},
)
check(
    "T5: tướng ban không còn trong client",
    [i.code for i in issues] == ["ban_not_owned"],
    str(issues),
)

issues = validate_arena_config(
    auto_ban_enabled=True,
    auto_pick_enabled=True,
    ban_champion_id=99,
    pick_chain=[1, 2, 0, 0],
    owned_ids=None,
)
check("T6: roster chưa xác minh → không đoán là lỗi", not issues, str(issues))


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class FakeCombo:
    def get(self):
        return "draft text"


class FakeValueCombo:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeLabel:
    def __init__(self):
        self.kwargs = {}

    def configure(self, **kwargs):
        self.kwargs = kwargs


class FakeSuggestCombo:
    def __init__(self):
        self._entry = object()
        self._canvas = object()


class FakeDimmer:
    def __init__(self):
        self.calls = []

    def set_brightness(self, value):
        self.calls.append(value)


class FakeEvent:
    def __init__(self, widget):
        self.widget = widget


class FakeKeyEvent:
    def __init__(self, keysym):
        self.keysym = keysym


def draft_issues(auto_ban, auto_pick):
    app: Any = AntiFateApp.__new__(AntiFateApp)
    app.arena_combos = {
        key: FakeCombo() for key in ("ban", "main", "b1", "b2", "b3")
    }
    app.auto_ban_var = FakeVar(auto_ban)
    app.auto_pick_var = FakeVar(auto_pick)
    app._arena_field_is_draft = lambda key: True
    return AntiFateApp._arena_draft_issues(app)


issues = draft_issues(False, False)
check("T7: cả hai tính năng tắt → draft không tạo lỗi", not issues, str(issues))

issues = draft_issues(False, True)
check(
    "T8: chỉ Auto pick bật → draft chỉ xét pick fields",
    {field for issue in issues for field in issue.fields}
    == {"main", "b1", "b2", "b3"},
    str(issues),
)

app = AntiFateApp.__new__(AntiFateApp)
app.arena_combos = {
    key: FakeValueCombo("" if key == "b1" else NOT_SET_LABEL)
    for key in ("ban", "main", "b1", "b2", "b3")
}
app._arena_loaded_ids = {"ban": 0, "main": 0, "b1": 60084, "b2": 0, "b3": 0}
app._arena_id_to_display = {}
app._arena_cached_names = {}
app._arena_owned_ids = set()
app.auto_ban_var = FakeVar(False)
app.auto_pick_var = FakeVar(True)
issues = AntiFateApp._arena_draft_issues(app)
check(
    "T8a: backup trống dù có giá trị cũ → không chặn START",
    not issues,
    str(issues),
)

app = AntiFateApp.__new__(AntiFateApp)
app._arena_id_to_display = {}
app._arena_cached_names = {}
app._arena_roster_known = False
check(
    "T8b: backup ID 0 hiển thị Không",
    AntiFateApp._arena_display_for_id(app, 0, "b1") == NO_PICK_LABEL,
)
check(
    "T8c: main ID 0 vẫn hiển thị placeholder cũ",
    AntiFateApp._arena_display_for_id(app, 0, "main") == NOT_SET_LABEL,
)
check(
    "T8c2: ID đã lưu hiện tên cache khi client chưa kết nối",
    AntiFateApp._arena_display_for_id(app, 60084, "main") == "Tướng đã lưu",
)

app = AntiFateApp.__new__(AntiFateApp)
app.arena_combos = {"b1": FakeValueCombo("")}
app._arena_owned = [{"name": "Akali"}, {"name": "Bel'Veth"}]
app._recent_names = lambda key, limit: ["Akali", "Bel'Veth"]
suggested = []
app._show_suggest = lambda key, items: suggested.extend(items)
AntiFateApp._update_suggest(app, "b1")
check(
    "T8d: suggest backup luôn có Không ở đầu",
    suggested[0] == NO_PICK_LABEL,
    str(suggested),
)

app = AntiFateApp.__new__(AntiFateApp)
app.arena_combos = {
    "b1": FakeValueCombo(""),
    "b2": FakeValueCombo(NO_PICK_LABEL),
    "b3": FakeValueCombo(NOT_SET_LABEL),
}
app._arena_loaded_ids = {"b1": 60084, "b2": 0, "b3": 0}
app._arena_cached_names = {}
cleared = []
app._on_arena_combo = lambda key: cleared.append(key)
AntiFateApp._commit_empty_optional_picks(app)
check("T8e: backup trống được commit thành Không", cleared == ["b1", "b3"])

app = AntiFateApp.__new__(AntiFateApp)
app.arena_combos = {"b1": FakeValueCombo("")}
app._arena_field_error_visible = {"b1": False}
app._on_arena_combo = lambda key: app.arena_combos[key].set(NO_PICK_LABEL)
app._update_suggest = lambda key: None
app._refresh_arena_validation = lambda: None
AntiFateApp._on_arena_combo_key(app, "b1", FakeKeyEvent("BackSpace"))
check(
    "T8f: xóa hết backup → field tự về Không",
    app.arena_combos["b1"].get() == NO_PICK_LABEL,
)

issues = draft_issues(True, False)
check(
    "T9: chỉ Auto ban bật → draft chỉ xét ban field",
    {field for issue in issues for field in issue.fields} == {"ban"},
    str(issues),
)


app: Any = AntiFateApp.__new__(AntiFateApp)
app._update_suggest = lambda key: (_ for _ in ()).throw(
    AssertionError("navigation key must not re-filter suggestions")
)
app._refresh_arena_validation = lambda: None
app._arena_field_error_visible = {"ban": True}
for key_name in ("Up", "Down", "Left", "Right"):
    AntiFateApp._on_arena_combo_key(app, "ban", FakeKeyEvent(key_name))
check("T10: navigation key không reset suggestion", True)

# ============ T11: newest Arena event appears first ============
app = AntiFateApp.__new__(AntiFateApp)
app._arena_live_events = []
app._render_arena_live = lambda: None
app.after = lambda delay, callback: callback()
AntiFateApp.update_arena_live(app, "event cũ", "gray")
AntiFateApp.update_arena_live(app, "event mới", "green")
check(
    "T11: log Arena mới nhất đứng đầu",
    app._arena_live_events[0][1] == "event mới"
    and app._arena_live_events[1][1] == "event cũ",
    str(app._arena_live_events),
)
check(
    "T11b: badge giữ đúng loại PICK khi có lỗi",
    AntiFateApp._arena_log_parts("PICK: PATCH failed", "red")
    == ("Chọn tướng", "Tự động chọn tướng đã dừng."),
)

# ============ T12: click outside dismisses suggestion ============
app = AntiFateApp.__new__(AntiFateApp)
active_combo = FakeSuggestCombo()
suggest_list = object()
outside_widget = object()
hidden = []
app._suggest_key = "ban"
app._suggest_listbox = suggest_list
app.arena_combos = {"ban": active_combo}
app._suggest_visible = lambda: True
app._hide_suggest = lambda: hidden.append("hide")
AntiFateApp._on_suggest_global_click(app, FakeEvent(outside_widget))
check("T12a: click ngoài đóng suggestion", hidden == ["hide"], str(hidden))

hidden.clear()
for inside_widget in (active_combo, active_combo._entry, active_combo._canvas, suggest_list):
    AntiFateApp._on_suggest_global_click(app, FakeEvent(inside_widget))
check("T12b: click trong vùng hợp lệ không đóng", hidden == [], str(hidden))

# ============ T13: scroll dismisses suggestion ============
AntiFateApp._on_suggest_scroll(app, FakeEvent(outside_widget))
check("T13: scroll đóng suggestion", hidden == ["hide"], str(hidden))

# ============ T14: auto dimmer OFF blocks bot success reset ============
app = AntiFateApp.__new__(AntiFateApp)
app.dimmer_enabled_var = FakeVar(True)
app.dimmer = FakeDimmer()
original_get = gui.config_manager.get
gui.config_manager.get = lambda key: (
    False if key == "auto_dimmer_switch_enabled" else original_get(key)
)
AntiFateApp.reset_dimmer(app)
check(
    "T14: auto dimmer OFF không ghi brightness",
    app.dimmer.calls == [],
    str(app.dimmer.calls),
)
gui.config_manager.get = original_get

if FAILURES:
    print(f"FAILED: {len(FAILURES)} test thất bại: {FAILURES}")
    sys.exit(1)
print("ALL TESTS PASSED")

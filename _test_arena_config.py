"""Focused tests for Arena configuration validation."""
import sys
from typing import Any

from arena_config import (
    NO_PICK_LABEL,
    NOT_SET_LABEL,
    champion_id,
    validate_arena_config,
)
from config import BotConfig
import gui
from gui import AntiFateApp
from constants import AppConfig, DefaultConfig, DISCORD_NOTIFICATION_SPECS


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
check(
    "T1b: Arena alias ID 60053 dùng cùng ID action 53",
    champion_id(60053) == 53 and champion_id("60053") == 53,
)
legacy_config = BotConfig.from_dict(
    {
        "arena_ban_champ": "60053",
        "arena_pick_chain": [60053, "60084", 0, 0],
        "arena_recent": {"ban": [60053, 53]},
        "arena_champion_names": {
            "60053": "Blitzcrank",
            "53": "Blitzcrank",
        },
    }
)
check(
    "T1c: config cũ được migrate mà không mất tướng",
    legacy_config.arena_ban_champ == 53
    and legacy_config.arena_pick_chain[:2] == [53, 84]
    and legacy_config.arena_recent == {"ban": [53]}
    and legacy_config.arena_champion_names == {"53": "Blitzcrank"},
    str(legacy_config),
)
default_values = BotConfig.from_dict({})
check(
    "T1d: default geometry và UI scale có một owner",
    default_values.window_geometry == AppConfig.GEOMETRY
    and default_values.ui_scale == DefaultConfig.UI_SCALE == 1.25,
    str(default_values),
)
default_config = BotConfig.from_dict({})
check(
    "T1e: Discord notifications mặc định tắt",
    not default_config.discord_notify_ban
    and not default_config.discord_notify_pick
    and not default_config.discord_notify_in_game,
    str(default_config),
)


class NotificationFakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class NotificationFakeNotifier:
    def __init__(self):
        self.calls = []

    def set_event_enabled(self, event, enabled):
        self.calls.append((event, enabled))


fake_app = AntiFateApp.__new__(AntiFateApp)
fake_notifier = NotificationFakeNotifier()
setattr(fake_app, "notifier", fake_notifier)
fake_var = NotificationFakeVar(True)
saved_notification_config = []
original_config_set = gui.config_manager.set
gui.config_manager.set = lambda key, value, save=True: (
    saved_notification_config.append((key, value)) or True
)
try:
    AntiFateApp._toggle_discord_notification(
        fake_app,
        DISCORD_NOTIFICATION_SPECS[0],
        fake_var,
    )
finally:
    gui.config_manager.set = original_config_set
check(
    "T1f: toggle Discord lưu config và áp dụng ngay",
    saved_notification_config == [("discord_notify_ban", True)]
    and fake_notifier.calls == [("arena.ban_verified", True)],
    str((saved_notification_config, fake_notifier.calls)),
)

# ============ T1g: champion selection batches config writes ============
class SelectionFakeCombo:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


app = AntiFateApp.__new__(AntiFateApp)
app.arena_combos = {"main": SelectionFakeCombo("Akali")}
app._arena_display_to_id_normalized = {"akali": 1}
app._arena_loaded_ids = {"main": 0}
app._arena_draft_keys = {"main"}
app._arena_field_error_visible = {"main": False}
app._arena_cached_names = {}
app._arena_owned = []
app._arena_id_to_display = {1: "Akali"}
app._arena_recent = {"main": []}
app._refresh_arena_validation = lambda: None
saved_selection_config = []
selection_sets = []
original_config_get = gui.config_manager.get
original_config_set = gui.config_manager.set
original_config_save = gui.config_manager.save_config
gui.config_manager.get = lambda key: {
    "arena_pick_chain": [0, 0, 0, 0],
    "arena_champion_names": {},
}.get(key)
gui.config_manager.set = lambda key, value, save=True: (
    selection_sets.append((key, value, save)) or True
)
gui.config_manager.save_config = lambda: (
    saved_selection_config.append("save") or True
)
try:
    AntiFateApp._on_arena_combo(app, "main")
finally:
    gui.config_manager.get = original_config_get
    gui.config_manager.set = original_config_set
    gui.config_manager.save_config = original_config_save
check(
    "T1g: chọn tướng chỉ ghi config một lượt",
    len(saved_selection_config) == 1
    and selection_sets
    and all(save is False for _, _, save in selection_sets),
    str((selection_sets, saved_selection_config)),
)

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


class FakeSlider:
    def __init__(self, value=100):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


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
app._arena_draft_keys = set()
app.auto_ban_var = FakeVar(False)
app.auto_pick_var = FakeVar(True)
issues = AntiFateApp._arena_draft_issues(app)
check(
    "T8a: backup trống dù có giá trị cũ → không chặn START",
    not issues,
    str(issues),
)
app._arena_draft_keys.add("b1")
check(
    "T8a2: draft chỉ đúng field đang gõ",
    AntiFateApp._arena_field_is_draft(app, "b1")
    and not AntiFateApp._arena_field_is_draft(app, "main"),
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
app._arena_draft_keys = set()
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
suggest_update_calls = []
validation_calls = []
app._update_suggest = lambda key: suggest_update_calls.append(key)
app._refresh_arena_validation = lambda: validation_calls.append(True)
app._arena_field_error_visible = {"ban": True}
for key_name in ("Up", "Down", "Left", "Right"):
    AntiFateApp._on_arena_combo_key(app, "ban", FakeKeyEvent(key_name))
check(
    "T10: navigation key không reset suggestion",
    suggest_update_calls == [] and validation_calls == [],
    str((suggest_update_calls, validation_calls)),
)

# ============ T10b: virtual edit cũng là draft ============
app = AntiFateApp.__new__(AntiFateApp)
app.after_idle = lambda callback: callback()
app.arena_combos = {"b1": FakeValueCombo("Yasuo")}
app._arena_draft_keys = set()
app._arena_field_error_visible = {"b1": False}
app.auto_ban_var = FakeVar(False)
app.auto_pick_var = FakeVar(True)
app._update_suggest = lambda _key: None
app._schedule_arena_validation = lambda: None
AntiFateApp._on_arena_virtual_edit(app, "b1")
virtual_draft_issues = AntiFateApp._arena_draft_issues(app)
check(
    "T10b: paste/cut/undo không cần KeyRelease vẫn chặn draft",
    "b1" in app._arena_draft_keys
    and any(
        issue.code == "draft" and issue.fields == ("b1",)
        for issue in virtual_draft_issues
    ),
    str(virtual_draft_issues),
)

# ============ T10c: virtual edit defer qua after_idle ============
# Widget binding chạy TRƯỚC class binding của Entry → lúc handler chạy,
# entry còn chữ TRƯỚC paste. Phải defer, không được đọc-chồng ngay.
app = AntiFateApp.__new__(AntiFateApp)
deferred = []
app.after_idle = lambda callback: deferred.append(callback)
app.arena_combos = {"b1": FakeValueCombo("")}
app._arena_draft_keys = set()
app._arena_field_error_visible = {"b1": False}
app._update_suggest = lambda _key: None
app._schedule_arena_validation = lambda: None
commits = []
app._on_arena_combo = lambda key: commits.append(key)
AntiFateApp._on_arena_virtual_edit(app, "b1")
check("T10c1: virtual edit không xử lý đồng bộ", deferred != [], str(deferred))
check("T10c2: chưa có commit nào trước idle", commits == [], str(commits))
# Giả lập paste đã đổ chữ vào entry TRƯỚC khi idle callback chạy
app.arena_combos["b1"].set("Yasuo")
for callback in deferred:
    callback()
check(
    "T10c3: optional rỗng + paste → không tự commit 0 ('Không')",
    commits == [],
    str(commits),
)
check(
    "T10c4: field được đánh dấu draft chờ Enter/focus-out",
    "b1" in app._arena_draft_keys,
    str(app._arena_draft_keys),
)

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

# ============ T14b: deferred automatic reset re-checks both gates ============
app = AntiFateApp.__new__(AntiFateApp)
app.dimmer_enabled_var = FakeVar(True)
app.dimmer = FakeDimmer()
app.dimmer_slider = FakeSlider()
callbacks = []
app.after = lambda _delay, callback: callbacks.append(callback)
gui.config_manager.get = lambda key: (
    True if key == "auto_dimmer_switch_enabled" else original_get(key)
)
AntiFateApp.reset_dimmer(app)
app.dimmer_enabled_var.value = False
for callback in callbacks:
    callback()
check(
    "T14b: tắt dimmer trước callback → không ghi brightness",
    app.dimmer.calls == [] and app._dimmer_reset_visual is False,
    str((app.dimmer.calls, app._dimmer_reset_visual)),
)
gui.config_manager.get = lambda key: (
    "false" if key == "auto_dimmer_switch_enabled" else original_get(key)
)
callbacks.clear()
app.dimmer_enabled_var.value = True
AntiFateApp.reset_dimmer(app)
check(
    "T14c: config truthy giả → không schedule reset",
    callbacks == [],
    str(callbacks),
)
gui.config_manager.get = original_get

if FAILURES:
    print(f"FAILED: {len(FAILURES)} test thất bại: {FAILURES}")
    sys.exit(1)
print("ALL TESTS PASSED")

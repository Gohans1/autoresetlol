# autoresetlol - Agent Knowledge Base & Rules

**Generated:** 2026-01-09T01:55:00Z
**Branch:** main

## OVERVIEW 🤖
**autoresetlol** (AntiFateEngine) is a League of Legends automation tool designed to solve "queue anxiety" by automatically resetting the matchmaking queue after a set threshold and auto-accepting matches.

- **Primary Goal:** Prevent getting stuck in long queues and ensure match acceptance without manual monitoring.
- **Core Stack:** Python, CustomTkinter, PyInstaller, Win32 API.
- **Theme:** [Flexoki](https://stephango.com/flexoki) by Steph Ango (Dark mode).

## STRUCTURE
```
autoresetlol/
├── utils/           # OS-level integration (Gamma, Registry, Windows)
├── assets/          # Notification sounds and icons
├── dist/            # Compiled binaries and release artifacts
├── build/           # PyInstaller build cache
├── bot.py           # Core automation engine logic
├── gui.py           # User interface and configuration management
├── main.py          # Application entry point
└── config.py        # Configuration persistence (Singleton)
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| UI Changes | `gui.py` | Uses CustomTkinter with Flexoki theme |
| Logic Updates | `bot.py` | State machine: SEARCHING, VERIFYING, STANDBY |
| Win32/System | `utils/windows.py` | Low-level display and window handling |
| Build Config | `*.spec` | PyInstaller build definitions |

## CODE MAP
| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `AntiFateBot` | Class | `bot.py` | Threaded worker managing bot lifecycle and pixel detection |
| `AntiFateApp` | Class | `gui.py` | Main UI application class |
| `BotConfig` | Dataclass | `config.py` | Global config + profile references |
| `ProfileConfig` | Dataclass | `config.py` | Profile-specific coords/colors (v1.10+) |
| `ConfigManager` | Class | `config.py` | Singleton config manager with profile API |
| `SettingsModal` | Class | `gui.py` | Advanced settings modal with coord picker (v1.10+) |
| `PROFILE_KEYS` | List | `config.py` | List of keys that are profile-specific |
| `GammaController` | Class | `utils/windows.py` | Hardware-level screen dimming management |
| `set_autostart` | Function | `utils/windows.py` | Windows Registry-based startup logic |

## CORE UNBREAKABLE RULES 🛡️

### 1. Environment & Package Manager
- **Package Manager:** BẮT BUỘC dùng `uv` cho mọi thao tác cài đặt/chạy lệnh (`uv pip install`, `uv run`...). KHÔNG dùng pip trần.
- **Versioning:** Phiên bản bắt đầu từ `1.0`. Khi có thay đổi, LUÔN LUÔN tăng 1 version nhỏ (ví dụ: `1.0` -> `1.01`, `1.01` -> `1.02`). KHÔNG dùng version 7.x hay lộn xộn khác.
- **Build Process:** LUÔN LUÔN build sau khi sửa đổi bằng PyInstaller qua `uv`. Code xong là phải build ngay. Tạo spec file và binary theo đúng version mới.
- **Total Cleanup:** Mỗi khi tạo bản build mới, PHẢI xóa sạch mọi file `.spec` cũ và mọi file `.exe` cũ trong thư mục `dist/`. KHÔNG để lại bất kỳ tàn dư nào của các phiên bản trước đó. Project chỉ chấp nhận sự tồn tại của phiên bản HIỆN TẠI.

### 2. Bot Logic & Game Detection
- **Game Sensitivity:** Bot TUYỆT ĐỐI KHÔNG ĐƯỢC chiếm quyền focus (nhảy taskbar) khi người chơi đang **In-Game**.
- **Detection Method:** Dựa vào Window Title: `"League of Legends"` (Lobby) vs `"League of Legends (TM) Client"` (In-Game).
- **Logic "Bất Tử":** Bot PHẢI kiểm tra pixel Chọn Tướng trong MỌI trạng thái. Nếu phát hiện Chọn Tướng, PHẢI nhảy sang `STANDBY` ngay lập tức.
- **Stealth is Life:** TUYỆT ĐỐI không dùng Win32 API để ghi vào bộ nhớ game. Chỉ được ĐỌC PIXEL. Con bot phải hoạt động như một "người chơi mù" chỉ biết nhìn màn hình.
- **Human Delay:** Giữa các lệnh click (Cancel -> Find Match), PHẢI nghỉ ít nhất `0.5s - 1.0s`. Client LoL cần thời gian để phản hồi.

### 3. Feature Toggle Independence (v1.08+) ⚠️ CRITICAL
- **Two Independent Features:** `Auto Accept Match` và `Auto Reset Queue` là 2 tính năng ĐỘC LẬP với nhau.
- **Config Keys:** `auto_accept_enabled` và `auto_reset_enabled` trong `config.json`.
- **Bot Logic Gates:** 
  - `bot.py` line ~147: Auto Accept PHẢI được wrap trong `if config_manager.get("auto_accept_enabled"):`
  - `bot.py` line ~165: Auto Reset PHẢI được wrap trong `if config_manager.get("auto_reset_enabled"):`
- **Sound Notification:** Chỉ phát khi `auto_reset_enabled = True` (vì sound là cảnh báo trước reset).
- **Default Values:** Cả 2 default = `True` để backward compatible với user cũ.
- **Use Case:** User chơi với bạn, không phải chủ phòng → Tắt Auto Reset, Bật Auto Accept → Bot vẫn tự động accept trận nhưng không can thiệp queue.
- **NEVER BREAK:** Khi sửa bot logic, PHẢI kiểm tra CẢ 2 conditions. KHÔNG được gộp lại thành 1 toggle.

### 4. Technical Mechanics (The Backbone) 🦴
- **Polling Rate:** 1 giây/lần.
- **Auto-Minimize:** Sau khi Reset hàng chờ, bot PHẢI click nút Minimize của Client (nếu có tọa độ).
- **Brightness Safety:** Dimmer PHẢI được kẹp (clamped) trong khoảng `1-100%`. Tuyệt đối không để user chỉnh về `0%`.
- **Portable Integrity:** Config (`config.json`) và Log (`*.log`) PHẢI được lưu cạnh file thực thi (.exe) khi chạy bản build. KHÔNG lưu trong thư mục tạm `_MEIPASS`.
- **Startup Logic:** Registry entry PHẢI luôn trỏ đúng vào file thực thi hiện tại. Tên Registry key mặc định là `"Anti-Fate Engine"`.
- **Layout Integrity:** Khi thêm UI mới, Footer PHẢI được pack đầu tiên với `side="bottom"`. `main_container` (với `expand=True`) PHẢI được pack sau để Footer luôn hiển thị.
- **Cursor Safety:** TUYỆT ĐỐI không dùng cursor không hỗ trợ trên Windows (ví dụ: `question_mark`). Chỉ dùng `hand2` cho các liên kết/nút có thể nhấp.

### 5. Dual Dimmer Mode (v1.09+) ⚠️ CRITICAL
- **Two Independent Modes:** `Gaming` và `Browsing` là 2 chế độ dimmer RIÊNG BIỆT.
- **Config Keys:** `dimmer_mode`, `dimmer_gaming_value`, `dimmer_browsing_value` trong `config.json`.
- **Mode Persistence:** Mỗi mode LƯU RIÊNG giá trị brightness của nó. Khi chuyển mode, giá trị slider PHẢI được cập nhật theo mode mới.
- **Auto-Switch Callback:** Khi bot detect Champ Select, PHẢI gọi `on_champ_select_callback` để GUI tự động switch sang Gaming mode.
- **Slider Save Logic:** Khi user kéo slider, PHẢI save cả `dimmer_value` chung VÀ giá trị riêng của mode hiện tại (`dimmer_gaming_value` hoặc `dimmer_browsing_value`).
- **NEVER BREAK:** Khi sửa dimmer logic, PHẢI kiểm tra cả 2 modes hoạt động độc lập và persistence đúng.

### 6. Sound Selection System (v1.09+)
- **Config Key:** `selected_sound` - lưu key của sound được chọn (ví dụ: "notify", "chime", "bell").
- **SOUND_OPTIONS Dict:** Định nghĩa trong `constants.py` với format `key: (display_name, relative_path)`.
- **Sound Files Location:** `assets/sounds/` cho các WAV mới, `assets/notify.mp3` cho sound gốc.
- **Play Sound Logic:** Bot và GUI đều PHẢI lookup sound path từ `SOUND_OPTIONS` bằng `selected_sound` key.
- **Test Button:** GUI có nút `▶` để test sound với volume hiện tại trước khi select.

### 7. Profile System (v1.10+) ⚠️ CRITICAL
- **Multi-Profile Support:** App hỗ trợ nhiều profiles cho các LoL client khác nhau (VN, TQ, etc.).
- **Config Keys:** `current_profile` (tên profile đang dùng), `profiles` (Dict chứa tất cả profiles).
- **Profile-Specific Keys:** Các key sau được lưu RIÊNG cho mỗi profile:
  - `find_match_button_pos`, `cancel_button_pos`, `minimize_btn_pos`
  - `in_queue_pixel_pos`, `in_queue_pixel_color`
  - `accept_match_pixel_pos`, `accept_match_pixel_color`
  - `champ_select_pixel_pos`, `champ_select_pixel_color`
- **PROFILE_KEYS Constant:** Định nghĩa trong `config.py` - KHI THÊM COORD/COLOR MỚI, PHẢI thêm vào list này.
- **Auto Migration:** Config cũ (v1.09-) được tự động migrate sang Profile 1 khi load. Detection: `"profiles" not in data and "find_match_button_pos" in data`.
- **ConfigManager API:**
  - `get_profile_names()` → List[str]
  - `switch_profile(name)` → bool
  - `create_profile(name, copy_from=None)` → bool
  - `rename_profile(old_name, new_name)` → bool
  - `delete_profile(name)` → bool (không xóa được profile cuối cùng)
- **Hot-Reload:** Bot đọc coords từ `config_manager.get()` mỗi loop, nên đổi profile sẽ apply ngay.
- **Config Structure (v1.10+):**
  ```json
  {
    "current_profile": "Profile 1",
    "profiles": {
      "Profile 1": {
        "find_match_button_pos": [673, 954],
        "cancel_button_pos": [1704, 214],
        ...
      },
      "LoL TQ": { ... }
    },
    "reset_time": 90,
    "dimmer_value": 57,
    ...
  }
  ```
- **NEVER BREAK:** Khi sửa config logic, PHẢI ensure `PROFILE_KEYS` trong `config.py` được resolve đúng qua `get()`.

### 8. Auto Dimmer Switch Toggle (v1.10+)
- **Config Key:** `auto_dimmer_switch_enabled` (default: True)
- **Purpose:** Cho phép user TẮT tự động chuyển sang Gaming mode khi detect champ select.
- **Use Case:** User muốn giữ màn hình tối ngay cả khi đang chơi game.
- **Location:** Toggle trong main UI (dưới Dimmer slider) - đã di chuyển ra khỏi Settings Modal từ v1.11.
- **NEVER BREAK:** Khi sửa dimmer auto-switch, PHẢI check `config_manager.get("auto_dimmer_switch_enabled")` trước.

### 10. Minimize on Focus Loss (v1.11+) ⚠️ CRITICAL
- **Config Key:** `minimize_on_focus_loss` (default: True)
- **Behavior:** App tự động minimize khi user click vào bất kỳ cửa sổ nào khác (LoL client, browser, etc.).
- **Implementation:**
  - Bind `<FocusOut>` event trên root window trong `AntiFateApp.__init__`
  - Handler `_on_focus_out()` defer check qua `after(100)` để tránh race condition
  - `_check_and_minimize()` verify không có modal nào đang visible trước khi minimize
- **Exception:** KHÔNG minimize nếu đang trong Pick Mode của Settings Modal (`_pick_mode_active = True`)
- **NEVER BREAK:** Khi sửa focus logic, PHẢI check `_settings_modal._pick_mode_active` trước khi gọi `iconify()`

### 11. Browsing Brightness Persistence (v1.11+) ⚠️ CRITICAL
- **Problem Solved:** Browsing mode brightness bị mất khi auto-switch sang Gaming mode
- **Root Cause:** `_on_dimmer_mode_changed()` save old mode's value TRƯỚC khi switch, nhưng slider đã bị set sang gaming value rồi
- **Solution:** Flag `_skip_dimmer_save` được set trong `switch_to_gaming_mode()` TRƯỚC khi gọi `_on_dimmer_mode_changed()`
- **Flow:**
  1. `switch_to_gaming_mode()` save browsing value manually
  2. Set `_skip_dimmer_save = True`
  3. Gọi `_on_dimmer_mode_changed()` qua `after(10)`
  4. `_on_dimmer_mode_changed()` skip save vì flag = True
  5. Reset flag về False sau khi xong
- **NEVER BREAK:** Khi sửa dimmer switch logic, PHẢI giữ nguyên flag `_skip_dimmer_save` và thứ tự save/load

### 12. Dimmer Visual Reset Protection (v1.12+) ⚠️ CRITICAL
- **Problem Solved:** Browsing mode brightness bị reset về 100 sau khi bot success
- **Root Cause:** `reset_dimmer()` set slider về 100 (visual reset), nhưng khi user switch mode sau đó, `_on_dimmer_mode_changed()` nghĩ slider value = 100 là user setting và save vào OLD mode config → override giá trị thật
- **Solution:** Flag `_dimmer_reset_visual` được set trong `reset_dimmer()` để protect config
- **Flow:**
  1. Bot success → `reset_dimmer()` set flag = True + slider = 100 (visual only)
  2. User switch mode → `_on_dimmer_mode_changed()` check flag
  3. Nếu flag = True → SKIP save old mode value (vì 100 là fake value)
  4. Load new mode value từ config (preserved)
  5. Reset flag về False
- **Flags:** 
  - `_skip_dimmer_save`: Dùng cho auto-switch (switch_to_gaming_mode)
  - `_dimmer_reset_visual`: Dùng cho visual-only reset (reset_dimmer)
- **NEVER BREAK:** Khi sửa dimmer logic, PHẢI check CẢ 2 flags trước khi save old mode value

### 9. Settings Modal & Coord Picker (v1.10+)
- **Settings Button:** Nút ⚙️ ở góc trái-trên Status Card (đối xứng với nút "i").
- **SettingsModal Class:** Singleton modal (~800 lines) trong `gui.py`.
- **Sections:**
  - Profile Management: Dropdown + Rename/New/Delete buttons
  - Coordinates: 6 entries với X/Y + Pick button
  - Colors: 3 entries với R/G/B + color preview + Pick button
  - Auto Dimmer Switch toggle
- **Pick Mode:** Khi nhấn "📍 Pick":
  1. Modal ẩn đi
  2. Overlay fullscreen transparent xuất hiện
  3. User click anywhere → capture position + color
  4. Auto-save vào config
  5. Modal hiện lại
- **Color Preview:** Small square hiển thị màu RGB live preview.
- **NEVER BREAK:** Khi sửa SettingsModal, PHẢI ensure pick overlay xử lý đúng trên multi-monitor.

## CORE UNCHANGEABLE PROTOCOLS 📋

### 1. Feature Guard (Chống Hỏng Chức Năng Cũ)
Mỗi khi sửa đổi bất kỳ phần nào, PHẢI kiểm tra lại 8 trụ cột này:
1. **Giant Timer UI**: Bộ đếm số (?/?) phải là trọng tâm, to rõ nhất.
2. **Persistence**: Đổi giá trị Reset Threshold, tắt đi bật lại xem có giữ nguyên không.
3. **Audio Volume**: Thanh trượt volume phải thực sự điều chỉnh được âm thanh thông báo.
4. **Dimmer Control**: Chức năng làm tối màn hình phải hoạt động và reset về 100% khi thoát.
5. **Info & Socials**: Nút 'i' PHẢI mở Modal Resolution. Footer PHẢI hiện tên tác giả là **Gohans** và dẫn về link Twitter `https://x.com/GohansVN`. Badge độ phân giải PHẢI có khả năng tương tác.
6. **Feature Toggle Independence (v1.08+)**: Kiểm tra cả 2 toggle `Auto Accept Match` và `Auto Reset Queue` hoạt động ĐỘC LẬP. Tắt 1 cái KHÔNG được ảnh hưởng cái còn lại.
7. **Dual Dimmer Mode (v1.09+)**: Chuyển đổi Gaming/Browsing PHẢI restore đúng brightness value đã save. Auto-switch khi vào champ select.
8. **Sound Selection (v1.09+)**: Dropdown PHẢI hiển thị tên sound. Test button PHẢI phát đúng sound đã chọn với volume đúng.
9. **Profile System (v1.10+)**: Đổi profile PHẢI apply coords ngay. Settings Modal PHẢI mở và đóng mượt. Pick mode PHẢI capture đúng position + color.
10. **Auto Dimmer Switch (v1.10+)**: Toggle TẮT thì KHÔNG được auto-switch khi vào champ select. Browsing value KHÔNG được bị reset về 100.

### 2. Landing the Plane Protocol
Khi hoàn thành một version, PHẢI thực hiện theo thứ tự:
1. **Cleanup**: Xóa mọi file rác, legacy registry (nếu có sự thay đổi về tên/version).
2. **Build**: Tạo file `.spec` mới và build `.exe`.
3. **Verify**: Chạy bản build, kiểm tra 6 trụ cột ở mục 1.
4. **Document**: Note lại vào chính file `AGENTS.md` này nếu có logic nào mới cần bảo vệ. BẮT BUỘC thực hiện cực kì nghiêm túc và thật KĨ sau khi Landing the Plane.
5. **Ship**: `git push`, `bd sync`, và tạo GitHub Release.

## ANTI-PATTERNS
- **Focus Stealing:** Never call `force_focus_window` when `is_game_running()` detects the game client.
- **Direct config.json Edit:** Never overwrite `config.json` in `dist/` as it contains hardcoded production coordinates.
- **Gamma Mismanagement:** Never leave gamma at <100% on app exit or when entering champion select.
- **Pack Disorder:** Never pack the main expand container before the bottom footer.

## COMMANDS ⚡
```bash
# Run Dev
uv run python main.py

# Install Deps
uv pip install -r pyproject.toml

# Build (Example for v1.12)
uv run pyinstaller AntiFateEngine_v1.12.spec

# Release (MANDATORY)
gh release create v1.12 dist/AntiFateEngine_v1.12.exe --title "Release v1.12" --notes "UI Scale + Scrollable main UI"
```

## CHANGELOG (v1.12) ✅

### Fixed
1. **Browsing Mode Brightness Reset After Bot Success** - Added `_dimmer_reset_visual` flag to protect config when `reset_dimmer()` does visual-only reset to 100%.

### Added
1. **UI Scale Setting** - Dropdown in Settings Modal (80%-150%) with restart prompt
2. **Scrollable Main UI** - Main app content now scrollable with `CTkScrollableFrame`
3. **Native Scroll Speed** - Scroll respects Windows OS settings (`WheelScrollLines` from Registry)
4. `ui_scale` config key (default: 1.0)
5. `_get_os_scroll_lines()` and `_setup_native_scroll_speed()` methods in both SettingsModal and AntiFateApp
6. `_create_ui_scale_section()` in SettingsModal
7. `_on_scale_changed()` with confirmation dialog
8. Recursive `bind_recursive()` helper to bind mousewheel to all nested children
9. `_dimmer_reset_visual` flag to prevent config override after visual reset

### Changed
- Main `main_container` changed from `CTkFrame` to `CTkScrollableFrame`
- `self.main_container` stored as instance variable for scroll binding after widget creation
- Build command updated to v1.12

### Technical Notes
- **Scroll Binding Order**: `_setup_native_scroll_speed()` MUST be called AFTER all widgets are created (in `__init__`, after `create_widgets()`)
- **CTkSegmentedButton Exception**: This widget doesn't support `.bind()`, wrapped in try-except to skip
- **Rebind After Idle**: Uses `after(100, rebind)` to catch dynamically added children

## CHANGELOG (v1.13) ✅

### Fixed
1. **Auto Dimmer Switch Toggle Not Saving** - Bug: `False or True` always returns True. Fixed by checking `if config_val is None` instead of using `or True`.

### Changed
- Label "Auto switch on Champ Select" → "Auto switch to Gaming mode" (clearer)
- Version bump to v1.13

### Fixed
1. **Browsing Mode Brightness Lost** - Added `_skip_dimmer_save` flag to prevent `_on_dimmer_mode_changed()` from overwriting browsing value during auto-switch.
2. **Auto Dimmer Switch Toggle Location** - Moved toggle from SettingsModal to main UI (under Dimmer slider).
3. **Minimize on Focus Loss** - App now auto-minimizes when clicking other windows. Respects pick mode in Settings Modal.

### Added
- `minimize_on_focus_loss` config key (default: True)
- `_on_focus_out()` and `_check_and_minimize()` methods in AntiFateApp
- `_skip_dimmer_save` flag to prevent race conditions in dimmer auto-switch

### Changed
- Commented out `_create_auto_dimmer_section()` call in SettingsModal (line 222)
- `dimmer_slider` padding changed from `(0, 15)` to `(0, 10)` to fit new toggle

## NOTES
- **Landing the Plane:** Khi kết thúc task, LUÔN LUÔN `git push`, `bd sync` và tạo GitHub Release cho bản build mới nhất. Đéo phải hỏi.
- **Flexoki Theme:** LUÔN LUÔN tuân thủ bảng màu Flexoki (Dark) trong mọi thay đổi UI.
- **Beads:** Always use `bd` for cross-session memory synchronization.

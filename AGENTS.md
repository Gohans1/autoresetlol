# autoresetlol - Agent Knowledge Base & Rules

**Generated:** 2026-01-04T01:50:00Z
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
| `BotConfig` | Dataclass | `config.py` | Typed configuration structure |
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

### 3. Technical Mechanics (The Backbone) 🦴
- **Polling Rate:** 1 giây/lần.
- **Auto-Minimize:** Sau khi Reset hàng chờ, bot PHẢI click nút Minimize của Client (nếu có tọa độ).
- **Brightness Safety:** Dimmer PHẢI được kẹp (clamped) trong khoảng `1-100%`. Tuyệt đối không để user chỉnh về `0%`.
- **Portable Integrity:** Config (`config.json`) và Log (`*.log`) PHẢI được lưu cạnh file thực thi (.exe) khi chạy bản build. KHÔNG lưu trong thư mục tạm `_MEIPASS`.
- **Startup Logic:** Registry entry PHẢI luôn trỏ đúng vào file thực thi hiện tại. Tên Registry key mặc định là `"Anti-Fate Engine"`.

## CORE UNCHANGEABLE PROTOCOLS 📋

### 1. Feature Guard (Chống Hỏng Chức Năng Cũ)
Mỗi khi sửa đổi bất kỳ phần nào, PHẢI kiểm tra lại 5 trụ cột này:
1. **Giant Timer UI**: Bộ đếm số (?/?) phải là trọng tâm, to rõ nhất.
2. **Persistence**: Đổi giá trị Reset Threshold, tắt đi bật lại xem có giữ nguyên không.
3. **Audio Volume**: Thanh trượt volume phải thực sự điều chỉnh được âm thanh thông báo.
4. **Dimmer Control**: Chức năng làm tối màn hình phải hoạt động và reset về 100% khi thoát.
5. **Info & Socials**: Nút 'i' phải mở Modal Resolution, và link chân trang phải trỏ đúng về Twitter tác giả.

### 2. Landing the Plane Protocol
Khi hoàn thành một version, PHẢI thực hiện theo thứ tự:
1. **Cleanup**: Xóa mọi file rác, legacy registry (nếu có sự thay đổi về tên/version).
2. **Build**: Tạo file `.spec` mới và build `.exe`.
3. **Verify**: Chạy bản build, kiểm tra 4 trụ cột ở mục 1.
4. **Document**: Note lại vào chính file `AGENTS.md` này nếu có logic nào mới cần bảo vệ. BẮT BUỘC thực hiện cực kì nghiêm túc và thật KĨ sau khi Landing the Plane.
5. **Ship**: `git push`, `bd sync`, và tạo GitHub Release.

## ANTI-PATTERNS
- **Focus Stealing:** Never call `force_focus_window` when `is_game_running()` detects the game client.
- **Direct config.json Edit:** Never overwrite `config.json` in `dist/` as it contains hardcoded production coordinates.
- **Gamma Mismanagement:** Never leave gamma at <100% on app exit or when entering champion select.

## COMMANDS ⚡
```bash
# Run Dev
uv run python main.py

# Install Deps
uv pip install -r pyproject.toml

# Build (Example for v1.05)
uv run pyinstaller AntiFateEngine_v1.05.spec

# Release (MANDATORY)
gh release create v1.05 dist/AntiFateEngine_v1.05.exe --title "Release v1.05" --notes "UI Overhaul: Info Modal, Professional Footer with author link, and Resolution Badge."
```

## NOTES
- **Landing the Plane:** Khi kết thúc task, LUÔN LUÔN `git push`, `bd sync` và tạo GitHub Release cho bản build mới nhất. Đéo phải hỏi.
- **Flexoki Theme:** LUÔN LUÔN tuân thủ bảng màu Flexoki (Dark) trong mọi thay đổi UI.
- **Beads:** Always use `bd` for cross-session memory synchronization.

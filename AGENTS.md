# autoresetlol - Agent Knowledge Base & Rules

## OVERVIEW 🤖
**autoresetlol** (AntiFateEngine) is a League of Legends automation tool (v7.14) designed to solve "queue anxiety" by automatically resetting the matchmaking queue after a set threshold and auto-accepting matches.

- **Primary Goal:** Prevent getting stuck in long queues and ensure match acceptance without manual monitoring.
- **Version:** v7.14 (Current Stable)
- **Status:** Active Development

---

## CORE UNBREAKABLE RULES 🛡️

### 1. Environment & Package Manager
- **Package Manager:** BẮT BUỘC dùng `uv` cho mọi thao tác cài đặt/chạy lệnh (`uv pip install`, `uv run`...). KHÔNG dùng pip trần.
- **Build Process:** LUÔN LUÔN build sau khi sửa đổi bằng PyInstaller qua `uv`. Tạo version mới (`v7.x`), KHÔNG ghi đè bản cũ.

### 2. Bot Logic & Game Detection
- **Game Sensitivity:** Bot TUYỆT ĐỐI KHÔNG ĐƯỢC chiếm quyền focus (nhảy taskbar) khi người chơi đang **In-Game**.
- **Detection Method:** Dựa vào Window Title:
    - `"League of Legends"` -> Lobby/Client (Được phép Focus).
    - `"League of Legends (TM) Client"` -> In-Game Fullscreen (**CẤM Focus**).
- **Global Accept:** Logic nút Accept phải hoạt động ngay cả khi window không ở foreground (Global pixel matching).

### 3. Technical Mechanics
- **Polling Rate:** 1 giây/lần.
- **Auto-Minimize:** Sau khi Reset hàng chờ, bot PHẢI click nút Minimize của Client nếu đã có tọa độ trong config để trả lại không gian cho người dùng.
- **Brightness Safety:** Dimmer PHẢI được kẹp (clamped) trong khoảng `1-100%`. Tuyệt đối không để user chỉnh về `0%` (gây đen màn hình).

### 4. Code Architecture & Logic
- **Separation of Concerns:** Logic bot (`bot.py`) tách biệt hoàn toàn với UI (`gui.py`).
- **Logic "Bất Tử":** Bot PHẢI kiểm tra pixel Chọn Tướng trong MỌI trạng thái (đặc biệt là khi đang đếm ngược reset 90s). Nếu phát hiện Chọn Tướng, PHẢI nhảy sang `STANDBY` ngay lập tức.
- **Manual Support:** Bot PHẢI hỗ trợ việc người dùng bấm Accept bằng tay.
- **Success UI Reset:** Khi xác nhận vào Chọn Tướng thành công, bot PHẢI reset Gamma Dimmer về 100% để đảm bảo tầm nhìn cho người dùng.

### 5. Notifications & Integration
- **Sound Alert:** Bot plays a 'ting' sound (`winsound.MB_ICONASTERISK`) exactly 1.5s before resetting the queue. This is toggleable via `config.json`.
- **Auto Startup:** Registry-based (`HKCU\...\Run`). Handles both `.py` (via python exe) and `.exe` (via `sys.frozen`) with proper path quoting.

---

## STRUCTURE & CODE MAP 🗺️

### Core Components
- **`main.py`**: Entry point. Initializes the GUI application.
- **`AntiFateBot` (`bot.py`)**: The engine. A threaded worker managing states: `SEARCHING`, `VERIFYING`, `STANDBY`.
- **`AntiFateApp` (`gui.py`)**: The UI. Built with `customtkinter`. Manages user interactions and bot lifecycle.
- **`ConfigManager` (`config.py`)**: Singleton handler for `config.json`. Uses `BotConfig` dataclass for type safety.
- **`GammaController` (`utils/windows.py`)**: Low-level Windows GDI32 integration for screen dimming.

### Utils & Helpers
- **`windows.py`**: Window handling (Focus, Title detection) and Registry-based Auto-Startup logic.
- **`constants.py`**: Centralized pixel coordinates, colors, and string constants.
- **`logger.py`**: Configured logging to both file (`autoresetlol.log`) and console.

---

## PROJECT CONVENTIONS 📝

- **Memory:** LUÔN LUÔN áp dụng hệ thống beads (bd) để đồng bộ trí nhớ giữa các phiên làm việc.
- **Config Safety:** CẤM GHI ĐÈ LÊN `config.json` trong folder `dist` vì chứa tọa độ hardcode.

---

## COMMANDS ⚡

| Task | Command |
| :--- | :--- |
| **Run Dev** | `uv run python main.py` |
| **Install Deps** | `uv pip install -r pyproject.toml` |
| **Build v7.14** | `uv run pyinstaller AntiFateEngine_v7.14.spec` |
| **Clean Build** | `rm -rf build/ dist/*.exe` |

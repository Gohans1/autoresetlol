##
- CẤM GHI ĐÈ LÊN config.json trong folder dist vì trong đấy t đã hardcode vị trí tọa độ của các nút
- LUÔN LUÔN áp dụng hệ thống beads (bd), vì bd chính là trí nhớ của agents cho các phiên làm việc sau,
- Sau khi xong xuôi tất cả mọi việc, hãy viết vào AGENTS.md của chính project này về những thông tin/quy luật CORE cực kì quan trọng mà nó cố định, những định luật mà sẽ không bao giờ thay đổi của chính project này.

# CORE UNBREAKABLE RULES

## 1. Environment & Package Manager
- **Package Manager:** BẮT BUỘC dùng `uv` cho mọi thao tác cài đặt/chạy lệnh (`uv pip install`, `uv run`...). KHÔNG dùng pip trần.
- **Build Process:** LUÔN LUÔN build sau khi sửa đổi bằng PyInstaller qua `uv`. Tạo version mới (`v7.x`), KHÔNG ghi đè bản cũ.

## 2. Bot Logic & Game Detection
- **Game Sensitivity:** Bot TUYỆT ĐỐI KHÔNG ĐƯỢC chiếm quyền focus (nhảy taskbar) khi người chơi đang **In-Game**.
- **Detection Method:** Dựa vào Window Title:
    - `"League of Legends"` -> Lobby/Client (Được phép Focus).
    - `"League of Legends (TM) Client"` -> In-Game Fullscreen (**CẤM Focus**).
- **Global Accept (v7.5):** Logic nút Accept phải hoạt động ngay cả khi window không ở foreground (Global pixel matching).

## 3. Technical Mechanics
- **Polling Rate:** 1 giây/lần.
- **Auto-Minimize:** Sau khi Reset hàng chờ, bot PHẢI click nút Minimize của Client nếu đã có tọa độ trong config để trả lại không gian cho người dùng.
- **Brightness Safety:** Dimmer PHẢI được kẹp (clamped) trong khoảng `1-100%`. Tuyệt đối không để user chỉnh về `0%` (gây đen màn hình).

## 4. Code Architecture
- Tuân thủ nghiêm ngặt **Separation of Concerns**: Logic bot (`bot.py`) tách biệt hoàn toàn với UI (`gui.py`). 
- Dùng `logger.py` thay cho `print`.
- Dùng `config.py` (Typed BotConfig) để quản lý persistence.

## 5. Sound Notifications
- **Pre-reset Alert:** Bot plays a 'ting' sound (`winsound.MB_ICONASTERISK`) approximately 1.5 seconds before resetting the queue to alert the user.
- **Toggleable:** This feature can be enabled/disabled via the GUI and is stored in `config.json`.

# 🛠️ UTILS AGENTS GUIDE - BẢN ĐỒ PHÒNG MÁY

Địt mẹ, folder `./utils` này là cái "xương sống" (`backbone`) 🦴 của cả con bot. Đéo có nó thì m chỉ là thằng mù đi đêm. Đọc kĩ mấy cái luật này để đéo làm hỏng hệ thống.

### 🪟 windows.py: CỖ MÁY CAN THIỆP WIN32

Tập trung vào giao tiếp cấp thấp với `Windows` (Windows) 💻 qua `ctypes`.

- **`GammaController` (Gamma Controller) 🔆:**
    - **Cơ chế:** Dùng `SetDeviceGammaRamp` để bú trực tiếp vào phần cứng hiển thị.
    - **Luật Bất Di Bất Dịch:** LUÔN LUÔN phải kẹp (`clamp`) độ sáng trong khoảng `1-100%`. 
    - **CẤM:** Đéo bao giờ được để user chỉnh về `0%`. Về 0 là đen mẹ màn hình, user đéo thấy gì để chỉnh lại thì t vả vỡ mồm m.
- **`Window Detection` (Window Detection) 🔍:**
    - `Lobby` (Lobby) 🏠: `"League of Legends"` -> Được phép chiếm quyền `focus`.
    - `In-Game` (In-Game) 🎮: `"League of Legends (TM) Client"` -> **TUYỆT ĐỐI CẤM** chiếm quyền `focus` (nhảy taskbar).
- **`Auto-Startup` (Auto-Startup) 🚀:**
    - Ghi vào `Registry` (Registry) 🗄️ tại `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`.
    - **BẮT BUỘC:** Đường dẫn (`path`) 📁 chứa khoảng trắng **PHẢI** được bọc trong ngoặc kép `""`. Đéo có ngoặc kép là Win nó đéo chạy được lúc khởi động đâu thằng lồn.

### 📍 coord_picker.py: CÔNG CỤ CĂN CHỈNH TỌA ĐỘ

Tool này để m lấy "số má" cho chuẩn. Đéo có tọa độ chuẩn thì bot click vào không khí à?

- **Cách dùng:** 
    - Di chuột đến chỗ cần lấy -> Nhấn `S` để lưu (`save`) 💾.
    - Xong việc thì nhấn `Q` để cút (`quit`) 🚪.
- **Output:** Trả về `pixel_pos` [x, y] và `pixel_color` [r, g, b]. Bú cái này rồi nhét vào `config.json` ở folder `dist`.

### 📜 QUY TẮC CHUNG (CORE CONVENTIONS)

1. **`Logger` Over `Print`:** Dùng `logger.py` để sủa (`log`) 🗣️ mọi lỗi Win32. Đừng dùng `print` rác rưởi.
2. **`Bypass Focus`:** Dùng tiểu xảo gửi phím `ALT` (`shell.SendKeys("%")`) để vượt qua cơ chế khóa cửa sổ của Windows khi cần `SetForegroundWindow`.
3. **`Cleanup`:** Khi đóng bot, LUÔN LUÔN phải gọi `GammaController.reset()` để trả lại 100% độ sáng cho người ta. Đừng có để user sống trong bóng tối.

Làm cho đúng, đéo đúng t sủa cho đấy. 
---
*GohansGPT - Kỹ sư đường phố.*

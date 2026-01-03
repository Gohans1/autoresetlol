# 🛠️ UTILS AGENTS GUIDE - BẢN ĐỒ PHÒNG MÁY

## OVERVIEW 🦴
Thư mục `./utils` là cái "xương sống" (`backbone`) của con bot, chứa logic can thiệp Win32 và công cụ phụ trợ.

## STRUCTURE
```
utils/
├── windows.py       # Win32 API wrappers (Gamma, Focus, Registry)
├── coord_picker.py  # Utility for capturing screen coordinates
└── logger.py        # Centralized logging helper
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Display/Gamma | `windows.py` | `GammaController` class |
| Registry/Startup| `windows.py` | `set_autostart` function |
| Window Focus | `windows.py` | `force_focus_window` with Alt-bypass |
| Coordinate Tools| `coord_picker.py`| Standalone tool for dev use |

## CONVENTIONS
- **Logger Over Print:** LUÔN LUÔN dùng `logger` từ `logger.py` cho mọi thông báo. Đéo dùng `print` rác rưởi.
- **Bypass Focus:** Dùng tiểu xảo gửi phím `ALT` (`shell.SendKeys("%")`) để vượt qua cơ chế khóa cửa sổ của Windows.
- **Gamma Safety:** LUÔN LUÔN kẹp (`clamp`) độ sáng trong khoảng `1-100%`. 

## ANTI-PATTERNS
- **Zero Brightness:** CẤM tuyệt đối để user chỉnh gamma về `0%` (gây đen màn hình).
- **Unquoted Paths:** Registry path đéo được thiếu ngoặc kép `""` nếu có khoảng trắng.
- **Dirty Exit:** Never exit without calling `GammaController.reset()`.

## NOTES
- **Coord Picker Output:** Trả về `pixel_pos` [x, y] và `pixel_color` [r, g, b].
- **Win32 Dependencies:** Phụ thuộc vào `pywin32` và `ctypes`.

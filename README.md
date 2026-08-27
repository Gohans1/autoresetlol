# Anti-Fate Engine

Desktop helper for League of Legends. It uses the local League Client API for
match acceptance, Arena ban/pick, and screen dimming.

## Tải bản dùng ngay

Mở [Releases](https://github.com/Gohans1/autoresetlol/releases/latest) và tải
`AntiFateEngine_v2.0.exe`.

Mở League Client trước khi chạy app. Chạy file `.exe` sau khi tải xong.

Windows có thể hiện cảnh báo SmartScreen vì bộ cài chưa có chữ ký số.

App tự tạo `config.json` và `autoresetlol.log` cạnh file `.exe`.

## Kiểm tra

```text
.venv\Scripts\python.exe run_tests.py
```

Trong Git Bash/Hermes terminal, dùng:

```text
PYTHONPATH= .venv/Scripts/python.exe run_tests.py
```

## Build Windows

PyInstaller nằm trong dependency group `build`, không nằm trong runtime dependencies.

```text
uv run --group build pyinstaller AntiFateEngine_v2.0.spec --clean --noconfirm
```

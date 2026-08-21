# Anti-Fate Engine

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

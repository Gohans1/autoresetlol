# Beads Export

*Generated: Mon, 22 Dec 2025 19:48:45 +07*

## Summary

| Metric | Count |
|--------|-------|
| **Total** | 26 |
| Open | 2 |
| In Progress | 1 |
| Blocked | 0 |
| Closed | 23 |

## Quick Actions

Ready-to-run commands for bulk operations:

```bash
# Close all in-progress items
bd close autoresetlol-2e9

# Close all open items
bd close autoresetlol-0v6 autoresetlol-47b

# View high-priority items (P0/P1)
bd show autoresetlol-2e9

```

## Table of Contents

- [🔵 autoresetlol-2e9 Fix: Missing Pillow dependency for PyAutoGUI](#autoresetlol-2e9)
- [🟢 autoresetlol-0v6 Fix focus stealing & Add Dimmer Persistence](#autoresetlol-0v6)
- [🟢 autoresetlol-47b Fix: Dimmer slider is capped at 20%, preventing further dimming](#autoresetlol-47b)
- [⚫ autoresetlol-abz Build AntiFateEngine v7.1 Release](#autoresetlol-abz)
- [⚫ autoresetlol-4nt Fix: ModuleNotFoundError customtkinter in exe build](#autoresetlol-4nt)
- [⚫ autoresetlol-9dr Build AntiFateEngine v7.1](#autoresetlol-9dr)
- [⚫ autoresetlol-czf Bug: Fix CTkSwitch on_color argument](#autoresetlol-czf)
- [⚫ autoresetlol-0fb Update: Separate Cancel and Find Match coordinates](#autoresetlol-0fb)
- [⚫ autoresetlol-9ei Fix: Calibration color error due to mouse hover](#autoresetlol-9ei)
- [⚫ autoresetlol-u0f Fix: PyInstaller missing hidden imports for Pillow/PyScreeze](#autoresetlol-u0f)
- [⚫ autoresetlol-3ki Core: Bot Logic & Threading Engine](#autoresetlol-3ki)
- [⚫ autoresetlol-bvj Epic: The Anti-Fate Engine - Auto Accept & Reset Queue](#autoresetlol-bvj)
- [⚫ autoresetlol-67v Build: AntiFateEngine V7.1 (Ghost Update)](#autoresetlol-67v)
- [⚫ autoresetlol-a2p Feature: Ghost Dimmer & Pin Toggle](#autoresetlol-a2p)
- [⚫ autoresetlol-opt Build: AntiFateEngine V7 (uv + customtkinter)](#autoresetlol-opt)
- [⚫ autoresetlol-swx UI: Refactor to CustomTkinter (Shadcn Dark Mode)](#autoresetlol-swx)
- [⚫ autoresetlol-0rr Infra: Migrate to uv package manager](#autoresetlol-0rr)
- [⚫ autoresetlol-dhd Feature: Persistent Supervisor Logic](#autoresetlol-dhd)
- [⚫ autoresetlol-dtv Refactor: Add Window Focus Logic](#autoresetlol-dtv)
- [⚫ autoresetlol-lm1 Setup: Project Structure & Config Manager](#autoresetlol-lm1)
- [⚫ autoresetlol-cag UI: Tkinter Dashboard Implementation](#autoresetlol-cag)
- [⚫ autoresetlol-30f Release Notes: AntiFateEngine V6](#autoresetlol-30f)
- [⚫ autoresetlol-15g Build: PyInstaller Packaging](#autoresetlol-15g)
- [⚫ autoresetlol-65h Feature: Calibration Helper](#autoresetlol-65h)
- [⚫ autoresetlol-gw7 Clarify project goal and Obsidian syntax usage](#autoresetlol-gw7)
- [⚫ autoresetlol-1p0 Docs: V6 User Guide](#autoresetlol-1p0)

---

## Dependency Graph

```mermaid
graph TD
    classDef open fill:#50FA7B,stroke:#333,color:#000
    classDef inprogress fill:#8BE9FD,stroke:#333,color:#000
    classDef blocked fill:#FF5555,stroke:#333,color:#000
    classDef closed fill:#6272A4,stroke:#333,color:#fff

    autoresetlol-0fb["autoresetlol-0fb<br/>Update: Separate Cancel and Find Matc..."]
    class autoresetlol-0fb closed
    autoresetlol-0rr["autoresetlol-0rr<br/>Infra: Migrate to uv package manager"]
    class autoresetlol-0rr closed
    autoresetlol-0v6["autoresetlol-0v6<br/>Fix focus stealing & Add Dimmer Persi..."]
    class autoresetlol-0v6 open
    autoresetlol-15g["autoresetlol-15g<br/>Build: PyInstaller Packaging"]
    class autoresetlol-15g closed
    autoresetlol-1p0["autoresetlol-1p0<br/>Docs: V6 User Guide"]
    class autoresetlol-1p0 closed
    autoresetlol-2e9["autoresetlol-2e9<br/>Fix: Missing Pillow dependency for Py..."]
    class autoresetlol-2e9 inprogress
    autoresetlol-30f["autoresetlol-30f<br/>Release Notes: AntiFateEngine V6"]
    class autoresetlol-30f closed
    autoresetlol-3ki["autoresetlol-3ki<br/>Core: Bot Logic & Threading Engine"]
    class autoresetlol-3ki closed
    autoresetlol-47b["autoresetlol-47b<br/>Fix: Dimmer slider is capped at 20%, ..."]
    class autoresetlol-47b open
    autoresetlol-4nt["autoresetlol-4nt<br/>Fix: ModuleNotFoundError customtkinte..."]
    class autoresetlol-4nt closed
    autoresetlol-65h["autoresetlol-65h<br/>Feature: Calibration Helper"]
    class autoresetlol-65h closed
    autoresetlol-67v["autoresetlol-67v<br/>Build: AntiFateEngine V7.1 (Ghost Upd..."]
    class autoresetlol-67v closed
    autoresetlol-9dr["autoresetlol-9dr<br/>Build AntiFateEngine v7.1"]
    class autoresetlol-9dr closed
    autoresetlol-9ei["autoresetlol-9ei<br/>Fix: Calibration color error due to m..."]
    class autoresetlol-9ei closed
    autoresetlol-a2p["autoresetlol-a2p<br/>Feature: Ghost Dimmer & Pin Toggle"]
    class autoresetlol-a2p closed
    autoresetlol-abz["autoresetlol-abz<br/>Build AntiFateEngine v7.1 Release"]
    class autoresetlol-abz closed
    autoresetlol-bvj["autoresetlol-bvj<br/>Epic: The Anti-Fate Engine - Auto Acc..."]
    class autoresetlol-bvj closed
    autoresetlol-cag["autoresetlol-cag<br/>UI: Tkinter Dashboard Implementation"]
    class autoresetlol-cag closed
    autoresetlol-czf["autoresetlol-czf<br/>Bug: Fix CTkSwitch on_color argument"]
    class autoresetlol-czf closed
    autoresetlol-dhd["autoresetlol-dhd<br/>Feature: Persistent Supervisor Logic"]
    class autoresetlol-dhd closed
    autoresetlol-dtv["autoresetlol-dtv<br/>Refactor: Add Window Focus Logic"]
    class autoresetlol-dtv closed
    autoresetlol-gw7["autoresetlol-gw7<br/>Clarify project goal and Obsidian syn..."]
    class autoresetlol-gw7 closed
    autoresetlol-lm1["autoresetlol-lm1<br/>Setup: Project Structure & Config Man..."]
    class autoresetlol-lm1 closed
    autoresetlol-opt["autoresetlol-opt<br/>Build: AntiFateEngine V7 (uv + custom..."]
    class autoresetlol-opt closed
    autoresetlol-swx["autoresetlol-swx<br/>UI: Refactor to CustomTkinter (Shadcn..."]
    class autoresetlol-swx closed
    autoresetlol-u0f["autoresetlol-u0f<br/>Fix: PyInstaller missing hidden impor..."]
    class autoresetlol-u0f closed

    autoresetlol-15g ==> autoresetlol-3ki
    autoresetlol-15g -.-> autoresetlol-bvj
    autoresetlol-15g ==> autoresetlol-cag
    autoresetlol-3ki -.-> autoresetlol-bvj
    autoresetlol-3ki ==> autoresetlol-lm1
    autoresetlol-65h -.-> autoresetlol-bvj
    autoresetlol-cag ==> autoresetlol-65h
    autoresetlol-cag -.-> autoresetlol-bvj
    autoresetlol-cag ==> autoresetlol-lm1
    autoresetlol-lm1 -.-> autoresetlol-bvj
    autoresetlol-opt ==> autoresetlol-swx
    autoresetlol-swx ==> autoresetlol-0rr
```

---

## 🐛 autoresetlol-2e9 Fix: Missing Pillow dependency for PyAutoGUI

| Property | Value |
|----------|-------|
| **Type** | 🐛 bug |
| **Priority** | 🔥 Critical (P0) |
| **Status** | 🔵 in_progress |
| **Created** | 2025-12-20 22:00 |
| **Updated** | 2025-12-22 00:02 |

### Description

User báo lỗi failed to get pixel info. PyAutoGUI cần Pillow để lấy màu pixel.

### Acceptance Criteria

- [ ] Pillow installed.\n- [ ] pixel() works.\n- [ ] Rebuilt EXE works.

### Design

Install Pillow -> Test pixel() function -> Rebuild EXE.

<details>
<summary>📋 Commands</summary>

```bash
# Mark as complete
bd close autoresetlol-2e9

# Add a comment
bd comment autoresetlol-2e9 'Your comment here'

# Change priority (0=Critical, 1=High, 2=Medium, 3=Low)
bd update autoresetlol-2e9 -p 1

# View full details
bd show autoresetlol-2e9
```

</details>

---

## 🐛 autoresetlol-0v6 Fix focus stealing & Add Dimmer Persistence

| Property | Value |
|----------|-------|
| **Type** | 🐛 bug |
| **Priority** | 🔹 Medium (P2) |
| **Status** | 🟢 open |
| **Created** | 2025-12-22 19:31 |
| **Updated** | 2025-12-22 19:31 |
| **Labels** | backend, bugfix, frontend |

### Description

1. Fix Bug: The bot steals window focus (focus_client) when the timer resets, interrupting fullscreen gameplay. Removed the unnecessary focus call. 2. Feature: Add a toggle switch for the Dimmer. 3. Feature: Save/Load Dimmer settings (brightness level and toggle state) to config.json so they persist across restarts.

### Acceptance Criteria

- [ ] Bot does NOT bring League client to foreground when timer resets.
- [ ] Dimmer UI has a Toggle Switch.
- [ ] Dimmer brightness and Toggle state are saved to config.json.
- [ ] On app launch, the dimmer automatically applies the last saved settings.

### Design

See plan in conversation.

<details>
<summary>📋 Commands</summary>

```bash
# Start working on this issue
bd update autoresetlol-0v6 -s in_progress

# Add a comment
bd comment autoresetlol-0v6 'Your comment here'

# Change priority (0=Critical, 1=High, 2=Medium, 3=Low)
bd update autoresetlol-0v6 -p 1

# View full details
bd show autoresetlol-0v6
```

</details>

---

## 🐛 autoresetlol-47b Fix: Dimmer slider is capped at 20%, preventing further dimming

| Property | Value |
|----------|-------|
| **Type** | 🐛 bug |
| **Priority** | 🔹 Medium (P2) |
| **Status** | 🟢 open |
| **Created** | 2025-12-22 19:13 |
| **Updated** | 2025-12-22 19:13 |
| **Labels** | bugfix, frontend |

### Description

The user reported that the 'Ghost Dimmer' slider stops dimming the screen when it reaches a certain point (perceived as 40-50%), even when the slider is moved lower. Investigation of gui.py reveals the CTkSlider widget is configured with from_=20, which prevents the slider from outputting a value lower than 20. This is the cause of the issue. The current implementation limits the dimming capability unnecessarily. By changing the slider's minimum value to 0, we allow the user to access the full intended dimming range, while the backend logic in dimmer.py still safely prevents a complete black screen by clamping the minimum brightness at 10%. This directly addresses the user's request for more dimming control.

### Acceptance Criteria

- [ ] The dimmer slider can be moved all the way down to 0.
- [ ] The screen brightness should dim further than the current limit.
- [ ] A safeguard should remain in place to prevent the screen from going completely black. (The existing clamp at 10% in dimmer.py will handle this).

### Design

1. Open gui.py.
2. Locate the self.dimmer_slider CTkSlider widget.
3. Change the from_ parameter from 20 to 0.
4. Change the number_of_steps parameter from 80 to 100 to maintain a 1-to-1 step-to-value ratio.

<details>
<summary>📋 Commands</summary>

```bash
# Start working on this issue
bd update autoresetlol-47b -s in_progress

# Add a comment
bd comment autoresetlol-47b 'Your comment here'

# Change priority (0=Critical, 1=High, 2=Medium, 3=Low)
bd update autoresetlol-47b -p 1

# View full details
bd show autoresetlol-47b
```

</details>

---

## 📋 autoresetlol-abz Build AntiFateEngine v7.1 Release

| Property | Value |
|----------|-------|
| **Type** | 📋 task |
| **Priority** | 🔥 Critical (P0) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-22 19:26 |
| **Updated** | 2025-12-22 19:27 |
| **Closed** | 2025-12-22 19:27 |

### Description

Rebuild the application executable using PyInstaller after updates to dimmer.py (1% brightness limit).

### Acceptance Criteria

- [ ] AntiFateEngine_v7.1.exe is created in dist/ directory\n- [ ] Executable runs without crashing\n- [ ] Dimmer feature allows setting brightness to 1%

### Design

Execute uv run pyinstaller with AntiFateEngine_v7.1.spec. Use --clean and --noconfirm flags to ensure a fresh build.

---

## 🐛 autoresetlol-4nt Fix: ModuleNotFoundError customtkinter in exe build

| Property | Value |
|----------|-------|
| **Type** | 🐛 bug |
| **Priority** | 🔥 Critical (P0) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-22 19:22 |
| **Updated** | 2025-12-22 19:23 |
| **Closed** | 2025-12-22 19:23 |

### Description

User reported that the compiled executable fails to start due to missing 'customtkinter', despite it being installed via uv. This indicates PyInstaller was likely run in the global environment or a different environment than the one where dependencies are installed.

### Acceptance Criteria

- [ ] PyInstaller runs successfully without errors.\n- [ ] Log output does not show 'ModuleNotFoundError' for customtkinter.\n- [ ] dist/AntiFateEngine_v7.1.exe is regenerated and contains the missing module.

### Design

Use 'uv run' to execute PyInstaller. This ensures the command runs within the context of the project's virtual environment (.venv), allowing PyInstaller to detect and bundle 'customtkinter' correctly. Using the existing spec file AntiFateEngine_v7.1.spec.

---

## 📋 autoresetlol-9dr Build AntiFateEngine v7.1

| Property | Value |
|----------|-------|
| **Type** | 📋 task |
| **Priority** | 🔥 Critical (P0) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-22 19:19 |
| **Updated** | 2025-12-22 19:20 |
| **Closed** | 2025-12-22 19:20 |

### Description

Rebuild the application using PyInstaller with AntiFateEngine_v7.1.spec. User confirms customtkinter is installed via uv.

### Acceptance Criteria

- [ ] Command runs successfully\n- [ ] dist/AntiFateEngine_v7.1.exe exists

### Design

Execute 'pyinstaller AntiFateEngine_v7.1.spec --clean --noconfirm'. Verify output in dist/ folder.

---

## 🐛 autoresetlol-czf Bug: Fix CTkSwitch on_color argument

| Property | Value |
|----------|-------|
| **Type** | 🐛 bug |
| **Priority** | 🔥 Critical (P0) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-22 00:02 |
| **Updated** | 2025-12-22 00:02 |
| **Closed** | 2025-12-22 00:02 |

### Description

Fix ValueError caused by unsupported 'on_color' argument in CTkSwitch.

### Acceptance Criteria

- [ ] UI launches without crash.\n- [ ] Switch toggle works correctly.

### Design

Replace on_color with progress_color in gui.py.

### Notes

FIXED: Replaced on_color with progress_color for CTkSwitch.

---

## ✨ autoresetlol-0fb Update: Separate Cancel and Find Match coordinates

| Property | Value |
|----------|-------|
| **Type** | ✨ feature |
| **Priority** | 🔥 Critical (P0) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-21 15:39 |
| **Updated** | 2025-12-21 15:42 |
| **Closed** | 2025-12-21 15:42 |

### Description

Game UI thay đổi, nút Hủy và Tìm Trận không trùng nhau. Cần tách tọa độ.

### Acceptance Criteria

- [ ] Config has cancel_button_pos.\n- [ ] Bot clicks separate coordinates for reset.

### Design

Add cancel_button_pos to config. Update bot logic to click cancel pos then find pos.

---

## 🐛 autoresetlol-9ei Fix: Calibration color error due to mouse hover

| Property | Value |
|----------|-------|
| **Type** | 🐛 bug |
| **Priority** | 🔥 Critical (P0) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-20 22:27 |
| **Updated** | 2025-12-20 22:29 |
| **Closed** | 2025-12-20 22:29 |

### Description

Logic lấy màu bị sai do hiệu ứng hover. Cần di chuột ra chỗ khác trước khi lấy màu.

### Acceptance Criteria

- [ ] Mouse moves away automatically during calibration.\n- [ ] Color captured is the non-hover color.

### Design

Update gui.py: Get Pos -> Move Mouse Away -> Wait -> Get Color at Pos.

---

## 🐛 autoresetlol-u0f Fix: PyInstaller missing hidden imports for Pillow/PyScreeze

| Property | Value |
|----------|-------|
| **Type** | 🐛 bug |
| **Priority** | 🔥 Critical (P0) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-20 22:22 |
| **Updated** | 2025-12-20 22:23 |
| **Closed** | 2025-12-20 22:23 |

### Description

Build lại EXE với hidden imports vì lỗi runtime thiếu thư viện.

### Acceptance Criteria

- [ ] EXE runs without import error.

### Design

Add explicit imports in main.py. Use --hidden-import flag during build.

---

## 📋 autoresetlol-3ki Core: Bot Logic & Threading Engine

| Property | Value |
|----------|-------|
| **Type** | 📋 task |
| **Priority** | 🔥 Critical (P0) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-20 21:06 |
| **Updated** | 2025-12-20 21:24 |
| **Closed** | 2025-12-20 21:24 |

### Description

Viết logic chính của bot chạy trên luồng riêng (Worker Thread).

### Acceptance Criteria

- [ ] Bot chạy trên thread riêng, GUI không bị đơ.\n- [ ] Phát hiện đúng màu pixel tại tọa độ.\n- [ ] Thực hiện đúng quy trình Reset Queue.\n- [ ] Tự động dừng khi bấm Stop hoặc Accept xong.

### Design

Sử dụng module  để chạy vòng lặp vô tận (while loop) mà không block GUI.\nLogic:\n- Loop 1s/lần.\n- Check pixel 'Accept' -> Click -> Stop.\n- Check pixel 'Finding' -> Count Timer -> Reset Queue nếu quá giờ.\n- Reset Queue: Click Cancel -> Wait -> Click Find Match.\n- Sử dụng PyAutoGUI để get pixel color và click.

### Dependencies

- 🔗 **parent-child**: `autoresetlol-bvj`
- ⛔ **blocks**: `autoresetlol-lm1`

---

## 🚀 autoresetlol-bvj Epic: The Anti-Fate Engine - Auto Accept & Reset Queue

| Property | Value |
|----------|-------|
| **Type** | 🚀 epic |
| **Priority** | 🔥 Critical (P0) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-20 21:05 |
| **Updated** | 2025-12-20 21:26 |
| **Closed** | 2025-12-20 21:26 |

### Description

Xây dựng ứng dụng desktop Python tự động chấp nhận trận đấu và reset hàng chờ LMHT để tránh autofill ở High Elo.

### Acceptance Criteria

- [ ] Tool chạy ổn định trên Windows.\n- [ ] Tự động accept khi có trận.\n- [ ] Tự động reset queue sau khoảng thời gian định trước.\n- [ ] Không bị treo UI (Not Responding).

### Design

Stack: Python, Tkinter, PyAutoGUI, Threading. Output: .exe file.

---

## 📋 autoresetlol-67v Build: AntiFateEngine V7.1 (Ghost Update)

| Property | Value |
|----------|-------|
| **Type** | 📋 task |
| **Priority** | ⚡ High (P1) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-22 00:00 |
| **Updated** | 2025-12-22 00:09 |
| **Closed** | 2025-12-22 00:09 |

### Description

Build new version with dimmer and pin toggle features.

### Acceptance Criteria

- [ ] EXE built successfully.\n- [ ] Dimmer works.\n- [ ] Pin toggle works.

### Design

Use uv run pyinstaller. Same specs as V7.

### Notes

COMPLETED: Built V7.1. Retried after closing running instance. Success.

---

## ✨ autoresetlol-a2p Feature: Ghost Dimmer & Pin Toggle

| Property | Value |
|----------|-------|
| **Type** | ✨ feature |
| **Priority** | ⚡ High (P1) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-21 23:58 |
| **Updated** | 2025-12-21 23:59 |
| **Closed** | 2025-12-21 23:59 |

### Description

Add Gamma Ramp based dimmer and Always-on-Top toggle.

### Acceptance Criteria

- [ ] Dimmer changes screen brightness without affecting pixel reading.\n- [ ] Pin toggle works.\n- [ ] Brightness resets on exit.

### Design

1. dimmer.py: Use SetDeviceGammaRamp for hardware dimming. 2. gui.py: Add CTkSwitch for topmost toggle. Add CTkSlider for brightness. Handle cleanup on exit.

### Notes

COMPLETED: Added dimmer.py with Gamma Ramp logic. Updated gui.py with Pin Toggle (switch) and Ghost Dimmer (slider). Handled cleanup on exit.

---

## 📋 autoresetlol-opt Build: AntiFateEngine V7 (uv + customtkinter)

| Property | Value |
|----------|-------|
| **Type** | 📋 task |
| **Priority** | ⚡ High (P1) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-21 23:29 |
| **Updated** | 2025-12-21 23:37 |
| **Closed** | 2025-12-21 23:37 |

### Description

Build the new version with uv and customtkinter support.

### Acceptance Criteria

- [ ] EXE built successfully.\n- [ ] EXE runs on clean environment.\n- [ ] UI renders correctly in EXE.

### Design

Use . Ensure customtkinter data files are included.

### Notes

COMPLETED: Built AntiFateEngine V7 with uv and PyInstaller. Included customtkinter resources. EXE located in dist/.

### Dependencies

- ⛔ **blocks**: `autoresetlol-swx`

---

## ✨ autoresetlol-swx UI: Refactor to CustomTkinter (Shadcn Dark Mode)

| Property | Value |
|----------|-------|
| **Type** | ✨ feature |
| **Priority** | ⚡ High (P1) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-21 23:29 |
| **Updated** | 2025-12-21 23:35 |
| **Closed** | 2025-12-21 23:35 |

### Description

Replace standard tkinter with customtkinter to achieve a modern, minimalist, dark mode UI inspired by Shadcn.

### Acceptance Criteria

- [ ] UI uses customtkinter.\n- [ ] Dark mode enabled.\n- [ ] Start/Stop/Calibrate buttons styled correctly.\n- [ ] Input field styled correctly.\n- [ ] Window is topmost and non-resizable.

### Design

Theme: Dark. Colors: Zinc/Slate tones. Components: CTkButton (Primary: White/Black, Destructive: Muted Red, Ghost: Outline), CTkEntry, CTkLabel. Layout: Clean, spacing, rounded corners.

### Notes

COMPLETED: Replaced standard tkinter with CustomTkinter. Applied Shadcn Dark Mode styling (Zinc palette). Added threaded calibration.

### Dependencies

- ⛔ **blocks**: `autoresetlol-0rr`

---

## 📋 autoresetlol-0rr Infra: Migrate to uv package manager

| Property | Value |
|----------|-------|
| **Type** | 📋 task |
| **Priority** | ⚡ High (P1) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-21 23:29 |
| **Updated** | 2025-12-21 23:34 |
| **Closed** | 2025-12-21 23:34 |

### Description

Replace pip with uv for faster and better dependency management.

### Acceptance Criteria

- [ ] uv installed and initialized.\n- [ ] All dependencies added via uv.\n- [ ] Project runs using .

### Design

Initialize uv project. Add dependencies: pyautogui, pillow, pyscreeze, pyinstaller, customtkinter, packaging. Remove old requirements if any.

### Notes

COMPLETED: Migrated to uv. Added dependencies: pyautogui, pillow, pyscreeze, pyinstaller, customtkinter, packaging, pywin32. Verified imports work.

---

## ✨ autoresetlol-dhd Feature: Persistent Supervisor Logic

| Property | Value |
|----------|-------|
| **Type** | ✨ feature |
| **Priority** | ⚡ High (P1) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-21 20:35 |
| **Updated** | 2025-12-21 21:37 |
| **Closed** | 2025-12-21 21:37 |

### Description

Bot runs continuously. After Accept, enters Standby mode. If Queue detected again (dodge), resumes Searching. Only stops on manual Stop.

### Design

Use a state machine: SEARCHING -> MATCH_FOUND -> STANDBY. In STANDBY, periodically check for Queue pixels. If Queue detected, revert to SEARCHING.

---

## 📋 autoresetlol-dtv Refactor: Add Window Focus Logic

| Property | Value |
|----------|-------|
| **Type** | 📋 task |
| **Priority** | ⚡ High (P1) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-21 20:35 |
| **Updated** | 2025-12-21 21:37 |
| **Closed** | 2025-12-21 21:37 |

### Description

Replace unreliable taskbar pixel check with win32gui/pygetwindow to force LoL client to foreground if inactive for > 2 mins.

### Design

Use win32gui to find window by title 'League of Legends'. If found and not foreground, setForeground.

---

## 📋 autoresetlol-lm1 Setup: Project Structure & Config Manager

| Property | Value |
|----------|-------|
| **Type** | 📋 task |
| **Priority** | ⚡ High (P1) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-20 21:07 |
| **Updated** | 2025-12-20 21:18 |
| **Closed** | 2025-12-20 21:18 |

### Description

Khởi tạo cấu trúc dự án và module quản lý file config.json.

### Acceptance Criteria

- [ ] Project chạy được file main.py rỗng.\n- [ ] Tự động sinh file config.json nếu chưa có.\n- [ ] Đọc được giá trị từ config.json vào biến.

### Design

Tạo file main.py và config.py. Module Config phải có khả năng load/save file json. Nếu file không tồn tại, tạo file mặc định với các giá trị mẫu (dummy values) cho tọa độ và màu sắc.

### Dependencies

- 🔗 **parent-child**: `autoresetlol-bvj`

---

## 📋 autoresetlol-cag UI: Tkinter Dashboard Implementation

| Property | Value |
|----------|-------|
| **Type** | 📋 task |
| **Priority** | ⚡ High (P1) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-20 21:07 |
| **Updated** | 2025-12-20 21:20 |
| **Closed** | 2025-12-20 21:20 |

### Description

Xây dựng giao diện người dùng (GUI) bằng Tkinter.

### Acceptance Criteria

- [ ] GUI hiển thị đúng layout.\n- [ ] Cửa sổ luôn nổi trên cùng (topmost).\n- [ ] Nhập được số vào ô input.\n- [ ] Các nút bấm phản hồi (print ra console là được).

### Design

Cửa sổ nhỏ gọn, Always on Top. Các thành phần:\n1. Label trạng thái (Status).\n2. Input box (Entry) cho thời gian reset (giây).\n3. Button 'Bắt Đầu' (Start).\n4. Button 'Dừng Lại' (Stop).\n5. Button 'Lấy Tọa Độ' (Calibrate) - Optional but recommended.\nLayout dùng pack() hoặc grid() cho gọn.

### Dependencies

- 🔗 **parent-child**: `autoresetlol-bvj`
- ⛔ **blocks**: `autoresetlol-lm1`
- ⛔ **blocks**: `autoresetlol-65h`

---

## 🧹 autoresetlol-30f Release Notes: AntiFateEngine V6

| Property | Value |
|----------|-------|
| **Type** | 🧹 chore |
| **Priority** | 🔹 Medium (P2) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-21 22:03 |
| **Updated** | 2025-12-21 22:34 |
| **Closed** | 2025-12-21 22:34 |

### Description

Final V6 Release. Features: Smart Focus (no flash if active), Immortal Supervisor, Dodge Auto-Reset, Debounce.

---

## 📋 autoresetlol-15g Build: PyInstaller Packaging

| Property | Value |
|----------|-------|
| **Type** | 📋 task |
| **Priority** | 🔹 Medium (P2) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-20 21:05 |
| **Updated** | 2025-12-20 21:26 |
| **Closed** | 2025-12-20 21:26 |

### Description

Đóng gói ứng dụng thành file .exe duy nhất.

### Acceptance Criteria

- [ ] File .exe chạy độc lập trên máy không cài Python.\n- [ ] Không hiện cửa sổ console đen ngòm.\n- [ ] Tool hoạt động đúng logic sau khi đóng gói.

### Design

Sử dụng PyInstaller với flag --onefile và --windowed (noconsole). Đảm bảo file config.json nằm cùng thư mục với file exe sau khi build.

### Dependencies

- 🔗 **parent-child**: `autoresetlol-bvj`
- ⛔ **blocks**: `autoresetlol-cag`
- ⛔ **blocks**: `autoresetlol-3ki`

---

## 📋 autoresetlol-65h Feature: Calibration Helper

| Property | Value |
|----------|-------|
| **Type** | 📋 task |
| **Priority** | 🔹 Medium (P2) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-20 21:05 |
| **Updated** | 2025-12-20 21:22 |
| **Closed** | 2025-12-20 21:22 |

### Description

Tính năng hỗ trợ lấy tọa độ và màu sắc cho user.

### Acceptance Criteria

- [ ] Lấy được tọa độ và màu sắc tại vị trí chuột sau khi delay.\n- [ ] Hiển thị thông tin rõ ràng cho user copy vào config.

### Design

Khi bấm nút 'Lấy Tọa Độ', tool sẽ đợi 3 giây (để user di chuột) rồi in ra tọa độ (x, y) và màu (r, g, b) của vị trí con trỏ chuột hiện tại. Có thể hiển thị lên popup hoặc update thẳng vào config (nâng cao).

### Dependencies

- 🔗 **parent-child**: `autoresetlol-bvj`

---

## 📋 autoresetlol-gw7 Clarify project goal and Obsidian syntax usage

| Property | Value |
|----------|-------|
| **Type** | 📋 task |
| **Priority** | 🔹 Medium (P2) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-20 20:29 |
| **Updated** | 2025-12-21 22:36 |
| **Closed** | 2025-12-21 22:36 |

### Description

The user provided a link to Obsidian syntax documentation but didn't specify the task. Need to clarify if we are building a knowledge base, a tool, or just setting up the repo structure.

---

## 📋 autoresetlol-1p0 Docs: V6 User Guide

| Property | Value |
|----------|-------|
| **Type** | 📋 task |
| **Priority** | ☕ Low (P3) |
| **Status** | ⚫ closed |
| **Created** | 2025-12-21 22:34 |
| **Updated** | 2025-12-21 22:36 |
| **Closed** | 2025-12-21 22:36 |

### Description

Guide user on how to use V6 features (Force Focus, Dodge Reset) and how to test them.

---


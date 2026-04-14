# Plan: Window-Behind Detection

## Context
The user overlays Intricate's rolled-up curtain strip on top of other apps. They want the app to know what window is directly behind it — starting with detecting the Claude desktop app. This enables the dock snap button to intelligently position itself based on the app underneath, and opens the door for future context-aware features.

## Approach

Create `utils/window_behind.py` — a lightweight ctypes utility that finds the window directly behind Intricate in Z-order.

### How it works
1. Get Intricate's own HWND via `int(self.winId())`
2. Walk Z-order with `GetWindow(hwnd, GW_HWNDNEXT)` skipping invisible/minimized windows
3. For the first visible window found, return a dict with:
   - `hwnd` — the window handle
   - `title` — window title text (`GetWindowTextW`)
   - `exe` — executable name (`GetWindowThreadProcessId` → `QueryFullProcessImageNameW`)
   - `rect` — window geometry (`GetWindowRect`)

### Reuse from existing code
- `OSClickMonitor.py` already has the PID → exe resolution pattern with proper 64-bit pointer handling — reuse the same ctypes setup for `user32` and `kernel32`

### Integration
- Expose a simple `get_window_behind(hwnd) -> dict | None` function
- Wire it to the dock button or a periodic check in `main_window.py`
- For now: call it on dock button press and log/display the result to verify it works

### Files to create/modify
- **Create:** `utils/window_behind.py` — the detection utility
- **Modify:** `main_window.py` — call from `_toggle_dock_position` and log result

### Win32 functions needed (all via ctypes, no pywin32)
- `GetWindow(hwnd, GW_HWNDNEXT)` — walk Z-order
- `IsWindowVisible(hwnd)` — skip hidden windows
- `IsIconic(hwnd)` — skip minimized windows
- `GetWindowTextW(hwnd, buf, len)` — window title
- `GetWindowRect(hwnd, RECT)` — window geometry
- `GetWindowThreadProcessId` — already in OSClickMonitor
- `QueryFullProcessImageNameW` — already in OSClickMonitor

## Verification
1. Launch Intricate over the Claude desktop app
2. Click the dock snap button
3. Check the info label / log output shows "Claude" as the window behind
4. Move Intricate over Chrome, click again — should show Chrome

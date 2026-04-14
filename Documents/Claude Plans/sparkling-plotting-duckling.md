# Plan: The Settlers — Family UI Alignment

## Context

The Settlers is part of the Single Shared Braincell app family but its UI predates the shared framework. It currently has its own local Theme.py, PrettyButton.py, and a different grid layout. Intricate and Notepad++Duplex+Turbo both use the `pretty_widgets` package and share the canonical 3-row grid layout: top toolbar, center content (with optional sidebar), bottom toolbar. The Settlers needs to join the family.

## Step 1: Switch to pretty_widgets package

The Settlers has local `Theme.py` and `PrettyButton.py` that duplicate the package. Replace with imports from `pretty_widgets`:
- `from pretty_widgets.graphics.Theme import Theme`
- `from pretty_widgets.widgets.PrettyButton import button`
- Delete local `Theme.py` and `PrettyButton.py`

The Settlers' `toml_writer.py` handles the shared TOML read/write — this stays as-is since it's the write side (Intricate only reads). But settings loading for Theme should go through `pretty_widgets.utils.settings`.

## Step 2: Rewrite main_window.py with family layout

Replace the current MainWindow with the canonical grid:

**Row 0 — Top Toolbar** (fixed height):
- Draggable title bar
- Title label: "The Settlers"
- Curtain toggle button (collapse/expand)
- Tray / Maximize / Close buttons (pinned right, absolute positioned)
- Same pattern as Intricate's `_build_top_toolbar` and `_reposition_exit_btn`

**Row 1 — Center** (stretches):
- Left sidebar with category icon buttons (same pattern as Intricate)
- Center content: the tabbed settings editor (existing functionality, preserved)
- Sidebar categories for The Settlers: Colors, Icons, Layout, Animation (maps to TOML sections)

**Row 2 — Bottom Toolbar** (fixed height):
- Status label (left) — existing StatusBarHandler pipes into this
- Save button (right)
- Same pattern as Intricate/Notepad++ bottom toolbar

## Step 3: Preserve existing functionality

Keep everything that works:
- Dynamic tab generation from TOML sections
- Hot-reload via SettingsWatcher (toml_writer.py)
- Atomic saves with type preservation
- System tray integration
- Curtain animation
- Browse buttons for icon paths
- StatusBarHandler logger integration

## Step 4: Update main.py boot sequence

Align with Intricate's boot pattern:
- Import `pretty_widgets.utils.settings` for TOML loading
- Call `Theme.reload()` before window construction
- Init settings watcher, connect to `Theme.reload()`

## Files to modify (in The Settlers repo)
- `main.py` — align boot sequence with pretty_widgets
- `main_window.py` — full rewrite to family layout

## Files to delete (in The Settlers repo)
- `Theme.py` — replaced by pretty_widgets.graphics.Theme
- `PrettyButton.py` — replaced by pretty_widgets.widgets.PrettyButton

## Files to keep unchanged
- `toml_writer.py` — The Settlers' own TOML write engine (its core purpose)
- `utils/logger.py` — already matches family pattern
- `utils/settings.py` — QSettings for local state (window geometry etc.)

## Verification
- `python main.py` from The Settlers directory
- Window appears with familiar 3-row layout
- Top toolbar: draggable, curtain toggle, tray/max/close buttons
- Center: tabbed settings editor (same content as before)
- Bottom: status bar with save button
- Edit a value → Save → Intricate picks up the change via its watcher
- Tray icon still works (minimize, restore, restart, quit)
- Curtain animation still works

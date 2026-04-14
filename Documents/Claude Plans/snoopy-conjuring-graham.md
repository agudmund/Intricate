# Add Tabbed Settings UI to The Settlers

## Context
The Settlers is a centralized settings app for a family of apps. Currently it shows all `[theme.icons]` fields in a flat list in the central area. As more TOML sections are used (`theme.colors`, `theme.icons`, `theme.curtains`), the UI needs tabs to organize settings by category.

## Approach

### 1. Seed `settings.toml` with all known sections
Add `[theme.colors]` and `[theme.curtains]` with their Theme.py defaults so the tabs have content to show.

```toml
[theme.colors]
window_bg = "#282828"
primary_border = "#6b5a47"
text_primary = "#d2d1cf"
backdrop = "#2a2a3a"

[theme.icons]
curtains = "iconic.png"
...existing...

[theme.curtains]
pace_ms = 450
easing = "OutExpo"
```

### 2. Add generic TOML read/write helpers to `toml_writer.py`
- `read_toml() -> dict` — returns the full parsed TOML
- `write_toml(data: dict)` — atomic write of the full dict
- Keep existing `read_theme_icons()` / `write_theme_icons()` working (they call the new helpers internally)

### 3. Refactor `main_window.py` central area to use `QTabWidget`
- Replace the current flat `_build_icon_fields()` content with a `QTabWidget`
- One tab per second-level TOML section: "Colors", "Icons", "Curtains"
- Each tab is a scrollable area with label + field rows built dynamically from the TOML keys
- Icons tab keeps its Browse buttons (file picker)
- Colors/curtains tabs get plain `QLineEdit` fields
- Style the tab bar to match the warm dark theme

### 4. Update save to write all sections
- `_save()` collects values from all tabs and writes the full TOML back

### 5. Update hot-reload to refresh all tabs
- `_on_settings_file_changed()` updates fields across all tabs

## Files Modified
- `settings.toml` — add colors + curtains sections
- `toml_writer.py` — add `read_toml()`, `write_toml()`
- `main_window.py` — QTabWidget, per-section tab building, save/reload for all

## Verification
- Run `python main.py` — window should show 3 tabs: Colors, Icons, Curtains
- Each tab shows the correct key/value fields from settings.toml
- Edit a value, click Save, verify settings.toml is updated
- Edit settings.toml externally, verify hot-reload updates the fields

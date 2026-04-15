# Settlers Category Design Brief

Visual language and layout specification for settings categories in The Settlers, the companion configuration app for Intricate. This brief codifies the lookdev established in the "Intricate's Titlebar Locations" (dock_offsets) category and extended to the "About Node" category.

## Page Structure

Each category occupies a scrollable tab page built by `_ensure_tab()`.

- **Container:** `QScrollArea` with transparent background and no border
- **Scrollbar:** 8px wide, transparent background, handle uses `Theme.primaryBorder` with 4px border radius
- **Inner widget:** `QWidget`, transparent background
- **Layout:** `QVBoxLayout` with 20px horizontal margins, 16px vertical margins, 1px item spacing
- **Tail anchoring:** A stretch item and optional description label are pinned to the bottom via `_tail_count` tracking. New field rows are inserted above the tail so the description always stays at the bottom

## Slider Row

The canonical control for integer attributes. One row per TOML key.

**Layout (left to right):**

| Widget | Type | Width | Details |
|--------|------|-------|---------|
| Label | `pretty_label` | 140px fixed | 12pt, display name derived from TOML key (`_` to space, title case) |
| Value readout | `pretty_label` | 36px fixed | 12pt, right-aligned, `#ffb6c1` pink, transparent background, no border |
| Slider | `PrettySlider` | fills remaining | Horizontal, `slider_handle.png` at 24px, 24px fixed height |
| Hidden field | `QLineEdit` | hidden | Stores the string value for TOML sync via `_on_field_changed` |

**Range:** Determined per category. Dock offsets use `(0, screen_height)`. About Node attributes use `(-50, 50)`. Future categories set their own range as appropriate.

**Bidirectional sync:**
- Slider `valueChanged` writes to the hidden field and updates the value readout label
- Hidden field `textChanged` updates the slider position (with `blockSignals` to prevent loops) and the readout label
- The hidden field connects to the shared `_on_field_changed` pipeline which writes back to `settings.toml`

**Optional apply button:** Dock offsets include a 24x24 flat icon button (no border, transparent background) that queries Intricate's current window position and sets the slider to that value. This is category-specific and not part of the base slider pattern.

## Color Swatch Cell

For hex color attributes (values starting with `#`). Arranged horizontally when multiple swatches share a row.

**Layout (vertical stack per swatch):**

| Widget | Alignment | Details |
|--------|-----------|---------|
| Label | Centered | Chandler42 font, 8pt, italic, weight 500, transparent background |
| Swatch | H-centered | `QFrame`, 110x70px, solid background color, 1px `Theme.primaryBorder` border, 4px radius |
| Hex input | Centered | `QLineEdit`, max 9 chars, same Chandler42 styling as label |

**Cell container:** `QVBoxLayout` with 0px top/bottom margins, 2px left/right, 2px spacing, top + center alignment.

**Sync:** Typing in the hex input updates the hidden `QLineEdit` for TOML sync and repaints the swatch background in real time. Only applies the color when the value is a valid hex format (`#RGB`, `#RRGGBB`, or `#RRGGBBAA`).

## Section Description

Optional poetic/explanatory text below all fields in a category.

- **Widget:** `pretty_label`, 9pt font size
- **Opacity:** 0.55 (applied via `QGraphicsOpacityEffect`)
- **Word wrap:** Disabled (multi-line via explicit `\n` in the description string)
- **Alignment:** Left + Top
- **Margins:** 16px top margin to separate from the last field row
- **Defined in:** `_SECTION_DESCRIPTIONS` dict, keyed by section path

## Theme Dependency

All visual values flow from `Theme` except the pink value readout color `#ffb6c1`, which is the one deliberate hardcoded accent. Background colors, border colors, text colors, and scrollbar styling all reference Theme attributes so they hot-reload when `settings.toml` changes.

## Tag Chip Row

For TOML fields that store a Python list as a string (e.g. `"['__pycache__', 'node_modules']"`). Each list entry renders as a removable pill. A small inline input at the row's right edge adds new entries.

**Layout (left to right):**

| Widget | Type | Width | Details |
|--------|------|-------|---------|
| Label | `pretty_label` | 200px fixed | 12pt, display name derived from TOML key |
| Chip container | `QWidget` (stretch=1) | fills remaining | `QHBoxLayout`, spacing 4px, stretch appended after chips |
| Add input | `QLineEdit` | 60px fixed | Pill-shaped, Chandler42 italic 9px, placeholder "+", returnPressed adds entry |
| Hidden field | `QLineEdit` | hidden | Canonical string representation — `str(list)` — synced to TOML |

**Chip anatomy:**
- `QFrame`, fixed height 20px, `QSizePolicy.Fixed` both axes
- `QHBoxLayout`, margins `(8, 0, 4, 0)`, spacing 2px
- `QLabel` — Chandler42 italic, 9px, `Theme.textPrimary`
- `QPushButton("×")` — 12×12px, flat, transparent; hover turns `#d87a9e`
- Border radius 10px (half of 20px height → true pill shape)
- Background `Theme.windowBg`, border `1px solid Theme.primaryBorder`

**Data flow:** `ast.literal_eval` parses the hidden field text → Python list → chips rebuild. Removing or adding a chip immediately serializes back to `str(list)` and triggers the standard `_on_field_changed` → TOML write pipeline.

**Add input tooltip:** "Type a name and press Enter — use > for nested paths (e.g. Documents>data)"

## Boolean Toggle Row

For TOML fields that store string booleans (`"True"` / `"False"`). Rendered as a `PrettyCheckbox` whose label column aligns with slider label columns.

**Layout (left to right):**

| Widget | Type | Details |
|--------|------|---------|
| `PrettyCheckbox` | `pretty_widgets.PrettyCheckbox` | `indicator_right=True` (default); `_label.setFixedWidth(200)` pins label to the shared label column |
| Stretch | — | Fills remaining row width after the indicator |
| Hidden field | `QLineEdit` (hidden) | Stores `"True"` or `"False"` for TOML sync |

**Signal:** `cb.toggled.connect(lambda checked, f=field: f.setText("True" if checked else "False"))`

**Alignment rule:** `cb._label.setFixedWidth(200)` must be set after constructing the checkbox so the indicator lands at the same x-position as slider controls and chip containers — the 200px label column is the shared visual axis of the category page.

## Adding a New Category

1. Add the TOML section (e.g. `[node.xxx]`) to `settings.toml`
2. Register a display name in `_SECTION_LABELS`
3. Optionally define field grouping in `_SECTION_FIELD_ORDER` — each inner list is a chunk separated by a spacer; use this to group related controls visually
4. Optionally add a description in `_SECTION_DESCRIPTIONS`
5. Add a section-specific branch in `_add_field_row()` for any fields needing custom controls:
   - Integer attributes → Slider Row
   - Hex color attributes → Color Swatch Cell (automatic, no branch needed)
   - List attributes (TOML string-encoded Python lists) → Tag Chip Row
   - Boolean string attributes (`"True"`/`"False"`) → Boolean Toggle Row
   - Everything else → plain `QLineEdit` (default fallback)

**The Tree Node category is the worked example** of combining all three custom control types in one page: one slider (max_depth), three chip rows (exclude lists), three boolean toggles (display options), with `_SECTION_FIELD_ORDER` providing the visual grouping.

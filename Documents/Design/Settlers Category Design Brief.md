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

## Adding a New Category

1. Add the TOML section (e.g. `[node.xxx]`) to `settings.toml`
2. Register a display name in `_SECTION_LABELS`
3. Optionally define field grouping in `_SECTION_FIELD_ORDER`
4. Optionally add a description in `_SECTION_DESCRIPTIONS`
5. Add a section-specific branch in `_add_field_row()` if the fields need sliders or other custom controls (otherwise they render as plain `QLineEdit` text fields, with hex colors automatically getting swatch cells)

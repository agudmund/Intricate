# Settlers Category Design Brief

Visual language and layout specification for settings categories in The Settlers, the companion configuration app for Intricate. This brief codifies the lookdev established in the "Intricate's Titlebar Locations" (dock_offsets) category and extended to the "About Node" category.

## The Four-Column Row Grid

Every row in every category — regardless of control type — must follow this layout:

```
labels (200px) | shorthands (36px) | content (stretch) | applicators (80px)
```

| Column | Width | Purpose |
|--------|-------|---------|
| **labels** | 200px fixed | Field name. Always a `pretty_label` at 12pt. |
| **shorthands** | 36px fixed | Value readout (pink `#ffb6c1`) for sliders. **Empty placeholder** for chip and checkbox rows — the space is reserved even when unused. |
| **content** | stretch (fills) | The interactive control: slider, chip container, checkbox indicator. |
| **applicators** | 80px fixed | Action widget: apply button, add-input pill, or empty placeholder. Always the same width regardless of what's inside. |

These values are defined as class constants on `MainWindow`:
```python
_COL_LABEL      = 200
_COL_SHORTHAND  =  36
_COL_APPLICATOR =  80
```

**Rule:** A row that lacks a particular column still reserves its width. Use `QSpacerItem(width, 24, QSizePolicy.Fixed, QSizePolicy.Fixed)` as the placeholder. Every row is the same effective width — the four columns are the visual skeleton of the category page.

## Page Structure

Each category occupies a scrollable tab page built by `_ensure_tab()`.

- **Container:** `QScrollArea` with transparent background and no border
- **Scrollbar:** 8px wide, transparent background, handle uses `Theme.primaryBorder` with 4px border radius
- **Inner widget:** `QWidget`, transparent background
- **Layout:** `QVBoxLayout` with 20px horizontal margins, 16px vertical margins, 1px item spacing
- **Tail anchoring:** A stretch item and the description label are pinned to the bottom via `_tail_count` tracking. New field rows are inserted above the tail so the description always stays at the bottom

## Vertical Rhythm Between Rows

Adjacent rows of the **same control type** sit at the layout's base 1 px spacing — the rhythm reads as a single uniform stride. **Chunk spacers (12 px) are reserved for control-type transitions only**: slider → swatch row, slider → chip row, slider → boolean toggle, etc.

Practical consequence for `_SECTION_FIELD_ORDER`: do not split a homogeneous run of sliders across multiple chunks just to express semantic groups — the chunks would introduce uneven gaps that read as a layout bug. Group all sliders into one chunk and let row order carry the grouping. Reach for chunk spacers only where the control type actually changes.

## Slider Row

The canonical control for integer attributes. One row per TOML key.

**Layout (left to right):**

| Widget | Type | Width | Details |
|--------|------|-------|---------|
| Label | `pretty_label` | `_COL_LABEL` (200px) | 12pt, display name derived from TOML key (`_` to space, title case) |
| Value readout | `pretty_label` | `_COL_SHORTHAND` (36px) | 12pt, right-aligned, `#ffb6c1` pink, transparent background, no border |
| Slider | `PrettySlider` | fills remaining | Horizontal, `slider_handle.png` at 24px, 24px fixed height |
| Applicator | `QSpacerItem` or button | `_COL_APPLICATOR` (80px) | Empty spacer for plain sliders; apply button (`setFixedSize(80, 24)`) for dock offsets |
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
| Swatch | H-centered | `_DraggableSwatch` (QFrame subclass), 110x70px, solid background color, 1px `Theme.primaryBorder` border, 4px radius. OpenHand cursor at rest, ClosedHand during drag |
| Hex input | Centered | `QLineEdit`, max 9 chars, same Chandler42 styling as label |

**Cell container:** `QVBoxLayout` with 0px top/bottom margins, 2px left/right, 2px spacing, top + center alignment.

**Gentle drag gesture:** The swatch itself is the picker. Press and drag vertically to shift HSL lightness — up lightens, down darkens. Calibrated at 1.5 px per lightness unit (0–255 scale), so a ~100 px drag covers roughly two-thirds of the range. Hue and saturation stay fixed; only lightness moves. Alpha is preserved across `#RGB`, `#RRGGBB`, and `#RRGGBBAA` forms.

**Philosophy:** This is a nudge, not a wheel. For hue-wide colour work, Photoshop and color.adobe.com remain the right tools. The Settlers swatch is the quiet one-axis adjustment that lives where you're already looking — no modal dialog, no RGBA picker, no colour-space navigation.

**Sync contract:** The swatch emits `colorDragged(hex)` live during the drag, which feeds the hex input's `setText`, which drives the single `_sync` path that writes the hidden `QLineEdit` and repaints the swatch. One write path whether the user types or drags — both end up in TOML through the same pipeline. Only applies the color when the value is a valid hex format (`#RGB`, `#RRGGBB`, or `#RRGGBBAA`).

### Convention: `bg_color` / `bg_color_front` — Two-State Depth Colors

Each node type that participates in the depth-toggle feedback pattern exposes a paired `bg_color` (back / normal Z-layer) and `bg_color_front` (pinned-forward) in its `[node.xxx]` TOML section. The front colour is usually a slightly HSL-lifted variant of the back — same hue and saturation, higher lightness — "a slightly stronger emphasis of the same colour" that reads as pinned without shouting.

**Node-side wiring:** each participating node overrides `_bg_color()` to branch on `self.data.depth_front`, and overrides `_apply_depth()` to stop the ambient `bg_anim`, null out `_bg_base`/`_current_bg`, then `setBrush(self._bg_color())`. The animation-stop-before-setBrush order is load-bearing — otherwise `_on_bg_changed` fires after the depth toggle and overwrites the brush with the outgoing target.

**Current adopters:** AboutNode, GitNode. Once a third node joins, consider lifting the pattern into BaseNode with hookpoints. Until then, per-node override is the convention.

**Not yet resolved in the convention:** when a node has a custom `node_tint` (user-chosen per-instance colour), the tint currently wins regardless of `depth_front`. A future refinement could HSL-lift the tint for the front state so tinted nodes also get depth-feedback — held off until a concrete use case calls for it.

## Section Description

Every category has a description — the small italic note at the bottom that explains what the category does and why a setting might want adjusting. Treat descriptions as standard furniture, not optional flourish — register a string in `_SECTION_DESCRIPTIONS` for every section that ships.

**Tone:** quiet, indirect, gently personifying. Explain what the category controls and why someone would touch it; don't command the reader. Em-dashes for asides. Short paragraphs separated by blank lines. Intricate is "she" when personified; the user is implicit. Look at `intricate.color_picker`, `intricate.dock_offsets`, and `intricate.joy` for canonical voice.

**Style:**
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
| Label | `pretty_label` | `_COL_LABEL` (200px) | 12pt, display name derived from TOML key |
| Shorthand spacer | `QSpacerItem` | `_COL_SHORTHAND` (36px) | Empty placeholder — reserves the column even though chips have no value readout |
| Chip container | `QWidget` (stretch=1) | fills remaining | `QHBoxLayout`, spacing 4px, stretch appended after chips |
| Add input | `QLineEdit` | `_COL_APPLICATOR` (80px) | Pill-shaped, Chandler42 italic 9px, placeholder "+", returnPressed adds entry |
| Hidden field | `QLineEdit` | hidden | Canonical string representation — `str(list)` — synced to TOML |

**Chip anatomy:**
- `QFrame`, fixed height 20px, `QSizePolicy.Fixed` both axes
- `QHBoxLayout`, margins `(8, 0, 4, 3)`, spacing 2px — the 3px bottom bias nudges the label upward so lowercase-heavy text (`__pycache__`, `.pyc`, `.log`) doesn't feel bottom-anchored. Font metrics reserve ascender/cap-height space that goes unused without uppercase letters; the asymmetric margin compensates
- `QLabel` — Chandler42 italic, 9px, `Theme.textPrimary`
- `QPushButton("×")` — 12×12px, flat, transparent; hover turns `#d87a9e`
- Border radius 10px (half of 20px height → true pill shape)
- Background `Theme.windowBg`, border `1px solid Theme.primaryBorder`

**Row wrapping:** When the number of pills exceeds the horizontal space, the chip container wraps onto additional lines and grows vertically to fit. Only pill rows do this — slider and checkbox rows remain single-line and tight. Implemented in `PrettyPillRow` via a custom flow layout that reports `heightForWidth`, so the enclosing QHBoxLayout re-sizes the whole row upward. The 28px `min_height` keeps an empty row visually at standard chip height.

**Data flow:** `ast.literal_eval` parses the hidden field text → Python list → chips rebuild. Removing or adding a chip immediately serializes back to `str(list)` and triggers the standard `_on_field_changed` → TOML write pipeline.

**Add input tooltip:** "Type a name and press Enter — use > for nested paths (e.g. Documents>data)"

## Boolean Toggle Row

For TOML fields that store string booleans (`"True"` / `"False"`). Rendered as a `pretty_label` for the field name plus a `PrettyCheckbox` with `show_indicator=False` — the checkbox hides its native indicator box and instead displays a pink `#ffb6c1` glyph (`✓` when checked, `—` when unchecked) as its label text. The glyph sits in the shorthands column, visually aligned with slider value readouts.

**Layout (left to right):**

| Widget | Type | Width | Details |
|--------|------|-------|---------|
| Label | `pretty_label` | `_COL_LABEL` (200px) | 12pt, display name derived from TOML key |
| Checkbox glyph | `PrettyCheckbox` | `_COL_SHORTHAND` (36px) | `show_indicator=False`, empty text — displays `✓` / `—` in `#ffb6c1` pink, center-aligned. Click toggles state. |
| Stretch | — | fills remaining | Empty content column |
| Applicator | `QSpacerItem` | `_COL_APPLICATOR` (80px) | Empty placeholder |
| Hidden field | `QLineEdit` | hidden | Stores `"True"` or `"False"` for TOML sync |

**Signal:** `chk.toggled.connect(lambda checked, f=field: f.setText("True" if checked else "False"))`

**PrettyCheckbox `show_indicator=False` mode:** When constructed with `show_indicator=False`, `PrettyCheckbox` hides the native `QCheckBox` indicator (0px width) and instead uses its internal `PrettyLabel` as the visual toggle. The label text swaps between `✓` and `—` on each toggle, styled `#ffb6c1` pink with center alignment. Clicking anywhere on the label toggles the underlying checkbox state. This mode is the standard for boolean rows — no visible checkbox box, just the pink lettering.

## Cycle Palette Pill Row

For state stored in a sidecar file rather than `settings.toml`. The canonical instance is the cycle palette in `intricate.color_picker`, which reads/writes `color_registry.toml` directly via module-scope helpers and a Qt file watcher. Renders as a row of pure-colour pills with an inline add-input on the right.

**Layout (left to right):**

| Widget | Type | Width | Details |
|--------|------|-------|---------|
| Label | `pretty_label` | `_COL_LABEL` (200px) | 12pt, top-aligned so it stays flush with the first pill line when the row wraps |
| Shorthand spacer | `QSpacerItem` | `_COL_SHORTHAND` (36px) | Empty placeholder |
| Pill container | `color_pill_row` | stretch=1 | Flowing horizontal pill row — wraps onto multiple lines when it overflows |
| Add input | `pill_add_input` | `_COL_APPLICATOR` (80px) | Hex add field, top-aligned to match the label |

**External sidecar contract:** unlike every other row type, this one bypasses `settings.toml`. Reads via `read_color_registry()`, writes on `pills.items_changed`, and a `QFileSystemWatcher` re-syncs when Intricate registers a new colour at runtime. The watcher uses `pills.set_items(fresh)` — silent, no `items_changed` echo — so the round-trip doesn't loop. Only direct user interaction emits `items_changed` → file write.

**Builder lives outside the main loop:** because the source isn't enumerated from `settings.toml`, the pill row is added by a dedicated builder (`_add_color_picker_tab()`) called after the main TOML enumeration finishes but before the saved-tab restore. Mirror this shape for any future sidecar-backed category.

## Merged Categories — `tab_path` Decoupling

When two TOML sources want to share one driver-side dashboard, decouple visual placement from persistence via the `tab_path` kwarg on `_add_color_row` (and any future row helper that gains it). The canonical instance is `intricate.color_picker`: chrome swatches sourced from `[theme.colors]` in `settings.toml` render in the same tab as the cycle palette pills sourced from `color_registry.toml`.

- `section_path` → drives the field registry key `(section_path, field_key)`, which the save loop walks to write the TOML
- `tab_path` → drives `_ensure_tab(tab_path)`, the visual tab the row renders into
- Defaults: when omitted, `tab_path = section_path` — the path most callers want

For the merge to land, the main TOML enumeration loop must skip the lifted source so it doesn't get its own auto-tab; the merged builder then renders the lifted row with `tab_path` pointing at the host tab. `_add_color_picker_tab()` is the worked example — chrome row first with `section_path="theme.colors"` and `tab_path="intricate.color_picker"`, spacer, then the cycle pill row.

## Adding a New Category

1. Add the TOML section (e.g. `[node.xxx]`) to `settings.toml`
2. Register a display name in `_SECTION_LABELS`
3. Optionally define field grouping in `_SECTION_FIELD_ORDER` — each inner list is a chunk separated by a spacer; use this to group related controls visually
4. Add a description in `_SECTION_DESCRIPTIONS` — required for every shipping category, see **Section Description**
5. Add a section-specific branch in `_add_field_row()` for any fields needing custom controls:
   - Integer attributes → Slider Row
   - Hex color attributes → Color Swatch Cell (automatic, no branch needed)
   - List attributes (TOML string-encoded Python lists) → Tag Chip Row
   - Boolean string attributes (`"True"`/`"False"`) → Boolean Toggle Row
   - Everything else → plain `QLineEdit` (default fallback)

**The Tree Node category is the worked example** of combining all three custom control types in one page: one slider (max_depth), three chip rows (exclude lists), three boolean toggles (display options), with `_SECTION_FIELD_ORDER` providing the visual grouping.

**For sidecar-backed state** (storage outside `settings.toml`), follow the **Cycle Palette Pill Row** pattern: a custom builder method invoked after the main enumeration loop, with its own helpers and `QFileSystemWatcher` for live re-sync.

**For merged categories** (multiple TOML sources sharing one tab), follow the **`tab_path` Decoupling** pattern: skip the lifted source in the enumeration loop and pass `tab_path=...` when adding the row.

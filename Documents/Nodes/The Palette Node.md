# The Palette Node

A swatch board for collecting hex values and looking at them side by side. Two-column grid of editable cells — each cell carries a label, a large colour panel, and the hex string underneath. Drag a swatch to another palette to move it; drag back onto the same palette to duplicate; drag a swatch up or down to nudge its HSL lightness without leaving the canvas.

The node is the design surface that sits next to writing work — the place where the user collects the colours a section of the writing wants to live with, before any of those values cross over into a Settlers theme or a piece of media. Lightweight, spatial, no Photoshop pretension; for serious colour work the user reaches for Photoshop or color.adobe.com, but for "what does this group look like together" the palette node is the right weight.

## Core Files

| File | Purpose |
|---|---|
| `nodes/PaletteNode.py` | Node + `_PaletteWidget` (the scrollable grid) + `_SwatchCell` (one entry) |
| `data/PaletteNodeData.py` | Pure Python dataclass — `colors: list[dict]`, title, geometry |

## How It Works

### Three Layers in One File

Inside `PaletteNode.py` the implementation stacks vertically as three classes, smallest first:

- **`_SwatchCell`** — a single entry. Label QLineEdit on top, a coloured `QFrame` in the middle, hex QLineEdit underneath, hover-revealed `×` button in the corner. Owns its own drag pickup and lightness-shift gesture. Emits change events upward through callback closures rather than Qt signals; the parent `_PaletteWidget` wires `on_change` and `on_remove` per cell.
- **`_PaletteWidget`** — the scrollable container. `QScrollArea` wrapping a `QGridLayout` of `_SwatchCell`s plus a `+ add color` button at the bottom. Owns the drag-drop event filter that places dropped swatches by viewport position and decides between copy and move based on the source palette.
- **`PaletteNode`** — the canvas-level node. Holds the `_PaletteWidget` in a `QGraphicsProxyWidget`, draws the title, exports to PNG via the snapshot button, and adopts AboutNode's shelf-via-resize gesture for the button row.

The split is deliberate: `_SwatchCell` is reusable in principle (any QWidget container could drop one in), `_PaletteWidget` is the body shape, and `PaletteNode` is just the canvas chrome around it. A future "palette pane" or "Settlers swatch picker" could share `_SwatchCell` without dragging the QGraphicsItem stack along.

### Title — Inline Edit on Double-Click

Each palette can carry a name (the screenshot user shows "Palette" by default). Double-click anywhere in the title row swaps in a `QLineEdit` overlay; `editingFinished` commits, an empty string falls back to "Palette".

The edit overlay's geometry is clamped to one title row (`_BODY_OFFSET` tall) rather than the body-spanning rect that `BaseNode._title_rect` returns by default — without the clamp the QLineEdit centres its content vertically inside a body-tall rect and the cursor floats in the middle of the swatch grid. Single-row clamp lands the edit overlay exactly where the painted title sits.

While the title is being edited the title text recolours from Lombardi-Lake (the painted state) to ivory white (the editing state) via the QLineEdit's stylesheet — a quiet visual cue that the field is hot.

### Shelf-via-Resize Gesture

PaletteNode adopts AboutNode's resize-driven shelf reveal verbatim. The button row starts hidden; the user yanks the bottom-right corner downward past 75 px to reveal, pulls back upward past 30 px to hide. Same asymmetric thresholds AboutNode uses so the gesture feels uniform between the two nodes.

```python
_RESIZE_SHELF_REVEAL_THRESHOLD = 75.0
_RESIZE_SHELF_HIDE_THRESHOLD   = 30.0
```

`_body_rect` tracks `_anim_top_offset` rather than the constant `_BUTTON_ZONE_H`, so the swatch grid slides up with the shelf when it collapses and stays aligned with the title across both states. `_on_shelf_tick` repositions the palette proxy every animation frame; without that hook the body would jump to its final position only at animation end, snapping past 32 px of empty space.

The double-click that used to fall through to BaseNode's default top-strip shelf-toggle is consumed in `mouseDoubleClickEvent` now — the resize gesture is the only way to flip the shelf, and the double-click is reserved for the title-edit overlay.

### The Two-Mode Drag on a Swatch

A press on the coloured panel arms two possible drags from a single mousedown. The motion direction picks which one fires:

- **Vertical-dominant motion** → HSL-lightness shift on the swatch itself. Up to lighten, down to darken. Live update via `setHsl(hue, saturation, new_lightness, alpha)`, where the new lightness is the base lightness plus `−dy / 1.5` (1.5 px per HSL unit on a 0–255 scale, lifted from the Settlers' `_DraggableSwatch`). No threshold; the smallest motion lands the smallest adjustment. Hue is preserved across the drag, including the `−1` hue value Qt uses for greys (without the explicit `if h < 0: h = 0` clamp, `setHsl` would reset a grey to red).
- **Horizontal-dominant motion past 15 px** → cross-palette `QDrag`. Mime payload is the cell's `{"label", "hex"}` dict; the rendered swatch becomes the drag pixmap. Source side calls `drag.exec(MoveAction | CopyAction)` so both outcomes are allowed, and the drop side picks one.

The direction lock is the load-bearing detail. If both gestures shared a single threshold-free start path, a vertical lightness drag with even a few pixels of horizontal drift could accidentally arm a cross-palette drag mid-shift. The `abs(dx) > abs(dy) and abs(dx) > 15` gate keeps a vertical wobble in lightness mode and reserves the cross-palette drag for an actual horizontal sweep.

```python
def mouseMoveEvent(self, event):
    if self._drag_start is None or not (event.buttons() & Qt.LeftButton):
        super().mouseMoveEvent(event)
        return
    delta = event.pos() - self._drag_start
    dx, dy = delta.x(), delta.y()
    if abs(dx) > abs(dy) and abs(dx) > 15:
        self._initiate_drag()         # cross-palette QDrag
        self._drag_start = None
        return
    if abs(dy) >= abs(dx):
        self._apply_lightness_shift(dy)   # live HSL nudge
    event.accept()
```

The lightness shift writes its new hex through `self._hex.setText(new_hex)`, which cascades through `textChanged` → `_on_hex_changed` (validates, repaints the panel) and the `on_change` lambda (propagates to `PaletteNode.data.colors`). One write, two slots, both update.

### Drop on Self → Duplicate

The drop side decides the action by walking up from `event.source()` to find the source's `_PaletteWidget` and comparing it against `self`:

```python
src_palette = event.source()
while src_palette and not isinstance(src_palette, _PaletteWidget):
    src_palette = src_palette.parent()
if src_palette is self:
    event.setDropAction(Qt.CopyAction)
else:
    event.setDropAction(Qt.MoveAction)
event.accept()
```

`MoveAction` triggers the source's post-`exec` removal step (`_remove_cell` on the originating palette). `CopyAction` skips it, so the original stays and the dropped insert becomes a duplicate. The framework was already in place for cross-palette move; this is just the drop side picking the right action.

The pre-fix workflow was: spawn a second palette, drag the swatch over to it, edit the original, drag the duplicate back. The new behaviour collapses that to a single drop-onto-self gesture.

### Auto-`#` on Bare Hex Paste

`_on_hex_changed` watches for valid hex characters of length 6 or 8 with no leading `#` and prepends one. Triggers on length 6 (RGB) and length 8 (RGBA) only — character-by-character typing of those forms isn't second-guessed before the user finishes.

```python
if (text and not text.startswith("#")
        and len(text) in (6, 8)
        and all(ch in "0123456789abcdefABCDEF" for ch in text)):
    self._hex.setText("#" + text)
    self._hex.setCursorPosition(len(text) + 1)
    return
```

Cursor jumps to end-of-text after the prepend so further typing continues at the natural position. The `setText` call recurses into this slot with the corrected value and falls through to the validator on the second pass — one code path covers both the auto-corrected case and the already-`#`-prefixed one.

### Snapshot Button

The shelf carries a single utility button (a sticker-style push icon): export the entire palette node — border, title, all swatches — as a PNG. `utils.helpers.snapshot_node` renders the QGraphicsItem to a QImage, writes the file, returns the path; the node then asks the main window to flash an InfoBar message confirming the export.

The snapshot is the atomic unit the user passes around — drop a palette PNG into a Settlers theme, into a chat, into a writing document — without exporting the data structure. A palette is a visual artefact; the PNG is its travelable form.

### Body Always Visible — Scroll Bar Until Auto-Size Lands

`_PaletteWidget` wraps its grid in a `QScrollArea` so a long palette stays scrollable inside a fixed-height node. The scroll bar styles down to a thin 5 px handle in `Theme.primaryBorder` — present, visible, but quiet. The pending follow-up on the focal list is to auto-size the node height to the swatch count so the scroll bar never appears in the typical case; until then, the scroll bar is the relief valve.

## Data Class

`PaletteNodeData` extends `NodeData` with:

- `colors: list[dict]` — each entry `{"label": str, "hex": str}`
- standard geometry — `x`, `y`, `width`, `height`, `uuid`, `node_type="palette"`, etc.
- standard chrome — `title`, `node_tint`, `depth_front`, `shelf_visible`

`to_dict` reads the live colour list off `self._palette.get_colors()` before serialising, so any in-flight edits land in the saved session.

## Lifecycle

### Removal

`_demolition_proxies = ['_title_proxy', '_palette_proxy']` — the demolition crew tears down both proxy widgets in the canonical order (scene-rect invalidate, `setParent(None)`, `deleteLater`). `_demolition_post` nulls the inner `_palette` reference; the QWidget itself is already gone via the proxy's child-cleanup path.

The title-edit `_title_proxy` is created lazily on first edit and torn down on commit, so in the idle case demolition skips it entirely.

## Lessons Learned

### `_title_rect` is a paint-clip rect, not an edit-overlay rect

`BaseNode._title_rect` returns a rect spanning from `_content_top()` to the bottom of the node — its consumer is `paint_content`, which draws into it with `Qt.AlignTop` so the height doesn't matter for paint. Reusing the same rect for a `QLineEdit` overlay traps the cursor and text in the body's vertical centre because QLineEdit centres its content. The fix was a one-line clamp: `QRectF(full.left(), full.top(), full.width(), self._BODY_OFFSET)`. Title overlays for nodes with body content all need the same clamp; when copying this pattern to a new node, don't reuse `_title_rect` directly without trimming the height.

### Direction-lock the press-armed drag if you have two drag modes

A single mousedown that arms two possible drag gestures (lightness shift here, cross-palette QDrag) needs an explicit direction-lock or the gestures bleed into each other. The 15-px Manhattan threshold the original code used was enough for one-mode press-arm, but adding the lightness shift behind the same press required disambiguation. `|dx| > |dy| and |dx| > 15` gates the cross-palette drag to actual horizontal motion; vertical-dominant motion stays in lightness mode regardless of magnitude. Without the gate, every long vertical lightness drag risked accidentally arming a cross-palette drag once it crossed 15 px Manhattan distance.

### `setText` cascades — let the slot run twice instead of fighting it

The bare-hex auto-correct sets the field to `"#" + text` and returns; the recursive `textChanged` invocation fires the same slot again with the corrected value, which falls through to the validator. Two passes through one function, no `blockSignals` dance, no parallel write path. The `on_change` callback also fires twice — once on the bad input (no-op because `QColor.isValid()` returns false) and once on the corrected input (propagates the new colour). The double-fire is harmless and the code is shorter than the alternative.

### HSL hue `−1` is Qt's grey marker — guard it

`QColor("#888888").getHsl()` returns `(-1, 0, 136, 255)` — the `−1` hue means "no hue, this is a grey." If you take that hue value and pass it back to `setHsl`, Qt clamps it to a fallback (effectively red), and a grey swatch jumps to red on the first lightness drag. The `if h < 0: h = 0` line in `_apply_lightness_shift` is the explicit clamp; same line lives in the Settlers' implementation for the same reason.

## Technical Notes

- The `+ add color` button has its own minimal stylesheet and uses `Theme.primaryBorder` for the rest state, `Theme.nodeBorderSelected` for hover. Click adds a default `("Color", "#c0a888")` entry to the end of the grid; the user edits both fields in place.
- Cells render their hover-revealed `×` button via `enterEvent` / `leaveEvent`. The button is repositioned in `enterEvent` because the cell width can change as the grid relays out — pinning it once in `__init__` would leave it floating off the right edge after a resize.
- `_index_at_container_pos` decides drop position by walking the cell list and comparing the drop point against each cell's geometry centre. A drop above a cell's vertical centre inserts before it; a drop in the same row to the left of the horizontal centre also inserts before it; otherwise the drop appends to the end.
- `_MIME_TYPE = "application/x-intricate-palette-color"` is unique to PaletteNode — the format is the gate that lets the eventFilter recognise its own swatches and ignore foreign drops.
- `_min_width = 280`, `_min_height = 300` — the 2-column layout collapses below those values; the constructor enforces them on session restore in case an older session carried a smaller geometry.

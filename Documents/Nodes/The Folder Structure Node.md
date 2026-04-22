# The Folder Structure Node

The TreeNode that displays a live folder structure for any project. Registered in `node_registry.toml` as "Folder Structure" — the node you glance at to see what's actually on disk. It walks the directory in-process, respects gitignore, and renders the result as a styled tree with heart bullet icons for files and bold white labels for folders.

*(Historical note: previously registered as "The Stuff and Stuff" — renamed 2026-04-22 to a plainer name.)*

## What It Shows

A flat text tree of a project folder. Folders render in **Lato Bold, pure white** (`#ffffff`). Files render in **Lato Regular, ivory** (`Theme.textPrimary` — currently `#d2d1cf`). Each file line gets a heart icon (`icons/tree_file_icon.png`) as a scene-native `QGraphicsPixmapItem` floating next to the text. Folder lines keep the 📁 emoji inline.

The node auto-sizes to fit all content — there is no scrollbar. The tree is read-only reference; you look at it, you don't edit it.

## Core Files

| File | Purpose |
|---|---|
| `nodes/TreeNode.py` | Node class, walker, HTML builder, heart placement |
| `data/TreeNodeData.py` | Pure Python dataclass — `tree_text`, `project_path` |
| `icons/tree_file_icon.png` | Heart icon source (full-res, scaled at render time) |
| `node_registry.toml` | Registry entry: name "Folder Structure", category "tools" |

## Architecture

### The Walker

`_TreeWalker` is an in-process directory walker transplanted from `cozy-snapshot.py` (v0.0.1 legacy). It walks a `Path` tree, applies filters at walk time, and yields indented text lines. No subprocess, no temp file.

Filters come from `[node.tree]` in `settings.toml`:
- `max_depth` — how deep to recurse (default 6)
- `exclude_dirs` — directory names to skip. Supports nested paths via `>` separator (e.g. `Documents>data`)
- `exclude_exts` — file extensions to skip
- `exclude_files` — specific filenames to skip
- `show_hidden` — whether to show dotfiles (default false)
- `use_gitignore` — respect `.gitignore` patterns (default true)
- `use_emoji` — include 📁 on folder lines (default true)

Always-ignored: `.git`, `__pycache__`, `.pkf` files.

The walker loads gitignore patterns from the nearest `.gitignore` upward plus the global gitignore (`~/.gitignore_global` or `~/.config/git/ignore`).

Sort order: directories first, then files, both alphabetical case-insensitive. Empty directories (after filtering) are pruned — they never appear in the output.

### Text to HTML

`_tree_to_html(text)` converts the walker's plain text into styled HTML and returns a tuple of `(html_string, file_line_indices)`.

Each line becomes its own `<p>` block. This is critical — using `<pre>` with `<br>` creates a single QTextDocument block, which makes it impossible to map block indices to individual lines for heart placement. The switch from `<pre><br>` to per-line `<p>` tags was the fix that made heart icons work.

Each `<p>` has:
- `font-family: Lato; font-size: 8pt`
- `white-space: pre` — preserves the indentation spaces from the walker
- `padding-left: 20px` — reserves horizontal space for the heart column
- `margin: 0` — no inter-paragraph spacing

Folder lines (ending with `/`) get `font-weight: 700; color: #ffffff`. File lines get `font-weight: 400` and inherit `Theme.textPrimary`.

Legacy `📄` emoji is stripped from cached session text (`raw.replace("📄 ", "")`) so old sessions don't show both the emoji and the heart icon.

### Heart Icon Placement

Hearts are `QGraphicsPixmapItem` children of the TreeNode, positioned at each file line's y-coordinate. This is the same scene-native pattern used by `NodeButton` — real items in the Qt Graphics View hierarchy, not paint hacks.

**Why not inline HTML images?** We tried `<img>` tags first. They work but inflate the line height, breaking the visual rhythm between folder and file lines. The hearts need to be bigger than the line height (18px icon on ~11px text) so they chain/overlap slightly between adjacent lines — the same weaving effect used in the chapter indexes in the documentation system.

**Why not viewport paint overlays?** We tried both an event filter on the viewport and a monkey-patched `paintEvent`. Neither worked — the event filter swallowed paint events causing a blank node, and the monkey-patch couldn't open a new QPainter after the original paint session ended. Scene-native items are the correct approach for anything that needs to coexist with `QGraphicsProxyWidget` content.

**The z-depth hierarchy** (logged by `intricate.tree` logger):

| Item | z-value | Notes |
|---|---|---|
| TreeNode self | 0.0 | The base `QGraphicsRectItem` |
| Editor proxy | 0.0 | `QGraphicsProxyWidget` holding the `PrettyEdit` |
| Toolbar proxy | 0.0 | `QGraphicsProxyWidget` holding the 📁 button |
| **Heart items** | **5.0** | Above the editor, visible on top of text |
| Name-editor proxy | 10.0 | Floating folder-name input, above everything |

Hearts must be above the editor proxy (z=0) or they render behind the text and are invisible. Setting them at z=5 puts them above the editor but below the name input overlay (z=10).

**Pixmap quality:** The heart pixmap is loaded at full resolution from `tree_file_icon.png` and each `QGraphicsPixmapItem` uses `setScale(HEART_SIZE / pixmap.width())` with `Qt.SmoothTransformation`. This means Qt re-rasterises from the full source at every zoom level — no pixelation when you zoom in. Pre-scaling to 18x18 and storing the small pixmap causes visible blur at higher zoom levels.

**Coordinate mapping:** Each heart's position is calculated from the QTextDocument block layout:
```
x = body_rect.x - 4       (nudged left so hearts sit snug with text)
y = body_rect.y + block_bounding_rect.y - 1
```
The body rect maps document coordinates into node-local coordinates. `doc.documentLayout().documentSize()` is called first to force a layout pass — without this, block bounding rects may return stale zeros.

### Auto-Sizing

The node measures its content for HEIGHT and sizes itself so every tree line is vertically visible without scrolling. WIDTH is driven by the title only — body content never widens the node, per the design rule *"resize according to the title width while keeping the default width on the body text where the tree is."*

**Width formula** (in `_auto_size`):
```
new_w = max(TreeNodeData.default_width, title_w + pad + right_pad)
```
where `title_w = self._measure_title_width()` — a `QPainterPath.addText().boundingRect()` read against the exact QFont the paint uses, and `right_pad` falls through to `BaseNode._TITLE_RIGHT_PAD` (default None → symmetric with `Theme.nodeTextPaddingLeft`). Long tree lines that exceed the body's available width clip horizontally — accepted tradeoff.

**Height formula**:
```
new_h = max(120, doc_h + chrome_y)
```
where `doc_h` comes from `doc.size().height()` after a constrained-width layout pass, and `chrome_y` includes the button zone, title gap, padding, and one extra line of breathing room.

**Title-only width** (not body-driven) plus **scrollbar disabled** means every tree line is vertically visible, and the node's horizontal footprint is predictable for a given project name rather than growing with filename length.

`_auto_fit_title_width` runs as a second pass at end-of-init to enforce the title-width minimum even if `_auto_size` decided otherwise (defensive; grow-only; no-op when the width is already sufficient).

## Lifecycle

### Creation (sidebar button)

1. `Scene.add_tree_node(pos, project_path)` creates `TreeNodeData` with the path
2. `__init__` builds toolbar, name input, tree view editor
3. `tree_text` is empty → `refresh()` → `_make_walker().build_text()` → `_set_text(text)`
4. `_set_text` → `_tree_to_html` → `setHtml` → `_auto_size` → `_place_hearts`

### Session restore

1. `TreeNodeData.from_dict(d)` reconstitutes the dataclass with saved `tree_text`
2. `__init__` detects `tree_text` is non-empty → `_set_text(tree_text)` directly (no walk)

### Refresh (sticker button)

First refresh fills the node directly. Subsequent refreshes spawn a sibling node so manual edits to the current one are preserved. The offset is `bottomRight + (20, 20)`.

### Refresh-in-place (after creating a new folder)

Destroys the current node with a particle burst and spawns a fresh replacement at the same position and z-value. Interaction flags are severed immediately to prevent Qt from routing events to the zombie node during the deferred-removal window.

### Serialization

`to_dict()` reads `self._editor.toPlainText()` — this strips all HTML back to plain text, so the saved `tree_text` is always clean. On reload, `_tree_to_html` rebuilds the formatting from scratch.

## Left Toolbar

A single 📁 button in a `QGraphicsProxyWidget` column to the left of the tree body. Clicking it shows a floating `PrettyEdit` name input (at z=10, above everything) where you type a folder name. On commit, the folder is created on disk and the node refreshes in place.

## Init File Compliance

On creation, `_ensure_init_files()` calls `utils.helpers.ensure_init_tree(root)` to create missing `__init__.py` files in Python package subfolders. This runs once at init, after the tree text is populated.

## TOML Configuration

```toml
[node.tree]
max_depth = 6
exclude_dirs = ["node_modules", "dist", "Documents>data"]
exclude_exts = [".pyc", ".pyo"]
exclude_files = ["desktop.ini", "Thumbs.db"]
show_hidden = false
use_gitignore = true
use_emoji = true
```

The `>` separator in `exclude_dirs` handles nested path exclusions without TOML escape conflicts (both `/` and `\` cause issues in TOML strings).

## Logger

Uses the Rust-backed logger via `setup_logger("intricate.tree")`. The z-depth compliance block logs the full scene hierarchy every time hearts are placed — useful for diagnosing visibility issues on nested `QGraphicsProxyWidget` content.

## Lessons Learned

### HTML block structure matters for QTextDocument

`<pre>` with `<br>` separators creates **one** QTextDocument block. `<p>` per line creates **one block per line**. If you need to map block indices to line numbers (for overlays, icons, annotations), you must use `<p>` tags. This cost several debugging rounds to discover — the hearts were being placed but the block iteration found zero matching indices because the entire tree was a single block.

### Scene-native items beat paint hacks for proxy content

`QGraphicsProxyWidget` owns its own paint pipeline. You cannot reliably paint on top of it from the parent node's `paint()` method, from a viewport event filter, or from a monkey-patched `paintEvent`. The correct pattern is `QGraphicsPixmapItem` (or any `QGraphicsItem`) as a child of the node with a z-value above the proxy. This is the same pattern used by `NodeButton`.

### Full-res pixmaps with setScale beat pre-scaled pixmaps

Pre-scaling a pixmap to display size (e.g. 18x18) then letting Qt scale it up on zoom produces visible blur. Loading the full-res source and using `item.setScale(target_size / source_size)` with `Qt.SmoothTransformation` lets Qt re-rasterise from the full source at every zoom level.

### Logging through the right system matters

`logging.getLogger("name")` creates a bare logger with no handlers if the name doesn't match the app's logger factory. In this codebase, always use `setup_logger("name")` from `pretty_widgets.utils.logger` — it routes through the Rust ring buffer when available and falls back to the stdlib 3-slot rotation otherwise.

### Measurement QFont must match paint QFont

The long title-width chase on 2026-04-22 bottomed out at this lesson. `BaseNode._measure_title_width` was building its QFont at `Theme.aboutFontSize + _TITLE_FONT_BUMP` (18pt with the user's `[node.about] font_size = 12`) but `BaseNode.paint_content` renders the title at just `Theme.aboutFontSize` (12pt, no bump). That 1.5× size mismatch inflated every width computation in every auto-fit code path — `_auto_fit_title_width`, `_auto_size`'s title clause, every downstream `new_w` — by the same ratio, silently.

The fix was to make `_measure_title_width` build its QFont the *same way* `paint_content` does. Contract: the measurement tracks the paint, not the other way around. Subclasses that override `paint_content` with a different title-font size must also override `_measure_title_width` to match.

Diagnostic surface kept for the next round: the `[tree-fit]`, `[tree-autosize]`, and `[resize-end]` DEBUG logs. Flip the log level up to INFO on the TreeNode / basenode loggers when investigating node-sizing regressions — the round-trip (my intent → user's final resize) is captured in a single pair of lines per spawn.

### QPainterPath over QFontMetrics for Chandler42

`QFontMetrics.horizontalAdvance()` reads the font's advance table, which on non-monospaced display fonts (Chandler42 is the canonical case) can over-report relative to actual rendered ink — the advance includes trailing per-glyph sidebearings that never draw. `QPainterPath.addText().boundingRect()` walks the actual glyph outlines and returns honest painted bounds. Scoped swap for title sizing only; QFontMetrics stays where it's reliable (body-document height, simple ASCII measurement in common fonts).

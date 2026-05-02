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
- `margin: 0 0 0 {HEART_COL_W}px` — reserves horizontal space for the heart column. **Must be `margin-left`, not `padding-left`** — Qt's QTextDocument HTML renderer silently drops `padding` on block elements but honours `margin` reliably. (See *Qt's HTML renderer drops padding on block elements* under Lessons Learned.)

`HEART_COL_W` currently sits at **14 px**. Iteration history: 20 → 28 → 36 (all silently dropped as `padding-left`, no visual change) → 28 with `margin-left` (first version that actually rendered) → **14** (halved on user request once the adjuster was actually working — tighter visual rhythm now that the indent landing is real).

Folder lines (ending with `/`) get `font-weight: 700; color: #ffffff`. File lines get `font-weight: 400` and inherit `Theme.textPrimary`.

Legacy `📄` emoji is stripped from cached session text (`raw.replace("📄 ", "")`) so old sessions don't show both the emoji and the heart icon.

### Editor configuration

The body editor is a `PrettyEdit` constructed with `spellcheck=False`. The tree is a list of file and folder names — `__init__.py`, `app_info`, `last_session`, `.otf`, and most filenames are not English words, so the default `DebouncedSpellHighlighter` red-squiggles nearly every line and flickers the squiggles each time the highlighter re-runs over a refreshed tree. `spellcheck=False` is the targeted opt-out. The default everywhere else in the app stays on — this is the one node that explicitly doesn't want it.

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

Hearts must be above the editor proxy (z=0) or they render behind the text and are invisible. Setting them at z=5 puts them cleanly on top of the editor content without competing with any other scene-layer.

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
2. `__init__` builds the left toolbar and the tree view editor
3. `tree_text` is empty → `refresh()` → `_make_walker().build_text()` → `_set_text(text)`
4. `_set_text` → `_tree_to_html` → `setHtml` → `_auto_size` → `_place_hearts`

### Session restore

1. `TreeNodeData.from_dict(d)` reconstitutes the dataclass with saved `tree_text`
2. `__init__` detects `tree_text` is non-empty → `_set_text(tree_text)` directly (no walk)

### Refresh (sticker button)

First refresh fills the node directly. Subsequent refreshes spawn a sibling node so manual edits to the current one are preserved. The offset is `bottomRight + (20, 20)`.

### Serialization

`to_dict()` reads `self._editor.toPlainText()` — this strips all HTML back to plain text, so the saved `tree_text` is always clean. On reload, `_tree_to_html` rebuilds the formatting from scratch.

## Left Toolbar

A single 📁 button in a `QGraphicsProxyWidget` column to the left of the tree body. Sits slightly larger than the inline folder glyphs in the tree text itself, which makes it read as the **root marker** of the tree rendering — the folder icon for the project's root.

**Click action:** open the project's root folder in Windows Explorer. Two cooperating steps:

1. **Roll curtains up** if they're not already (`mw.toggle_curtains()`). Mirrors the pattern `GitNode._launch_github_desktop` uses when switching to GitHub Desktop — Intricate yields the foreground by getting smaller, not by any explicit focus dance. Best-effort, wrapped in an except so a scene-less edge case doesn't block the file-open.
2. **`os.startfile(project_path)`** — Windows' shell-execute path for the folder. Silent no-op on missing path or OSError; this is a shortcut, not a load-bearing operation.

**Why `os.startfile` and not `subprocess.Popen(["explorer", path])`** — the stdlib route wraps `ShellExecuteEx`, which tells the shell *"do what happens if the user double-clicks this folder."* Windows' default behaviour there is to **raise and focus an existing Explorer window** pointing at the same path rather than spawn a duplicate. The alternative (`Popen`-launching `explorer.exe` directly) does spawn duplicates — every click adds another Explorer instance to the taskbar. Every "open X externally" button in the app should prefer `os.startfile` for this reason.

**Why the curtains-roll helps beyond cosmetics** — with Intricate as a frameless always-on-top app, the target window (Explorer, GitHub Desktop, etc.) arrives UNDERNEATH Intricate without the roll. Rolling first guarantees the user sees the target app as the top surface of their desktop when it opens, matching what happens when the user triggers the same app via any other shortcut.

*(Historical note: previously clicked to create a new subfolder in the project root — repurposed 2026-04-22 since project layouts stabilised enough that folder creation from here was no longer a daily utility. The whole name-input plumbing was removed in the same pass. This slot is the foothold for future filesystem actions on the tree; it's the one node in the app that has a dedicated left sidebar for its own category of actions.)*

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

### Qt's HTML renderer drops `padding` on block elements — use `margin`

Surfaced 2026-05-02 round 4. The pre-fix `_tree_to_html` used `padding-left:20px` on each `<p>` to reserve horizontal space for the heart column. The user reported hearts overlapping with the start of file/folder names. Bumping the value to `28px`, then `36px`, produced **no visible change** in the rendered tree — the hearts kept landing on top of the text.

Root cause: Qt's QTextDocument HTML/CSS subset silently parses but does not apply `padding` declarations on block elements. There's no warning, no fallback, no rendered hint that the property was ignored — the layout just behaves as if you'd never set it. `margin` on the same elements works correctly.

The fix was a one-character family swap: `padding: 0 0 0 {HEART_COL_W}px` → `margin: 0 0 0 {HEART_COL_W}px`. The first run with `margin-left` *immediately* showed the indent landing in the right place, validating that all the previous bumps had been no-ops.

Diagnostic posture for the future: if you set a CSS property on a Qt-rendered HTML block and it appears to have zero effect, **try the margin equivalent before reaching for any other tool**. Check the property against Qt's documented [CSS subset support table](https://doc.qt.io/qt-6/richtext-html-subset.html) before assuming the property is honoured.

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

### Intricate-initiated shell actions inherit session context

`Win+E` in Windows opens a blank Explorer window — the OS can't know which folder the user intends to browse to. The 📁 button on this node opens Explorer **with a destination**, because the session graph already carries the intent (the node's `project_path`). Every "open X externally" button the app grows going forward inherits that same property: Intricate-initiated actions are smarter than OS-initiated ones for the same operation, because Intricate knows things the shell can't. Small practical benefit: fewer duplicate Explorer windows piling up in the taskbar over a work day, because `os.startfile` consolidates onto any existing instance rather than spawning a fresh one every time.

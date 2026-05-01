# The Markdown Node

The read-only documentation viewer. Takes raw markdown text, converts it to GitHub dark theme HTML on a background thread, and displays it in a scrollable QTextEdit. Every `.md` file in the `Documents/` folder is one click away from becoming a MarkdownNode on the canvas.

MarkdownNode is a base class — four specialised subclasses inherit from it for dedicated document types:

| Subclass | Purpose | Data class |
|---|---|---|
| `ArchitectureNode` | Displays `Architecture.md` | `ArchitectureNodeData` |
| `NodeSchemaNode` | Displays `Node Type Schema.md` | `NodeSchemaNodeData` |
| `ReadmeNode` | Displays `README.md` from the project root | `ReadmeNodeData` |
| `RegistryNode` | Displays `node_registry.toml` as rendered docs | `RegistryNodeData` |

Generic MarkdownNodes are spawned for everything else — any `.md` file picked from the Info sidebar menu. `ArchitectureNode` and `NodeSchemaNode` differ from generic MarkdownNodes in that they hard-load their source `.md` file from disk on init (path baked into the class as `_DOC_PATH`) and cache the content in `data.label` for session persistence; generic MarkdownNodes receive their `label` text directly from the menu click.

## Core Files

| File | Purpose |
|---|---|
| `nodes/MarkdownNode.py` | Base class — HTML viewer, markdown converter, async render |
| `data/MarkdownNodeData.py` | Pure Python dataclass — `label` (raw markdown), `depth_front` |
| `nodes/ArchitectureNode.py` | Subclass for `Architecture.md` |
| `nodes/NodeSchemaNode.py` | Subclass for `Node Type Schema.md` |
| `nodes/ReadmeNode.py` | Subclass for `README.md` |
| `nodes/RegistryNode.py` | Subclass for `node_registry.toml` |

## How It Works

### Spawning

The Info sidebar menu scans `Documents/` recursively. Subdirectories become submenus, `.md` files become menu entries. Clicking an entry reads the file's text and passes it as the `label` field to `Scene.add_markdown_node(pos, label=text)`. Two files are excluded from the generic scan (`_DEDICATED = {"Architecture.md", "Node Type Schema.md"}`) and instead get dedicated factory entries that spawn their own subclass: `Architecture.md` → `ArchitectureNode`, `Node Type Schema.md` → `NodeSchemaNode`.

The `Documents/Data/` subfolder is excluded from the menu scan (`_SKIP_DIRS = {"data", "Data"}`).

The Info menu also surfaces a **Memory** submenu when `~/.claude/projects/{cwd-encoded}/memory/` exists — Anthropic's Claude Code memory store for the current working directory. `MEMORY.md` is pinned to the top of this submenu and runs through a `_transform_memory_index()` pre-parse that rewrites its bullet-link index format (`- [Name](file) — desc`) into standard `## Name` + body so the chunker can chew it. Memory files are kept outside the general pipeline as an external-format isolation layer — Anthropic owns that format and may change it across Claude Code versions; the rewrite is the only adapter, and the rest of the pipeline stays unaware of the special case.

### Async Rendering

Markdown-to-HTML conversion is CPU-bound (the `markdown` package plus regex post-processing). To keep the canvas responsive:

1. `__init__` starts a daemon thread running `_render_worker()`
2. The worker calls `_markdown_to_html(self.data.label)` and stores the result in `_pending_html`
3. A `QTimer` at 100ms interval polls `_check_render_delivery()` on the main thread
4. When `_pending_html` is set, the timer stops, the HTML is injected into the QTextEdit

The node appears instantly with an empty viewer. Content fills in shortly after without blocking pan/zoom or other nodes.

### Markdown to HTML Pipeline

`_markdown_to_html()` is a static method that runs on the worker thread. The pipeline:

1. **markdown package** converts raw markdown to HTML using three extensions:
   - `tables` — pipe-delimited table syntax
   - `fenced_code` — triple-backtick code blocks
   - `codehilite` — syntax highlighting via Pygments (Monokai theme, inline styles)

2. **Inline style injection** — Qt's QTextEdit ignores `<style>` blocks entirely. All styling must be inline on each element. The method does a series of string replacements to inject GitHub dark theme colors:
   - Headings: `#e6edf3` text, 600 weight, `Segoe UI` font family, bottom border on h1/h2
   - Paragraphs: 14px `Segoe UI`, `#e6edf3`
   - Code blocks: Monokai-themed with transparent background (code background is `#282828`)
   - Inline code: `#343942` background pill
   - Tables: `#30363d` borders, header background `#282828`
   - Links: `#58a6ff`
   - Blockquotes: left border, muted text `#8b949e`
   - Horizontal rules: `#30363d` top border

3. **Pygments cleanup** — strips the wrapper `<div class="codehilite">` and empty `<span></span>` tags that Pygments generates.

4. **ASCII tree conversion** — detects `<pre>` blocks containing box-drawing characters (`├└│─`) and converts them from raw ASCII art into emoji-decorated tree lines. This is the `_cozy_tree_line()` parser (legacy name, same function in `TextNode.py`). It:
   - Parses indentation depth from box-drawing prefixes
   - Adds 📁/📄 emoji
   - Colors folders in `#d4a44c`, files in `#e6edf3`, descriptions in `#8b949e`
   - Replaces the `<pre>` block with a styled `<p>` block

### Spawn Pipeline

The "spawn nodes" button on the MarkdownNode (sticker-style icon, added in `_build_buttons`) takes the rendered markdown text and explodes it into a chained tree of `AboutNode` and `WarmNode` instances on the canvas; the source MarkdownNode then self-vaporises (zombie-spawn pattern), leaving the spawned tree as the new on-canvas representation of the document.

`_split_into_nodes(title_pattern=r'^#{1,6}\s+')` is the entry point. The `title_pattern` regex defaults to "match markdown headings H1–H6" but is exposed as a parameter so future formats (shader code, FBX outlines, anything with non-markdown delimiters) can chunk on different patterns without subclassing.

**Chunking.** Lines matching `title_pattern` open a new section; everything between two title lines becomes that section's body. Each `(title, body)` pair becomes one (optional) AboutNode for the heading, followed by zero or more nodes for the body's paragraphs.

**Paragraph classification.** Body text is split on blank lines. Each paragraph is sized against `_CALLOUT_MAX_CHARS = 90`:

- **≤ 90 chars** → `AboutNode` callout (the green pill). The small punctuation of the document.
- **> 90 chars** → `WarmNode` substance panel (the dark prose box). The body weight of the document.

Backticks are stripped from the measured copy first so `` `identifier` `` doesn't inflate a callout into substance.

**WarmNode title extraction.** Long paragraphs run through two title-extraction passes:

1. `_transform_markdown_table()` — if the paragraph is a markdown table (header row, `|---|---|` separator on line 2, data rows), the header cells are joined into the title (Oxford comma at 3+ cells), the separator is dropped, and each data row becomes a single pipe-stripped, whitespace-collapsed body line.
2. `_extract_leading_bold()` — otherwise, if the paragraph opens with `**phrase**` (optionally preceded by a `1.`, `-`, or `*` list marker; optionally followed by a `—`, `:`, or `-` separator), the phrase becomes the title and the rest becomes the body. Trailing `:` and `.` are stripped from the title since the WarmNode title font already cues end-of-phrase visually.

If neither pass fires, the WarmNode spawns with an empty title and the full paragraph as body.

**Label normalisation.** All AboutNode labels and WarmNode titles run through `prettify_label()` (in `utils/label_cleanup.py`):

- ISO dates `YYYY-MM-DD` → `Month Dayth Year`
- ` — ` (em-dash with surrounding spaces) → `: `
- `**bold**` and lone `*italic*` markers stripped
- Box-drawing chars (Unicode U+2500 block) stripped — defensive backstop for ASCII tree fragments leaking from `<pre>` blocks into a title slot
- Backticks stripped
- Trailing `:` stripped

WarmNode body text gets a lighter pass (just `**` and `*` strip) so prose body keeps its in-line ISO dates and em-dashes verbatim.

**Structural filtering.** Paragraphs matching `is_structural_only()` (`---`, `***`, `===`, table separators with ≥3 non-whitespace structural chars) are skipped entirely — they're source scaffolding, not content the reader needs a node for.

**Layout.** Spawned nodes are placed via `spiral_place()` in `utils/placement.py`, anchored each to the previous node's `_wander_origin`. Placement runs through a 3D raycaster so nodes scatter organically around their anchor rather than landing on a grid — the result is the readable tree shape, not a spreadsheet. `Connection` wires chain consecutive spawned nodes in reading order. The first spawned node gets viewport-centred placement when the source MarkdownNode is offscreen.

**WarmNode auto-fit.** WarmNodes call `_auto_fit_title_width()` (widens only if the extracted title would otherwise clip) and `_auto_fit_height(shrink=True)` (snug-fits height to body content). Both are guarded by `hasattr()` so the rename-driven exposure pass (cozy → pretty → intricate) doesn't trip silent breakage on a renamed method.

### Background Color

The node uses `#0d1117` (GitHub's dark theme background) instead of `Theme.nodeBg`. This is set in `__init__` via `setBrush()` and respects `Theme.aboutTransparency` for the alpha blend. The depth toggle (`_apply_depth`) re-applies this brush so front/back layer switching preserves the GitHub look.

## HTML Viewer

A plain `QTextEdit` wrapped in a `QGraphicsProxyWidget`:

- **Read-only** — `setReadOnly(True)`, no editing
- **No frame** — `setFrameShape(NoFrame)`
- **Custom scrollbar** — 6px wide, `#30363d` handle, transparent track
- **Selection colors** — `#264f78` highlight, `#e6edf3` text
- **Document margin** — 12px via `document().setDocumentMargin(12)`
- **Horizontal scroll** — always off

The viewer is positioned inside the node below the button zone (`_BUTTON_ZONE_H = 40px`) with `_PAD = 8px` padding on all sides.

## Data Class

`MarkdownNodeData` extends `NodeData` with two fields:

- `label: str` — the raw markdown source text (not HTML)
- `depth_front: bool` — front/back layer toggle state

Default size: 400 x 320. No `node_type` registry entry — MarkdownNodes are not in `node_registry.toml` because they're spawned programmatically from the Info menu, not from sidebar buttons.

## Lifecycle

### Creation
`Scene.add_markdown_node(pos, label=text)` → `MarkdownNode(MarkdownNodeData(label=text))` → viewer built → daemon thread starts rendering → timer delivers HTML.

### Session restore
`MarkdownNodeData.from_dict(d)` reconstitutes the dataclass with the saved `label`. The markdown is re-rendered from scratch on every load — HTML is never persisted.

### Removal
`_prepare_for_removal()`:
1. Stops the delivery timer
2. Disconnects `timeout` signal (explicit `.disconnect()` to break the C++ signal reference)
3. Severs the proxy via `setWidget(None)` — prevents the ucrtbase.dll stack overrun on Windows when Python GC races Qt's C++ destructor
4. Nulls `_editor` and calls `super()`

### Serialization
`to_dict()` calls `sync_data()` then returns `data.to_dict()`. The raw markdown `label` is what gets saved — no HTML in the session file.

## The _cozy_tree_line Parser

Both `MarkdownNode` and `TextNode` contain identical copies of `_cozy_tree_line()`. This is a local function inside `_markdown_to_html()` / the equivalent in TextNode. It converts ASCII tree lines (the `├── 📁 folder/` format) into styled HTML spans.

The parser handles:
- Box-drawing character depth counting (`├──`, `└──`, `│`)
- Fallback to space-based indentation (4 spaces = 1 depth level)
- Description extraction after `—` or `─` separators
- Color assignment: folders `#d4a44c`, files `#e6edf3`, descriptions `#8b949e`
- Icon injection: 📁 for folders (trailing `/` or contains `(`), 📄 for files

This is a legacy name from v0.0.1 — renaming to `_intricate_tree_line` is pending as part of the broader Cozy → Intricate naming migration.

## Technical Notes

- The `markdown` Python package is a runtime dependency. If missing, the worker thread catches the ImportError and sets `_pending_html` to an error message.
- The delivery timer fires at 100ms intervals — fast enough to feel instant, slow enough to not waste cycles polling.
- `paint_content()` is a no-op — all rendering is delegated to the QTextEdit proxy. The node title comes from `BaseNode`'s default title paint.
- Subclasses typically only override `__init__` (to set a different data class) and `_build_buttons()` (to add node-specific controls). The markdown rendering pipeline is shared.

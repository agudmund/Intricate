# Intricate Node Type Schema

> **34 node types** across 8 sidebar categories.
> Every node exists because it earned its place through daily use.
> This document is the living reference — update it when nodes are added, renamed, or reorganised.

---

## Sidebar Layout

The sidebar runs top-to-bottom in this order. Each icon opens a category menu.

| Position | Category | Icon | Nodes |
|----------|----------|------|-------|
| 1 | Text | `iconText` | About, Warm, Text, Cushions, Code, Bloom, Null |
| 2 | Images | `iconImagesGroup` | Image, Video, Sequence, Fluff and Honey |
| 3 | Audio | `iconAudioGroup` | Sound, Merger, Silence |
| 4 | Visual | `iconVisualGroup` | Bezier, Palette, Value, Sticker |
| 5 | Health | `iconHealthGroup` | Health, Perf, Log, Joy Inspector |
| 6 | Tools | `iconToolsGroup` | Restore, Snip, Git, Tree, Session, Premiere Bridge |
| 7 | Info | `iconInfoGroup` | Intricate, Readme, Architecture, Node Schema, Registry |
| 8 | Claude | `iconClaude` | Claude, Census, Response (auto-spawned) |

---

## Text Category

### The Glorious About Node
- **Type key:** `about` | **Icon:** `iconAbout`
- **Files:** `nodes/AboutNode.py`, `data/AboutNodeData.py`
- Minimal sticky-note. Single editable label, no body area. Double-click to edit. Used as a category memo planted near groups of nodes.
- `_has_depth_toggle = True`, `_show_emoji_btn = False`

### The Comfortable Warm Node
- **Type key:** `warm` | **Icon:** `iconWarm`
- **Files:** `nodes/WarmNode.py`, `data/WarmNodeData.py`
- The main content node — the star of the show. Emoji accent + title row with free-form body text area. Double-click to activate editor. Integrates with bridge file for cross-app serialisation.
- `_has_depth_toggle = True`

### The Simple Text Node
- **Type key:** `text` | **Icon:** `iconText`
- **Files:** `nodes/TextNode.py`, `data/TextNodeData.py`
- Always-editable plain text node (Lato font). No double-click activation — click anywhere and start typing.
- `_has_depth_toggle = True`

### The Cushions Node
- **Type key:** `cushions` | **Icon:** `iconCushions`
- **Files:** `nodes/CushionsNode.py`, `data/CushionsNodeData.py`
- Cushioned text node with export button on the button strip. Based on TextNode with always-editable multiline text.
- `_has_depth_toggle = True`

### The Code Node
- **Type key:** `code` | **Icon:** `iconCode`
- **Files:** `nodes/CodeNode.py`, `data/CodeNodeData.py`
- Syntax-highlighted code display with monospace font (Consolas). Supports drag-and-drop of code files from Explorer. Browse button on button strip.
- `_has_depth_toggle = True`

### The Bloom Node
- **Type key:** `bloom` | **Icon:** `iconBloom`
- **Files:** `nodes/BloomNode.py`, `data/BloomNodeData.py`
- Particle scatter controller — original Intricate algorithm. Embedded controls (combobox, spinbox, sliders) for configuring scatter mode, count, seed, density falloff, stiffness, speed, and distance. Fire button triggers the burst.
- `_has_depth_toggle = True`

### The Null Node
- **Type key:** `null` | **Icon:** `iconNull`
- **Files:** `nodes/NullNode.py`, `data/NullNodeData.py`
- Transparent passthrough anchor. No content, no editor — just ports, a position, and a subtle crosshair. Used as spatial reference point for BloomNode scatter origins, wire routing, etc.
- `_has_depth_toggle = True`, ports always visible

---

## Images Category

### The Images
- **Type key:** `image` | **Icon:** `iconImage`
- **Files:** `nodes/ImageNode.py`, `data/ImageNodeData.py`
- Renders image thumbnail on canvas with editable caption. Auto-spawns an AboutNode wired as caption. Double-click image area to browse. Supports base64 and file paths. Vision rename and stamp buttons on button strip.
- Backed by the shared byte-preserving media cache (`utils/media_cache.py`) — content-addressed, EXIF/XMP/ICC/tEXt preserved, passive drift detection on restore. See `Documents/Nodes/The Image Node.md`.
- `_has_depth_toggle = True`

### The Videos
- **Type key:** `video` | **Icon:** `iconVideo`
- **Files:** `nodes/VideoNode.py`, `data/VideoNodeData.py`
- Full video playback inside node body via QMediaPlayer. Progress bar scrub, volume slider, mute and loop toggles. Double-click to load. Supports .mp4, .avi, .mov, .mkv, .webm and more.
- **LOD-adaptive rendering** — each incoming frame sized at ingest to `video_rect × view zoom`, capped at source resolution. Memory proportional to on-screen size, so hundreds of tiny clips in an animatic view stay light while zooming into one gets crisp up to source res. Paused videos re-emit on LOD change via `setPosition()` nudge.
- **Byte-preserving media cache** (shared with ImageNode). Data fields: `source_path`, `cache_key` (dotted `<sha256>.<ext>`), `source_size` + `source_mtime` as cheap drift fingerprints. Three-tier restore: source → cache → placeholder. Drift detection uses stat first, full rehash only on mismatch, surfaces as AboutNode sticky note — never auto-heals. See `Documents/Nodes/The Video Node.md`.
- `_has_depth_toggle = True`

### The Sequences
- **Type key:** `sequence` | **Icon:** `iconSequence`
- **Files:** `nodes/SequenceNode.py`, `data/SequenceNodeData.py`
- Image sequence scrubber — loads frames from a folder on demand. Slider iterates over sorted files. Double-click to pick folder. Header, image area, scrub slider, and frame counter.
- `_has_depth_toggle = True`

### The Fluff and Honey Node
- **Type key:** `fbx` | **Icon:** `iconFbx`
- **Files:** `nodes/FbxNode.py`, `data/FbxNodeData.py`
- 3D model viewer placeholder. Will load vertices from fluffandhoney.dll, render point clouds with perspective projection, and orbit camera with scrubber. Currently a pretty placeholder with intent.
- `_has_depth_toggle = True`

---

## Audio Category

### The Sound
- **Type key:** `audio` | **Icon:** `iconAudio`
- **Files:** `nodes/AudioNode.py`, `data/AudioNodeData.py`
- Compact audio player for WAV, MP3, FLAC and friends. Drop file or browse to load. Play/pause via status line click. Mute toggle (emoji), split at playhead (sticker), and loop toggle (sticker) on button strip. Volume slider and progress bar scrub.
- `_has_depth_toggle = True`

### The Merger
- **Type key:** `merge` | **Icon:** `iconMerge`
- **Files:** `nodes/MergeNode.py`, `data/MergeNodeData.py`
- Lists connected AudioNodes in sequential order as a merge staging area. Manual drag-to-reorder list (custom implementation — Qt's InternalMove breaks in proxy widgets). Builds ffmpeg command for final merge.
- `_has_depth_toggle = True`

### The Silence
- **Type key:** `audio_hold` | **Icon:** `iconAudio`
- **Files:** `nodes/AudioHoldNode.py`, `data/AudioHoldNodeData.py`
- Silence placeholder — pure data, no audio player, no files. MergeNode reads hold_seconds and inserts silence via anullsrc in the ffmpeg chain. Scrub progress bar to adjust duration. Zero resource usage.
- `_has_depth_toggle = True`

---

## Visual Category

### The Prestigious Bezier Node
- **Type key:** `bezier` | **Icon:** `iconBezier`
- **Files:** `nodes/BezierNode.py`, `data/BezierNodeData.py`
- Interactive cubic bezier curve with draggable control handles. Children handle items allow manipulation of cp1/cp2 offsets within node bounds.

### The Beautiful Palette Node
- **Type key:** `palette` | **Icon:** `iconPalette`
- **Files:** `nodes/PaletteNode.py`, `data/PaletteNodeData.py`
- Swatch board: collect hex values and see their colours side by side. Entries include label, colour swatch box, and editable hex value. Drag-droppable with MIME type for colour exchange.

### The Oddly Important Value Node
- **Type key:** `value` | **Icon:** `iconValue`
- **Files:** `nodes/ValueNode.py`, `data/ValueNodeData.py`
- Transparent image-sequence node with PrettySlider scrubber. Fills node body with current frame from `./Images/Value/`. Fully transparent background — floats above regular nodes at Z=100.

### Snickers Stickers!
- **Type key:** `sticker` | **Icon:** `iconSticker`
- **Files:** `nodes/StickerNode.py`, `data/StickerNodeData.py`
- Frameless, chromeless PNG sticker. No buttons, border, or caption — just image with alpha composited directly onto canvas. Double-click to browse PNG. Floats above regular nodes at Z=100.

---

## Health Category

### The Health Node
- **Type key:** `health` | **Icon:** `iconHealth`
- **Files:** `nodes/HealthNode.py`, `data/HealthNodeData.py`
- Live system health monitor. Polls Python GC on configurable interval, displays current node census. Click detection via OSClickMonitor (WH_MOUSE_LL global Windows hook) classifies clicks as Qt scene, Qt widget, or external process.
- `_has_depth_toggle = True`

### The Performance Beast
- **Type key:** `perf` | **Icon:** `iconPerf`
- **Files:** `nodes/PerfNode.py`, `data/PerfNodeData.py`
- Live UI performance monitor. Times every paint lap via _PaintTimer event filter on viewport. Rolling frame-time window (120 samples), ignores stalls > 2s.
- `_has_depth_toggle = True`

### Tinkerbells Tail
- **Type key:** `log` | **Icon:** `iconLog`
- **Files:** `nodes/LogNode.py`, `data/LogNodeData.py`
- Live tail of current session log file (intricate.log). QFileSystemWatcher fires on file writes; 1.5s poll timer backs it up. Keeps last 400 lines.
- `_has_depth_toggle = True`

### The Joy Inspector
- **Type key:** `joy_stats` | **Icon:** `iconHealth` (pink fallback)
- **Files:** `nodes/JoyStatsNode.py`, `data/NodeData.py` (generic base)
- Live debug display for the joy tamagotchi system. Reads all joy state from main window every second, paints compact stats grid. Pure read-only.
- `_has_depth_toggle = True`, `_show_emoji_btn = True`

---

## Tools Category

### The Grand Restoration
- Not a node — sidebar action that brings back the last deleted node.

### There Comes A Time In Everyone's Life... (Snip)
- Not a node — sidebar action that enters wire snip mode to remove explicit wire connections.

### The Not So Boring Anymore Node (Git)
- **Type key:** `git` | **Icon:** `iconGit`
- **Files:** `nodes/GitNode.py`, `data/GitNodeData.py`
- Git status dashboard for all Desktop repos. Polls git status every 10 seconds on daemon thread. GitHub Desktop launch and bulk push buttons on button strip.
- `_has_depth_toggle = True`

### The Stuff and Stuff (Tree)
- **Type key:** `tree` | **Icon:** `iconTree`
- **Files:** `nodes/TreeNode.py`, `data/TreeNodeData.py`
- Project folder structure display via in-process tree walker. Respects gitignore and TOML filters. No subprocess or temp files.
- `_has_depth_toggle = True`

### Total Recall (Session)
- **Type key:** `session` | **Icon:** `iconSession`
- **Files:** `nodes/SessionNode.py`, `data/SessionNodeData.py`
- Utility for inspecting and importing external session files. Drop session file to see summary (node count, type breakdown, connections). Import button spawns all nodes and connections at SessionNode position.
- `_has_depth_toggle = True`

### The Premiere Bridge Node
- **Type key:** `premiere_bridge` | **Icon:** `iconPremiereBridge`
- **Files:** `nodes/PremiereBridgeNode.py`, `data/PremiereBridgeNodeData.py`, `utils/premiere_transport.py`
- Live wire to Adobe Premiere Pro 2026 via CEP extension. Owns a `WebSocketTransport` targeting `ws://127.0.0.1:9914` where a Node.js server inside Premiere's CEP panel listens. Frames travel as `Prop|Val|Track|Clip`. Handshake on connect (`HELLO` → `READY|ERROR`), 5s heartbeat (`PING` → `PONG`), three-strikes silent-wire detection. On `ERROR` or silent wire, spawns a chained AboutNode carrying a poetic reason line plus structural details (expected/actual, available sequences). Permissive by default; flip to strict mode by populating `expected_project` / `expected_sequence`. Full canonical writeup at `Documents/Nodes/The Premiere Bridge Node.md`.
- `_has_depth_toggle = True`

---

## Info Category

### Intricate
- **Type key:** `info` | **Icon:** `iconInfo`
- **Files:** `nodes/InfoNode.py`, `data/InfoNodeData.py`
- Read-only node displaying app version and era. No editor — just painted label with poetic body lines.
- `_has_depth_toggle = True`

### The Readme
- **Type key:** `readme` | **Icon:** `iconTree`
- **Files:** `nodes/ReadmeNode.py`, `data/ReadmeNodeData.py`
- Read-only markdown renderer inheriting from MarkdownNode. Converts markdown to GitHub-styled HTML in a scrollable QTextEdit. Spawn-nodes button splits body text into individual AboutNodes. Content set at creation.
- `_has_depth_toggle = True`

### Architecture
- **Type key:** `architecture` | **Icon:** `iconInfoGroup`
- **Files:** `nodes/ArchitectureNode.py`, `data/ArchitectureNodeData.py`
- Read-only viewer for `Documents/Architecture.md`. Inherits MarkdownNode — loads the architecture reference document from disk at creation.
- `_has_depth_toggle = True`

### Node Type Schema
- **Type key:** `node_schema` | **Icon:** `iconInfoGroup`
- **Files:** `nodes/NodeSchemaNode.py`, `data/NodeSchemaNodeData.py`
- Read-only viewer for `Documents/Node Type Schema.md`. Inherits MarkdownNode — loads this document from disk at creation.
- `_has_depth_toggle = True`

### The Registry
- **Type key:** `registry` | **Icon:** `iconInfoGroup`
- **Files:** `nodes/RegistryNode.py`, `data/RegistryNodeData.py`
- Live viewer for `node_registry.toml` — the creative writing surface for node naming. Renders all entries as a formatted markdown table grouped by category. Watches the registry file and re-renders on changes. Edit button opens the TOML in the system editor.
- `_has_depth_toggle = True`

---

## Claude Category

### The Majestic Claude Node
- **Type key:** `claude` | **Icon:** `iconClaudeNode`
- **Files:** `nodes/ClaudeNode.py`, `data/ClaudeNodeData.py`
- Claude API integration with custom input field (Enter submits, Shift+Enter newline). Spawns ClaudeResponseNode instances with replies, wired in a chain. Body toggle button (sticker icons) to collapse/expand the reply log.
- `_has_depth_toggle = True`

### The Curious Token Counter (Census)
- **Type key:** `claude_info` | **Icon:** `iconClaudeCensus`
- **Files:** `nodes/ClaudeInfoNode.py`, `data/ClaudeInfoNodeData.py`
- Live token-usage dashboard. Scans all JSONL files in Claude projects folder on daemon thread, surfaces cumulative stats on main thread via QTimer.
- `_has_depth_toggle = True`

### Claude's Emotional Scale (Response)
- **Type key:** `claude_response` | **Icon:** `iconClaudeResponse`
- **Files:** `nodes/ClaudeResponseNode.py`, `data/ClaudeResponseNodeData.py`
- Multiline sticky note capturing a full Claude reply. Auto-sized based on text dimensions. Medium Oblique font for visual distinction.
- `_has_depth_toggle = True`
- **Not user-spawnable** — created programmatically by ClaudeNode only.

---

## Statistics

| Metric | Count |
|--------|-------|
| Total node types | 34 |
| User-spawnable from sidebar | 33 |
| Programmatically-spawned only | 1 (ClaudeResponseNode) |
| With depth toggle | 28 |
| Without depth toggle | 6 (Bezier, Palette, Value, Sticker, plus 2 non-node actions) |
| Sidebar categories | 8 |

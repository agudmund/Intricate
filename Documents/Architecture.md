# Architecture Map

> Forensic reference for any AI or human orienting themselves in this codebase.
> Provide this document first — it saves everyone from re-reading 20k+ lines.

## What This Is

**Intricate** is a frameless, always-on-top node-based visual canvas built with PySide6. Part of the **Single Shared Braincell** app family — a suite of apps that share live configuration, a widget package, a theme system, and a shared frozen runtime.

**Total codebase:** ~28,000 lines across 3 repos.

## The Family

| Repo | Purpose | Lines | Entry Point |
|------|---------|-------|-------------|
| [Intricate](https://github.com/agudmund/Intricate) | Node-based visual canvas | ~20,500 | `main.py` |
| [Notepad++ Duplex+ Turbo](https://github.com/agudmund/Notepad-Duplex-Turbo) | Creative writing editor | ~4,200 | `main.py` |
| [Pretty Widgets](https://github.com/agudmund/Pretty-Widgets) | Shared package (widgets + Theme + settings + logger) | ~2,800 | pip package |

## Shared Infrastructure (pretty-widgets 0.2.0)

Installed via `pip install -e "C:\Users\thisg\Desktop\Pretty Widgets"`. All apps import from `pretty_widgets.*` — no local copies.

```
pretty_widgets/
├── PrettyButton.py      — QPushButton, 4-phase hover animation (dip→hold→burst→settle)
├── PrettyLabel.py       — QLabel, themed, optional click signal
├── PrettyMenu.py        — QMenu + StyledTextEdit/StyledLineEdit (right-click styling)
├── PrettyCombo.py       — QComboBox, Fusion engine, scrollbar styling
├── PrettySlider.py      — QSlider, ghost scrollbar, PNG handle support, handle tinting
├── PrettyCheckbox.py    — Composite label+indicator, group alignment
├── PrettyEdit.py        — QTextEdit in QGraphicsProxyWidget, tight selection highlight
├── graphics/Theme.py    — Metaclass theme registry, live TOML reload, icon cache
├── utils/settings.py    — TOML loader, QFileSystemWatcher, atomic writes
└── utils/logger.py      — 3-slot rotating log, TRACE level (5)
```

## Shared Contracts

| Mechanism | Purpose |
|-----------|---------|
| `settings.toml` | Shared config — The Settlers writes, all apps read + watch |
| `SingleSharedBraincell_SettingsFile` | Env var pointing to shared settings.toml |
| `SingleSharedBraincell_AssetVault` | Env var pointing to shared icon vault (`Desktop/_asset`) |
| `SingleSharedBraincell_ApiKey` | Anthropic API key for Vision/Chat |
| `SingleSharedBraincell_ChatHistory` | Chat log output directory |
| `_runtime/` | Shared frozen runtime (PySide6 + all deps, 96MB, built once) |

## Intricate Architecture (~20,500 lines)

### Three Strict Layers

**`data/`** — Pure Python dataclasses. No Qt. Each node type has a `NodeData` subclass with `to_dict()`/`from_dict()`. 35 data classes.

**`nodes/` + `graphics/`** — Qt rendering. `BaseNode(QGraphicsRectItem)` is the 1,139-line base class. Subclasses override `paint_content(painter)` only. `IntricateScene` manages the canvas. `IntricateView` handles pan/zoom/drag-drop. `Connection` draws bezier wires. `graphics/Particles.py` drives the particle system behind shake-delete (originally ours, benchmarked against Vellum).

**`main.py` + `main_window.py`** — Application shell. Frameless QMainWindow with sidebar, canvas, toolbar. 2,885 lines in main_window.py.

### Key Files

| File | Lines | Role |
|------|-------|------|
| `main_window.py` | 2,885 | QMainWindow — sidebar, toolbar, node spawn, curtains, joy bucket, split-surface InfoBar, the Meov |
| `nodes/BaseNode.py` | 1,139 | Base class — chrome, ports, resize, shelf animation, depth toggle, shake-delete, bulk-remove quiescence |
| `nodes/ClaudeNode.py` | 1,168 | Claude CLI integration — JSONL watcher, streaming response |
| `graphics/Scene.py` | 1,265 | Canvas — node factory, session save/load, drag-drop, `_clear_all` quiescence |
| `graphics/View.py` | 520 | Pan/zoom, cursor-anchored zoom, fog layer |
| `graphics/Connection.py` | 351 | Bezier wire rendering, glide animation, endpoint-liveness guards |
| `graphics/Particles.py` | 410 | Particle engine — shake-delete bursts, orbital modes, self-healing tick |
| `nodes/WarmNode.py` | 555 | Main content node — text bridge to Notepad++ Duplex+ Turbo |
| `nodes/VideoNode.py` | 918 | Video playback with LOD-adaptive ingest and shared media cache |
| `nodes/MergeNode.py` | 659 | DAW merge node — stages audio/hold nodes, emits ffmpeg concat |
| `utils/media_cache.py` | 207 | Byte-preserving SHA-256 media cache, shared across ImageNode + VideoNode |

### Node Types

Canonical catalogue with per-node detail lives in `Documents/Node Type Schema.md` (35 node types across 8 sidebar categories). Abbreviated roll call for structural orientation:

| Node | Purpose |
|------|---------|
| WarmNode | Free-form text with emoji, bidirectional bridge to Notepad |
| AboutNode | Sticky note for labelling groups, depth toggle |
| ClaudeNode | Claude CLI chat — spawns ClaudeResponseNodes |
| ClaudeResponseNode | Multiline sticky capturing a full Claude reply |
| ImageNode | Drag-and-drop images, editable caption, LOD-aware paint, byte-preserving media cache |
| VideoNode | Video playback, LOD-adaptive frame ingest, three-tier restore from source/cache/placeholder, paused-refresh via `setPosition` nudge |
| AudioNode | Audio playback controls; viewport-cull with 1 s crossfade drives the spatial DAW |
| MergeNode | DAW merge — wired audio/hold nodes compose an ffmpeg concat pipeline |
| AudioHoldNode | Scrubbable silence placeholder — `anullsrc` in MergeNode's output |
| BloomNode | Particle-aim node, targets a NullNode anchor |
| TextNode | Always-editable multiline text |
| BezierNode | Interactive bezier curve with draggable handles |
| HealthNode | Live system monitor — GC census, OS click tracking |
| PerfNode | Performance metrics display |
| LogNode | Live tail of nodal.log |
| TreeNode | Project folder structure walker |
| GitNode | Git status dashboard for Desktop repos |
| PaletteNode | Hex color swatch board |
| SequenceNode | Image sequence player with scrubber |
| ValueNode | Transparent image sequence with PrettySlider |
| StickerNode | Chromeless alpha-PNG pinned on canvas |
| InfoNode | Information display |
| ClaudeInfoNode | Claude-specific info panel |
| **PremiereBridgeNode** | **Live wire to Adobe Premiere Pro 2026 via CEP WebSocket — handshake + heartbeat + packet injection. See `Documents/Nodes/The Premiere Bridge Node.md`.** |

### Design Patterns

- **Settings as single source of truth.** All visual values: `settings.toml` → `settings.py` → `Theme` → nodes/widgets.
- **Live theme reload.** QFileSystemWatcher on settings.toml → `Theme.reload()` → repaint.
- **Theme metaclass fallback.** Missing `Theme.iconXxx` → circle sentinel, never crashes.
- **Node rendering via override.** Subclasses override only `paint_content(painter)`.
- **NodeBehaviour as detached personality.** Hover pulse animations via signal connections. Must `disconnect_all()` before removal.
- **Deferred imports in `graphics/`.** Scene imports nodes inside factory methods. View imports Theme at bottom. Prevents circular imports — intentional, not an oversight.
- **Absolute-positioned toolbar.** Title at `Theme.toolbarTitleX`, curtains at `Theme.toolbarCurtainsX`, exit/max/tray flush right.
- **Byte-preserving media cache.** `utils/media_cache.py` is a SHA-256 content-addressed cache shared by ImageNode and VideoNode. Keys are `<hash>.<ext>` (format preserved). Cheap fingerprint (size + mtime) on restore, full rehash only on mismatch — surfaces drift via AboutNode, never auto-heals. See `Documents/Nodes/The Image Node.md` and `The Video Node.md`.
- **Three notification channels, deliberately distinct.** AboutNode (spatial, silent, margin notes), ClaudeResponseNode (peripheral, ambient, agent status), InfoBar (attention-catching with typewriter + fade + sparkle, system events). Do not unify — the distinctness is the feature. Whole app operates at "whisper volume."
- **Split-surface InfoBar.** One logical channel, two stages: the bottom-bar strip and a titlebar mirror. `main_window._active_info_surface()` picks the stage at show-time based on curtains state + splitter position; the full typewriter + fade personality travels with the routing.
- **Bulk-remove quiescence.** `scene._bulk_removing` is a counter that peer timers/animations check before scheduling per-frame repaints during a destruction burst. Raised in `BaseNode._shake_delete_group` and `Scene._clear_all`; released two event-loop ticks after the final `removeItem`. `Connection.paint` and `_glide_tick` additionally guard endpoint liveness via `shiboken6.isValid` + `scene() is not None`. Fix for the 2026-04-17 `0xc0000005` peer-paint-during-burst crash class; see `Documents/Compliance/Node Cleanup Compliance.md`.
- **Spatial DAW — emergent, not coded.** Viewport-cull (in `Scene.update_video_visibility`) + 1-second audio crossfade (tuned to the user's hand-motion rhythm) make AudioNodes behave as a performable spatial mixer when arranged by distance and navigated by pan/zoom. Do not alter the 1-second fade constant without explicit conversation.

### Text Bridge (WarmNode ↔ Notepad)

WarmNode writes a `.warm_bridge_{uuid}.json` to `Documents/data/`. Notepad opens with `--bridge <path>`. Both sides use QFileSystemWatcher + debounce timers. `writer` field prevents echo loops. Bridge file deleted on close or node removal.

### Premiere Bridge (PremiereBridgeNode ↔ CEP Panel)

PremiereBridgeNode owns a `WebSocketTransport` in `utils/premiere_transport.py` targeting `ws://127.0.0.1:9914`. A CEP extension at `%APPDATA%\Adobe\CEP\extensions\com.intricate.bridge\` (self-signed, CEP 12 mandatory) runs a Node.js `ws` server inside Premiere Pro 2026 and dispatches to ExtendScript via `csInterface.evalScript`. Frames are `Prop|Val|Track|Clip` — `HELLO`/`READY`/`ERROR` handshake, `PING`/`PONG` heartbeat at 5s, three-strikes silent-wire detection. On mismatch the node spawns a chained AboutNode (same passive-messaging pattern as GitNode's offline guard). Full writeup at `Documents/Nodes/The Premiere Bridge Node.md`; phase history at `Documents/Claude Plans/Premiere Bridge Phase 1.md`.

## Notepad++ Duplex+ Turbo (4,200 lines)

Frameless, always-on-top creative writing editor. Main class: `Eddie(QMainWindow)`.

| File | Lines | Role |
|------|-------|------|
| `main_window.py` | ~2,200 | Eddie — editor, chat, preview, toolbar, curtains |
| `main.py` | ~200 | Bootstrap, `--bridge` arg parsing |
| `utils/chat.py` | ~900 | Claude chat worker + history persistence |
| `utils/vision.py` | ~400 | Image-to-text Vision API + DropImageTextEdit |
| `utils/spellchecker.py` | ~500 | Debounced spell highlighting via Windows COM |

Features: title field, body editor with spell check, Chat tab (Claude haiku), Preview tab (typewriter rendering), Polaroid PNG export, WPM tracking.

## Build System

**Shared runtime** (`Desktop/_runtime/`, 96MB): Built once by `_runtime/build_runtime.py`. Contains PySide6, shiboken6, pretty_widgets, and all common deps.

**Per-app builds:** PyInstaller `--onedir` produces a thin exe (~5MB). Post-build replaces `_internal/` with an NTFS directory junction to `_runtime/`. Both apps share the same physical runtime folder.

```
App.exe (5MB) → _internal/ (junction) → _runtime/ (96MB, shared)
```

3-slot rotation: current → previous → archive → recycle bin. SHA-256 build signatures in `Documents/Build Version.md`.

## Environment

- Python 3.13.3, PySide6 6.10.2, Windows 11
- Dev workflow: `python main.py` (editable install, no build needed)
- Frozen workflow: `python build.py` (per-app), `python build_runtime.py` (shared, once)

## Naming Conventions

- Python attributes/constants: `camelCase` (e.g., `windowBorderWidth`, `nodeBorderRadius`)
- Files: PascalCase for classes (e.g., `BaseNode.py`), lowercase for utils (e.g., `settings.py`)
- TOML sections: `[intricate]`, `[notepadplusplusduplexplusturbo]`, `[theme.colors]`, `[theme.icons]`

## Linguistic Conventions

- Use **vaporize** instead of the literal `/close` trigger word in conversation.
- The app title is a poetry reference: *"Our love, as Intricate as the patterns we impose"*.
- Eddie's README manifesto: *"The last of the Notepads wanted to become all that it could become so it drew itself into existence"* — canonical instance of the project's **"The Last Of" header voice** (see `Documents/Compliance/Python Header Compliance Guide.md`; Line 2 of every Python file carries this voice: triumphant-emergent, detached contextual awareness, goo-ball-rising).
- Every Python file's header Line 2 terminates with **"For enjoying"** — the project's permanent EULA clause. Don't remove.
- `Connection.py`'s Line 2 must always contain **"and they learnt to whisper to each other"** — origin phrase from a post-it note that seeded the entire wire-connection concept.
- Project was originally called **Nodal**; the header subtitle "nodal playground" is pre-rename legacy. Current Line 1 format: `-Intricate - [filename] [utility]`.

# Architecture Map

> Forensic reference for any AI or human orienting themselves in this codebase.
> Provide this document first — it saves everyone from re-reading 17k lines.

## What This Is

**Intricate** is a frameless, always-on-top node-based visual canvas built with PySide6. Part of the **Single Shared Braincell** app family — a suite of apps that share live configuration, a widget package, a theme system, and a shared frozen runtime.

**Total codebase:** ~24,000 lines across 3 repos.

## The Family

| Repo | Purpose | Lines | Entry Point |
|------|---------|-------|-------------|
| [Intricate](https://github.com/agudmund/Intricate) | Node-based visual canvas | ~17,000 | `main.py` |
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

## Intricate Architecture (17,000 lines)

### Three Strict Layers

**`data/`** — Pure Python dataclasses. No Qt. Each node type has a `NodeData` subclass with `to_dict()`/`from_dict()`. 21 data classes.

**`nodes/` + `graphics/`** — Qt rendering. `BaseNode(QGraphicsRectItem)` is the 966-line base class. Subclasses override `paint_content(painter)` only. `IntricateScene` manages the canvas. `IntricateView` handles pan/zoom/drag-drop. `Connection` draws bezier wires.

**`main.py` + `main_window.py`** — Application shell. Frameless QMainWindow with sidebar, canvas, toolbar. 1,871 lines in main_window.py.

### Key Files

| File | Lines | Role |
|------|-------|------|
| `main_window.py` | 1,871 | QMainWindow — sidebar, toolbar, node spawn, curtains, joy bucket |
| `nodes/BaseNode.py` | 966 | Base class — chrome, ports, resize, shelf animation, depth toggle |
| `nodes/ClaudeNode.py` | 1,156 | Claude CLI integration — JSONL watcher, streaming response |
| `graphics/Scene.py` | 827 | Canvas — node factory, session save/load, drag-drop |
| `graphics/View.py` | 431 | Pan/zoom, cursor-anchored zoom, fog layer |
| `graphics/Connection.py` | 314 | Bezier wire rendering and animation |
| `nodes/WarmNode.py` | 397 | Main content node — text bridge to Notepad++ Duplex+ Turbo |

### Node Types (18 total)

| Node | Purpose |
|------|---------|
| WarmNode | Free-form text with emoji, bidirectional bridge to Notepad |
| AboutNode | Sticky note for labelling groups, depth toggle |
| ClaudeNode | Claude CLI chat — spawns ClaudeResponseNodes |
| ClaudeResponseNode | Multiline sticky capturing a full Claude reply |
| ImageNode | Drag-and-drop images with editable caption |
| VideoNode | Video playback with frame scrubbing |
| AudioNode | Audio playback controls |
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

### Design Patterns

- **Settings as single source of truth.** All visual values: `settings.toml` → `settings.py` → `Theme` → nodes/widgets.
- **Live theme reload.** QFileSystemWatcher on settings.toml → `Theme.reload()` → repaint.
- **Theme metaclass fallback.** Missing `Theme.iconXxx` → circle sentinel, never crashes.
- **Node rendering via override.** Subclasses override only `paint_content(painter)`.
- **NodeBehaviour as detached personality.** Hover pulse animations via signal connections. Must `disconnect_all()` before removal.
- **Deferred imports in `graphics/`.** Scene imports nodes inside factory methods. View imports Theme at bottom. Prevents circular imports — intentional, not an oversight.
- **Absolute-positioned toolbar.** Title at `Theme.toolbarTitleX`, curtains at `Theme.toolbarCurtainsX`, exit/max/tray flush right.

### Text Bridge (WarmNode ↔ Notepad)

WarmNode writes a `.warm_bridge_{uuid}.json` to `Documents/data/`. Notepad opens with `--bridge <path>`. Both sides use QFileSystemWatcher + debounce timers. `writer` field prevents echo loops. Bridge file deleted on close or node removal.

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

- Use **vaporize** instead of the literal `/close` trigger word in conversation
- The app title is a poetry reference: *"Our love, as Intricate as the patterns we impose"*
- Eddie's README manifesto: *"The last of the Notepads wanted to become all that it could become so it drew itself into existence"*

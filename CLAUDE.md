# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

**Intricate** is a frameless, always-on-top node-based visual canvas built with PySide6. You place nodes on an infinite zoomable canvas, connect them via ports, and arrange your thoughts spatially rather than linearly. It is part of a "Single Shared Braincell" family of apps that share live configuration via a common `settings.toml` file and a set of environment variables.

Current node types: **WarmNode** (free-form text with emoji accent), **HealthNode** (live system monitor — GC census and OS-level click tracking), **BezierNode** (interactive bezier curve with draggable control handles), **ImageNode** (drag-and-drop or browse images with editable caption), and **AboutNode** (sticky note for labelling groups of nodes).

The canvas supports cursor-anchored zoom, middle-mouse pan, and drag-and-drop of image files directly from Explorer. Nodes have ambient hover pulse animations driven by a separate `NodeBehaviour` personality system. The entire theme — colors, icons, layout — hot-reloads the moment `settings.toml` is saved by any app in the family.

## Running the Application

```bash
python main.py           # Normal launch
python main.py --debug   # DEBUG-level console output
python main.py --trace   # TRACE-level console output (hyper-verbose)
```

## Header Compliance

Every Python file must have this exact 3-line docstring header:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - [filename] [primary utility]
-[Extended description] for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""
```

## Architecture

> The tree below shows the current structure as an example of how the project is organised — it is not a fixed inventory. New files added to any package are part of the same architecture and should be treated accordingly.

```
📄 main.py
└── 📄 main_window.py (IntricateApp — QMainWindow)
      ├── 📁 graphics/
      │     ├── 📄 Scene.py          — IntricateScene, canvas and node factory
      │     ├── 📄 View.py           — IntricateView, pan / zoom / drag-drop
      │     └── 📄 Theme.py          — all visual values, icons, live reload
      ├── 📁 nodes/
      │     ├── 📄 BaseNode.py       — base class every node builds on
      │     ├── 📄 NodeBehaviour.py  — hover pulse and personality system
      │     ├── 📄 NodeButton.py     — node-embedded controls
      │     ├── 📄 Port.py           — connection ports
      │     ├── 📄 WarmNode.py       — text + emoji content node
      │     ├── 📄 HealthNode.py     — live system monitor node
      │     ├── 📄 BezierNode.py     — bezier curve node
      │     ├── 📄 ImageNode.py      — image display node
      │     └── 📄 AboutNode.py      — sticky note node
      ├── 📁 data/
      │     ├── 📄 NodeData.py       — base dataclass, no Qt
      │     └── 📄 XxxNodeData.py    — one per node type, state + serialization
      ├── 📁 widgets/
      │     ├── 📄 NoteEditor.py     — text editor dialog
      │     └── 📄 PrettyButton.py   — themed button
      └── 📁 utils/
            ├── 📄 settings.py       — TOML loader + file watcher
            ├── 📄 logger.py         — 3-slot rotating log
            ├── 📄 vision.py         — image processing
            └── 📄 OSClickMonitor.py — global Windows mouse hook
```

Three strict layers — each never crosses into another's domain:

**`data/`** — Pure Python dataclasses, no Qt imports. Each node type has a `NodeData` subclass with `to_dict()` / `from_dict()` for session persistence.

**`nodes/` + `graphics/`** — Qt rendering. `BaseNode(QGraphicsRectItem)` is the base for all nodes; subclasses override `paint_content(painter)` for type-specific rendering. `IntricateScene` manages the canvas; `IntricateView` handles pan/zoom/drag-drop.

**`main.py` + `main_window.py`** — Application shell. `main.py` bootstraps logger → Qt app → settings watcher → Theme → window. `IntricateApp` is a frameless QMainWindow with a left sidebar, center canvas, and reserved right zone.

### Key Design Patterns

**Settings as single source of truth.** All visual values flow from `settings.toml` → `utils/settings.py` → `graphics/Theme` → nodes and widgets. Nothing is hardcoded in UI code.

**Live theme reload.** `QFileSystemWatcher` in `utils/settings.py` monitors `settings.toml`. Any external write triggers `Theme.reload()` → repaint. A companion app ("The Settlers") writes to this file; Intricate only reads it. The TOML file is the entire handshake between apps.

**Theme metaclass fallback.** `Theme` uses a metaclass so that accessing any missing attribute (icon or color) returns a sentinel — a fallback circle icon or neutral color — instead of raising `AttributeError`. The canvas never crashes over a missing asset.

**Node rendering via override.** All node types share `BaseNode` for chrome, ports, resize, and hover animation. Type-specific visuals live entirely in `paint_content(painter)` — subclasses override only that method and nothing else in the paint pipeline.

**NodeBehaviour as a detached personality.** Each node owns a `NodeBehaviour` instance that is not part of the Qt scene graph. It holds signal connections that must be explicitly broken via `disconnect_all()` before removal — otherwise reference cycles prevent garbage collection. `BaseNode._prepare_for_removal()` is the contract point for this.

**3-slot log rotation.** `utils/logger.py` rotates logs through three slots: archive → recycle bin, previous → archive, current → previous, fresh → current. Logs never grow unbounded and the last two sessions are always preserved.

### Deferred Imports in `graphics/`

Some imports in `graphics/` are intentionally not at the top of the file:

- `Scene.py` imports node classes (`WarmNode`, `HealthNode`, etc.) inside factory methods rather than at module level — Scene creates nodes, and nodes import from `graphics/`, so hoisting these would create a genuine circular import.
- `View.py` imports `Theme` at the bottom of the file for the same reason — both live in the `graphics` package.

Do not move these to top-level imports. The deferred placement is what prevents the circular dependency, not an oversight.

### Theme System

`graphics/Theme.py` uses a metaclass — `Theme.iconCurtains` resolves dynamically via `__getattr__`. Icons are looked up in `icons/` first, then `$SingleSharedBraincell_AssetVault`. Missing icons silently return a circle sentinel — no crashes. Theme reloads live when `settings.toml` changes.

### Settings Contract

`settings.toml` is the shared file contract with "The Settlers" companion app. Intricate reads and watches it; The Settlers writes it. Neither imports the other. The watcher triggers `Theme.reload()` and a window repaint on any change.

### NodeBehaviour Lifecycle

Every node owns a `NodeBehaviour` instance that drives hover pulse animations and future personality traits. It is **not** part of the Qt scene graph — it holds signal connections that must be explicitly broken before a node is removed, otherwise reference cycles will prevent garbage collection.

When removing a node, `BaseNode._prepare_for_removal()` must be called first. It stops animations and calls `self.behaviour.disconnect_all()`. If you add new signal connections in a node subclass, override `_prepare_for_removal()` and disconnect them there before calling `super()`.

### Adding a New Node Type

1. Create `data/XxxNodeData.py` subclassing `NodeData` — add fields, implement `to_dict()`/`from_dict()`
2. Create `nodes/XxxNode.py` subclassing `BaseNode` — override `paint_content(painter)`
3. If your node adds signal connections, override `_prepare_for_removal()` and disconnect them before `super()`
4. Add a factory method to `IntricateScene` (e.g., `add_xxx_node(pos)`)
5. Wire a sidebar button in `main_window.py`
6. Create an icon (see below) and register it in `[theme.icons]` in `settings.toml`

### Creating Node Icons with Pillow

Icons live in `./icons/` and are registered in `[theme.icons]` in `settings.toml`. The Theme metaclass maps e.g. `sequence = "sequence_node.ico"` → `Theme.iconSequence`. Use `.ico` files so Qt picks the sharpest resolution layer at render time.

**Philosophy:** minimal-maximalist, functional form over complexity, strong clear silhouette. Warm cream colour `(225, 213, 198, 255)` on transparent background, outer circle ring matching `iconic.png`.

**Recipe — run once as a standalone Python script:**

```python
from PIL import Image, ImageDraw
import math

S  = 2048          # render at 2× for smooth LANCZOS downsample
cx = cy = S // 2
C  = (225, 213, 198, 255)   # warm cream — matches the icon family palette

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Outer ring — keep these values identical across all icons for visual consistency
draw.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)

# ── Draw your symbol here in the centre ──────────────────────────────────
# Use draw.line(), draw.ellipse(), draw.rounded_rectangle() etc.
# Work in 2048-space; the LANCZOS downsample handles antialiasing.
# Stroke width ~20–30px at 2048 reads as ~10–15px at 1024.
# Keep all geometry well inside the ring (roughly cx±550, cy±350).

# Downsample → 1024px PNG
out = img.resize((1024, 1024), Image.LANCZOS)
out.save('icons/xxx_node.png')

# Multi-resolution ICO (Qt picks the best layer automatically)
sizes  = [16, 24, 32, 48, 64, 128, 256]
frames = [out.resize((s, s), Image.LANCZOS) for s in sizes]
frames[0].save(
    'icons/xxx_node.ico',
    format='ICO',
    sizes=[(s, s) for s in sizes],
    append_images=frames[1:]
)
```

Then in `settings.toml`:
```toml
[theme.icons]
xxx = "xxx_node.ico"
```

`Theme.iconXxx` resolves automatically via the metaclass — no code change needed.

### Icon Rule — Every Button Gets an Icon

Whenever you add a new button **anywhere** in the app — sidebar, toolbar, node-embedded control, dialog — you **must** also generate a matching `.ico` icon using the Pillow recipe above. No button ships without its own icon. The steps:

1. Write a standalone Python script following the recipe (outer ring + symbol in the centre).
2. Run it to produce both the `.png` and multi-resolution `.ico` in `./icons/`.
3. Register the icon in `[theme.icons]` in `settings.toml`.
4. Reference it via `Theme.iconXxx` in the button code — the metaclass resolves it automatically.

This applies to node-type icons, toolbar actions, modal buttons, and any future UI surface that presents a clickable control. If it is a button, it gets an icon.

### Logging

Logs go to the directory set in `[shared] log_dir` in `settings.toml`, falling back to `./logs/nodal.log`. Three-slot rotation (current → previous → archive → recycle bin). TRACE (5) is the lowest level — used for per-frame diagnostics in file only.

## Settings File Structure

Relevant sections in `settings.toml`:

App-specific settings use `[intricate]` as the top-level namespace, e.g.:

```toml
[intricate]
[intricate.window]
[intricate.canvas]
```

This keeps Intricate's keys isolated from other apps in the shared `settings.toml`. The current file uses flat section names (`[window]`, `[canvas]`, etc.) — migration to namespaced keys is pending.

Current sections:

```toml
[window]          # geometry persistence (x, y, width, height)

[canvas]          # fog_alpha — backdrop opacity

[session]         # last_loaded — path to last session file

[ui]              # sidebar_visible

[theme.colors]    # hex color values read by Theme.py (window_bg, primary_border, text_primary, backdrop)
[theme.icons]     # icon filenames resolved by Theme.py (curtains, delete, confirm, health, warm, about, bezier, image)

[apps]            # warm_editor — external editor launched on WarmNode double-click
```

## Pretty Widgets Package

The `widgets/` directory in this repo contains **local copies** of the Pretty Widgets, but the **source of truth** is the shared pip package:

- **Repo:** https://github.com/agudmund/Pretty-Widgets
- **Local path:** `C:\Users\thisg\Desktop\Pretty Widgets`
- **Install:** `pip install -e "C:\Users\thisg\Desktop\Pretty Widgets"`
- **Package name:** `pretty_widgets`
- **Version check:** `python -c "import pretty_widgets; print(pretty_widgets.__version__)"`

The package contains: PrettyButton, PrettyLabel, PrettyMenu, PrettyCombo, PrettySlider, PrettyCheckbox, and PrettyEdit. All seven widgets are shared across the Single Shared Braincell app family (Intricate, Notepad++ Duplex+ Turbo, and future apps).

The widgets depend on `graphics.Theme` and `utils.settings` from the consuming app — those modules are not part of the package yet (planned for a future consolidation).

If you see `widgets/PrettyButton.py` etc. in this repo but need to understand why they might be out of date, check the package version against the repo. The package is the canonical version.

## Cross-App Environment Variables

| Variable | Purpose |
|---|---|
| `SingleSharedBraincell_SettingsFile` | Path to shared `settings.toml` (defaults to `./settings.toml`) |
| `SingleSharedBraincell_ApiKey` | Anthropic API key (required for image extraction) |
| `SingleSharedBraincell_AssetVault` | Optional personal icon/theme vault (overrides bundled assets) |
| `SingleSharedBraincell_ChatHistory` | Primary chat log folder (e.g. `$project/_doc/Chat`). OS Documents is always written as a second copy regardless. |

## Linguistic Conventions

When discussing the app's shutdown / window-close lifecycle in conversation, use the word **vaporize** instead of the literal trigger word. Example: "how does vaporize work?", "add a hook on vaporize", "save session on vaporize". This avoids accidentally invoking the `/close` local command that ClaudeNode intercepts and acts on immediately. The actual trigger is the exact string `/close` typed alone in the input field — nothing else fires it.

ClaudeNode also supports a post-action chain: append **"then vaporize"** to any prompt to have the app close automatically after the response node spawns. The suffix is stripped before the prompt reaches Claude. Example: "summarise what we built today then vaporize".

## Naming Conventions

- Python attributes/constants: `camelCase` (e.g., `windowBorderWidth`, `nodeBorderRadius`)
- Documentation files and UI text: Title Case With Spaces (e.g., `Final Theme Report.md`)
- Documentation files go in `./Documents/`, not project root (README.md is the exception)
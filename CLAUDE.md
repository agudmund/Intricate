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

> **Forensic Map:** `Documents/Architecture.md` is the comprehensive reference for all three repos, shared infrastructure, design patterns, node types, and the build system. When making structural changes (new node types, new shared modules, build system changes, new apps in the family), update that document to keep it current.

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

### Documents Folder Structure

`Documents/` is organised into subdirectories by category. The Info sidebar menu dynamically scans this folder and builds nested context menus from its structure — subdirectories become submenus, `.md` files become entries that spawn MarkdownNodes.

```
Documents/
├── Architecture.md          — forensic map (dedicated ArchitectureNode)
├── Node Type Schema.md      — node type reference (dedicated NodeSchemaNode)
├── Build/                   — build version rotation (managed by build.py)
├── Compliance/              — header and docstring compliance reports
├── Design/                  — design briefs and specifications
├── Nodes/                   — per-node-type feature writeups
├── Claude Plans/            — archived implementation plans (see below)
└── data/                    — session persistence (not shown in menu)
```

Three strict layers — each never crosses into another's domain:

**`data/`** — Pure Python dataclasses, no Qt imports. Each node type has a `NodeData` subclass with `to_dict()` / `from_dict()` for session persistence.

**`nodes/` + `graphics/`** — Qt rendering. `BaseNode(QGraphicsRectItem)` is the base for all nodes; subclasses override `paint_content(painter)` for type-specific rendering. `IntricateScene` manages the canvas; `IntricateView` handles pan/zoom/drag-drop.

**`main.py` + `main_window.py`** — Application shell. `main.py` bootstraps logger → Qt app → settings watcher → Theme → window. `IntricateApp` is a frameless QMainWindow with a left sidebar, center canvas, and reserved right zone.

### Key Design Patterns

**Settings as single source of truth.** All visual values flow from `settings.toml` → `utils/settings.py` → `graphics/Theme` → nodes and widgets. Nothing is hardcoded in UI code.

**Live theme reload.** `QFileSystemWatcher` in `utils/settings.py` monitors `settings.toml`. Any external write triggers `Theme.reload()` → repaint. A companion app ("The Settlers") writes to this file; Intricate only reads it at runtime (it never programmatically writes back to the TOML). The TOML file is the entire handshake between apps. Note: this is a runtime contract between the apps — freely edit `settings.toml` when working on the project (adding icons, updating values, etc.).

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

### Progress Bar Gradient

Every progress bar in the app — sidebar joy bar, video playback scrub, volume slider, or any future bar — uses the same 4-stop pink gradient. This is the canonical "progress bar look" and must never vary:

```python
grad.setColorAt(0.0, QColor("#1e1e1e"))   # dark base
grad.setColorAt(0.4, QColor("#5c3e4f"))   # muted rose
grad.setColorAt(0.7, QColor("#a56a85"))   # warm mauve
grad.setColorAt(1.0, QColor("#d87a9e"))   # bright pink
```

Direction follows the fill axis: left-to-right for horizontal bars, bottom-to-top for vertical bars. Background behind the bar is `QColor(Theme.nodeBg).lighter(130)` with 3px border radius.

### Settings Contract

`settings.toml` is the shared file contract with "The Settlers" companion app. At runtime, Intricate reads and watches it while The Settlers writes it — neither imports the other. The watcher triggers `Theme.reload()` and a window repaint on any change. This is a runtime separation only: edit `settings.toml` directly whenever needed during development.

### NodeBehaviour Lifecycle

Every node owns a `NodeBehaviour` instance that drives hover pulse animations and future personality traits. It is **not** part of the Qt scene graph — it holds signal connections that must be explicitly broken before a node is removed, otherwise reference cycles will prevent garbage collection.

When removing a node, `BaseNode._prepare_for_removal()` must be called first. It stops animations and calls `self.behaviour.disconnect_all()`. If you add new signal connections in a node subclass, override `_prepare_for_removal()` and disconnect them there before calling `super()`.

### Adding a New Node Type

1. Create `data/XxxNodeData.py` subclassing `NodeData` — add fields, implement `to_dict()`/`from_dict()`
2. Create `nodes/XxxNode.py` subclassing `BaseNode` — override `paint_content(painter)`
3. If your node adds signal connections, override `_prepare_for_removal()` and disconnect them before `super()`. Every `QTimer.timeout.connect()` and `QVariantAnimation.valueChanged.connect()` must have a matching `.disconnect()` in `_prepare_for_removal()` — `.stop()` alone does not sever the C++ signal reference and will cause a GC leak
4. Add a factory method to `IntricateScene` (e.g., `add_xxx_node(pos)`)
5. Register the `node_type` string in `_KNOWN_TYPES` in `utils/session.py` — the session validator whitelists known types and will silently drop any node whose type is not in this set
6. Wire a sidebar button in `main_window.py`
7. Create an icon (see below) and register it in `[theme.icons]` in `settings.toml`

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

Whenever you add a new button **anywhere** in the app — sidebar, toolbar, node-embedded control, dialog — you **must** also generate a matching `.ico` icon. No button ships without its own icon. There are three icon families, each with its own visual language and pipeline:

#### 1. Sidebar & Toolbar Icons (Pillow line-art) — elegant, passive, corporate

For sidebar buttons, toolbar actions, and menu entries. Minimal cream-on-transparent line drawings inside a circle ring. These are the quiet, professional icons that frame the workspace.

1. Write a standalone Python script following the Pillow recipe above (outer ring + symbol in the centre).
2. Run it to produce both the `.png` and multi-resolution `.ico` in `./icons/`.
3. Register the icon in `[theme.icons]` in `settings.toml`.
4. Reference it via `Theme.iconXxx` in the button code — the metaclass resolves it automatically.

#### 2. Node Function Buttons (emoji-style) — overtly cute, primary actions

For primary node function buttons on the button strip — actions core to what the node *does*. These match the 3D emoji aesthetic so they sit flush with the native emoji buttons (More Glory, depth, tint). Bold, warm, character-driven. Example: the GitHub Desktop octocat on GitNode.

1. **Draft the shape** — use the Pillow recipe to create a clean vector silhouette (outer ring + symbol). This is the structural reference.
2. **Generate the emoji render** — feed the silhouette through an image generator to produce a 3D shaded emoji-style version (warm gradients, soft lighting, subtle depth, matching the native OS emoji look).
3. **Extract and clean** — write a Python script (see `icons/extract_github_icon.py` as reference) that:
   - Crops the icon from the generated image
   - Removes the background via colour-distance masking (`numpy`)
   - Removes any drop shadow underneath (dark pixels in the bottom region)
   - Trims transparent edges, pads to square, resamples to 1024×1024
   - Produces both `.png` and multi-resolution `.ico`
4. Register in `[theme.icons]` in `settings.toml` and reference via `Theme.iconXxx`.

#### 3. Node Utility Buttons (sticker-style) — clear, functional, secondary

For utility and housekeeping actions on the button strip — things the node *can do* but that aren't its primary identity. Flat sticker aesthetic: bold shape, coloured fill, dark outline, white peel border. Visually distinct from the emoji buttons so the user reads them as tools rather than characters. Example: the push arrow on GitNode.

1. **Draft or source the shape** — create or find a clean icon of the action (arrow, gear, refresh, etc.). A simple flat vector with a sticker border treatment works best.
2. **Generate the sticker render** — feed the shape through an image generator requesting a "sticker" style: flat coloured fill (purple/blue tones fit the palette), dark outline, white cut-out border, no drop shadow.
3. **Extract and clean** — write a Python script (see `icons/extract_push_icon.py` and `icons/extract_trim_audio.py` as references) that:
   - Crops the icon from the generated image
   - Removes the background via colour-distance masking and warm-fringe removal
   - Uses `scipy.ndimage.label` to keep only the largest connected component (kills stray dots)
   - **Defringes white matte contamination** on semi-transparent edge pixels — this is critical for low-contrast stickers (e.g. grey icon on white background) that will sit on a dark node. Reverse the compositing math: `actual_rgb = (observed_rgb - 255 * (1 - α)) / α`. Without this step, anti-aliased edges carry baked-in white that halos visibly on dark backgrounds. See `extract_trim_audio.py` for the reference implementation.
   - Trims transparent edges, pads to square, resamples to 1024×1024
   - Produces both `.png` and multi-resolution `.ico`
   - **Verify on dark background** — composite the result onto `(45, 52, 54)` (node background colour) and visually check for fringe before shipping.
4. Register in `[theme.icons]` in `settings.toml` and reference via `Theme.iconXxx`.

All three families use `NodeButton` for rendering on the button strip. `NodeButton` in `NodeButton.py` scales icon-based buttons up by 1.28× to compensate for transparent padding and match emoji glyph size. The visual hierarchy reads as: emoji buttons are the stars, sticker buttons are the tools, sidebar icons are the furniture.

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

## Plan Archiving

When you create an implementation plan (the `.md` file generated in `.claude/plans/`), always copy a clean version into `./Documents/Claude Plans/` with a descriptive Title Case name (e.g., `Documents Restructure.md`, `GitNode Offline Guard.md`). This builds a retraceable history of architectural decisions and implementation plans inside the repo, versionable alongside the code they describe. The Info sidebar menu picks these up automatically via the nested context menu system.
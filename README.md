# Intricate

**Version 0.5.0 — The Other Era**

A gentle nodal space where thoughts interlink ideas, transitioning thoughts to things.

Built with PySide6. Frameless, always-on-top, infinite zoomable canvas. Part of the "Single Shared Braincell" family of apps that share live configuration via a common `settings.toml` file.

## Node Types

| Node | Purpose |
|------|---------|
| **WarmNode** | Free-form text with emoji accent |
| **AboutNode** | Sticky note / region highlighter with animated button shelf |
| **ImageNode** | Drag-and-drop images with editable caption and AI vision extraction |
| **VideoNode** | Video playback with spatial audio mixing — volume fades by proximity |
| **ClaudeNode** | Claude API chat node with DAG-networked conversation flow |
| **ClaudeResponseNode** | AI response display with chain linking |
| **TextNode** | Lightweight text block |
| **LogNode** | Scrollable log viewer |
| **TreeNode** | Project folder structure visualizer |
| **InfoNode** | Read-only version and era display |
| **SequenceNode** | Image sequence viewer |
| **BezierNode** | Interactive bezier curve with draggable control handles |
| **HealthNode** | Live system monitor — GC census and OS-level click tracking |
| **PaletteNode** | Color palette display |
| **ValueNode** | Numeric value display |
| **PerfNode** | Performance metrics |

## Canvas

- Cursor-anchored scroll wheel zoom
- Alt+Right-click drag zoom (Photoshop-style, Wacom-friendly)
- Middle-mouse pan
- Drag-and-drop images and videos from Explorer
- Per-session camera position and zoom persistence
- Ambient hover pulse animations via NodeBehaviour personality system
- Spatial audio mixing — node distance on canvas acts as a live mixer

## Architecture

```
📄 main.py                — version, era, entry point
└── 📄 main_window.py     — IntricateApp (frameless QMainWindow)
      ├── 📁 graphics/
      │     ├── 📄 Scene.py        — canvas, node factory, session save/load
      │     ├── 📄 View.py         — pan, zoom, drag-drop, wire snip
      │     ├── 📄 Theme.py        — metaclass theme, live reload from settings.toml
      │     └── 📄 Connection.py   — bezier wires between nodes
      ├── 📁 nodes/
      │     ├── 📄 BaseNode.py     — base class, buttons, resize, depth toggle
      │     ├── 📄 NodeBehaviour.py — hover pulse, bg animation
      │     ├── 📄 NodeButton.py   — icon + emoji button controls
      │     ├── 📄 Port.py         — connection ports
      │     └── 📄 *Node.py        — one per node type
      ├── 📁 data/
      │     ├── 📄 NodeData.py     — base dataclass (no Qt)
      │     └── 📄 *NodeData.py    — one per node type, to_dict/from_dict
      ├── 📁 widgets/
      │     ├── 📄 PrettyButton.py — themed button with hover animation
      │     ├── 📄 PrettyCombo.py  — themed combo box
      │     ├── 📄 PrettySlider.py — themed slider with PNG handle support
      │     ├── 📄 PrettyEdit.py   — inline text editor with selection highlight
      │     ├── 📄 PrettyMenu.py   — styled context menus and text inputs
      │     ├── 📄 PrettyLabel.py  — themed label
      │     └── 📄 NoteEditor.py   — full note editing dialog
      └── 📁 utils/
            ├── 📄 settings.py     — TOML loader + file watcher
            ├── 📄 session.py      — save/load, rotation, checksum, migration
            ├── 📄 audio.py        — UI chime feedback + global mute
            ├── 📄 vision.py       — Claude Vision API worker
            ├── 📄 logger.py       — 3-slot rotating log with TRACE level
            ├── 📄 ColorPicker.py  — curated node tint palette
            ├── 📄 IconPicker.py   — emoji icon bank
            └── 📄 helpers.py      — ensure_dir, clean_pycache, utilities
```

## Running

```bash
python main.py           # Normal launch
python main.py --debug   # DEBUG-level console output
python main.py --trace   # TRACE-level (hyper-verbose)
```

---
*Built by Yours Truly and Various Intelligences — For enjoying*

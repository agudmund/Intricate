# Intricate

**Intricate** is a frameless, always-on-top node-based visual canvas built with PySide6. You place nodes on an infinite zoomable canvas, connect them via ports, and arrange your thoughts spatially rather than linearly. It is part of a "Single Shared Braincell" family of apps that share live configuration via a common `settings.toml` file and a set of environment variables.

Current node types: **WarmNode** (free-form text with emoji accent), **HealthNode** (live system monitor — GC census and OS-level click tracking), **BezierNode** (interactive bezier curve with draggable control handles), **ImageNode** (drag-and-drop or browse images with editable caption), and **AboutNode** (sticky note for labelling groups of nodes).

The canvas supports cursor-anchored zoom, middle-mouse pan, and drag-and-drop of image files directly from Explorer. Nodes have ambient hover pulse animations driven by a separate `NodeBehaviour` personality system. The entire theme — colors, icons, layout — hot-reloads the moment `settings.toml` is saved by any app in the family.

## Architecture

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

---
*It is what it is*

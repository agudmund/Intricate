# Architecture Map

> Forensic reference for any AI or human orienting themselves in this codebase.
> Provide this document first — it saves everyone from re-reading the source tree.
>
> **Last refreshed: 2026-04-18.** For what's changed since, see `Documents/Changelog.md` — append-only log of paradigm-level shifts dated to the day they landed. If this doc and the Changelog disagree, the Changelog is newer.
>
> Living stats (line counts, folder geometry, exact file sizes) deliberately omitted — they drift every day and belong in their own place. This doc carries structure and intent only.

## What This Is

**Intricate** is a frameless, always-on-top node-based visual canvas built with PySide6. Part of the **Single Shared Braincell** app family — a suite of apps that share live configuration, a widget package, a theme system, and a shared frozen runtime.

**Current version:** 0.5.0 — "The Other Era"

## The Family

| Repo | Purpose | Entry Point |
|------|---------|-------------|
| [Intricate](https://github.com/agudmund/Intricate) | Node-based visual canvas | `main.py` |
| [Notepad++ Duplex+ Turbo](https://github.com/agudmund/Notepad-Duplex-Turbo) | Creative writing editor | `main.py` |
| [Pretty Widgets](https://github.com/agudmund/Pretty-Widgets) | Shared package (widgets + Theme + settings + logger) | pip package |

## Shared Infrastructure (pretty-widgets)

Installed via `pip install -e "C:\Users\thisg\Desktop\Pretty Widgets"`. All apps import from `pretty_widgets.*` — no local copies.

```
pretty_widgets/
├── PrettyButton.py      — QPushButton, 4-phase hover animation (dip→hold→burst→settle)
├── PrettyLabel.py       — QLabel, themed, optional click signal
├── PrettyMenu.py        — QMenu + StyledTextEdit/StyledLineEdit (right-click styling,
│                           paste strips HTML to plain text — 2026-04-18)
├── PrettyCombo.py       — QComboBox, Fusion engine, scrollbar styling
├── PrettySlider.py      — QSlider, ghost scrollbar, PNG handle support, handle tinting
├── PrettyCheckbox.py    — Composite label+indicator, group alignment
├── PrettyEdit.py        — QTextEdit in QGraphicsProxyWidget, tight selection highlight
├── PrettyTooltip.py     — Pill-shaped custom tooltip (WA_TransparentForMouseEvents
│                           so it never intercepts clicks)
├── graphics/Theme.py    — Metaclass theme registry, live TOML reload, icon cache
├── utils/settings.py    — TOML loader, QFileSystemWatcher, atomic writes
└── utils/logger.py      — 3-slot rotating log, TRACE level (5), Rust-backed ring buffer
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

## Intricate Architecture

### Three Strict Layers

**`data/`** — Pure Python dataclasses. No Qt. Each node type has a `NodeData` subclass with `to_dict()`/`from_dict()`.

**`nodes/` + `graphics/`** — Qt rendering. `BaseNode(QGraphicsRectItem)` is the base for most node types. `StickerNode` is a sibling root (not a BaseNode subclass) — first-class chromeless alpha-PNG overlay. Subclasses override `paint_content(painter)` only. `IntricateScene` manages the canvas. `IntricateView` handles pan/zoom/drag-drop and emits `viewTransformed` on every transform mutation. `Connection` draws bezier wires with a self-quiescent glide engine. `graphics/Particles.py` drives the particle system behind shake-delete. Shared node infrastructure lives in underscore-prefixed modules (`nodes/_shake_detect.py`, `nodes/_demolition.py`) to distinguish them from node-type files.

**`main.py` + `main_window.py`** — Application shell. Frameless QMainWindow with sidebar, canvas, toolbar.

### Key Load-Bearing Modules

| Module | Role |
|--------|------|
| `main_window.py` | QMainWindow — sidebar, toolbar, node spawn, curtains, joy bucket, split-surface InfoBar, the Meov |
| `graphics/Scene.py` | Canvas — node factory, session save/load, drag-drop, `_clear_all` quiescence, altitude-aware media culling |
| `nodes/BaseNode.py` | Base class — chrome, ports, resize, shelf animation, depth toggle, shake detection, bulk-remove quiescence (delegates teardown to the demolition crew) |
| `nodes/ClaudeNode.py` | Claude CLI integration — JSONL watcher, streaming response |
| `nodes/VideoNode.py` | Video playback with LOD-adaptive ingest, shared media cache, tiny-render pause at aerial zoom |
| `nodes/WarmNode.py` | Main content node — plain-text storage, bidirectional bridge to Notepad |
| `nodes/MergeNode.py` | DAW merge node — stages audio/hold nodes, emits ffmpeg concat |
| `graphics/View.py` | Pan/zoom, cursor-anchored zoom, fog layer, `viewTransformed` signal |
| `graphics/Particles.py` | Particle engine — shake-delete bursts, orbital modes, self-healing tick |
| `graphics/Connection.py` | Bezier wire rendering, glide animation (self-quiescent), endpoint-liveness guards |
| `nodes/_demolition.py` | Declarative teardown crew — manifest-based per-node cleanup |
| `utils/persistence/media_cache.py` | Byte-preserving SHA-256 media cache, shared by Image / Video / Sticker |
| `nodes/_shake_detect.py` | Shared shake-gesture detector used by BaseNode + StickerNode |

### Node Types

Canonical catalogue with per-node detail lives in `Documents/Node Type Schema.md` (30+ node types across 8 sidebar categories). Abbreviated roll call for structural orientation:

| Node | Purpose |
|------|---------|
| WarmNode | Free-form text with emoji, plain-text storage, bidirectional bridge to Notepad |
| AboutNode | Sticky note for labelling groups, depth toggle |
| ClaudeNode | Claude CLI chat — spawns ClaudeResponseNodes |
| ClaudeResponseNode | Multiline sticky capturing a full Claude reply |
| ImageNode | Drag-and-drop images, editable caption, LOD-aware paint, byte-preserving media cache, passive drift detection |
| VideoNode | Video playback, LOD-adaptive frame ingest, three-tier restore from source/cache/placeholder, tiny-render pause |
| AudioNode | Audio playback controls; viewport + altitude cull with 1 s crossfade drives the spatial DAW |
| MergeNode | DAW merge — wired audio/hold nodes compose an ffmpeg concat pipeline |
| AudioHoldNode | Scrubbable silence placeholder — `anullsrc` in MergeNode's output |
| BloomNode | Particle-aim node, targets a NullNode anchor |
| TextNode | Always-editable multiline text |
| BezierNode | Interactive bezier curve with draggable handles |
| HealthNode | Live system monitor — GC census; OS click tracking opt-in via `[intricate.health] click_monitor` |
| PerfNode | Performance metrics display |
| LogNode | Live tail of intricate.log |
| TreeNode | Project folder structure walker |
| GitNode | Git status dashboard for Desktop repos |
| PaletteNode | Hex color swatch board |
| SequenceNode | Image sequence player with scrubber |
| ValueNode | Transparent image sequence with PrettySlider |
| **StickerNode** | **Chromeless alpha-PNG overlay — first-class root type (not a BaseNode subclass). Alpha-channel click-through preserved as a feature; viewport-pinnable via right-click context menu. Media-cached same as ImageNode. Reference implementation for future raw-sibling node types.** |
| InfoNode | Information display |
| ClaudeInfoNode | Claude-specific info panel |
| **PremiereBridgeNode** | **Live wire to Adobe Premiere Pro 2026 via CEP WebSocket — handshake + heartbeat + packet injection. See `Documents/Nodes/The Premiere Bridge Node.md`.** |

### Design Patterns

- **Settings as single source of truth.** All visual values: `settings.toml` → `settings.py` → `Theme` → nodes/widgets.
- **Live theme reload.** QFileSystemWatcher on settings.toml → `Theme.reload()` → repaint.
- **Theme metaclass fallback.** Missing `Theme.iconXxx` → circle sentinel, never crashes.
- **Node rendering via override.** Subclasses override only `paint_content(painter)`.
- **NodeBehaviour as detached personality.** Hover pulse animations via signal connections. Must `disconnect_all()` before removal — now handled uniformly by the demolition crew.
- **Deferred imports in `graphics/`.** Scene imports nodes inside factory methods. View imports Theme at bottom. Prevents circular imports — intentional, not an oversight.
- **Absolute-positioned toolbar.** Title at `Theme.toolbarTitleX`, curtains at `Theme.toolbarCurtainsX`, exit/max/tray flush right.
- **Demolition crew — separate profession from construction.** `nodes/_demolition.py` owns the teardown procedure. Nodes declare what they own via class-level manifest attributes (`_demolition_proxies`, `_demolition_timers`, `_demolition_animations`, `_demolition_thread_flag`, `_demolition_media_players`, `_demolition_workers`) and optional `_demolition_pre`/`_demolition_post` hooks for bespoke ordering. The crew walks the MRO so subclass declarations extend parent ones automatically. `BaseNode._prepare_for_removal` is a one-line delegate to `demolish(self)`. `StickerNode.itemChange` calls the crew directly as a non-BaseNode root. Replaced ~494 lines of per-node teardown boilerplate with ~30 lines of declarations and a standalone 347-line crew. Same 5-phase procedure + canonical proxy-widget recipe (setWidget(None) → widget setParent + deleteLater → scene.removeItem → null) happens in one place for every node type. See `Documents/Compliance/Node Cleanup Compliance.md` 2026-04-18 entries.
- **First-class chromeless root — StickerNode.** `StickerNode` inherits directly from `QGraphicsRectItem`, not `BaseNode`. Reference implementation for a raw-image-style root without the BaseNode chrome/pulse/button apparatus. Composes `ShakeDetector` (from `_shake_detect.py`) for the signature shake-to-delete gesture. Alpha-channel click-through is a preserved feature — `paint()` never fills the rect, so transparent pixels remain interactable with whatever sits behind. ValueNode is the natural next migration to this root.
- **Byte-preserving media cache.** `utils/persistence/media_cache.py` is a SHA-256 content-addressed cache shared by ImageNode, VideoNode, and StickerNode. Keys are `<hash>.<ext>` (format preserved). Cheap fingerprint (size + mtime) on restore, full rehash only on mismatch — surfaces drift via AboutNode, never auto-heals. Live keys from all cached node types contribute to `gc_cache` on every session save. Framework doc at `Documents/Design/Media Cache.md`; per-node integration at `Documents/Nodes/The Image Node.md`, `The Video Node.md`, `The Stickers Node.md`.
- **HTML-free paste pipeline.** `pretty_widgets.PrettyMenu.StyledTextEdit` overrides `insertFromMimeData` to strip HTML from clipboard and insert plain text only. WarmNode stores `body_text` as `toPlainText()` (was `toHtml()`), and the legacy-HTML load path round-trips through a scratch `QTextDocument` to migrate pre-2026-04-18 sessions. Prevents per-character-span paint cost on ambient editors.
- **Sensory-with-altitude — zoom-gated decoders and animations.** The canvas's sensory density scales with zoom as altitude in a cityscape. At helicopter zoom (< ~0.15 — 60px on-screen for a 400px node), media decoders rest and pulse animations silence; at eye level and sidewalk zoom everything plays full-fat. Implementation landmarks: `Scene._MEDIA_TINY_RENDER_PX = 60` gates `update_video_visibility` for both VideoNode and AudioNode (video freezes on last frame, audio fades to silence via existing `_fade_volume`); `NodeBehaviour._should_pulse()` gates hover pulse + bg animations at the same 60 px on-screen threshold (_PULSE_MIN_ON_SCREEN_PX). The pulse commitment is explicit: the "gust of wind through grass" cursor-sweep effect is signature, worth the perf cost at normal zoom, and only silenced where the scale delta would be sub-pixel. Benchmark at `logs/bench_pulse_animations.py`.
- **viewTransformed signal on IntricateView.** Overrides `scale()` and `translate()` to emit `viewTransformed` after super — single source of truth for any transform mutation (pan, wheel zoom, alt-drag zoom, programmatic). Pinned StickerNodes subscribe to remap their scene position to the recorded viewport coordinates. No polling, no per-paint work. Benchmark at `logs/bench_view_transformed.py`.
- **Three notification channels, deliberately distinct.** AboutNode (spatial, silent, margin notes), ClaudeResponseNode (peripheral, ambient, agent status), InfoBar (attention-catching with typewriter + fade + sparkle, system events). Do not unify — the distinctness is the feature. Whole app operates at "whisper volume."
- **Split-surface InfoBar.** One logical channel, two stages: the bottom-bar strip and a titlebar mirror. `main_window._active_info_surface()` picks the stage at show-time based on curtains state + splitter position; the full typewriter + fade personality travels with the routing. Titlebar font scales proportionally with `Theme.handleHeightTop` via a 9:25 ratio.
- **Bulk-remove quiescence + ghost-net.** `scene._bulk_removing` is a counter that peer timers/animations check before scheduling per-frame repaints during a destruction burst. Raised in `BaseNode._shake_delete_group` and `Scene._clear_all`; released two event-loop ticks after the final `removeItem`. `Connection.paint` and `_glide_tick` additionally guard endpoint liveness via `shiboken6.isValid` + `scene() is not None`. On outermost release (counter returning to 0) each bulk-delete path plus the single-node shake-delete path forces a `viewport.update()` across every view — defensive net against paint-scheduler residue under heavy-burst load. See `Documents/Compliance/Node Cleanup Compliance.md`.
- **Spatial DAW — emergent, not coded.** Viewport-cull + altitude-cull (in `Scene.update_video_visibility`) + 1-second audio crossfade (tuned to the user's hand-motion rhythm) make AudioNodes behave as a performable spatial mixer when arranged by distance and navigated by pan/zoom. Do not alter the 1-second fade constant without explicit conversation.
- **Contextual absence, not error banners.** Features are presence-gated at the context level, not error-caught at runtime. Missing context → silent absence. HealthNode's OS click monitor is opt-in via `[intricate.health] click_monitor` in settings.toml — default off, because the WH_MOUSE_LL hook adds systemwide input delay when the Qt main thread is busy.

### Text Bridge (WarmNode ↔ Notepad)

WarmNode writes a `.warm_bridge_{uuid}.json` to `Documents/data/`. Notepad opens with `--bridge <path>`. Both sides use QFileSystemWatcher + debounce timers. `writer` field prevents echo loops. Bridge file deleted on close or node removal.

### Premiere Bridge (PremiereBridgeNode ↔ CEP Panel)

PremiereBridgeNode owns a `WebSocketTransport` in `utils/premiere_transport.py` targeting `ws://127.0.0.1:9914`. A CEP extension at `%APPDATA%\Adobe\CEP\extensions\com.intricate.bridge\` (self-signed, CEP 12 mandatory) runs a Node.js `ws` server inside Premiere Pro 2026 and dispatches to ExtendScript via `csInterface.evalScript`. Frames are `Prop|Val|Track|Clip` — `HELLO`/`READY`/`ERROR` handshake, `PING`/`PONG` heartbeat at 5s, three-strikes silent-wire detection. On mismatch the node spawns a chained AboutNode (same passive-messaging pattern as GitNode's offline guard). Full writeup at `Documents/Nodes/The Premiere Bridge Node.md`; phase history at `Documents/Claude Plans/Premiere Bridge Phase 1.md`.

## Design Documentation

Framework-level designs that outgrew node-specific docs live in `Documents/Design/`:

| Doc | Scope |
|-----|-------|
| `Media Cache.md` | SHA-256 content-addressed byte-preserving cache — primitive shared by Image, Video, Sticker. Four invariants (content-addressed keys, byte-preserving, free dedup, retention-by-reference). API surface, integration recipe for new cached node types. |
| `Settlers Category Design Brief.md` | Visual language + four-column grid spec for the Settlers companion app's settings categories. |

Per-node implementation writeups live in `Documents/Nodes/`. Compliance logs (crash classes, fixes, audits) live in `Documents/Compliance/Node Cleanup Compliance.md`.

## Notepad++ Duplex+ Turbo

Frameless, always-on-top creative writing editor. Main class: `Eddie(QMainWindow)`.

| Module | Role |
|--------|------|
| `main_window.py` | Eddie — editor, chat, preview, toolbar, curtains |
| `main.py` | Bootstrap, `--bridge` arg parsing |
| `utils/chat.py` | Claude chat worker + history persistence |
| `utils/vision.py` | Image-to-text Vision API + DropImageTextEdit |
| `utils/spellchecker.py` | Debounced spell highlighting via Windows COM |

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
- Infrastructure helpers prefixed `_` in `nodes/` (e.g., `_demolition.py`, `_shake_detect.py`) to mark them as non-node-type modules.
- TOML sections: `[intricate]`, `[notepadplusplusduplexplusturbo]`, `[theme.colors]`, `[theme.icons]`

## Linguistic Conventions

- Use **vaporize** instead of the literal `/close` trigger word in conversation.
- The app title is a poetry reference: *"Our love, as Intricate as the patterns we impose"*.
- Eddie's README manifesto: *"The last of the Notepads wanted to become all that it could become so it drew itself into existence"* — canonical instance of the project's **"The Last Of" header voice** (see `Documents/Compliance/Python Header Compliance Guide.md`; Line 2 of every Python file carries this voice: triumphant-emergent, detached contextual awareness, goo-ball-rising).
- Every Python file's header Line 2 terminates with **"For enjoying"** — the project's permanent EULA clause. Don't remove.
- `Connection.py`'s Line 2 must always contain **"and they learnt to whisper to each other"** — origin phrase from a post-it note that seeded the entire wire-connection concept.
- Project was originally called **Nodal**; the header subtitle "nodal playground" is pre-rename legacy. Current Line 1 format: `-Intricate - [filename] [utility]`.
- Version eras are **non-linear by design** — gaps between numbers (e.g. 0.4.0 skipped between 0.3.0 and 0.5.0) are intentional and authored, not mistakes. Use exactly what the user provides when bumping.

# The Log Node

A live tail of the current session log file, rendered as a read-only text panel with a detached sticker slider on its right edge. Open one on the canvas and you can watch `intricate.log` stream in alongside the work that's producing it — no terminal, no editor, no context switch. The node never persists content; every refresh reads directly from disk so what you see on the canvas is the same bytes the Rust-backed logger is writing.

LogNode is a standard `BaseNode` descendant — chrome, button strip, ports, resize grip, depth toggle. The detail that makes it useful is everything below the button zone: a `PrettyEdit` in a `QGraphicsProxyWidget` shows the tail, and a vertical `PrettySlider` on its right edge replaces the native Qt scrollbar with the same sticker handle the sidebar uses for the blur and zoom dials. The two are bidirectionally wired, so dragging the slider scrolls the text and scrolling the text moves the slider.

## Core Files

| File | Purpose |
|---|---|
| `nodes/LogNode.py` | The node — editor + slider construction, watcher + poll timer, scroll-preservation logic |
| `data/LogNodeData.py` | Pure Python dataclass — geometry, title, depth-front toggle |

## How It Works

### Two Ways to Create

1. **Sidebar button** — click the log icon in the left sidebar; `Scene.add_log_node(pos)` spawns a 440 × 320 node at the canvas centre, the editor mounts, the watcher and poll timer start, and an initial `_refresh` pulls whatever the log file holds at that moment.
2. **Session restore** — `LogNodeData.from_dict` rebuilds the geometry, `LogNode(__init__)` rewires watcher + poll timer + editor + slider from scratch. Content is never restored from the session — only the size, position, and depth state.

### Log Path Resolution

The node finds the file the same way the logger does, by reaching into `shared_braincell.logger._resolve_log_dir`. That function honours `[shared] log_dir` in `settings.toml` and falls back to `Documents/Data/Logs/` if the key is unset. From that directory the node picks the most recently modified `intricate_*.log` by mtime:

```python
candidates = sorted(logs_dir.glob("intricate_*.log"), key=lambda p: p.stat().st_mtime)
return candidates[-1] if candidates else logs_dir / "intricate.log"
```

The glob covers both the current Rust-backed format (`intricate_YYYYMMDD-HH.MM.SS.log`) and the legacy stdlib format (`intricate_YYYY-MM-DD_HHMMSS.log`), so a LogNode opened in a long-lived session can tail across a logger upgrade without code changes. See `Documents/Design/Rust-Backed Logger.md` for the writer side of this contract.

### The Tail Engine — Watcher + Poll Timer

Two redundant triggers drive `_refresh`:

- **`QFileSystemWatcher`** on the resolved log path — fires `fileChanged` on every write the OS observes. This is the low-latency signal: a log line landing on disk produces a refresh within milliseconds.
- **1.5 s poll timer** — backs the watcher up. `QFileSystemWatcher` is notoriously lossy on Windows during rotation; the file gets unlinked + recreated and the watcher's entry quietly drops. The poll guards against that — every 1.5 s `_refresh` checks whether `self._log_path` is still in `self._watcher.files()` and re-adds it if it's not.

Both triggers funnel into the same `_refresh` method. Whichever fires first wins; the other is a no-op because content equality short-circuits before any work.

### 400-Line Cap

`_MAX_LINES = 400` is the soft cap on what the editor displays. `_refresh` reads the full file, splits into lines, joins the last 400 back together, and feeds that to the editor. The cap exists so a long-running session whose log file grows past a few MB doesn't pay the cost of laying out the whole document on every tick — 400 lines is enough to read context around a recent event, and anyone who needs the older content can open the file directly.

Content equality check (`if self._editor.toPlainText() != tail`) is the inner gate. When the file hasn't actually changed between two ticks — same size, same content, watcher just being noisy — the editor is left alone and the user's selection survives.

### Detached Scroll Slider

The editor's native scrollbar is suppressed two ways: `scrollbar=False` to `PrettyEdit` (which sets the policy to `ScrollBarAlwaysOff`) plus an explicit `setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)` belt-and-braces. The scrollbar object lives on — the QTextEdit needs it internally for scroll geometry — only its visual rendering is off.

In its place, a vertical `PrettySlider` lives in a 30 px column to the right of the editor:

```python
self._scroll_slider = pretty_slider(
    Qt.Orientation.Vertical,
    handle_icon="slider_handle_vertical.png",
    handle_size=28,
    range=(0, 100),
    value=0,
    invertedAppearance=True,
)
```

The slider sits in its own `QGraphicsProxyWidget` child of the node, positioned by `_position_editor` alongside the editor proxy. `invertedAppearance=True` flips the value-to-pixel mapping so the handle moves DOWN as the scrollbar value INCREASES — matching the visual convention that scrolled-to-top puts the handle at the top of the rail. `PrettySlider`'s own stylesheet supplies a transparent groove, transparent add/sub-pages, and the PNG sticker handle; the node must NOT call `setStyleSheet` on the slider afterwards or the default Qt blue rail comes back (regression on 2026-05-19).

`handle_size=28` matches the sidebar's blur and zoom sliders so the LogNode reads as a peer of those controls rather than as a competing visual language. Same canonical sticker family, same size, same rail-free aesthetic.

### Bidirectional Bridge

Three signal connections wire the slider and the editor's scrollbar together:

```python
vsb = self._editor.verticalScrollBar()
vsb.rangeChanged.connect(self._scroll_slider.setRange)
vsb.valueChanged.connect(self._scroll_slider.setValue)
self._scroll_slider.valueChanged.connect(vsb.setValue)
```

`rangeChanged` keeps the slider's range in sync with the document's scroll range — when the editor grows from 100 lines to 400, the slider's `(min, max)` follows. `valueChanged` in both directions keeps the handle position aligned with the actual scroll offset. The feedback loop (slider sets scrollbar → scrollbar emits valueChanged → slider's setValue → slider emits valueChanged → scrollbar's setValue …) self-closes because `setValue` is a no-op when the value hasn't changed.

### Scroll Position Preservation

`setPlainText` resets the scrollbar to 0 on every call. Without protection, the slider would jump to the top of the rail on every 1.5 s tick, which made mid-log reading nearly impossible (regression caught on 2026-05-19).

The fix lives in `_refresh`:

```python
sb           = self._editor.verticalScrollBar()
at_bottom    = sb.value() >= sb.maximum() - 4
saved_value  = sb.value()

self._editor.setPlainText(tail)

if at_bottom:
    sb.setValue(sb.maximum())
else:
    sb.setValue(min(saved_value, sb.maximum()))
```

Two cases, both restorative:

- **At-bottom** (within 4 px of the maximum) → follow the tail. New lines arriving at the bottom stay visible. This is the standard "live log viewer" behaviour.
- **Anywhere else** → restore the saved scroll value, clamped to the new maximum. The user's parked reading position survives across refreshes.

The 4 px threshold gives the user a small dead zone at the bottom — you don't have to be pixel-perfect at the maximum for the tail-following to engage.

### Paint Layout

`paint_content` is intentionally empty — the editor proxy covers the whole content area, so there's nothing for the node to paint underneath. Body fill comes from `BaseNode.paint` using `self._bg_color()`, which honours the depth-front toggle:

```python
QColor(Theme.aboutBgColorFront if self.data.depth_front else Theme.aboutBgColor)
```

Alpha is set from `Theme.aboutTransparency` so the canvas backdrop blur breathes through, same family palette as AboutNode and JoyStatsNode. The button strip, depth toggle, emoji shuffler, and ports all come from `BaseNode` unchanged.

## Data Class

`LogNodeData` extends `NodeData` with one node-specific field:

- `node_type: str = "log"`
- `title: str = "intricate.log"`
- `width: float = 440.0`
- `height: float = 320.0`
- `depth_front: bool = False` — front/back depth toggle

Content never persists. The serialised form covers geometry, identity, and depth state only — log file path is re-resolved on every load so a moved log directory or rotated file is picked up automatically.

## Lifecycle

### Creation

`Scene.add_log_node(pos)` → `LogNode(LogNodeData())` → `BaseNode.__init__` (chrome, ports, behaviour) → `_build_editor` (PrettyEdit proxy + sticker slider proxy + bidirectional wire) → `_resolve_log_path` → `QFileSystemWatcher` install → poll timer started → initial `_refresh` populates the editor. The whole sequence completes before the node is visible.

### Session Restore

`LogNodeData.from_dict(d)` → `LogNode(data)` → same `__init__` flow as fresh, but the persisted width/height carry forward instead of the defaults. Watcher and poll timer rebuild from scratch; the first `_refresh` after restore fills the editor with whatever the log file currently holds.

### Removal

Two paths converge on the same demolition crew:

1. **Shake-delete** — shake the node → `_on_shake_triggered` → particle burst → `removeItem` deferred one tick → scene-leave → `itemChange` → `demolish(self)` from `nodes/_demolition.py`
2. **Direct scene-leave** — session switch or vaporize → `itemChange(ItemSceneChange, None)` → `demolish(self)`

`_demolition_pre` runs before the crew's standard phases:

```python
_demolition_proxies = ['_scroll_slider_proxy']
_demolition_timers  = [('_poll_timer', '_refresh')]

def _demolition_pre(self) -> None:
    # File watcher (peer signal — disconnected inline, not via manifest)
    try: self._watcher.fileChanged.disconnect(self._on_file_changed)
    except (RuntimeError, TypeError, AttributeError): pass
    # Slider ↔ scrollbar wiring — severed before the proxy is torn down
    # so a drag landing mid-removal can't dispatch valueChanged onto a
    # dying scrollbar.
    if self._scroll_slider is not None and self._editor is not None:
        for src_sig, dst in (...three connections...):
            try: src_sig.disconnect(dst)
            except (RuntimeError, TypeError, AttributeError): pass
    self._scroll_slider = None
    if self._editor:
        self._editor.teardown()
    self._editor = None
```

The crew then walks `_demolition_proxies` to tear down the slider's `QGraphicsProxyWidget`, walks `_demolition_timers` to stop and disconnect the poll timer, and runs the standard BaseNode phases (heal connections, detach, behaviour sever).

## Technical Notes

- The poll timer is an orphan (`LogNode` is `QGraphicsRectItem`-based, not a `QObject`-derived widget), so `_refresh` carries the canonical orphan-timer guard: `try: self.scene()` raises `RuntimeError` on a dead C++ wrapper, in which case `_timer_slot_alive('_poll_timer')` stops and disconnects the timer before bailing. Same pattern as HealthNode, GitNode, PerfNode, JoyStatsNode.
- The file watcher is disconnected inline in `_demolition_pre` rather than declared as a manifest entry. The crew's manifest categories (`_demolition_proxies`, `_demolition_timers`, `_demolition_animations`, `_demolition_threads`, `_demolition_media`, `_demolition_workers`) don't cover peer signal connections held against a `QFileSystemWatcher`, so the disconnect is a one-line inline call inside the pre-hook.
- Slider signal disconnects also live in `_demolition_pre` rather than the manifest, for the same reason — the three connections (`rangeChanged`, `valueChanged` × 2) are peer signals between the slider widget and the editor's scrollbar, neither of which is the manifest's target. The proxy itself goes through the standard `_demolition_proxies` flow.
- `PrettyEdit.position(rect)` and `QGraphicsProxyWidget.setGeometry(rect)` both take parent-node coordinates, so the editor and slider rects in `_position_editor` are computed against `self.rect()` directly without translation.
- Content equality check (`if self._editor.toPlainText() != tail`) before `setPlainText` is doing real work — it makes the every-1.5s poll cheap when nothing changed, and it preserves the user's text selection across no-op refreshes. Without it, every poll would reset the selection regardless of whether content actually moved.
- `PrettySlider`'s built-in stylesheet provides the transparent groove + PNG handle. Overriding `setStyleSheet` on the slider widget — even with something innocuous like `"background: transparent;"` — clobbers that stylesheet and Qt falls back to the default blue rail. The compositing flags (`WA_TranslucentBackground`, `setAutoFillBackground(False)`) are widget-level rather than stylesheet-level, so those stay.

## Relationship to Other Systems

- **`Documents/Design/Rust-Backed Logger.md`** — the writer side of the file LogNode tails. The logger writes timestamped `intricate_YYYYMMDD-HH.MM.SS.log` files into `[shared] log_dir`; LogNode resolves the same directory and tails the most recent one. The two pieces share no code; the file on disk is the entire contract.
- **`pretty_widgets.PrettySlider`** — the sticker-handle slider widget. LogNode uses the same `handle_icon="slider_handle_vertical.png"` + `handle_size=28` configuration as the sidebar's blur and zoom sliders, so the three controls form a coherent visual family across the app's surfaces.
- **`pretty_widgets.PrettyEdit`** — the themed `QTextEdit` that wraps itself in a `QGraphicsProxyWidget`. LogNode uses the read-only configuration (`read_only=True`, `always_visible=True`) with the native scrollbar suppressed (`scrollbar=False`); the slider provides the only scroll affordance.
- **`The Majestic`** — the editor's right-edge scroll slider and the chat panel's mirrored left-edge slider use the same pattern LogNode adopted. The architectural piece is the bidirectional `rangeChanged` + `valueChanged` wiring against a `ScrollBarAlwaysOff` text view; the visual piece is the canonical sticker handle. LogNode's version is a direct port of that recipe into the canvas-proxy world.

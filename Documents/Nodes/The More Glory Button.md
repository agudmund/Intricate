# The More Glory Button

The EmojiButton system that gives every node a shufflable emoji accent. Named for its tooltip — click it and more glory arrives.

## Core Mechanism

Each node has an EmojiButton in the top-left button strip. It renders a single emoji glyph from the shared pool, shuffles to a random one on click, and shuffles fresh on every session load. The graph never looks the same twice.

The emoji pool lives in `utils/IconPicker.py` — 28 emoji in total, curated for warmth and personality.

## Lifecycle

- **Session load**: Every node starts with an empty emoji. BaseNode's `_build_buttons` detects this and picks a random one from the pool before the button renders.
- **Click**: Left-click shuffles to a new random emoji from the pool. The parent node repaints immediately.
- **Session save**: Emoji is NOT persisted. The `to_dict` chain omits the emoji field entirely. Every session load is a fresh shuffle.
- **Node removal**: `EmojiButton.detach()` nulls the get/set callback references to break parent capture cycles before GC.

## Node-Specific Behavior

### PaletteNode — Always Starts With Heart Eyes
`PaletteNodeData` has a hardcoded default of `😍`. Since the dataclass default is non-empty, the shuffle-on-load guard skips it. The palette always opens with heart eyes, but clicking More Glory shuffles it like any other node.

### GitNode — Mood Indicator
- **Offline push attempt**: Sets emoji to `😒` (unamused face) when the connectivity check fails. A passive-aggressive but accurate status indicator.
- **Successful push**: Shuffles to a random emoji from the pool — celebration mode.

### AboutNode — Custom Shuffle
AboutNode hides the standard EmojiButton (`_show_emoji_btn = False`) and builds its own shuffle mechanism. The emoji lives in `_shuffle_emoji` on the instance, not in `data.emoji`. Double-clicking the top strip reshuffles it.

### JoyStatsNode — No Emoji
Pure read-only debug display. Hides the emoji button entirely.

### AudioNode — Mute Toggle
Uses EmojiButton for a mute indicator: shows `🫢` when muted, `😊` when playing. This is a functional toggle, not a shuffle button.

### ImageNode — Action Buttons
Four EmojiButton instances for specific actions, none of which are the More Glory shuffle:
- `💎` Stamp source file with vision metadata
- `🔍` Read PNG metadata
- `○` Toggle border
- `🔄` Convert to PNG

## Rendering

EmojiButton renders the glyph via `QPainter.drawText` using `Theme.healthFontFamily` at 70% of the button size constant. An `EMOJI_OVERFLOW` padding of 4px prevents glyph clipping at the bottom.

The button respects LOD gating — below 0.25 zoom, it skips rendering entirely so distant nodes stay clean.

## The Emoji Pool

28 carefully chosen emoji that define the personality range of the graph:

`✨ 🤗 😍 📌 💖 🧸 💕 😊 😁 💜 😮 🫤 😘 😒 😉 😎 😋 🥰 😗 🥲 😚 😥 😯 😏 😲 😬 😇 🙂‍↔️`

## Related Systems

- **Depth Toggle Button**: Uses EmojiButton to render `😯` (front layer) or `🫤` (back layer). Not a shuffle — functional toggle.
- **Tint Button**: Always renders `😎`. Triggers the color picker for node tinting.
- **HoverGlow**: Not used by EmojiButton. The emoji button relies on click handling and LOD gating only.

## Technical Notes

- The button is a `QGraphicsObject` child of the node, not part of the paint pipeline. It positions itself via `_position_buttons()` in the button strip.
- `get_emoji` and `set_emoji` are lambda closures capturing `self.data.emoji`. The `detach()` method nulls these before removal to prevent GC reference cycles.
- The shuffle uses `random.choice()` which gives uniform distribution across the 28-emoji pool. No weighting, no history — pure random, every click.

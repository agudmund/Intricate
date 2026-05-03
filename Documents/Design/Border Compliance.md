# Border Compliance

Every container, dialog, node, widget, and bevel in the Single Shared Braincell suite shares one borderline. A thin sepia stroke at `#6b5a47` that frames the entire app's chrome — every surface-edge the user sees is the same hue, the same width, the same breath. The hex value isn't ornamental; it's the signature that ties the whole family to one wardrobe. This document maps where that signature originates, how it propagates, and where it surfaces — so a touch in any one place produces a coherent ripple across the rest.

## The single source

The canonical border colour lives at exactly one place in settings:

```toml
[theme.colors]
primary_border = "#6b5a47"
```

That string is the patch-bay nib for every border the user sees. Change it once, every chrome surface in Intricate, The Majestic, and The Settlers picks up the new value on the next theme reload — including the borders of nodes, popups, dialogs, splitters, comboboxes, pills, tooltips, and the bezier-handle vertices.

The hover state is a slight lift in lightness:

```toml
[node]
border_color          = "#6b5a47"   # base, optional per-app override
border_hover_color    = "#8a7560"   # mouseover
border_selected_color = "#a38f7b"   # active selection
```

All three live in the same hue family — same warmth, stepping up the lightness ramp — so hover and selection register as a *brightening of the same line* rather than a different colour intruding.

## The cascade

`Theme.primaryBorder` (Pretty Widgets) is the runtime singleton every QSS string and every QPen reads from. When `[theme.colors].primary_border` lands in settings, `Theme.reload()` propagates it through a fixed cascade:

```
primary_border
   │
   ├─→ Theme.primaryBorder
   │
   ├─→ Theme.toolbarBorder       (top toolbar / titlebar strip)
   ├─→ Theme.buttonBorder        (PrettyButton rest state)
   ├─→ Theme.buttonBorderHover   (PrettyButton hover state)
   ├─→ Theme.nodeBorder          (BaseNode normal pen)
   ├─→ Theme.comboboxBorder      (PrettyCombo, dropdown popups)
   └─→ Theme.bezierHandleColor   (BezierNode handle vertices)
```

Each cascade target is also exposed as its own Theme attribute so per-surface overrides remain available — but in normal operation every one of them holds the same `primary_border` value, and the entire chrome reads as one continuous line.

The hover and selected siblings have their own paths:

```
[node].border_hover_color    →  Theme.nodeBorderHover    →  BaseNode.hover_pen
[node].border_selected_color →  Theme.nodeBorderSelected →  BaseNode.selected_pen
```

These are *not* part of the `primary_border` cascade. They're independently set in the `[node]` section and only apply to nodes (other chrome surfaces don't have hover/selected variants of the border). This isolation is intentional: the cascade carries the *base* identity; the lighter variants carry the *interaction state* and live one level below.

## The per-node override carve-out

The base `nodeBorder` has a special status — it's the one cascade target that's *also* re-settable from `[node]`. A user wanting to give nodes a slightly different border from the rest of the chrome can write:

```toml
[theme.colors]
primary_border = "#6b5a47"   # everything else

[node]
border_color   = "#7a6a55"   # nodes specifically
```

…and `nodeBorder` honours the `[node].border_color` value while toolbar / buttons / combobox / bezier handles keep `primary_border`. This is the carve-out the user added "just in case" — useful when a future design wants nodes-specifically distinguishable from the surrounding chrome, without breaking the cascade for everything else.

The implementation tracks an `_node_border_explicit` flag during `Theme.reload()`. When `[node].border_color` is set, the flag flips true; the later `[theme.colors]` cascade then *skips* `nodeBorder` while still cascading every other dependent. Without this carve-out the cascade silently overwrote the per-node override (last-write-wins on the class attribute) — a fragility surfaced by the 2026-05-03 audit and fixed in the same pass.

## Where the border surfaces

A traced map of every place the runtime cascade lands:

### Node chrome

`BaseNode.__init__` builds three QPens at construction:

```python
self.normal_pen   = QPen(QColor(Theme.nodeBorder),         Theme.nodeBorderWidth)
self.hover_pen    = QPen(QColor(Theme.nodeBorderHover),    Theme.nodeBorderWidth)
self.selected_pen = QPen(QColor(Theme.nodeBorderSelected),
                         Theme.nodeBorderWidth * Theme.nodeBorderSelectedScale)
```

`BaseNode.paint()` selects between them based on hover / selected state and calls `painter.drawRoundedRect(self.rect(), self.round_radius, self.round_radius)`. Every node type inherits this — WarmNode, AboutNode, ImageNode, AudioNode, VideoNode, GitNode, CodeNode, PaletteNode, TreeNode, ClaudeNode, the Joy / Perf / Health monitors, every one. Their outer borders all flow from `Theme.nodeBorder`.

### Container chrome

QSS `border: 1px solid {Theme.primaryBorder};` interpolation appears in:

| Surface | File |
|---|---|
| Main window outer chrome | `Intricate/main_window.py` (lines 94, 138) |
| InfoBar bottom strip | `Intricate/main_window.py:1854` |
| Project / preview panels | `Intricate/main_window.py:1200` |
| BloomNode dialog | `Intricate/nodes/BloomNode.py:33, 43` |
| ClaudeNode body frame | `Intricate/nodes/ClaudeNode.py:1075` |
| GitNode commit dialog | `Intricate/nodes/GitNode.py:194, 235` |
| PaletteNode swatch panels + add-color button | `Intricate/nodes/PaletteNode.py:240, 318` |
| WarmNode body frame | `Intricate/nodes/WarmNode.py:142` |
| Majestic editor + chat frames | `Majestic/main_window.py:909, 2036` |

### Pretty Widgets (shared family)

Every shared widget that has a border reads from `Theme.primaryBorder`:

- `PrettyCheckbox` — checkbox glyph border
- `PrettyCombo` — closed-state and open-popup borders
- `PrettyMenu` — popup container border
- `PrettyPill` — pill outline + add-input outline
- `PrettyTooltip` — tooltip pill border (uses the painter path, same colour)

### Bezier nodes

`BezierNode` handle vertices and arm strokes read from `Theme.bezierHandleColor` (cascade target) and `Theme.bezierArmColor` (independent, intentionally darker for visual hierarchy).

## The two intentional exceptions

Two surfaces visibly carry a non-`primary_border` line and are *not* compliance violations — they're deliberate content-frame choices documented here so they don't get "fixed" by accident:

1. **`ClaudeNode` inner-input frame** — `border: 1px solid rgba(255, 255, 255, 25);`
   The QTextEdit inside ClaudeNode where the user types their prompt. Translucent white at low alpha, layered over a slightly-darker-than-node-bg input panel for visual separation. The outer ClaudeNode border still uses `Theme.primaryBorder`; this inner border is content-frame chrome, not container chrome.

2. **`MarkdownNode` / `TextNode` rendered tables** — `border: 1px solid #30363d;`
   GitHub-flavoured markdown renders tables with GitHub's actual table border colour inside the QTextDocument HTML. This is *content* styling — the markdown-rendered cells inside the node — not the node chrome. The node's own outer border still reads from `Theme.nodeBorder`.

If a future change wants either of these to follow the canonical sepia, the change is local to those files and explicit. They sit *inside* the chrome, never blurring the chrome's edge.

## How to add new chrome that respects this

When adding a new container, dialog, widget, or any surface with a border:

- **Always interpolate `{Theme.primaryBorder}` in QSS strings**, never a literal hex.
- **Always read `Theme.nodeBorder` / `Theme.nodeBorderHover` / `Theme.nodeBorderSelected` for QPen-rendered node borders**, never literal hex.
- **Don't inline `#6b5a47`** — it appears literally only as the class-default fallback inside `Theme.py`, the icon-loader fallback colour for missing assets, and the default palette accent in `PaletteNodeData`. New code never needs the literal value.
- **For HTML / QTextDocument content rendering** (markdown tables, code blocks, etc.) the border colour can be content-appropriate (GitHub greys, etc.) — the rule is *"chrome reads from Theme, content can choose its own"*.

The full dependency from a new surface back to the source is:

```
your new QSS  →  {Theme.primaryBorder}  ←  Theme.reload()  ←  [theme.colors].primary_border
```

Touch the value once at the source, every dependent line follows.

## Fivefold protection

The single-source design is what gives the chrome its consistency, but it also means a single bad value at the source ripples everywhere. Three protections compound:

1. **Class-level default** — `Theme.primaryBorder = "#6b5a47"` is the literal class attribute. If `Theme.reload()` never runs (early boot, frozen exe edge case, settings.toml missing), the chrome still has a known-good colour.
2. **Per-section try/except** — `Theme.reload()` wraps every settings block in its own `try/except` so a corrupt `[theme.colors]` value can't take down `[node]` or vice versa. Existing values are retained.
3. **`_safe()` value coercion** — every `int` / `float` / `str` parse goes through a typed coercion helper that returns the previous value on a parse failure rather than crashing the reload.

The DMX patch-bay metaphor: individual nibs can show bad values, but the patching itself never goes down.

## See also

- `Documents/Design/Icon Pipeline.md` — the same single-source-with-cascade discipline applied to icons (cream colour `(225, 213, 198, 255)` for line-art family, etc.)
- `Documents/Nodes/The Palette Node.md` — the `Push.png` arrow sticker referenced from `Theme.iconCodeBrowse` and `Theme.iconPush`, same single-source pattern at the icon layer
- `Pretty Widgets/src/pretty_widgets/graphics/Theme.py` — the runtime cascade implementation
- The 2026-05-03 audit that produced this doc — every QSS border across the suite traced and confirmed compliant; one fragility found in the cascade order and fixed in the same pass

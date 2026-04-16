# Unified Spawn Button for MarkdownNode

## Context

ReadmeNode and CushionsNode both have "split into nodes" buttons that use nearly identical spiral collision placement code, but diverge in what they parse and what they spawn. The user wants a unified version on MarkdownNode (the base class for all info/doc nodes) that:

- Parses markdown by **headings** — each heading becomes an **AboutNode** (title), each body section becomes a **WarmNode** (content)
- **Chains all spawned nodes** with Connection wires — heading→body→heading→body etc.
- Uses the best spiral placement algorithm (from ClaudeNode) extracted as a reusable utility

This gives every info node the split capability for free, since they all inherit from MarkdownNode.

## Approach

### 1. Extract spiral placement to `utils/placement.py`

The ClaudeNode spiral algorithm is the gold standard — viewport-center origin, 16 probes per ring, adaptive step sizing, graceful chain-tail fallback. Extract it as a standalone utility class so it can evolve independently.

**File:** `utils/placement.py`

```python
def spiral_place(scene, node, origin: QPointF, max_radius: int = 4000,
                 padding: float = 28.0, probes: int = 16,
                 fallback: QPointF | None = None) -> QPointF
```

- Viewport-center origin when view exists, configurable fallback
- `_clear()` collision check against BaseNode instances with padded bounding rect
- Ring step = `max(node_w, node_h) // 2`
- Max radius = `2.5× viewport diagonal` when view available, else `max_radius` param
- Fallback: caller-provided point, or origin if canvas is fully packed

### 2. Add `_split_into_nodes()` to `nodes/MarkdownNode.py`

The split method takes a **pattern parameter** — not hardcoded to markdown headings. The caller decides what constitutes a "title" line vs "body" text. This time we pass `r'^#{1,6}\s+'` for markdown headings, but the same mechanism will work for any delimiter pattern in future uses.

**Signature:**
```python
def _split_into_nodes(self, title_pattern: str = r'^#{1,6}\s+') -> None
```

**Logic (pattern-agnostic):**
- Walk lines of `self.data.label`
- Any line matching `title_pattern` → **AboutNode** (title/label node)
- Consecutive non-matching lines accumulated → **WarmNode** (content body)
- Preamble text before first match → WarmNode with no preceding AboutNode
- Empty body (two title lines back-to-back) → AboutNode only, skip WarmNode
- **All nodes chained** with `Connection(prev_node, node)` — full sequence stays linked

The button on MarkdownNode calls `self._split_into_nodes()` with the default markdown heading pattern. Subclasses or future callers can pass a different pattern.

**Auto-sizing:** WarmNode's own `_auto_fit_height()` handles sizing — it uses `BODY_TOP + doc_h + PADDING + 16.0` which accounts for emoji/title chrome. We rely on that after construction.

### 3. Wire the button in `MarkdownNode._build_buttons()`

- Use `iconSpawnNodesClean` (the purple chain icon, `icons/spawn_nodes_clean.png`)
- Since it's on the base class, all MarkdownNode subclasses inherit it
- ReadmeNode keeps its existing button for now (it spawns AboutNodes only, different intent)

## Files to Modify

| File | Change |
|------|--------|
| `utils/placement.py` | **New file** — `spiral_place()` extracted from ClaudeNode's algorithm |
| `nodes/MarkdownNode.py` | Add `_split_into_nodes()` + spawn button in `_build_buttons()` |

## Existing Code to Reuse

- **Spiral algorithm** — ClaudeNode `_spawn_single_response()` lines 562-630 (the gold standard)
- **Connection wiring** — `Connection(prev_node, node)` + `scene.addItem(conn)`
- **WarmNode construction** — `WarmNode(WarmNodeData(body_text=..., title=""))` then `_auto_fit_height()`
- **AboutNode creation** — `scene.add_about_node(pos, label)` from Scene.py
- **Button pattern** — `NodeButton(self, icon, callback)` appended to `self._buttons`

## Verification

1. Launch `python main.py`
2. Click Info → Nodes → any doc (e.g. "The Stuff and Stuff Node")
3. MarkdownNode spawns, auto-fits to full content height
4. Click the chain spawn button on the node
5. Verify: AboutNodes appear for each heading, WarmNodes for each body section
6. Verify: **all spawned nodes are chained** with Connection wires (heading→body→heading→body)
7. Verify: nodes don't overlap (spiral placement working)
8. Verify: WarmNodes auto-size to fit their text content
9. Close app during/after split — no crash

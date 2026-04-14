# MergeNode — Audio Merge List Node

## Context

New node type that lists connected AudioNodes in sequential order. Standard BaseNode chrome (depth toggle, color picker, emoji). Body displays the filenames/captions of connected audio nodes, updating live as connections are added or removed.

## Files to Create

### 1. `data/MergeNodeData.py`

Minimal dataclass extending NodeData:
- `node_type = "merge"`
- `title = "Merge"`
- `depth_front: bool = False`
- `node_tint: str = ""`
- Standard `to_dict()` / `from_dict()`

### 2. `nodes/MergeNode.py`

- `_has_depth_toggle = True`
- `_show_ports_btn = True` (needs ports to receive connections)
- `paint_content(painter)` — draws title via `super()`, then iterates `self.connections` to find connected AudioNodes and paints their captions/filenames as a numbered list below the title
- Connections are checked by testing `isinstance(node, AudioNode)` on both `conn.start_node` and `conn.end_node` (whichever isn't self)
- List updates on every paint cycle — no caching needed since paint is called on any scene change

### 3. `icons/merge_node.ico` + `.png`

Pillow recipe: outer ring + merge symbol (converging arrows into a center point).

## Files to Modify

### 4. `graphics/Scene.py`

Add `add_merge_node(pos)` factory method following the existing pattern (deferred import inside method).

### 5. `main_window.py`

Wire a sidebar button for MergeNode in the node spawn section.

### 6. `settings.toml`

Register `merge = "merge_node.ico"` in `[theme.icons]`.

## Connected Node Iteration Pattern

```python
def _get_connected_audio_nodes(self):
    from nodes.AudioNode import AudioNode
    audio_nodes = []
    for conn in self.connections:
        other = conn.end_node if conn.start_node is self else conn.start_node
        if other and isinstance(other, AudioNode):
            audio_nodes.append(other)
    return audio_nodes
```

## Verification

1. Create a MergeNode from the sidebar
2. Create 2-3 AudioNodes, load audio files
3. Connect AudioNodes to MergeNode via ports
4. MergeNode displays the audio filenames in order
5. Disconnect one — list updates
6. Session save/load preserves the node

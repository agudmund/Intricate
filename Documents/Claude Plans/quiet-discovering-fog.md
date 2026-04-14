# BloomNode — Particle Scatter Controller

## Context

BloomNode is a new node type that controls particle scatter effects on the canvas. It lets the user choose between scatter algorithms (sunflower/orbital) via a combobox, and picks up which PNG to scatter by reading from a connected ImageNode's pixmap.

## Files to Create

### `data/BloomNodeData.py`
- `node_type = "bloom"`
- `scatter_mode: str = "sprinkle"` — `"sprinkle"` or `"orbital"`
- `particle_count: int = 8000`
- `depth_front: bool = False`
- Standard `to_dict()` / `from_dict()`

### `nodes/BloomNode.py`
- Inherits `BaseNode`, `_has_depth_toggle = True`
- **Combobox** for scatter mode — `QComboBox` in a `QGraphicsProxyWidget`, options: `["Sunflower", "Orbital"]`
- **Buttons**: bloom/fire button that triggers the scatter
- **`_fire_scatter()`**: reads connected node for an icon/pixmap, calls `sprinkle()` or `orbital_burst()` at the node's center
- **`_get_input_image()`**: iterate `self.connections`, find connected ImageNode, extract its icon name or source_path filename
- **`paint_content()`**: render title + scatter mode label
- **`_prepare_for_removal()`**: call `super()`
- Standard serialization

### Connection pattern (from MergeNode):
```python
def _get_input_image(self):
    from nodes.ImageNode import ImageNode
    for conn in self.connections:
        other = conn.end_node if conn.start_node is self else conn.start_node
        if other and isinstance(other, ImageNode):
            return other
    return None
```

## Files to Modify

### `utils/session.py`
- Add `"bloom"` to `_KNOWN_TYPES`

### `graphics/Scene.py`
- Add `add_bloom_node(pos)` factory method

### `main_window.py`
- Add `_spawn_bloom_node()` method
- Add menu entry in the visual/creative menu section

## Verification
1. Create BloomNode from sidebar menu
2. Switch combobox between Sunflower and Orbital
3. Click fire button → particle scatter at node center using default heart.png
4. Connect an ImageNode to BloomNode → fire → scatter uses ImageNode's source image
5. Save session, reload → BloomNode restores with scatter mode preserved
6. Delete BloomNode → no segfault (particle flush test)

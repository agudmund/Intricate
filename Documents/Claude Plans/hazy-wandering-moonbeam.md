# Add Rudimentary FBX Node

## Context
The user has a hand-built FBX loader in `Desktop/Wormhole/c side/` — a C DLL (`fluffandhoney.dll`) that extracts vertices from FBX files via ufbx, with Python ctypes bindings and a PIL-based point cloud renderer. This node is a placeholder/memo — just enough to exist in the menu and load on the canvas, ready for future tinkering.

## Files to Create

### 1. `data/FbxNodeData.py`
- Minimal NodeData subclass, `node_type = "fbx"`
- Field: `fbx_path: str = ""` (path to loaded FBX file, for future use)
- Standard `to_dict()` / `from_dict()`

### 2. `nodes/FbxNode.py`
- Minimal BaseNode subclass with `_has_depth_toggle = True`
- Default size ~280×200
- `paint_content()`: paint a label like "FBX" and the filename stem if loaded, similar to AboutNode's simple text rendering
- No actual FBX loading yet — just the shell
- Standard header compliance

### 3. Icon: `icons/make_fbx_icon.py`
- Pillow recipe: outer ring + "FBX" or a simple 3D cube wireframe silhouette in the centre
- Generate `fbx_node.png` + `fbx_node.ico`

## Files to Modify

### 4. `graphics/Scene.py`
- Add `add_fbx_node(pos)` factory method (deferred import pattern)
- Add `elif node_type == "fbx":` branch in `_restore_node()`

### 5. `main_window.py`
- Add `_spawn_fbx_node()` method
- Add menu entry in `_show_visual_menu()` — fits with the special/creative nodes

### 6. `settings.toml`
- Register icon: `fbx = "fbx_node.ico"` under `[theme.icons]`

## Verification
- Launch with `python main.py --trace`
- Click visual category → see FBX entry in menu
- Spawn an FBX node → appears on canvas with "FBX" label
- Save/reload session → node persists

# Plan: Extract ReadmeNode from TextNode

## Context

ReadmeNode is currently implemented as a TextNode with `render_html=True` and `node_tint="#0d1117"`. The user wants it as an independent module because:
- It's more elaborate than TextNode (markdown rendering, styled HTML viewer)
- Future plans for the input port are incompatible with the TextNode base
- Clean modular architecture — each node type is its own file

## Approach

**ReadmeNode subclasses BaseNode directly** (not TextNode), giving it full independence for future divergence. The markdown rendering pipeline and HTML viewer are moved into ReadmeNode. TextNode keeps its `render_html` path for backward compatibility with existing sessions.

## Files to Create

### `data/ReadmeNodeData.py`
- Subclass `NodeData`
- Fields: `node_type="readme"`, `title="Readme"`, `label=""` (markdown content), `width=400`, `height=320`
- Defaults to the dark GitHub tint and always renders HTML — no `render_html` flag needed
- `to_dict()` / `from_dict()` as standard

### `nodes/ReadmeNode.py`
- Subclass `BaseNode` directly
- `__init__`: dark background (`#0d1117`), builds HTML viewer
- `_build_html_viewer()`: read-only QTextEdit with dark theme stylesheet, from TextNode lines 74-97
- `_markdown_to_html()`: static method, from TextNode lines 115-320 (the full markdown+CSS pipeline)
- `_position_editor()`: from TextNode lines 325-336
- `_build_buttons()`: split button (from TextNode) — keep for now, can diverge later
- `paint_content()`: pass — editor handles display
- `setRect()`: repositions editor
- `_prepare_for_removal()`: cleans up `_html_proxy`, calls super
- `sync_data()` / `to_dict()` / `from_dict()`: standard serialization
- Header compliance per CLAUDE.md

## Files to Modify

### `utils/session.py` (~line 150)
- Add `"readme"` to `_KNOWN_TYPES` frozenset

### `graphics/Scene.py`
- Add `add_readme_node(pos, label)` factory method (after existing `add_text_node`)
- Add `elif node_type == "readme":` case in `_restore_node()` deserialization chain

### `main_window.py`
- Change `_spawn_readme_node()` to call `self.scene.add_readme_node()` instead of `self.scene.add_text_node(render_html=True)`

### `nodes/TextNode.py`
- No changes — keep `render_html` path for backward compat with existing "text" type sessions

## Registration Checklist
1. `data/ReadmeNodeData.py` — new dataclass
2. `nodes/ReadmeNode.py` — new node class
3. `_KNOWN_TYPES` in `utils/session.py` — add "readme"
4. `Scene._restore_node()` — add deserialization case
5. `Scene.add_readme_node()` — factory method
6. `main_window._spawn_readme_node()` — redirect to new factory
7. Icon: reuse existing `Theme.iconTree` (already used for the readme menu item)

## Verification
- Launch app, open Lectures on Faith session — existing text nodes with `render_html=True` still work as TextNode
- Spawn a new Readme from sidebar menu — creates a ReadmeNode with `node_type="readme"`
- Save session, reload — ReadmeNode persists and restores correctly
- Shake-delete a ReadmeNode — clean removal, no leaks

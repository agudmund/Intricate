# Plan: Design brief + dynamic info menu

## Task 1: Write the Settlers Category Design Brief

Create `Documents/Settlers Category Design Brief.md` describing the visual language for settings categories in The Settlers, based on the dock_offsets lookdev and the about node clone.

Covers:
- Page structure (transparent QScrollArea, 20/16px margins, 1px spacing)
- Slider row pattern (pretty_label 140px + pink val_label 36px + PrettySlider + hidden QLineEdit)
- Color swatch pattern (Chandler42 font, 110x70 swatch, hex input, bidirectional sync)
- Section descriptions (pretty_label 9pt, 55% opacity, below fields)
- Theme dependency (all colors from Theme, no hardcoded values except pink `#ffb6c1` value readout)

## Task 2: Dynamic info menu from Documents/ folder

**Problem:** The info category sidebar menu has 5 hardcoded entries (info, readme, architecture, node_schema, registry). Adding/removing documents requires code changes.

**Approach:** Keep the existing hardcoded entries (info, readme, registry — these have special behavior). After them, add a separator and dynamically list every `.md` file in `Documents/` that doesn't already have a dedicated node. Each dynamic entry spawns a `ReadmeNode` pre-filled with the file contents — no new node types needed.

### Files to modify

**`main_window.py`** — `_show_category_menu` or `_show_info_menu`:
- After the registry-driven menu items, add a separator
- Scan `Documents/` for `.md` files
- Skip files that already have dedicated handlers (Architecture.md, Node Type Schema.md)
- For each remaining .md, add a menu action that loads the file and spawns a `MarkdownNode` (the base class for all doc nodes) pre-filled with the content

### Implementation detail

Build the menu manually in `_show_info_menu` — first the registry-driven entries (same pattern as `_show_category_menu`), then a separator, then dynamic .md entries. Each dynamic entry spawns a `MarkdownNode` (from `nodes/MarkdownNode.py` + `data/MarkdownNodeData.py`) with the file content loaded into `data.label`. Need a `scene.add_markdown_node(label=...)` factory method to match the existing pattern.

### Verification
1. Add/remove a .md file in Documents/ and restart Intricate
2. Confirm the info menu updates to reflect the folder contents
3. Click a dynamic entry — confirm a ReadmeNode spawns with the file's content
4. Confirm existing entries (Intricate, The Readme, Architecture, Node Schema, The Registry) still work

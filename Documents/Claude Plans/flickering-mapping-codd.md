# Align The Settlers Layout with Intricate

## Context
The Settlers currently has a flat 3-row grid (toolbar, center, bottom toolbar) with no sidebars. Intricate uses a nested splitter hierarchy that gives it collapsible left/right sidebars, a resizable bottom toolbar, and the beveled canvas in the center. We're aligning The Settlers to match this structure so all apps in the family share the same layout skeleton — even if sidebars start empty.

## File
`C:/Users/thisg/Desktop/The Settlers/main_window.py`

## Reference: Intricate's Layout Hierarchy
```
Grid Row 0: top_toolbar (fixed height)
Grid Row 1: _sidebar_splitter (stretches)
  ├─ [0] sidebar (left, fixed width, collapsible)
  └─ [1] _v_splitter (vertical)
       ├─ [0] splitter (horizontal)
       │    ├─ [0] central content (stretches)
       │    └─ [1] rightPanel (collapsible, starts collapsed)
       └─ [1] bottomToolbar (collapsible via splitter)
```

## Changes

### 1. Replace the grid center + bottom with nested splitters
Currently: grid row 1 = BeveledWidget, grid row 2 = bottom toolbar.
New: grid row 1 = `_sidebar_splitter`, grid row 2 removed.

- **`_sidebar_splitter`** (QSplitter, Horizontal) — left sidebar + everything else
  - `[0]` Left sidebar (empty QWidget, fixed width matching `Theme.sidebarWidth()`, collapsible)
  - `[1]` `_v_splitter` (QSplitter, Vertical) — center+right above, bottom below
    - `[0]` `_center_splitter` (QSplitter, Horizontal) — center + right panel
      - `[0]` BeveledWidget with the QStackedWidget inside (stretch=1)
      - `[1]` Right panel (empty QFrame, collapsible, starts collapsed)
    - `[1]` Bottom toolbar (the existing save/eXid bar, collapsible)

### 2. Build methods to add
- `_setupCentralArea()` — creates the 3 nested splitters, places BeveledWidget + stacked pages inside center, empty placeholders for sidebars
- Refactor `_build_bottom_toolbar()` — remove `grid.addWidget` at the end, return the widget instead so it can be added to `_v_splitter`

### 3. Splitter styling
Match Intricate's pattern:
- Handle width: 4px
- Handle styled with `Theme.windowBg`
- Cursor: ArrowCursor on horizontal handles, SplitVCursor on vertical
- Left sidebar: collapsible=True, stretch=0
- Right panel: collapsible=True, stretch=0, starts at 0 width
- Center: collapsible=False, stretch=1
- Bottom toolbar: collapsible=True, stretch=0

### 4. Curtain animation update
Currently hides/shows `self.central` and `self.bottomToolbar`. Change to hide/show `self._sidebar_splitter` (which contains everything).

### 5. Keep everything else the same
- Top toolbar: unchanged (grid row 0)
- Stacked pages + combobox navigation: unchanged, just reparented inside the BeveledWidget within the center splitter
- Save/hot-reload/field logic: untouched
- Window geometry persistence: untouched
- BeveledWidget class: unchanged, just used in the new splitter position

## Verification
- Launch The Settlers — central area should have the beveled border visible
- Left/right sidebars empty but splitter handles visible if you drag
- Bottom toolbar (save/eXid) should be resizable via vertical splitter
- Curtains animation should still work
- ComboBox page switching should still work
- Window geometry + active tab persistence should still work

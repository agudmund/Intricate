# Tag Chips for Tree Node Exclude Lists

## Context

The Tree Node's exclude fields (`exclude_dirs`, `exclude_exts`, `exclude_files`) store Python list strings like `"['__pycache__', 'node_modules']"` in settings.toml. Currently rendered as raw QLineEdit text fields in The Settlers — ugly and error-prone. Need tag-style removable chips like email recipients.

## Design

### Where it lives

Inline in The Settlers' `_add_field_row` — a new specialized path for `node.tree` string list fields. NOT a new Pretty Widget yet — prove the concept first, extract later if it generalizes.

### Visual

Each entry is a pill/chip:
- Theme.windowBg background, Theme.primaryBorder border, pill-shaped (half-height radius)
- Entry text in Chandler42 italic
- Small "×" on the right edge to remove
- Click × → chip disappears, backing field updates
- A small "+" button or text input at the end to add new entries

### Data flow

1. Parse: `ast.literal_eval(field.text())` → Python list
2. Render: one chip per entry in a `QFlowLayout`-style wrapping container
3. On remove: filter the list, serialize back to `str(list)`, call `field.setText()`
4. On add: append to list, serialize, `field.setText()`
5. The hidden QLineEdit backing field holds the canonical string — same save path as everything else

### Implementation in `_add_field_row`

New condition before the generic else:
```python
elif section_path == "node.tree" and field_key.startswith("exclude_"):
    # Tag chip rendering for exclude lists
```

### Chip widget

A small `QFrame` with horizontal layout: `QLabel(text)` + `QPushButton("×")`. Styled with pill border-radius, themed colors. Click × removes the chip and updates the backing field.

### Add mechanism

Small `QLineEdit` at the end of the chip flow — type a name, press Enter, chip appears. The input clears and stays ready for the next entry.

## Files Modified

- `The Settlers/main_window.py` — new path in `_add_field_row` for exclude list fields

## Verification

1. Open The Settlers → The Tree Node category
2. See chips for each exclude entry (folders, extensions, files)
3. Click × on a chip → it disappears, setting updates
4. Type a new entry → press Enter → chip appears
5. Close and reopen → chips persist from the updated toml value

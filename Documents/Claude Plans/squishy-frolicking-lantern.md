# Dynamic Radial Shadow on Sticker Buttons

## Context

Sticker-style buttons currently have baked-in drop shadows. The user wants shadows to radiate outward from the canvas view centre — creating a fake 3D lighting effect where a single overhead light sits at screen centre. On press, the button shifts toward centre (into the surface), removing the shadow. This gives physical depth without a 3D engine.

## Approach

**Single light source at view centre.** For each sticker button, compute the vector from view centre to the button's screen position. The shadow offset is along that vector (outward). On press, shift the icon in the opposite direction (inward, toward the light).

**Two targets:**
1. **NodeButton** (canvas sticker buttons) — modify `paint()` in `NodeButton.py`
2. **Feed button** (sidebar QPushButton) — custom `paintEvent` override

Both use the same math: direction vector → shadow offset → painter compositing.

## Implementation

### 1. Shadow-clean sticker assets

Strip the baked shadow from `catnip_sticker_1024.png` — produce a clean version with NO shadow. The shadow will be rendered dynamically at paint time. Keep the pressed variant as-is (it's just the clean icon shifted).

### 2. `NodeButton.py` — dynamic shadow in `paint()`

In the `paint()` method (line 89), before drawing the icon pixmap:

```
1. Get view centre in scene coords
2. Get button centre in scene coords  
3. Compute direction = button_centre - view_centre, normalize
4. Shadow offset = direction * SHADOW_DISTANCE (e.g. 3-4px at current LOD)
5. Paint shadow: draw the pixmap at offset position with reduced opacity (0.4)
6. Paint icon: draw the pixmap at normal position
```

Only apply to sticker-style buttons (add a `_has_shadow = False` class flag, set True on sticker buttons).

### 3. Feed button — override `paintEvent`

Replace the QPushButton with a small subclass that overrides `paintEvent`:
- Compute direction from button's global centre to window centre
- Draw the icon pixmap with shadow offset (outward from centre)
- On press state: draw at offset position (toward centre), no shadow

### 4. Press behaviour

- **Normal state**: icon at base position, shadow drawn offset outward from centre
- **Pressed state**: icon shifts toward centre by the shadow distance, no shadow drawn
- This creates the illusion of the button being pushed into the surface

## Files to modify

- `icons/process_catnip_sticker.py` — generate a shadow-free clean sticker
- `nodes/NodeButton.py` — add dynamic shadow to `paint()` for sticker buttons
- `main_window.py` — custom paintEvent on feed button

## Verification

1. Feed button shadow points away from screen centre (bottom-left area → shadow toward bottom-left)
2. Press feed button → icon shifts toward centre, shadow disappears
3. Release → snaps back with shadow
4. Resize window → shadow direction updates
5. Node sticker buttons on canvas → shadow direction changes with pan/zoom

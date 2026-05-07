# Polaroids

A polaroid is a one-click freeze-frame of the canvas — the visible viewport rendered to a transparent PNG, dropped into the family-wide images folder, and announced via the infobar. Click the message to open Explorer with the file pre-selected. The feature is meant to be invoked while looking at something worth keeping: a finished arrangement, a chain that's about to change, a zoom altitude that says everything. Output is the deliverable; the running canvas keeps moving.

## Trigger

Right-click the top toolbar → **Polaroid Snapshot** in the context menu (`main_window.py:945-948`). Wired to `IntricateApp._snapshot_viewport`, which delegates to `utils.helpers.snapshot_viewport(view, session_name=…)`.

The trigger lives in the titlebar context menu rather than the sidebar because polaroids are a punctuation gesture — a moment, not a workflow. The same menu hosts the other titlebar utilities (restore-deleted, snip-wire, project-folder lock, mute) that share the same "occasional but useful" cadence.

## What Gets Captured

The visible viewport — exactly what's on screen at the current pan and zoom, minus the backdrop. The renderer maps the viewport rect into scene coordinates and calls `scene.render()` into a transparent `QImage(Format_ARGB32_Premultiplied)` filled with `0`, so anything outside a node's bounding box arrives as alpha 0. `Theme.backDrop` is never painted into the polaroid, so the resulting PNG composites cleanly onto any surface — slide deck, polaroid wall, paper proof.

Render scale defaults to `2×` for crisp output without hand-tuning per display. Antialiasing is on.

## Filename Convention

```
first attempt   →  {session} {lowest-about-label}.png
on collision    →  {session} {lowest-about-label} 2.png, 3.png, 4.png, …
```

The stem is built from the active session name and the visible AboutNode label closest to the bottom of the viewport. Both segments pass through `_sanitize` (filesystem-unsafe characters stripped, hard-capped at 40 chars). Empty segments are dropped. If both are empty, the fallback stem is `Intricate snapshot`.

Collision-resolution mirrors The Majestic's `_resolve_majestic_save_path` (`The Majestic/main_window.py:132`): counter starts at `2`, no parentheses, plain space separator. Two apps writing to the same images folder produce the same naming shape, so you can sort the folder by name and find the polaroid you took regardless of which app it came from.

The previous convention appended a 14-digit `{stem} - YYYYMMDDHHMMSS.png` timestamp as the uniqueness guarantee, but the file list got harder to scan as the day went on and repeat polaroids of the same view scattered across the timeline. Counter-based collision-resolution keeps related polaroids adjacent in Explorer and lets the user re-snap a view without thinking about file conflicts.

## Lowest-About-Label

`_lowest_about_label(view)` (`utils/helpers.py:164`) walks the scene for AboutNode instances whose bounding rect intersects the viewport, picks the one with the highest `y` (furthest down on screen), and returns its label. AboutNodes are the canvas's sticky-note labels for groups of nodes — they tend to live at the top or bottom of a logical cluster, so the lowest visible label usually names whatever the user is currently looking at.

When no AboutNode is visible, the segment is empty and the stem falls back to `{session}.png` alone.

## Output Folder

Resolved from `[shared] images_dir` in `settings.toml`. Family-wide convention — Intricate's polaroids and The Majestic's polaroids land side by side. Per-app overrides exist (`[intricate] images_dir`, `[themajestic] images_dir`) but are rare; the shared folder is the default.

If the folder doesn't exist, `ensure_dir` creates it. If the save itself fails, the function returns `None` and the calling site silently skips the infobar — quiet absence rather than a noisy banner.

## After-Save Affordance

`_snapshot_viewport` calls `show_info` with a click-to-open-in-Explorer callback (`subprocess.Popen(["explorer", "/select,", str(path)])`). The infobar message reads `Snap saved → {filename}`; clicking it opens Explorer with the new file pre-selected. The polaroid is published; the user decides where it goes from there. The whisper-volume rule applies — the message is informational, not an interrupt.

## Related: `snapshot_node`

`utils/helpers.snapshot_node(node, filename)` is the per-node sibling — captures a single node's bounding rect to a transparent PNG. Currently used by **PaletteNode** for its "export the palette" button (`PaletteNode.py:551`). Filename is the node's title. **No collision-resolution** — repeat exports overwrite the previous file silently. The shared images folder is the same.

This asymmetry is intentional: polaroids and per-node exports have different intent. A polaroid freezes a moment in time, so collisions are unwanted accidents and the counter keeps both copies. A node export publishes the current authoritative version of a structured artefact (palette, future per-node exports), so overwrite is the desired behaviour. A future pass might unify them under a shared collision-policy parameter, but the difference reads correctly today.

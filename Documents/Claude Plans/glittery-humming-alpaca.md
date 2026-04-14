# Documents/ Restructure + Nested Info Menu + GitNode Writeup

## Context

Documents/ is flat — architecture docs, compliance reports, build versions, and design briefs all at the same level. We're adding a GitNode writeup and need structure for the growing doc library. The Info sidebar menu dynamically scans Documents/ for .md files, so it needs to handle subdirectories with nested context menus.

## File Moves

```
Documents/
├── Architecture.md                          ← stays (top-level reference)
├── Node Type Schema.md                      ← stays (top-level reference)
├── Build/
│   ├── Build Version.md                     ← moved
│   ├── Build Version Previous.md            ← moved
│   └── Build Version Archive.md             ← moved
├── Compliance/
│   ├── Docstring Compliance Report.md       ← moved
│   └── Python Header Compliance Guide.md    ← moved
├── Design/
│   └── Settlers Category Design Brief.md    ← moved
├── Nodes/
│   └── The Brilliant GitHub Node.md         ← NEW writeup
└── data/                                    ← stays (session files)
```

## Code Changes

### 1. Move files via git mv (preserves history)

### 2. `main_window.py` — `_show_info_menu` (line ~1519)
- Currently: scans `Documents/` for `.md` files, flat list
- Change: recurse into subdirectories, build nested submenus per folder
- Folders become submenu entries (folder name as label), files inside become actions
- Top-level `.md` files still appear directly in the main menu (Architecture.md, Node Type Schema.md are excluded via `_DEDICATED`)

### 3. `build.py` (line ~98)
- Currently writes to `Documents/Build Version.md`
- Update to `Documents/Build/Build Version.md`
- Also update rotation paths for Previous and Archive variants

### 4. `CLAUDE.md` 
- Reference to `Documents/Architecture.md` stays (no change)
- Add mention of new folder structure in Architecture section

### 5. Claude memory files
- `project_node_type_schema.md` — path unchanged (stays at Documents/ root)
- `project_deployment.md` — update build.py reference from `Documents/Build Version.md` to `Documents/Build/Build Version.md`

### 6. Write `Documents/Nodes/The Brilliant GitHub Node.md`
- Feature writeup suitable for animation into a presentation
- Cover: repo scanning, status indicators (dirty/session/unpushed/clean), bulk push with offline guard, plushie loading ceremony, GitHub Desktop launcher with maximize

## Files to Modify
- `main_window.py` — `_show_info_menu` method (~line 1493)
- `build.py` — docs folder path (~line 23, ~line 98)
- `CLAUDE.md` — add folder structure note
- `C:\Users\thisg\.claude\projects\C--Users-thisg-Desktop-Intricate\memory\project_deployment.md` — update path

## Verification
- Launch app, click Info sidebar button — see nested submenus for Build/, Compliance/, Design/, Nodes/
- Top-level Architecture.md and Node Type Schema.md still have dedicated node entries
- Click a nested doc entry — spawns a MarkdownNode with the content
- Run build.py — Build Version.md lands in Documents/Build/

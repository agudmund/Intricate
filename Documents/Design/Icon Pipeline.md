# Icon Pipeline

The process by which every button, sidebar entry, and node-embedded control in Intricate acquires its graphic. Icons are not decoration here — they carry the visual language of the app, and the canvas is dense enough that a mismatched icon reads as a bug. This document describes the three icon families, the end-to-end pipeline that produces each family, and the wiring that surfaces the finished asset at runtime.

## The Three Families

Every icon in the app belongs to exactly one of three families. The families are distinguishable at a glance and are built by different pipelines. They co-exist deliberately — a canvas with only one family feels flat; a canvas with all three reads as a layered workspace with chrome, characters, and tools.

| Family | Role | Visual language | Example |
|---|---|---|---|
| **Sidebar & Toolbar** | The furniture — quiet, professional, framing | Cream line-art inside a ring, transparent background | Category buttons (Text, Images, Audio) |
| **Node Function (emoji)** | The stars — primary actions that define what a node *is* | 3D shaded emoji, warm gradients, soft depth | The octocat on GitNode |
| **Node Utility (sticker)** | The tools — secondary actions a node *can do* | Flat coloured fill, dark outline, white peel border | The push arrow on GitNode, the pause button on AudioNode |

The hierarchy reads as: emoji buttons are the stars, sticker buttons are the tools, sidebar icons are the furniture. An icon's family is a decision about role before it's a decision about style.

All three families render through the same widget, `NodeButton`. Sidebar/Pillow (Family 1) and emoji (Family 2) icons get a **1.28×** scale to compensate for the ~22% transparent padding around their outer ring; without it they read visibly smaller than emoji glyphs sitting next to them on the same button strip. Sticker icons (Family 3) fill edge-to-edge out to their white peel border and render at **1.0×** — scaling them up would crowd the strip. The branch lives at `nodes/NodeButton.py:133` as `scale = 1.0 if self._sticker_shadow else 1.28`.

## Family 1 — Sidebar & Toolbar (Pillow line-art)

The quiet family. Used for sidebar category buttons, toolbar actions, menu entries, and anything framing the workspace. Drawn programmatically with Pillow — no generator, no image round-trip, no extraction step.

### Visual specification

- Cream colour `(225, 213, 198, 255)` on transparent background
- Outer circle ring, constant across the family: `ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)`
- Symbol lives inside the ring, well clear of the edges (`cx ± 550`, `cy ± 350` is a safe envelope)
- Stroke width ~20–30px at 2048 renders as ~10–15px at the final 1024 target
- Minimal-maximalist — functional form, strong silhouette, no ornament

### Pipeline

Standalone Python script, run once per icon. The full recipe:

```python
from PIL import Image, ImageDraw

S  = 2048                               # 2× render for smooth LANCZOS downsample
cx = cy = S // 2
C  = (225, 213, 198, 255)               # cream — matches the family palette

img  = Image.new('RGBA', (S, S), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Outer ring — keep identical across all icons for visual consistency
draw.ellipse([cx-800, cy-800, cx+800, cy+800], outline=C, width=52)

# ── Draw your symbol here, centred ──────────────────────────────────
# draw.line(), draw.ellipse(), draw.rounded_rectangle(), etc.

# Downsample → 1024 PNG
out = img.resize((1024, 1024), Image.LANCZOS)
out.save('icons/xxx_node.png')

# Multi-resolution ICO
out.save('icons/xxx_node.ico', format='ICO',
         sizes=[(s, s) for s in [16, 24, 32, 48, 64, 128, 256]])
```

No extraction step. No defringe. The output is always exactly what the draw calls produced — Pillow's compositor operates in straight alpha, so anti-aliased edges are already clean against transparent.

## Family 2 — Node Function (emoji)

The characters. Used for primary node function buttons — the action core to what the node *does*, rendered in a 3D emoji aesthetic so it sits flush next to native emoji buttons on the same strip. Bold, warm, character-driven.

### Pipeline

Four stages:

1. **Draft** — use the Pillow recipe above to sketch a clean vector silhouette (outer ring + symbol). This is the structural reference, not the deliverable.
2. **Generate** — feed the silhouette to an image generator asking for a 3D shaded emoji render: warm gradients, soft lighting, subtle depth, matching the OS emoji look. Tweak the prompt until the render sits visually flush with native emoji glyphs.
3. **Extract** — write a Python script (see `tools/icon_pipeline/scripts/extract_github_icon.py` as reference) that crops the icon from the generated strip, removes the background via colour-distance masking (`numpy`), removes any drop shadow underneath (dark pixels in the bottom region), trims transparent edges, pads to square, and resamples to 1024×1024.
4. **Wire** — register in `[theme.icons]` in `settings.toml`, reference via `Theme.iconXxx`.

The draft step exists because generators produce consistent proportions and centering when seeded from a clean silhouette — without it, each icon's content sits at a different size inside the ring and the family reads inconsistent.

## Family 3 — Node Utility (sticker)

The tools. Used for utility and housekeeping actions on the button strip — things a node *can do* but that aren't its primary identity. Flat sticker aesthetic: bold shape, coloured fill, dark outline, white peel border. Visually distinct from emoji buttons so the user reads them as tools rather than characters.

### Pipeline

Same four stages as Family 2, with one critical addition in extraction:

1. **Draft or source** — create or find a clean flat icon of the action (arrow, gear, refresh, pause). A simple vector with a sticker-border treatment works best.
2. **Generate** — ask the image generator for a sticker style: flat coloured fill (purple/blue tones fit the palette), dark outline, white cut-out border, no drop shadow.
3. **Extract** — see reference implementations in `tools/icon_pipeline/scripts/extract_push_icon.py`, `extract_trim_audio.py`, `extract_pause_icon.py`. The script must:
   - Crop the icon from the generated image
   - Remove the background via colour-distance masking + warm-fringe removal
   - Use `scipy.ndimage.label` to keep the largest connected component (kills stray dots)
   - **Defringe white matte contamination** on semi-transparent edge pixels — this step is non-negotiable (see next section)
   - Trim transparent edges, pad to square, resample to 1024×1024
   - Produce both `.png` and multi-resolution `.ico`
   - Write a verification PNG composited on the node background for visual check
4. **Wire** — same as Family 2.

### The defringe step

Anti-aliased edge pixels in a generated sticker carry baked-in white from the source matte. Composite such a pixel onto Intricate's dark node background and the baked-in white shows as a visible halo. The defringe reverses the compositing math: for each semi-transparent pixel, recover the pre-composite RGB by inverting `observed = α·actual + (1-α)·255`:

```python
alpha_norm = np.clip(a / 255.0, 0.001, 1.0)
semi_transparent = (a > 0) & (a < 250)
for ch in range(3):
    original = arr[:, :, ch]
    decontaminated = (original - 255.0 * (1.0 - alpha_norm)) / alpha_norm
    arr[:, :, ch] = np.where(
        semi_transparent, np.clip(decontaminated, 0, 255), original
    )
```

Solid interior pixels (`α == 255`) are left alone — only the edge band needs correction. Skip this step and the sticker looks fine on white, visibly haloed on the canvas.

### The verification step

Every sticker extraction script writes a companion PNG composited onto the node background:

```python
dark_bg = Image.new("RGBA", (1024, 1024), (45, 52, 54, 255))
dark_bg.paste(out, (0, 0), out)
dark_bg.save("Documents/Data/Icon Pipeline/_verify_xxx_dark.png")
```

`(45, 52, 54)` is the canonical node background. The verification PNG is where a bad defringe reveals itself. Visually check the `_verify_*_dark.png` before considering the extraction done. Verify PNGs land in `Documents/Data/Icon Pipeline/`, **not** in `icons/` — `icons/` is reserved for production assets the running app references; verify composites are author-time audit artefacts and live alongside the other `Documents/Data/` runtime sidecars. The toolkit constant is `VERIFY_DIR` in `tools/icon_pipeline/paths.py`; `write_dark_verify()` honours it by default and creates the directory on demand. These files are tracked alongside the icons they verify — `git ls-files "Documents/Data/Icon Pipeline/_verify_*_dark.png"` lists the current set — so a future audit can re-inspect what each extraction shipped against the dark backdrop without re-running the pipeline.

## Wiring — From File to Rendered Button

Once an icon's `.ico` and `.png` exist in `icons/`, three things connect it to the running app:

1. **Registration** in `settings.toml`:
   ```toml
   [theme.icons]
   xxx = "xxx_node.ico"
   ```
2. **Metaclass resolution** in `pretty_widgets.graphics.Theme` — `Theme.iconXxx` resolves dynamically through the metaclass. Icons are looked up first in `./icons/`, then in `$SingleSharedBraincell_AssetVault`. A missing icon returns a circle sentinel — the app never crashes over a missing asset.
3. **Reference** from code — whatever button-building helper is in use (`setup_iconic_button`, `_make_exid_button`, a `NodeButton` on a node's button strip) takes `Theme.iconXxx` and passes the resolved path to Qt.

No code change is needed to add a new icon — the metaclass auto-exposes whatever is registered in `[theme.icons]`. Adding a new button that uses an existing icon is a one-line reference. Adding a new button with a new icon is "register + reference."

## The Icon Rule

Whenever a new button is added **anywhere** in the app — sidebar, toolbar, node-embedded control, dialog — a matching `.ico` must be generated with it. No button ships without its own icon. The right family is the one that matches the button's role in the visual hierarchy above. A sidebar action that ships with a hand-drawn sticker will feel miscategorised; an emoji button that ships with a Pillow line-art icon will read as secondary when it should read as primary.

## Worked Example — The 2026-04-22 Pause Refresh

The pause sticker used by AudioNode, VideoNode, and MergeNode had been extracted from a low-resolution source with visible kerning artefacts. The refresh produced a concrete walkthrough of the Family 3 pipeline with the simplest possible extraction path:

1. **Source** — a new cleaner sticker was hand-cleaned into `Images/Stickers/Pause.png`, carrying its own alpha channel (fully transparent outside, opaque inside the sticker peel). This made the flood-fill step in the old extraction script redundant.
2. **Extraction** — `tools/icon_pipeline/scripts/extract_pause_icon.py` was simplified to: largest-component cleanup → white-matte defringe on semi-transparent edges → trim, square, 1024 resize → PNG + multi-res ICO.
3. **Verification** — the verify PNG against `(45, 52, 54)` showed a clean white peel with no halo on the dark background.
4. **No wiring change** — the output filenames (`icons/pauseIconic.png`, `icons/pauseIconic.ico`) were preserved, so every consumer via `Theme.iconPauseIconic` picked up the new asset on the next Theme reload.

The update was two files of work (source PNG + script) and zero lines of Python-consumer change. That is the pipeline running as designed: when assets are the primitive and consumers reference them through the metaclass, a visual refresh is a data edit, not a code edit.

## The Brand Mark Refresh Chain

`icons/Stickers/Intricate.ico` is the proprietary identity icon. It sits on the desktop `.lnk`, the pinned taskbar slot, the systray, the `.intricate` file-type icon in Explorer, and embedded in the `.exe` at build time. Refreshing it touches more than a node icon does because Windows caches the rendered version per file *and per app-identity* across several shell databases and registry hives — the icon-pipeline scripts produce the new asset, but the OS won't surface it until those caches are explicitly invalidated.

The pipeline for the brand mark itself is deliberately simple. `tools/icon_pipeline/scripts/extract_intricate_icon.py` is a passthrough, not an extraction — the PNG at `icons/Stickers/Intricate.png` is treated as already-finished art (authored externally, dropped in by hand). No defringe, no largest-component cleanup, no resize. The script just writes a verify composite on the dark node bg and emits the multi-resolution ICO from the source as-is. This is the right shape because the input is a fully-cleaned hand-authored sticker, not a generator output that needs the post-processing tail.

The complete refresh chain — verified manually on 2026-05-10, every step here is a real touch point with an associated failure mode if skipped:

**1. Regenerate the ICO**
`python tools/icon_pipeline/scripts/extract_intricate_icon.py`. Produces `icons/Stickers/Intricate.ico` (7 frames: 16/24/32/48/64/128/256) and `Documents/Data/Icon Pipeline/_verify_intricate_dark.png`. If skipped: nothing else does anything useful, every downstream step propagates the old icon.

**2. Re-save both `Intricate.lnk` shortcuts**
There are *two* live `.lnk` files that pin the icon path, not one:
- `C:\Users\thisg\Desktop\Intricate\Intricate.lnk` — the project-folder launcher (what File Explorer surfaces)
- `%AppData%\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\Intricate.lnk` — the pinned-taskbar shortcut

For each: load via `WScript.Shell.CreateShortcut(path)`, set `IconLocation = "C:\…\icons\Stickers\Intricate.ico,0"`, call `Save()`. Bumps mtime and forces Explorer to re-read the `IconLocation` field. If skipped: the per-file shell-icon cache keyed on the old path persists, so the icon never visibly changes in that surface.

  Runnable: `Documents/Data/icon_pipeline_lnk_resave.ps1`

**3. Update the `.intricate` file-association DefaultIcon (registry)**
`HKCU\Software\Classes\Intricate.Session\DefaultIcon` stores the icon path Explorer uses when rendering `.intricate` session files. This **auto-heals on Intricate boot** via `register_file_association()` in `main.py` — `_expected_association_icon()` returns the current canonical path and the registrar rewrites if drifted. Worth knowing because: if you've changed the path but haven't relaunched Intricate yet, this is still stale; and on a fresh setup it has to land before file icons render correctly. `Set-ItemProperty -Path "HKCU:\Software\Classes\Intricate.Session\DefaultIcon" -Name "(Default)" -Value "..."` is the direct write.

**4. Wipe shell icon caches**
Stop `explorer.exe`, delete every `iconcache_*.db` and `thumbcache_*.db` under `%LocalAppData%\Microsoft\Windows\Explorer\`, then restart `explorer.exe`. The legacy `%LocalAppData%\IconCache.db` (Win7/XP-era) is **conditional** — modern Win11 does not generate it, so don't worry if it isn't present. The cache files hold rendered-pixel snapshots keyed by file path; they don't refresh on icon-content change unless deleted. Explorer will be down for ~1–2 seconds and respawn automatically; iconcache files rebuild immediately on restart, thumbcache files repopulate lazily as folders are browsed. If skipped: icons on the desktop and in Explorer continue to show the cached old rendering even though every path now points correctly.

  Runnable: `Documents/Data/icon_pipeline_cache_flush.ps1`

**5. Reset the identity-locked Personalization cache**
This is the cache the memory entry `project_personalization_panel_cache_is_identity_locked.md` warns about. Win11 stores per-AUMID systray state in `HKCU\Control Panel\NotifyIconSettings\<hash>\` — and crucially, **the cached icon is stored as raw PNG bytes inside the `IconSnapshot` registry value** (starts with `\x89PNG` header), not as a path reference. So even when every path is corrected, Windows keeps showing the embedded snapshot until that key is deleted. The reset:
- Locate the entry whose `ExecutablePath` is `C:\python\pythonw.exe` (Intricate's launcher), delete the whole sub-key `Remove-Item "HKCU:\Control Panel\NotifyIconSettings\<hash>" -Force -Recurse`.
- Sweep stale identity records: `Remove-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\FeatureUsage\AppSwitched" -Name Intricate` (the historical bare-identity baggage), same for `SingleSharedBraincell.Intricate`, same for `ShowJumpView\Intricate`. These are alt-tab and jump-list usage counters; deleting them is cosmetic but clears the identity attachments.
- Refresh the shell: `& "$env:SystemRoot\System32\ie4uinit.exe" -show` (returns exit 1 even on success — normal), then broadcast `SHChangeNotify(SHCNE_ASSOCCHANGED)` via `[Shell32]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)`.
- **DO NOT touch `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Taskband\Favorites` or `FavoritesResolve`** — those are the pinned-items blob for *every* app on the taskbar. Wiping them loses every pinned item, not just Intricate.
- Always back up first: `reg export "HKCU\Control Panel\NotifyIconSettings\<hash>" backup.reg /y`.

  Runnable: `Documents/Data/icon_pipeline_identity_cache_reset.ps1`

If after step 5 the pinned taskbar slot still shows the wrong icon, the bulletproof fallback is **manual unpin + repin** of the taskbar item — Windows binds fresh on repin and there's no programmatic alternative that matches its reliability.

**6. Restart Intricate**
The running window's taskbar icon and the systray icon come from `QIcon("icons/Stickers/Intricate.ico")` loaded once at process start. A vaporize-relaunch picks up the new asset. If skipped: the *running* session keeps showing the old icon in its own window and tray slot even though everything else in the OS has refreshed.

What this chain **does not** require is a fresh AUMID. The namespaced form `SingleSharedBraincell.Intricate` (set in `main.py` via `SetCurrentProcessExplicitAppUserModelID`) was a one-time fix for the Win11 Personalization > Taskbar cache that had bound a wrong icon to the bare `Intricate` identity at some earlier point. That binding is now path-stable — once the cache reset above runs, the pinned-taskbar slot picks up the new mark on next launch. Future brand-mark refreshes do not need re-namespacing.

The brand mark also doubles as `Theme.iconCurtains` — it is BOTH a real UI primitive (the curtains share-arrow that appears on the canvas) AND the family-wide fallback for any missing-icon lookup. If a `Theme.iconXxx` reference can't resolve, the metaclass returns this share-arrow as the sentinel rather than crashing. Recognising the share-arrow in a "wrong icon" bug means our own fallback path triggered, not a Windows-generic placeholder.

## The Personalization › Taskbar Panel — What Drives What

The panel at Settings › Personalization › Taskbar › "Other system tray icons" is a hybrid surface that merges several data sources. The 2026-05-10 investigation mapped which input drives which output — useful because the obvious-sounding levers (Qt's `setToolTip`, AUMID metadata, the registry's `InitialTooltip` field) turned out to *not* drive the panel's label, while only `IconSnapshot` moved the icon. The actual ground truth:

| Panel surface | Data source | Notes |
|---|---|---|
| **Icon** (the small image in the row) | `HKCU\Control Panel\NotifyIconSettings\<hash>\IconSnapshot` — raw PNG bytes embedded in the registry value | This is the lever. Write 32×32 PNG bytes, the panel updates on next Settings *reopen* (UI caches; close-window + reopen forces re-read). |
| **Label** (the row text) | PE `FileDescription` resource embedded in the binary at `ExecutablePath` | NOT registry. `InitialTooltip`, `AUMID DisplayName`, and Qt `setToolTip` were all tested and none of them moved this. |
| **Toggle state** (On/Off switch) | `NotifyIconSettings\<hash>\IsPromoted` | `1` = pin to visible tray, `0` = stay in chevron overflow. |
| **Hover tooltip** on the live systray icon | `Shell_NotifyIcon` `szTip`, populated live by Qt's `setToolTip` | Independent of the panel — affects only the live tray icon, not the persistent panel row. |
| **Live entry presence** in panel before user has toggled | Shell_NotifyIcon enumeration of running tray processes | Apps appear in the panel because they're currently running with a registered tray icon. The first user-toggle is what *persists* a `NotifyIconSettings\<hash>\` entry. |

### Why dev shows "Python" and production will show "Intricate"

The panel label comes from the PE `FileDescription` resource of the binary at `ExecutablePath`. Two realities for Intricate:

| Mode | Launcher | PE FileDescription | Panel label |
|---|---|---|---|
| Dev | `C:\python\pythonw.exe` | `"Python"` (Microsoft's resource) | `Python` |
| Built | `dist\Intricate\Intricate.exe` | `"Intricate"` (PyInstaller writes from `--name`) | `Intricate` |

There is no registry override for this. The label being "Python" in dev mode is a property of running interpreted Python via Microsoft's launcher binary — the same way a Node app run via `node main.js` would surface as "Node.js" in the panel. **It's technically correct (the binary running IS pythonw.exe) and resolves naturally to "Intricate" the moment a built `.exe` ships.**

The `IconSnapshot` lever IS available, though, so the dev-mode panel shows "Python" *with the correct brand sticker* — enough identifier that the row is unambiguously Intricate's even while the binary name reads as generic.

### What we tested and what each lever actually did

Five distinct writes attempted while chasing the panel label; only one moved the rendering:

- ✅ **`IconSnapshot`** (PNG bytes in `NotifyIconSettings\<hash>\`) → drives the panel icon. Confirmed.
- ❌ **`InitialTooltip`** (`NotifyIconSettings\<hash>\InitialTooltip`) → no observable effect on this panel. May still be read by other Windows surfaces.
- ❌ **AUMID `DisplayName`** (`HKCU\Software\Classes\AppUserModelId\SingleSharedBraincell.Intricate\DisplayName`) → no effect on the Personalization panel. Likely affects other surfaces (toast notifications, jump lists, the "running apps" listing in Task Manager).
- ❌ **AUMID `IconUri`** (sibling above) → no effect on the Personalization panel.
- ✅ **Qt `setToolTip("Intricate")`** → drives the hover-tooltip over the live tray icon. Confirmed at the systray, not at the panel.

The four no-bite writes still ship because they're harmless and may bite for surfaces we haven't catalogued (jump lists, taskbar grouping for chained processes, toast titles). The boot-time self-heal maintains all of them at the canonical values.

### Boot-time Self-Heal — `_heal_systray_panel_metadata()`

In `main_window.py`'s `_setup_system_tray()`, immediately after Qt registers the tray icon and tooltip, an idempotent helper runs:

```python
self._heal_systray_panel_metadata()
```

It writes (silently, non-fatal on every step):

1. **AUMID metadata** at `HKCU\Software\Classes\AppUserModelId\SingleSharedBraincell.Intricate`:
   - `DisplayName = "Intricate"`
   - `IconUri = <absolute path to icons/Stickers/Intricate.ico>`

2. **NotifyIconSettings sweep** — for every entry whose `ExecutablePath` filename matches Intricate's launcher (`pythonw.exe` / `python.exe` in dev, `Intricate.exe` in production), writes:
   - `InitialTooltip = "Intricate"`
   - `IconSnapshot = <32×32 PNG bytes>` rendered via `QIcon(path).pixmap(32, 32).save(QBuffer, "PNG")`

Both `python.exe` and `pythonw.exe` are patched because Windows aggregates them under one panel row, so whichever variant the current run is using might not be the one with the persisted entry.

If no matching `NotifyIconSettings` entry exists yet (user has never toggled the panel switch), the sweep finds nothing and the function returns silently. The user's first panel toggle creates an entry; the next Intricate launch patches it automatically with the current brand mark — no manual intervention.

The shape mirrors `_ensure_file_association()` in `main.py`: write the canonical state to known registry surfaces on every boot, accept that some writes might no-op or fail, and trust that eventual convergence happens across normal user workflows.

For the AUMID metadata write specifically as a standalone outside the Intricate runtime (useful for setup-time, fresh-machine recovery, or verification): `Documents/Data/icon_pipeline_aumid_register.ps1`.

### Other maintenance scripts

- **`Documents/Data/icon_pipeline_orphan_cleanup.ps1`** — sweeps `NotifyIconSettings` for entries whose `ExecutablePath` no longer exists on disk (apps uninstalled, retired Microsoft Store versions, etc.) and removes them after a `.reg` backup. Runs in preview mode by default; `-Apply` to delete. Useful as a periodic tidy pass — Windows accumulates orphans over time but never auto-prunes.

### One-shot manual patch — `Documents/Data/spp_systray_label.ps1`

For machines where the runtime self-heal hasn't yet had a chance to populate, the one-shot PowerShell script does the same patching from outside Intricate. Useful for: fresh setups, manual recovery after a registry reset, or verifying the panel update independently of Intricate's runtime. Runs in HKCU — no admin elevation needed.

```
& 'C:\Users\thisg\Desktop\Intricate\Documents\Data\spp_systray_label.ps1'
```

The script generates the PNG via `System.Drawing` instead of Qt (so it can run from any PowerShell session, no Qt runtime needed) and writes to the same two `NotifyIconSettings` entries. Idempotent — safe to run repeatedly.

## Technical Notes

- **Render at 2×, downsample via LANCZOS.** The Pillow recipe renders at 2048 and downsamples to 1024 because Pillow's draw primitives do not anti-alias — the LANCZOS downsample is what produces smooth edges. Drawing directly at 1024 produces visibly jagged strokes.
- **Multi-resolution ICO matters.** Qt picks the sharpest layer for each render target — a 16px tray icon uses the 16px layer, a 256px menu icon uses the 256px layer. Shipping a single-resolution ICO produces blurry small renders.
- **The extract / generate scripts are one-shot tools, not runtime modules.** They live in `tools/icon_pipeline/scripts/`, each with a brief docstring identifying its source PNG and the icon it produces. They are not imported by anything in the runtime app — running one is a manual authoring action. They MAY import from the local `tools/icon_pipeline/` toolkit (canvas, save, extract, verify, batch helpers) so the family-1 canvas scaffolding, defringe, largest-component cleanup, multi-resolution ICO save, etc. don't have to be copy-pasted across every script. The toolkit itself is also author-time only — it never lands in the runtime tree, only build-time scripts touch it.
- **`NodeButton.py`'s 1.28× / 1.0× split is load-bearing.** Non-sticker icons (Families 1 & 2) get 1.28× to compensate for ~22% transparent padding around the outer ring; stickers (Family 3) fill edge-to-edge to their white peel border and stay at 1.0×. The branch is `scale = 1.0 if self._sticker_shadow else 1.28`. Change the padding convention and these constants must change in lockstep, or icons drift in apparent size relative to emoji glyphs on the same strip.
- **Theme reload is live.** Saving `settings.toml` after registering a new icon triggers `Theme.reload()` and repaints every button that references the metaclass attribute. No restart required for icon swaps once wiring exists.

## Source Workspace vs Production Icons

Two distinct directories, two distinct roles:

| Location | Holds | Role |
|---|---|---|
| `Images/Stickers/` | Hand-authored sticker source PNGs in flight — kerning being cleaned up, palette being conformed, white padding being normalised to the 30 px standard | **Source workspace** — author-time lookdev folder. Pipeline scripts read from here. |
| `icons/` | Finished, processed icons consumed at runtime | **Production** — the only directory the running app references. |

The flow is: **source PNG lands in `Images/Stickers/` → pipeline script processes (extract, defringe, square, multi-res ICO) → output written to `icons/`**. As each source completes its pipeline pass, the source file is ticked off and removed from the workspace; the finished icon in `icons/` is what consumers see.

**Production code never references `Images/Stickers/`.** The only readers of that folder are the author-time extraction scripts in `tools/icon_pipeline/scripts/` — they take source PNGs as input and produce icons as output. Anywhere else in the codebase pointing at `Images/Stickers/` is a bug (the Settlers systray icon path was the canonical example: a stale `Intricate/Images/Stickers/Chat.png` reference that survived the workspace's relocation and stopped resolving — fix was to point at the local `icons/Chat.ico` instead, the production-side asset).

**Current home of the workspace:** `Images/Stickers/` lives in `[Desktop]/Iconic/`, a dedicated session project for handling all icon work — separate from Intricate's repo so the lookdev iteration (palette conform, kerning cleanup, padding normalisation, sticker compliance audit) doesn't pollute the production tree. `Intricate/Images/Stickers/` still holds legacy sources mid-migration; once the migration completes, that location can be removed entirely. Pipeline scripts use relative paths (`Images/Stickers/Pause.png`) so they resolve against whichever working directory they're invoked from — typically the Iconic project root.

## Proprietary vs Tertiary — the directory split

The `icons/` directory is split into two zones at the file-system level, mirroring the design rule from `project_external_app_icons_translated.md`:

| Location | Holds | Examples |
|---|---|---|
| `icons/` (root) | **Proprietary** Intricate brand assets — every icon designed in our own visual language | `Stickers/Intricate.ico`, `warm_node.ico`, `claude_node.ico`, `Push.png`, every sidebar / toolbar / sticker icon authored in-house |
| `icons/Tertiary/` | **Tertiary** third-party brand assets — official icons of external apps Intricate references, kept in their original branding without alteration | `claude_desktop.ico`, `claude_cli.ico`, `anthropic_icon.ico`, `adobe_group.ico`, `indesign_app.ico`, `Adobe-Emblem.png` |

The split makes the proprietary/third-party boundary visible at a glance in the asset folder. It enforces the no-altered-branding rule physically: nothing in `icons/Tertiary/` is meant to be touched, recoloured, or restyled — these are the canonical brand assets of other companies, used as-is per the three-tier icon treatment doctrine. The proprietary `icons/` root, by contrast, is fair game for the recolor / solidify / rebuild batch utilities and any creative pass.

Some Tertiary icons are **procedurally extracted** from the OS at boot via `utils/app_icons.py` — `indesign_app.ico` from the registered `.indd` handler, `claude_desktop.ico` from the MSIX AppsFolder entry, `claude_cli.ico` from the CLI executable. Whatever version the user has installed becomes the canonical icon in the cache automatically. The cached files are written to `icons/Tertiary/` (the destination is the dict value in `_APP_ICON_MAP` / `_LAUNCHER_ICON_MAP`, prefixed with `Tertiary/`), keeping the boundary intact even for icons we don't author ourselves.

Settings.toml registrations for tertiary icons include the path prefix:

```toml
[theme.icons]
claude     = "Tertiary/claude_desktop.ico"
claudeCode = "Tertiary/claude_cli.ico"
anthropic  = "Tertiary/anthropic_icon.ico"
adobeGroup = "Tertiary/adobe_group.ico"
```

`Theme._resolve_icon_path` handles the subdirectory transparently — `Path(icons_dir) / filename` works for either flat or nested filenames, so the metaclass lookup stays the same regardless of whether the asset is proprietary or tertiary.

The split is a 2026-05-04 refactor — pre-this date, all icons sat flat in `icons/` and the proprietary/third-party boundary lived only in code conventions and our own discipline.

## The `tools/icon_pipeline/` Toolkit

The author-time helpers used by the generation and extraction scripts. Six small modules; the runtime app never touches any of this. Lives at `tools/icon_pipeline/` rather than embedded in the asset directory — `icons/` is for asset files only, code lives in `tools/` (different departments, same kitchen).

| Module | Surface | What it does |
|---|---|---|
| `canvas.py` | `make_line_art_canvas()`, `CREAM`, `CANVAS_SIZE`, `OUTPUT_SIZE` | Family-1 (sidebar / toolbar) entry point — build the 2048×2048 RGBA canvas with the canonical outer ring already drawn, return `(img, draw, cx, cy)` for the caller to add their symbol. |
| `save.py` | `save_png_and_ico()`, `DEFAULT_ICO_SIZES` | Universal output step — resize to 1024 LANCZOS, write `{name}.png` and the multi-resolution `{name}.ico` with the canonical seven-layer set `[16, 24, 32, 48, 64, 128, 256]`. |
| `extract.py` | `keep_largest_component()`, `defringe_against_white()`, `trim_and_square()` | Family-2/3 (emoji / sticker) post-processing tail — kill stray dots via `scipy.ndimage.label`, reverse-composite white-matte contamination off semi-transparent edges, crop to bbox + pad to square. |
| `verify.py` | `write_dark_verify()`, `NODE_BG` | The companion `_verify_*_dark.png` writer — composite the finished icon over `(45, 52, 54)` so a missed defringe shows as a halo before the icon ships. |
| `batch.py` | `run_over_icons()`, `BATCH_TARGETS` | Shared roster + iteration for the three batch utilities (`recolor_all`, `solidify_all`, `rebuild_ico`). The roster is centralised here so the three scripts can never drift again. |
| `paths.py` | `REPO_ROOT`, `ICONS_DIR`, `IMAGES_DIR` | Resolved-once `Path` constants so scripts get a stable anchor regardless of where they're invoked from or where they live in the tree. |

The toolkit was extracted on 2026-05-04 from the existing 47 scripts after an audit found:
- 13 extract scripts copy-pasted the same 5-line defringe block
- 13 extract scripts copy-pasted the same 7-line largest-component block
- 22 generators copy-pasted the same 4-line canvas + outer-ring scaffolding
- All 47 scripts copy-pasted the same 2-line multi-resolution ICO save
- The three batch utilities had three near-but-not-quite-identical hardcoded `ICONS = [...]` lists — actual drift, not just duplication

The 44 non-batch scripts kept their existing logic verbatim during the migration (they work; touching them risks breaking working extraction recipes for negligible gain). They migrate to the toolkit organically as they're touched in future work — next sticker update refactors that script, next batch refresh refactors those, etc. The three batch utilities WERE refactored at extraction time because their drift was the actual problem the audit caught.

## Relationship to Other Systems

- **Theme** (`pretty_widgets.graphics.Theme`) — the metaclass is what makes icon names feel like first-class attributes. Every icon filename in `settings.toml` becomes a `Theme.iconXxx` attribute at runtime. Theme used to live at `graphics/Theme.py` in this repo; it was extracted to the shared Pretty Widgets package alongside the rest of the family-wide infrastructure.
- **NodeButton** (`nodes/NodeButton.py`) — the single render point for all three families. Scaling, alignment, and hover handling live here, not in the button creation sites.
- **Settings contract** — `settings.toml` is the shared file contract with The Settlers. Icon registrations are written by hand in Intricate's development, but could in principle be edited from The Settlers without touching Intricate's code.
- **Asset vault** — `$SingleSharedBraincell_AssetVault` is the optional override path. An icon present in both the bundled `./icons/` and the vault resolves to the vault version first, giving the user a clean override channel without editing the repo.

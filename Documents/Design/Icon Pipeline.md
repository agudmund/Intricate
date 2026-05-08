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
dark_bg.save("icons/_verify_xxx_dark.png")
```

`(45, 52, 54)` is the canonical node background. The verification PNG is where a bad defringe reveals itself. Visually check the `_verify_*_dark.png` before considering the extraction done. These files are tracked alongside the icon they verify — `git ls-files icons/_verify_*_dark.png` lists the current set — so a future audit can re-inspect what each extraction shipped against the dark backdrop without re-running the pipeline.

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

## Worked Example — The 2026-05-08 Brand Mark Refresh

`icons/Intricate.ico` is the proprietary identity icon. It sits on the desktop `.lnk`, the running-window taskbar slot, the systray, and embedded in the `.exe` at build time. Refreshing it touches more than a node icon does because Windows caches the rendered version per file across several shell databases — the icon-pipeline scripts produce the new asset, but the OS won't surface it until those caches are flushed.

The pipeline for the brand mark itself is deliberately simple. `tools/icon_pipeline/scripts/extract_intricate_icon.py` is a passthrough, not an extraction — the PNG at `icons/Intricate.png` is treated as already-finished art (authored externally, dropped in by hand). No defringe, no largest-component cleanup, no resize. The script just writes a verify composite on the dark node bg and emits the multi-resolution ICO from the source as-is. This is the right shape because the input is a fully-cleaned hand-authored sticker, not a generator output that needs the post-processing tail.

When the PNG changes, the chain to refresh is:

1. **Regenerate the ICO** — `python tools/icon_pipeline/scripts/extract_intricate_icon.py`. Produces `icons/Intricate.ico` (7 frames: 16/24/32/48/64/128/256) and `icons/_verify_intricate_dark.png`.
2. **Re-save `Intricate.lnk`** — load the shortcut via `WScript.Shell`, set `IconLocation` back to `icons/Intricate.ico,0`, and call `Save()`. Bumps mtime and forces Explorer to re-read the `IconLocation` field. Without this, the per-file shell-icon cache for the .lnk persists.
3. **Wipe shell icon caches** — stop `explorer.exe`, delete every `iconcache_*.db` and `thumbcache_*.db` under `%LocalAppData%\Microsoft\Windows\Explorer\` (plus the legacy `%LocalAppData%\IconCache.db`), then restart `explorer.exe`. The cache files hold rendered-pixel snapshots keyed by file path; they don't refresh on icon-content change unless deleted.
4. **Restart Intricate** — the running window's taskbar icon and the systray icon come from `QIcon("icons/Intricate.ico")` loaded once at process start. A vaporize-relaunch picks up the new asset.

What this **doesn't** require is a fresh AUMID. The namespaced form `SingleSharedBraincell.Intricate` (set in `main.py` via `SetCurrentProcessExplicitAppUserModelID`) was a one-time fix for the Win11 Personalization > Taskbar cache that had bound a wrong icon to the bare `Intricate` identity at some earlier point. That binding is now path-stable — once the file content changes and the shell caches are flushed, the pinned-taskbar slot picks up the new mark on next launch. Future brand-mark refreshes do not need re-namespacing.

The brand mark also doubles as `Theme.iconCurtains` — it is BOTH a real UI primitive (the curtains share-arrow that appears on the canvas) AND the family-wide fallback for any missing-icon lookup. If a `Theme.iconXxx` reference can't resolve, the metaclass returns this share-arrow as the sentinel rather than crashing. Recognising the share-arrow in a "wrong icon" bug means our own fallback path triggered, not a Windows-generic placeholder.

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
| `icons/` (root) | **Proprietary** Intricate brand assets — every icon designed in our own visual language | `Intricate.ico`, `warm_node.ico`, `claude_node.ico`, `Push.png`, every sidebar / toolbar / sticker icon authored in-house |
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

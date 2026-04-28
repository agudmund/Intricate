# Changelog

> Append-only log of paradigm-level shifts. One block per shift, dated to the day it landed, newest at the top.
>
> Not a git log — `git log` is finer-grained and machine-readable. This is the human-readable "what *fundamentally* changed today" ledger. When `Documents/Architecture.md` drifts, this file still tells the truth about what's happened since its last refresh.
>
> Rules:
> - **Append only.** Never rewrite past entries. If a paradigm is replaced, add a new entry referencing the old one.
> - **Commit hash + date** at the top of each entry — `git show <hash>` recovers the full diff.
> - **Three-ish sentences** per entry. Enough to orient, not a full essay. The compliance doc + memory files + per-node docs carry the depth.
> - **Paradigm shifts only.** Bug fixes belong in commit messages or the compliance log. This file is for the kind of change that would surprise someone who read the Architecture doc a week ago.

---

## 2026-04-28

### VideoNode swapped to PyAV — A/V Transport Engine Stage 1 + Stage 3 landed

QMediaPlayer is gone from VideoNode. The new backend is `utils/video_decoder.py` — PyAV (libav* via Python), one decoder thread per node, LOD-aware ingest at decode time via libswscale, frames delivered to the GUI thread via Qt signals. This is Stage 3 of `Documents/Design/A-V Transport Engine — Forward Design Exploration.md` landed standalone (Stage 2 Transport seat, Stage 1's auto-spawn AudioNode + ConductorNode chain, and Stage 4 audio sample-server still pending). Ping-pong is now a real loop mode — bounded ring buffer captures decoded frames on the forward pass and replays them in reverse, no seek-restart artifact at the loop boundary. Loop became tri-state (`off | loop | pingpong`) with back-compat read of the legacy `looping` bool.

### VideoNode amputated audio entirely (Stage 1 of the same doc)

`volume`, `muted`, the volume slider, the mute toggle button, the 1-second cull-fade, the `is_muted()` consultation, and the QAudioOutput pipeline are all gone. Audio is AudioNode's exclusive domain in the Transport architecture. Old session files still loadable — back-compat reads silently drop the audio fields. `MergeNode._overlay_to_file` updated to fall through to full volume on VideoNode-extracted tracks (was reading `node.data.volume`). Roughly 200 lines of complexity left the file. The auto-spawn-sister-AudioNode + ConductorNode chain that completes Stage 1 is deferred to its own pass; for now, audio for video clips is a manual AudioNode add.

---

## 2026-04-21

### Version bump: 0.6.0, "The Housekeeping before paradise arrives Era"

Two empty Kanban focal lists in one morning — zero bugs, zero active housekeeping — a first in the project's history. Changes gathered in the sweep: cross-session copy/paste (the v0.0.2 ceiling, the bug that caused the full-repo rewrite originally, finally closed), right-sidebar pin survives session switch + app restart, restart-on-close singleton release fixed after silent post-`shared_braincell`-migration break, bottom toolbar dormant shrink + eXid test-bench workflow, sidebar 2-row bars grid with icon-fill compensation, media-node teardown heap-corruption fix (VideoNode + AudioNode six-step pattern against `0xc0000374`), CRITICAL log emoji tag, PrettyPill widget extraction, `[theme.sidebar]` TOML migration, curtains + maximize taskbar breathing margin. Era name reflects the moment: paradise hasn't arrived, but everything breakable has been tended to and the ceiling on what can be built next has been removed.

### Cross-session copy/paste — the v0.0.2 ceiling lifted

Ctrl+C captures the selected chain as a pure-Python dict; session switch is harmless because the dict holds zero Qt references; Ctrl+V spawns fresh nodes via the existing `Scene.import_session` path (battle-tested by SessionNode's "Total Recall" drag-drop since v0.0.2). The historic bug in this territory killed both Intricate and Notepad++ Duplex+ Turbo and caused the full-repo delete + handwritten 2k-line core rewrite; it fell on the first attempt this time because the foundation — `to_dict`/`from_dict` universal, UUID remap generic, `_KNOWN_TYPES` whitelisting — had accumulated into the exact shape the fix required. Concrete validation that the 20+ iterations of refactor-safety discipline were load-bearing for something specific.

---

## 2026-04-18

### Inner-widget signal-destructor race closed on ClaudeNode (+ MergeNode sweep)

`0xc0000409` Qt fastfail in `ucrtbase.dll` two seconds after ClaudeNode shake-delete completed cleanly. Signals on inner widgets (`_input.submitted / textChanged / focused`) weren't disconnected before the crew's proxy teardown `deleteLater`'d the widget — late emissions during the deferred-destruction window hit bound methods on the dying node. Same class as the MarkdownNode fix earlier; now explicitly documented as a rule: any `self._inner.signal.connect(self._method)` where `_inner` is inside a declared proxy must be severed in `_demolition_pre`. Swept MergeNode's `_list.customContextMenuRequested` for the same shape. See `Documents/Compliance/Node Cleanup Compliance.md` 2026-04-18 entry.

### `08f5c4b` — Architecture doc refresh for 0.5.0 Era + breadcrumb infrastructure

Rewrote `Architecture.md` for the new paradigms landed over the preceding 24 hours. Then — realising the Architecture doc was going stale within a single day of iteration — stripped line counts and folder-tree diagrams from it, added a "last refreshed" marker at the top, and seeded this changelog as an append-only breadcrumb trail. Future readers get the big picture from Architecture, the drift since from here.

### `9d4ca9d`, `4d94ad5` — Bulk-delete ghost-net across all shake paths

Rare render artefacts where a deleted node's border chrome stayed on the viewport buffer under heavy shake-delete bursts. Each deferred-remove callback already invalidated the node's rect; added a `viewport.update()` at the outermost `_bulk_removing` counter release plus the single-node shake-delete path. Covers three routes: `BaseNode._shake_delete_group` (ctrl-a + shake), `Scene._clear_all` (session reload), `BaseNode.mouseReleaseEvent` deferred remove (single shake). Catches the residue Qt's paint scheduler occasionally misses when hundreds of `removeItem`s fire in one tick.

### `451e2d9` — Audio joins video at the helicopter altitude

Completed the cityscape metaphor on the aerial row: `Scene.update_video_visibility` now applies the 60 px tiny-render gate to both `VideoNode` and `AudioNode`. Zoom out far enough and the canvas goes properly silent — all decks quiet, matching the video-freeze. Existing `_fade_volume` envelope machinery handles the smooth silence/wake without any new infrastructure. One-line behavioural change; big metaphorical payoff.

### `9bfb0f5` — Pulse animation aerial-view gate

`NodeBehaviour._should_pulse()` silences hover pulse + bg animations when the node's on-screen size is below 60 px. The 1.018 pulse scale produces sub-pixel deltas at that size — pure CPU cost with zero visible effect. Preserves the signature "gust of wind through grass" cursor-sweep effect at street / penthouse zoom (see memory `project_pulse_vibrance_commitment.md`), silences it in the helicopter band where it can't read. Benchmark at `logs/bench_pulse_animations.py`.

### `c1d2d31` — Video tiny-render pause at aerial zoom

`Scene._MEDIA_TINY_RENDER_PX = 60`. When a video's on-screen dimension drops below this (typical trigger: zoom ~0.15 on a 400 px video), the node pauses its decoder and keeps painting the last frame as a static thumbnail. Existing viewport-intersection culling doesn't help at zoom-out (all videos technically "in view"); this gate closes that gap. Foundation of the sensory-with-altitude pattern that pulse + audio later joined.

### `2efc026` — HTML-free paste pipeline

`pretty_widgets.PrettyMenu.StyledTextEdit` now overrides `insertFromMimeData` to strip HTML from clipboard. `WarmNode` stores `body_text` as `toPlainText()` (was `toHtml()`) and migrates legacy HTML bodies through a scratch `QTextDocument` on load. Resolves session-specific lag from web pastes inheriting per-character span formatting — paint cost was scaling with formatted-run count, multiplied by pulse/bg animations forcing per-frame repaints. Ambient editor styling now applies uniformly regardless of paste source.

### `54159e6` — HealthNode click monitor: opt-in via settings

`WH_MOUSE_LL` low-level Windows mouse hooks delay every mouse event system-wide up to `LowLevelHooksTimeout` (default 200 ms) while Windows waits for the hook callback to return on the Qt main thread. Under any main-thread load that queues messages behind the hook, the delay becomes visible as sticky cursor response. The click-tracking display line on `HealthNode` is a nice-to-have, not core — gated behind `[intricate.health] click_monitor` in `settings.toml`, default off. Input lag that matched the timeout value exactly was traced directly to this hook firing on every mouse event.

### `99782ef` — utils/ concern-group regrouping + widgets/ vacated

`utils/` had grown to 22 flat files mixing six concerns. Split into `utils/persistence/` (session, media_cache, registry, HappyTimes), `utils/motion/` (MotionCurves, OrbitalMotion, hover_glow), `utils/pickers/` (ColorPicker, IconPicker, PhrasePicker); miscellany stayed at the root. `widgets/` folder vacated (Pretty Widgets absorbed it years ago; last file `StickerButton.py` moved to `utils/`). Companion commit `ced100f` fixed the `__file__.parent.parent` walks in moved persistence modules — they needed a third `.parent` after the deepening.

### `b19dc6e` — Demolition crew extraction: separate profession from construction

Teardown procedure extracted from every node's `_prepare_for_removal` into `nodes/_demolition.py`. Nodes now declare what they own via class-level manifest attributes (`_demolition_proxies`, `_demolition_timers`, `_demolition_animations`, `_demolition_thread_flag`, `_demolition_media_players`, `_demolition_workers`) and optional `_demolition_pre` / `_demolition_post` hooks for bespoke ordering. The crew walks the MRO so subclass declarations extend parent ones automatically. Replaced ~494 lines of per-node boilerplate with ~30 lines of declarations + a standalone 347-line crew. Same 5-phase procedure happens in one place for every node type; adding a new node type no longer requires re-learning the teardown recipe. See `Documents/Compliance/Node Cleanup Compliance.md` 2026-04-18 entry.

### `b120414` — Media cache extended to stickers + framework doc promoted

`StickerNode` now participates in the byte-preserving media cache alongside Image and Video: `cache_key`, `source_size`, `source_mtime` added to `StickerNodeData`; load hierarchy is cache-first (cache_key → source_path → legacy b64) with passive drift detection. `graphics/Scene.py`'s `gc_cache` call whitelists `"sticker"` in `_CACHED_TYPES`. New framework doc at `Documents/Design/Media Cache.md` treats the cache as a standalone primitive independent of any node type: four invariants (content-addressed keys, byte-preserving, free dedup, retention-by-reference), API surface table, recipe for adding new cached node types.

### `de24bd7` — Sticker UX polish: right-click Pin menu, sidebar regrouped

Right-click on a sticker opens a `PrettyMenu` with a checkable "Pin to Viewport" entry. Moved the sticker entry from the visual category to images in `node_registry.toml` and renamed from "Snickers Stickers!" to "Stickers" — images submenu order now reads image → video → sticker → sequence → fbx.

### `4e010b5` — StickerNode detached from BaseNode: first-class chromeless root

`StickerNode` inherits directly from `QGraphicsRectItem`, not `BaseNode`. Reference implementation for raw-image-style root types — no chrome, no pulse, no button strip to silence. Extracted shake-detection into shared helper `nodes/_shake_detect.py` (composed by both roots). Six external sites widened to duck-type over node roots (`hasattr(item, 'data') + hasattr(item, 'to_dict')`) so session save/load, scene clear, selection walking, placement collision all flow uniformly across roots. `ValueNode` is the natural next migration candidate; see memory `project_chromeless_root_candidates.md`.

### `74e592c` — Version bump: 0.5.0, "The Other Era"

The Expressive Era (0.3.0) taught the app how to communicate properly. The Other Era (0.5.0) inherits from there. Tagged as `v0.5.0` on origin for restore-point reference. Era naming is deliberately non-linear — 0.4.0 was skipped with authored intent (see memory `project_era_naming.md`); don't speculate on the gap.

### `90f2d60` — StickerNode scrollbar signal-destructor race closed + `viewTransformed` signal added

Shaking a pinned `StickerNode` was tripping `0xc0000409` Qt fastfail in `ucrtbase.dll` — a scrollbar `valueChanged` signal colliding with the node's destructor during the deferred-removeItem window. Added synchronous pre-shake quieting via new `_quiet_for_shake()` hook on `BaseNode` + subclass override on StickerNode. Also added `viewTransformed = Signal()` on `IntricateView`, emitted via overridden `scale()` / `translate()` — new canonical channel for pan/zoom-aware components that need to know when the view transform mutated. Pinned stickers now listen to this signal to stay anchored through pan-by-translate (scrollbars don't fire on canvas pan). Benchmark at `logs/bench_view_transformed.py` measures sub-μs-per-subscriber cost; 100-pinned-stickers worst case stays under 3 ms per pan gesture.

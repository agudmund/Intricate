# The Brilliant GitHub Node

A live git status dashboard that watches every repository on the Desktop surface. What started as "the boring but necessary node" evolved into a fully theatrical DevOps companion with personality, offline awareness, and a dancing plushie.

## What It Does

The GitNode scans all Desktop folders for `.git` directories on a configurable interval (default 10 s) and displays them in a colour-coded list grouped by status. It commits, pushes, and launches GitHub Desktop — all without leaving the canvas. The title "Git Status" reads in teal (`#72b8b8`, the Lombardi Lake variant lifted for plum contrast); the body is the live repo list.

## Status Indicators

Four states, each with its own dot colour in the repo list:

- **Blue dot** — Dirty. Uncommitted changes that are not session files. Needs review.
- **Green dot** — Session. Only session-managed files have changed — safe to bulk-commit without review. This includes:
  - Session save files (`{project}.intricate`, timestamped backups under `Documents/Data/Backup/`, legacy `session.json` / `session_previous.json` / `session_archive.json` for in-flight migrations)
  - Image node cache PNGs (`Documents/Data/Cache/*.png`, case-insensitive for layouts predating 2026-04-24)
  - Top-level runtime sidecars in `Documents/Data/` — `curtain_perf.csv`, `joy_stats.json`, `system_events.jsonl`. New sidecars added by the running app go here too (see `_SESSION_DATA_FILES` in `nodes/GitNode.py`)
  - Warm bridge temporaries (`.warm_bridge_*.json`)
  - The `Documents/Data/` tree itself (Backup/, Cache/, Data folder names)
- **Amber dot** — Unpushed. Working tree is clean but local commits have not been pushed to the remote. Detected via `git rev-list --count @{u}..HEAD`.
- **No dot** — Clean. Nothing to commit, nothing to push. Everything is in sync.

The list is grouped and separated: dirty repos on top (needs attention), then session repos (auto-committable), then unpushed (needs a push), then clean (all good). Each group is divided by a faint horizontal separator drawn at 30% opacity in the primary border colour.

## Auto-Height

The node auto-fits its height to the dirty + session + unpushed groups while leaving the clean group out of the height budget — clean repos are visible only when the user manually expands the node beyond the auto-fit height. This keeps the node compact when most repos are clean (the common case) without sacrificing visibility for the rare moment when something needs attention. Manual resize wins: once the user drags the node to a different size, auto-height stops nudging.

## Bulk Push

The push button (sticker-style arrow icon) collects session and unpushed repos in a single operation:

1. **Connectivity check** — pings `github.com:443` before anything else. If offline, spawns an AboutNode wired to the GitNode with a gentle reminder to turn the internet on, and sets the More Glory emoji to an unamused face.
2. **Curtain roll-up** — if the curtains are down (window collapsed to its compact state) the bulk-push gesture lifts them temporarily so the commit dialog has room to breathe. They restore to their previous state automatically once the dialog closes.
3. **Commit dialog** — if there are session repos, a frameless themed dialog asks for a commit message (placeholder text "session sync…"). Unpushed repos skip this step since they already have commits. Cancelling the dialog aborts the entire push.
4. **Parallel worker** — session repos get `git add -A`, `git commit`, `git push`. Unpushed repos get just `git push`. All repos push in parallel via `ThreadPoolExecutor(max_workers=8)`, fastest finishes first.
5. **Live updates** — each completed push sets a `_push_dirty` flag. The delivery timer (250 ms, main thread) picks this up and triggers a rescan — the green-dot list updates in real time as each repo finishes, not all at once at the end.
6. **On completion** — when the last future completes, a `_push_complete` flag fires the dismiss ceremony, shuffles the More Glory emoji to a random one (celebration), and restarts the poll timer.

## The Loading Ceremony

When spawned fresh from the sidebar, the GitNode performs a loading ritual:

1. A VideoNode appears to the right, wired to the GitNode, playing a looping animation of a dancing plushie bear with "YOU GOT THIS!" — the most encouraging progress indicator in existence. The clip lives in `./Clippy/Progress Plushie.mp4` (the project's video-asset folder, parallel to `Images/` which holds stills only).
2. The GitNode body shows "hang on, gimme a sec…" while the background thread scans repos.
3. The moment the scan completes, the VideoNode is dismissed — it bursts into a particle simulation, the wire dissolves, and the repo list slides into place.

The same ceremony plays during bulk push operations. The plushie dances while commits and pushes run on the worker thread, then bursts into particles when the operation completes.

The plushie video is an exception to VideoNode's default contract — it loops and autoplays from frame zero, where regular VideoNodes default to single-play and pause on load. The override is intentional: a paused frame zero would leave the user with no signal that anything is happening.

Session restores skip the animation entirely — the node loads quietly with its last known state.

## GitHub Desktop Launcher

The cat emoji button (custom 3D icon inspired by the GitHub octocat — a deliberate Tier-2 visual lineage that preserves the source's silhouette in Intricate's register) launches or focuses GitHub Desktop:

- If already running, maximizes and focuses the existing window.
- If not running, launches via the `github-windows://` protocol handler, then polls every 500 ms (up to ~10 s) for the window to appear and maximizes it automatically.
- Curtains roll up before the switch so GitHub Desktop has the full screen to itself when it comes forward.

This works around a Windows limitation where apps don't reliably restore their maximized state across launches.

## Claude App Launcher

A matching launcher in the sidebar's Claude category opens the Claude desktop app with the same maximize-on-launch pattern. Accessible from the Anthropic logo menu alongside the Claude Node and Token Counter.

## Emoji Mood System

The More Glory button reflects the node's operational state:

- **Offline push attempt** — switches to the unamused face (😒), a passive-aggressive but accurate status indicator.
- **Successful push** — shuffles to a random emoji from the full More Glory pool, celebrating the accomplishment.

## Configuration

`[node.git]` keys in `settings.toml` — all read live at call time, so changes take effect on the next scan or push without restarting the app:

| Key | Type | Default | Effect |
|---|---|---|---|
| `exclude_repos` | list | `[]` | Folder basenames to skip during scan and push. For cloned-but-not-maintained repos that share the Desktop with the user's own projects. |
| `poll_interval_ms` | int | `10000` | How often the auto-scan fires, in ms. Floored at 1000 to avoid runaway scans. |
| `status_color_session` | hex | `#7ac47a` | Green-dot colour. |
| `status_color_dirty` | hex | `#7a9ac4` | Blue-dot colour. |
| `status_color_unpushed` | hex | `#c4a87a` | Amber-dot colour. |

The status colours feed straight into `QColor` for dot painting, so any valid Qt colour string works — hex, named (`"darkseagreen"`), `rgb(…)`, etc.

## Technical Notes

- **Scan delivery** — repo scanning runs on a daemon thread with results delivered via a 250 ms poll timer on the main thread. The node appears immediately; the repo list populates asynchronously.
- **Session-path classification** — `_is_session_path()` identifies session-managed files via four mutually-reinforcing rules: `_SESSION_DATA_FILES` (top-level runtime sidecars), `SESSION_EXT` suffix (`.intricate` files including timestamped backups), case-insensitive `Documents/Data/Cache/` path-segment match, and the `_SESSION_DIRS` / `_LEGACY_SESSION_FILENAMES` basename sets. Add new runtime sidecars to `_SESSION_DATA_FILES` rather than expanding any of the broader rules; explicit is safer than broad here.
- **Unpushed detection** — uses `git rev-list --count @{u}..HEAD` which gracefully returns a non-zero exit code for repos without an upstream, falling through to clean status.
- **Cross-thread signaling** — the push worker communicates with the main thread via `_push_dirty` / `_push_complete` flags polled by the delivery timer. `QTimer.singleShot` from worker threads is unreliable in PySide6 and is not used.
- **Loading plushie lifecycle** — the VideoNode spawned during loading has its caption label suppressed (`_spawn_label = False`) and loops until dismissed. On dismiss, the video player is stopped synchronously and media links severed (`setVideoOutput(None)`, `setAudioOutput(None)`) before the deferred `removeItem`. Full teardown fires via `itemChange` → `_prepare_for_removal`, guarded by `BaseNode._removal_done` to prevent double cleanup.
- **Demolition contract** — `_demolition_timers` registers `_poll_timer` and `_delivery_timer` for the standard BaseNode teardown crew. `_demolition_pre` dismisses the loading plushie synchronously before the rest of the teardown runs, because the dismiss has its own orchestrated ordering (stop player, sever media links, clear wires) that needs the GitNode's signal surface still alive.
- **Push timeout** — 60 seconds per repo. Failures are logged with stderr output for diagnostics.
- **Parallel push** — `ThreadPoolExecutor(max_workers=8)` with `as_completed` — repos finish in order of speed, not submission order. Each completion triggers a rescan so the node visually reflects progress in real time.
- **Subprocess windows** — every `subprocess.run` uses `CREATE_NO_WINDOW` on Windows when running under pythonw (no console), so the user never sees a flicker of cmd.exe popping up during a scan or push.
- **Legacy depth tint** — the historical `#4a3a5a` value in `data.node_tint` is a "use Theme" sentinel rather than a real custom tint, so existing sessions saved with it fall through to the theme's depth-aware colours instead of forcing the legacy hue.

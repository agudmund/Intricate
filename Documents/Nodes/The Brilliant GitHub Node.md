# The Brilliant GitHub Node

A live git status dashboard that watches every repository on the Desktop surface. What started as "the boring but necessary node" evolved into a fully theatrical DevOps companion with personality, offline awareness, and a dancing plushie.

## What It Does

The GitNode scans all Desktop folders for `.git` directories every 10 seconds and displays them in a colour-coded list. It commits, pushes, and launches GitHub Desktop — all without leaving the canvas.

## Status Indicators

Four states, each with its own dot colour in the repo list:

- **Blue dot** — Dirty. Uncommitted changes that are not session files.
- **Green dot** — Session. Only session-related files have changed (auto-save artifacts). Safe to bulk-commit without review.
- **Amber dot** — Unpushed. Working tree is clean but local commits have not been pushed to the remote. Detected via `git rev-list --count @{u}..HEAD`.
- **No dot** — Clean. Nothing to commit, nothing to push. Everything is in sync.

The list is grouped and separated: dirty repos on top (needs attention), then session repos (auto-committable), then unpushed (needs a push), then clean (all good).

## Bulk Push

The push button (sticker-style arrow icon) collects session and unpushed repos in a single operation:

1. **Connectivity check** — pings `github.com:443` before anything else. If offline, spawns an AboutNode wired to the GitNode with a gentle reminder to turn the internet on, and sets the More Glory emoji to an unamused face.
2. **Commit dialog** — if there are session repos, a frameless themed dialog asks for a commit message. Unpushed repos skip this step since they already have commits.
3. **Worker thread** — session repos get `git add -A`, `git commit`, `git push`. Unpushed repos get just `git push`. All on a background thread so the UI stays responsive.
4. **On completion** — the More Glory emoji shuffles to a random one (celebration), and the repo list refreshes to reflect the new state.

## The Loading Ceremony

When spawned fresh from the sidebar, the GitNode performs a loading ritual:

1. A VideoNode appears to the right, wired to the GitNode, playing a looping animation of a dancing plushie bear with "YOU GOT THIS!" — the most encouraging progress indicator in existence.
2. The GitNode body shows "hang on, gimme a sec..." while the background thread scans repos.
3. The moment the scan completes, the VideoNode is dismissed — it bursts into a particle simulation, the wire dissolves, and the repo list slides into place.

The same ceremony plays during bulk push operations. The plushie dances while commits and pushes run on the worker thread, then bursts into particles when the operation completes.

Session restores skip the animation entirely — the node loads quietly with its last known state.

## GitHub Desktop Launcher

The cat emoji button (custom 3D icon inspired by the GitHub octocat) launches or focuses GitHub Desktop:

- If already running, maximizes and focuses the existing window.
- If not running, launches via the `github-windows://` protocol handler, then polls every 500ms for the window to appear and maximizes it automatically.

This works around a Windows limitation where apps do not reliably restore their maximized state across launches.

## Claude App Launcher

A matching launcher in the sidebar's Claude category opens the Claude desktop app with the same maximize-on-launch pattern. Accessible from the Anthropic logo menu alongside the Claude Node and Token Counter.

## Emoji Mood System

The More Glory button reflects the node's operational state:

- **Offline push attempt** — switches to the unamused face, a passive-aggressive but accurate status indicator.
- **Successful push** — shuffles to a random emoji from the full More Glory pool, celebrating the accomplishment.

## Technical Notes

- Repo scanning runs on a daemon thread with results delivered via a 250ms poll timer on the main thread. The node appears immediately; the repo list populates asynchronously.
- The `_is_session_path` filter identifies session-related files (`.intricate`, backup slots, warm bridge temporaries) so they can be auto-committed without cluttering the dirty list.
- Unpushed detection uses `git rev-list --count @{u}..HEAD` which gracefully returns a non-zero exit code for repos without an upstream, falling through to clean status.
- The VideoNode spawned during loading has its caption label suppressed (`_spawn_label = False`) and loops until dismissed. Cleanup follows BaseNode's deferred removal pattern via `itemChange` to avoid double `_prepare_for_removal` calls.
- Push timeout is 60 seconds per repo. Failures are logged with stderr output for diagnostics.

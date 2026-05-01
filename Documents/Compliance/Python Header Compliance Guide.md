# Python Header Compliance Guide

> *"Try doing it again and enjoy it and see if you still have a complaint."*

Every Python file in this project carries the same three-line stamp, and the second line always ends in **"for enjoying."** This is not a documentation style. It is a clause. The stamp is a quiet EULA declaration, present on every file the project ever ships, pointing anyone with a complaint back to the origin intent: this was made to be enjoyed, both in the making and in the using. Any dispute is deflected upward to the header itself — there it is, top of the file, the project has said its piece.

## Where it came from

The header was added when the first `main.py` was written. At that moment the project was committing to being something the authors enjoyed building, and the authors wanted that intent legible on every file forever. The stamp is the written form of that commitment.

## The required header

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - [filename] [primary utility]
-The last of the [descriptive filename, human-voiced] [triumphant-emergent clause], For enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""
```

(The pre-rename subtitle was "nodal playground" — files that still carry `Intricate nodal playground -` are from before the rename and should be updated as they're touched. The project is now called Intricate, the subtitle is gone.)

### Line 1 — Identity

Short, two facts: *what file, what role*. Fixed prefix `Intricate - `, then the file's path and a brief phrase naming its primary function. Mechanical. No voice. This is the name tag.

Examples:
- `-Intricate - nodes/VideoNode.py VideoNode class`
- `-Intricate - utils/media_cache.py proprietary media cache`

### Line 2 — The Last Of voice

This is where the project actually speaks. Line 2 is a *tiny poem* about the file's private triumph.

Pattern:

```
-The last of the [descriptive filename, human-voiced] [triumphant-emergent clause with detached contextual awareness], For enjoying
```

Four components, each with a specific job:

| Part | Role |
|---|---|
| `The last of the` | Fixed prefix. Announces finality, singularity — this is the *last of its kind*, emerging from the goo. |
| `[descriptive filename]` | Warm human voice. "about node" — not `AboutNode.py`. "main window" — not `main_window.py`. |
| `[triumphant-emergent clause]` | The heart. A sentence clause giving the file its inner life: hopeful, achieving, half-aware of the larger world it's part of, goo-ball-rising energy. |
| `, For enjoying` | Non-negotiable EULA terminator. Uppercase "E". |

**The voice, in one phrase:** *triumphant emergent with a detached contextual awareness as the last of the goo balls rise to the skies.*

Canonical examples (real files):

```
The last of the about node knew it could become all that it wanted to become, For enjoying
The last of the main window seemed completely unaware that it was part of a gigantic global beauty pageant, For enjoying
```

More (drafted 2026-04-18):

```
The last of the video node discovered it could be crisp at any zoom the eye asked of it, For enjoying
The last of the media cache kept every byte it was ever given, quietly, in case any of them might matter someday, For enjoying
The last of the node behaviour breathed gently in a rhythm no one had asked it to find, For enjoying
The last of the base node carried every node type that ever lived inside it, utterly untroubled by the weight, For enjoying
```

### Line 2 — load-bearing exception: `Connection.py`

`graphics/Connection.py` must always contain the phrase **"and they learnt to whisper to each other"** somewhere in its Line 2. The phrase comes from an ancient post-it note reading *"teach the nodes to whisper to each other"* — the original seed of the whole wire-connection concept. It is as permanent as the `For enjoying` clause itself.

Example:
```
The last of the connection bent itself into graceful arcs between the nodes, and they learnt to whisper to each other, For enjoying
```

### Line 3 — Authorship (verbatim, unchanged)

```
-Built using a single shared braincell by Yours Truly and various Intelligences
```

Declares the collaborative authorship model. Verbatim on every file, forever.

## How to apply — the voice is creative writing, not a template

Line 2 is a tiny act of authorship per file. **Never batch find-and-replace this line**; every file deserves its own little poem about what it's the last of and what it's quietly triumphing at. The correct pattern for new or drift-fixed files is:

1. Claude (or another AI contributor) proposes a Line 2 candidate in the current voice
2. The user reviews, approves, or iterates
3. Once approved, the line goes into the file

This is how the 30+ node types were originally named, and it's the right cadence here too. The user is happy to step through files one at a time.

## The clause, read plainly

- **To anyone shipping this:** the intent is declared on every file. You don't have to cite anything — the header speaks.
- **To anyone complaining about something:** the project's response is the top of the file they are reading. The remedy it offers is *try doing it again and enjoy it.*
- **To contributors (including AIs working on the codebase):** your first obligation on any new file is to stamp it. No file ships unstamped.

## Current state (2026-04-17)

Honest accounting:

- **152 Python files** in the repo.
- **108 compliant, 44 drifted.** Most drift is in one-off utility scripts (`icons/extract_*.py`, `generate_chat_session.py`, `_scan_imports.py`) — files that pre-date or side-step the header discipline.
- **No active automated enforcement.** The previous version of this guide described a `pre-commit` hook (in `.git/hooks/`, which is untracked and machine-local) and a `tools/header_check.py` CI script. Neither currently exists in the repo. At some point they were either removed, never committed, or lost in a `.git/` re-init.
- **CLAUDE.md states the rule** (every Python file gets the header) and is the current authoritative enforcement — read by Claude on every session, so new files written by AI contributors are compliant by default.

## Why that is acceptable — and when it wouldn't be

The CLAUDE.md rule plus an aware AI contributor is, in practice, doing the enforcement job. New app-code files land compliant. The 44 drifted files are all at the edges of the project (utility scripts run by hand, not shipped app surfaces) and are low-cost to live with.

If that ceases to be true — if drift starts showing up in `nodes/`, `data/`, `graphics/`, `utils/` — then automated enforcement should be reinstated. The pre-commit hook is the cheapest mechanism; the CI script is the most robust.

## Reinstating enforcement (optional, when needed)

If a future drift event makes it worth rebuilding the tooling, these are the shapes that worked before:

**Local pre-commit hook** — `.git/hooks/pre-commit` (PowerShell, no extension, must be `chmod +x` on Unix):

```powershell
$ErrorActionPreference = "Stop"
$files = git diff --cached --name-only --diff-filter=ACM | Where-Object { $_ -like "*.py" }
foreach ($file in $files) {
    $content = Get-Content $file -Raw -ErrorAction SilentlyContinue
    if (-not $content) { continue }
    $ok = ($content -match '(?s)^#!/usr/bin/env python3\s*\r?\n# -\*- coding: utf-8 -\*-\s*\r?\n"""') `
          -and ($content -match 'for enjoying')
    if (-not $ok) {
        Write-Host "header-check: $file is missing the header or 'for enjoying'. Fix before committing."
        exit 1
    }
}
exit 0
```

Because `.git/hooks/` is untracked per-clone, committing this hook requires either symlinking from a tracked `hooks/` directory plus a one-time `git config core.hooksPath hooks` setup per machine, or distributing via a script that copies the hook into place.

**CI-side check** — `tools/header_check.py`, runnable locally with `python tools/header_check.py` and in CI:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - tools/header_check.py header compliance auditor
-Walks every .py file and confirms each carries the For Enjoying header, For enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""
import sys
from pathlib import Path

SKIP_DIRS = {'.git', '_internal', '__pycache__', 'venv', '.venv'}

def is_compliant(p: Path) -> bool:
    try:
        lines = p.read_text(encoding='utf-8').splitlines()
    except (OSError, UnicodeDecodeError):
        return False
    if len(lines) < 5:
        return False
    return (
        lines[0] == '#!/usr/bin/env python3'
        and lines[1] == '# -*- coding: utf-8 -*-'
        and lines[2] == '"""'
        # Accept both the current prefix and the legacy "nodal playground" form;
        # legacy files get upgraded to the current form as they're touched
        and (lines[3].startswith('-Intricate - ') or lines[3].startswith('-Intricate nodal playground - '))
        and lines[4].rstrip().lower().endswith('for enjoying')
    )

def main() -> int:
    bad = [
        p for p in Path('.').rglob('*.py')
        if not any(part in SKIP_DIRS for part in p.parts)
        and not is_compliant(p)
    ]
    if bad:
        print(f'{len(bad)} non-compliant file(s):')
        for p in bad:
            print(f'  {p}')
        return 1
    print('All Python files carry the For Enjoying clause.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
```

## What still needs doing (or doesn't)

- **44 drifted files** are a decision, not a bug. Cleaning them up is a tinker-friendly task for a future session — low stakes, each file is one edit. Doing it all at once is a single-commit sweep; doing it as-touched spreads the diff over time.
- **Automated enforcement** can be reinstated any time the drift rate starts mattering. Until then the CLAUDE.md rule + AI-assisted authoring is doing the work.
- **The clause itself** stays — never reworded, never removed. It is the project's signature.

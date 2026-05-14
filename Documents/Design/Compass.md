# Compass

Compass is the family's way of locating itself. Every Single Shared Braincell app needs to find the asset vault — that's where signatures, icons, polaroid exports, and shared resources live — and historically each app has carried its own copy of "where is `_asset` on disk?" logic. The result was duplication, drift, and a tax every time a new machine, OneDrive layout, or repo rename came along. Compass replaces that with one mental model: **you tell git where you cloned the vault. Compass asks git. The apps stop asking the user.**

The whole design is built around reducing a two-step ceremony to one: clone the vault, launch the app. No setup wizard, no dialog, no per-app config. The app should already know where you put the vault by the time you see its first frame.

## Two-Layer Architecture

Compass is split into two pieces that live in different repos, by design:

```
┌─────────────────────────────────────────┬────────────────────────────────────────┐
│  the seed                               │  the compass                           │
│  utils/compass_seed.py inside each app  │  _asset/Intricate/Compass/ in the vault│
│  ~80 lines, almost never changes        │  evolves freely as the family grows    │
│  one job: locate _asset, return Path    │  registry, paths, brand, era, adapters │
└─────────────────────────────────────────┴────────────────────────────────────────┘
```

The seed bootstraps consciousness. Compass *is* the consciousness. An app without compass is still an app — it just operates on local fallbacks, knowing it's in a quieter, unconnected state. An app with compass operates as a full citizen of the family.

The seed lives inside each app because something has to find the vault before the vault can speak. Those ~80 lines are the irreducible bootstrap — they have to exist locally. The seed's payload is intentionally tiny and changes almost never: a host, a user, a repo name template, and the strategy ordering. Hebrews 13:8 — the same yesterday, today, and forever.

The full compass lives in the vault because the vault is the family's neutral hub. Anything else — putting compass inside Intricate, for instance — would force unrelated repos (like a poetry collection) to take an unwanted dependency on Intricate just to find their shared resources. The vault is the only repo every family member can safely depend on without creating loops.

## Identity — How the Seed Knows It Found the Right Repo

The vault's identity is a remote URL, not a folder name. Folder names drift (`_asset`, `assets`, `Asset Vault`), and in fact the on-disk folder name and the URL repo name diverge in practice: the vault is `_asset` on disk (sorts first in Explorer's alphabet) but `Asset-Repository` on GitHub. The seed tracks both separately. It reads `.git/config` directly as a text file — no git binary required — and matches the `[remote "origin"]` URL against a small canonical set built from pieces:

```python
GIT_HOST             = "github.com"
GIT_USER             = "agudmund"
URL_TEMPLATES        = ("https://{host}/{user}/{repo}.git", "git@{host}:{user}/{repo}.git")
VAULT_FOLDER_NAMES   = ("_asset",)            # what to look for on disk (strategy 5)
VAULT_REPO_URL_NAMES = ("Asset-Repository",)  # what .git/config will say (identity check)
```

Both URL forms are honoured so https and ssh-keyed clones both resolve. Each list is a tuple, not a single value, so a rename can land alongside the old name during a transition without breaking deployed seeds.

If the URL matches and the folder also contains `Intricate/Compass/`, presence is `HERE`. If the URL matches but `Intricate/Compass/` is missing — older vault snapshot, never updated — presence is `PARTIAL`, the path is still returned, and the apps fall back to their local behaviours while compass-full is unavailable. The folder is there; the brain isn't yet loaded.

## The Five Strategies

The seed tries strategies in order, escalating politely. The first one that returns a usable path wins; subsequent strategies never run.

**1. `SingleSharedBraincell_AssetVault` env var.** The override-first lever. Production deployments set this directly; on dev machines it's a self-populated cache after the first discovery. If the cached path no longer exists, the seed clears it and falls through — self-healing on relocation. This is also the cleanest production story: when the vault is on AWS, a local server, or any other non-sibling location, the deployment sets the env var explicitly and the rest of the strategies never fire.

**2. Sibling of the running app.** The 99% case. The seed walks up to its own repo's parent and looks for `_asset` next door. Three filesystem stats and it's home. The vast majority of dev-machine launches resolve here.

**3. Walk up the parent chain.** When the vault doesn't sit exactly as a sibling — perhaps it's one folder shallower or deeper than the running app — the seed widens the search by walking up `_PARENT_WALK_DEPTH` (currently 4) levels and checking each parent's children. Handles the cases where the family's filesystem layout isn't perfectly flat.

**4. OS indexer.** Deferred. Windows Search via COM, macOS `mdfind`, Linux `locate` — all routes to ask the OS "do you know where any folder named `_asset` lives?" Faster than strategy 5 when the index is warm, but each has its own ceremony to wire up properly. Placeholder returns empty; when the 1% of cases that fall to strategy 5 start costing real time, this is where to extend.

**5. Bounded recursive scan.** Last resort. Walks the user profile tree from `~/`, skipping the directories that never contain a vault (`node_modules`, `site-packages`, `AppData`, hidden dirs, etc.), with a hard wall-clock cap of `_FIND_TIMEOUT_SECS` (currently 30s). If the vault is on disk under the user profile, this finds it. If it's not — production case, vault deliberately on a network mount, etc. — the env var should have been set explicitly.

Each strategy returns either `(path, presence)` for a hit or `(None, None)` to pass on. The composite returns `(None, NOT_CLONED)` only if every strategy passes.

## Presence States

Compass doesn't think in terms of "found or not." It thinks in terms of **honest absence states**, each with its own meaning and downstream behaviour:

| State           | Meaning                                                  | Caller behaviour                         |
|-----------------|----------------------------------------------------------|------------------------------------------|
| `HERE`          | Vault is local and fully accessible                      | Normal operation                         |
| `PARTIAL`       | Vault is local but missing `Intricate/Compass/`          | Use local fallbacks; vault is an asset dump only |
| `GATED_BY_USER` | Vault found but `.git/config` is permission-denied       | Surface clearly: "owned by another user — re-clone or `takeown`" |
| `NOT_CLONED`    | Vault not found anywhere by any strategy                 | Quiet absence; fall back to repo-local `./Images` etc. |

The four states are deliberately distinct because each one gets a different InfoBar message and a different fallback path. Lumping them into "found or not" would erase information the user benefits from knowing — particularly the `GATED_BY_USER` case, which is rare but produces confusing symptoms if it's silently treated as "not cloned."

A fifth state, `REMOTE`, is planned for the future — when the vault doesn't have a local filesystem path at all (true cloud-only storage, S3 buckets, etc.). The seed stays filesystem-flavoured; `REMOTE` lives in compass-full's territory, where destination adapters can dispatch to local paths or cloud handles transparently.

## Persistence

When discovery succeeds via strategies 2–5, the seed writes the path back to the user environment via `setx` on Windows (in-process plus persistent across reboots) or via the in-process env var only on POSIX (shell rc files are the user's territory, and most non-Windows deployments will set the env var explicitly anyway). The next launch hits strategy 1 immediately and skips all the work.

If the persisted path stops resolving — vault moved, drive remapped, OneDrive desktop swapped for local desktop — the seed clears the cache implicitly (the existence check fails) and re-discovers. No manual intervention. The env var heals itself.

## Current Status

The seed is implemented at `utils/compass_seed.py`. It exposes one public function:

```python
from utils.compass_seed import find_asset_vault, Presence

path, presence = find_asset_vault()
if presence == Presence.HERE:
    # full operation
elif presence == Presence.PARTIAL:
    # vault present but compass module missing
elif presence == Presence.GATED_BY_USER:
    # specific error path
else:
    # NOT_CLONED — quiet fallback
```

Not yet wired into Intricate's startup. That happens in the next step alongside the first compass-full skeleton in `_asset/Intricate/Compass/`.

## Forward Path

The work is staged so each step is observable in isolation:

1. **Seed in Intricate** *(complete)* — `utils/compass_seed.py`, ready to be called.
2. **Compass-full skeleton in the vault** — `_asset/Intricate/Compass/` with `registry.py` (known repos), `paths.py` (logical names), `__init__.py` (public API). Wire Intricate to load it via the seed.
3. **Majestic adopts compass** — replace `_get_majestic_images_dir` with `compass.paths.majestic_editor_polaroid_dir()`. Editor polaroid routes through compass; chat polaroid follows shortly after.
4. **Triple-destination support** — destinations become a list, adapters dispatch to local Path or cloud handle, polaroid button stops caring whether there's one folder or three.
5. **Other family apps onboard** — poetry collection, future apps, each carrying its own copy of the seed (`~80` lines, copy-paste, no install ceremony). Compass-full evolves in the vault; every app benefits without redeployment.

The vault's role is sharpening alongside this work: it's the family's nervous system, not a file dump. Curated content (icons, signatures, fonts, polaroid exports that have graduated from local drafts) lives there. Scratch space stays in each project. Compass codifies that boundary by making the vault the place where the family learns what its current vocabulary is — `paths.images_subdir` is `"Snips"` today, may be `"Glory"` in five years, lives in one file in the vault, every app reflects the rename on next launch.

## Related

- [Polaroids.md](Polaroids.md) — the first concrete consumer of compass's path resolution
- [AWS Integration.md](AWS Integration.md) — the production-vault case that motivates the env-var-first strategy ordering
- Asset Vault — `$SingleSharedBraincell_AssetVault`, the env var compass reads and writes
- Pretty Widgets — sibling shared package, intentionally Qt-only; compass is what cross-family code looks like when it's not Qt-flavoured

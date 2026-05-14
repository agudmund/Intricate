#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/compass_seed.py bootstrap locator for the asset vault
-she remembers nothing, except where to find the one who remembers everything
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple


# ─── Identity ────────────────────────────────────────────────────────────────
# The vault's name, decomposed into pieces.  When something migrates — new
# host, account rename, repo rename — one constant changes here and every
# family app picks up the new identity on next launch.  These change rarely
# by design (Hebrews 13:8 — the same yesterday, today, and forever).
#
# Folder name and URL repo name are tracked separately because they
# diverge in practice: the vault folder on disk is "_asset" (sorts first
# in Explorer's alphabet) while the GitHub repo is "Asset-Repository".

GIT_HOST              = "github.com"
GIT_USER              = "agudmund"
URL_TEMPLATES         = (
    "https://{host}/{user}/{repo}.git",
    "git@{host}:{user}/{repo}.git",
)
VAULT_FOLDER_NAMES    = ("_asset",)            # on-disk names — strategy 5 filters by these
VAULT_REPO_URL_NAMES  = ("Asset-Repository",)  # URL forms — .git/config matches these

ENV_VAR_NAME          = "SingleSharedBraincell_AssetVault"


def _expected_remote_urls() -> set:
    """All canonical URL forms the vault's .git/config could carry."""
    return {
        template.format(host=GIT_HOST, user=GIT_USER, repo=repo)
        for template in URL_TEMPLATES
        for repo in VAULT_REPO_URL_NAMES
    }


# ─── Presence — four honest states ───────────────────────────────────────────
# The seed never panics; it escalates politely and reports back.  Each state
# carries enough information for the InfoBar to phrase itself without the
# caller needing to know how the discovery went.

class Presence(Enum):
    HERE          = "here"           # vault is local and accessible
    NOT_CLONED    = "not_cloned"     # vault is not present anywhere we can find
    GATED_BY_USER = "gated_by_user"  # vault is present but owned by another OS user
    PARTIAL       = "partial"        # vault is present but missing Intricate/Compass/

    @property
    def is_resolved(self) -> bool:
        """True when a usable vault path is attached to this presence."""
        return self in (Presence.HERE, Presence.PARTIAL)


# ─── Search budget ───────────────────────────────────────────────────────────
# Bounded effort, no surprises.  Strategy 3 walks up this many parents from
# the running file; strategy 5 caps total wall time so startup stays snappy.

_PARENT_WALK_DEPTH = 4
_FIND_TIMEOUT_SECS = 30

_SCAN_SKIP_DIRS = frozenset({
    "node_modules", "site-packages", "__pycache__", "AppData",
    "Windows", "Program Files", "Program Files (x86)",
})


# ─── Identity check — is this folder the vault? ──────────────────────────────
# Reads .git/config as a text file so no git binary is required.  Returns
# the URL or None.  PermissionError propagates up so callers can tag the
# candidate as gated rather than missing.

def _read_remote_url(git_config_path: Path) -> Optional[str]:
    in_origin = False
    try:
        with git_config_path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("[remote ") and "origin" in stripped:
                    in_origin = True
                    continue
                if in_origin and stripped.startswith("["):
                    break  # left the origin section without finding url
                if in_origin and stripped.startswith("url"):
                    _, _, val = stripped.partition("=")
                    return val.strip()
    except PermissionError:
        raise
    except OSError:
        return None
    return None


def _classify(candidate: Path) -> Presence:
    """Classify a candidate folder's presence state.

    HERE          — vault confirmed, Intricate/Compass/ exists
    PARTIAL       — vault confirmed but compass module missing
    GATED_BY_USER — folder exists but .git/config not readable
    NOT_CLONED    — folder doesn't match the vault's identity
    """
    git_config = candidate / ".git" / "config"
    if not git_config.exists():
        return Presence.NOT_CLONED
    try:
        url = _read_remote_url(git_config)
    except PermissionError:
        return Presence.GATED_BY_USER
    if url not in _expected_remote_urls():
        return Presence.NOT_CLONED
    if not (candidate / "Intricate" / "Compass").exists():
        return Presence.PARTIAL
    return Presence.HERE


# ─── Strategy 1 — env var ────────────────────────────────────────────────────
# Override-first.  Production sets this directly; discovery sets it on dev
# machines once.  If the cached path no longer exists, fall through and
# re-discover — self-healing on relocation.

def _try_env_var() -> Tuple[Optional[Path], Optional[Presence]]:
    cached = os.environ.get(ENV_VAR_NAME, "").strip()
    if not cached:
        return None, None
    path = Path(cached)
    if not path.exists():
        return None, None
    return path, _classify(path)


# ─── Strategies 2 + 3 — sibling-first, then walk up ──────────────────────────
# The 99% case lives in strategy 2 — the vault is the running app's sibling.
# Strategy 3 widens up to _PARENT_WALK_DEPTH levels for less typical layouts.

def _try_sibling_walk() -> Tuple[Optional[Path], Optional[Presence]]:
    here = Path(__file__).resolve()
    seen: set = set()
    gated: Optional[Path] = None

    for depth, parent in enumerate(here.parents):
        if depth >= _PARENT_WALK_DEPTH:
            break
        try:
            children = [c for c in parent.iterdir() if c.is_dir()]
        except (PermissionError, OSError):
            continue
        for candidate in children:
            if candidate in seen:
                continue
            seen.add(candidate)
            presence = _classify(candidate)
            if presence.is_resolved:
                return candidate, presence
            if presence == Presence.GATED_BY_USER:
                gated = candidate
    if gated is not None:
        return gated, Presence.GATED_BY_USER
    return None, None


# ─── Strategy 4 — OS indexer (deferred) ──────────────────────────────────────
# Windows Search COM and macOS mdfind have their own ceremony; sibling-walk
# catches the 99% case and bounded scan catches the rest.  Wire this in
# when the 1% starts costing real time.

def _try_os_indexer() -> Tuple[Optional[Path], Optional[Presence]]:
    return None, None  # placeholder for a future revision


# ─── Strategy 5 — bounded recursive scan ─────────────────────────────────────
# Last resort.  Walks the user profile tree with a wall-clock cap, skipping
# the directories that never contain the vault.  Honest about its cost:
# if this fires often we should add strategy 4 properly.

def _try_recursive_scan() -> Tuple[Optional[Path], Optional[Presence]]:
    root = Path.home()
    deadline = time.monotonic() + _FIND_TIMEOUT_SECS
    targets = set(VAULT_FOLDER_NAMES)
    gated: Optional[Path] = None
    try:
        for dirpath, dirnames, _ in os.walk(root):
            if time.monotonic() > deadline:
                break
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and d not in _SCAN_SKIP_DIRS
            ]
            for d in dirnames:
                if d not in targets:
                    continue
                candidate = Path(dirpath) / d
                presence = _classify(candidate)
                if presence.is_resolved:
                    return candidate, presence
                if presence == Presence.GATED_BY_USER:
                    gated = candidate
    except (PermissionError, OSError):
        pass
    if gated is not None:
        return gated, Presence.GATED_BY_USER
    return None, None


# ─── Persistence — make the discovery stick ──────────────────────────────────
# Write to both the current process (immediate) and the user environment
# (survives reboots).  setx on Windows; POSIX falls back to in-process only
# since shell rc files are the user's territory.

def _persist_env_var(path: Path) -> None:
    str_path = str(path)
    os.environ[ENV_VAR_NAME] = str_path

    if sys.platform == "win32":
        try:
            subprocess.run(
                ["setx", ENV_VAR_NAME, str_path],
                check=False,
                capture_output=True,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass  # setx unavailable is non-fatal; the in-process var still works


# ─── Public entry point ──────────────────────────────────────────────────────
# The only function callers need.  Strategies fire in order; the first one
# that returns a resolved path persists it so subsequent launches skip
# straight to strategy 1.  presence is always populated; path is None
# only when presence is NOT_CLONED.

def find_asset_vault() -> Tuple[Optional[Path], Presence]:
    """Locate the asset vault on this machine.

    Strategies, in order:
        1. SingleSharedBraincell_AssetVault env var (production override + cache)
        2. Sibling of the running app
        3. Walk up parents looking for a sibling at each level
        4. OS indexer (deferred — placeholder returning empty)
        5. Bounded recursive scan from the user profile

    On first successful discovery (strategies 2-5), the env var is set so
    subsequent launches skip straight to strategy 1.
    """
    for strategy in (_try_env_var, _try_sibling_walk, _try_os_indexer, _try_recursive_scan):
        path, presence = strategy()
        if path is not None and presence is not None:
            if presence.is_resolved and strategy is not _try_env_var:
                _persist_env_var(path)
            return path, presence

    return None, Presence.NOT_CLONED

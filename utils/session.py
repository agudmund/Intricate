#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/session.py session persistence
-Path resolution, migration, save/load and validation for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import os
import sys
import hashlib
import json
from pathlib import Path
from typing import List

try:
    from send2trash import send2trash as _send_to_trash
except ImportError:
    _send_to_trash = None

from pretty_widgets.utils.logger import setup_logger
from utils.helpers import ensure_dir

logger = setup_logger("session")

# The canonical session file extension.  It's just JSON inside, but a custom
# extension sidesteps autotools and .gitignore rules that blanket-exclude *.json.
SESSION_EXT = ".intricate"


# ═════════════════════════════════════════════════════════════════════════════
# Path helpers
# ═════════════════════════════════════════════════════════════════════════════

def session_path(project_name: str) -> Path | None:
    """Return the session file path for a project folder name, or None if empty."""
    if not project_name:
        return None
    return Path.home() / "Desktop" / project_name / "Documents" / "data" / f"session{SESSION_EXT}"


def project_root_from_session(path: Path) -> Path:
    """Derive the project root (~/Desktop/{project}/) from a session.json path."""
    return path.parent.parent.parent


def migrate_legacy_session(path: Path, project_root: Path) -> None:
    """Migrate old session layouts to the current convention.

    Handles two legacy layouts:
      1. session.json at project root  → Documents/data/session.intricate
      2. session.json in Documents/data → session.intricate  (extension rename)
    """
    # Legacy layout 1: root-level session.json → Documents/data/
    old_root = project_root / "session.json"
    if old_root.exists() and not path.exists():
        ensure_dir(path.parent)
        try:
            old_root.rename(path)
            logger.info(f"migrated session.json -> {path.relative_to(project_root)}")
        except OSError as e:
            logger.warning(f"session migration failed: {e}")

        old_backup = project_root / "backup"
        new_backup = path.parent / "backup"
        if old_backup.exists() and old_backup.is_dir() and not new_backup.exists():
            try:
                old_backup.rename(new_backup)
                logger.info("migrated backup/ -> Documents/data/backup/")
            except OSError as e:
                logger.warning(f"backup migration failed: {e}")

    # Legacy layout 2: session.json in Documents/data/ → .intricate extension
    old_json = path.with_suffix(".json")
    if old_json.exists() and not path.exists():
        try:
            old_json.rename(path)
            logger.info(f"migrated {old_json.name} -> {path.name}")
        except OSError as e:
            logger.warning(f"extension migration failed: {e}")
        # Also rename backup files
        backup_dir = path.parent / "backup"
        if backup_dir.exists():
            for old_bak in backup_dir.glob("session*_*.json"):
                new_bak = old_bak.with_suffix(SESSION_EXT)
                try:
                    old_bak.rename(new_bak)
                except OSError:
                    pass


def enter_project(path: Path) -> Path:
    """Run migration, chdir to the project root, and return it.

    Returns the project_root so the caller can pass it on to scene methods.
    """
    project_root = project_root_from_session(path)
    migrate_legacy_session(path, project_root)

    if project_root.exists():
        try:
            os.chdir(str(project_root))
        except OSError:
            pass

    return project_root


# ═════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═════════════════════════════════════════════════════════════════════════════

def _session_checksum(data: dict) -> str:
    uuids = sorted(n.get("uuid", "") for n in data.get("nodes", []))
    vp = data.get("viewport", {})
    payload = json.dumps({"uuids": uuids, "viewport": vp}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _get_sessions_dir() -> Path:
    """
    Get the absolute path to the sessions directory.

    Works correctly regardless of where the process was launched from.
    Handles both normal script execution and PyInstaller bundles.
    """
    if hasattr(sys, '_MEIPASS'):
        base_path = Path(sys.executable).parent
    else:
        base_path = Path(__file__).resolve().parent.parent

    return base_path / "sessions"


def _rotate_session(filepath: str):
    """
    3-slot save rotation — mirrors build.py's rotateAndArchive and logger.py's _rotate_logs.
    On each save: archive → recycle bin, previous → archive, current → previous.
    Backup slots are kept in ./sessions/backup/ — only the live file stays in ./sessions/.
    """
    current    = Path(filepath)
    backup_dir = current.parent / "backup"
    ensure_dir(backup_dir)

    previous = backup_dir / (current.stem + "_previous" + SESSION_EXT)
    archive  = backup_dir / (current.stem + "_archive" + SESSION_EXT)

    def _trash(path: Path):
        """Send to recycle bin; fall back to permanent delete if send2trash is unavailable."""
        if _send_to_trash:
            try:
                _send_to_trash(str(path))
                return
            except Exception:
                pass
        path.unlink(missing_ok=True)

    try:
        if archive.exists():
            _trash(archive)
        if previous.exists():
            previous.rename(archive)
        if current.exists():
            current.rename(previous)
    except Exception:
        pass  # Rotation failure is non-fatal — save continues regardless


# ═════════════════════════════════════════════════════════════════════════════
# Node sanitisation — runs before from_dict() sees the data
# ═════════════════════════════════════════════════════════════════════════════

_KNOWN_TYPES = frozenset({
    "warm", "about", "bezier", "health", "claude", "claude_response",
    "text", "cushions", "code", "log", "image", "video", "sequence",
    "tree", "info", "git", "audio", "merge", "audio_hold", "palette",
    "sticker", "value", "perf", "claude_info", "fbx", "session",
    "joy_stats", "readme",
})

_PATH_FIELDS = ("source_path", "project_path", "folder_path")

_GEOM_DEFAULTS = {"x": 0.0, "y": 0.0, "width": 300.0, "height": 200.0, "z_value": 0.0}


def _sanitise_node(node: dict, index: int, issues: list) -> dict | None:
    """
    Sanitise a single node dict in-place. Returns None to drop the node.
    Appends human-readable warnings to *issues*.
    """
    import math
    import re
    import uuid as _uuid

    tag = f"node[{index}]"

    # ── node_type whitelist ───────────────────────────────────────────────
    ntype = node.get("node_type", "")
    if ntype not in _KNOWN_TYPES:
        issues.append(f"{tag} unknown node_type '{ntype}' — dropped")
        return None

    # ── UUID — alphanumeric + hyphens only ────────────────────────────────
    raw_uuid = str(node.get("uuid", ""))
    clean_uuid = re.sub(r'[^a-zA-Z0-9_-]', '', raw_uuid)
    if not clean_uuid:
        clean_uuid = _uuid.uuid4().hex
        issues.append(f"{tag} invalid uuid — assigned fresh: {clean_uuid[:8]}")
    if clean_uuid != raw_uuid:
        issues.append(f"{tag} uuid sanitised: {raw_uuid[:16]!r} → {clean_uuid[:8]}")
    node["uuid"] = clean_uuid

    # ── Geometry — safe float, reject NaN/Inf, clamp dimensions ──────────
    for field, default in _GEOM_DEFAULTS.items():
        raw = node.get(field, default)
        try:
            val = float(raw)
        except (TypeError, ValueError):
            issues.append(f"{tag} {field} not numeric ({raw!r}) — using default {default}")
            val = default
        if math.isnan(val) or math.isinf(val):
            issues.append(f"{tag} {field} is NaN/Inf — using default {default}")
            val = default
        node[field] = val

    # Clamp width/height to sane bounds
    for dim in ("width", "height"):
        node[dim] = max(10.0, min(node[dim], 10_000.0))

    # ── String fields — truncate to prevent memory bombs ─────────────────
    title = node.get("title", "")
    if isinstance(title, str) and len(title) > 500:
        node["title"] = title[:500]
        issues.append(f"{tag} title truncated to 500 chars")

    emoji = node.get("emoji", "")
    if isinstance(emoji, str) and len(emoji) > 32:
        node["emoji"] = emoji[:32]
        issues.append(f"{tag} emoji truncated to 32 chars")

    # ── Path fields — reject null bytes ──────────────────────────────────
    for pf in _PATH_FIELDS:
        pval = node.get(pf)
        if isinstance(pval, str) and '\x00' in pval:
            node[pf] = ""
            issues.append(f"{tag} {pf} contained null bytes — cleared")

    return node


# ═════════════════════════════════════════════════════════════════════════════
# SessionManager
# ═════════════════════════════════════════════════════════════════════════════

class SessionManager:
    """Manage persistence of nodal graph sessions to/from JSON files.
    Handles session creation, loading, saving, and listing with proper error handling.
    """

    SESSIONS_DIR = "sessions"
    VERSION = "1.0"

    @staticmethod
    def get_available_sessions() -> List[str]:
        """Retrieve list of all saved session file names from the sessions directory.

        Returns:
            List of session names (without .json extension)
        """
        sessions_path = _get_sessions_dir()

        if not sessions_path.exists():
            logger.warning(f"Sessions directory not found at {sessions_path}")
            return []

        # Accept both .intricate and legacy .json files in the sessions dir
        session_files = sorted(
            f for f in sessions_path.iterdir()
            if f.suffix in (SESSION_EXT, ".json") and f.is_file()
        )
        return [f.stem for f in session_files]

    @staticmethod
    def get_session_filename(display_name: str) -> str:
        """Get the full absolute filepath for a session by its display name."""
        sessions_dir = _get_sessions_dir()
        return str(sessions_dir / f"{display_name}{SESSION_EXT}")

    @staticmethod
    def save_session(filepath: str, data: dict):
        """Drive the data to the warehouse and save as JSON."""
        try:
            # Ensure the directory exists
            ensure_dir(Path(filepath).parent)

            # 3-slot rollover before writing — matches build.py / logger.py rotation pattern
            _rotate_session(filepath)
            data["checksum"] = _session_checksum(data)

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Session saved successfully to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save session: {e}")

    @staticmethod
    def get_session_data(filepath: str) -> dict | None:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Sanitise structure
            if not isinstance(data.get("nodes"), list):
                data["nodes"] = []
            if not isinstance(data.get("connections"), list):
                data["connections"] = []
            if not isinstance(data.get("viewport"), dict):
                data["viewport"] = {}

            stored = data.pop("checksum", None)
            if stored is None:
                logger.warning(f"[SESSION] No checksum — '{Path(filepath).stem}' is a legacy file, loading anyway")
            elif stored != _session_checksum(data):
                logger.warning(f"[SESSION] Checksum mismatch — '{Path(filepath).stem}' rejected at the gate")
                return None

            # Deduplicate nodes by UUID
            seen_uuids = set()
            clean_nodes = []
            for node in data["nodes"]:
                uuid = node.get("uuid")
                if uuid and uuid not in seen_uuids:
                    seen_uuids.add(uuid)
                    clean_nodes.append(node)
                elif uuid:
                    logger.warning(f"[SESSION] Duplicate UUID removed on load: {uuid[:8]}")
            data["nodes"] = clean_nodes

            # Validate and log any anomalies
            return SessionManager.validate_session_data(data, filepath)

        except Exception as e:
            logger.warning(f"[SESSION] Failed to load {filepath}: {e}")
            return None

    @staticmethod
    def validate_session_data(data: dict, filepath: str) -> dict:
        """
        Validate, sanitise, and report session data anomalies.
        Runs _sanitise_node() on every node dict before from_dict() sees it.
        Drops nodes that can't be salvaged, logs everything suspicious.
        """
        name = Path(filepath).stem

        issues = []

        # Structure checks
        if not isinstance(data.get("nodes"), list):
            issues.append("nodes key missing or not a list")
            data["nodes"] = []
        if not isinstance(data.get("connections"), list):
            issues.append("connections key missing or not a list")
            data["connections"] = []
        if not isinstance(data.get("viewport"), dict):
            issues.append("viewport key missing or not a dict")
            data["viewport"] = {}

        # Per-node sanitisation + dedup
        seen_uuids = set()
        clean_nodes = []
        for i, node in enumerate(data["nodes"]):
            if not isinstance(node, dict):
                issues.append(f"node[{i}] is not a dict — dropped")
                continue

            sanitised = _sanitise_node(node, i, issues)
            if sanitised is None:
                continue

            uuid = sanitised.get("uuid")
            if not uuid:
                issues.append(f"node[{i}] has no uuid after sanitisation — dropped")
                continue
            if uuid in seen_uuids:
                issues.append(f"node[{i}] duplicate uuid {uuid[:8]} — dropped")
                continue

            seen_uuids.add(uuid)
            clean_nodes.append(sanitised)

        data["nodes"] = clean_nodes

        # Connection integrity checks
        for i, conn in enumerate(data["connections"]):
            start = conn.get("start_uuid")
            end = conn.get("end_uuid")
            if start and start not in seen_uuids:
                issues.append(f"connection[{i}] start_uuid {start[:8]} not found in nodes")
            if end and end not in seen_uuids:
                issues.append(f"connection[{i}] end_uuid {end[:8]} not found in nodes")

        if issues:
            logger.warning(f"[SESSION VALIDATOR] '{name}' — {len(issues)} issue(s) found:")
            for issue in issues:
                logger.warning(f"  {issue}")
        else:
            logger.debug(f"[SESSION VALIDATOR] '{name}' — clean")

        return data

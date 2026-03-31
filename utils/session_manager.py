#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Cozy times nodal playground - session_manager.py session persistence
-Save and load nodal graphs from JSON session files for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import os
import sys
import hashlib, json
from pathlib import Path
from typing import List, Optional

try:
    from send2trash import send2trash as _send_to_trash
except ImportError:
    _send_to_trash = None

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsView

from utils.logger import setup_logger
import uuid as uuid_module

logger = setup_logger()

def _session_checksum(data: dict) -> str:
    uuids = sorted(n.get("uuid","") for n in data.get("nodes", []))
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
    backup_dir.mkdir(exist_ok=True)

    previous = backup_dir / (current.stem + "_previous.json")
    archive  = backup_dir / (current.stem + "_archive.json")

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

        session_files = sorted(sessions_path.glob("*.json"))
        return [f.stem for f in session_files]

    @staticmethod
    def get_session_filename(display_name: str) -> str:
        """Get the full absolute filepath for a session by its display name."""
        sessions_dir = _get_sessions_dir()
        return str(sessions_dir / f"{display_name}.json")

    @staticmethod
    def save_session(filepath: str, data: dict):
        """Drive the data to the warehouse and save as JSON."""
        try:
            # Ensure the directory exists
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)

            # 3-slot rollover before writing — matches build.py / logger.py rotation pattern
            _rotate_session(filepath)
            data["checksum"] = _session_checksum(data)

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"✅ Session saved successfully to {filepath}")
        except Exception as e:
            logger.error(f"❌ Failed to save session: {e}")
        

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
        Validate and report session data anomalies without rejecting the session.
        Logs warnings for anything suspicious so patterns can be identified.
        Sanitises only the minimum needed to prevent crashes — never silently drops data.
        """
        from utils.logger import setup_logger
        logger = setup_logger()
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

        # Node integrity checks
        seen_uuids = set()
        for i, node in enumerate(data["nodes"]):
            uuid = node.get("uuid")
            node_type = node.get("node_type", "unknown")
            title = node.get("title", "untitled")

            if not uuid:
                issues.append(f"node[{i}] '{title}' ({node_type}) has no uuid")
            elif uuid in seen_uuids:
                issues.append(f"node[{i}] '{title}' ({node_type}) has duplicate uuid: {uuid[:8]}")
            else:
                seen_uuids.add(uuid)

            for field in ("x", "y", "width", "height"):
                val = node.get(field)
                if val is None:
                    issues.append(f"node[{i}] '{title}' missing field: {field}")
                elif not isinstance(val, (int, float)):
                    issues.append(f"node[{i}] '{title}' field {field} is not numeric: {val!r}")

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
                logger.warning(f"  ⚠ {issue}")
        else:
            logger.debug(f"[SESSION VALIDATOR] '{name}' — clean ✅")

        return data
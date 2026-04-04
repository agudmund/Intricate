#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/session.py session file helpers
-Path resolution and legacy migration for session persistence for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import os
from pathlib import Path
from utils.logger import setup_logger
from utils.helpers import ensure_dir

logger = setup_logger("session")


def session_path(project_name: str) -> Path | None:
    """Return the session.json path for a project folder name, or None if empty."""
    if not project_name:
        return None
    return Path.home() / "Desktop" / project_name / "Documents" / "data" / "session.json"


def project_root_from_session(path: Path) -> Path:
    """Derive the project root (~/Desktop/{project}/) from a session.json path."""
    return path.parent.parent.parent


def migrate_legacy_session(path: Path, project_root: Path) -> None:
    """Move a root-level session.json and backup/ into Documents/data/ if needed.

    Old layout kept session.json at the project root.  This migrates it to
    Documents/data/session.json so the project root stays clean.
    """
    old_session = project_root / "session.json"
    if old_session.exists() and not path.exists():
        ensure_dir(path.parent)
        try:
            old_session.rename(path)
            logger.info(f"migrated session.json -> {path.relative_to(project_root)}")
        except OSError as e:
            logger.warning(f"session migration failed: {e}")

        # Move the old backup/ folder too if it exists
        old_backup = project_root / "backup"
        new_backup = path.parent / "backup"
        if old_backup.exists() and old_backup.is_dir() and not new_backup.exists():
            try:
                old_backup.rename(new_backup)
                logger.info("migrated backup/ -> Documents/data/backup/")
            except OSError as e:
                logger.warning(f"backup migration failed: {e}")


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

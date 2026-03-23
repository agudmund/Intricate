#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Cozy times nodal playground - logger.py its really just a fancypants print statement wrapper
-3-slot startup rotation with recycle bin safety net, matching build.py's rollover methodology for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import os
import sys
import logging
from pathlib import Path

# TRACE (level 5) sits below DEBUG — file-only, never reaches the console.
# Use for hyper-verbose diagnostics (paint cycles, frame-level events, etc.)
TRACE = 5
logging.addLevelName(TRACE, "TRACE")


def get_base_dir() -> Path:
    """
    Returns the absolute path to the directory containing the executable or script.
    Works for standard Python execution and PyInstaller bundles.
    """
    if hasattr(sys, '_MEIPASS'):
        # Running as a PyInstaller EXE
        return Path(sys.executable).parent
    # Running as a normal script
    return Path(__file__).resolve().parent.parent


def _rotate_logs(logs_dir: Path):
    """
    3-slot startup rotation — mirrors build.py's rotateAndArchive pattern.
    On each app launch: archive → recycle bin, previous → archive, current → previous.
    A clean nodal.log is always waiting for the new session.
    """
    current  = logs_dir / "nodal.log"
    previous = logs_dir / "nodal_previous.log"
    archive  = logs_dir / "nodal_archive.log"

    try:
        from send2trash import send2trash as _send_to_trash
    except ImportError:
        _send_to_trash = None

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
        pass  # Rotation failure is non-fatal — log startup continues regardless


def setup_logger(name: str = "nodal") -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.DEBUG)

    # 1. Setup Paths with Environment Variable Priority
    # Check for $COZYLOG first. If it's not set, use the smart fallback.
    cozy_env = os.environ.get("COZYLOG")

    if cozy_env:
        logs_dir = Path(cozy_env)
    else:
        logs_dir = get_base_dir() / "logs"

    try:
        logs_dir.mkdir(exist_ok=True, parents=True)
    except Exception:
        # Emergency fallback if the chosen directory isn't writable
        logs_dir = Path(os.path.expanduser("~")) / ".nodal_logs"
        logs_dir.mkdir(exist_ok=True)

    # 2. Startup Rotation — 3-slot recycle bin pattern matching build.py
    _rotate_logs(logs_dir)

    log_file = logs_dir / "nodal.log"

    # 3. Formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 4. Stream Handler (Console)
    # We check if sys.stdout exists (safety for pythonw)
    if sys.stdout is not None:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(logging.INFO)
        logger.addHandler(stream_handler)

    # 5. File Handler — plain, rotation is handled manually at startup
    file_handler = logging.FileHandler(log_file, encoding='utf-8')  # Ensures the Sparkle ✨ is saved correctly to disk
    file_handler.setFormatter(formatter)
    file_handler.setLevel(TRACE)
    logger.addHandler(file_handler)

    return logger


def set_log_level(debug: bool, trace: bool = False):
    """Switch console verbosity: INFO (default) → DEBUG (--debug) → TRACE (--trace).
    FileHandlers are always kept at TRACE so sub-DEBUG diagnostics are
    preserved in nodal.log without ever surfacing in the console unless --trace is passed.
    """
    logger = logging.getLogger("nodal")
    if trace:
        console_level = TRACE
        logger_level  = TRACE
    elif debug:
        console_level = logging.DEBUG
        logger_level  = TRACE
    else:
        console_level = logging.INFO
        logger_level  = logging.INFO

    logger.setLevel(logger_level)
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setLevel(console_level)

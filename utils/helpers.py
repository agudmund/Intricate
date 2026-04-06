#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/helpers.py common helper utilities
-Shared helpers that keep the codebase consistent and tidy for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import os
import shutil
from pathlib import Path
from pretty_widgets.utils.logger import setup_logger

logger = setup_logger("helpers")


# ── __init__.py template ─────────────────────────────────────────────────────
_INIT_TEMPLATE = (
    '#!/usr/bin/env python3\n'
    '# -*- coding: utf-8 -*-\n'
    '"""\n'
    '-Intricate nodal playground - {path}/__init__.py package initializer\n'
    '-{name} package initializer for enjoying\n'
    '-Built using a single shared braincell by Yours Truly and various Intelligences\n'
    '"""\n'
)


def ensure_dir(path: str | Path) -> bool:
    """Create a directory (and parents) if it doesn't already exist.

    Returns True if the directory is usable after the call, False on failure.
    """
    path = Path(path)
    try:
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            logger.info(f"🌱 Created directory: {path}")
        else:
            logger.log(5, f"✓ Directory already exists: {path}")
        return True
    except OSError as e:
        logger.warning(f"⚠ Failed to create directory: {path} — {e}")
        return False


def ensure_init(path: str | Path, project_root: str | Path | None = None) -> bool:
    """Create __init__.py with the standard header if missing.

    Args:
        path:         The directory that should contain __init__.py.
        project_root: Optional root for deriving the relative path in the header.
                      Falls back to using the directory name alone.

    Returns True if __init__.py exists after the call, False on failure.
    """
    path = Path(path)
    init_file = path / "__init__.py"
    if init_file.exists():
        logger.info(f"✓ __init__.py already in {path}")
        return True
    try:
        rel  = path.relative_to(project_root) if project_root else Path(path.name)
        name = rel.parts[-1].capitalize() if rel.parts else path.name.capitalize()
        init_file.write_text(
            _INIT_TEMPLATE.format(path=rel.as_posix(), name=name),
            encoding="utf-8",
        )
        logger.info(f"🌱 Created __init__.py in {path}")
        return True
    except OSError as e:
        logger.warning(f"⚠ Failed to create __init__.py in {path} — {e}")
        return False


def ensure_init_tree(root: str | Path) -> int:
    """Walk a project tree and create missing __init__.py in Python package folders.

    A subfolder is treated as a library package when it contains .py files
    but no main.py.  Folders with main.py are standalone entry points and
    are left alone.

    Returns the number of __init__.py files created.
    """
    root = Path(root)
    skip = {".git", "__pycache__"}
    created = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
        py_files = [f for f in filenames if f.endswith(".py")]
        if not py_files or "main.py" in py_files or "__init__.py" in py_files:
            continue
        if ensure_init(dirpath, project_root=root):
            created += 1
    return created


def clean_pycache(root: str | Path | None = None) -> int:
    """Remove all __pycache__ folders and .pyc files under root.

    Args:
        root: Directory to clean. Defaults to the project root
              (parent of utils/).

    Returns the number of __pycache__ directories removed.
    """
    if root is None:
        root = Path(__file__).resolve().parent.parent
    root = Path(root)
    cleaned = 0
    try:
        for item in root.rglob("__pycache__"):
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
                logger.info(f"🧹 Removed: {item}")
                cleaned += 1
        for item in root.rglob("*.pyc"):
            item.unlink(missing_ok=True)
    except Exception:
        pass
    return cleaned


def snapshot_node(node, filename: str | None = None, scale: int = 2) -> Path | None:
    """Render a QGraphicsItem to a transparent PNG.

    Args:
        node:     Any QGraphicsItem (BaseNode subclass) currently in a scene.
        filename: Output filename (without directory). Defaults to node title + .png.
        scale:    Render multiplier for crisp output (default 2×).

    Returns the Path of the saved PNG, or None on failure.
    """
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter
    import pretty_widgets.utils.settings as _s

    scene = node.scene()
    if not scene:
        return None

    scene_rect = node.mapRectToScene(node.boundingRect())
    w = int(scene_rect.width()  * scale)
    h = int(scene_rect.height() * scale)
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)

    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing)
    scene.render(painter, QRectF(0, 0, w, h), scene_rect)
    painter.end()

    out_dir = Path(_s.get("shared", "images_dir", default="."))
    ensure_dir(out_dir)
    title = filename or (getattr(node.data, 'title', 'Node').strip() or "Node") + ".png"
    if not title.lower().endswith(".png"):
        title += ".png"
    path = out_dir / title
    img.save(str(path))
    logger.info(f"📸 Snapshot saved: {path}")
    return path


def _lowest_about_label(view) -> str:
    """Return the label of the AboutNode with the highest y (furthest down) visible in the viewport."""
    from nodes.AboutNode import AboutNode

    scene = view.scene()
    if not scene:
        return ""
    vp_rect = view.mapToScene(view.viewport().rect()).boundingRect()
    best_y = -float("inf")
    best_label = ""
    for item in scene.items():
        if isinstance(item, AboutNode) and vp_rect.intersects(item.sceneBoundingRect()):
            y = item.scenePos().y()
            if y > best_y:
                best_y = y
                best_label = getattr(item.data, "label", "")
    return best_label.strip()


def _sanitize(text: str, max_len: int = 40) -> str:
    """Strip a string down to filesystem-safe characters."""
    import re
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', text)
    text = text.strip(". ")
    return text[:max_len] if text else ""


def snapshot_viewport(view, session_name: str = "", scale: int = 2) -> Path | None:
    """Render the current viewport to a transparent PNG — nodes included, background removed.

    Captures exactly what the view shows at the current pan/zoom, but with a
    fully transparent background instead of Theme.backDrop. This gives a clean
    alpha channel suitable for compositing or chroma-free workflows.

    Filename convention:
        {timestamp}_{session}_{lowest-about-label}.png
    Any empty segment is omitted.

    Args:
        view:         The IntricateView instance.
        session_name: Current project / session name (may be empty).
        scale:        Render multiplier for crisp output (default 2×).

    Returns the Path of the saved PNG, or None on failure.
    """
    from datetime import datetime
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter
    import pretty_widgets.utils.settings as _s

    scene = view.scene()
    if not scene:
        return None

    # Map the visible viewport rect to scene coordinates
    vp_rect = view.viewport().rect()
    scene_rect = view.mapToScene(vp_rect).boundingRect()

    w = int(vp_rect.width()  * scale)
    h = int(vp_rect.height() * scale)
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)   # fully transparent

    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing)
    scene.render(painter, QRectF(0, 0, w, h), scene_rect)
    painter.end()

    # ── Build filename: timestamp_session_aboutlabel.png ─────────────────
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    parts = [stamp]
    s = _sanitize(session_name)
    if s:
        parts.append(s)
    about = _sanitize(_lowest_about_label(view))
    if about:
        parts.append(about)
    title = "_".join(parts) + ".png"

    out_dir = Path(_s.get("shared", "images_dir", default="."))
    ensure_dir(out_dir)
    path = out_dir / title
    img.save(str(path))
    logger.info(f"📸 Viewport snapshot saved: {path}")
    return path

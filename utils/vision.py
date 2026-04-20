#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/vision.py DropImageTextEdit shim + re-export of VisionWorker
-VisionWorker now lives in the shared intricate_vision package; this file keeps the drag-and-drop QTextEdit subclass until it migrates into PrettyEdit
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path

from PySide6.QtWidgets import QTextEdit
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtCore import Signal

from pretty_widgets.utils.logger import setup_logger

# VisionWorker + DROP_EXTENSIONS are now imported from the shared package
# so every app in the family shares one Vision branch.  The drag-and-drop
# QTextEdit subclass below stays local until it migrates into PrettyEdit
# (Phase 2 of the vision-centralisation plan).
from intricate_vision import VisionWorker, DROP_EXTENSIONS

# Re-export for back-compat with existing callers (`from utils.vision import
# VisionWorker` still works verbatim).
__all__ = ["VisionWorker", "DROP_EXTENSIONS", "DropImageTextEdit"]

_log = setup_logger("vision")


# ---------------------------------------------------------------------------
# Drag-and-drop QTextEdit subclass
# ---------------------------------------------------------------------------

class DropImageTextEdit(QTextEdit):
    """
    QTextEdit that accepts image file drops and emits image_dropped(Path).

    All other drop types (plain text, URLs, other files) fall through to
    the default QTextEdit handler so normal paste behaviour is unaffected.

    Accepted extensions are defined by DROP_EXTENSIONS (imported from
    intricate_vision).

    Connect image_dropped to a slot that creates a VisionWorker::

        self.editor = DropImageTextEdit()
        self.editor.image_dropped.connect(self._on_image_dropped)

        def _on_image_dropped(self, path: Path):
            worker = VisionWorker(path, parent=self)
            worker.finished.connect(self.editor.insertPlainText)
            worker.failed.connect(lambda err: print(err))
            worker.start()
    """

    image_dropped = Signal(Path)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self._has_image_files(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._has_image_files(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent):
        paths = self._image_paths(event.mimeData())
        if paths:
            event.acceptProposedAction()
            for p in paths:
                _log.info(f"[vision] image dropped → {p}")
                self.image_dropped.emit(p)
        else:
            super().dropEvent(event)

    @staticmethod
    def _has_image_files(mime) -> bool:
        if not mime.hasUrls():
            return False
        return any(
            Path(u.toLocalFile()).suffix.lower() in DROP_EXTENSIONS
            for u in mime.urls()
        )

    @staticmethod
    def _image_paths(mime) -> list[Path]:
        if not mime.hasUrls():
            return []
        return [
            Path(u.toLocalFile())
            for u in mime.urls()
            if Path(u.toLocalFile()).suffix.lower() in DROP_EXTENSIONS
        ]

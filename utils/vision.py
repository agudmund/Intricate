#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-The last of the Notepads didnt seem to be aware that it was part of a gigantic global beauty pageant - utils/vision.py
-Claude Vision API worker and drag-and-drop QTextEdit subclass, reusable across all apps in the family
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import base64
import json
import os
import urllib.request
import urllib.error
from pathlib import Path

from PySide6.QtWidgets import QTextEdit
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtCore import Qt, QThread, Signal

from utils.logger import setup_logger

_log = setup_logger("vision")

# ---------------------------------------------------------------------------
# Accepted image extensions for drag-and-drop
# ---------------------------------------------------------------------------
DROP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# Media type map for the API payload
_MEDIA_TYPES = {
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif":  "image/gif",
}


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class VisionWorker(QThread):
    """
    Sends one image to the Claude Vision API and emits the result.

    Runs entirely off the main thread — safe to fire-and-forget from any
    widget. Connect finished/failed before calling start().

    Signals:
        finished(str)  — extracted text on success
        failed(str)    — human-readable error message on failure

    Args:
        image_path:  Path to the image file to send.
        prompt:      Optional override for the extraction prompt.
                     Defaults to a terse "extract text only" instruction.
        model:       Anthropic model string. Defaults to claude-opus-4-5.
        max_tokens:  Max tokens for the response. Defaults to 2048.
        parent:      Optional QObject parent — keeps the worker alive
                     until the parent is destroyed.

    API key:
        Read from the SingleSharedBraincell_ApiKey environment variable,
        consistent with the rest of the family's env var naming convention.

    Usage (minimal)::

        worker = VisionWorker(Path("my_image.png"), parent=self)
        worker.finished.connect(self._on_text_extracted)
        worker.failed.connect(self._on_error)
        worker.start()

    Usage (custom prompt)::

        worker = VisionWorker(
            image_path=Path("chart.png"),
            prompt="Describe all the data values in this chart.",
            parent=self,
        )
    """

    finished = Signal(str)
    failed   = Signal(str)

    _DEFAULT_PROMPT = (
        "Extract all the text from this image exactly as written. "
        "Return only the extracted text with no commentary, labels, or formatting."
    )

    def __init__(
        self,
        image_path: Path,
        prompt:     str = "",
        model:      str = "claude-opus-4-5",
        max_tokens: int = 2048,
        parent          = None,
    ):
        super().__init__(parent)
        self.image_path = image_path
        self.prompt     = prompt or self._DEFAULT_PROMPT
        self.model      = model
        self.max_tokens = max_tokens

    def run(self):
        api_key = os.environ.get("SingleSharedBraincell_ApiKey", "").strip()
        if not api_key:
            self.failed.emit(
                "API key not found.\n"
                "Set the SingleSharedBraincell_ApiKey environment variable."
            )
            return

        try:
            raw = self.image_path.read_bytes()
        except OSError as e:
            self.failed.emit(f"Could not read image file:\n{e}")
            return

        b64        = base64.standard_b64encode(raw).decode("ascii")
        media_type = _MEDIA_TYPES.get(self.image_path.suffix.lower(), "image/png")

        payload = json.dumps({
            "model":      self.model,
            "max_tokens": self.max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type":   "image",
                            "source": {
                                "type":       "base64",
                                "media_type": media_type,
                                "data":       b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": self.prompt,
                        },
                    ],
                }
            ],
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            self.failed.emit(f"API error {e.code}:\n{detail[:300]}")
            return
        except Exception as e:
            self.failed.emit(f"Network error:\n{e}")
            return

        try:
            text = body["content"][0]["text"]
        except (KeyError, IndexError) as e:
            self.failed.emit(f"Unexpected API response shape:\n{e}")
            return

        _log.info(
            f"[vision] extraction complete — {len(text)} chars "
            f"from {self.image_path.name}"
        )
        self.finished.emit(text)


# ---------------------------------------------------------------------------
# Drag-and-drop QTextEdit subclass
# ---------------------------------------------------------------------------

class DropImageTextEdit(QTextEdit):
    """
    QTextEdit that accepts image file drops and emits image_dropped(Path).

    All other drop types (plain text, URLs, other files) fall through to
    the default QTextEdit handler so normal paste behaviour is unaffected.

    Accepted extensions are defined by DROP_EXTENSIONS at module level.

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

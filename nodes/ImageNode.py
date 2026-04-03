#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/ImageNode.py ImageNode class
-Renders image thumbnails on the canvas with an editable caption for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import base64
from pathlib import Path

from PySide6.QtWidgets import (
    QGraphicsProxyWidget, QFileDialog, QGraphicsItem
)
from PySide6.QtCore import Qt, QRectF, QPointF, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import (
    QPainter, QPixmap, QImage, QColor, QPen, QPainterPath
)

from nodes.BaseNode import BaseNode
from data.ImageNodeData import ImageNodeData
from graphics.Theme import Theme
from widgets.PrettyEdit import PrettyEdit
import utils.settings as settings
from utils.logger import setup_logger

logger = setup_logger("image")


# Layout constants
CAPTION_HEIGHT  = 28.0      # Height of the caption band at the bottom
IMAGE_PADDING   = 6.0       # Inset on all sides — prevents image clipping rounded corners
CLIP_RADIUS_MIN = 2.0       # Minimum clip radius inside the padding


class ImageNode(BaseNode):
    """
    Renders an image thumbnail with an editable caption.

    Layout (top to bottom inside the node body):
        ┌─────────────────────────┐
        │  IMAGE_PADDING          │
        │  ┌───────────────────┐  │
        │  │                   │  │
        │  │   image area      │  │
        │  │                   │  │
        │  └───────────────────┘  │
        │  caption band           │
        └─────────────────────────┘

    Interaction zones (routed in mouseDoubleClickEvent):
        Caption band  → activate inline QLineEdit editor
        Image area    → open file browser

    OS drag and drop:
        Handled by IntricateView.dropEvent — image files dragged from Explorer
        land on the view, get mapped to scene coordinates, and the nearest
        ImageNode (or a new one) receives the path via load_from_path().

    Caption editing:
        QLineEdit wrapped in QGraphicsProxyWidget. Hidden until double-click
        on the caption zone, shown inline, hidden again on Return/Escape/focus-loss.
        Backspace and Delete are fully isolated to the editor — they never
        propagate to the scene's delete handler while editing is active.

    Serialization:
        image_b64 holds the full image as a base64 PNG.
        Sessions are self-contained — no file path dependencies.
    """

    def __init__(self, data: ImageNodeData | None = None):
        if data is None:
            data = ImageNodeData()
        super().__init__(data)

        self._pixmap: QPixmap | None = None   # Full-resolution source pixmap
        self._scaled_cache: QPixmap | None = None          # Cached scaled pixmap
        self._scaled_cache_size: tuple[int, int] | None = None  # (w, h) key

        # ── Caption editor ────────────────────────────────────────────────────
        self._editor: PrettyEdit | None = None
        self._build_caption_editor()

        # ── Restore image if session data carries one ─────────────────────────
        if data.image_b64:
            self._load_from_b64(data.image_b64)
        elif data.source_path:
            p = Path(data.source_path)
            if p.exists():
                self._restore_from_path(p)

    # ─────────────────────────────────────────────────────────────────────────
    # CAPTION EDITOR
    # ─────────────────────────────────────────────────────────────────────────

    def _build_caption_editor(self) -> None:
        """
        Construct the PrettyEdit proxy and hide it.
        Built once at node creation, shown/hidden on demand.
        """
        self._editor = PrettyEdit(
            self,
            font_family=Theme.healthFontFamily,
            font_size=9,
            font_color=Theme.textPrimary,
            commit_on_focus_loss=True,
        )
        self._editor.committed.connect(self._on_caption_committed)

    def _caption_rect(self) -> QRectF:
        """The caption band at the bottom of the node."""
        r = self.rect()
        return QRectF(r.x(), r.bottom() - CAPTION_HEIGHT, r.width(), CAPTION_HEIGHT)

    def _image_rect(self) -> QRectF:
        """The padded image display area below the button shelf, above the caption band."""
        r = self.rect()
        top = r.y() + self._BUTTON_ZONE_H + IMAGE_PADDING
        return QRectF(
            r.x()     + IMAGE_PADDING,
            top,
            r.width() - IMAGE_PADDING * 2,
            r.height() - (top - r.y()) - IMAGE_PADDING - CAPTION_HEIGHT,
        )

    def _start_caption_edit(self) -> None:
        """Show the inline editor positioned over the caption band."""
        self._editor.start_edit(self.data.caption, self._caption_rect())

    def _on_caption_committed(self, text: str) -> None:
        """Save the edited caption text."""
        self.data.caption = text
        self.update()

    def _cancel_caption_edit(self) -> None:
        """Discard edits, restore view focus policy, hide editor."""
        self._editor.cancel()
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # IMAGE LOADING
    # ─────────────────────────────────────────────────────────────────────────

    def load_from_path(self, path: str | Path) -> None:
        """
        Load an image from a file path.

        Sets the caption to the filename stem if no caption exists yet.
        Encodes to base64 PNG for session persistence.
        Public — called by file browser and by View.dropEvent.
        """
        path = Path(path)
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return

        # Scale down large images at load time — keeps session base64 small and
        # paint calls fast.  2048px on the longest side is sharp at any node size.
        _MAX = 2048
        if pixmap.width() > _MAX or pixmap.height() > _MAX:
            pixmap = pixmap.scaled(
                _MAX, _MAX,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )

        self._pixmap = pixmap
        self._scaled_cache = None  # invalidate on new image

        # Record the resolved absolute path so sync_project_images can skip it next load
        self.data.source_path = str(path.resolve())

        # Set filename stem as initial caption — Vision will update it if available
        if not self.data.caption:
            self.data.caption = path.stem

        logger.info(f"image loaded: {path.name} ({pixmap.width()}x{pixmap.height()}px)")
        self._encode_to_b64()
        self.update()

    def _run_vision(self, path: Path) -> None:
        """
        Spin up a VisionWorker to identify the image content.

        Checks the PNG's tEXt metadata first — if the file was already
        processed (even under a different name), the stored caption is used
        directly and no API call is made.

        Prompt is intentionally brief — we want a short descriptive label
        suitable as a node caption, not a full description.
        Worker is parented to this node so it's cleaned up on removal.
        """
        try:
            from utils.vision import VisionWorker, read_png_vision_stamp
            import os

            # Fast path: PNG already stamped — use the embedded caption as-is
            cached = read_png_vision_stamp(path)
            if cached:
                self._on_vision_result(cached)
                return

            if not os.environ.get("SingleSharedBraincell_ApiKey", "").strip():
                return  # No key — skip silently, filename stem stays

            self._vision_worker = VisionWorker(
                image_path = path,
                prompt     = (
                    "Describe this image in 5 words or fewer. "
                    "Return only the description, no punctuation."
                ),
                max_tokens = 20,
                parent     = None,  # No Qt parent — node lifetime managed separately
            )
            self._vision_worker.finished.connect(self._on_vision_result)
            self._vision_worker.failed.connect(self._on_vision_failed)
            self._vision_worker.start()
        except Exception:
            pass  # Vision is a convenience — never crash the canvas over it

    def _on_vision_result(self, text: str) -> None:
        """Update caption with Vision result and repaint."""
        caption = text.strip().strip(".")
        if caption:
            self.data.caption = caption
            if self._editor and not self._editor.proxy.isVisible():
                self.update()

    def _on_vision_failed(self, error: str) -> None:
        """Log Vision failure quietly — filename stem caption stays."""
        logger.debug(f"vision caption skipped: {error[:80]}")

    def _restore_from_path(self, path: Path) -> None:
        """Load pixmap from path for session restore — no b64 encode, render context not ready yet."""
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return
        _MAX = 2048
        if pixmap.width() > _MAX or pixmap.height() > _MAX:
            pixmap = pixmap.scaled(_MAX, _MAX, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._pixmap = pixmap
        self._scaled_cache = None

    def _load_from_b64(self, b64_str: str) -> None:
        """Reconstruct the pixmap from a base64 PNG string (session restore)."""
        try:
            raw = base64.b64decode(b64_str)
            img = QImage.fromData(raw, "PNG")
            if not img.isNull():
                self._pixmap = QPixmap.fromImage(img)
                self._scaled_cache = None  # invalidate on new image
        except Exception:
            pass

    def _encode_to_b64(self) -> None:
        """Encode the current pixmap to base64 PNG and store in data."""
        if self._pixmap is None or self._pixmap.isNull():
            return
        buf  = QBuffer()
        buf.open(QIODevice.WriteOnly)
        self._pixmap.save(buf, "PNG")
        self.data.image_b64 = base64.b64encode(buf.data().data()).decode("utf-8")

    def _open_file_browser(self) -> None:
        """Open a file dialog to pick an image, starting from the last used directory."""
        win = self._lower_window()
        start_dir = settings.get_nested("node", "image", "last_dir", "")
        path, _ = QFileDialog.getOpenFileName(
            None,
            "Select Image",
            start_dir,
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff)"
        )
        self._raise_window(win)
        if path:
            settings.set_nested("node", "image", "last_dir", str(Path(path).parent))
            self.load_from_path(path)

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        from nodes.NodeButton import NodeButton
        super()._build_buttons()
        eye_pix = Theme.icon(Theme.iconVisionEye, fallback_color="#9ab8d9")
        self._buttons.append(NodeButton(self, eye_pix, self._vision_rename))

    def _vision_rename(self) -> None:
        """Button action: call the vision API to identify this image and update its caption."""
        src = self.data.source_path
        if src:
            self._run_vision(Path(src))

    def _trigger_vision(self) -> None:
        """Send this node's image to a ClaudeNode's vision API."""
        if not self.data.image_b64:
            # File-backed restore: encode on demand now that the render context is live.
            self._encode_to_b64()
        if not self.data.image_b64:
            return
        from nodes.ClaudeNode import ClaudeNode
        # Prefer a wired ClaudeNode — respects the user's explicit connection
        for conn in list(self.connections):
            try:
                other = conn.end_node if conn.start_node is self else conn.start_node
            except RuntimeError:
                continue
            if isinstance(other, ClaudeNode):
                other.process_vision(self.data.image_b64, self.data.caption)
                return
        # Fall back to any ClaudeNode in the scene
        scene = self.scene()
        if scene:
            claude = next((n for n in scene.items() if isinstance(n, ClaudeNode)), None)
            if claude:
                claude.process_vision(self.data.image_b64, self.data.caption)

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        """
        Route double-click to the correct zone.

        Caption band → start inline edit
        Image area   → open file browser
        """
        pos = event.pos()
        if self._caption_rect().contains(pos):
            self._start_caption_edit()
            event.accept()
            return
        if self._image_rect().contains(pos):
            self._open_file_browser()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:
        """
        Route keyboard events when the caption editor is active.
        Escape cancels. Everything else goes to the editor via the proxy.
        Backspace/Delete are fully contained here — they never reach the
        scene's delete handler while editing is active.
        """
        if self._editor and self._editor.proxy.isVisible():
            if event.key() == Qt.Key_Escape:
                self._cancel_caption_edit()
                event.accept()
                return
            # Let the proxy handle all other keys including Backspace/Delete
            event.accept()
            return
        super().keyPressEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        """
        Paint the image thumbnail and caption band inside the node shell.
        Called by BaseNode.paint after the shell (background + border) is drawn.
        """
        painter.save()

        ir = self._image_rect()
        cr = self._caption_rect()

        if self._pixmap and not self._pixmap.isNull():
            # ── Clip to rounded rect so image respects the node corners ───────
            clip_radius = max(CLIP_RADIUS_MIN, self.round_radius - IMAGE_PADDING)
            clip_path   = QPainterPath()
            clip_path.addRoundedRect(ir, clip_radius, clip_radius)
            painter.setClipPath(clip_path)

            # ── Scale pixmap to fit, preserving aspect ratio ──────────────────
            # Cache the scaled result — SmoothTransformation on a 2048px source
            # is expensive; skip it on every pan-frame repaint.
            ir_size = (int(ir.width()), int(ir.height()))
            if self._scaled_cache is None or self._scaled_cache_size != ir_size:
                self._scaled_cache = self._pixmap.scaled(
                    ir.width(),
                    ir.height(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                self._scaled_cache_size = ir_size
            scaled = self._scaled_cache
            # Centre the scaled pixmap within the image rect
            draw_x = ir.x() + (ir.width()  - scaled.width())  / 2.0
            draw_y = ir.y() + (ir.height() - scaled.height()) / 2.0
            painter.drawPixmap(QPointF(draw_x, draw_y), scaled)

            painter.setClipping(False)

            # ── Bevel border over the image ───────────────────────────────────
            bevel_r = max(CLIP_RADIUS_MIN, self.round_radius - IMAGE_PADDING)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(0, 0, 0, 80), 1))
            painter.drawRoundedRect(ir, bevel_r, bevel_r)
            painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
            painter.drawRoundedRect(ir.adjusted(1, 1, -1, -1), max(CLIP_RADIUS_MIN, bevel_r - 1), max(CLIP_RADIUS_MIN, bevel_r - 1))

        else:
            # ── Placeholder when no image is loaded ───────────────────────────
            painter.setPen(QPen(QColor(Theme.primaryBorder), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(ir, CLIP_RADIUS_MIN, CLIP_RADIUS_MIN)
            painter.setPen(QColor(Theme.healthColorLabel))
            painter.drawText(ir, Qt.AlignCenter, "double-click\nto load image")

        # ── Caption band ──────────────────────────────────────────────────────
        if not self._editor or not self._editor.proxy.isVisible():
            caption_text = self.data.caption or self.data.title
            painter.setPen(QColor(Theme.textPrimary))
            painter.drawText(cr, Qt.AlignCenter, caption_text)

        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        """
        Clean up ImageNode-specific resources before scene departure.
        Caption editor hidden, view focus restored, pixmap released.
        """
        if self._editor:
            self._editor.teardown()
        self._pixmap = None
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        # File-backed images: data layer saves source_path and discards b64 anyway —
        # no need to encode. Paste-only images (no source_path): encode so b64 is fresh.
        if not self.data.source_path:
            self._encode_to_b64()
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'ImageNode':
        return ImageNode(ImageNodeData.from_dict(data))

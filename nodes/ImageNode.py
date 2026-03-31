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
    QGraphicsProxyWidget, QLineEdit, QFileDialog, QGraphicsItem
)
from PySide6.QtCore import Qt, QRectF, QPointF, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import (
    QPainter, QPixmap, QImage, QColor, QPen, QPainterPath
)

from nodes.BaseNode import BaseNode
from data.ImageNodeData import ImageNodeData
from graphics.Theme import Theme
import utils.settings as settings
from utils.logger import setup_logger

logger = setup_logger("imagenode")


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

        # ── Caption editor ────────────────────────────────────────────────────
        self._editor_proxy: QGraphicsProxyWidget | None = None
        self._editor: QLineEdit | None = None
        self._build_caption_editor()

        # ── Restore image if session data carries one ─────────────────────────
        if data.image_b64:
            self._load_from_b64(data.image_b64)

    # ─────────────────────────────────────────────────────────────────────────
    # CAPTION EDITOR
    # ─────────────────────────────────────────────────────────────────────────

    def _build_caption_editor(self) -> None:
        """
        Construct the QLineEdit proxy and hide it.
        Built once at node creation, shown/hidden on demand.
        """
        self._editor = QLineEdit()
        self._editor.setAlignment(Qt.AlignCenter)
        self._editor.setFrame(False)
        self._editor.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                color: {Theme.textPrimary};
                font-family: {Theme.healthFontFamily};
                font-size: 9pt;
                border: none;
                padding: 0px;
                selection-background-color: {Theme.primaryBorder};
            }}
        """)
        self._editor.returnPressed.connect(self._commit_caption)
        self._editor.editingFinished.connect(self._commit_caption)

        self._editor_proxy = QGraphicsProxyWidget(self)
        self._editor_proxy.setWidget(self._editor)
        self._editor_proxy.hide()

    def _caption_rect(self) -> QRectF:
        """The caption band at the bottom of the node."""
        r = self.rect()
        return QRectF(r.x(), r.bottom() - CAPTION_HEIGHT, r.width(), CAPTION_HEIGHT)

    def _image_rect(self) -> QRectF:
        """The padded image display area above the caption band."""
        r = self.rect()
        return QRectF(
            r.x()      + IMAGE_PADDING,
            r.y()      + IMAGE_PADDING,
            r.width()  - IMAGE_PADDING * 2,
            r.height() - IMAGE_PADDING * 2 - CAPTION_HEIGHT,
        )

    def _start_caption_edit(self) -> None:
        """
        Show the inline editor positioned over the caption band.

        The view is set to Qt.NoFocus by design so it never steals keyboard
        focus from toolbar widgets. That same policy blocks the QLineEdit
        from receiving focus when requested from within the scene.

        Solution: temporarily lift the view to StrongFocus while editing,
        restore NoFocus on commit or cancel. The window behaves correctly
        in both states — this is a narrow, deterministic switch.
        """
        cr = self._caption_rect()
        self._editor_proxy.setGeometry(cr)
        self._editor.setText(self.data.caption)
        self._editor.selectAll()

        # Lift view focus policy so the embedded QLineEdit can receive keys
        if self.scene() and self.scene().views():
            self.scene().views()[0].setFocusPolicy(Qt.StrongFocus)

        self._editor_proxy.show()
        self._editor_proxy.setFocus()
        self._editor.setFocus(Qt.MouseFocusReason)

    def _commit_caption(self) -> None:
        """Save the edited caption, restore view focus policy, hide editor."""
        if not self._editor_proxy.isVisible():
            return
        text = self._editor.text().strip()
        self.data.caption = text
        self._editor_proxy.hide()
        self._restore_view_focus()
        self.update()

    def _cancel_caption_edit(self) -> None:
        """Discard edits, restore view focus policy, hide editor."""
        self._editor_proxy.hide()
        self._restore_view_focus()
        self.update()

    def _restore_view_focus(self) -> None:
        """Return the view to NoFocus — editing is done."""
        if self.scene() and self.scene().views():
            self.scene().views()[0].setFocusPolicy(Qt.NoFocus)

    # ─────────────────────────────────────────────────────────────────────────
    # IMAGE LOADING
    # ─────────────────────────────────────────────────────────────────────────

    def load_from_path(self, path: str | Path) -> None:
        """
        Load an image from a file path.

        Sets the caption to the filename stem if no caption exists yet.
        Fires a VisionWorker to identify the image content — on response
        the caption updates automatically. Fire and forget, no blocking.
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

        # Record the resolved absolute path so sync_project_images can skip it next load
        self.data.source_path = str(path.resolve())

        # Set filename stem as initial caption — Vision will update it if available
        if not self.data.caption:
            self.data.caption = path.stem

        self._encode_to_b64()
        self.update()

        # Fire Vision worker — identifies the image and updates caption on response.
        # Uses SingleSharedBraincell_ApiKey env var. Degrades silently if key is
        # absent or API is unreachable — filename stem stays as caption.
        self._run_vision(path)

    def _run_vision(self, path: Path) -> None:
        """
        Spin up a VisionWorker to identify the image content.

        Prompt is intentionally brief — we want a short descriptive label
        suitable as a node caption, not a full description.
        Worker is parented to this node so it's cleaned up on removal.
        """
        try:
            from utils.vision import VisionWorker
            import os
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
            if self._editor and not self._editor_proxy.isVisible():
                self.update()

    def _on_vision_failed(self, error: str) -> None:
        """Log Vision failure quietly — filename stem caption stays."""
        try:
            from utils.logger import setup_logger
            setup_logger("imagenode").debug(f"[Vision] caption skipped: {error[:80]}")
        except Exception:
            pass

    def _load_from_b64(self, b64_str: str) -> None:
        """Reconstruct the pixmap from a base64 PNG string (session restore)."""
        try:
            raw = base64.b64decode(b64_str)
            img = QImage.fromData(raw, "PNG")
            if not img.isNull():
                self._pixmap = QPixmap.fromImage(img)
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
        vision_pix = Theme.icon(Theme.imageVisionIcon, fallback_color="#9ab8d9")
        self._buttons.append(NodeButton(self, vision_pix, self._trigger_vision))
        trash_pix   = Theme.icon(Theme.iconDelete,  fallback_color="#c97b7b")
        confirm_pix = Theme.icon(Theme.iconConfirm, fallback_color="#d4a96a")
        self._buttons.append(NodeButton(self, trash_pix, self._delete_source_file, confirm_pix))

    def _delete_source_file(self) -> None:
        """
        Send the source file to the recycle bin, then remove this node.

        Uses send2trash so the file is recoverable — not a permanent delete.
        If source_path is empty (image was pasted / has no file behind it),
        the node is removed without touching the filesystem.
        """
        path = self.data.source_path
        if path:
            try:
                from send2trash import send2trash
                send2trash(path)
            except Exception as e:
                logger.warning(f"[ImageNode] Could not trash '{path}': {e}")
        scene = self.scene()
        if scene:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: scene.removeItem(self))

    def _trigger_vision(self) -> None:
        """Send this node's image to a ClaudeNode's vision API."""
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
        if self._editor_proxy and self._editor_proxy.isVisible():
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
            scaled = self._pixmap.scaled(
                ir.width(),
                ir.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
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
        if not self._editor_proxy or not self._editor_proxy.isVisible():
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
        if self._editor_proxy and self._editor_proxy.isVisible():
            self._editor_proxy.hide()
            self._restore_view_focus()
        self._pixmap = None
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self._encode_to_b64()   # Ensure b64 is current before serializing
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'ImageNode':
        return ImageNode(ImageNodeData.from_dict(data))

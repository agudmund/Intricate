#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/ImageNode.py ImageNode class
-Renders image thumbnails on the canvas with an editable caption for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import base64
import math
import threading
from pathlib import Path

from PySide6.QtWidgets import QFileDialog
from PySide6.QtCore import Qt, QRectF, QPointF, QBuffer, QByteArray, QIODevice, QTimer
from PySide6.QtGui import (
    QPainter, QPixmap, QImage, QImageReader, QColor, QPen, QPainterPath
)

from nodes.BaseNode import BaseNode
from data.ImageNodeData import ImageNodeData
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.utils.logger import setup_logger

logger = setup_logger("image")


# Layout constants
IMAGE_PADDING   = 6.0       # Inset on all sides — prevents image clipping rounded corners
CLIP_RADIUS_MIN = 2.0       # Minimum clip radius inside the padding



class ImageNode(BaseNode):
    """
    Renders an image thumbnail on the canvas.

    Layout (top to bottom inside the node body):
        ┌─────────────────────────┐
        │  IMAGE_PADDING          │
        │  ┌───────────────────┐  │
        │  │                   │  │
        │  │   image area      │  │
        │  │                   │  │
        │  └───────────────────┘  │
        └─────────────────────────┘

    Caption lives in a separate AboutNode that is automatically spawned
    and wired to this ImageNode whenever the caption changes. Double-click
    the image area to open a file browser.

    Serialization:
        image_b64 holds the full image as a base64 PNG.
        Sessions are self-contained — no file path dependencies.
    """

    _has_depth_toggle = True

    def __init__(self, data: ImageNodeData | None = None):
        if data is None:
            data = ImageNodeData()
        super().__init__(data)

        self._pixmap: QPixmap | None = None   # Full-resolution source pixmap
        self._scaled_cache: QPixmap | None = None          # Cached scaled pixmap
        self._scaled_cache_size: tuple[int, int] | None = None  # (target_w, target_h) key in device pixels

        # ── Async image loading state ─────────────────────────────────────────
        self._pending_pixmap: QPixmap | None = None
        self._pending_cache_key: str | None = None   # "" = done with no key
        self._pending_drift: str | None = None        # drift-warning message or None
        self._pending_size:  int | None = None        # fingerprint to fold into data after worker
        self._pending_mtime: float | None = None
        self._loading: bool = False

        self._image_delivery_timer = QTimer()
        self._image_delivery_timer.setInterval(100)
        self._image_delivery_timer.timeout.connect(self._check_image_delivery)

        # ── Kick off async restore if there's anything to load ────────────────
        if data.cache_key or data.source_path or data.image_b64:
            self._loading = True
            threading.Thread(target=self._image_load_worker, daemon=True).start()
            self._image_delivery_timer.start()

    # ─────────────────────────────────────────────────────────────────────────
    # CAPTION → ABOUT NODE
    # ─────────────────────────────────────────────────────────────────────────

    def _top_offset(self) -> float:
        """Vertical space reserved above the image — tracks the animated shelf offset."""
        return self._anim_top_offset

    def _image_rect(self) -> QRectF:
        """The padded image display area below the button shelf.

        Height is computed as if the shelf is always fully open so the
        image keeps a constant aspect ratio regardless of shelf state.
        Only the vertical position shifts with the animation.
        """
        r = self.rect()
        top = r.y() + self._top_offset() + IMAGE_PADDING
        return QRectF(
            r.x()     + IMAGE_PADDING,
            top,
            r.width() - IMAGE_PADDING * 2,
            r.height() - (top - r.y()) - IMAGE_PADDING,
        )

    def _spawn_caption_node(self, caption: str) -> None:
        """Spawn an AboutNode with *caption* and wire it to this ImageNode."""
        scene = self.scene()
        if not scene:
            return
        pos = self.scenePos()
        about_pos = QPointF(pos.x(), pos.y() + self.rect().height() + 20)
        about = scene.add_about_node(pos=about_pos, label=caption)

        from graphics.Connection import Connection
        conn = Connection(self, about)
        scene.addItem(conn)
        conn.update_path()

    # ─────────────────────────────────────────────────────────────────────────
    # IMAGE LOADING
    # ─────────────────────────────────────────────────────────────────────────

    def load_from_path(self, path: str | Path) -> None:
        """
        Load an image from a file path.

        Sets the caption to the filename stem if no caption exists yet.
        Heavy I/O (file read, scaling, cache write) runs in a daemon thread;
        the delivery timer picks up the pixmap when ready.
        Public — called by file browser and by View.dropEvent.
        """
        path = Path(path)

        # Set metadata immediately — no I/O needed
        self.data.source_path = str(path.resolve())
        if not self.data.caption:
            self.data.caption = path.stem
            self._spawn_caption_node(path.stem)

        # Clear current image and kick off async load
        self._pixmap = None
        self._scaled_cache = None
        self._loading = True
        self.update()

        def _worker(p=path):
            pixmap = None
            cache_key = ""
            try:
                raw = p.read_bytes()
            except OSError:
                raw = b""
            if raw:
                try:
                    from utils.persistence.media_cache import cache_source_bytes
                    cache_key = cache_source_bytes(raw, p.suffix)
                except Exception:
                    pass
                img = self._decode_with_orientation(raw)
                if img is not None and not img.isNull():
                    pixmap = QPixmap.fromImage(img)
                    logger.info(f"image loaded: {p.name} ({pixmap.width()}x{pixmap.height()}px)")
                # Record fingerprint of the just-cached source so the next
                # session's drift check has a reference point.
                try:
                    st = p.stat()
                    self._pending_size  = st.st_size
                    self._pending_mtime = st.st_mtime
                except OSError:
                    pass
            self._pending_pixmap = pixmap
            self._pending_cache_key = cache_key

        threading.Thread(target=_worker, daemon=True).start()
        self._image_delivery_timer.start()

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
            from utils.vision import VisionWorker
            from utils.persistence.png_stamp import read_png_vision_stamp
            import os

            # Fast path: PNG already stamped — use the embedded caption as-is
            cached = read_png_vision_stamp(path)
            if cached:
                self._on_vision_result(cached)
                return

            if not os.environ.get("SingleSharedBraincell_ApiKey", "").strip():
                return
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
        except Exception as exc:
            logger.warning(f"vision rename failed: {exc}")

    def _on_vision_result(self, text: str) -> None:
        """Update caption with Vision result, spawn a new AboutNode label."""
        if self.scene() is None:
            logger.log(5, "[VISION] result arrived for removed image %s — discarding",
                        self.data.uuid[:8])
            return  # Node already removed — worker finished after deletion
        caption = text.strip().strip(".")
        if caption:
            self.data.caption = caption
            self._spawn_caption_node(caption)
            self.update()

    def _on_vision_failed(self, error: str) -> None:
        """Spawn an AboutNode with the full API error so it's always visible on canvas."""
        if self.scene() is None:
            logger.log(5, "[VISION] failure arrived for removed image %s — discarding",
                        self.data.uuid[:8])
            return  # Node already removed
        self._spawn_caption_node(error)
        logger.warning(f"vision failed: {error}")

    # ── Async image loading ─────────────────────────────────────────────────

    @staticmethod
    def _decode_with_orientation(raw: bytes) -> QImage | None:
        """Decode raw image bytes, honouring EXIF orientation. Thread-safe."""
        buf = QBuffer()
        buf.setData(QByteArray(raw))
        buf.open(QIODevice.ReadOnly)
        reader = QImageReader(buf)
        reader.setAutoTransform(True)
        img = reader.read()
        return None if img.isNull() else img

    @staticmethod
    def _decode_b64(b64_str: str) -> QPixmap | None:
        """Decode a base64 PNG string to a QPixmap. Thread-safe."""
        try:
            raw = base64.b64decode(b64_str)
            img = QImage.fromData(raw, "PNG")
            if not img.isNull():
                return QPixmap.fromImage(img)
        except Exception:
            pass
        return None

    def _image_load_worker(self) -> None:
        """Background thread — loads image via cache/path/b64, writes to pending fields."""
        pixmap = None
        cache_key = ""
        try:
            from utils.persistence.media_cache import (
                load_cached, cache_source_bytes, cache_pixmap,
                hash_file, key_hash,
            )

            # Path 1: cached
            if self.data.cache_key:
                pixmap = load_cached(self.data.cache_key)
                if pixmap is not None:
                    cache_key = self.data.cache_key
                    # Passive drift check — cheap fingerprint (size + mtime)
                    # first, full hash only on fingerprint change. Policy is
                    # flag-don't-auto-fix, so we record the observed fingerprint
                    # after each check. Same fingerprint on next restore means
                    # nothing has changed since the last look → no re-warning.
                    # A content change since the stored fingerprint triggers a
                    # hash, and a hash-confirmed mismatch raises the drift flag.
                    if self.data.source_path:
                        sp = Path(self.data.source_path)
                        if sp.exists():
                            try:
                                st = sp.stat()
                                cur_size, cur_mtime = st.st_size, st.st_mtime
                            except OSError:
                                cur_size, cur_mtime = 0, 0.0
                            fingerprint_clean = (
                                cur_size == self.data.source_size
                                and abs(cur_mtime - self.data.source_mtime) < 1.0
                                and self.data.source_size != 0
                            )
                            if not fingerprint_clean:
                                src_hash = hash_file(sp)
                                if src_hash and src_hash != key_hash(cache_key):
                                    self._pending_drift = (
                                        f"source drifted — cache no longer matches\n"
                                        f"{sp.name}"
                                    )
                                # Record the fingerprint we just observed so
                                # the next restore sees a clean match and stays
                                # silent — we've already surfaced this state.
                                self._pending_size  = cur_size
                                self._pending_mtime = cur_mtime

            # Path 2: source file → cache raw bytes + decode for display
            if pixmap is None and self.data.source_path:
                p = Path(self.data.source_path)
                if p.exists():
                    try:
                        raw = p.read_bytes()
                    except OSError:
                        raw = b""
                    if raw:
                        cache_key = cache_source_bytes(raw, p.suffix)
                        img = self._decode_with_orientation(raw)
                        if img is not None and not img.isNull():
                            pixmap = QPixmap.fromImage(img)
                        # Record fingerprint of the freshly-cached source so
                        # the next restore's drift check has a reference point
                        try:
                            st = p.stat()
                            self._pending_size  = st.st_size
                            self._pending_mtime = st.st_mtime
                        except OSError:
                            pass

            # Path 3: legacy base64
            if pixmap is None and self.data.image_b64:
                pixmap = self._decode_b64(self.data.image_b64)
                if pixmap and not pixmap.isNull():
                    cache_key = cache_pixmap(pixmap)

        except Exception as exc:
            logger.warning(f"[load] worker failed for {self.data.uuid[:8]}: {exc}")

        # Atomic writes under GIL — main thread timer picks these up
        self._pending_pixmap = pixmap
        self._pending_cache_key = cache_key  # "" sentinel = done, no key

    def _check_image_delivery(self) -> None:
        """Main-thread timer callback — picks up the loaded pixmap from the worker."""
        if self._pending_cache_key is None:
            return  # worker still running

        pixmap = self._pending_pixmap
        cache_key = self._pending_cache_key
        self._pending_pixmap = None
        self._pending_cache_key = None

        self._image_delivery_timer.stop()
        self._loading = False

        if pixmap is not None and not pixmap.isNull():
            self._pixmap = pixmap
            self._scaled_cache = None
        if cache_key:
            self.data.cache_key = cache_key

        # Fold in the fingerprint the worker observed. Recording this silently
        # (whether or not drift was surfaced) is what stops the next session
        # restore from re-warning about the same unchanged-since-last-look state.
        if self._pending_size is not None:
            self.data.source_size = self._pending_size
            self._pending_size = None
        if self._pending_mtime is not None:
            self.data.source_mtime = self._pending_mtime
            self._pending_mtime = None

        drift = self._pending_drift
        self._pending_drift = None
        if drift:
            self._spawn_caption_node(drift)
            logger.info(f"[drift] {self.data.uuid[:8]} — {drift.splitlines()[0]}")

        self.update()

    def _encode_to_b64(self) -> None:
        """Encode the current pixmap to base64 PNG and store in data."""
        if self._pixmap is None or self._pixmap.isNull():
            return
        buf  = QBuffer()
        buf.open(QIODevice.WriteOnly)
        self._pixmap.save(buf, "PNG")
        self.data.image_b64 = base64.b64encode(buf.data().data()).decode("utf-8")

    def _open_file_browser(self) -> None:
        """Open a file dialog to pick an image, starting from the last used directory.

        Mirrors GitNode's commit-dialog choreography — roll up the curtains
        to reveal the desktop while the explorer dialog is on screen, then
        roll them back down on close. Same lower/raise dance ensures the
        always-on-top window doesn't fight the dialog for focus.
        """
        win = self._lower_window()
        # Roll curtains up if currently down — restore on dialog close
        was_collapsed = False
        mw = None
        try:
            views = self.scene().views() if self.scene() else []
            if views:
                mw = views[0].window()
                if hasattr(mw, 'is_collapsed') and not mw.is_collapsed:
                    mw.toggle_curtains()
                    was_collapsed = True
        except Exception:
            pass
        scene = self.scene()
        start_dir = scene.get_browse_dir("image") if scene else ""
        path, _ = QFileDialog.getOpenFileName(
            None,
            "Select Image",
            start_dir,
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff)"
        )
        if was_collapsed and mw is not None:
            try:
                mw.toggle_curtains()
            except Exception:
                pass
        self._raise_window(win)
        if path:
            if scene:
                scene.remember_browse_dir("image", str(Path(path).parent))
            self.load_from_path(path)

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _toggle_border(self) -> None:
        self.data.show_border = not self.data.show_border
        self.update()

    def _build_buttons(self) -> None:
        from nodes.NodeButton import NodeButton, EmojiButton
        super()._build_buttons()
        eye_pix = Theme.icon("vision_rename.png", fallback_color="#9ab8d9")
        vision_btn = NodeButton(self, eye_pix, self._vision_rename)
        vision_btn.setToolTip("Ask Claude what this image is about")
        self._buttons.append(vision_btn)
        stamp_btn = EmojiButton(
            self,
            get_emoji=lambda: "\U0001F48E",  # 💎
            set_emoji=lambda _: self._stamp_source_file(),
        )
        stamp_btn.setToolTip("Goddess level and Stamp On It")
        self._buttons.append(stamp_btn)
        inspect_btn = EmojiButton(
            self,
            get_emoji=lambda: "\U0001F50D",  # 🔍
            set_emoji=lambda _: self._inspect_stamp(),
        )
        inspect_btn.setToolTip("Read PNG metadata stamp")
        self._buttons.append(inspect_btn)
        self._border_btn = EmojiButton(
            self,
            get_emoji=lambda: "\u25cb",  # ○
            set_emoji=lambda _: self._toggle_border(),
        )
        self._border_btn.setToolTip("Toggle ivory border")
        self._buttons.append(self._border_btn)
        convert_btn = EmojiButton(
            self,
            get_emoji=lambda: "\U0001F504",  # 🔄
            set_emoji=lambda _: self._convert_to_png(),
        )
        convert_btn.setToolTip("Convert source image to PNG")
        self._buttons.append(convert_btn)

    def _convert_to_png(self) -> None:
        """Convert the source file to PNG, update the node to point at the new file."""
        src = self.data.source_path
        if not src:
            self._spawn_caption_node("no source path")
            return
        p = Path(src)
        if not p.exists():
            self._spawn_caption_node(f"file not found — {p.name}")
            return
        if p.suffix.lower() == ".png":
            self._spawn_caption_node("already PNG")
            return
        png_path = p.with_suffix(".png")
        try:
            from PIL import Image
            with Image.open(p) as img:
                img.save(png_path, "PNG")
            # Reload from the new PNG
            self.load_from_path(png_path)
            self._spawn_caption_node(f"converted: {p.name} → {png_path.name}")
            logger.info(f"converted {p.name} → {png_path.name}")
        except Exception as exc:
            self._spawn_caption_node(f"convert failed: {exc}")
            logger.warning(f"convert to PNG failed: {exc}")

    def _vision_rename(self) -> None:
        """Button action: call the vision API to identify this image and update its caption."""
        src = self.data.source_path
        if src:
            self._run_vision(Path(src))

    def _show_info(self, msg: str) -> None:
        """Push a message to the window's info label."""
        try:
            scene = self.scene()
            if scene:
                for view in scene.views():
                    win = view.window()
                    if hasattr(win, 'show_info'):
                        win.show_info(msg)
                        return
        except Exception:
            pass

    def _inspect_stamp(self) -> None:
        """Read the PNG tEXt stamp and spawn an AboutNode showing its contents."""
        src = self.data.source_path
        if not src:
            self._spawn_caption_node("no source path")
            return
        p = Path(src)
        # Check if the file is actually a PNG at the binary level
        try:
            magic = p.read_bytes()[:8]
            if magic != b'\x89PNG\r\n\x1a\n':
                self._spawn_caption_node(f"not a real PNG — magic: {magic[:4]}")
                return
        except Exception as exc:
            self._spawn_caption_node(f"cannot read file: {exc}")
            return
        from utils.persistence.png_stamp import read_png_vision_stamp
        stamp = read_png_vision_stamp(p)
        if stamp:
            self._spawn_caption_node(stamp)
        else:
            self._spawn_caption_node("no stamp found")

    def _find_connected_about(self) -> str | None:
        """Return the label from the single connected AboutNode, or None."""
        from nodes.AboutNode import AboutNode
        abouts = []
        for conn in list(self.connections):
            try:
                other = conn.end_node if conn.start_node is self else conn.start_node
            except RuntimeError:
                continue
            if isinstance(other, AboutNode):
                abouts.append(other)
        if len(abouts) == 1:
            return abouts[0].data.label or None
        return None

    def _stamp_source_file(self) -> None:
        """Write the connected AboutNode's label into the source PNG's tEXt metadata."""
        src = self.data.source_path
        if not src:
            self._spawn_caption_node("stamp: no source path")
            return
        caption = self._find_connected_about()
        if not caption:
            self._spawn_caption_node("stamp: connect exactly 1 AboutNode")
            return
        p = Path(src)
        if not p.exists():
            self._spawn_caption_node(f"stamp: file not found — {p.name}")
            return
        from utils.persistence.png_stamp import write_png_vision_stamp, read_png_vision_stamp
        if not caption.startswith("Intricate: "):
            caption = f"Intricate: {caption}"
        write_png_vision_stamp(p, caption)
        # Verify it stuck
        verify = read_png_vision_stamp(p)
        if verify == caption:
            # Re-cache: the source bytes changed (new tEXt chunk), so the old
            # cache_key now points at a stale copy. Read fresh bytes, re-hash,
            # re-cache, and update the node's cache_key so cache mirrors source.
            try:
                from utils.persistence.media_cache import cache_source_bytes
                raw = p.read_bytes()
                new_key = cache_source_bytes(raw, p.suffix)
                if new_key:
                    self.data.cache_key = new_key
                    logger.debug(f"[stamp] re-cached {p.name} → {new_key[:12]}…")
            except Exception as exc:
                logger.warning(f"[stamp] re-cache failed: {exc}")
            self._spawn_caption_node(caption)
        else:
            self._spawn_caption_node(f"failed — wrote '{caption}' but read back '{verify}'")

    def _trigger_vision(self) -> None:
        """Send this node's image to a ClaudeNode's vision API.

        Prefers base64 of the cached source bytes — same bytes that are on disk,
        preserving EXIF, XMP, ICC and any tEXt stamps so the Vision model sees
        the exact file. Falls back to encoding the in-memory pixmap for nodes
        with no cache entry (legacy or just-pasted).
        """
        payload = ""
        if self.data.cache_key:
            try:
                from utils.persistence.media_cache import cached_bytes
                raw = cached_bytes(self.data.cache_key)
                if raw:
                    payload = base64.b64encode(raw).decode("utf-8")
            except Exception:
                pass
        if not payload:
            if not self.data.image_b64:
                self._encode_to_b64()
            payload = self.data.image_b64
        if not payload:
            return
        from nodes.ClaudeNode import ClaudeNode
        # Prefer a wired ClaudeNode — respects the user's explicit connection
        for conn in list(self.connections):
            try:
                other = conn.end_node if conn.start_node is self else conn.start_node
            except RuntimeError:
                continue
            if isinstance(other, ClaudeNode):
                other.process_vision(payload, self.data.caption)
                return
        # Fall back to any ClaudeNode in the scene
        scene = self.scene()
        if scene:
            claude = next((n for n in scene.items() if isinstance(n, ClaudeNode)), None)
            if claude:
                claude.process_vision(payload, self.data.caption)

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        """Double-click the top strip to toggle buttons, image area to browse."""
        if self._image_rect().contains(event.pos()):
            self._open_file_browser()
            event.accept()
            return
        # Fall through to BaseNode — handles shelf toggle on top-strip double-click
        super().mouseDoubleClickEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        """
        LOD-aware content tier.

        Shell (background + border) has already been drawn by BaseNode.paint;
        this handoff fills the interior with a screen-pixel-resolution bitmap,
        regenerating the scaled cache only when the view's zoom crosses a
        quantized 0.5 step. Capped at source resolution — we never invent
        pixels the decode did not provide; beyond that cap the painter's
        SmoothPixmapTransform handles the residual upscale without blocking.
        """
        painter.save()

        ir = self._image_rect()

        if self._pixmap and not self._pixmap.isNull():
            # ── Clip to rounded rect so image respects the node corners ───────
            clip_radius = max(CLIP_RADIUS_MIN, self.round_radius - IMAGE_PADDING)
            clip_path   = QPainterPath()
            clip_path.addRoundedRect(ir, clip_radius, clip_radius)
            painter.setClipPath(clip_path)

            # ── Scale pixmap to fit, preserving aspect ratio ──────────────────
            # Key the scaled cache on image_rect × view LOD so zooming the canvas
            # regenerates the bitmap at screen-pixel resolution instead of
            # upscaling a node-sized cache. Capped at the source pixmap size —
            # no point scaling beyond the pixels we have.
            raw_lod = max(1.0, abs(painter.worldTransform().m11()))
            # Quantize to 0.5 steps so continuous zooming doesn't rescale the
            # full-res pixmap on every frame — only at meaningful detail jumps.
            lod = max(1.0, math.ceil(raw_lod * 2.0) / 2.0)
            target_w = min(self._pixmap.width(),  int(ir.width()  * lod) + 1)
            target_h = min(self._pixmap.height(), int(ir.height() * lod) + 1)
            target_size = (target_w, target_h)
            if self._scaled_cache is None or self._scaled_cache_size != target_size:
                self._scaled_cache = self._pixmap.scaled(
                    target_w,
                    target_h,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                self._scaled_cache_size = target_size
            scaled = self._scaled_cache
            # Aspect-fit the scaled pixmap into image_rect in scene coordinates.
            # At high zoom the scaled cache clamps at source resolution; painter
            # will upsample from there, but the drawn rect must still fill ir.
            sw, sh = scaled.width(), scaled.height()
            aspect = sw / sh if sh else 1.0
            if ir.width() / ir.height() > aspect:
                draw_h = ir.height()
                draw_w = draw_h * aspect
            else:
                draw_w = ir.width()
                draw_h = draw_w / aspect
            draw_x = ir.x() + (ir.width()  - draw_w) / 2.0
            draw_y = ir.y() + (ir.height() - draw_h) / 2.0
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(QRectF(draw_x, draw_y, draw_w, draw_h), scaled, QRectF(scaled.rect()))

            painter.setClipping(False)

            # ── Border ────────────────────────────────────────────────────────
            bevel_r = max(CLIP_RADIUS_MIN, self.round_radius - IMAGE_PADDING)
            painter.setBrush(Qt.NoBrush)
            if self.data.show_border:
                # Ivory white border — sits inside the image rect
                painter.setPen(QPen(QColor(225, 213, 198, 255), 3))
                painter.drawRoundedRect(
                    ir.adjusted(1, 1, -1, -1), bevel_r, bevel_r,
                )
            else:
                # Default subtle bevel
                painter.setPen(QPen(QColor(0, 0, 0, 80), 1))
                painter.drawRoundedRect(ir, bevel_r, bevel_r)
                painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
                painter.drawRoundedRect(
                    ir.adjusted(1, 1, -1, -1),
                    max(CLIP_RADIUS_MIN, bevel_r - 1),
                    max(CLIP_RADIUS_MIN, bevel_r - 1),
                )

        else:
            # ── Placeholder when no image is loaded ───────────────────────────
            painter.setPen(QPen(QColor(Theme.primaryBorder), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(ir, CLIP_RADIUS_MIN, CLIP_RADIUS_MIN)
            painter.setPen(QColor(Theme.healthColorLabel))
            text = "loading\u2026" if self._loading else "double-click\nto load image"
            painter.drawText(ir, Qt.AlignCenter, text)

        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    _demolition_timers = [('_image_delivery_timer', '_check_image_delivery')]
    _demolition_workers = [('_vision_worker', ['finished', 'failed'])]

    def _demolition_pre(self) -> None:
        # Null the pending-delivery fields BEFORE the crew stops the
        # timer — ordering here keeps a late-finishing daemon thread
        # from writing into state we're about to drop.
        self._pending_pixmap = None
        self._pending_cache_key = None
        self._pending_drift = None
        self._pending_size  = None
        self._pending_mtime = None
        self._loading = False

    def _demolition_post(self) -> None:
        # Crew has severed VisionWorker signals; null the worker ref.
        self._vision_worker = None
        self._pixmap = None
        self._scaled_cache = None

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        # Cache handles persistence — ensure pasted images without a cache_key
        # get cached before save (belt-and-suspenders for edge cases).
        if self._pixmap and not self.data.cache_key:
            from utils.persistence.media_cache import cache_pixmap
            self.data.cache_key = cache_pixmap(self._pixmap)
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'ImageNode':
        return ImageNode(ImageNodeData.from_dict(data))

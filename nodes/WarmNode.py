#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/WarmNode.py WarmNode class
-The main content node. Free-form text with an emoji accent and editable title, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from pretty_widgets.PrettyEdit import PrettyEdit
from PySide6.QtCore import Qt, QRectF, QPointF, QPoint, QFileSystemWatcher, QTimer
from PySide6.QtGui import QPainter, QPainterPath, QFont, QFontMetrics, QColor, QPen
from PySide6.QtWidgets import QWidget

from nodes.BaseNode import BaseNode
from data.WarmNodeData import WarmNodeData
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.utils.logger import setup_logger

_log = setup_logger("warmnode")

# Layout constants
EMOJI_SIZE      = 28.0      # Emoji accent area at top-left
TITLE_HEIGHT    = 22.0      # Title band below emoji row
PADDING         = 10.0      # General internal padding
BODY_TOP        = PADDING + EMOJI_SIZE + 16.0   # Body text starts below title + breathing room

# Oversized-paste threshold. A single paste whose total would push the node
# past this size triggers an automatic chain-split into multiple WarmNodes.
# 50 KB is generous for prose (a long chapter is ~30–50 KB) and comfortably
# below the sizes where Qt's text layout costs real frames — the 5.8 MB
# skyscraper that caused the 2026-04-18 crash would split into ~120 nodes
# instead of one proxy Qt can't render.
WARM_SPLIT_THRESHOLD = 50_000

# Bridge file lives alongside session data
_BRIDGE_DIR = Path(__file__).resolve().parent.parent / "Documents" / "data"


def _html_to_plain(body: str) -> str:
    """Strip HTML to plain text via a scratch QTextDocument.
    Handles the legacy `toHtml()` save format used before 2026-04-18,
    and any session that still carries web-paste-styled body_text.
    Plain strings pass through unchanged."""
    if not body:
        return ""
    if not body.lstrip().startswith(("<", "<!DOCTYPE")):
        return body
    from PySide6.QtGui import QTextDocument as _QTextDocument
    doc = _QTextDocument()
    doc.setHtml(body)
    return doc.toPlainText()


class _WireOverlay(QWidget):
    """Transparent top-level widget that mirrors the floating-connection
    wire on top of any popup menu.

    A QGraphicsScene item can't be stacked above a QMenu popup — they
    live in separate rendering trees (scene-rendered-in-viewport vs
    top-level-popup-window).  So when a right-click spawns both a
    context menu and a floating wire, the wire's endpoint is hidden
    under the menu.

    This overlay is a borderless stays-on-top widget covering the full
    virtual desktop, raised above the menu, that re-draws the wire's
    bezier path.  Mouse events pass through (transparent for input).
    Updated in lockstep with the scene wire by the same cursor tracker."""

    def __init__(self, start_screen_pos: QPoint):
        super().__init__(None)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        from PySide6.QtGui import QGuiApplication
        # Cover the union of all screens so the wire is never clipped
        vg = QGuiApplication.primaryScreen().virtualGeometry()
        self.setGeometry(vg)
        self._start = start_screen_pos
        self._end = start_screen_pos
        self.show()
        self.raise_()

    def update_end(self, screen_pos: QPoint) -> None:
        self._end = screen_pos
        self.update()

    def paintEvent(self, _event) -> None:
        from pretty_widgets.graphics.Theme import Theme
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        p0 = self.mapFromGlobal(self._start)
        p1 = self.mapFromGlobal(self._end)
        # Simple horizontal-tangent cubic bezier, same shape family the
        # scene wires use (curvature weighted by the horizontal reach).
        dx = abs(p1.x() - p0.x())
        c1 = QPointF(p0.x() + dx * 0.5, p0.y())
        c2 = QPointF(p1.x() - dx * 0.5, p1.y())
        path = QPainterPath()
        path.moveTo(QPointF(p0))
        path.cubicTo(c1, c2, QPointF(p1))
        pen = QPen(QColor(Theme.nodeBorder),
                   Theme.nodeBorderWidth,
                   Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)


class _SmartPrettyEdit(PrettyEdit):
    """PrettyEdit subclass that intercepts oversized pastes before they land
    in the document, and exposes a class-level contextMenuEvent hook so the
    owning node can prepend its own actions to the right-click menu.

    On a paste that would push the document past the owning WarmNode's
    split threshold, the paste is diverted to the node's chain-split
    routine instead of being inserted. This prevents Qt from attempting
    to render multi-megabyte text in a single QTextEdit proxy — the
    exact condition that crashes Qt6Core.dll during scene load. Small
    pastes pass through unchanged.

    contextMenuEvent is overridden at the *class* level (not assigned to an
    instance) because PySide6's C++ → Python virtual dispatch only finds
    overrides on the class — instance attribute shadowing is silently
    ignored for Qt virtuals.  The owning node supplies a callback via
    context_menu_extra(ctx) that receives the standard menu and is free
    to insert / prepend / append actions before the menu is shown.
    """

    def __init__(self, *args, threshold: int = 0, on_oversized_paste=None,
                 context_menu_extra=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._split_threshold = threshold
        self._on_oversized_paste = on_oversized_paste
        self._context_menu_extra = context_menu_extra
        # Set during right-click → suppresses the single commit-on-focus-loss
        # triggered by View.mousePressEvent's self.setFocus(). Without this,
        # the queued FocusOut hides the proxy before our deferred menu can
        # open, leaving a dismissed/stranded popup.
        self._suppress_next_commit = False

    def commit(self):
        """Suppress a single commit if armed by mousePressEvent on
        right-click.  Without this, View.mousePressEvent's self.setFocus()
        queues a FocusOut that triggers commit-on-focus-loss → proxy.hide()
        before our synchronous exec() opens the menu."""
        if self._suppress_next_commit:
            self._suppress_next_commit = False
            return None
        return super().commit()

    def insertFromMimeData(self, mime) -> None:
        text = mime.text() or mime.html() or ''
        if (text and self._on_oversized_paste is not None
                and self._split_threshold > 0):
            existing = self.toPlainText()
            if len(existing) + len(text) > self._split_threshold:
                # Defer so the paste action's own event processing completes
                # before the scene starts growing — keeps Qt's state machine
                # out of our way while we spawn nodes.
                from PySide6.QtCore import QTimer as _QTimer
                cb = self._on_oversized_paste
                _QTimer.singleShot(0, lambda e=existing, t=text: cb(e, t))
                return
        super().insertFromMimeData(mime)

    def mousePressEvent(self, event) -> None:
        """Right-click → context menu.  Matches the working StickerNode
        pattern (commit de24bd7): pretty_menu() with no parent → genuine
        top-level popup with Qt.Popup window flag, executed synchronously
        from the press handler.  Menu contents harvested from QTextEdit's
        createStandardContextMenu() so the full set is preserved (Undo /
        Redo / Cut / Copy / Paste / Delete / Select All), then 'The
        Majestic' prepended via context_menu_extra.

        commit-suppression is still required — View.mousePressEvent calls
        self.setFocus() which triggers a queued FocusOut on this editor,
        and commit-on-focus-loss would otherwise hide the proxy before
        the synchronous exec() had a chance to run."""
        if event.button() == Qt.RightButton:
            # Start a floating connection wire in parallel with the menu —
            # same gesture as right-clicking any other node for wiring.
            # The wire is intentionally "in the way": it tracks cursor
            # position while the menu is open, pointing at whichever
            # menu entry the user is hovering.  Once the menu closes the
            # wire is still floating and can be completed on a target
            # node (or cancelled with another right-click on the canvas).
            node = getattr(self, '_parent_node', None)
            scene = node.scene() if node is not None else None
            view = (scene.views()[0]
                    if (scene is not None and scene.views()) else None)
            if scene is not None and hasattr(scene, 'begin_connection'):
                scene.begin_connection(node)
            # Overlay mirror of the wire, raised above the menu — scene
            # items can't Z-stack over a top-level popup, so we paint a
            # matching bezier on a transparent stays-on-top widget that
            # covers the whole virtual desktop.  Start point: node's
            # right-edge center, mapped scene → view → global.
            from PySide6.QtGui import QCursor
            start_screen = QCursor.pos()
            if node is not None and view is not None:
                r = node.rect()
                right_center_scene = node.mapToScene(
                    QPointF(r.right(), r.center().y()))
                start_screen = view.mapToGlobal(
                    view.mapFromScene(right_center_scene))
            overlay = _WireOverlay(start_screen)
            # Cursor-tracking timer — the menu's modal event loop processes
            # QTimer events, so this fires throughout the exec() and keeps
            # both the scene wire AND the overlay endpoint glued to the
            # cursor (which is hovering menu entries).
            tracker = QTimer()
            tracker.setInterval(16)   # ~60 fps
            def _track_cursor():
                cursor = QCursor.pos()
                if scene is not None and view is not None and hasattr(
                        scene, 'update_floating_connection'):
                    scene_pos = view.mapToScene(view.mapFromGlobal(cursor))
                    scene.update_floating_connection(scene_pos)
                overlay.update_end(cursor)
                overlay.raise_()   # re-raise each tick in case menu re-stacks
            tracker.timeout.connect(_track_cursor)
            tracker.start()
            self._suppress_next_commit = True
            from pretty_widgets.PrettyMenu import menu as pretty_menu
            ctx = pretty_menu()   # NO parent — top-level popup
            # Harvest the full standard QTextEdit menu.  QActions can
            # belong to multiple menus; reparenting them into ctx gives
            # us the complete Undo/Redo/Cut/Copy/Paste/Delete/Select-All
            # set with correct enable/disable state, without re-implementing
            # any of Qt's internal logic.
            std = self.createStandardContextMenu()
            for action in list(std.actions()):
                std.removeAction(action)
                ctx.addAction(action)
            std.deleteLater()
            if self._context_menu_extra is not None:
                try:
                    self._context_menu_extra(ctx)
                except Exception:
                    pass
            ctx.exec(event.globalPosition().toPoint())
            tracker.stop()
            tracker.deleteLater()
            overlay.hide()
            overlay.deleteLater()
            ctx.deleteLater()
            event.accept()
            return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:
        # Right-click press is handled in mousePressEvent above — suppress
        # Qt's follow-up QContextMenuEvent so a second menu doesn't flash.
        event.accept()


class WarmNode(BaseNode):
    """
    The main content node — the star of the show.

    Layout (top to bottom):
        ── emoji + title row ──
        ── body text area (QTextEdit proxy, editable) ──

    Double-click anywhere in the body area activates the text editor.
    The title is painted directly and edited via double-click on the title zone.
    The emoji is painted as an accent — changeable via future emoji picker.

    Serialization:
        body_text and emoji are stored in WarmNodeData.
        Both survive session save/load cleanly.

    Bridge:
        Double-clicking the title opens Notepad++ Duplex+ Turbo with a
        bidirectional JSON bridge file.  Edits in either app propagate
        to the other via QFileSystemWatcher with debounce timers.
    """

    _has_depth_toggle = True

    # Class-level shared font cache for body paint (matches AboutNode /
    # TextNode pattern).  All WarmNode idle bodies use the same font, so
    # one QFont + one QFontMetrics serve every instance rather than one
    # pair per node.
    _SHARED_BODY_FONTS: dict = {}

    def __init__(self, data: WarmNodeData | None = None):
        if data is None:
            data = WarmNodeData()
        super().__init__(data)

        # ── Body text editor ──────────────────────────────────────────────────
        # Lazy: only built on first double-click in the body zone.  See
        # the TextNode precedent (commit a2337bb) and the same principle
        # AboutNode has always used — one active editor on the canvas at
        # a time, so 146 eager builds at session load was pure waste.
        # paint_content renders the body text from data.body_text when
        # the editor is absent.
        self._editor: 'PrettyEdit | None' = None

        # ── Bridge state (runtime only — not persisted) ───────────────────────
        self._bridge_path: str | None = None
        self._bridge_watcher: QFileSystemWatcher | None = None
        self._bridge_writing = False

        self._bridge_debounce = QTimer()
        self._bridge_debounce.setSingleShot(True)
        self._bridge_debounce.setInterval(300)
        self._bridge_debounce.timeout.connect(self._process_bridge_change)

        self._bridge_write_debounce = QTimer()
        self._bridge_write_debounce.setSingleShot(True)
        self._bridge_write_debounce.setInterval(500)
        self._bridge_write_debounce.timeout.connect(self._write_bridge)

    # ─────────────────────────────────────────────────────────────────────────
    # LAYOUT ZONES
    # ─────────────────────────────────────────────────────────────────────────

    def _body_rect(self) -> QRectF:
        r = self.rect()
        return QRectF(
            r.x() + PADDING,
            r.y() + BODY_TOP,
            r.width()  - PADDING * 2,
            r.height() - BODY_TOP - PADDING,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # BODY EDITOR
    # ─────────────────────────────────────────────────────────────────────────

    def _ensure_body_editor(self) -> None:
        """Lazy-build the body PrettyEdit on first double-click in the
        body zone.  Idempotent — subsequent calls are no-ops.  Uses the
        smart-paste variant so a paste that would push the body past
        WARM_SPLIT_THRESHOLD auto-splits into a chain of sibling
        WarmNodes instead of trying to render a single huge document."""
        if self._editor is not None:
            return
        # Caret height = tight bounds of lowercase 'l'.  Lato's ascent
        # includes diacritic headroom above the cap line, so the caret
        # would overshoot if we used that; matching the ascender-glyph
        # silhouette keeps it indistinguishable from an 'l' on the line.
        fm = QFontMetrics(QFont(Theme.warmBodyFontFamily, Theme.warmBodyFontSize))
        _l_height = fm.tightBoundingRect("l").height() + 1   # +1 for AA edge
        self._editor = _SmartPrettyEdit(
            self,
            font_family=Theme.warmBodyFontFamily,
            font_size=Theme.warmBodyFontSize,
            font_color=Theme.textPrimary,
            always_visible=False,
            commit_on_focus_loss=True,
            normalize_layout=False,
            caret_height=_l_height,
            threshold=WARM_SPLIT_THRESHOLD,
            on_oversized_paste=self._split_oversized_paste,
            context_menu_extra=self._add_majestic_action,
        )
        # Give emoji glyphs 3px extra descent room without affecting text layout.
        # CSS padding-bottom on the body element adds space below each line's
        # content box — just enough to prevent emoji circle clipping.
        self._editor.document().setDefaultStyleSheet(
            "body { padding-bottom: 3px; }"
        )
        # Always display as plain text — web-paste HTML with per-char span
        # formatting made paint cost scale with run count and loaded the
        # whole canvas (2026-04-18 lag investigation).  Legacy sessions
        # with HTML body round-trip through a scratch document to strip
        # the tags cleanly; the user's ambient node styling takes over.
        self._editor.setPlainText(_html_to_plain(self.data.body_text))
        self._editor.textChanged.connect(self._on_text_changed)
        self._editor.committed.connect(self._on_committed)

        self._editor.proxy.setGeometry(self._body_rect())

    def _on_text_changed(self) -> None:
        """Sync text to data on every keystroke — no explicit commit needed.
        Saved as plain text — `insertFromMimeData` in StyledTextEdit now
        strips HTML on paste, so the editor never holds rich formatting
        to preserve, and the save path can stay simple."""
        if self._editor:
            self.data.body_text = self._editor.toPlainText()
            # Propagate inline edits to bridge if active
            if self._bridge_path and os.path.exists(self._bridge_path):
                self._bridge_write_debounce.start()

    def _on_committed(self, text: str) -> None:
        """Fires when the lazy editor loses focus — PrettyEdit has already
        hidden its proxy at this point.  paint_content takes over the
        visual until the next edit trigger."""
        self.data.body_text = text
        self.update()

    def _split_oversized_paste(self, existing: str, new_text: str) -> None:
        """Called by _SmartPrettyEdit when a paste would push this node past
        WARM_SPLIT_THRESHOLD. Chunks the combined content gently (paragraphs
        first, then smaller boundaries), keeps the first chunk in this node,
        and spawns additional WarmNodes for the rest — chained with
        Connection wires so the original reading order is preserved
        spatially. Same placement machinery CushionsNode._export uses.

        Catches the pathology at paste time rather than letting Qt try to
        render a multi-megabyte document in a single proxy (the 2026-04-18
        crash class). Whispers the split count via InfoBar so the action
        isn't invisible — the user sees a chain of new nodes appear.
        """
        from utils.text_chunker import chunk_text
        from graphics.Connection import Connection
        from utils.placement import spiral_place, wander_origin

        full_content = (existing + new_text) if existing else new_text
        chunks = chunk_text(full_content, max_chars=WARM_SPLIT_THRESHOLD)
        if not chunks:
            return

        # First chunk stays here. blockSignals keeps this from retriggering
        # _on_text_changed mid-sync, which would write partial state to data.
        first_chunk = chunks[0]
        self._editor.blockSignals(True)
        self._editor.setPlainText(first_chunk)
        self._editor.blockSignals(False)
        self.data.body_text = first_chunk
        self._auto_fit_height()

        scene = self.scene()
        if not scene or len(chunks) == 1:
            return

        _OFFSCREEN = QPointF(-999_999, -999_999)
        _PADDING   = 28
        prev_node  = self

        for chunk in chunks[1:]:
            wdata = WarmNodeData(body_text=chunk, title="")
            node  = WarmNode(wdata)
            node.setPos(_OFFSCREEN)
            scene.addItem(node)
            scene.raise_node(node)
            # Auto-fit height from the document's layout
            if node._editor:
                doc = node._editor.document()
                doc.setTextWidth(node.rect().width() - _PADDING * 2)
                doc_h = doc.size().height()
                needed = 90.0 + doc_h + _PADDING
                if needed > node.rect().height():
                    r = node.rect()
                    node.setRect(QRectF(r.x(), r.y(), r.width(), needed))
                    node.data.height = needed
            chain_origin = wander_origin(prev_node)
            pos = spiral_place(
                scene, node, origin=chain_origin,
                parent=prev_node,
                fallback=chain_origin, padding=_PADDING,
            )
            node.setPos(pos)
            conn = Connection(prev_node, node)
            scene.addItem(conn)
            prev_node = node

        # Whisper so the user knows the split happened. Reach through the
        # scene's views to find the main window; the info channel is the
        # right voice for a systemic "I handled this, here's what happened"
        # note (see project_three_notification_channels memory).
        try:
            views = scene.views() if scene else []
            if views:
                window = views[0].window()
                if hasattr(window, 'show_info'):
                    window.show_info(f"big paste split into {len(chunks)} nodes")
        except Exception:
            pass
        _log.info("[warm split] %s — paste split into %d chunks (total %d chars)",
                  self.data.uuid[:8], len(chunks), len(full_content))

    def _add_majestic_action(self, ctx) -> None:
        """Prepend 'The Majestic' to the editor's standard context menu.
        Called by _SmartPrettyEdit.contextMenuEvent after it builds the
        styled menu but before showing it."""
        first = ctx.actions()[0] if ctx.actions() else None
        majestic_action = ctx.addAction("The Majestic")
        if first:
            ctx.removeAction(majestic_action)
            ctx.insertAction(first, majestic_action)
            ctx.insertSeparator(first)
        majestic_action.triggered.connect(self._launch_editor)

    # ─────────────────────────────────────────────────────────────────────────
    # BRIDGE — WRITE
    # ─────────────────────────────────────────────────────────────────────────

    def _write_bridge(self) -> None:
        """Write current state directly to the bridge JSON file.

        Writes in-place (no temp+replace) so QFileSystemWatcher never loses
        track of the file.  os.replace deletes+recreates on Windows which
        drops the path from the watcher — a known issue that also prevents
        future proxying through a networked file layer.
        """
        if not self._bridge_path:
            return
        payload = {
            "version":   1,
            "node_uuid": self.data.uuid,
            "title":     self.data.title,
            "body_text": self.data.body_text,
            "writer":    "intricate",
            "timestamp": time.time(),
        }
        try:
            self._bridge_writing = True
            with open(self._bridge_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:
            _log.warning(f"[WarmNode] bridge write failed: {e}")
        finally:
            QTimer.singleShot(150, self._clear_bridge_writing)

    def _clear_bridge_writing(self) -> None:
        self._bridge_writing = False

    # ─────────────────────────────────────────────────────────────────────────
    # BRIDGE — WATCH
    # ─────────────────────────────────────────────────────────────────────────

    def _start_bridge_watcher(self) -> None:
        """Create a QFileSystemWatcher on the bridge file."""
        self._stop_bridge_watcher()
        if not self._bridge_path:
            return
        self._bridge_watcher = QFileSystemWatcher([self._bridge_path])
        self._bridge_watcher.fileChanged.connect(self._on_bridge_file_changed)
        watched = self._bridge_watcher.files()
        _log.info(f"[WarmNode] bridge watcher started — watching {len(watched)} file(s): {watched}")

    def _stop_bridge_watcher(self) -> None:
        """Disconnect and discard the current bridge watcher."""
        if self._bridge_watcher:
            try:
                self._bridge_watcher.fileChanged.disconnect()
            except RuntimeError:
                pass
            self._bridge_watcher.deleteLater()
            self._bridge_watcher = None

    def _on_bridge_file_changed(self, path: str) -> None:
        """Watcher callback — defensive re-add, then debounce."""
        _log.log(5, "[WarmNode] bridge file changed signal — writing=%s path=%s",
                 self._bridge_writing, path)
        if self._bridge_writing:
            _log.log(5, "[WarmNode] bridge change ignored — we are the writer")
            return
        # Some editors delete+recreate — re-add if missing from watch list
        if self._bridge_watcher and path not in self._bridge_watcher.files():
            _log.log(5, "[WarmNode] bridge path dropped from watcher — re-adding")
            if os.path.exists(path):
                self._bridge_watcher.addPath(path)
        self._bridge_debounce.start()

    def _process_bridge_change(self) -> None:
        """Read the bridge file and apply changes from Eddie."""
        _log.log(5, "[WarmNode] _process_bridge_change firing — path=%s", self._bridge_path)
        if not self._bridge_path:
            return
        try:
            with open(self._bridge_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError, FileNotFoundError) as e:
            _log.log(5, "[WarmNode] bridge read failed: %s", e)
            return  # missing or mid-write partial file — skip silently

        writer = data.get("writer")
        _log.log(5, "[WarmNode] bridge read — writer=%s title=%s", writer, data.get("title", "")[:20])
        if writer == "intricate":
            _log.log(5, "[WarmNode] bridge change ignored — echo of our own write")
            return  # echo of our own write

        # Apply body_text changes
        new_body = data.get("body_text", "")
        body_changed = new_body != self.data.body_text
        if body_changed:
            self.data.body_text = new_body
            if self._editor:
                self._editor.blockSignals(True)
                # Bridge writes are plain text; legacy HTML payloads (old
                # pre-2026-04-18 sessions) still round-trip to plain via
                # the same helper used on construction.
                self._editor.setPlainText(_html_to_plain(new_body))
                self._editor.blockSignals(False)
            else:
                # Lazy-editor mode (idle): paint_content renders from
                # data.body_text, so force a repaint to reflect the
                # bridge-pushed change on the canvas.
                self.update()

        # Apply title changes
        new_title = data.get("title", "")
        if new_title != self.data.title:
            self.data.title = new_title
            self.update()

        if body_changed:
            self._auto_fit_height()

    # ─────────────────────────────────────────────────────────────────────────
    # BRIDGE — LAUNCH
    # ─────────────────────────────────────────────────────────────────────────

    def _launch_editor(self) -> None:
        """
        Launch Notepad++ Duplex+ Turbo with a bidirectional bridge file.

        The bridge JSON is written first, then the editor is launched with
        --bridge <path>.  A QFileSystemWatcher monitors the file for changes
        from the editor side.
        """
        _log.info(f"[WarmNode] _launch_editor called — uuid={self.data.uuid[:8]}")
        # Clean up any stale bridge session — this disconnects debounce signals,
        # so reconnect them immediately for the new session.
        self._teardown_bridge()
        self._bridge_debounce.timeout.connect(self._process_bridge_change)
        self._bridge_write_debounce.timeout.connect(self._write_bridge)

        # Create bridge file — sanitise uuid to prevent path traversal
        import re
        safe_uuid = re.sub(r'[^a-zA-Z0-9_-]', '', self.data.uuid)
        if not safe_uuid:
            _log.warning("[WarmNode] Invalid uuid — cannot create bridge")
            return
        os.makedirs(str(_BRIDGE_DIR), exist_ok=True)
        self._bridge_path = str(_BRIDGE_DIR / f".warm_bridge_{safe_uuid}.json")
        self._write_bridge()

        # Resolve editor command
        cmd = self._resolve_editor_cmd()
        if not cmd:
            _log.warning("[WarmNode] No editor found — cannot launch")
            return

        try:
            _log.log(5, "[WarmNode] Launching editor cmd=%s", cmd)
            proc = subprocess.Popen(cmd, stderr=subprocess.PIPE)
            _log.info(f"[WarmNode] Launched editor (pid={proc.pid}): {cmd}")

            # Monitor for early crash — if the subprocess exits within 2 seconds,
            # log its stderr so silent import errors become visible.
            def _watch_early_exit():
                import time
                time.sleep(2)
                if proc.poll() is not None:
                    stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
                    _log.warning(f"[WarmNode] Editor exited early (code={proc.returncode}): {stderr[:500]}")
                else:
                    # Process is still running — release stderr to avoid blocking
                    if proc.stderr:
                        proc.stderr.close()
            import threading
            threading.Thread(target=_watch_early_exit, daemon=True).start()

            self._start_bridge_watcher()
            self._roll_up_curtains()
        except Exception as e:
            _log.warning(f"[WarmNode] Failed to launch editor: {e}")

    def _resolve_editor_cmd(self) -> list[str] | None:
        """Build the subprocess command list for the editor.

        Resolution order for the warm_editor setting:
            1. Absolute or relative path → resolve directly
            2. Bare filename → scan sibling directories on Desktop
               (Single Shared Braincell apps live next to each other)
               Prefers source repos (main.py) over frozen .exe builds
            3. Bare filename → shutil.which() (PATH fallback)
        """
        import shutil
        import pretty_widgets.utils.settings as _settings
        editor_path = _settings.get("apps", "warm_editor", "").strip()

        if not editor_path:
            _log.log(5, "[WarmNode] warm_editor setting is empty")
            return None

        p = Path(editor_path).resolve()
        _log.log(5, "[WarmNode] warm_editor raw=%r resolved=%s", editor_path, p)

        # If direct resolution doesn't find a file, try alternative lookups
        if not p.exists():
            _log.log(5, "[WarmNode] resolved path does not exist, trying alternatives")
            # Desktop sibling scan first — finds the source repo (main.py)
            # over any stale frozen build that might be on PATH
            desktop = Path(__file__).resolve().parent.parent.parent
            found = self._find_editor_on_desktop(desktop, editor_path)
            if found:
                p = found
                _log.log(5, "[WarmNode] found via Desktop sibling: %s", p)
            else:
                # Last resort — check PATH for a frozen .exe
                which = shutil.which(editor_path)
                if which:
                    p = Path(which)
                    _log.log(5, "[WarmNode] found via which (PATH): %s", p)
                else:
                    _log.warning("[WarmNode] warm_editor not found: %s", editor_path)
                    return None

        # Reject paths with shell metacharacters
        raw = str(p)
        if any(c in raw for c in ('&', '|', ';', '`', '$', '\n')):
            _log.warning("[WarmNode] warm_editor rejected — suspicious characters: %s", editor_path)
            return None

        bridge = self._validated_bridge_path()
        if bridge is None:
            return None

        # Directory with main.py → run from source
        if p.is_dir() and (p / "main.py").exists():
            cmd = [sys.executable, str(p / "main.py"), "--bridge", bridge]
            _log.log(5, "[WarmNode] resolved to directory with main.py: %s", cmd)
            return cmd
        # Executable file
        if p.is_file() and p.suffix in ('.exe', '.py', '.pyw'):
            cmd = [str(p), "--bridge", bridge]
            _log.log(5, "[WarmNode] resolved to executable: %s", cmd)
            return cmd

        _log.warning("[WarmNode] warm_editor path not found or not an executable: %s (resolved: %s)",
                     editor_path, p)
        return None

    @staticmethod
    def _find_editor_on_desktop(desktop: Path, editor_name: str) -> Path | None:
        """Scan Desktop siblings for the editor — matches .exe by name or directory with main.py.

        Normalisation replaces '+' with 'plus' before stripping non-alnum,
        so 'Notepad++ Duplex+ Turbo' → 'notepadplusplusduplexplusturbo'
        matches exe stem 'NotepadPlusPlusDuplexPlusTurbo' exactly.
        """
        stem = Path(editor_name).stem  # "NotepadPlusPlusDuplexPlusTurbo"
        if not desktop.is_dir():
            return None
        import re
        def _norm(s: str) -> str:
            return re.sub(r'[^a-z0-9]', '', s.lower().replace('+', 'plus'))
        norm_stem = _norm(stem)
        if not norm_stem:
            return None
        for child in desktop.iterdir():
            if not child.is_dir():
                continue
            if _norm(child.name) != norm_stem:
                continue
            # Prefer directory with main.py (dev/source mode) over frozen .exe
            if (child / "main.py").is_file():
                return child
            exe = child / editor_name
            if exe.is_file():
                return exe
        return None

    def _validated_bridge_path(self) -> str | None:
        """Return the bridge path only if it lives inside the expected directory."""
        if not self._bridge_path:
            return None
        bp = Path(self._bridge_path).resolve()
        expected = _BRIDGE_DIR.resolve()
        if not str(bp).startswith(str(expected)):
            _log.warning(f"[WarmNode] bridge path outside expected directory: {bp}")
            return None
        return str(bp)

    def _teardown_bridge(self) -> None:
        """Stop watching and clean up the bridge file."""
        self._bridge_debounce.stop()
        try:
            self._bridge_debounce.timeout.disconnect(self._process_bridge_change)
        except RuntimeError:
            pass
        self._bridge_write_debounce.stop()
        try:
            self._bridge_write_debounce.timeout.disconnect(self._write_bridge)
        except RuntimeError:
            pass
        self._stop_bridge_watcher()
        if self._bridge_path:
            try:
                os.remove(self._bridge_path)
            except FileNotFoundError:
                pass
            except OSError:
                pass
            self._bridge_path = None

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def _roll_up_curtains(self) -> None:
        """Collapse the main window to its HUD strip so the editor gets focus."""
        try:
            views = self.scene().views() if self.scene() else []
            if not views:
                return
            win = views[0].window()
            if hasattr(win, 'is_collapsed') and not win.is_collapsed:
                win.toggle_curtains()
        except Exception:
            pass

    def mouseDoubleClickEvent(self, event) -> None:
        """
        Double-click zones:

            Body zone   → lazy-build the inline editor, focus it
            Elsewhere   → shelf toggle (BaseNode default)
        """
        if self._body_rect().contains(event.pos()):
            # First double-click in the body builds the editor; subsequent
            # double-clicks reuse the existing hidden editor (no rebuild).
            self._ensure_body_editor()
            if self.scene() and self.scene().views():
                self.scene().views()[0].setFocusPolicy(Qt.StrongFocus)
            # start_edit positions, shows, and focuses the proxy in one
            # pass — the same flow AboutNode and TextNode use.
            self._editor.start_edit(
                _html_to_plain(self.data.body_text),
                self._body_rect(),
                select_all=False,
            )
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event) -> None:
        """Restore view focus policy when the node loses focus."""
        if self.scene() and self.scene().views():
            self.scene().views()[0].setFocusPolicy(Qt.NoFocus)
        super().focusOutEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        # Emoji + title — fully delegated to BaseNode
        super().paint_content(painter)
        # Body text — painted from data.body_text in the idle state so
        # the node looks identical to its active-edit state without
        # paying the editor construction cost until the user actually
        # double-clicks the body zone.  When the editor is alive and
        # its proxy is visible, let the editor do its own paint (skip).
        if (self._editor is not None
                and getattr(self._editor, 'proxy', None) is not None
                and self._editor.proxy.isVisible()):
            return
        body = self.data.body_text
        if not body:
            return

        fkey = (Theme.warmBodyFontFamily, Theme.warmBodyFontSize)
        cached = WarmNode._SHARED_BODY_FONTS.get(fkey)
        if cached is None:
            f = QFont(Theme.warmBodyFontFamily, Theme.warmBodyFontSize)
            cached = (f, QFontMetrics(f))
            WarmNode._SHARED_BODY_FONTS[fkey] = cached
        font, _fm = cached

        painter.save()
        painter.setFont(font)
        painter.setPen(QColor(Theme.textPrimary))
        # Match the editor's 4px document margin (normalize_layout=False)
        # so idle paint and active editor align on both axes.
        body_rect = self._body_rect().adjusted(4, 4, 0, 0)
        painter.drawText(
            body_rect,
            Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop,
            body,
        )
        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # GEOMETRY
    # ─────────────────────────────────────────────────────────────────────────

    def _auto_fit_title_width(self) -> None:
        """Grow the node's width if the current title would overflow.
        Never shrinks — preserves user corner-drag resizes and default
        widths that already fit.  Measured with the same font /
        style / size the BaseNode title-paint uses, so the layout
        calculation matches what will render.

        Body text wrapping is unaffected — the whole point is to
        accommodate a long title without forcing the body columns to
        widen.  If the node is already wider than the title needs,
        nothing changes."""
        if not self.data.title:
            return
        from PySide6.QtGui import QFont, QFontMetrics
        r = self.rect()
        font = QFont(self._TITLE_FONT, max(1, Theme.aboutFontSize + self._TITLE_FONT_BUMP))
        font.setStyleName(self._TITLE_STYLE)
        fm = QFontMetrics(font)
        title_w = fm.horizontalAdvance(self.data.title)
        pad = Theme.nodeTextPaddingLeft
        needed = title_w + pad * 2 + 8   # 8 px trailing buffer
        if needed > r.width():
            self.prepareGeometryChange()
            self.setRect(QRectF(r.x(), r.y(), needed, r.height()))
            self.data.width = needed

    def _auto_fit_height(self, shrink: bool = False) -> None:
        """Resize the node to fit the current text content.

        shrink=False (default): grow-only.  Expands the node when text
        overflows the current height; never reduces below the current
        setting.  Preserves any manual corner-drag resize the user has
        applied, and preserves a user's custom height across session
        reloads.

        shrink=True: snug-to-content.  Both grows and shrinks so the
        node exactly matches its body text (plus the button zone,
        padding, and min-height floor).  Used by the markdown-split
        spawner — freshly-spawned chain nodes pack tightly against
        their content instead of carrying the default empty space at
        the bottom.  Those nodes have never been resized manually, so
        shrinking is safe.
        """
        r = self.rect()
        body_w = r.width() - PADDING * 2
        if self._editor is not None:
            # Active edit: measure via the editor's document (most accurate
            # because it respects the same layout Qt will render with).
            self._editor.document().setTextWidth(body_w)
            doc_h = self._editor.document().size().height()
        else:
            # Idle (lazy): measure via QFontMetrics.boundingRect with word
            # wrap — identical to what paint_content renders, so the fit
            # is visually correct without paying the editor construction
            # cost.  Called during session restore / MarkdownNode's snug-
            # fit spawn flow for 146 WarmNodes that never had an editor.
            fkey = (Theme.warmBodyFontFamily, Theme.warmBodyFontSize)
            cached = WarmNode._SHARED_BODY_FONTS.get(fkey)
            if cached is None:
                _f = QFont(Theme.warmBodyFontFamily, Theme.warmBodyFontSize)
                cached = (_f, QFontMetrics(_f))
                WarmNode._SHARED_BODY_FONTS[fkey] = cached
            fm = cached[1]
            body = self.data.body_text or ""
            if body:
                from PySide6.QtCore import QRect as _QRect
                probe_rect = _QRect(0, 0, int(body_w), 100000)
                bounding = fm.boundingRect(
                    probe_rect, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, body,
                )
                doc_h = bounding.height() + 6.0  # match CSS padding-bottom:3px × 2 headroom
            else:
                doc_h = 0.0
        # Total: body top offset + document height + padding + a small buffer
        needed = BODY_TOP + doc_h + PADDING + 16.0
        target = max(needed, self._min_height)

        if shrink:
            # Snug to content — both grow and shrink, clamped at min_height
            changed = abs(target - r.height()) > 0.5
        else:
            # Grow only — never override a user-set height with something smaller
            changed = needed > r.height()
            target  = needed  # grow-only path doesn't clamp; existing behaviour

        if changed:
            self.prepareGeometryChange()
            new_rect = QRectF(r.x(), r.y(), r.width(), target)
            self.setRect(new_rect)
            self.data.height = target

    def setRect(self, rect: QRectF) -> None:
        super().setRect(rect)
        # Editor may be None (lazy, idle) or present (after first
        # activation) — only reposition when it actually exists.
        if self._editor is not None and self._editor.proxy is not None:
            self._editor.proxy.setGeometry(self._body_rect())

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _demolition_pre(self) -> None:
        # WarmNode → Majestic bridge owns a file watcher + daemon worker;
        # _teardown_bridge handles both.  PrettyEdit teardown severs the
        # editor's own proxy widget internally.
        self._teardown_bridge()
        if self._editor:
            self._editor.teardown()
        self._editor = None

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'WarmNode':
        return WarmNode(WarmNodeData.from_dict(data))

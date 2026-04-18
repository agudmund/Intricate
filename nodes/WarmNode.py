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
from PySide6.QtCore import Qt, QRectF, QPointF, QFileSystemWatcher, QTimer
from PySide6.QtGui import QPainter, QFont, QColor, QPen

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


class _SmartPrettyEdit(PrettyEdit):
    """PrettyEdit subclass that intercepts oversized pastes before they land
    in the document.

    On a paste that would push the document past the owning WarmNode's
    split threshold, the paste is diverted to the node's chain-split
    routine instead of being inserted. This prevents Qt from attempting
    to render multi-megabyte text in a single QTextEdit proxy — the
    exact condition that crashes Qt6Core.dll during scene load. Small
    pastes pass through unchanged.
    """

    def __init__(self, *args, threshold: int = 0, on_oversized_paste=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._split_threshold = threshold
        self._on_oversized_paste = on_oversized_paste

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

    def __init__(self, data: WarmNodeData | None = None):
        if data is None:
            data = WarmNodeData()
        super().__init__(data)

        # ── Body text editor ──────────────────────────────────────────────────
        self._editor: PrettyEdit | None = None
        self._build_body_editor()

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

    def _build_body_editor(self) -> None:
        """Build the PrettyEdit proxy, always visible — it IS the content.

        Uses the smart-paste variant so a paste that would push the body
        past WARM_SPLIT_THRESHOLD auto-splits into a chain of sibling
        WarmNodes instead of trying to render a single huge document."""
        self._editor = _SmartPrettyEdit(
            self,
            font_family=Theme.healthFontFamily,
            font_size=9,
            font_color=Theme.textPrimary,
            always_visible=True,
            normalize_layout=False,
            threshold=WARM_SPLIT_THRESHOLD,
            on_oversized_paste=self._split_oversized_paste,
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

        # Extend the standard right-click menu with "Open in Notepad"
        self._editor.contextMenuEvent = self._editor_context_menu

        self._editor.proxy.setGeometry(self._body_rect())
        # Fit height on restore — accounts for layout constant changes across versions
        self._auto_fit_height()

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

    def _editor_context_menu(self, event) -> None:
        """Standard context menu with 'Open in Notepad' prepended."""
        from pretty_widgets.PrettyMenu import menu_stylesheet
        ctx = self._editor.createStandardContextMenu()
        ctx.setStyleSheet(menu_stylesheet())
        # Prepend our action before the standard Cut/Copy/Paste
        first = ctx.actions()[0] if ctx.actions() else None
        notepad_action = ctx.addAction("Open in Notepad")
        if first:
            ctx.removeAction(notepad_action)
            ctx.insertAction(first, notepad_action)
            ctx.insertSeparator(first)
        notepad_action.triggered.connect(self._launch_editor)
        ctx.exec(event.globalPos())
        ctx.deleteLater()

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

            Body zone   → focus the inline QTextEdit editor
            Elsewhere   → shelf toggle (BaseNode default)
        """
        if self._body_rect().contains(event.pos()):
            if self.scene() and self.scene().views():
                self.scene().views()[0].setFocusPolicy(Qt.StrongFocus)
            self._editor.proxy.setFocus()
            self._editor.setFocus(Qt.MouseFocusReason)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        """Fallback right-click — areas not covered by the body editor."""
        super().contextMenuEvent(event)

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

    # ─────────────────────────────────────────────────────────────────────────
    # GEOMETRY
    # ─────────────────────────────────────────────────────────────────────────

    def _auto_fit_height(self) -> None:
        """Resize the node to fit the current text content."""
        if not self._editor:
            return
        r = self.rect()
        # Tell the document to wrap at the current node width
        body_w = r.width() - PADDING * 2
        self._editor.document().setTextWidth(body_w)
        doc_h = self._editor.document().size().height()
        # Total: body top offset + document height + padding + a small buffer
        needed = BODY_TOP + doc_h + PADDING + 16.0
        if needed > r.height():
            self.prepareGeometryChange()
            new_rect = QRectF(r.x(), r.y(), r.width(), needed)
            self.setRect(new_rect)
            self.data.height = needed

    def setRect(self, rect: QRectF) -> None:
        super().setRect(rect)
        if self._editor and self._editor.proxy:
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

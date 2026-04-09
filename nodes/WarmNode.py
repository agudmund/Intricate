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

from PySide6.QtWidgets import QGraphicsProxyWidget
from pretty_widgets.PrettyMenu import StyledTextEdit as QTextEdit
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
BODY_TOP        = PADDING + EMOJI_SIZE + 4.0    # Body text starts here

# Bridge file lives alongside session data
_BRIDGE_DIR = Path(__file__).resolve().parent.parent / "Documents" / "data"


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
        self._editor: QTextEdit | None = None
        self._editor_proxy: QGraphicsProxyWidget | None = None
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
        """Build the QTextEdit proxy, hidden until double-clicked."""
        self._editor = QTextEdit()
        self._editor.setFrameStyle(0)
        self._editor.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {Theme.textPrimary};
                font-family: {Theme.healthFontFamily};
                font-size: 9pt;
                border: none;
                padding: 12px 0px 0px 0px;
                selection-background-color: {Theme.primaryBorder};
            }}
        """)
        self._editor.setPlainText(self.data.body_text)
        self._editor.textChanged.connect(self._on_text_changed)

        # Extend the standard right-click menu with "Open in Notepad"
        self._editor.contextMenuEvent = self._editor_context_menu

        self._editor_proxy = QGraphicsProxyWidget(self)
        self._editor_proxy.setWidget(self._editor)
        self._editor_proxy.setGeometry(self._body_rect())
        self._editor_proxy.show()   # WarmNode shows editor by default — it IS the content

    def _on_text_changed(self) -> None:
        """Sync text to data on every keystroke — no explicit commit needed."""
        if self._editor:
            self.data.body_text = self._editor.toPlainText()
            # Propagate inline edits to bridge if active
            if self._bridge_path and os.path.exists(self._bridge_path):
                self._bridge_write_debounce.start()

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
        """Atomic write of current state to the bridge JSON file."""
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
        tmp = self._bridge_path + ".tmp"
        try:
            self._bridge_writing = True
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp, self._bridge_path)
        except OSError as e:
            _log.warning(f"[WarmNode] bridge write failed: {e}")
        finally:
            # Clear the guard after the watcher event has had time to fire
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
        if self._bridge_writing:
            return
        # Some editors delete+recreate — re-add if missing from watch list
        if self._bridge_watcher and path not in self._bridge_watcher.files():
            if os.path.exists(path):
                self._bridge_watcher.addPath(path)
        self._bridge_debounce.start()

    def _process_bridge_change(self) -> None:
        """Read the bridge file and apply changes from Eddie."""
        if not self._bridge_path:
            return
        try:
            with open(self._bridge_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError, FileNotFoundError):
            return  # missing or mid-write partial file — skip silently

        if data.get("writer") == "intricate":
            return  # echo of our own write

        # Apply body_text changes
        new_body = data.get("body_text", "")
        body_changed = new_body != self.data.body_text
        if body_changed:
            self.data.body_text = new_body
            if self._editor:
                self._editor.blockSignals(True)
                self._editor.setPlainText(new_body)
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
        # Clean up any stale bridge session
        self._teardown_bridge()

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
            2. Bare filename → shutil.which() (checks PATH)
            3. Bare filename → scan sibling directories on Desktop
               (Single Shared Braincell apps live next to each other)
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
            # Try shutil.which (checks PATH)
            which = shutil.which(editor_path)
            if which:
                p = Path(which)
                _log.log(5, "[WarmNode] found via which: %s", p)
            else:
                # Scan sibling directories on Desktop for the bare filename
                # or a directory whose main.py matches the app name pattern
                desktop = Path(__file__).resolve().parent.parent.parent
                found = self._find_editor_on_desktop(desktop, editor_path)
                if found:
                    p = found
                    _log.log(5, "[WarmNode] found via Desktop sibling: %s", p)
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
        self._bridge_write_debounce.stop()
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
            self._editor_proxy.setFocus()
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
        if self._editor_proxy:
            self._editor_proxy.setGeometry(self._body_rect())

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        self._teardown_bridge()
        if self._editor_proxy:
            self._editor_proxy.hide()
        if self.scene() and self.scene().views():
            self.scene().views()[0].setFocusPolicy(Qt.NoFocus)
        self._editor = None
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'WarmNode':
        return WarmNode(WarmNodeData.from_dict(data))

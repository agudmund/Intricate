#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/LogNode.py LogNode class
-Live tail of nodal.log — reads and auto-refreshes the current session log for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path

from PySide6.QtWidgets import QGraphicsProxyWidget
from widgets.PrettyMenu import StyledTextEdit as QTextEdit
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QPainter, QFont, QColor, QPen

from nodes.BaseNode import BaseNode
from data.LogNodeData import LogNodeData
from graphics.Theme import Theme


_BUTTON_ZONE_H = 40.0
_PAD           = 8.0
_MAX_LINES     = 400   # keep the last N lines to stay snappy


class LogNode(BaseNode):
    """
    Displays a live tail of the current session log file (nodal.log).

    The log path is resolved from [shared] log_dir in settings.toml,
    falling back to ./logs/nodal.log.

    A QFileSystemWatcher fires on every write to the file; a 1.5s poll
    timer backs it up in case the watcher loses track after rotation.
    Content is always re-read from disk — nothing is persisted in the session.
    """
    _has_depth_toggle = True

    def __init__(self, data: LogNodeData | None = None):
        if data is None:
            data = LogNodeData()
        super().__init__(data)

        self.setBrush(self._bg_color())
        _w = Theme.nodeBorderWidth
        self.normal_pen   = QPen(QColor(Theme.aboutBorderColor),         _w)
        self.hover_pen    = QPen(QColor(Theme.aboutBorderHoverColor),    _w)
        self.selected_pen = QPen(QColor(Theme.aboutBorderSelectedColor), _w)
        self.current_pen  = self.normal_pen
        self.setPen(self.current_pen)
        self._min_height  = Theme.aboutMinHeight
        self._apply_depth()

        self._editor: QTextEdit | None = None
        self._editor_proxy: QGraphicsProxyWidget | None = None
        self._build_editor()

        # ── File tail ─────────────────────────────────────────────────────────
        self._log_path = self._resolve_log_path()

        from PySide6.QtCore import QFileSystemWatcher
        self._watcher = QFileSystemWatcher()
        if self._log_path.exists():
            self._watcher.addPath(str(self._log_path))
        self._watcher.fileChanged.connect(self._on_file_changed)

        self._poll_timer = QTimer()
        self._poll_timer.setInterval(1500)
        self._poll_timer.timeout.connect(self._refresh)
        self._poll_timer.start()

        self._refresh()

    # ─────────────────────────────────────────────────────────────────────────

    def _bg_color(self) -> QColor:
        c = QColor(Theme.aboutBgColorFront if self.data.depth_front else Theme.aboutBgColor)
        c.setAlpha(Theme.aboutBgAlpha)
        return c

    def _apply_depth(self) -> None:
        super()._apply_depth()
        self.setBrush(self._bg_color())

    # ─────────────────────────────────────────────────────────────────────────
    # EDITOR
    # ─────────────────────────────────────────────────────────────────────────

    def _build_editor(self) -> None:
        self._editor = QTextEdit()
        self._editor.setReadOnly(True)
        self._editor.setFrameShape(QTextEdit.NoFrame)
        self._editor.setFont(QFont("Consolas", 7))
        self._editor.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {Theme.aboutFontColor};
                font-family: Consolas, "Courier New", monospace;
                font-size: 7pt;
                border: none;
                padding: 0px;
            }}
            QScrollBar:vertical {{
                width: 4px;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {Theme.primaryBorder};
                border-radius: 2px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        self._editor_proxy = QGraphicsProxyWidget(self)
        self._editor_proxy.setWidget(self._editor)
        self._position_editor()
        self._editor_proxy.show()

    def _position_editor(self) -> None:
        r = self.rect()
        self._editor_proxy.setGeometry(QRectF(
            r.left()  + _PAD,
            r.top()   + _BUTTON_ZONE_H,
            r.width() - _PAD * 2,
            r.height() - _BUTTON_ZONE_H - _PAD,
        ))

    # ─────────────────────────────────────────────────────────────────────────
    # LOG TAIL
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_log_path() -> Path:
        try:
            from utils.settings import get as _get
            log_dir = _get("shared", "log_dir", default=None)
            if log_dir:
                return Path(log_dir) / "nodal.log"
        except Exception:
            pass
        return Path(__file__).resolve().parent.parent / "logs" / "nodal.log"

    def _refresh(self) -> None:
        if self._editor is None:
            return
        if not self._log_path.exists():
            # Re-register if the file reappeared (e.g. after rotation)
            if self._watcher.files():
                pass
            return
        try:
            # Re-add to watcher if the path dropped out (file was rotated/recreated)
            if str(self._log_path) not in self._watcher.files():
                self._watcher.addPath(str(self._log_path))

            text = self._log_path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            tail = "\n".join(lines[-_MAX_LINES:])

            # Only update if content actually changed — avoids cursor flicker
            if self._editor.toPlainText() != tail:
                sb = self._editor.verticalScrollBar()
                at_bottom = sb.value() >= sb.maximum() - 4

                self._editor.setPlainText(tail)

                if at_bottom:
                    sb.setValue(sb.maximum())
        except Exception:
            pass

    def _on_file_changed(self, _path: str) -> None:
        """QFileSystemWatcher fires here on every write."""
        self._refresh()

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT + LAYOUT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        pass  # editor covers the content area

    def setRect(self, rect) -> None:
        super().setRect(rect)
        if hasattr(self, '_editor_proxy') and self._editor_proxy:
            self._position_editor()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        self._poll_timer.stop()
        try:
            self._watcher.fileChanged.disconnect(self._on_file_changed)
        except RuntimeError:
            pass
        if self._editor_proxy:
            self._editor_proxy.hide()
        self._editor = None
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION — content is always live, only geometry is saved
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'LogNode':
        return LogNode(LogNodeData.from_dict(data))

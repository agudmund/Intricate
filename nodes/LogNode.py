#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/LogNode.py LogNode class
-Live tail of nodal.log — reads and auto-refreshes the current session log for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path

from PySide6.QtWidgets import QGraphicsProxyWidget
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QPainter, QFont, QColor

from nodes.BaseNode import BaseNode
from data.LogNodeData import LogNodeData
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.PrettyEdit import PrettyEdit


_BUTTON_ZONE_H = 40.0
_PAD           = 8.0
_MAX_LINES     = 400   # keep the last N lines to stay snappy


class LogNode(BaseNode):
    """
    Displays a live tail of the current session log file (intricate.log).

    The log path is resolved from [shared] log_dir in settings.toml,
    falling back to Documents/Data/Logs/intricate.log.

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
        self._min_height  = Theme.aboutMinHeight
        self._apply_depth()

        self._editor: PrettyEdit | None = None
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
        c.setAlpha(Theme.aboutTransparency)
        return c

    def _apply_depth(self) -> None:
        super()._apply_depth()
        self.setBrush(self._bg_color())

    # ─────────────────────────────────────────────────────────────────────────
    # EDITOR
    # ─────────────────────────────────────────────────────────────────────────

    def _build_editor(self) -> None:
        self._editor = PrettyEdit(
            self,
            font_family="Consolas",
            font_size=7,
            font_color=Theme.nodeFontColor,
            always_visible=True,
            read_only=True,
            scrollbar=True,
            scrollbar_width=4,
        )
        self._position_editor()

    def _position_editor(self) -> None:
        r = self.rect()
        self._editor.position(QRectF(
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
        # Reuse the logger's resolver so LogNode sees the same directory the
        # Rust/Python logger writes into — settings.toml override, then the
        # Documents/Data/Logs default.
        try:
            from shared_braincell.logger import _resolve_log_dir
            logs_dir = _resolve_log_dir()
        except Exception:
            logs_dir = Path(__file__).resolve().parent.parent / "Documents" / "Data" / "Logs"

        # Most recent timestamped log (Rust logger: intricate_YYYYMMDD-HH.MM.SS.log
        # on current builds, legacy intricate_YYYY-MM-DD_HHMMSS.log on older ones)
        candidates = sorted(logs_dir.glob("intricate_*.log"), key=lambda p: p.stat().st_mtime)
        if candidates:
            return candidates[-1]
        return logs_dir / "intricate.log"

    def _refresh(self) -> None:
        # Orphan-timer guard (see BaseNode._timer_slot_alive).
        if not self._timer_slot_alive('_poll_timer'):
            return
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
        if hasattr(self, '_editor') and self._editor:
            self._position_editor()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    _demolition_timers = [('_poll_timer', '_refresh')]

    def _demolition_pre(self) -> None:
        # _watcher is a QFileSystemWatcher owned by the node — peer signal,
        # disconnect inline.
        try:
            self._watcher.fileChanged.disconnect(self._on_file_changed)
        except (RuntimeError, TypeError, AttributeError):
            pass
        if self._editor:
            self._editor.teardown()
        self._editor = None

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION — content is always live, only geometry is saved
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'LogNode':
        return LogNode(LogNodeData.from_dict(data))

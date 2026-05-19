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
from pretty_widgets.PrettySlider import slider as pretty_slider


_BUTTON_ZONE_H = 40.0
_PAD           = 8.0
_SLIDER_COL_W  = 30.0   # detached scroll-slider column on the right edge
_MAX_LINES     = 400    # keep the last N lines to stay snappy


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
        self._scroll_slider = None
        self._scroll_slider_proxy: QGraphicsProxyWidget | None = None
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
            scrollbar=False,
        )
        # Native scrollbar is hidden via the PrettyEdit flag above; we also
        # set the policy explicitly so a downstream code path can't quietly
        # bring it back and paint a competing handle next to our slider.
        self._editor.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Detached scroll slider — sticker handle on its own column to the
        # right of the editor. handle_size=28 + the canonical PNG handle
        # match the sidebar's blur/zoom sliders; PrettySlider's own
        # stylesheet already supplies a transparent groove, so we MUST
        # NOT override setStyleSheet here or the default Qt blue rail
        # comes back.
        self._scroll_slider = pretty_slider(
            Qt.Orientation.Vertical,
            handle_icon="slider_handle_vertical.png",
            handle_size=28,
            range=(0, 100),
            value=0,
            invertedAppearance=True,
        )
        self._scroll_slider.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._scroll_slider.setAutoFillBackground(False)

        self._scroll_slider_proxy = QGraphicsProxyWidget(self)
        self._scroll_slider_proxy.setWidget(self._scroll_slider)

        # Bidirectional bridge — scrollbar range/value drive the slider;
        # the slider drives the scrollbar when the user drags.  The
        # feedback loop self-closes: setValue is a no-op when the value
        # hasn't moved, so each side stops re-emitting after one bounce.
        vsb = self._editor.verticalScrollBar()
        vsb.rangeChanged.connect(self._scroll_slider.setRange)
        vsb.valueChanged.connect(self._scroll_slider.setValue)
        self._scroll_slider.valueChanged.connect(vsb.setValue)

        self._position_editor()

    def _position_editor(self) -> None:
        r = self.rect()
        self._editor.position(QRectF(
            r.left()  + _PAD,
            r.top()   + _BUTTON_ZONE_H,
            r.width() - _PAD * 2 - _SLIDER_COL_W,
            r.height() - _BUTTON_ZONE_H - _PAD,
        ))
        if self._scroll_slider_proxy is not None:
            self._scroll_slider_proxy.setGeometry(QRectF(
                r.right() - _PAD - _SLIDER_COL_W,
                r.top()   + _BUTTON_ZONE_H,
                _SLIDER_COL_W,
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
                at_bottom    = sb.value() >= sb.maximum() - 4
                saved_value  = sb.value()

                self._editor.setPlainText(tail)

                # at_bottom → follow the tail; otherwise restore the user's
                # parked position so reading mid-log isn't disrupted every
                # 1.5s when a new line lands. setPlainText resets the
                # scrollbar to 0 by default, which made the slider snap to
                # the top on every refresh.
                if at_bottom:
                    sb.setValue(sb.maximum())
                else:
                    sb.setValue(min(saved_value, sb.maximum()))
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

    _demolition_timers  = [('_poll_timer', '_refresh')]
    _demolition_proxies = ['_scroll_slider_proxy']

    def _demolition_pre(self) -> None:
        # _watcher is a QFileSystemWatcher owned by the node — peer signal,
        # disconnect inline.
        try:
            self._watcher.fileChanged.disconnect(self._on_file_changed)
        except (RuntimeError, TypeError, AttributeError):
            pass
        # Sever slider ↔ scrollbar wiring before the crew tears the proxy
        # down — a drag landing between scene-leave and removeItem must
        # not dispatch valueChanged onto a dying scrollbar.
        if self._scroll_slider is not None and self._editor is not None:
            vsb = self._editor.verticalScrollBar()
            for src_sig, dst in (
                (vsb.rangeChanged,                  self._scroll_slider.setRange),
                (vsb.valueChanged,                  self._scroll_slider.setValue),
                (self._scroll_slider.valueChanged,  vsb.setValue),
            ):
                try:
                    src_sig.disconnect(dst)
                except (RuntimeError, TypeError, AttributeError):
                    pass
        self._scroll_slider = None
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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/InfoNode.py InfoNode class
-A read-only display node showing version, era, and app identity for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QFont, QFontMetrics, QColor

from nodes.BaseNode import BaseNode
from data.InfoNodeData import InfoNodeData
from pretty_widgets.graphics.Theme import Theme


class InfoNode(BaseNode):
    _has_depth_toggle = True
    """
    Read-only node that displays app version and era.

    No editor, no editing — just a painted label that always
    reflects the current __version__ and __era__ from main.py.
    """

    _BODY_LINES = [
        "A gentle nodal space where thoughts interlink ideas transitioning thoughts to things",
        "",
        "A creative space where the next breath of air found room to grow into all that it could become",
        "",
        "Built using a single shared braincell",
        "By Yours Truly and various Intelligences",
        "",
        "    For enjoying",
    ]

    def __init__(self, data: InfoNodeData | None = None):
        if data is None:
            data = InfoNodeData()

        # Auto-size width from widest body line + padding
        from main import __version__, __era__, __version_history__
        body_font = QFont("Lato", max(1, Theme.aboutFontSize - 1))
        fm = QFontMetrics(body_font)
        history_lines = [f"  {line}" for line in __version_history__]
        all_lines = [f"Version {__version__}", __era__] + history_lines + self._BODY_LINES
        max_w = max(fm.horizontalAdvance(line) for line in all_lines)
        data.width = max(data.width, max_w + 30)

        # Auto-size height to fit every section — mirrors the per-line
        # y-advances in paint_content so content never clips.  Touched
        # when a new version history line or body stanza is added.
        _SECTION_PAD = 12          # gap before history and footnote sections
        _VERSION_GAP = 28          # gap between era line and description
        _VERSION_LINE_H = 18
        _BODY_LINE_H    = 16
        _HISTORY_LINE_H = 14
        _FOOT_LINE_H    = 14
        _FOOT_LINES     = 2        # "Nodes harmed" + "but many were aggressively fluffed"
        _TAIL_PAD       = 10       # breathing room under the last footnote line
        needed_below_title = (
            _VERSION_LINE_H * 2                     # Version + Era
            + _VERSION_GAP
            + _BODY_LINE_H * len(self._BODY_LINES)  # description stanza
            + _SECTION_PAD
            + _HISTORY_LINE_H * len(__version_history__)
            + _SECTION_PAD
            + _FOOT_LINE_H * _FOOT_LINES
            + _TAIL_PAD
        )
        # _body_top() includes the title band; use a representative value
        # so we don't have to instantiate super() first.  AboutNode's
        # _body_top is ~50 for the font sizes used here.
        needed_total = 50 + needed_below_title
        data.height = max(data.height, needed_total)

        super().__init__(data)
        self.setBrush(self._bg_color())
        self._apply_depth()

    def _bg_color(self) -> QColor:
        tint = getattr(self.data, 'node_tint', '')
        c = QColor(tint) if tint and QColor(tint).isValid() else QColor(Theme.aboutBgColor)
        c.setAlpha(Theme.aboutTransparency)
        return c

    def _apply_depth(self) -> None:
        super()._apply_depth()
        beh = getattr(self, 'behaviour', None)
        if beh:
            beh.bg_anim.stop()
            beh._bg_base    = None
            beh._current_bg = None
        self.setBrush(self._bg_color())

    def paint_content(self, painter: QPainter) -> None:
        from main import __version__, __era__, __version_history__

        painter.save()
        r = self.rect()
        pad = self._CONTENT_PAD
        top = self._content_top()

        # Title
        title_font = QFont(self._TITLE_FONT, max(1, Theme.aboutFontSize + self._TITLE_FONT_BUMP))
        title_font.setStyleName(self._TITLE_STYLE)
        painter.setFont(title_font)
        painter.setPen(QColor("#72b8b8"))   # Lombardi Lake variant
        painter.drawText(
            QRectF(r.left() + pad, r.top() + top, r.width() - pad * 2, self._TITLE_HEIGHT),
            Qt.AlignLeft | Qt.AlignTop,
            "Intricate",
        )

        # Version + Era
        body_font = QFont(self._BODY_FONT, max(1, Theme.aboutFontSize + self._BODY_FONT_BUMP))
        painter.setFont(body_font)
        painter.setPen(QColor(Theme.nodeFontColor))
        painter.setOpacity(0.85)
        y = r.top() + self._body_top()
        painter.drawText(
            QRectF(r.left() + pad, y, r.width() - pad * 2, 20),
            Qt.AlignLeft | Qt.AlignTop,
            f"Version {__version__}",
        )
        y += 18
        painter.drawText(
            QRectF(r.left() + pad, y, r.width() - pad * 2, 20),
            Qt.AlignLeft | Qt.AlignTop,
            __era__,
        )

        # Description
        y += 28
        for line in self._BODY_LINES:
            painter.drawText(
                QRectF(r.left() + pad, y, r.width() - pad * 2, 20),
                Qt.AlignLeft | Qt.AlignTop,
                line,
            )
            y += 16

        # Version history — rendered as authored prose, verbatim.  Lines
        # matching the current __version__ get a brighter opacity so the
        # "you are here" reads without any extra chrome.
        y += 12
        history_font = QFont("Lato", max(1, Theme.aboutFontSize - 2))
        painter.setFont(history_font)
        for line in __version_history__:
            is_current = line.startswith(f"{__version__} ")
            painter.setOpacity(0.85 if is_current else 0.55)
            painter.drawText(
                QRectF(r.left() + pad, y, r.width() - pad * 2, 16),
                Qt.AlignLeft | Qt.AlignTop,
                f"  {line}",
            )
            y += 14

        # Footnote
        y += 12
        footnote_font = QFont("Lato", max(1, Theme.aboutFontSize - 3))
        painter.setFont(footnote_font)
        painter.setOpacity(0.5)
        painter.drawText(
            QRectF(r.left() + pad, y, r.width() - pad * 2, 16),
            Qt.AlignLeft | Qt.AlignTop,
            "Nodes harmed: 0",
        )
        y += 14
        painter.drawText(
            QRectF(r.left() + pad, y, r.width() - pad * 2, 16),
            Qt.AlignLeft | Qt.AlignTop,
            "but many were aggressively fluffed",
        )

        painter.restore()

    def to_dict(self) -> dict:
        return self.data.to_dict()

    @staticmethod
    def from_dict(d: dict) -> 'InfoNode':
        return InfoNode(InfoNodeData.from_dict(d))

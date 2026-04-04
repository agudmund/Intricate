#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/GitNode.py GitNode class
-A mundane but necessary git status dashboard for all Desktop repos for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QPainter, QFont, QColor

from nodes.BaseNode import BaseNode
from data.GitNodeData import GitNodeData
from graphics.Theme import Theme
from utils.logger import setup_logger

_log = setup_logger("git")

_HEADER_H   = 44.0   # space for title above the list
_ROW_H      = 20.0   # height per repo row
_PAD        = 15.0
_DOT_R      = 5.0    # status dot radius
_POLL_MS    = 10000   # refresh every 10 seconds


def _scan_repos() -> list[tuple[str, bool]]:
    """Scan ~/Desktop for git repos. Returns [(name, is_dirty), ...] sorted."""
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        return []
    repos = []
    for folder in sorted(desktop.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        git_dir = folder / ".git"
        if not git_dir.exists():
            continue
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(folder),
                capture_output=True, text=True, timeout=5,
            )
            dirty = bool(result.stdout.strip())
            repos.append((folder.name, dirty))
        except Exception:
            repos.append((folder.name, True))  # assume dirty on error
    return repos


class GitNode(BaseNode):
    _has_depth_toggle = True
    _show_emoji_btn   = False
    """
    Dashboard node showing all Desktop git repos with red/green status dots.

    Green = clean (nothing to commit), Red = dirty (uncommitted changes).
    Auto-refreshes every 10 seconds.
    """

    def __init__(self, data: GitNodeData | None = None):
        if data is None:
            data = GitNodeData()
        super().__init__(data)

        c = QColor(Theme.aboutBgColor)
        c.setAlpha(Theme.aboutBgAlpha)
        self.setBrush(c)
        self._apply_depth()

        self._repos: list[tuple[str, bool]] = []
        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._refresh)
        self._poll_timer.start(_POLL_MS)
        # Initial scan deferred so the node appears immediately
        QTimer.singleShot(0, self._refresh)

    def _refresh(self) -> None:
        try:
            self._repos = _scan_repos()
            self.update()
        except RuntimeError:
            self._poll_timer.stop()

    def _bg_color(self) -> QColor:
        tint = getattr(self.data, 'node_tint', '')
        c = QColor(tint) if tint and QColor(tint).isValid() else QColor(Theme.aboutBgColor)
        c.setAlpha(Theme.aboutBgAlpha)
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
        painter.save()
        r = self.rect()

        # Title
        title_font = QFont("Chandler42", max(1, Theme.aboutFontSize + 2))
        painter.setFont(title_font)
        painter.setPen(QColor(Theme.nodeFontColor))
        painter.drawText(
            QRectF(r.left() + _PAD, r.top() + _HEADER_H - 20, r.width() - _PAD * 2, 24),
            Qt.AlignLeft | Qt.AlignTop,
            "Git Status",
        )

        # Repo list
        body_font = QFont("Lato", max(1, Theme.aboutFontSize - 1))
        painter.setFont(body_font)
        y = r.top() + _HEADER_H + 8

        if not self._repos:
            painter.setPen(QColor(Theme.nodeFontColor))
            painter.setOpacity(0.5)
            painter.drawText(
                QRectF(r.left() + _PAD, y, r.width() - _PAD * 2, _ROW_H),
                Qt.AlignLeft | Qt.AlignVCenter,
                "No git repos found on Desktop",
            )
        else:
            for name, dirty in self._repos:
                if y + _ROW_H > r.bottom():
                    break
                # Status dot
                dot_color = QColor("#c47a7a") if dirty else QColor("#7ac47a")
                painter.setBrush(dot_color)
                painter.setPen(Qt.NoPen)
                dot_x = r.left() + _PAD + _DOT_R
                dot_y = y + _ROW_H / 2
                painter.drawEllipse(QRectF(dot_x - _DOT_R, dot_y - _DOT_R, _DOT_R * 2, _DOT_R * 2))

                # Repo name
                painter.setPen(QColor(Theme.nodeFontColor))
                painter.setOpacity(0.85)
                painter.drawText(
                    QRectF(r.left() + _PAD + _DOT_R * 2 + 8, y, r.width() - _PAD * 2 - _DOT_R * 2 - 8, _ROW_H),
                    Qt.AlignLeft | Qt.AlignVCenter,
                    name,
                )
                painter.setOpacity(1.0)
                y += _ROW_H

        painter.restore()

    def _prepare_for_removal(self) -> None:
        self._poll_timer.stop()
        super()._prepare_for_removal()

    def to_dict(self) -> dict:
        return self.data.to_dict()

    @staticmethod
    def from_dict(d: dict) -> 'GitNode':
        return GitNode(GitNodeData.from_dict(d))

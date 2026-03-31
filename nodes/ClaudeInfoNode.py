#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/ClaudeInfoNode.py ClaudeInfoNode class
-Live token-usage dashboard. Scans Claude JSONL sessions and celebrates for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import json
import threading
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QFont, QColor, QPen

from nodes.BaseNode import BaseNode
from data.ClaudeInfoNodeData import ClaudeInfoNodeData
from graphics.Theme import Theme


def _human_tokens(n: int) -> str:
    """Format token count with K/M suffix."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


class ClaudeInfoNode(BaseNode):
    """
    Live token-usage dashboard that scans all JSONL files in the
    Claude projects folder and surfaces cumulative stats on the canvas.

    Heavy I/O (scanning every JSONL) runs on a daemon thread so the
    canvas never hitches.  Results land on the main thread via QTimer.
    """

    def __init__(self, data: ClaudeInfoNodeData | None = None):
        if data is None:
            data = ClaudeInfoNodeData()
        super().__init__(data)

        self.setBrush(QColor(Theme.healthNodeBg))

        # ── Live readings ──────────────────────────────────────────────────
        self._input_tokens:   int = 0
        self._output_tokens:  int = 0
        self._cache_create:   int = 0
        self._cache_read:     int = 0
        self._total_tokens:   int = 0
        self._session_count:  int = 0
        self._message_count:  int = 0
        self._scan_count:     int = 0
        self._scanning:       bool = False

        # ── Poll timer — 10 s between scans ──────────────────────────────
        self._poll_timer = QTimer()
        self._poll_timer.setInterval(10_000)
        self._poll_timer.timeout.connect(self._kick_scan)
        self._poll_timer.start()

        self._kick_scan()

    # ─────────────────────────────────────────────────────────────────────
    # SCAN — runs on a daemon thread
    # ─────────────────────────────────────────────────────────────────────

    def _kick_scan(self) -> None:
        if self._scanning:
            return
        self._scanning = True
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self) -> None:
        folder = self.data.folder_path
        if not folder:
            folder = str(Path.home() / ".claude" / "projects")

        input_t = output_t = cache_c = cache_r = 0
        sessions = messages = 0

        base = Path(folder)
        # If folder_path points to a specific project subfolder, scan that;
        # otherwise walk all project subfolders for a global view.
        jsonl_files = list(base.glob("*.jsonl")) if base.exists() else []
        if not jsonl_files and base.exists():
            jsonl_files = list(base.glob("**/*.jsonl"))

        sessions = len(jsonl_files)
        for jf in jsonl_files:
            try:
                with open(jf, encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            if entry.get("type") != "assistant":
                                continue
                            u = entry.get("message", {}).get("usage")
                            if not u:
                                continue
                            messages += 1
                            input_t += u.get("input_tokens", 0)
                            output_t += u.get("output_tokens", 0)
                            cache_c += u.get("cache_creation_input_tokens", 0)
                            cache_r += u.get("cache_read_input_tokens", 0)
                        except (json.JSONDecodeError, AttributeError):
                            pass
            except OSError:
                pass

        # Deliver to main thread
        def _apply():
            self._input_tokens  = input_t
            self._output_tokens = output_t
            self._cache_create  = cache_c
            self._cache_read    = cache_r
            self._total_tokens  = input_t + output_t + cache_c + cache_r
            self._session_count = sessions
            self._message_count = messages
            self._scan_count   += 1
            self._scanning      = False
            self.update()

        QTimer.singleShot(0, _apply)

    # ─────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────

    def itemChange(self, change, value):
        if change == self.GraphicsItemChange.ItemSceneChange and value is None:
            self._poll_timer.stop()
        return super().itemChange(change, value)

    # ─────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        r      = self.rect()
        pad    = 12
        x      = r.x() + pad
        y      = r.y() + pad
        w      = r.width() - pad * 2
        line_h = 18

        c_label = QColor(Theme.healthColorLabel)
        c_calm  = QColor(Theme.healthColorCalm)
        c_warn  = QColor(Theme.healthColorWarn)
        c_high  = QColor(Theme.healthColorHigh)
        c_text  = QColor(Theme.textPrimary)

        f_label  = QFont(Theme.healthFontFamily, max(1, Theme.healthFontSizeLabel))
        f_value  = QFont(Theme.healthFontFamily, max(1, Theme.healthFontSizeValue))
        f_value.setBold(True)
        f_header = QFont(Theme.healthFontFamily, max(1, Theme.healthFontSizeHeader))
        f_header.setBold(True)
        f_footer = QFont(Theme.healthFontFamily, max(1, Theme.healthFontSizeFooter))

        # ── HEADER ───────────────────────────────────────────────────────
        painter.setFont(f_header)
        painter.setPen(c_text)
        painter.drawText(int(x), int(y), int(w), line_h + 4,
                         Qt.AlignLeft | Qt.AlignVCenter, "🧠  Claude Token Census")
        y += line_h + 6

        # ── DIVIDER ──────────────────────────────────────────────────────
        div_pen = QPen(QColor(Theme.primaryBorder), 1, Qt.DotLine)
        painter.setPen(div_pen)
        painter.drawLine(int(x), int(y), int(x + w), int(y))
        y += 8

        # ── HERO — total tokens ──────────────────────────────────────────
        hero_font = QFont(Theme.healthFontFamily, max(1, 16))
        hero_font.setBold(True)
        painter.setFont(hero_font)

        if self._total_tokens >= 1_000_000:
            hero_color = c_high
        elif self._total_tokens >= 100_000:
            hero_color = c_warn
        else:
            hero_color = c_calm

        painter.setPen(hero_color)
        painter.drawText(int(x), int(y), int(w), 28,
                         Qt.AlignCenter | Qt.AlignVCenter,
                         _human_tokens(self._total_tokens) + " tokens")
        y += 32

        # ── DIVIDER ──────────────────────────────────────────────────────
        painter.setPen(div_pen)
        painter.drawLine(int(x), int(y), int(x + w), int(y))
        y += 8

        # ── ROWS ─────────────────────────────────────────────────────────
        rows = [
            ("Input",         _human_tokens(self._input_tokens),  c_calm),
            ("Output",        _human_tokens(self._output_tokens), c_warn),
            ("Cache create",  _human_tokens(self._cache_create),  c_label),
            ("Cache read",    _human_tokens(self._cache_read),    c_label),
            ("Sessions",      str(self._session_count),           c_text),
            ("Messages",      f"{self._message_count:,}",         c_text),
        ]

        for label, value, value_color in rows:
            painter.setFont(f_label)
            painter.setPen(c_label)
            painter.drawText(int(x), int(y), int(w * 0.6), line_h,
                             Qt.AlignLeft | Qt.AlignVCenter, label)
            painter.setFont(f_value)
            painter.setPen(value_color)
            painter.drawText(int(x), int(y), int(w), line_h,
                             Qt.AlignRight | Qt.AlignVCenter, value)
            y += line_h + 3

        # ── FOOTER ───────────────────────────────────────────────────────
        y += 4
        painter.setPen(div_pen)
        painter.drawLine(int(x), int(y), int(x + w), int(y))
        y += 6
        painter.setFont(f_footer)
        painter.setPen(c_label)
        status = "scanning…" if self._scanning else f"scan #{self._scan_count}"
        painter.drawText(int(x), int(y), int(w), line_h,
                         Qt.AlignCenter, f"every 10 s  ·  {status}")

    # ─────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'ClaudeInfoNode':
        return ClaudeInfoNode(ClaudeInfoNodeData.from_dict(data))

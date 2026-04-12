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
from PySide6.QtGui import QPainter, QColor

from nodes.BaseNode import BaseNode
from data.ClaudeInfoNodeData import ClaudeInfoNodeData
from pretty_widgets.graphics.Theme import Theme


# ── Pricing (per million tokens, April 2026) ──────────────────────────────
_PRICING = {
    "claude-opus-4-6":   {"input":  5.00, "output": 25.00},
    "claude-opus-4-5":   {"input":  5.00, "output": 25.00},
    "claude-sonnet-4-6": {"input":  3.00, "output": 15.00},
    "claude-sonnet-4-5": {"input":  3.00, "output": 15.00},
    "claude-haiku-4-5":  {"input":  1.00, "output":  5.00},
    "claude-haiku-4-6":  {"input":  1.00, "output":  5.00},
}


def _get_pricing(model: str) -> dict | None:
    if not model:
        return None
    if model in _PRICING:
        return _PRICING[model]
    for key in _PRICING:
        if model.startswith(key):
            return _PRICING[key]
    m = model.lower()
    if "opus" in m:
        return _PRICING["claude-opus-4-6"]
    if "sonnet" in m:
        return _PRICING["claude-sonnet-4-6"]
    if "haiku" in m:
        return _PRICING["claude-haiku-4-5"]
    return None


def _calc_cost(model: str, inp: int, out: int, cache_read: int, cache_create: int) -> float:
    p = _get_pricing(model)
    if not p:
        return 0.0
    return (
        inp          * p["input"]  / 1_000_000
        + out        * p["output"] / 1_000_000
        + cache_read * p["input"]  * 0.10 / 1_000_000
        + cache_create * p["input"] * 1.25 / 1_000_000
    )


def _human_tokens(n: int) -> str:
    """Format token count with K/M suffix."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _human_cost(v: float) -> str:
    """Format cost as $X.XX."""
    if v >= 1.0:
        return f"${v:,.2f}"
    if v >= 0.01:
        return f"${v:.2f}"
    return f"${v:.4f}"


class ClaudeInfoNode(BaseNode):
    """
    Live token-usage dashboard that scans all JSONL files in the
    Claude projects folder and surfaces cumulative stats on the canvas.

    Deduplicates streaming events by message.id — Claude Code logs
    multiple records per API response, only the last per message_id
    is kept (it has the final usage tallies).

    Heavy I/O runs on a daemon thread so the canvas never hitches.
    Results land on the main thread via QTimer.
    """
    _has_depth_toggle = True

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
        self._total_cost:     float = 0.0
        self._model_stats:    dict = {}  # model → {input, output, cache_read, cache_create, cost, turns}

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
        session_ids = set()
        messages = 0
        total_cost = 0.0
        model_stats = {}  # model → {input, output, cache_read, cache_create, cost, turns}

        base = Path(folder)
        jsonl_files = list(base.glob("*.jsonl")) if base.exists() else []
        if not jsonl_files and base.exists():
            jsonl_files = list(base.glob("**/*.jsonl"))

        for jf in jsonl_files:
            try:
                # Dedup: last record per message_id wins (final usage tallies)
                seen_messages = {}  # message_id → turn dict
                turns_no_id = []

                with open(jf, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        if entry.get("type") != "assistant":
                            # Track session IDs from any record type
                            sid = entry.get("sessionId")
                            if sid:
                                session_ids.add(sid)
                            continue

                        sid = entry.get("sessionId")
                        if sid:
                            session_ids.add(sid)

                        msg = entry.get("message", {})
                        u = msg.get("usage")
                        if not u:
                            continue

                        it = u.get("input_tokens", 0) or 0
                        ot = u.get("output_tokens", 0) or 0
                        cr = u.get("cache_read_input_tokens", 0) or 0
                        cc = u.get("cache_creation_input_tokens", 0) or 0

                        # Skip zero-token records
                        if it + ot + cr + cc == 0:
                            continue

                        model = msg.get("model", "unknown")
                        message_id = msg.get("id", "")

                        turn = {
                            "model": model,
                            "input": it, "output": ot,
                            "cache_read": cr, "cache_create": cc,
                        }

                        if message_id:
                            seen_messages[message_id] = turn
                        else:
                            turns_no_id.append(turn)

                # Aggregate deduplicated turns
                for turn in turns_no_id + list(seen_messages.values()):
                    messages += 1
                    input_t  += turn["input"]
                    output_t += turn["output"]
                    cache_r  += turn["cache_read"]
                    cache_c  += turn["cache_create"]

                    m = turn["model"]
                    cost = _calc_cost(m, turn["input"], turn["output"],
                                      turn["cache_read"], turn["cache_create"])
                    total_cost += cost

                    if m not in model_stats:
                        model_stats[m] = {"input": 0, "output": 0, "cache_read": 0,
                                          "cache_create": 0, "cost": 0.0, "turns": 0}
                    ms = model_stats[m]
                    ms["input"]        += turn["input"]
                    ms["output"]       += turn["output"]
                    ms["cache_read"]   += turn["cache_read"]
                    ms["cache_create"] += turn["cache_create"]
                    ms["cost"]         += cost
                    ms["turns"]        += 1

            except OSError:
                pass

        # Deliver to main thread
        def _apply():
            self._input_tokens  = input_t
            self._output_tokens = output_t
            self._cache_create  = cache_c
            self._cache_read    = cache_r
            self._total_tokens  = input_t + output_t + cache_c + cache_r
            self._session_count = len(session_ids)
            self._message_count = messages
            self._total_cost    = total_cost
            self._model_stats   = model_stats
            self._scan_count   += 1
            self._scanning      = False
            self.update()

        QTimer.singleShot(0, _apply)

    # ─────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        self._poll_timer.stop()
        try:
            self._poll_timer.timeout.disconnect(self._kick_scan)
        except RuntimeError:
            pass
        super()._prepare_for_removal()

    def itemChange(self, change, value):
        if change == self.GraphicsItemChange.ItemSceneChange and value is None:
            self._poll_timer.stop()
        return super().itemChange(change, value)

    # ─────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        from utils.paint import make_kit, draw_header, draw_hero, draw_rows, draw_footer

        kit = make_kit(self._TITLE_FONT, self._TITLE_STYLE, self._TITLE_FONT_BUMP)
        r   = self.rect()
        x   = r.x() + kit.pad
        y   = r.y() + self._anim_top_offset + kit.pad
        w   = r.width() - kit.pad * 2

        y = draw_header(painter, kit, x, y, w, "Token Census")

        # ── Hero — total tokens ──────────────────────────────────────────
        c_calm = QColor(Theme.healthColorCalm)
        c_warn = QColor(Theme.healthColorWarn)
        c_high = QColor(Theme.healthColorHigh)
        c_text = QColor(Theme.textPrimary)

        if self._total_tokens >= 1_000_000:
            hero_color = c_high
        elif self._total_tokens >= 100_000:
            hero_color = c_warn
        else:
            hero_color = c_calm

        y = draw_hero(painter, kit, x, y, w,
                      _human_tokens(self._total_tokens) + " tokens", hero_color)

        # ── Rows ─────────────────────────────────────────────────────────
        rows: list[tuple[str, str, QColor]] = [
            ("Input",         _human_tokens(self._input_tokens),  c_calm),
            ("Output",        _human_tokens(self._output_tokens), c_warn),
            ("Cache create",  _human_tokens(self._cache_create),  kit.c_label),
            ("Cache read",    _human_tokens(self._cache_read),    kit.c_label),
            ("Sessions",      f"{self._session_count:,}",         c_text),
            ("Messages",      f"{self._message_count:,}",         c_text),
            ("Est. cost",     _human_cost(self._total_cost),      c_high),
        ]

        y = draw_rows(painter, kit, x, y, w, rows)

        # ── Per-model breakdown ──────────────────────────────────────────
        if self._model_stats:
            y += 6
            # Sort by cost descending
            for model, ms in sorted(self._model_stats.items(),
                                     key=lambda kv: kv[1]["cost"], reverse=True):
                # Short model name
                short = model.replace("claude-", "").replace("-", " ").title()
                tokens = ms["input"] + ms["output"] + ms["cache_read"] + ms["cache_create"]
                label = f"{short}"
                value = f"{_human_tokens(tokens)}  {_human_cost(ms['cost'])}"
                rows_m = [(label, value, c_text)]
                y = draw_rows(painter, kit, x, y, w, rows_m)

        status = "scanning…" if self._scanning else f"scan #{self._scan_count}"
        draw_footer(painter, kit, x, y, w, f"every 10 s  ·  {status}  ·  deduped", gap=4)

    # ─────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'ClaudeInfoNode':
        return ClaudeInfoNode(ClaudeInfoNodeData.from_dict(data))

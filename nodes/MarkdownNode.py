#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/MarkdownNode.py markdown rendering base
-GitHub dark theme markdown viewer base class for all doc nodes for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import re
import threading

from PySide6.QtWidgets import QGraphicsProxyWidget, QTextEdit
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QPainter, QColor

from nodes.BaseNode import BaseNode
from data.MarkdownNodeData import MarkdownNodeData
from pretty_widgets.graphics.Theme import Theme


_BUTTON_ZONE_H = 40.0
_PAD           = 8.0
_BG_COLOR      = "#0d1117"   # GitHub dark theme background


class MarkdownNode(BaseNode):
    """
    Base class for read-only markdown rendering nodes.

    Converts markdown text to GitHub-styled HTML and displays it inside
    a scrollable QTextEdit.  Subclasses provide their own data class
    and optionally override _build_buttons() for extra controls.
    """
    _has_depth_toggle = True

    def __init__(self, data: MarkdownNodeData | None = None):
        if data is None:
            data = MarkdownNodeData()
        super().__init__(data)

        c = QColor(_BG_COLOR)
        c.setAlpha(Theme.aboutBgAlpha)
        self.setBrush(c)
        self._apply_depth()

        self._html_proxy: QGraphicsProxyWidget | None = None
        self._editor: QTextEdit | None = None
        self._pending_html: str | None = None
        self._removed: bool = False
        self._build_html_viewer()

        # Render markdown on a worker thread — node appears instantly,
        # content arrives shortly after without blocking the canvas.
        self._delivery_timer = QTimer()
        self._delivery_timer.setInterval(100)
        self._delivery_timer.timeout.connect(self._check_render_delivery)
        if self.data.label:
            threading.Thread(target=self._render_worker, daemon=True).start()
            self._delivery_timer.start()

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        from nodes.NodeButton import NodeButton
        super()._build_buttons()
        spawn_pix = Theme.icon(Theme.iconSpawnNodesClean, fallback_color="#7ab88a")
        btn = NodeButton(self, spawn_pix, self._split_into_nodes)
        btn._sticker_shadow = True
        self._buttons.append(btn)

    # ─────────────────────────────────────────────────────────────────────────
    # BACKGROUND
    # ─────────────────────────────────────────────────────────────────────────

    def _bg_color(self) -> QColor:
        c = QColor(_BG_COLOR)
        c.setAlpha(Theme.aboutBgAlpha)
        return c

    def _apply_depth(self) -> None:
        super()._apply_depth()
        self.setBrush(self._bg_color())

    # ─────────────────────────────────────────────────────────────────────────
    # HTML VIEWER
    # ─────────────────────────────────────────────────────────────────────────

    def _build_html_viewer(self) -> None:
        """Read-only QTextEdit with GitHub dark theme for markdown rendering."""
        te = QTextEdit()
        te.setReadOnly(True)
        te.setFrameShape(QTextEdit.NoFrame)
        te.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        te.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        te.setStyleSheet(
            "QTextEdit { background: transparent; border: none;"
            "            selection-background-color: #264f78;"
            "            selection-color: #e6edf3; }"
        )
        te.document().setDocumentMargin(12)

        self._html_proxy = QGraphicsProxyWidget(self)
        self._html_proxy.setWidget(te)
        self._editor = te
        self._position_editor()

    def _position_editor(self) -> None:
        r = self.rect()
        rect = QRectF(
            r.left()  + _PAD,
            r.top()   + _BUTTON_ZONE_H,
            r.width() - _PAD * 2,
            r.height() - _BUTTON_ZONE_H - _PAD,
        )
        if self._html_proxy:
            self._html_proxy.setGeometry(rect)

    # ─────────────────────────────────────────────────────────────────────────
    # MARKDOWN → HTML
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _markdown_to_html(md_text: str) -> str:
        """Convert markdown to GitHub-styled HTML for QTextEdit rendering.

        Qt's QTextEdit ignores <style> blocks entirely — all styling must be
        inline on each element.  This method converts markdown to HTML via the
        markdown package, then post-processes the tags to inject GitHub dark
        theme inline styles.
        """
        import markdown
        body = markdown.markdown(
            md_text,
            extensions=["tables", "fenced_code", "codehilite"],
            extension_configs={"codehilite": {"noclasses": True, "pygments_style": "monokai"}},
        )

        # GitHub dark theme colour tokens
        _fg       = "#e6edf3"
        _muted    = "#8b949e"
        _border   = "#30363d"
        _code_bg  = "#282828"
        _code_inl = "#343942"
        _link     = "#58a6ff"
        _mono     = "'Cascadia Mono', Consolas, monospace"
        _sans     = "'Segoe UI', Helvetica, Arial, sans-serif"

        # ── Inline style injection — tag → style mapping ─────────────────
        _replacements = [
            (r'<pre style="',
             f'<pre style="background:transparent; padding:0; margin:0; '
             f'font-family:{_mono}; font-size:12px; color:{_fg}; '),
            (r'<pre>',
             f'<pre style="background:transparent; color:{_fg}; '
             f'padding:0; margin:0; font-family:{_mono}; font-size:12px;">'),
            (r'<code>',
             f'<code style="font-family:{_mono}; font-size:12px; '
             f'background-color:{_code_inl}; color:{_fg}; padding:3px 6px;">'),
            (r'<h1>',
             f'<h1 style="font-size:24px; font-weight:600; color:{_fg}; '
             f'font-family:{_sans}; border-bottom:1px solid {_border}; '
             f'padding-bottom:8px; margin-top:20px; margin-bottom:12px;">'),
            (r'<h2>',
             f'<h2 style="font-size:20px; font-weight:600; color:{_fg}; '
             f'font-family:{_sans}; border-bottom:1px solid {_border}; '
             f'padding-bottom:6px; margin-top:18px; margin-bottom:10px;">'),
            (r'<h3>',
             f'<h3 style="font-size:16px; font-weight:600; color:{_fg}; '
             f'font-family:{_sans}; margin-top:14px; margin-bottom:8px;">'),
            (r'<p>',
             f'<p style="color:{_fg}; font-family:{_sans}; font-size:14px; '
             f'margin-top:4px; margin-bottom:2px;">'),
            (r'<a ',
             f'<a style="color:{_link};" '),
            (r'<table>',
             f'<table style="border:1px solid {_border}; table-layout:fixed; width:100%;" cellpadding="8" cellspacing="0">'),
            (r'<th>',
             f'<th style="background-color:{_code_bg}; color:{_fg}; '
             f'font-weight:600; border:1px solid {_border}; padding:8px 14px; '
             f'font-family:{_sans}; font-size:14px;">'),
            (r'<td>',
             f'<td style="color:{_fg}; border:1px solid {_border}; '
             f'padding:8px 14px; font-family:{_sans}; font-size:14px;">'),
            (r'<blockquote>',
             f'<blockquote style="border-left:3px solid {_border}; '
             f'padding-left:14px; color:{_muted}; margin:10px 0;">'),
            (r'<strong>',
             f'<strong style="font-weight:600; color:{_fg};">'),
            (r'<hr>',
             f'<hr style="border:none; border-top:1px solid {_border}; '
             f'margin-top:18px; margin-bottom:18px;">'),
            (r'<hr />',
             f'<hr style="border:none; border-top:1px solid {_border}; '
             f'margin-top:18px; margin-bottom:18px;" />'),
        ]

        for pattern, replacement in _replacements:
            body = body.replace(pattern, replacement)

        # Strip Pygments wrapper div
        body = re.sub(r'<div class="codehilite"[^>]*>\s*', '', body)
        body = body.replace('</div>', '')
        body = body.replace('<span></span>', '')
        body = body.replace('\n</code>', '</code>')

        # ── Convert ASCII tree structures to cozy emoji+indent format ────
        _tree_chars = set("├└│─┤┬┴┼")
        _folder_c = "#d4a44c"
        _desc_c   = "#8b949e"
        _file_c   = "#e6edf3"
        _strip_tags = re.compile(r'<[^>]+>')

        def _cozy_tree_line(line: str) -> str:
            if not line.strip():
                return ""
            if not any(c in line for c in _tree_chars):
                return f'<span style="color:{_file_c};">{line}</span>'

            stripped = line.lstrip(" ")
            lead_spaces = len(line) - len(stripped)

            rest = stripped
            depth = 0
            while rest:
                if rest[:3] in ("├──", "└──") and (len(rest) < 4 or rest[3] == " "):
                    rest = rest[4:] if len(rest) > 3 else ""
                    depth += 1
                    break
                elif rest.startswith("│"):
                    rest = rest[1:]
                    while rest.startswith(" "):
                        rest = rest[1:]
                    depth += 1
                else:
                    break

            if lead_spaces >= 4 and depth == 0:
                depth += lead_spaces // 4

            name = rest.strip()
            if not name:
                return ""

            desc_html = ""
            for sep in ("— ", "─ "):
                idx = name.find(sep)
                if idx > 0:
                    desc = name[idx + len(sep):]
                    name = name[:idx].rstrip()
                    desc_html = f' <span style="color:{_desc_c};">— {desc}</span>'
                    break

            indent = "    " * depth
            is_folder = name.rstrip().endswith("/") or "(" in name
            if depth == 0 and is_folder:
                return f'{indent}<span style="color:{_folder_c};">{name}</span>{desc_html}'
            icon = "\U0001f4c1 " if is_folder else "\U0001f4c4 "
            color = _folder_c if is_folder else _file_c
            return f'{indent}<span style="color:{color};">{icon}{name}</span>{desc_html}'

        def _process_pre_block(match):
            content = match.group(2)
            raw = _strip_tags.sub('', content)
            lines = raw.split("\n")
            while lines and not lines[-1].strip():
                lines.pop()

            is_tree = any(any(c in line for c in _tree_chars) for line in lines)
            if is_tree:
                cozy = "<br/>".join(_cozy_tree_line(l) for l in lines if _cozy_tree_line(l))
                block = (f'<p style="font-family:{_mono}; font-size:12px; '
                         f'color:{_fg}; margin:8px 0; padding:8px; '
                         f'background-color:{_code_bg}; white-space:pre;">{cozy}</p>')
            else:
                cozy = "<br/>".join(
                    f'<span style="color:{_fg};">{l}</span>' if l.strip() else ''
                    for l in lines
                )
                block = (f'<p style="font-family:{_mono}; font-size:12px; '
                         f'color:{_fg}; margin:8px 0; padding:8px; '
                         f'background-color:{_code_bg}; white-space:pre;">{cozy}</p>')
            return block

        body = re.sub(
            r'(<pre[^>]*>(?:\s*<span[^>]*></span>)*\s*<code[^>]*>)(.*?)</code></pre>',
            _process_pre_block,
            body,
            flags=re.DOTALL,
        )

        return f'<body style="margin:8px;">{body}</body>'

    # ─────────────────────────────────────────────────────────────────────────
    # ASYNC RENDER — daemon thread produces HTML, main thread delivers it
    # ─────────────────────────────────────────────────────────────────────────

    def _render_worker(self) -> None:
        """Background thread — convert markdown to HTML."""
        try:
            html = self._markdown_to_html(self.data.label)
            if not self._removed:
                self._pending_html = html
        except Exception:
            if not self._removed:
                self._pending_html = "<p>Render failed</p>"

    def _check_render_delivery(self) -> None:
        """Main-thread timer that picks up the rendered HTML from the worker."""
        if self._removed or self._pending_html is None:
            return
        html = self._pending_html
        self._pending_html = None
        self._delivery_timer.stop()
        if self._editor:
            self._editor.setHtml(html)
            self._auto_fit_height()

    # ─────────────────────────────────────────────────────────────────────────
    # AUTO-FIT
    # ─────────────────────────────────────────────────────────────────────────

    _BOTTOM_PAD = 40.0   # spacious bottom padding — visual "end of content" cue

    def _auto_fit_height(self) -> None:
        """Grow the node to fit the full rendered document — no scrolling."""
        if not self._editor:
            return
        r = self.rect()
        body_w = r.width() - _PAD * 2
        self._editor.document().setTextWidth(body_w)
        doc_h = self._editor.document().size().height()
        needed = _BUTTON_ZONE_H + doc_h + self._BOTTOM_PAD
        if abs(needed - r.height()) > 2.0:
            self.prepareGeometryChange()
            new_rect = QRectF(r.x(), r.y(), r.width(), needed)
            self.setRect(new_rect)
            self.data.height = needed

    # ─────────────────────────────────────────────────────────────────────────
    # SPLIT INTO CHAINED NODES
    # ─────────────────────────────────────────────────────────────────────────

    def _split_into_nodes(self, title_pattern: str = r'^#{1,6}\s+') -> None:
        """Split content into chained AboutNodes (titles) and WarmNodes (body).

        The *title_pattern* regex decides which lines are headings vs body
        text.  Default matches markdown headings; callers can pass any
        pattern to split on different delimiters.

        Every spawned node is chained to the previous one with a Connection
        wire, producing a linked reading sequence.
        """
        import re
        from PySide6.QtCore import QPointF, QRectF

        scene = self.scene()
        if not scene:
            return

        text = self.data.label
        if not text or not text.strip():
            return

        from nodes.WarmNode import WarmNode
        from data.WarmNodeData import WarmNodeData
        from graphics.Connection import Connection
        from utils.placement import spiral_place

        import math
        import random

        _OFFSCREEN = QPointF(-999_999, -999_999)
        prev_node = self
        source_hidden = not self.isVisible()

        # ── Parse into (title, body) pairs ──────────────────────────────
        sections: list[tuple[str | None, str]] = []
        current_title: str | None = None
        body_lines: list[str] = []

        for line in text.splitlines():
            if re.match(title_pattern, line):
                # Flush previous section
                body = "\n".join(body_lines).strip()
                if current_title is not None or body:
                    sections.append((current_title, body))
                # Start new section — strip the markdown markers for the label
                current_title = re.sub(title_pattern, "", line).strip()
                body_lines = []
            else:
                body_lines.append(line)

        # Flush final section
        body = "\n".join(body_lines).strip()
        if current_title is not None or body:
            sections.append((current_title, body))

        if not sections:
            return

        # ── Spawn nodes ─────────────────────────────────────────────────
        first_node = True
        for title, body in sections:

            # AboutNode for the heading
            if title:
                about = scene.add_about_node(pos=_OFFSCREEN, label=title)
                about.data.title = title[:40]
                if first_node and source_hidden:
                    pos = spiral_place(scene, about)
                    first_node = False
                else:
                    chain_origin = self._wander_origin(prev_node)
                    pos = spiral_place(
                        scene, about, origin=chain_origin,
                        fallback=chain_origin,
                    )
                about.setPos(pos)
                if not (first_node or (prev_node is self and source_hidden)):
                    conn = Connection(prev_node, about)
                    scene.addItem(conn)
                prev_node = about
                first_node = False

            # WarmNode for the body text
            if body:
                wdata = WarmNodeData(body_text=body, title="")
                warm = WarmNode(wdata)
                warm.setPos(_OFFSCREEN)
                scene.addItem(warm)
                scene.raise_node(warm)

                # Let WarmNode's own auto-fit handle sizing
                if hasattr(warm, '_auto_fit_height'):
                    warm._auto_fit_height()

                if first_node and source_hidden:
                    pos = spiral_place(scene, warm)
                    first_node = False
                else:
                    chain_origin = self._wander_origin(prev_node)
                    pos = spiral_place(
                        scene, warm, origin=chain_origin,
                        fallback=chain_origin,
                    )
                warm.setPos(pos)
                if not (prev_node is self and source_hidden):
                    conn = Connection(prev_node, warm)
                    scene.addItem(conn)
                prev_node = warm
                first_node = False

    @staticmethod
    def _wander_origin(prev_node) -> 'QPointF':
        """Pick a random origin near *prev_node* — sticky-note desk scatter.
        Thin alias for utils.placement.wander_origin kept so subclasses can
        override if they ever need a different distribution.
        """
        from utils.placement import wander_origin
        return wander_origin(prev_node)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT + LAYOUT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        pass  # HTML viewer handles display

    def setRect(self, rect) -> None:
        super().setRect(rect)
        if hasattr(self, '_html_proxy') and self._html_proxy:
            self._position_editor()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _quiet_background_machinery(self) -> None:
        """Stop signal/timer machinery synchronously, without touching
        scene-graph children (proxy, buttons, ports).

        Used by the Info sidebar's zombie-spawn pattern: after
        `_split_into_nodes` has emitted the readable cells, the source
        MarkdownNode is slated for removal on the next event-loop tick.
        During the window between the synchronous split returning and
        the deferred `removeItem` firing, the 100 ms delivery timer can
        emit `_check_render_delivery` — which races Qt's C++ destructor
        as it begins disconnecting signals during removeItem, and trips
        the `c0000409` fastfail invariant in Qt6Core.dll.

        Calling this method synchronously after the split closes the
        race: timer stopped, signals severed, worker flagged to bail.
        The scene-graph layer (proxy, children) is deliberately left
        intact so Qt's own removeItem can tear it down cleanly; the
        full cleanup then runs via `_prepare_for_removal` as usual."""
        self._removed = True
        if hasattr(self, '_delivery_timer') and self._delivery_timer is not None:
            self._delivery_timer.stop()
            try:
                self._delivery_timer.timeout.disconnect(self._check_render_delivery)
            except RuntimeError:
                pass

    def _prepare_for_removal(self) -> None:
        # Signal the worker thread to discard its result
        self._removed = True

        self._delivery_timer.stop()
        try:
            self._delivery_timer.timeout.disconnect(self._check_render_delivery)
        except RuntimeError:
            pass

        if self._html_proxy:
            w = self._html_proxy.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
            self._html_proxy.setWidget(None)
            scene = self.scene()
            if scene:
                scene.removeItem(self._html_proxy)
            self._html_proxy = None
        self._editor = None

        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

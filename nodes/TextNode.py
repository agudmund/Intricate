#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/TextNode.py TextNode class
-Always-editable multiline text node with Lato font, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import math
import random

from PySide6.QtWidgets import QGraphicsProxyWidget, QTextEdit
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QFont, QColor

from nodes.BaseNode import BaseNode
from data.TextNodeData import TextNodeData
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.PrettyEdit import PrettyEdit


_BUTTON_ZONE_H = 40.0
_PAD           = 8.0


class TextNode(BaseNode):
    """
    A plain always-editable text node using Lato font.

    The QTextEdit is always visible — no double-click activation needed.
    Click anywhere on the node to start typing. Resize freely.
    """
    _has_depth_toggle = True

    def __init__(self, data: TextNodeData | None = None):
        if data is None:
            data = TextNodeData()
        super().__init__(data)

        self.setBrush(self._bg_color())
        self._min_height  = Theme.aboutMinHeight
        self._apply_depth()

        self._editor: PrettyEdit | None = None
        self._build_editor()

    # ─────────────────────────────────────────────────────────────────────────

    def _bg_color(self) -> QColor:
        tint = getattr(self.data, 'node_tint', '')
        if tint:
            c = QColor(tint)
            if not c.isValid():
                c = QColor(Theme.aboutBgColorFront if self.data.depth_front else Theme.aboutBgColor)
        else:
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
        if self.data.render_html:
            self._build_html_viewer()
        else:
            self._build_plain_editor()

    def _build_html_viewer(self) -> None:
        """Bare QTextEdit for read-only HTML rendering — no PrettyEdit."""
        te = QTextEdit()
        te.setReadOnly(True)
        te.setFrameShape(QTextEdit.NoFrame)
        te.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        te.setStyleSheet(
            "QTextEdit { background: transparent; border: none;"
            "            selection-background-color: #264f78;"
            "            selection-color: #e6edf3; }"
            "QScrollBar:vertical { border: none; background: transparent;"
            "    width: 6px; }"
            "QScrollBar::handle:vertical { background: #30363d;"
            "    min-height: 20px; border-radius: 3px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical"
            "    { height: 0px; }"
        )
        te.setHtml(self._markdown_to_html(self.data.label))
        te.document().setDocumentMargin(8)

        self._html_proxy = QGraphicsProxyWidget(self)
        self._html_proxy.setWidget(te)
        self._editor = te
        self._position_editor()

    def _build_plain_editor(self) -> None:
        """PrettyEdit for editable plain text — the standard TextNode mode."""
        self._editor = PrettyEdit(
            self,
            font_family=Theme.claudeBodyFontFamily,
            font_size=Theme.claudeBodyFontSize,
            font_color=Theme.nodeFontColor,
            always_visible=True,
        )
        self._editor.setPlainText(self.data.label)
        self._editor.textChanged.connect(self._on_text_changed)
        self._position_editor()

    # _wrap_code_blocks removed — code blocks now render without
    # frame wrappers or background highlights, same as tree blocks.

    @staticmethod
    def _markdown_to_html(md_text: str) -> str:
        """Convert markdown to GitHub-styled HTML for QTextEdit rendering.

        Qt's QTextEdit ignores <style> blocks entirely — all styling must be
        inline on each element.  This method converts markdown to HTML via the
        markdown package, then post-processes the tags to inject GitHub dark
        theme inline styles.
        """
        import re
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
        # Order matters: more specific patterns first (pre > code before code)
        _replacements = [
            # Code blocks — no background, no padding. Pygments span colours
            # are stripped later; code text renders clean on the node bg.
            (r'<pre style="',
             f'<pre style="background:transparent; padding:0; margin:0; '
             f'font-family:{_mono}; font-size:12px; color:{_fg}; '),
            # Plain <pre> without existing style
            (r'<pre>',
             f'<pre style="background:transparent; color:{_fg}; '
             f'padding:0; margin:0; font-family:{_mono}; font-size:12px;">'),
            # Inline code (not inside pre — handle after pre replacement)
            (r'<code>',
             f'<code style="font-family:{_mono}; font-size:12px; '
             f'background-color:{_code_inl}; color:{_fg}; padding:3px 6px;">'),
            # Headings
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
            # Paragraphs — tight margins so gaps before code blocks stay small
            (r'<p>',
             f'<p style="color:{_fg}; font-family:{_sans}; font-size:14px; '
             f'margin-top:4px; margin-bottom:2px;">'),
            # Links
            (r'<a ',
             f'<a style="color:{_link};" '),
            # Tables
            (r'<table>',
             f'<table style="border:1px solid {_border};" cellpadding="8" cellspacing="0">'),
            (r'<th>',
             f'<th style="background-color:{_code_bg}; color:{_fg}; '
             f'font-weight:600; border:1px solid {_border}; padding:8px 14px; '
             f'font-family:{_sans}; font-size:14px;">'),
            (r'<td>',
             f'<td style="color:{_fg}; border:1px solid {_border}; '
             f'padding:8px 14px; font-family:{_sans}; font-size:14px;">'),
            # Block quotes
            (r'<blockquote>',
             f'<blockquote style="border-left:3px solid {_border}; '
             f'padding-left:14px; color:{_muted}; margin:10px 0;">'),
            # Strong / emphasis
            (r'<strong>',
             f'<strong style="font-weight:600; color:{_fg};">'),
            # Horizontal rules
            (r'<hr>',
             f'<hr style="border:none; border-top:1px solid {_border}; '
             f'margin-top:18px; margin-bottom:18px;">'),
            (r'<hr />',
             f'<hr style="border:none; border-top:1px solid {_border}; '
             f'margin-top:18px; margin-bottom:18px;" />'),
        ]

        for pattern, replacement in _replacements:
            body = body.replace(pattern, replacement)

        # Strip Pygments' <div class="codehilite" ...> wrapper — it adds
        # its own background bar above the <pre> block.
        body = re.sub(r'<div class="codehilite"[^>]*>\s*', '', body)
        body = body.replace('</div>', '')

        # Strip empty <span></span> Pygments injects before <code>
        body = body.replace('<span></span>', '')

        # Trim trailing newline inside <code> blocks — prevents a phantom
        # empty line at the bottom of every code block.
        body = body.replace('\n</code>', '</code>')

        # ── Convert ASCII tree structures to cozy emoji+indent format ─────
        # Pygments wraps every character in <span style="..."> tags, so we
        # first strip all spans to recover raw text, then rebuild with our
        # cozy TreeNode-style format: 📁/📄 emoji, clean indentation, colours.
        # re already imported at method top

        _tree_chars = set("├└│─┤┬┴┼")
        _folder_c = "#d4a44c"   # warm gold for folders
        _desc_c   = "#8b949e"   # muted for descriptions
        _file_c   = "#e6edf3"   # ivory for filenames
        _strip_tags = re.compile(r'<[^>]+>')

        def _cozy_tree_line(line: str) -> str:
            if not line.strip():
                return ""
            if not any(c in line for c in _tree_chars):
                return f'<span style="color:{_file_c};">{line}</span>'

            # Strip leading whitespace — track it but don't count as depth
            stripped = line.lstrip(" ")
            lead_spaces = len(line) - len(stripped)

            # Count depth by consuming tree prefixes
            rest = stripped
            depth = 0
            while rest:
                if rest[:3] in ("├──", "└──") and (len(rest) < 4 or rest[3] == " "):
                    rest = rest[4:] if len(rest) > 3 else ""
                    depth += 1
                    break
                elif rest.startswith("│"):
                    rest = rest[1:]
                    # Consume trailing spaces after │
                    while rest.startswith(" "):
                        rest = rest[1:]
                    depth += 1
                else:
                    break

            # Account for leading spaces as extra depth (some trees indent with spaces)
            if lead_spaces >= 4 and depth == 0:
                depth += lead_spaces // 4

            name = rest.strip()
            if not name:
                return ""

            # Split description if present (— em dash or ─ box horizontal)
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
                # Root entry — no icon, just the name (matches TreeNode behaviour)
                return f'{indent}<span style="color:{_folder_c};">{name}</span>{desc_html}'
            icon = "📁 " if is_folder else "📄 "
            color = _folder_c if is_folder else _file_c
            return f'{indent}<span style="color:{color};">{icon}{name}</span>{desc_html}'

        def _process_pre_block(match):
            content = match.group(2)
            # Strip all HTML tags to get raw text
            raw = _strip_tags.sub('', content)
            lines = raw.split("\n")
            # Filter empty trailing lines
            while lines and not lines[-1].strip():
                lines.pop()

            is_tree = any(any(c in line for c in _tree_chars) for line in lines)
            if is_tree:
                # Tree block — emoji icons, clean indentation, dark background
                cozy = "<br/>".join(_cozy_tree_line(l) for l in lines if _cozy_tree_line(l))
                block = (f'<p style="font-family:{_mono}; font-size:12px; '
                         f'color:{_fg}; margin:8px 0; padding:8px; '
                         f'background-color:{_code_bg}; white-space:pre;">{cozy}</p>')
            else:
                # Code block — clean monospace text on dark background panel
                cozy = "<br/>".join(
                    f'<span style="color:{_fg};">{l}</span>' if l.strip() else ''
                    for l in lines
                )
                block = (f'<p style="font-family:{_mono}; font-size:12px; '
                         f'color:{_fg}; margin:8px 0; padding:8px; '
                         f'background-color:{_code_bg}; white-space:pre;">{cozy}</p>')
            return block

        # Match <pre>...<code> blocks — Pygments may insert <span></span>
        # or other tags between pre and code.
        body = re.sub(
            r'(<pre[^>]*>(?:\s*<span[^>]*></span>)*\s*<code[^>]*>)(.*?)</code></pre>',
            _process_pre_block,
            body,
            flags=re.DOTALL,
        )

        return f'<body style="margin:8px;">{body}</body>'

    def _on_text_changed(self) -> None:
        self.data.label = self._editor.toPlainText()

    def _position_editor(self) -> None:
        r = self.rect()
        rect = QRectF(
            r.left()  + _PAD,
            r.top()   + _BUTTON_ZONE_H,
            r.width() - _PAD * 2,
            r.height() - _BUTTON_ZONE_H - _PAD,
        )
        if hasattr(self, '_html_proxy'):
            self._html_proxy.setGeometry(rect)
        else:
            self._editor.position(rect)

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        from nodes.NodeButton import NodeButton
        super()._build_buttons()
        spawn_pix = Theme.icon(Theme.iconSpawnNodesClean, fallback_color="#7ab88a")
        btn = NodeButton(self, spawn_pix, self._split_into_about_nodes)
        btn._sticker_shadow = True
        self._buttons.append(btn)

    # ─────────────────────────────────────────────────────────────────────────
    # SPLIT — explode body text into individual AboutNodes
    # ─────────────────────────────────────────────────────────────────────────

    def _split_into_about_nodes(self) -> None:
        """
        Split each non-empty line of the body text into its own AboutNode.

        Placement uses the same spiral-probe strategy as ClaudeNode response
        nodes: spawn off-screen, measure real size, then spiral outward from
        this node's position probing for a clear slot with PADDING breathing
        room. Each subsequent node starts its search from the previous node's
        position so the chain flows outward organically.
        """
        scene = self.scene()
        if not scene:
            return

        text = self.data.label if self._editor is None else self._editor.toPlainText()
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return

        from nodes.BaseNode import BaseNode as _BaseNode

        PADDING         = 28
        PROBES_PER_RING = 16
        _OFFSCREEN      = QPointF(-999_999, -999_999)

        origin = self.pos() + QPointF(self.rect().width() + 60, 0)

        for line in lines:
            node = scene.add_about_node(pos=_OFFSCREEN, label=line)
            node.data.title = line[:40]
            nr = node.rect()
            nw, nh = nr.width(), nr.height()

            step       = max(1, int(max(nw, nh)) // 2)
            max_radius = 4000

            def _clear(p):
                candidate = QRectF(p.x() - PADDING, p.y() - PADDING,
                                   nw + PADDING * 2, nh + PADDING * 2)
                for item in scene.items(candidate):
                    if item is node:
                        continue
                    # Duck-typed over BaseNode + StickerNode roots.
                    if hasattr(item, 'data') and hasattr(item, 'to_dict'):
                        return False
                return True

            pos = origin
            found = _clear(origin)
            if not found:
                for radius in range(step, max_radius, step):
                    base = random.uniform(0, 2 * math.pi)
                    for k in range(PROBES_PER_RING):
                        angle = base + k * (2 * math.pi / PROBES_PER_RING)
                        candidate = QPointF(
                            origin.x() + math.cos(angle) * radius,
                            origin.y() + math.sin(angle) * radius,
                        )
                        if _clear(candidate):
                            pos = candidate
                            found = True
                            break
                    if found:
                        break

            if not found:
                pos = origin

            node.setPos(pos)
            origin = pos + QPointF(nw + 40, 0)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT + LAYOUT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        pass  # editor is always visible — nothing to paint

    def setRect(self, rect) -> None:
        super().setRect(rect)
        if hasattr(self, '_editor') and self._editor:
            self._position_editor()

    # ─────────────────────────────────────────────────────────────────────────
    # INTERACTION
    # ─────────────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        if self._editor and hasattr(self._editor, 'proxy'):
            self._editor.proxy.setFocus()
            self._editor.setFocus(Qt.MouseFocusReason)
        event.accept()

    def keyPressEvent(self, event) -> None:
        if self.data.render_html:
            super().keyPressEvent(event)
            return
        if self._editor and hasattr(self._editor, 'proxy') and self._editor.proxy.isVisible():
            if event.key() == Qt.Key_Escape:
                self._editor._restore_view_focus()
                if self.scene() and self.scene().views():
                    self.scene().views()[0].setFocus()
                event.accept()
                return
            event.accept()
            return
        super().keyPressEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    # TextNode has two render modes — HTML (proxied) and plain (PrettyEdit
    # editor).  Declaring _html_proxy is safe whether or not it exists;
    # the crew skips missing attrs.  The editor-teardown path lives in
    # _demolition_pre for the plain-mode case.
    _demolition_proxies = ['_html_proxy']

    def _demolition_pre(self) -> None:
        # HTML mode: crew handles the proxy.  Plain mode: tear down the
        # PrettyEdit editor here so its own proxy teardown runs.
        if not (hasattr(self, '_html_proxy') and self._html_proxy):
            if self._editor and hasattr(self._editor, 'teardown'):
                self._editor.teardown()
        self._editor = None

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def sync_data(self) -> None:
        super().sync_data()
        if self._editor and not self.data.render_html:
            self.data.label = self._editor.toPlainText()

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'TextNode':
        return TextNode(TextNodeData.from_dict(data))

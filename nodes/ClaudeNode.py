#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/ClaudeNode.py ClaudeNode class
-Skeletal Claude-branded node, ready to be packed with features, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import json
import queue
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QRectF, QFileSystemWatcher, QTimer, Signal, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import QGraphicsProxyWidget, QTextEdit

from nodes.BaseNode import BaseNode
from data.ClaudeNodeData import ClaudeNodeData
from graphics.Theme import Theme
import utils.settings as settings


class _InputEdit(QTextEdit):
    """Multiline input; plain Enter submits, Shift+Enter inserts newline."""
    submitted = Signal(str)
    focused   = Signal()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.focused.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            text = self.toPlainText().strip()
            if text:
                self.submitted.emit(text)
                self.clear()
        else:
            super().keyPressEvent(event)


class ClaudeNode(BaseNode):
    """
    Claude node — connects to a Claude Code session, pipes input/output through the node.

    Inherits all chrome, ports, resize, hover pulse, lifecycle handling,
    and default title rendering from BaseNode.
    """
    _has_depth_toggle = True

    def __init__(self, data: ClaudeNodeData | None = None):
        if data is None:
            data = ClaudeNodeData(
                width=Theme.claudeDefaultWidth,
                height=Theme.claudeDefaultHeight,
            )
        super().__init__(data)
        self.setBrush(self._bg_color())
        self._apply_depth()
        self._rebuild_pens()
        if settings.watcher:
            settings.watcher.changed.connect(self._on_theme_reload)
        self._min_width  = data.width
        self._min_height = data.height
        self._current_uuid: str | None = None
        self._watcher: QFileSystemWatcher | None = None
        self._file_offset: int = 0
        self._current_reply: str = ""
        self._response_count: int = 0
        self._reply_done_timer = QTimer()
        self._reply_done_timer.setSingleShot(True)
        self._reply_done_timer.setInterval(1500)
        self._reply_done_timer.timeout.connect(self._on_reply_done)
        self._build_body()
        self._build_input()
        self._auto_connect()

    # ─────────────────────────────────────────────────────────────────────────
    # AUTO CONNECT
    # ─────────────────────────────────────────────────────────────────────────

    def _auto_connect(self) -> None:
        """Find the 'Intricate Claude Node' session (or most recent) and connect."""
        p = Path(self.data.folder_path)
        if not p.exists():
            return
        target_uuid = None
        fallback_uuid = None
        fallback_mtime = 0.0
        for jsonl_file in p.glob("*.jsonl"):
            try:
                mtime = jsonl_file.stat().st_mtime
                if mtime > fallback_mtime:
                    fallback_mtime = mtime
                    fallback_uuid = jsonl_file.stem
                with open(jsonl_file, encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "custom-title" not in line:
                            continue
                        try:
                            entry = json.loads(line.strip())
                            if entry.get("type") == "custom-title" and entry.get("customTitle") == "Intricate Claude Node":
                                target_uuid = jsonl_file.stem
                        except json.JSONDecodeError:
                            pass
            except OSError:
                pass
        uuid = target_uuid or fallback_uuid
        if not uuid:
            return
        self._current_uuid = uuid
        self._start_watching(uuid)

    # ─────────────────────────────────────────────────────────────────────────
    # SESSION WATCHER
    # ─────────────────────────────────────────────────────────────────────────

    def _start_watching(self, uuid: str) -> None:
        jsonl_path = Path(self.data.folder_path) / f"{uuid}.jsonl"
        if not jsonl_path.exists():
            return
        if self._watcher:
            self._watcher.fileChanged.disconnect()
            self._watcher.deleteLater()
        self._watcher = QFileSystemWatcher([str(jsonl_path)])
        self._file_offset = jsonl_path.stat().st_size  # only show new output
        self._watcher.fileChanged.connect(self._on_file_changed)

    def _on_file_changed(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                f.seek(self._file_offset)
                new_lines = f.readlines()
                self._file_offset = f.tell()
        except OSError:
            return
        for line in new_lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("type") != "assistant":
                    continue
                for block in entry.get("message", {}).get("content", []):
                    if block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if text:
                            self._append_body(text)
                            self._current_reply += text + " "
                            self._reply_done_timer.start()
            except json.JSONDecodeError:
                pass
        # Re-add path — some writers remove and recreate the file
        if self._watcher and path not in self._watcher.files():
            self._watcher.addPath(path)


    def _build_buttons(self) -> None:
        from nodes.NodeButton import NodeButton
        super()._build_buttons()
        show_pix = Theme.icon(Theme.claudeBodyShowIcon, fallback_color="#7ab8c9")
        hide_pix = Theme.icon(Theme.claudeBodyHideIcon, fallback_color="#4a7a8a")
        btn = NodeButton(self, show_pix, self._toggle_body, hide_pix, toggle=True)
        self._buttons.append(btn)

    def _collapsed_height(self) -> float:
        pad = Theme.nodeTextPaddingLeft
        return self._BUTTON_ZONE_H + Theme.nodeFontVerticalOffset + Theme.nodeTextPaddingTop + self._title_height() + 6 + self._input_h() + pad * 2

    def _toggle_body(self) -> None:
        if not (hasattr(self, '_body_proxy') and self._body_proxy):
            return
        r = self.rect()
        if self._body_proxy.isVisible():
            self._full_height = r.height()
            self._body_proxy.hide()
            new_h = self._collapsed_height()
        else:
            self._body_proxy.show()
            new_h = getattr(self, '_full_height', self._min_height)
        self.data.body_visible = self._body_proxy.isVisible()
        self.prepareGeometryChange()
        self.setRect(QRectF(r.left(), r.top(), r.width(), new_h))
        self._min_height = self._collapsed_height() if not self._body_proxy.isVisible() else Theme.claudeDefaultHeight
        self._position_input()
        self._position_buttons()

    def _rebuild_pens(self) -> None:
        w = Theme.claudeBorderWidth
        self.normal_pen   = QPen(self.normal_pen.color(),   w)
        self.hover_pen    = QPen(self.hover_pen.color(),    w)
        self.selected_pen = QPen(self.selected_pen.color(), w)
        self.setPen(self.normal_pen)

    def _on_theme_reload(self) -> None:
        self._rebuild_pens()
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # BODY
    # ─────────────────────────────────────────────────────────────────────────

    def _build_body(self) -> None:
        self._body = QTextEdit()
        self._body.setReadOnly(True)
        self._body.setFrameShape(QTextEdit.Shape.NoFrame)
        self._body.setFont(QFont(Theme.claudeBodyFontFamily, max(1, Theme.claudeBodyFontSize)))
        self._body.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {Theme.aboutFontColor};
                font-family: {Theme.claudeBodyFontFamily};
                font-size: {Theme.claudeBodyFontSize}pt;
                border-top: 1px solid rgba(0,0,0,80);
                border-left: 1px solid rgba(0,0,0,80);
                border-bottom: 1px solid rgba(255,255,255,40);
                border-right: 1px solid rgba(255,255,255,40);
                padding: 4px;
            }}
        """)
        if self.data.body_text:
            self._body.setPlainText(self.data.body_text)
        self._body_proxy = QGraphicsProxyWidget(self)
        self._body_proxy.setWidget(self._body)
        self._position_body()
        if not self.data.body_visible:
            self._body_proxy.hide()
            self._min_height = self._collapsed_height()

    def _append_body(self, text: str) -> None:
        self._body.append(text)
        self.data.body_text = self._body.toPlainText()

    # ─────────────────────────────────────────────────────────────────────────
    # INPUT
    # ─────────────────────────────────────────────────────────────────────────

    _INPUT_H_MIN = 24.0

    def _input_h(self) -> float:
        if not hasattr(self, '_input'):
            return self._INPUT_H_MIN
        fm = QFontMetrics(self._input.font())
        lines = max(1, self._input.document().blockCount())
        return fm.lineSpacing() * lines + 10

    def _build_input(self) -> None:
        self._input = _InputEdit()
        self._input.submitted.connect(self._send_input)
        self._input.setFrameShape(QTextEdit.Shape.NoFrame)
        self._input.setPlaceholderText("Type a message…")
        self._input.setFont(QFont(Theme.claudeBodyFontFamily, max(1, Theme.claudeBodyFontSize)))
        self._apply_input_style()
        if self.data.input_text:
            self._input.setPlainText(self.data.input_text)
        self._input.textChanged.connect(self._on_input_changed)
        self._input_proxy = QGraphicsProxyWidget(self)
        self._input_proxy.setWidget(self._input)
        self._position_input()
        QTimer.singleShot(0, lambda: self._input.focused.connect(self._on_input_focused))

    def _on_input_changed(self) -> None:
        self.data.input_text = self._input.toPlainText()
        self._resize_for_input()

    def _resize_for_input(self) -> None:
        collapsed_h = self._collapsed_height()
        r = self.rect()
        body_hidden = not (hasattr(self, '_body_proxy') and self._body_proxy and self._body_proxy.isVisible())
        if body_hidden and abs(r.height() - collapsed_h) > 0.5:
            self.prepareGeometryChange()
            self.setRect(QRectF(r.left(), r.top(), r.width(), collapsed_h))
            self._min_height = collapsed_h
        self._position_input()
        if not body_hidden:
            self._position_body()

    def _on_input_focused(self) -> None:
        self.data.depth_front = True
        self._apply_depth()

    def _on_reply_done(self) -> None:
        self.data.depth_front = True
        self._apply_depth()
        scene = self.scene()
        reply = self._current_reply.strip()
        self._current_reply = ""
        if scene and reply and "no response requested" not in reply.lower():
            from PySide6.QtCore import QPointF
            nudge = self._response_count * 3
            pos = self.pos() + QPointF(nudge, nudge)
            self._response_count += 1
            scene.add_claude_response_node(pos=pos, label=reply)

    def _send_input(self, text: str) -> None:
        if self._handle_local_command(text):
            return
        if not self._current_uuid:
            return
        self._append_body(f"\n› {text}\n")
        import textwrap
        self._title_question = textwrap.fill(text.capitalize(), width=84)
        self.data.title = self._title_question
        self.update()
        self.data.depth_front = False
        self._apply_depth()
        jsonl_path = Path(self.data.folder_path) / f"{self._current_uuid}.jsonl"
        try:
            self._file_offset = jsonl_path.stat().st_size
        except OSError:
            pass
        self._stream_q = queue.SimpleQueue()
        proc = subprocess.Popen(
            ["powershell.exe", "-Command",
             f"claude --resume={self._current_uuid} --print \"{text}\""],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        threading.Thread(target=self._read_proc_stdout, args=(proc,), daemon=True).start()
        self._stream_timer = QTimer()
        self._stream_timer.timeout.connect(self._flush_stream_title)
        self._stream_timer.start(80)

    def _read_proc_stdout(self, proc) -> None:
        try:
            for chunk in iter(lambda: proc.stdout.read(64), ""):
                if chunk:
                    self._stream_q.put(chunk)
        finally:
            self._stream_q.put(None)

    def _flush_stream_title(self) -> None:
        buf = getattr(self, "_stream_title_buf", "")
        done = False
        while True:
            try:
                item = self._stream_q.get_nowait()
            except queue.Empty:
                break
            if item is None:
                done = True
                break
            buf += item
        self._stream_title_buf = buf
        display = buf.replace("\n", " ").strip()
        if display:
            self.data.title = display[-80:] if len(display) > 80 else display
            self.update()
        if done:
            self._stream_timer.stop()
            self._stream_title_buf = ""
            self.data.title = getattr(self, "_title_question", self.data.title)
            self.update()

    def _handle_local_command(self, text: str) -> bool:
        from PySide6.QtWidgets import QApplication, QMainWindow
        from PySide6.QtCore import QTimer
        cmd = text.strip().lower()
        if cmd == "/close" or "close the app" in cmd or "close app" in cmd:
            win = next((w for w in QApplication.topLevelWidgets()
                        if isinstance(w, QMainWindow) and w.isVisible()), None)
            if win:
                QTimer.singleShot(0, win.close)
            return True
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        painter.save()
        r    = self.rect()
        pad  = Theme.nodeTextPaddingLeft
        font = QFont(Theme.aboutFontFamily, max(1, Theme.aboutFontSize))
        painter.setFont(font)
        painter.setPen(QColor(Theme.aboutFontColor))
        title_rect = QRectF(
            r.left() + pad,
            r.top() + self._BUTTON_ZONE_H + Theme.nodeFontVerticalOffset + Theme.nodeTextPaddingTop,
            r.width() - pad * 2,
            r.height() - self._BUTTON_ZONE_H,
        )
        painter.drawText(title_rect, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, self.data.title)
        painter.restore()

    def _title_height(self) -> float:
        r    = self.rect()
        pad  = Theme.nodeTextPaddingLeft
        font = QFont(Theme.aboutFontFamily, max(1, Theme.aboutFontSize))
        fm   = QFontMetrics(font)
        text_w = int(r.width() - pad * 2)
        bound  = fm.boundingRect(0, 0, text_w, 0,
                                 Qt.TextWordWrap | Qt.AlignLeft,
                                 self.data.title)
        return float(bound.height())

    # ─────────────────────────────────────────────────────────────────────────
    # LAYOUT
    # ─────────────────────────────────────────────────────────────────────────

    def _position_body(self) -> None:
        r         = self.rect()
        pad       = Theme.nodeTextPaddingLeft
        title_top = self._BUTTON_ZONE_H + Theme.nodeFontVerticalOffset + Theme.nodeTextPaddingTop
        body_y    = r.top() + title_top + self._title_height() + 6
        input_top = r.bottom() - self._input_h() - pad
        self._body_proxy.setGeometry(QRectF(
            r.left() + pad,
            body_y,
            r.width() - pad * 2,
            max(0.0, input_top - body_y - 6),
        ))

    def _position_input(self) -> None:
        r   = self.rect()
        pad = Theme.nodeTextPaddingLeft
        ih = self._input_h()
        self._input_proxy.setGeometry(QRectF(
            r.left() + pad,
            r.bottom() - ih - pad,
            r.width() - pad * 2,
            ih,
        ))

    def _bg_color(self) -> QColor:
        c = QColor(Theme.claudeBgColorFront if self.data.depth_front else Theme.claudeBgColorBack)
        c.setAlpha(Theme.claudeBgAlpha)
        return c

    def _apply_input_style(self) -> None:
        if not hasattr(self, '_input'):
            return
        self._input.setStyleSheet(f"""
            QTextEdit {{
                background: {Theme.claudeBgColorInput};
                color: {Theme.aboutFontColor};
                font-family: {Theme.claudeBodyFontFamily};
                font-size: {Theme.claudeBodyFontSize}pt;
                border: none;
                border-top: 1px solid rgba(255,255,255,30);
                padding: 4px;
            }}
        """)

    def _apply_depth(self) -> None:
        super()._apply_depth()
        self.setBrush(self._bg_color())
        self._apply_input_style()

    def setRect(self, rect) -> None:
        super().setRect(rect)
        if hasattr(self, '_body_proxy'):
            self._position_body()
        if hasattr(self, '_input_proxy'):
            self._position_input()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        if settings.watcher:
            try:
                settings.watcher.changed.disconnect(self._on_theme_reload)
            except RuntimeError:
                pass
        if self._watcher:
            self._watcher.fileChanged.disconnect()
            self._watcher.deleteLater()
            self._watcher = None
        if hasattr(self, '_body_proxy') and self._body_proxy:
            self._body_proxy.hide()
        if hasattr(self, '_input_proxy') and self._input_proxy:
            self._input_proxy.hide()
        self._body  = None
        self._input = None
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def sync_data(self) -> None:
        super().sync_data()
        if hasattr(self, '_body') and self._body:
            self.data.body_text = self._body.toPlainText()
        if hasattr(self, '_input') and self._input:
            self.data.input_text = self._input.toPlainText()

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'ClaudeNode':
        return ClaudeNode(ClaudeNodeData.from_dict(data))

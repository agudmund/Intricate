#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/ClaudeNode.py ClaudeNode class
-Skeletal Claude-branded node, ready to be packed with features, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import json
import re
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRectF, QFileSystemWatcher, Signal, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeyEvent
from PySide6.QtWidgets import QGraphicsProxyWidget, QTextEdit

_ANSI_RE = re.compile(r'\x1b(?:\[[0-9;]*[A-Za-z]|\].*?(?:\x07|\x1b\\))|[\r\x08]')


class _OutputReader(QObject):
    """Reads subprocess stdout in a daemon thread; emits line_ready on the Qt thread."""
    line_ready = Signal(str)

    def __init__(self, process: subprocess.Popen) -> None:
        super().__init__()
        self._process = process
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            for raw in iter(self._process.stdout.readline, b''):
                text = _ANSI_RE.sub('', raw.decode('utf-8', errors='replace')).rstrip('\n')
                if text.strip():
                    self.line_ready.emit(text)
        except Exception:
            pass

from nodes.BaseNode import BaseNode
from data.ClaudeNodeData import ClaudeNodeData
from graphics.Theme import Theme
from widgets.PrettyCombo import PrettyCombo


class _InputEdit(QTextEdit):
    """Multiline input; plain Enter submits, Shift+Enter inserts newline."""
    submitted = Signal(str)

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
            data = ClaudeNodeData()
        super().__init__(data)
        self.setBrush(self._bg_color())
        self._apply_depth()
        self._min_width  = data.width
        self._min_height = data.height
        self._current_uuid: str | None = None
        self._watcher: QFileSystemWatcher | None = None
        self._file_offset: int = 0
        self._process: subprocess.Popen | None = None
        self._reader: _OutputReader | None = None
        self._build_combo()
        self._build_body()
        self._build_input()

    # ─────────────────────────────────────────────────────────────────────────
    # COMBO
    # ─────────────────────────────────────────────────────────────────────────

    def _build_combo(self) -> None:
        self._combo = PrettyCombo()
        for display_name, uuid in self._read_folder():
            self._combo.addItem(display_name, uuid)
        self._combo.activated.connect(self._on_session_selected)
        self._combo_proxy = QGraphicsProxyWidget(self)
        self._combo_proxy.setWidget(self._combo)
        self._position_combo()

    def _on_session_selected(self, index: int) -> None:
        uuid = self._combo.itemData(index)
        if not uuid:
            return
        self._stop_process()
        self._current_uuid = uuid
        self._start_watching(uuid)
        self._process = subprocess.Popen(
            ["powershell.exe", "-NoExit", "-Command", f"claude --resume={uuid}"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self._reader = _OutputReader(self._process)
        self._reader.line_ready.connect(self._append_body)

    def _stop_process(self) -> None:
        if self._reader:
            self._reader.line_ready.disconnect()
            self._reader = None
        if self._process and self._process.poll() is None:
            self._process.terminate()
        self._process = None

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
            if not line or '"type":"assistant"' not in line:
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
            except json.JSONDecodeError:
                pass
        # Re-add path — some writers remove and recreate the file
        if self._watcher and path not in self._watcher.files():
            self._watcher.addPath(path)

    # ─────────────────────────────────────────────────────────────────────────
    # FOLDER SCAN
    # ─────────────────────────────────────────────────────────────────────────

    def _read_folder(self) -> list[tuple[str, str]]:
        p = Path(self.data.folder_path)
        if not p.exists():
            return []
        items = []
        for jsonl_file in p.glob("*.jsonl"):
            uuid = jsonl_file.stem
            custom_title = None
            try:
                with open(jsonl_file, encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "custom-title" not in line:
                            continue
                        try:
                            entry = json.loads(line.strip())
                            if entry.get("type") == "custom-title":
                                custom_title = entry.get("customTitle")
                        except json.JSONDecodeError:
                            pass
            except OSError:
                pass
            items.append((custom_title or uuid, uuid))
        return sorted(items, key=lambda x: x[0])

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
                border: 1px solid rgba(255,255,255,30);
                padding: 4px;
            }}
        """)
        if self.data.body_text:
            self._body.setPlainText(self.data.body_text)
        self._body_proxy = QGraphicsProxyWidget(self)
        self._body_proxy.setWidget(self._body)
        self._position_body()

    def _append_body(self, text: str) -> None:
        self._body.append(text)
        self.data.body_text = self._body.toPlainText()

    # ─────────────────────────────────────────────────────────────────────────
    # INPUT
    # ─────────────────────────────────────────────────────────────────────────

    _INPUT_H = 72.0

    def _build_input(self) -> None:
        self._input = _InputEdit()
        self._input.submitted.connect(self._send_input)
        self._input.setFrameShape(QTextEdit.Shape.NoFrame)
        self._input.setPlaceholderText("Type a message…")
        self._input.setFont(QFont(Theme.claudeBodyFontFamily, max(1, Theme.claudeBodyFontSize)))
        self._input.setStyleSheet(f"""
            QTextEdit {{
                background: rgba(255, 255, 255, 18);
                color: {Theme.aboutFontColor};
                font-family: {Theme.claudeBodyFontFamily};
                font-size: {Theme.claudeBodyFontSize}pt;
                border: none;
                border-top: 1px solid rgba(255,255,255,30);
                padding: 4px;
            }}
        """)
        if self.data.input_text:
            self._input.setPlainText(self.data.input_text)
        self._input.textChanged.connect(self._on_input_changed)
        self._input_proxy = QGraphicsProxyWidget(self)
        self._input_proxy.setWidget(self._input)
        self._position_input()

    def _on_input_changed(self) -> None:
        self.data.input_text = self._input.toPlainText()

    def _send_input(self, text: str) -> None:
        if not self._current_uuid:
            return
        subprocess.Popen(
            ["powershell.exe", "-Command",
             f"claude --resume={self._current_uuid} --print \"{text}\""],
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # LAYOUT
    # ─────────────────────────────────────────────────────────────────────────

    def _position_combo(self) -> None:
        r       = self.rect()
        pad     = Theme.nodeTextPaddingLeft
        font    = QFont(Theme.aboutFontFamily, max(1, Theme.aboutFontSize))
        line_h  = QFontMetrics(font).height()
        title_top = (self._BUTTON_ZONE_H
                     + Theme.nodeFontVerticalOffset
                     + Theme.nodeTextPaddingTop)
        combo_y = title_top + line_h + 4
        self._combo_proxy.setGeometry(QRectF(
            r.left() + pad,
            r.top()  + combo_y,
            r.width() - pad * 2,
            self._combo.sizeHint().height(),
        ))

    def _position_body(self) -> None:
        r            = self.rect()
        pad          = Theme.nodeTextPaddingLeft
        combo_bottom = (self._combo_proxy.geometry().bottom()
                        if hasattr(self, '_combo_proxy') else 60)
        input_top    = r.bottom() - self._INPUT_H - pad
        body_y       = combo_bottom + 6
        self._body_proxy.setGeometry(QRectF(
            r.left() + pad,
            body_y,
            r.width() - pad * 2,
            max(0.0, input_top - body_y - 6),
        ))

    def _position_input(self) -> None:
        r   = self.rect()
        pad = Theme.nodeTextPaddingLeft
        self._input_proxy.setGeometry(QRectF(
            r.left() + pad,
            r.bottom() - self._INPUT_H - pad,
            r.width() - pad * 2,
            self._INPUT_H,
        ))

    def _bg_color(self) -> QColor:
        c = QColor(Theme.claudeBgColorFront if self.data.depth_front else Theme.claudeBgColor)
        c.setAlpha(Theme.claudeBgAlpha)
        return c

    def _apply_depth(self) -> None:
        super()._apply_depth()
        self.setBrush(self._bg_color())

    def setRect(self, rect) -> None:
        super().setRect(rect)
        if hasattr(self, '_combo_proxy'):
            self._position_combo()
        if hasattr(self, '_body_proxy'):
            self._position_body()
        if hasattr(self, '_input_proxy'):
            self._position_input()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        self._stop_process()
        if self._watcher:
            self._watcher.fileChanged.disconnect()
            self._watcher.deleteLater()
            self._watcher = None
        if hasattr(self, '_combo_proxy') and self._combo_proxy:
            self._combo_proxy.hide()
        if hasattr(self, '_body_proxy') and self._body_proxy:
            self._body_proxy.hide()
        if hasattr(self, '_input_proxy') and self._input_proxy:
            self._input_proxy.hide()
        self._combo = None
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

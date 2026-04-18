#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/ClaudeNode.py ClaudeNode class
-Skeletal Claude-branded node, ready to be packed with features, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import json
import queue
import re
import subprocess
import threading
from pathlib import Path

_ANSI_RE = re.compile(r'\x1b\[[^A-Za-z]*[A-Za-z]')

from PySide6.QtCore import QRectF, QFileSystemWatcher, QTimer, Signal, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import QGraphicsProxyWidget, QFrame, QVBoxLayout
from pretty_widgets.PrettyMenu import StyledTextEdit as QTextEdit

from nodes.BaseNode import BaseNode
from data.ClaudeNodeData import ClaudeNodeData
from pretty_widgets.graphics.Theme import Theme
import pretty_widgets.utils.settings as settings


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
        self._current_uuid: str | None = None
        self._watcher: QFileSystemWatcher | None = None
        self._file_offset: int = 0
        self._current_reply: str = ""
        self._reply_received: bool = False   # set True the moment file-watcher content arrives
        self._stdout_accumulated: str = ""   # full stdout of the current subprocess run
        self._last_response_node = None      # chain: wire new responses from the previous one

        self._reply_done_timer = QTimer()
        self._reply_done_timer.setSingleShot(True)
        self._reply_done_timer.setInterval(1500)
        self._reply_done_timer.timeout.connect(self._on_reply_done)

        # Debounce JSONL watcher — coalesces rapid burst writes during tool use
        self._jsonl_debounce = QTimer()
        self._jsonl_debounce.setSingleShot(True)
        self._jsonl_debounce.setInterval(150)
        self._jsonl_debounce.timeout.connect(self._process_jsonl_change)
        self._pending_jsonl_path: str = ""

        self._greeted: bool = False   # prevent double-greeting across session loads

        self._build_body()
        self._build_input()
        self._min_height = self._collapsed_height()
        # Fresh session each time — _current_uuid stays None until first prompt
        # self._auto_connect()

    # ─────────────────────────────────────────────────────────────────────────
    # SCENE LIFECYCLE — greeting on entry
    # ─────────────────────────────────────────────────────────────────────────

    def itemChange(self, change, value):
        if (change == self.GraphicsItemChange.ItemSceneHasChanged
                and value is not None
                and not self._greeted):
            # Give the event loop a moment to settle, then consider greeting.
            QTimer.singleShot(2000, self._attempt_greeting)
        return super().itemChange(change, value)

    def _attempt_greeting(self) -> None:
        """
        Send a quiet, hospitable greeting if the body is still empty and no
        user input has been sent yet.  Retries up to twice if the session
        UUID isn't wired yet (e.g. slow startup).
        """
        if self._greeted:
            return
        # Only greet when the body has no prior conversation content
        body_text = self.data.body_text.strip() if self.data.body_text else ""
        if body_text:
            self._greeted = True   # session loaded with content — no greeting needed
            return
        self._greeted = True
        self._send_greeting()

    def _send_greeting(self) -> None:
        """
        Fire a hidden greeting prompt — doesn't update the node title or
        body, just lets Claude say something warm into a response node.
        Samples a phrase from PhrasePicker to seed each greeting's tone.
        """
        import random
        from utils.PhrasePicker import motivationalMessages
        seed_phrase = random.choice(motivationalMessages)
        _GREETING_PROMPT = (
            "The user has just returned to Intricate — "
            "and Claude has arrived. Construct a brief, warm, civil "
            "greeting. One or two sentences at most. Be natural and unhurried, "
            "as if you're a thoughtful presence in the room rather than a chatbot. "
            f"Let the spirit of \"{seed_phrase}\" color the mood of your greeting — "
            "don't quote it directly, just let it influence the feeling and tone."
        )
        cmd = ["claude", "--print"]
        if self._current_uuid:
            cmd.append(f"--resume={self._current_uuid}")
        _project_cwd = str(Path(__file__).resolve().parent.parent)

        self._reply_received = False
        self._stdout_accumulated = ""
        self._last_response_node = None
        self._suppress_body_append = True   # greeting text only goes to response node
        self._pre_send_jsonl_stems: set = set()
        if self._current_uuid:
            jsonl_path = Path(self.data.folder_path) / f"{self._current_uuid}.jsonl"
            try:
                self._file_offset = jsonl_path.stat().st_size
            except OSError:
                pass
        else:
            p = Path(self.data.folder_path)
            self._pre_send_jsonl_stems = set(f.stem for f in p.glob("*.jsonl")) if p.exists() else set()
            self._file_offset = 0

        # Stop any in-flight stream before starting a new one
        if hasattr(self, '_stream_timer') and self._stream_timer:
            self._stream_timer.stop()
        self._stream_q = queue.SimpleQueue()
        self._status_q = queue.SimpleQueue()

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=_project_cwd,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        proc.stdin.write(_GREETING_PROMPT)
        proc.stdin.close()
        threading.Thread(target=self._read_proc_stdout, args=(proc, self._stream_q), daemon=True).start()
        threading.Thread(target=self._read_proc_stderr, args=(proc, self._status_q), daemon=True).start()
        self._stream_timer = QTimer()
        self._stream_timer.timeout.connect(self._flush_stream_title)
        self._stream_timer.start(150)

    # ─────────────────────────────────────────────────────────────────────────
    # AUTO CONNECT
    # ─────────────────────────────────────────────────────────────────────────

    def _auto_connect(self) -> None:
        """
        Find the 'Intricate Claude Node' session (or most recent) and connect.
        If no sessions exist yet, _current_uuid stays None — the first prompt
        sent via _send_input will create the session implicitly.
        """
        p = Path(self.data.folder_path)
        target_uuid = None
        fallback_uuid = None
        fallback_mtime = 0.0

        if p.exists():
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
        if uuid:
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
        # Debounce: restart the 150 ms window on every write event so rapid
        # tool-use bursts collapse into a single _process_jsonl_change call.
        self._pending_jsonl_path = path
        self._jsonl_debounce.start()
        # Re-add path immediately — some writers remove and recreate the file
        if self._watcher and path not in self._watcher.files():
            self._watcher.addPath(path)

    def _process_jsonl_change(self) -> None:
        """Read new JSONL lines after the debounce window settles."""
        path = self._pending_jsonl_path
        if not path:
            return
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
                            self._reply_received = True
                            self._reply_done_timer.start()
            except json.JSONDecodeError:
                pass

    def _scan_jsonl_for_reply(self) -> None:
        """
        Directly scan the JSONL file for new assistant text entries.

        Called after the subprocess exits as a reliable fallback when
        QFileSystemWatcher doesn't fire (common on Windows). If no JSONL text
        is found but stdout accumulated content, that is used instead so that
        a response node always spawns on success.

        When _current_uuid was None at send time, discovers the newly created
        JSONL, wires the watcher, and picks up its UUID for future sends.
        """
        if self._reply_received:
            return   # file watcher already handled it

        # If we started without a UUID, find the new JSONL the process created
        if not self._current_uuid:
            p = Path(self.data.folder_path)
            if p.exists():
                existing = getattr(self, '_pre_send_jsonl_stems', set())
                new_uuid = None
                newest_mtime = 0.0
                for jsonl_file in p.glob("*.jsonl"):
                    if jsonl_file.stem in existing:
                        continue
                    try:
                        mtime = jsonl_file.stat().st_mtime
                        if mtime > newest_mtime:
                            newest_mtime = mtime
                            new_uuid = jsonl_file.stem
                    except OSError:
                        pass
                if new_uuid:
                    self._current_uuid = new_uuid
                    self._start_watching(new_uuid)
            if not self._current_uuid:
                return   # session creation failed entirely
        jsonl_path = Path(self.data.folder_path) / f"{self._current_uuid}.jsonl"
        try:
            with open(jsonl_path, encoding="utf-8", errors="ignore") as f:
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
                            self._current_reply += text + " "
                            self._reply_received = True
            except json.JSONDecodeError:
                pass

        if self._reply_received:
            self._reply_done_timer.start()
            return

        # Last resort: use accumulated stdout content (plain text from --print)
        stdout = _ANSI_RE.sub('', self._stdout_accumulated).strip()
        if stdout:
            self._current_reply = stdout
            self._reply_received = True
            self._reply_done_timer.start()

    def _build_buttons(self) -> None:
        from nodes.NodeButton import NodeButton
        super()._build_buttons()
        show_pix = Theme.icon(Theme.claudeBodyShowIcon, fallback_color="#7ab8c9")
        hide_pix = Theme.icon(Theme.claudeBodyHideIcon, fallback_color="#4a7a8a")
        btn = NodeButton(self, show_pix, self._toggle_body, hide_pix, toggle=True)
        btn.setToolTip("Toggle Reply Body")
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
        self._position_input()
        self._position_buttons()

    def _rebuild_pens(self) -> None:
        w = Theme.claudeBorderWidth
        self.normal_pen   = QPen(self.normal_pen.color(),   w)
        self.hover_pen    = QPen(self.hover_pen.color(),    w)
        self.selected_pen = QPen(self.selected_pen.color(), w)
        self.setPen(self.normal_pen)

    def _on_theme_reload(self) -> None:
        try:
            self._rebuild_pens()
            self.update()
        except RuntimeError:
            pass

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
                color: {Theme.nodeFontColor};
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
            collapsed = self._collapsed_height()
            r = self.rect()
            self.prepareGeometryChange()
            self.setRect(QRectF(r.left(), r.top(), r.width(), collapsed))

    def _append_body(self, text: str) -> None:
        if getattr(self, '_suppress_body_append', False):
            return
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

        # Wrap in a QFrame so the outer dark border and inner light border can
        # both use the shorthand `border` property — Qt QSS only honours
        # border-radius reliably with the shorthand, not directional sides.
        self._input_frame = QFrame()
        self._input_frame.setObjectName("inputFrame")
        _layout = QVBoxLayout(self._input_frame)
        _layout.setContentsMargins(1, 1, 1, 1)
        _layout.setSpacing(0)
        _layout.addWidget(self._input)

        self._apply_input_style()
        if self.data.input_text:
            self._input.setPlainText(self.data.input_text)
        self._input.textChanged.connect(self._on_input_changed)
        self._input_proxy = QGraphicsProxyWidget(self)
        self._input_proxy.setWidget(self._input_frame)
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
        self._position_input()
        if not body_hidden:
            self._position_body()

    def _on_input_focused(self) -> None:
        self.data.depth_front = True
        self._apply_depth()

    # ── Node spawn directives ────────────────────────────────────────────────
    # Replies may contain <!--node:TYPE JSON--> directives. These are parsed
    # out before the response node is created, then executed after placement
    # to spawn companion nodes (palette, about, etc.) wired to the chain.

    _NODE_DIRECTIVE_RE = re.compile(r'<!--node:(\w+)\s+(.*?)-->', re.DOTALL)

    def _extract_node_directives(self, text: str):
        """Return (clean_text, [(type, kwargs), ...]) with directives stripped."""
        directives = []
        def _collect(match):
            try:
                directives.append((match.group(1), json.loads(match.group(2))))
            except (json.JSONDecodeError, ValueError):
                pass
            return ""
        clean = self._NODE_DIRECTIVE_RE.sub(_collect, text).strip()
        return clean, directives

    def _execute_node_directives(self, directives, anchor_node) -> None:
        """Spawn nodes described by directives and wire them to anchor_node."""
        scene = self.scene()
        if not scene:
            return
        from PySide6.QtCore import QPointF
        from graphics.Connection import Connection
        offset_y = 0.0
        for node_type, kwargs in directives:
            factory = getattr(scene, f'add_{node_type}_node', None)
            if factory is None:
                continue
            pos = anchor_node.pos() + QPointF(
                anchor_node.rect().width() + 30,
                offset_y,
            )
            spawned = factory(pos=pos, **kwargs)
            conn = Connection(anchor_node, spawned)
            scene.addItem(conn)
            offset_y += spawned.rect().height() + 20

    def _spawn_response_node(self, text: str) -> None:
        """Spawn ClaudeResponseNode(s) with text and wire them into the chain.

        If the text contains <!--chain--> markers, each segment becomes its own
        response node — chained in order, each with its own directives.

        Placement strategy per segment:
          1. Extract <!--node:TYPE JSON--> directives from the segment.
          2. Create the node off-screen so its real dimensions are known.
          3. Spiral outward from the current camera centre, probing a rect the
             exact size of the node (+ padding) against all existing scene nodes.
          4. Move the node to the first clear slot.
          5. Wire to the previous node in the chain.
          6. Spawn any directive nodes and wire them to the response node.
        """
        segments = text.split('<!--chain-->')
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            self._spawn_single_response(segment)

    def _spawn_single_response(self, text: str) -> None:
        """Spawn one ClaudeResponseNode, place it, wire it, execute directives."""
        import random
        import math
        from PySide6.QtCore import QPointF, QRectF

        scene = self.scene()
        if not scene:
            return

        # Strip spawn directives before creating the visible response node.
        clean_text, directives = self._extract_node_directives(text)
        if not clean_text and not directives:
            return

        # Build the node off-screen first so we know its real size.
        from nodes.BaseNode import BaseNode as _BaseNode
        _OFFSCREEN = QPointF(-999_999, -999_999)
        node = scene.add_claude_response_node(pos=_OFFSCREEN, label=clean_text or "(spawned nodes)", node_tint=getattr(self, '_chain_color', ''))
        nr   = node.rect()           # actual width × height after text layout
        NW, NH = nr.width(), nr.height()
        PADDING = 28                 # breathing room around each candidate rect

        def _clear(p: QPointF) -> bool:
            """True if placing the node at p would not overlap any existing node.
            Duck-typed to cover BaseNode + StickerNode roots."""
            candidate_rect = QRectF(p.x() - PADDING, p.y() - PADDING,
                                    NW + PADDING * 2, NH + PADDING * 2)
            for item in scene.items(candidate_rect):
                if item is node:
                    continue
                if hasattr(item, 'data') and hasattr(item, 'to_dict'):
                    return False
            return True

        views = scene.views()
        if views:
            view   = views[0]
            vr     = view.mapToScene(view.viewport().rect()).boundingRect()
            origin = vr.center()

            # Spiral outward: ring step = half the longer node dimension so
            # we never skip a gap wider than the node itself.
            STEP            = max(1, int(max(NW, NH)) // 2)
            MAX_RADIUS      = int(max(vr.width(), vr.height()) * 2.5)
            PROBES_PER_RING = 16   # more angles = fewer blind spots per ring

            pos   = origin
            found = _clear(origin)
            if not found:
                for radius in range(STEP, MAX_RADIUS, STEP):
                    base = random.uniform(0, 2 * math.pi)
                    for k in range(PROBES_PER_RING):
                        angle = base + k * (2 * math.pi / PROBES_PER_RING)
                        candidate = QPointF(
                            origin.x() + math.cos(angle) * radius,
                            origin.y() + math.sin(angle) * radius,
                        )
                        if _clear(candidate):
                            pos   = candidate
                            found = True
                            break
                    if found:
                        break

            if not found:
                # Canvas fully packed — nudge right of the chain tail
                wire_src = (
                    self._last_response_node
                    if self._last_response_node is not None
                       and self._last_response_node.scene()
                    else self
                )
                pos = wire_src.pos() + QPointF(wire_src.rect().width() + 40, 0)
        else:
            pos = self.pos() + QPointF(0, self.rect().height() + 16)

        node.setPos(pos)

        # Chain: wire from the previous response node if it still exists,
        # otherwise anchor back to the ClaudeNode as the chain root.
        from graphics.Connection import Connection
        wire_source = (
            self._last_response_node
            if self._last_response_node is not None and self._last_response_node.scene()
            else self
        )
        conn = Connection(wire_source, node)
        scene.addItem(conn)
        self._last_response_node = node

        # Spawn any companion nodes requested by directives in the reply.
        if directives:
            self._execute_node_directives(directives, node)

    def process_vision(self, image_b64: str, caption: str) -> None:
        """
        Send image_b64 to the Claude vision API and spawn a response node.

        Delegates to VisionWorker — never blocks the canvas.
        """
        import os
        from utils.vision import VisionWorker

        if not os.environ.get("SingleSharedBraincell_ApiKey", "").strip():
            self._spawn_response_node(
                "API key not set — check SingleSharedBraincell_ApiKey."
            )
            return

        prompt = "Describe this image in detail."
        if caption:
            prompt = f'Image caption: "{caption}"\n\n{prompt}'

        # Surface it in the body log and show a title spinner
        self._append_body(f"\n› [Vision: {caption or 'image'}]\n")
        self._last_response_node = None   # vision call starts a fresh chain
        _saved_title = self.data.title
        self.data.title = f"Vision: {caption or 'image'}…"
        self.update()

        def _on_finished(text: str):
            self.data.title = _saved_title
            self._append_body(text)
            self.update()
            self._spawn_response_node(text)

        def _on_failed(err: str):
            self.data.title = _saved_title
            self._append_body(err)
            self.update()
            self._spawn_response_node(err)

        worker = VisionWorker(
            image_b64=image_b64,
            prompt=prompt,
            model="claude-sonnet-4-6",
            max_tokens=1024,
            timeout=60,
            parent=self,
        )
        worker.finished.connect(_on_finished)
        worker.failed.connect(_on_failed)
        worker.start()
        self._vision_worker = worker   # prevent GC

    def _on_reply_done(self) -> None:
        self.data.depth_front = True
        self._apply_depth()
        close_after = getattr(self, '_close_on_reply', False)
        self._close_on_reply = False
        reply = self._current_reply.strip()
        self._current_reply = ""
        if reply and "no response requested" not in reply.lower():
            self._spawn_response_node(reply)

        if close_after:
            import json
            from pathlib import Path
            flag = Path(__file__).resolve().parent.parent / ".vaporize_restart.json"
            flag.write_text(json.dumps({"reply": reply}), encoding="utf-8")
            from PySide6.QtWidgets import QApplication, QMainWindow
            from PySide6.QtCore import QTimer
            win = next((w for w in QApplication.topLevelWidgets()
                        if isinstance(w, QMainWindow) and w.isVisible()), None)
            if win:
                QTimer.singleShot(400, win.close)

    def _check_error_response(self, status_text: str) -> None:
        """If the subprocess exited with no reply, surface a friendly error node."""
        if self._reply_received:
            return   # file-watcher confirmed content arrived — all good
        sl = status_text.lower()
        if any(kw in sl for kw in ("connect", "network", "unreachable", "timeout",
                                   "enotfound", "api connection", "no route")):
            msg = "No internet connection — remember to turn on WiFi before talking to the API."
        elif any(kw in sl for kw in ("api key", "authentication", "unauthorized", "401")):
            msg = "API key issue — check that SingleSharedBraincell_ApiKey is set correctly."
        elif status_text.strip():
            msg = f"Claude didn't respond:\n\n{status_text.strip()[:300]}"
        else:
            msg = "Claude didn't respond — no output received. Check your connection."
        self._spawn_response_node(msg)

    def _connected_input_context(self) -> str:
        """
        Collect context from nodes wired into this ClaudeNode, up to 2 hops deep.
        Returns a prefix string to prepend to the outgoing prompt, or "" if nothing
        is connected.  Each node type contributes what it knows:
            - All nodes: title and node_type
            - WarmNode / AboutNode: body_text / label
            - PaletteNode: list of hex colors
            - ImageNode: caption
            - ClaudeResponseNode: label (the response text)
        """

        def _node_text(src) -> str:
            if hasattr(src, 'sync_data'):
                src.sync_data()
            d = src.data
            lines = [f"[{d.node_type}] {d.title}"]
            if hasattr(d, 'colors') and d.colors:
                for c in d.colors:
                    h   = c.get('hex', '')
                    lbl = c.get('label', '').strip()
                    if h:
                        lines.append(f"  {lbl}: {h}" if lbl else f"  {h}")
            elif hasattr(d, 'body_text') and d.body_text.strip():
                lines.append(d.body_text.strip())
            elif hasattr(d, 'label') and d.label.strip():
                lines.append(d.label.strip())
            elif hasattr(d, 'caption') and d.caption.strip():
                lines.append(f"caption: {d.caption.strip()}")
            return "\n".join(lines)

        def _input_nodes(node):
            """Nodes wired into node's input ports (inbound only)."""
            for conn in list(getattr(node, 'connections', [])):
                try:
                    end = conn.end_node
                    src = conn.start_node
                except RuntimeError:
                    continue
                if end is node and src is not None and hasattr(src, 'data'):
                    yield src

        def _neighbor_nodes(node):
            """All nodes connected to node in either direction (for depth-2)."""
            for conn in list(getattr(node, 'connections', [])):
                try:
                    end = conn.end_node
                    src = conn.start_node
                except RuntimeError:
                    continue
                other = src if (end is node) else end
                if other is not None and hasattr(other, 'data'):
                    yield other

        parts = []
        seen = {id(self)}   # never include ClaudeNode itself
        for src in _input_nodes(self):
            uid = id(src)
            if uid in seen:
                continue
            seen.add(uid)
            parts.append(_node_text(src))
            for src2 in _neighbor_nodes(src):
                uid2 = id(src2)
                if uid2 in seen:
                    continue
                seen.add(uid2)
                parts.append("  " + _node_text(src2).replace("\n", "\n  "))

        if not parts:
            return ""
        return "Connected nodes:\n" + "\n\n".join(parts) + "\n\n"

    def _send_input(self, text: str) -> None:
        display_text = text                        # keep original for title/body
        text = self._preprocess_input(text)
        if self._handle_local_command(text):
            return

        # Update UI immediately — before any async work so the node feels responsive
        self._suppress_body_append = False   # user is talking; restore normal body logging
        self._append_body(f"\n› {display_text}\n")
        import textwrap
        self._title_question = textwrap.fill(display_text.capitalize(), width=84)
        self.data.title = self._title_question
        self.update()
        self.data.depth_front = False
        self._apply_depth()

        # Prepend context from any nodes wired into the input ports
        context = self._connected_input_context()
        if context:
            text = context + text

        # Snapshot JSONL size so the watcher only picks up new content.
        # When _current_uuid is None this is a brand-new session — snapshot existing
        # stems so we can identify the new JSONL after the process exits.
        self._pre_send_jsonl_stems: set = set()
        if self._current_uuid:
            jsonl_path = Path(self.data.folder_path) / f"{self._current_uuid}.jsonl"
            try:
                self._file_offset = jsonl_path.stat().st_size
            except OSError:
                pass
        else:
            p = Path(self.data.folder_path)
            self._pre_send_jsonl_stems = set(f.stem for f in p.glob("*.jsonl")) if p.exists() else set()
            self._file_offset = 0

        self._reply_received = False
        self._stdout_accumulated = ""
        self._last_response_node = None   # reset chain — new question anchors back to ClaudeNode
        from utils.ColorPicker import random as pick_color
        self._chain_color = pick_color()
        self._stream_q  = queue.SimpleQueue()
        self._status_q  = queue.SimpleQueue()

        # Call claude directly and pipe prompt via stdin — no tempfile,
        # no PowerShell, no string interpolation (injection-safe).
        cmd = ["claude", "--print"]
        if self._current_uuid:
            cmd.append(f"--resume={self._current_uuid}")
        # CWD must match the project the session was created in —
        # claude --resume maps sessions by project directory.
        _project_cwd = str(Path(__file__).resolve().parent.parent)

        # Stop any in-flight stream (e.g. greeting still running) before starting a new one
        if hasattr(self, '_stream_timer') and self._stream_timer:
            self._stream_timer.stop()

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=_project_cwd,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        proc.stdin.write(text)
        proc.stdin.close()
        threading.Thread(target=self._read_proc_stdout, args=(proc, self._stream_q), daemon=True).start()
        threading.Thread(target=self._read_proc_stderr, args=(proc, self._status_q), daemon=True).start()
        self._stream_timer = QTimer()
        self._stream_timer.timeout.connect(self._flush_stream_title)
        self._stream_timer.start(150)

    def _read_proc_stdout(self, proc, q) -> None:
        try:
            for chunk in iter(lambda: proc.stdout.read(64), ""):
                if chunk:
                    q.put(chunk)
        finally:
            q.put(None)

    def _read_proc_stderr(self, proc, q) -> None:
        try:
            for chunk in iter(lambda: proc.stderr.read(64), ""):
                if chunk:
                    q.put(chunk)
        finally:
            q.put(None)

    def _flush_stream_title(self) -> None:
        # Stdout — append response text to body as it streams
        chunks = []
        done = False
        while True:
            try:
                item = self._stream_q.get_nowait()
            except queue.Empty:
                break
            if item is None:
                done = True
                break
            chunks.append(item)
        if chunks:
            joined = "".join(chunks)
            self._append_body(joined)
            self._stdout_accumulated += joined

        # Stderr — show last visible status line (spinner, tool use) as title
        buf = getattr(self, "_status_buf", "")
        while True:
            try:
                chunk = self._status_q.get_nowait()
            except queue.Empty:
                break
            if chunk is None:
                break
            buf += chunk
        self._status_buf = buf
        if buf:
            segments = [_ANSI_RE.sub('', s).strip() for s in re.split(r'[\r\n]+', buf)]
            last = next((s for s in reversed(segments) if s), None)
            if last:
                new_title = last[-80:]
                if new_title != self.data.title:
                    self.data.title = new_title
                    self.update()

        if done:
            self._stream_timer.stop()
            final_status = self._status_buf
            self._status_buf = ""
            self.data.title = getattr(self, "_title_question", self.data.title)
            self.update()
            # Direct JSONL scan — don't rely solely on QFileSystemWatcher (unreliable on Windows).
            # Give the OS 200 ms to finish flushing the file, then scan manually.
            QTimer.singleShot(200, self._scan_jsonl_for_reply)
            # If neither watcher nor scan delivered a reply, surface a friendly error.
            QTimer.singleShot(800, lambda: self._check_error_response(final_status))

    def _preprocess_input(self, text: str) -> str:
        """Substitute escape tokens and strip post-action suffixes.
        Trailing 'then vaporize' sets _close_on_reply so the app closes
        after the response node spawns. [close] passes the literal word safely."""
        import re
        self._close_on_reply = bool(
            re.search(r'\bthen\s+vaporize\s*$', text, re.IGNORECASE)
        )
        text = re.sub(r'\s*,?\s*then\s+vaporize\s*$', '', text, flags=re.IGNORECASE).strip()
        return text.replace("[close]", "close")

    def _handle_local_command(self, text: str) -> bool:
        from PySide6.QtWidgets import QApplication, QMainWindow
        from PySide6.QtCore import QTimer
        # Only the exact /close command triggers — loose phrase matching made it
        # impossible to discuss the close event without accidentally firing it.
        if text.strip() == "/close":
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
        font.setStyleName("MediumOblique")
        painter.setFont(font)
        painter.setPen(QColor("#72b8b8"))   # Lombardi Lake variant
        title_rect = QRectF(
            r.left() + pad,
            r.top() + self._anim_top_offset + Theme.nodeFontVerticalOffset + Theme.nodeTextPaddingTop,
            r.width() - pad * 2,
            r.height() - self._anim_top_offset,
        )
        painter.drawText(title_rect, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, self.data.title)

        painter.restore()

    def _title_height(self) -> float:
        r    = self.rect()
        pad  = Theme.nodeTextPaddingLeft
        font = QFont(Theme.aboutFontFamily, max(1, Theme.aboutFontSize))
        font.setStyleName("MediumOblique")
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
        # Outer frame — primary border colour, matches node + window border
        rad_outer = max(4, int(self._input_h() / 2))
        rad_inner = max(3, rad_outer - 1)
        if hasattr(self, '_input_frame'):
            self._input_frame.setStyleSheet(f"""
                QFrame#inputFrame {{
                    border: 1px solid {Theme.primaryBorder};
                    border-radius: {rad_outer}px;
                    background: transparent;
                }}
            """)
        # Inner edit — slightly darker than node bg for visual separation
        input_bg = self._bg_color().darker(140)
        input_bg.setAlpha(255)
        self._input.setStyleSheet(f"""
            QTextEdit {{
                background: {input_bg.name()};
                color: {Theme.nodeFontColor};
                font-family: {Theme.claudeBodyFontFamily};
                font-size: {Theme.claudeBodyFontSize}pt;
                border: 1px solid rgba(255, 255, 255, 25);
                border-radius: {rad_inner}px;
                padding: 4px 10px;
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

    _demolition_timers = [
        ('_reply_done_timer', '_on_reply_done'),
        ('_jsonl_debounce',   '_process_jsonl_change'),
        ('_stream_timer',     '_flush_stream_title'),
    ]
    _demolition_proxies = ['_input_proxy', '_body_proxy']

    def _demolition_pre(self) -> None:
        # Sever the settings watcher's peer signal — it lives outside the
        # node's Qt object tree, so the crew has no way to know about it.
        if settings.watcher:
            try:
                settings.watcher.changed.disconnect(self._on_theme_reload)
            except (RuntimeError, TypeError):
                pass
        # Tear down the QFileSystemWatcher for the JSONL stream.  It's a
        # standalone QObject the node owns, not a proxied widget — crew
        # doesn't manage it, but its cleanup shape is stable.
        if self._watcher:
            try: self._watcher.fileChanged.disconnect()
            except (RuntimeError, TypeError): pass
            self._watcher.deleteLater()
            self._watcher = None

    def _demolition_post(self) -> None:
        # The crew tore down _input_proxy and _body_proxy (including
        # their inner widgets via setParent(None) + deleteLater()).
        # These refs are already stale Python-side after the crew's walk;
        # null them + the input_frame helper that lived alongside.
        if hasattr(self, '_input_frame') and self._input_frame:
            try: self._input_frame.deleteLater()
            except (RuntimeError, AttributeError): pass
        self._body = None
        self._input = None
        self._input_frame = None
        self._last_response_node = None   # sever response-chain reference

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

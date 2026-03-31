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
from PySide6.QtWidgets import QGraphicsProxyWidget, QTextEdit, QFrame, QVBoxLayout

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
        self._reply_received: bool = False   # set True the moment file-watcher content arrives
        self._stdout_accumulated: str = ""   # full stdout of the current subprocess run
        self._last_response_node = None      # chain: wire new responses from the previous one

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
        """
        Find the 'Intricate Claude Node' session (or most recent) and connect.
        If no sessions exist for this project, create a fresh one via `claude`.
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
        else:
            # No sessions found for this project — create a new one.
            threading.Thread(target=self._create_new_session, daemon=True).start()

    def _create_new_session(self) -> None:
        """
        Bootstrap a fresh Claude session for this project by running `claude`
        without --resume. Discovers the new JSONL UUID and wires up the watcher.
        Runs on a background thread; connects back to the main thread via QTimer.
        """
        p = Path(self.data.folder_path)
        # Snapshot existing JSONL stems before the new session is created
        existing = set(f.stem for f in p.glob("*.jsonl")) if p.exists() else set()

        # A silent seed prompt — the node checks this sentinel and won't spawn a response node.
        # Run with the project dir as CWD so Claude maps the session to the right folder.
        import os
        project_cwd = os.getcwd()   # main thread already chdir'd to the project folder
        _ps_cmd = "claude --print 'no response requested'"
        try:
            subprocess.run(
                ["powershell.exe", "-Command", _ps_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                cwd=project_cwd,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=60,
            )
        except Exception:
            return

        # Find the JSONL that appeared after the run
        def _on_main():
            if not p.exists():
                return
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

        QTimer.singleShot(0, _on_main)

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
                            self._reply_received = True
                            self._reply_done_timer.start()
            except json.JSONDecodeError:
                pass
        # Re-add path — some writers remove and recreate the file
        if self._watcher and path not in self._watcher.files():
            self._watcher.addPath(path)

    def _scan_jsonl_for_reply(self) -> None:
        """
        Directly scan the JSONL file for new assistant text entries.

        Called after the subprocess exits as a reliable fallback when
        QFileSystemWatcher doesn't fire (common on Windows). If no JSONL text
        is found but stdout accumulated content, that is used instead so that
        a response node always spawns on success.
        """
        if self._reply_received:
            return   # file watcher already handled it
        if not self._current_uuid:
            return
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
            collapsed = self._collapsed_height()
            self._min_height = collapsed
            r = self.rect()
            self.prepareGeometryChange()
            self.setRect(QRectF(r.left(), r.top(), r.width(), collapsed))

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
            self._min_height = collapsed_h
        self._position_input()
        if not body_hidden:
            self._position_body()

    def _on_input_focused(self) -> None:
        self.data.depth_front = True
        self._apply_depth()

    def _spawn_response_node(self, text: str) -> None:
        """Spawn a ClaudeResponseNode with text and wire it to this node."""
        import random
        from PySide6.QtCore import QPointF, QRectF
        scene = self.scene()
        if not scene:
            return
        views = scene.views()
        if views:
            view   = views[0]
            vr     = view.mapToScene(view.viewport().rect()).boundingRect()
            margin = 40

            def _pick_pos():
                return QPointF(
                    random.uniform(vr.left() + margin, vr.right()  - margin),
                    random.uniform(vr.top()  + margin, vr.bottom() - margin),
                )

            def _node_under(p):
                probe = QRectF(p.x() - 4, p.y() - 4, 8, 8)
                for item in scene.items(probe):
                    if hasattr(item, 'data'):
                        return item
                return None

            pos = _pick_pos()
            for _ in range(20):
                occupant = _node_under(pos)
                if occupant is None:
                    break
                if getattr(occupant.data, 'node_type', '') == 'claude_response':
                    break
                pos = _pick_pos()
        else:
            vr  = None
            pos = self.pos() + QPointF(0, self.rect().height() + 16)

        node = scene.add_claude_response_node(pos=pos, label=text)

        if views and vr is not None:
            nr = node.rect()
            margin = 40
            cx = max(vr.left() + margin,
                     min(node.pos().x(), vr.right()  - margin - nr.width()))
            cy = max(vr.top()  + margin,
                     min(node.pos().y(), vr.bottom() - margin - nr.height()))
            node.setPos(QPointF(cx, cy))

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

    def process_vision(self, image_b64: str, caption: str) -> None:
        """
        Send image_b64 to the Claude vision API and spawn a response node.

        Runs the HTTP call on a daemon thread — never blocks the canvas.
        Result arrives on the main thread via QTimer.singleShot.
        """
        import os
        import json
        import urllib.request
        import urllib.error

        api_key = os.environ.get("SingleSharedBraincell_ApiKey", "").strip()
        if not api_key:
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

        def _call():
            try:
                payload = json.dumps({
                    "model":      "claude-sonnet-4-6",
                    "max_tokens": 1024,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {
                                "type":   "image",
                                "source": {
                                    "type":       "base64",
                                    "media_type": "image/png",
                                    "data":       image_b64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }],
                }).encode("utf-8")

                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/messages",
                    data=payload,
                    headers={
                        "x-api-key":         api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type":      "application/json",
                    },
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                    text = body["content"][0]["text"].strip()
                except urllib.error.HTTPError as e:
                    detail = e.read().decode("utf-8", errors="replace")
                    text = f"Vision API error {e.code}:\n{detail[:300]}"
                except Exception as e:
                    text = f"Vision request failed:\n{e}"
            except Exception as e:
                text = f"Vision setup failed:\n{e}"

            def _done():
                self.data.title = _saved_title
                self._append_body(text)
                self.update()
                self._spawn_response_node(text)
            QTimer.singleShot(0, _done)

        threading.Thread(target=_call, daemon=True).start()

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
        Collect context from every node wired into this ClaudeNode's input ports.
        Returns a prefix string to prepend to the outgoing prompt, or "" if nothing
        is connected.  Each node type contributes what it knows:
            - All nodes: title and node_type
            - WarmNode / AboutNode / TextNode: body_text
            - ImageNode: caption (image bytes handled separately when vision is wired)
            - ClaudeResponseNode: label (the response text)
        """
        parts = []
        for conn in list(self.connections):
            try:
                end = conn.end_node
                src = conn.start_node
            except RuntimeError:
                continue
            if end is not self:
                continue
            if src is None or not hasattr(src, 'data'):
                continue
            if hasattr(src, 'sync_data'):
                src.sync_data()
            d = src.data
            section = [f"[{d.node_type}] {d.title}"]
            if hasattr(d, 'body_text') and d.body_text.strip():
                section.append(d.body_text.strip())
            elif hasattr(d, 'label') and d.label.strip():
                section.append(d.label.strip())
            elif hasattr(d, 'caption') and d.caption.strip():
                section.append(f"caption: {d.caption.strip()}")
            parts.append("\n".join(section))
        if not parts:
            return ""
        return "Connected nodes:\n" + "\n\n".join(parts) + "\n\n"

    def _send_input(self, text: str) -> None:
        display_text = text                        # keep original for title/body
        text = self._preprocess_input(text)
        if self._handle_local_command(text):
            return
        if not self._current_uuid:
            return
        # Prepend context from any nodes wired into the input ports
        context = self._connected_input_context()
        if context:
            text = context + text
        self._append_body(f"\n› {display_text}\n")
        import textwrap
        self._title_question = textwrap.fill(display_text.capitalize(), width=84)
        self.data.title = self._title_question
        self.update()
        self.data.depth_front = False
        self._apply_depth()
        jsonl_path = Path(self.data.folder_path) / f"{self._current_uuid}.jsonl"
        try:
            self._file_offset = jsonl_path.stat().st_size
        except OSError:
            pass
        self._reply_received = False
        self._stdout_accumulated = ""
        self._last_response_node = None   # reset chain — new question anchors back to ClaudeNode
        self._stream_q  = queue.SimpleQueue()
        self._status_q  = queue.SimpleQueue()
        # Write prompt to a temp file so PowerShell can read it back into $p —
        # this avoids both the Windows 32K command-line length limit and all
        # special-character escaping issues (brackets, dollar signs, backticks).
        import tempfile
        _tf = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", encoding="utf-8", delete=False
        )
        _tf.write(text)
        _tf.close()
        _tmp = _tf.name.replace("\\", "/")
        _ps_cmd = (
            f"$p = [System.IO.File]::ReadAllText('{_tmp}', "
            f"[System.Text.Encoding]::UTF8); "
            f"Remove-Item '{_tmp}' -ErrorAction SilentlyContinue; "
            f"claude --resume={self._current_uuid} --print $p"
        )
        proc = subprocess.Popen(
            ["powershell.exe", "-Command", _ps_cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        threading.Thread(target=self._read_proc_stdout, args=(proc,), daemon=True).start()
        threading.Thread(target=self._read_proc_stderr, args=(proc,), daemon=True).start()
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

    def _read_proc_stderr(self, proc) -> None:
        try:
            for chunk in iter(lambda: proc.stderr.read(64), ""):
                if chunk:
                    self._status_q.put(chunk)
        finally:
            self._status_q.put(None)

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
                self.data.title = last[-80:]
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
        # Inner edit — subtle light inset ring gives the bevel depth
        self._input.setStyleSheet(f"""
            QTextEdit {{
                background: {Theme.claudeBgColorInput};
                color: {Theme.aboutFontColor};
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

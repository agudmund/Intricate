#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/GitNode.py GitNode class
-A mundane but necessary git status dashboard for all Desktop repos for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import subprocess
import sys
from pathlib import Path

# On pythonw (no console) every subprocess.run spawns a visible console window
# unless we explicitly suppress it with CREATE_NO_WINDOW.
_SUBPROCESS_FLAGS = (
    subprocess.CREATE_NO_WINDOW
    if sys.platform == "win32" and not sys.stdout
    else 0
)

import threading

from PySide6.QtCore import Qt, QRectF, QPointF, QTimer
from PySide6.QtGui import QPainter, QFont, QColor
from PySide6.QtWidgets import QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsRectItem

from nodes.BaseNode import BaseNode
from data.GitNodeData import GitNodeData
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.PrettyButton import PrettyButton
from pretty_widgets.utils.logger import setup_logger

_log = setup_logger("git")

_ROW_H      = 20.0   # height per repo row
_DOT_R      = 5.0    # status dot radius
_POLL_MS    = 10000   # default refresh period — overridden by [node.git] poll_interval_ms


def _get_excluded_repos() -> set[str]:
    """Read [node.git] exclude_repos live at call time.  Folders whose
    basename appears here are skipped during scan + push — used for
    cloned-but-not-maintained repos living on Desktop alongside the
    user's own projects."""
    import ast
    import pretty_widgets.utils.settings as _s
    val = _s.get_nested("node", "git", "exclude_repos", default=[])
    if isinstance(val, list):
        return set(val)
    if isinstance(val, str) and val.strip().startswith("["):
        try:
            result = ast.literal_eval(val)
            if isinstance(result, (list, tuple)):
                return set(result)
        except Exception:
            pass
    return set()


def _get_poll_interval_ms() -> int:
    """Read [node.git] poll_interval_ms at call time, with fallback to
    the baked-in default."""
    import pretty_widgets.utils.settings as _s
    val = _s.get_nested("node", "git", "poll_interval_ms", default=_POLL_MS)
    try:
        return max(1000, int(val))   # floor at 1s to avoid runaway scans
    except (TypeError, ValueError):
        return _POLL_MS


_DOT_COLORS_DEFAULT = {
    "session":  "#7ac47a",   # green
    "dirty":    "#7a9ac4",   # blue
    "unpushed": "#c4a87a",   # amber
}


def _get_status_colors() -> dict:
    """Read [node.git] status_color_* keys at call time, with fallback
    to the baked-in defaults.  Each key maps a status name to a hex
    string; the caller feeds that into QColor to paint the dot."""
    import pretty_widgets.utils.settings as _s
    return {
        status: _s.get_nested("node", "git", f"status_color_{status}",
                              default=_DOT_COLORS_DEFAULT[status])
        for status in _DOT_COLORS_DEFAULT
    }


from utils.persistence.session import SESSION_EXT
# Legacy session filenames still classify as session-only during migration.
# Current scheme uses {project}.intricate with timestamped backups, both
# caught by the suffix + path checks below.
_LEGACY_SESSION_FILENAMES = {
    "session.json", "session_previous.json", "session_archive.json",
}
_SESSION_DIRS      = {"backup", "Backup", "Documents", "data", "cache", "Data", "Cache"}


def _is_session_path(raw: str) -> bool:
    """Check if a porcelain path is session-related (files or directories).

    Matches:
      - Any *.intricate file (live session, timestamped backups, legacy names)
      - The Documents/Data/ tree (Backup/, Cache/)
      - Image node cache PNGs (Documents/Data/Cache/*.png)
      - Warm bridge files (.warm_bridge_*.json)
    """
    p = raw.strip().strip('"').rstrip("/")
    name = Path(p).name
    if name in _LEGACY_SESSION_FILENAMES or name in _SESSION_DIRS:
        return True
    # Any .intricate file — covers {project}.intricate and all timestamped
    # backups under Backup/ without needing a pattern list
    if name.endswith(SESSION_EXT):
        return True
    # Image cache PNGs inside Documents/Data/Cache/ (case-insensitive match
    # so legacy lowercase layouts pre-2026-04-24 still classify correctly).
    pl = p.lower()
    if "documents/data/cache/" in pl or "documents\\data\\cache\\" in pl:
        return True
    # Warm bridge temp files
    if name.startswith(".warm_bridge_") and name.endswith(".json"):
        return True
    return False


# Status: "clean" = no changes, "session" = only session files, "dirty" = real changes
def _scan_repos() -> list[tuple[str, str]]:
    """Scan ~/Desktop for git repos. Returns [(name, status), ...] sorted.

    Statuses: dirty, session, unpushed, clean.
    """
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        return []
    excluded = _get_excluded_repos()
    repos = []
    for folder in sorted(desktop.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        if folder.name in excluded:
            continue
        git_dir = folder / ".git"
        if not git_dir.exists():
            continue
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(folder),
                capture_output=True, text=True, timeout=5,
                creationflags=_SUBPROCESS_FLAGS,
            )
            lines = result.stdout.strip().splitlines()
            if lines:
                all_session = all(
                    _is_session_path(line[3:])
                    for line in lines if len(line) > 3
                )
                repos.append((folder.name, "session" if all_session else "dirty"))
            else:
                # Working tree clean — check if ahead of remote
                ahead = subprocess.run(
                    ["git", "rev-list", "--count", "@{u}..HEAD"],
                    cwd=str(folder),
                    capture_output=True, text=True, timeout=5,
                    creationflags=_SUBPROCESS_FLAGS,
                )
                count = ahead.stdout.strip()
                if count.isdigit() and int(count) > 0:
                    repos.append((folder.name, "unpushed"))
                else:
                    repos.append((folder.name, "clean"))
        except Exception:
            repos.append((folder.name, "dirty"))
    return repos



class _CommitDialog(QDialog):
    """Frameless commit-message dialog matching the app's visual language."""

    def __init__(self, repo_count: int, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(380)

        # ── Outer container with background + border ─────────────────────
        container = QWidget(self)
        container.setStyleSheet(f"""
            QWidget#commitContainer {{
                background: {Theme.windowBg};
                border: 1px solid {Theme.primaryBorder};
                border-radius: 9px;
            }}
        """)
        container.setObjectName("commitContainer")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ── Label ────────────────────────────────────────────────────────
        label = QLabel(f"Commit message for {repo_count} session repo(s):")
        label.setStyleSheet(f"""
            color: {Theme.textPrimary};
            font-family: '{Theme.healthFontFamily}';
            font-size: {Theme.healthFontSizeLabel}pt;
        """)
        label.setWordWrap(True)
        layout.addWidget(label)

        # ── Text input ───────────────────────────────────────────────────
        # PrettyEdit in proxy-less mode for regular dialog layout.
        from pretty_widgets.PrettyEdit import PrettyEdit
        from PySide6.QtGui import QFontMetrics as _QFM
        self._input = PrettyEdit(
            None,
            font_family    = Theme.healthFontFamily,
            font_size      = Theme.healthFontSizeLabel,
            font_color     = Theme.textPrimary,
            always_visible = True,
            enter_commits  = True,
            placeholder    = "session sync\u2026",
        )
        self._input.setStyleSheet(f"""
            QTextEdit {{
                background: {Theme.backDrop};
                color: {Theme.textPrimary};
                border: 1px solid {Theme.primaryBorder};
                border-radius: 5px;
                padding: 6px 10px;
                font-family: '{Theme.healthFontFamily}';
                font-size: {Theme.healthFontSizeLabel}pt;
            }}
        """)
        _fm = _QFM(self._input.font())
        self._input.setFixedHeight(_fm.lineSpacing() + 14)
        self._input.committed.connect(lambda _t: self.accept())
        layout.addWidget(self._input)

        # ── Buttons ──────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        cancel_btn = PrettyButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        ok_btn = PrettyButton("Push")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)

        layout.addLayout(btn_row)

        self._input.setFocus()

    def message(self) -> str:
        return self._input.toPlainText().strip()


class GitNode(BaseNode):
    _has_depth_toggle = True
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
        c.setAlpha(Theme.aboutTransparency)
        self.setBrush(c)
        self._apply_depth()

        self._repos: list[tuple[str, bool]] = []
        self._scanning = False
        self._pending_repos = None          # written by worker thread
        self._loading_node = None           # VideoNode spawned during scan
        self._pushing = False               # True while bulk push worker is running
        self._push_dirty = False            # set by worker thread when a repo finishes
        self._push_complete = False         # set by worker thread when all futures done
        self._first_scan = False            # set True by Scene.add_git_node for sidebar spawns

        # Delivery timer — runs on main thread, checks for worker results
        self._delivery_timer = QTimer()
        self._delivery_timer.setInterval(250)
        self._delivery_timer.timeout.connect(self._check_delivery)

        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._refresh)
        self._poll_timer.start(_get_poll_interval_ms())
        # Initial scan deferred so the node appears immediately
        QTimer.singleShot(0, self._refresh)

    def _refresh(self) -> None:
        if self._scanning:
            return
        self._scanning = True
        if self._first_scan:
            self._spawn_loading_node()
        self._delivery_timer.start()
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _spawn_loading_node(self) -> None:
        """Spawn a VideoNode playing the plushie animation wired to this node."""
        scene = self.scene()
        if not scene:
            return
        video_path = str(
            Path(__file__).resolve().parent.parent / "Images" / "Progress Bar Animation.mp4"
        )
        # Place it to the right of this node
        r = self.rect()
        spawn_pos = self.mapToScene(QPointF(r.right() + 30, r.top()))
        from nodes.VideoNode import VideoNode
        video_node = VideoNode()
        video_node._spawn_label = False
        video_node.data.looping = True
        if spawn_pos is not None:
            video_node.setPos(spawn_pos)
        scene.addItem(video_node)
        video_node.load_from_path(video_path)
        # Wire them together
        from graphics.Connection import Connection
        wire = Connection(self, video_node)
        scene.addItem(wire)
        self._loading_node = video_node

    def _dismiss_loading_node(self) -> None:
        """Destroy the loading VideoNode with a particle burst."""
        node = self._loading_node
        self._loading_node = None
        if node is None:
            return
        scene = node.scene()
        if not scene:
            return

        from graphics.Particles import sprinkle
        center = node.mapToScene(node.rect().center())

        # Strip all wires from the video node
        for conn in list(node.connections):
            conn._glide_timer.stop()
            try:
                conn._glide_timer.timeout.disconnect(conn._glide_tick)
            except RuntimeError:
                pass
            other = conn.end_node if conn.start_node is node else conn.start_node
            if other is not None and other is not node:
                try:
                    other.connections.remove(conn)
                except ValueError:
                    pass
            conn.start_node = None
            conn.end_node = None
            if conn.scene():
                scene.removeItem(conn)
        node.connections.clear()

        # Particle burst + deferred removal
        # Stop the video player and sever its media links NOW so no frames
        # are delivered during the deferred-removal window.  Full teardown
        # happens via itemChange → _prepare_for_removal when removeItem fires.
        sprinkle(scene, center, count=8000)
        if hasattr(node, '_player'):
            node._player.stop()
            node._player.setVideoOutput(None)
            node._player.setAudioOutput(None)
        node.setVisible(False)
        node.setFlags(QGraphicsRectItem.GraphicsItemFlags(0))
        def _remove(n=node, sc=scene):
            try:
                sc.removeItem(n)
            except RuntimeError:
                pass
        QTimer.singleShot(0, _remove)

    def _scan_worker(self) -> None:
        try:
            self._pending_repos = _scan_repos()
        except Exception:
            self._pending_repos = []

    def _check_delivery(self) -> None:
        """Main-thread timer that picks up scan results and push-worker signals.

        During push, the worker sets _push_dirty each time a repo finishes.
        We trigger a rescan when dirty, and handle push completion when
        _push_complete is set — all on the main thread, no cross-thread timers.
        """
        # ── Push-worker signals (thread-safe flags → main-thread actions) ──
        if getattr(self, '_push_dirty', False):
            self._push_dirty = False
            if not self._scanning:
                self._scanning = True
                threading.Thread(target=self._scan_worker, daemon=True).start()

        if getattr(self, '_push_complete', False):
            self._push_complete = False
            self._pushing = False
            self._dismiss_loading_node()
            import random
            from utils.pickers.IconPicker import emojiIcons
            self.data.emoji = random.choice(emojiIcons)
            self._poll_timer.start()
            # One final rescan to capture the last push results
            if not self._scanning:
                self._scanning = True
                threading.Thread(target=self._scan_worker, daemon=True).start()

        # ── Scan result delivery ────────────────────────────────────────────
        if self._pending_repos is None:
            return
        repos = self._pending_repos
        self._pending_repos = None
        self._scanning = False
        self._first_scan = False
        if not self._pushing:
            self._delivery_timer.stop()
            self._dismiss_loading_node()
        try:
            self._repos = repos
            self._auto_height()
            self.update()
        except RuntimeError:
            self._poll_timer.stop()

    def _auto_height(self) -> None:
        """Resize to fit dirty + session + unpushed groups, leaving clean repos for manual expand."""
        dirty    = sum(1 for _, s in self._repos if s == "dirty")
        session  = sum(1 for _, s in self._repos if s == "session")
        unpushed = sum(1 for _, s in self._repos if s == "unpushed")
        rows = dirty + session + unpushed
        groups = sum(1 for g in (dirty, session, unpushed) if g)
        if groups > 1:
            rows += groups - 1   # separators between groups
        # Minimum: header area even if nothing dirty
        rows = max(rows, 1)
        h = self._BUTTON_ZONE_H + self._BODY_OFFSET + rows * _ROW_H + 16
        r = self.rect()
        if abs(r.height() - self.data.height) < 1.0:
            # Only auto-resize if the user hasn't manually resized
            self.prepareGeometryChange()
            self.setRect(QRectF(r.x(), r.y(), r.width(), h))
            self.data.height = h

    def _build_buttons(self) -> None:
        super()._build_buttons()
        from nodes.NodeButton import NodeButton as _NodeButton

        # GitHub Desktop launcher
        gh_pix = Theme.icon(Theme.iconGithubDesktop, fallback_color="#8a9a8a")
        gh_btn = _NodeButton(self, gh_pix, lambda: self._launch_github_desktop())
        gh_btn.setToolTip("Open GitHub Desktop")
        self._buttons.append(gh_btn)

        # Bulk push session-only repos
        push_pix = Theme.icon(Theme.iconPush, fallback_color="#8a9a8a")
        self._push_btn = _NodeButton(self, push_pix, self._bulk_push_sessions)
        self._push_btn.setToolTip("Push all session-only repos")
        self._buttons.append(self._push_btn)

    def _launch_github_desktop(self) -> None:
        """Focus GitHub Desktop if running, otherwise launch it. Roll up curtains."""
        import ctypes
        user32 = ctypes.windll.user32

        # Try to find an existing GitHub Desktop window
        hwnd = user32.FindWindowW(None, None)
        found = 0
        while hwnd:
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    if "GitHub Desktop" in buf.value:
                        found = hwnd
                        break
            hwnd = user32.GetWindow(hwnd, 2)  # GW_HWNDNEXT

        # Roll up curtains before switching
        try:
            views = self.scene().views() if self.scene() else []
            if views:
                mw = views[0].window()
                if hasattr(mw, 'is_collapsed') and not mw.is_collapsed:
                    mw.toggle_curtains()
        except Exception:
            pass

        if found:
            # Maximize and focus the existing window
            SW_MAXIMIZE = 3
            user32.ShowWindow(found, SW_MAXIMIZE)
            user32.SetForegroundWindow(found)
            _log.info("[git] focused existing GitHub Desktop")
        else:
            import os
            try:
                os.startfile("github-windows://")
                _log.info("[git] launched GitHub Desktop — polling for window")
                self._poll_maximize_github(user32)
            except Exception:
                _log.warning("[git] failed to launch GitHub Desktop", exc_info=True)

    def _poll_maximize_github(self, user32) -> None:
        """Poll for the GitHub Desktop window to appear, then maximize it."""
        attempts = [0]
        timer = QTimer()
        timer.setInterval(500)

        def _check():
            attempts[0] += 1
            hwnd = user32.FindWindowW(None, None)
            while hwnd:
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        import ctypes
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        if "GitHub Desktop" in buf.value:
                            user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
                            user32.SetForegroundWindow(hwnd)
                            _log.info("[git] maximized GitHub Desktop after launch")
                            timer.stop()
                            return
                hwnd = user32.GetWindow(hwnd, 2)
            if attempts[0] >= 20:  # ~10 seconds
                _log.warning("[git] gave up waiting for GitHub Desktop window")
                timer.stop()

        timer.timeout.connect(_check)
        timer.start()

    def _bulk_push_sessions(self) -> None:
        """Prompt for a commit message, then git add+commit+push all green-dot repos on a worker thread."""
        session_repos  = [name for name, status in self._repos if status == "session"]
        unpushed_repos = [name for name, status in self._repos if status == "unpushed"]
        if not session_repos and not unpushed_repos:
            return

        # Check connectivity before committing — catch the "wifi is off" morning scenario
        if not self._check_online():
            return

        # Session repos need a commit message; unpushed repos already have one
        msg = ""
        if session_repos:
            win = self._lower_window()
            was_collapsed = False
            try:
                views = self.scene().views() if self.scene() else []
                if views:
                    mw = views[0].window()
                    if hasattr(mw, 'is_collapsed') and not mw.is_collapsed:
                        mw.toggle_curtains()
                        was_collapsed = True
            except Exception:
                pass
            dlg = _CommitDialog(len(session_repos))
            result = dlg.exec()
            if was_collapsed:
                try:
                    mw.toggle_curtains()
                except Exception:
                    pass
            self._raise_window(win)
            if result != QDialog.DialogCode.Accepted or not dlg.message().strip():
                return
            msg = dlg.message().strip()

        self._loading_node = None   # clear any stale ref from initial scan
        self._pushing = True
        self._push_dirty = False
        self._push_complete = False
        self._spawn_loading_node()
        self._poll_timer.stop()   # pause polling while push runs
        self._delivery_timer.start()  # keep delivery timer alive for push signals
        _log.info("[git] plushie spawned for bulk push")
        threading.Thread(
            target=self._push_worker,
            args=(session_repos, unpushed_repos, msg),
            daemon=True,
        ).start()

    def _check_online(self) -> bool:
        """Quick connectivity check. Spawns an AboutNode reminder if offline."""
        import socket
        try:
            socket.create_connection(("github.com", 443), timeout=3).close()
            return True
        except OSError:
            pass
        scene = self.scene()
        if scene:
            r = self.rect()
            pos = self.mapToScene(QPointF(r.right() + 30, r.center().y()))
            about = scene.add_about_node(
                pos=pos,
                label="You should probably turn the internet on before pushing things to git",
            )
            from graphics.Connection import Connection
            wire = Connection(self, about)
            scene.addItem(wire)
        self.data.emoji = "\U0001f612"   # 😒
        self.update()
        _log.warning("[git] offline — push aborted")
        return False

    def _push_worker(self, session_repos: list[str], unpushed_repos: list[str], msg: str) -> None:
        """Parallel push — each repo gets its own thread, fastest finishes first.

        Cross-thread communication uses _push_dirty flag instead of
        QTimer.singleShot (which doesn't reliably cross thread boundaries
        in PySide6).  The delivery timer already ticks every 250ms on the
        main thread — it picks up the flag and triggers a rescan.
        """
        import subprocess as _sp
        from concurrent.futures import ThreadPoolExecutor, as_completed

        desktop = Path.home() / "Desktop"

        def _git(cmd, cwd):
            r = _sp.run(cmd, cwd=cwd, capture_output=True, text=True,
                        timeout=60, creationflags=_SUBPROCESS_FLAGS)
            if r.returncode != 0:
                _log.warning(f"[git] {cmd} failed in {Path(cwd).name}: {r.stderr.strip()}")
            return r

        def _push_session(name):
            cwd = str(desktop / name)
            _git(["git", "add", "-A"], cwd)
            _git(["git", "commit", "-m", msg], cwd)
            result = _git(["git", "push"], cwd)
            if result.returncode == 0:
                _log.info(f"[git] pushed {name}")
            return name

        def _push_unpushed(name):
            cwd = str(desktop / name)
            result = _git(["git", "push"], cwd)
            if result.returncode == 0:
                _log.info(f"[git] pushed unpushed {name}")
            return name

        remaining = len(session_repos) + len(unpushed_repos)
        futures = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            for name in session_repos:
                futures.append(pool.submit(_push_session, name))
            for name in unpushed_repos:
                futures.append(pool.submit(_push_unpushed, name))

            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    _log.warning(f"[git] parallel push failed: {e}", exc_info=True)
                remaining -= 1
                # Signal the main-thread delivery timer to rescan
                self._push_dirty = True

        # All futures done — signal completion for the delivery timer
        self._push_complete = True

    # Legacy hardcoded default that means "use Theme" — not a real custom tint.
    # Existing sessions saved with this value fall through to the theme colours.
    _LEGACY_TINTS = {"#4a3a5a"}

    def _bg_color(self) -> QColor:
        tint = getattr(self.data, 'node_tint', '')
        if tint and tint.lower() not in self._LEGACY_TINTS and QColor(tint).isValid():
            c = QColor(tint)
        else:
            c = QColor(Theme.gitBgColorFront if self.data.depth_front else Theme.gitBgColor)
        c.setAlpha(Theme.aboutTransparency)
        return c

    def _apply_depth(self) -> None:
        super()._apply_depth()
        # Stop any in-flight animation before setting the new color — otherwise
        # _on_bg_changed fires after us and overwrites the brush with the old target.
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
        pad = self._CONTENT_PAD
        top = self._content_top()
        title_font = QFont(self._TITLE_FONT, max(1, Theme.aboutFontSize + self._TITLE_FONT_BUMP))
        title_font.setStyleName(self._TITLE_STYLE)
        painter.setFont(title_font)
        painter.setPen(QColor("#72b8b8"))   # Lombardi Lake variant — teal lifted for plum contrast
        painter.drawText(
            QRectF(r.left() + pad, r.top() + top, r.width() - pad * 2, self._TITLE_HEIGHT),
            Qt.AlignLeft | Qt.AlignTop,
            "Git Status",
        )

        # Repo list
        body_font = QFont(self._BODY_FONT, max(1, Theme.aboutFontSize + self._BODY_FONT_BUMP))
        painter.setFont(body_font)
        y = r.top() + self._body_top()

        if not self._repos:
            painter.setPen(QColor(Theme.nodeFontColor))
            painter.setOpacity(0.5)
            msg = "hang on, gimme a sec..." if self._scanning else "No git repos found on Desktop"
            painter.drawText(
                QRectF(r.left() + pad, y, r.width() - pad * 2, _ROW_H),
                Qt.AlignLeft | Qt.AlignVCenter,
                msg,
            )
        else:
            dirty    = [(n, s) for n, s in self._repos if s == "dirty"]
            session  = [(n, s) for n, s in self._repos if s == "session"]
            unpushed = [(n, s) for n, s in self._repos if s == "unpushed"]
            clean    = [(n, s) for n, s in self._repos if s == "clean"]

            def _draw_group(group):
                nonlocal y
                for name, status in group:
                    if y + _ROW_H > r.bottom():
                        return
                    if status != "clean":
                        _dot_colors = _get_status_colors()
                        dot_color = QColor(_dot_colors.get(status, _DOT_COLORS_DEFAULT["dirty"]))
                        painter.setBrush(dot_color)
                        painter.setPen(Qt.NoPen)
                        dot_x = r.left() + pad + _DOT_R
                        dot_y = y + _ROW_H / 2
                        painter.drawEllipse(QRectF(dot_x - _DOT_R, dot_y - _DOT_R, _DOT_R * 2, _DOT_R * 2))
                    painter.setPen(QColor(Theme.nodeFontColor))
                    painter.setOpacity(0.85)
                    painter.drawText(
                        QRectF(r.left() + pad + _DOT_R * 2 + 8, y, r.width() - pad * 2 - _DOT_R * 2 - 8, _ROW_H),
                        Qt.AlignLeft | Qt.AlignVCenter,
                        name,
                    )
                    painter.setOpacity(1.0)
                    y += _ROW_H

            def _draw_sep():
                nonlocal y
                if y + _ROW_H > r.bottom():
                    return
                sep_y = y + _ROW_H / 2
                painter.setPen(QColor(Theme.primaryBorder))
                painter.setOpacity(0.3)
                painter.drawLine(
                    int(r.left() + pad), int(sep_y),
                    int(r.right() - pad), int(sep_y),
                )
                painter.setOpacity(1.0)
                y += _ROW_H

            if dirty:
                _draw_group(dirty)
            if session:
                if dirty:
                    _draw_sep()
                _draw_group(session)
            if unpushed:
                if dirty or session:
                    _draw_sep()
                _draw_group(unpushed)
            if clean:
                if dirty or session or unpushed:
                    _draw_sep()
                _draw_group(clean)

        painter.restore()

    _demolition_timers = [
        ('_poll_timer',     '_refresh'),
        ('_delivery_timer', '_check_delivery'),
    ]

    def _demolition_pre(self) -> None:
        # Loading plushie is a child VideoNode wired to this GitNode
        # during push — must come down synchronously before the crew
        # starts tearing down its own signal surface, because the plushie
        # dismiss has its own orchestrated ordering (stop player, sever
        # media links, clear wires).
        self._dismiss_loading_node()

    def to_dict(self) -> dict:
        return self.data.to_dict()

    @staticmethod
    def from_dict(d: dict) -> 'GitNode':
        return GitNode(GitNodeData.from_dict(d))

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

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QPainter, QFont, QColor
from PySide6.QtWidgets import QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel

from nodes.BaseNode import BaseNode
from data.GitNodeData import GitNodeData
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.PrettyButton import PrettyButton
from pretty_widgets.utils.logger import setup_logger

_log = setup_logger("git")

_ROW_H      = 20.0   # height per repo row
_DOT_R      = 5.0    # status dot radius
_POLL_MS    = 10000   # refresh every 10 seconds


_SESSION_FILENAMES = {"session.json", "session_previous.json", "session_archive.json"}
_SESSION_DIRS      = {"backup", "Documents", "data"}


def _is_session_path(raw: str) -> bool:
    """Check if a porcelain path is session-related (files or directories)."""
    p = raw.strip().strip('"').rstrip("/")
    name = Path(p).name
    return name in _SESSION_FILENAMES or name in _SESSION_DIRS


# Status: "clean" = no changes, "session" = only session files, "dirty" = real changes
def _scan_repos() -> list[tuple[str, str]]:
    """Scan ~/Desktop for git repos. Returns [(name, status), ...] sorted."""
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
                creationflags=_SUBPROCESS_FLAGS,
            )
            lines = result.stdout.strip().splitlines()
            if not lines:
                repos.append((folder.name, "clean"))
            else:
                all_session = all(
                    _is_session_path(line[3:])
                    for line in lines if len(line) > 3
                )
                repos.append((folder.name, "session" if all_session else "dirty"))
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
        from pretty_widgets.PrettyMenu import StyledLineEdit
        self._input = StyledLineEdit()
        self._input.setPlaceholderText("session sync\u2026")
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {Theme.backDrop};
                color: {Theme.textPrimary};
                border: 1px solid {Theme.primaryBorder};
                border-radius: 5px;
                padding: 6px 10px;
                font-family: '{Theme.healthFontFamily}';
                font-size: {Theme.healthFontSizeLabel}pt;
            }}
        """)
        self._input.returnPressed.connect(self.accept)
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
        return self._input.text()


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
        c.setAlpha(Theme.aboutBgAlpha)
        self.setBrush(c)
        self._apply_depth()

        self._repos: list[tuple[str, bool]] = []
        self._scanning = False
        self._pending_repos = None          # written by worker thread

        # Delivery timer — runs on main thread, checks for worker results
        self._delivery_timer = QTimer()
        self._delivery_timer.setInterval(250)
        self._delivery_timer.timeout.connect(self._check_delivery)

        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._refresh)
        self._poll_timer.start(_POLL_MS)
        # Initial scan deferred so the node appears immediately
        QTimer.singleShot(0, self._refresh)

    def _refresh(self) -> None:
        if self._scanning:
            return
        self._scanning = True
        self._delivery_timer.start()
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self) -> None:
        try:
            self._pending_repos = _scan_repos()
        except Exception:
            self._pending_repos = []

    def _check_delivery(self) -> None:
        """Main-thread timer that picks up results from the worker."""
        if self._pending_repos is None:
            return
        repos = self._pending_repos
        self._pending_repos = None
        self._scanning = False
        self._delivery_timer.stop()
        try:
            self._repos = repos
            self._auto_height()
            self.update()
        except RuntimeError:
            self._poll_timer.stop()

    def _auto_height(self) -> None:
        """Resize to fit dirty + session groups, leaving clean repos for manual expand."""
        dirty   = sum(1 for _, s in self._repos if s == "dirty")
        session = sum(1 for _, s in self._repos if s == "session")
        rows = dirty + session
        if dirty and session:
            rows += 1   # separator
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
        push_pix = Theme.icon(Theme.iconGitPush, fallback_color="#8a9a8a")
        self._push_btn = _NodeButton(self, push_pix, self._bulk_push_sessions)
        self._push_btn.setToolTip("Push all session-only repos")
        self._buttons.append(self._push_btn)

    def _launch_github_desktop(self) -> None:
        """Launch GitHub Desktop as a detached process."""
        import os
        try:
            os.startfile("github-windows://")
            _log.info("[git] launched GitHub Desktop")
        except Exception:
            _log.warning("[git] failed to launch GitHub Desktop", exc_info=True)

    def _bulk_push_sessions(self) -> None:
        """Prompt for a commit message, then git add+commit+push all green-dot repos on a worker thread."""
        session_repos = [name for name, status in self._repos if status == "session"]
        if not session_repos:
            return

        win = self._lower_window()
        # Roll up curtains so the canvas tucks into the titlebar while the
        # dialog is open, then roll back down graciously after.
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

        threading.Thread(
            target=self._push_worker,
            args=(session_repos, dlg.message().strip()),
            daemon=True,
        ).start()

    def _push_worker(self, repos: list[str], msg: str) -> None:
        """Run git add+commit+push for each repo on a background thread."""
        import subprocess as _sp
        from PySide6.QtCore import QTimer

        desktop = Path.home() / "Desktop"
        for name in repos:
            cwd = str(desktop / name)
            try:
                _run = lambda cmd: _sp.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30, creationflags=_SUBPROCESS_FLAGS)
                _run(["git", "add", "-A"])
                _run(["git", "commit", "-m", msg])
                _run(["git", "push"])
                _log.info(f"[git] pushed {name}")
            except Exception:
                _log.warning(f"[git] failed to push {name}", exc_info=True)

        QTimer.singleShot(0, self._refresh)

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
            painter.drawText(
                QRectF(r.left() + pad, y, r.width() - pad * 2, _ROW_H),
                Qt.AlignLeft | Qt.AlignVCenter,
                "No git repos found on Desktop",
            )
        else:
            dirty   = [(n, s) for n, s in self._repos if s == "dirty"]
            session = [(n, s) for n, s in self._repos if s == "session"]
            clean   = [(n, s) for n, s in self._repos if s == "clean"]

            def _draw_group(group):
                nonlocal y
                for name, status in group:
                    if y + _ROW_H > r.bottom():
                        return
                    if status != "clean":
                        dot_color = QColor("#7ac47a") if status == "session" else QColor("#7a9ac4")
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
            if clean:
                if dirty or session:
                    _draw_sep()
                _draw_group(clean)

        painter.restore()

    def _prepare_for_removal(self) -> None:
        self._poll_timer.stop()
        try:
            self._poll_timer.timeout.disconnect(self._refresh)
        except RuntimeError:
            pass
        self._delivery_timer.stop()
        try:
            self._delivery_timer.timeout.disconnect(self._check_delivery)
        except RuntimeError:
            pass
        super()._prepare_for_removal()

    def to_dict(self) -> dict:
        return self.data.to_dict()

    @staticmethod
    def from_dict(d: dict) -> 'GitNode':
        return GitNode(GitNodeData.from_dict(d))

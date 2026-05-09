#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - nodes/_dialog_helper.py extra-window framework
-Backstage hands for any node that needs a dialog or popup to surface cleanly, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import sys
from contextlib import contextmanager

from PySide6.QtCore import Qt, QEventLoop, QTimer, QAbstractAnimation
from PySide6.QtWidgets import QApplication
from shared_braincell.logger import setup_logger

_log = setup_logger("dialog")


class _DialogChoreographyMixin:
    """Modal-dialog choreography shared by BaseNode, ChromelessRoot, and the
    application main window.

    Lives as a pure-Python mixin so any class that owns or has access to the
    application main window can use it via multiple inheritance:

        class BaseNode(QGraphicsRectItem, _DialogChoreographyMixin): ...
        class ChromelessRoot(QGraphicsRectItem, _DialogChoreographyMixin): ...
        class IntricateApp(QMainWindow, _DialogChoreographyMixin): ...

    Any concrete user — node, root, or main window — can then spawn a
    dialog with the canonical Windows-foreground choreography:

        with self._dialog_choreography() as mw:
            path, _ = QFileDialog.getOpenFileName(mw, "Title", start, filter)
            # use path...

    The mixin locates the application main window via ``_get_main_window()``,
    which subclasses can override. Default walks ``self.scene().views()[0]
    .window()`` (correct for any QGraphicsItem placed on the IntricateScene);
    ``IntricateApp(QMainWindow)`` overrides to return ``self`` directly.
    """

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN WINDOW LOOKUP
    # ─────────────────────────────────────────────────────────────────────────

    def _get_main_window(self):
        """Locate the application main window for dialog parenting + flag flips.

        Default implementation walks ``self.scene().views()[0].window()`` —
        correct for any QGraphicsItem placed on the IntricateScene. Subclasses
        whose ``self`` IS the main window (e.g. ``IntricateApp(QMainWindow)``)
        override to return ``self`` directly, no traversal needed.

        Returns None if no main window can be located (e.g. a node not yet
        added to a scene). Choreography handles the None case gracefully.
        """
        try:
            views = self.scene().views() if self.scene() else []
            return views[0].window() if views else None
        except (AttributeError, RuntimeError):
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # WINDOW FLAG MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────────

    def _drop_topmost(self):
        """Drop always-on-top before opening a dialog so it isn't hidden.

        Pushes the current windowFlags onto an instance-level stack so
        nested ``with self._dialog_choreography():`` calls (any future
        feature that branches dialog flow off another dialog flow on the
        same node / window) restore correctly in LIFO order. A flat
        single-attribute save would have the inner call read the OUTER
        call's already-modified flags and clobber the outer's saved
        state on its own exit — recoverable but confusing. Stack
        bookkeeping closes that door.
        """
        win = self._get_main_window()
        if win is not None:
            if not hasattr(self, '_saved_flags_stack'):
                self._saved_flags_stack = []
            saved = win.windowFlags()
            self._saved_flags_stack.append(saved)
            win.setWindowFlags(saved & ~Qt.WindowStaysOnTopHint)
            win.show()
        return win

    def _restore_topmost(self, win=None) -> None:
        """Restore always-on-top after the dialog closes.

        Pops the most recently saved flags from the stack — see
        ``_drop_topmost`` for the LIFO contract. Empty-stack fallback
        is silent (matches the prior hasattr-guard behaviour for cases
        where ``_drop_topmost`` returned early without a real win).
        """
        stack = getattr(self, '_saved_flags_stack', None)
        if win is not None and stack:
            win.setWindowFlags(stack.pop())
            win.show()
            win.raise_()

    # ─────────────────────────────────────────────────────────────────────────
    # CHOREOGRAPHY
    # ─────────────────────────────────────────────────────────────────────────

    @contextmanager
    def _dialog_choreography(self):
        """Run a modal dialog with Intricate's standard choreography.

        Drops always-on-top, rolls curtains up if currently down, focuses
        the main window so the dialog spawns with a real owner HWND in
        front, then restores curtains and always-on-top on exit. Yields
        the main window (or None if there is no scene/view) so the caller
        can pass it as the dialog's parent — important on Windows so the
        native file picker doesn't drift behind another desktop window.

        Three settle-points are load-bearing for Windows focus reliability:

          1. **Drain pending events immediately after `_drop_topmost()`.**
             `setWindowFlags` inside `_drop_topmost()` recreates the
             native HWND on Windows.  Without an immediate drain, the
             recreation events stack up behind the curtain animation
             and dialog spawn — the dialog ends up parented to a not-
             yet-foregrounded HWND and the OS silently refuses to
             surface it.  On a fresh session this manifests as the
             first-ever file-browser click rolling the curtains up
             but the dialog never appearing; subsequent clicks succeed
             because the HWND is now warm.  Draining here breaks the
             stack-up so the HWND is settled before any further
             choreography begins.
          2. **Curtain animation must finish before yielding.** Without
             waiting, the dialog spawns mid-geometry-transition (the
             curtain roll is ~539 ms).  Windows refuses to promote the
             dialog to foreground while its parent HWND is in animated
             flight, so the dialog opens behind whatever else holds the
             foreground state.  We block on `curtain_anim.finished` via
             a nested QEventLoop with two safeties: the slot is
             connected BEFORE the state inspection (so a fast finish
             between attribute access and state read can't leave us
             listening for an already-emitted signal), and a 1500 ms
             single-shot timer also quits the loop in case `finished`
             is missed entirely (e.g. animation interrupted without
             emitting).  Either path drains the loop cleanly.
          3. **Drain the event queue after activate/raise.**
             `activateWindow()` is a request that may not land until
             pending events drain.  `processEvents()` flushes pending
             events so the activation actually takes effect before the
             dialog spawns.

        Without these settle-points, the focus loss is intermittent —
        sometimes the race resolves favourably, sometimes the dialog
        ends up under another desktop app, and on a fresh session the
        first dialog can fail to surface entirely.

        Usage:
            with self._dialog_choreography() as mw:
                path, _ = QFileDialog.getOpenFileName(mw, "Title", start, filter)
                # use path...
        """
        win = self._drop_topmost()
        # Settle (1): drain HWND-recreation aftermath before further
        # choreography stacks events on top of it.  See docstring above.
        QApplication.processEvents()
        # mw and win are the same here — _drop_topmost already located
        # the main window via _get_main_window. Aliased for readability:
        # `win` reads as "the thing whose flags we restore on exit",
        # `mw` reads as "the parent we hand to the dialog and the curtain
        # owner". Same object, two roles.
        was_collapsed = False
        mw = win
        try:
            if mw is not None and hasattr(mw, 'is_collapsed') and not mw.is_collapsed:
                mw.toggle_curtains()
                was_collapsed = True
                # Settle (2): block until the curtain roll finishes.
                anim = getattr(mw, 'curtain_anim', None)
                if anim is not None:
                    loop = QEventLoop()
                    anim.finished.connect(loop.quit)
                    # Connect-before-state-check closes a race where
                    # the animation could finish between the attribute
                    # access above and the state read below, leaving
                    # us listening for a signal that already fired.
                    if anim.state() == QAbstractAnimation.State.Running:
                        # Safety timeout — see (2) in docstring.  Scales
                        # with the curtain anim duration so a future
                        # speed-up or slow-down keeps the same margin
                        # ratio; floored at 1500 ms so a momentarily
                        # zero-duration anim doesn't collapse the
                        # safety to nothing.
                        safety_ms = max(1500, anim.duration() * 3)
                        QTimer.singleShot(safety_ms, loop.quit)
                        loop.exec()
                    try:
                        anim.finished.disconnect(loop.quit)
                    except (RuntimeError, TypeError):
                        pass
        except Exception:
            _log.debug("[dialog] curtain settle path raised", exc_info=True)
        if mw is not None:
            try:
                mw.activateWindow()
                mw.raise_()
                # Settle (3): drain pending events so the activation
                # actually lands before the dialog spawns.
                QApplication.processEvents()
            except Exception:
                _log.debug("[dialog] activate/raise path raised", exc_info=True)
        # Schedule a post-spawn centring nudge for the modal dialog the
        # caller is about to spawn. The timer fires while the modal
        # dialog is up (Qt's event loop keeps running during a modal
        # exec / getOpenFileName), grabs the foreground HWND, and moves
        # it to centre on the parent's monitor. First call after a fresh
        # boot may show a brief flash at the OS-remembered position
        # before the move; subsequent calls use the now-centred position
        # Windows just remembered, so they spawn centred from the start.
        # PrettyDialog-derived dialogs are already centred via
        # showEvent — this nudge is idempotent in that case.
        if mw is not None:
            try:
                parent_hwnd = int(mw.winId())
                QTimer.singleShot(50, lambda: _center_modal_dialog_on_screen(parent_hwnd))
            except Exception:
                _log.debug("[dialog] failed to schedule centring", exc_info=True)
        try:
            yield mw
        finally:
            if was_collapsed and mw is not None:
                try:
                    mw.toggle_curtains()
                except Exception:
                    _log.debug("[dialog] curtain restore path raised", exc_info=True)
            self._restore_topmost(win)

def _center_modal_dialog_on_screen(parent_hwnd: int, retries: int = 6) -> None:
    """Move the foreground modal dialog to the centre of the parent's monitor.

    Called via QTimer.singleShot from inside ``_dialog_choreography``
    while the user's modal dialog is up. Solves the "native file dialog
    opens at the OS-remembered top-left position on a fresh machine"
    friction by moving the dialog to centre as soon as it spawns;
    Windows then remembers the centred position in its ComDlg32 MRU,
    so subsequent dialogs spawn already centred without any visible
    move at all.

    Platform-gated to Windows where the Win32 ABI gives us the post-
    spawn positioning Qt itself does not. On other platforms this is
    a no-op — native macOS / Linux dialogs handle centring through
    their own OS conventions.

    Multi-monitor honest: ``MonitorFromWindow`` finds the monitor the
    parent main window is currently on, ``GetMonitorInfo`` reads its
    work area (excludes the OS taskbar), and the dialog centres there.

    Polls briefly with ``retries`` if the foreground hasn't switched
    to the dialog yet (slow spawn, machine under load). Each retry
    waits ~30 ms; default 6 retries means up to ~180 ms of pollback
    before giving up — covers the slowest realistic dialog spawn
    without holding the choreography open if no dialog ever appears.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32

        hwnd = user32.GetForegroundWindow()
        if not hwnd or int(hwnd) == int(parent_hwnd):
            # Foreground hasn't switched to the dialog yet. Retry briefly
            # so a slow spawn doesn't lose the centring.
            if retries > 0:
                QTimer.singleShot(
                    30,
                    lambda: _center_modal_dialog_on_screen(parent_hwnd, retries - 1),
                )
            return

        # Read the dialog's current size so we can centre without resizing.
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return
        w = rect.right - rect.left
        h = rect.bottom - rect.top

        # Find the parent's monitor (multi-monitor honest).
        MONITOR_DEFAULTTONEAREST = 2
        hmon = user32.MonitorFromWindow(int(parent_hwnd), MONITOR_DEFAULTTONEAREST)

        class _MONITORINFO(ctypes.Structure):
            _fields_ = [
                ('cbSize',    wintypes.DWORD),
                ('rcMonitor', wintypes.RECT),
                ('rcWork',    wintypes.RECT),
                ('dwFlags',   wintypes.DWORD),
            ]
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return

        sx = mi.rcWork.left
        sy = mi.rcWork.top
        sw = mi.rcWork.right - mi.rcWork.left
        sh = mi.rcWork.bottom - mi.rcWork.top
        x = sx + (sw - w) // 2
        y = sy + (sh - h) // 2

        user32.MoveWindow(hwnd, x, y, w, h, True)
    except Exception:
        _log.debug("[dialog] modal dialog centring failed", exc_info=True)


# The Qt-managed dialog base (PrettyDialog) was promoted to the Pretty
# Widgets package on 2026-05-09 — it's a universal "ceremony popup"
# primitive that other apps in the family can inherit directly. Import
# from `pretty_widgets.PrettyDialog` (or `from pretty_widgets import
# PrettyDialog`). The choreography mixin above stays here because it's
# Intricate-specific (knows about curtains, is_collapsed, etc.).

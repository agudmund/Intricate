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
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QDialog


class _DialogChoreographyMixin:
    """Modal-dialog choreography shared by BaseNode and ChromelessRoot.

    Lives as a pure-Python mixin so the chromeless family doesn't have
    to inherit BaseNode's chrome to get the same dialog behaviour. Both
    base classes pull this in via multiple inheritance:

        class BaseNode(QGraphicsRectItem, _DialogChoreographyMixin): ...
        class ChromelessRoot(QGraphicsRectItem, _DialogChoreographyMixin): ...

    Any concrete node — chromeless or otherwise — can then spawn a file
    or save dialog with the canonical Windows-foreground choreography:

        with self._dialog_choreography() as mw:
            path, _ = QFileDialog.getOpenFileName(mw, "Title", start, filter)
            # use path...

    Assumes ``self.scene()`` returns the IntricateScene whose first view
    is anchored to the application main window — true for every node
    that has been added to the canvas.
    """

    # ─────────────────────────────────────────────────────────────────────────
    # WINDOW FLAG MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────────

    def _lower_window(self):
        """Drop always-on-top before opening a file dialog so it isn't hidden."""
        views = self.scene().views() if self.scene() else []
        win = views[0].window() if views else None
        if win:
            self._saved_flags = win.windowFlags()
            win.setWindowFlags(self._saved_flags & ~Qt.WindowStaysOnTopHint)
            win.show()
        return win

    def _raise_window(self, win=None) -> None:
        """Restore always-on-top after the dialog closes."""
        if win and hasattr(self, '_saved_flags'):
            win.setWindowFlags(self._saved_flags)
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

          1. **Drain pending events immediately after `_lower_window()`.**
             `setWindowFlags` inside `_lower_window()` recreates the
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
        win = self._lower_window()
        # Settle (1): drain HWND-recreation aftermath before further
        # choreography stacks events on top of it.  See docstring above.
        QApplication.processEvents()
        was_collapsed = False
        mw = None
        try:
            views = self.scene().views() if self.scene() else []
            if views:
                mw = views[0].window()
                if hasattr(mw, 'is_collapsed') and not mw.is_collapsed:
                    mw.toggle_curtains()
                    was_collapsed = True
                    # Settle (2): block until the curtain roll finishes.
                    anim = getattr(mw, 'curtain_anim', None)
                    if anim is not None:
                        loop = QEventLoop()
                        anim.finished.connect(loop.quit)
                        # Connect-before-state-check closes a race
                        # where the animation could finish between
                        # the attribute access above and the state
                        # read below, leaving us listening for a
                        # signal that already fired.
                        if anim.state() == QAbstractAnimation.State.Running:
                            # Safety timeout — see (2) in docstring.
                            QTimer.singleShot(1500, loop.quit)
                            loop.exec()
                        try:
                            anim.finished.disconnect(loop.quit)
                        except (RuntimeError, TypeError):
                            pass
        except Exception:
            pass
        if mw is not None:
            try:
                mw.activateWindow()
                mw.raise_()
                # Settle (3): drain pending events so the activation
                # actually lands before the dialog spawns.
                QApplication.processEvents()
            except Exception:
                pass
        try:
            yield mw
        finally:
            if was_collapsed and mw is not None:
                try:
                    mw.toggle_curtains()
                except Exception:
                    pass
            self._raise_window(win)


# ─────────────────────────────────────────────────────────────────────────────
# QT-MANAGED DIALOG BASE
# ─────────────────────────────────────────────────────────────────────────────
# The choreography above handles WHEN an extra window appears (curtain dance,
# HWND settle, focus). The class below handles HOW a Qt-managed extra window
# holds its ground once shown. Native OS dialogs (QFileDialog and friends)
# don't need this — they're owned by the OS shell and defend themselves via
# the OS's own positioning rules. Qt-managed QDialog subclasses sit in the
# same z-order band as Chrome's YouTube PiP and other HWND_TOPMOST citizens
# on Windows, and need active defense to win the band.
#
# The two halves compose: wrap a PrettyDialogBase exec() in
#   `with self._dialog_choreography() as mw:`
# and the dialog gets the curtain-dance + topmost-band defense for free.


class _PrettyDialogBase(QDialog):
    """QDialog base with cross-OS topmost-band defense baked in.

    Inherit this for any Qt-managed dialog spawned from inside Intricate
    so it lands on top of the always-on-top main window, and on Windows
    additionally wins the topmost-band z-order race against Chrome's
    YouTube PiP and other HWND_TOPMOST citizens.

    Subclasses still own their own visual chrome (frameless flag,
    stylesheet, layout, content). The base only owns the show-time
    defense and activate/raise — no visual opinions.
    """

    def showEvent(self, event):
        super().showEvent(event)
        self._center_on_screen()
        self._assert_topmost_if_platform()
        self.activateWindow()
        self.raise_()

    def _center_on_screen(self) -> None:
        """Position the dialog centered on the appropriate screen.

        Overrides Qt's default parent-relative positioning, which can
        land the dialog off-centre when the parent main window is in a
        transient state during the choreography — most notably the
        collapsed-curtain state, where Qt would centre the dialog on
        the small strip at the top of the screen and the dialog would
        land flat against the title bar instead of in the middle of
        the canvas. With explicit centring here, every Qt-managed
        ceremony dialog spawns dead-centre regardless of parent
        geometry quirks.

        Honours multi-monitor setups by preferring the parent's
        screen when available, falling back to the primary screen.
        Uses ``availableGeometry`` so the centred dialog excludes
        the OS taskbar from its calculation.
        """
        screen = None
        parent = self.parent()
        if parent is not None:
            try:
                screen = parent.screen()
            except Exception:
                pass
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geom = screen.availableGeometry()
        self.move(
            geom.x() + (geom.width()  - self.width())  // 2,
            geom.y() + (geom.height() - self.height()) // 2,
        )

    def _assert_topmost_if_platform(self) -> None:
        """OS-aware topmost-band defense hook.

        Windows: re-asserts HWND_TOPMOST via Win32 SetWindowPos so we
        land at the *top* of the topmost band (Chrome PiP also sits in
        that band, and the most recent SetWindowPos wins).

        macOS / Linux: Qt's WindowStaysOnTopHint plus activate/raise is
        sufficient in practice — this method stays as the expansion
        point if a per-OS defense ever proves needed (NSWindow.level on
        macOS, _NET_WM_STATE_ABOVE on X11/Wayland).
        """
        if sys.platform == "win32":
            self._win32_set_topmost()

    def _win32_set_topmost(self) -> None:
        """Re-assert HWND_TOPMOST after Qt finishes showing the dialog."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            HWND_TOPMOST   = ctypes.c_void_p(-1)
            SWP_NOSIZE     = 0x0001
            SWP_NOMOVE     = 0x0002
            SWP_SHOWWINDOW = 0x0040
            user32.SetWindowPos(
                ctypes.c_void_p(int(self.winId())),
                HWND_TOPMOST,
                0, 0, 0, 0,
                SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW,
            )
        except Exception:
            pass

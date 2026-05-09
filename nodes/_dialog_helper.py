#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - nodes/_dialog_helper.py dialog choreography mixin
-A small backstage hand for any node that needs a dialog to surface cleanly, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from contextlib import contextmanager

from PySide6.QtCore import Qt, QEventLoop, QTimer, QAbstractAnimation
from PySide6.QtWidgets import QApplication


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

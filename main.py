#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - main.py application launcher
-Launches the Intricate node-based UI application for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import sys
from PySide6.QtWidgets import QApplication
from main_window import IntricateApp
import utils.settings as settings
from graphics.Theme import Theme

APP_NAME = "Intricate"
ORG_NAME = "Single Shared Braincell"

def main():
    print(f"{APP_NAME} is generally so happy that you are here. ✨")

    app = QApplication(sys.argv)

    # ── Settings and Theme bootstrap ──────────────────────────────────────────
    # settings._reload() already ran at import time above, so Theme.reload()
    # here pulls the initial TOML values into Theme before any UI is created.
    Theme.reload()

    # File watcher — must be created after QApplication exists.
    # Connects the TOML file change signal to Theme.reload so any write
    # from The Settlers (or anyone else) ripples through immediately.
    _watcher = settings.init_watcher()
    _watcher.changed.connect(Theme.reload)
    _watcher.changed.connect(lambda: app.activeWindow() and app.activeWindow().update())

    window = IntricateApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

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

APP_NAME = "Intricate"
ORG_NAME = "Single Shared Braincell"

def main():
    print(f"{APP_NAME} is generally so happy that you are here. ✨")
    app = QApplication(sys.argv)
    window = IntricateApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

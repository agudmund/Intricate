#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - main.py application launcher for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import sys
from PySide6.QtWidgets import QApplication
from main_window import IntricateApp


def main():
    app = QApplication(sys.argv)
    window = IntricateApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

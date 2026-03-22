#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - main_window.py main application window
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QPushButton
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt


class IntricateApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Intricate")
        self.setMinimumSize(400, 300)

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setAlignment(Qt.AlignCenter)

        btn = QPushButton("yay!")
        btn.setFont(QFont("Chandler42", 22))
        btn.setFixedSize(160, 70)

        layout.addWidget(btn)

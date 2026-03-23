#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - widgets/demo_dialog.py
-A simple demo dialog using PrettyDialog for demonstration/testing.
"""

from PySide6.QtWidgets import QLabel, QVBoxLayout
from widgets.pretty_dialog import PrettyDialog

class DemoDialog(PrettyDialog):
    def __init__(self, parent=None):
        super().__init__(parent, title="Demo Dialog")
        layout = QVBoxLayout()
        layout.addWidget(QLabel("This is a demo of PrettyDialog!", self))
        self.central.setLayout(layout)

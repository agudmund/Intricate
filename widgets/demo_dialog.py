#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - widgets/demo_dialog.py DemoDialog dialog widget
-A simple demo dialog using PrettyDialog for demonstration/testing for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QLabel, QVBoxLayout
from widgets.pretty_dialog import PrettyDialog

class DemoDialog(PrettyDialog):
    def __init__(self, parent=None):
        super().__init__(parent, title="Demo Dialog")
        layout = QVBoxLayout()
        layout.addWidget(QLabel("This is a demo of PrettyDialog!", self))
        self.central.setLayout(layout)

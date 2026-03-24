#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - widgets/settings_dialog.py SettingsDialog dialog widget
-SettingsDialog: settings with General and Theme tabs, icon path selectors, TOML-backed for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog
from PySide6.QtCore import Qt
from graphics.Theme import Theme
import utils.settings as settings
from pathlib import Path
from graphics.PrettyButton import button
from widgets.pretty_dialog import PrettyDialog


        # btns = QHBoxLayout()
        # save_btn = button("Exid", clicked=self.save)  # Again, Note : Exid is not a typo, its an exit button named Exid
        # btns.addStretch()
        # btns.addWidget(save_btn)
        # self.layout.addLayout(btns)

        # the stylesheet defaults are not being inherited from the Prettybutton, for now set them per window
        # self.setStyleSheet(f"background: #282828; border: {Theme.windowBorderWidth}px solid {Theme.primaryBorder}; border-radius: 10px;")


    def save(self):
        """the settings window is currently undergoing migration from QSettings to TOML"""
        # Write icon paths to settings.toml
        # for attr, field in self.icon_fields.items():
            # settings.set_value("theme", attr, field.text())
            # Theme._icon_cache.pop(getattr(Theme, attr), None)
        self.accept()

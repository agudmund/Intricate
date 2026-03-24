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

class SettingsDialog(PrettyDialog):
    def __init__(self, parent=None):
        super().__init__(parent, title="The Unnecciarily Nitpicky but Incredibly Beautiful Settings Window 🌱")
        
        self.setMinimumWidth(500)
        self.setMinimumHeight(600)

        # Create your tabs
        self.tabs = QTabWidget()
        
        # Add the tabs to the content layout from the template
        self.content_layout.addWidget(self.tabs)
        
        self._setup_tabs()

    def _setup_tabs(self):
        self._setup_general_tab()
        self._setup_theme_tab()

    def _setup_general_tab(self):
        """General Ui Settings"""
        general_tab = QWidget()
        gen_layout = QVBoxLayout(general_tab)
        gen_layout.addWidget(QLabel("Coming soon, Future!"))
        gen_layout.addStretch()
        self.tabs.addTab(general_tab, "General")

    def _setup_theme_tab(self):
        """Theme Settings"""
        theme_tab = QWidget()
        theme_layout = QVBoxLayout(theme_tab)
        theme_layout.addWidget(QLabel("General Theme Settings"))

        icon_fields = {}
        for attr in dir(Theme):
            if attr.startswith("icon") and isinstance(getattr(Theme, attr), str):
                path = getattr(Theme, attr)
                row = QHBoxLayout()
                label = QLabel(attr, theme_tab)
                field = QLineEdit(path, theme_tab)
                browse = QPushButton("Browse", theme_tab)
                browse.clicked.connect(lambda _, a=attr, f=field: self._browse_icon(a, f))
                row.addWidget(label)
                row.addWidget(field)
                row.addWidget(browse)
                theme_layout.addLayout(row)
                icon_fields[attr] = field

        theme_layout.addStretch()
        self.tabs.addTab(theme_tab, "Theme")

    def _browse_icon(self, attr, field):
        file, _ = QFileDialog.getOpenFileName(self, "Select Icon", str(Path(field.text()).parent), "Images (*.png *.jpg *.bmp)")
        if file:
            field.setText(file)
            # Clear icon cache for this filename
            Theme._icon_cache.pop(getattr(Theme, attr), None)
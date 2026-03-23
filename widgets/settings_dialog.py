#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - widgets/settings_dialog.py
-SettingsDialog: settings with General and Theme tabs, icon path selectors, TOML-backed.
"""

from PySide6.QtWidgets import QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog
from PySide6.QtCore import Qt
from graphics.Theme import Theme
import utils.settings as settings
from pathlib import Path

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.tabs = QTabWidget(self)
        self._setup_tabs()
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        btns = QHBoxLayout()
        save_btn = QPushButton("Save", self)
        save_btn.clicked.connect(self.save)
        btns.addStretch()
        btns.addWidget(save_btn)
        layout.addLayout(btns)

    def _setup_tabs(self):
        self.general_tab = QWidget()
        self.theme_tab = QWidget()
        self.tabs.addTab(self.general_tab, "General")
        self.tabs.addTab(self.theme_tab, "Theme")
        self._setup_general_tab()
        self._setup_theme_tab()

    def _setup_general_tab(self):
        layout = QVBoxLayout(self.general_tab)
        layout.addWidget(QLabel("(Future settings go here)", self.general_tab))
        layout.addStretch()

    def _setup_theme_tab(self):
        layout = QVBoxLayout(self.theme_tab)
        self.icon_fields = {}
        for attr in dir(Theme):
            if attr.startswith("icon") and isinstance(getattr(Theme, attr), str):
                path = getattr(Theme, attr)
                row = QHBoxLayout()
                label = QLabel(attr, self.theme_tab)
                field = QLineEdit(path, self.theme_tab)
                browse = QPushButton("Browse", self.theme_tab)
                browse.clicked.connect(lambda _, a=attr, f=field: self._browse_icon(a, f))
                row.addWidget(label)
                row.addWidget(field)
                row.addWidget(browse)
                layout.addLayout(row)
                self.icon_fields[attr] = field
        layout.addStretch()

    def _browse_icon(self, attr, field):
        file, _ = QFileDialog.getOpenFileName(self, "Select Icon", str(Path(field.text()).parent), "Images (*.png *.jpg *.bmp)")
        if file:
            field.setText(file)
            # Clear icon cache for this filename
            Theme._icon_cache.pop(getattr(Theme, attr), None)

    def save(self):
        # Write icon paths to settings.toml
        for attr, field in self.icon_fields.items():
            settings.set_value("theme", attr, field.text())
            Theme._icon_cache.pop(getattr(Theme, attr), None)
        self.accept()

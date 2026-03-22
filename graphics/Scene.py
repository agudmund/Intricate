#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - graphics/Scene.py
-The infinite canvas. Holds items, manages the world, owns the purge contract.
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtWidgets import QGraphicsScene
from PySide6.QtCore import Qt


class IntricateScene(QGraphicsScene):
    """
    The world.

    Responsibilities:
        - Owns the scene rect (the navigable infinite space)
        - Will own the purge contract when sessions arrive
        - Will own node registration when nodes arrive

    Deliberately empty of features for now. The foundation is the feature.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # The navigable space — large enough to feel infinite, not actually infinite
        # so Qt's BSP tree stays performant
        self.setSceneRect(-5000, -5000, 10000, 10000)

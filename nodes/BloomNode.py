#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/BloomNode.py BloomNode class
-Particle scatter controller that blooms the canvas with PNG confetti for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtWidgets import QComboBox, QSpinBox, QGraphicsProxyWidget

from nodes.BaseNode import BaseNode
from data.BloomNodeData import BloomNodeData
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.utils.logger import setup_logger

_log = setup_logger("bloom")

_PAD = 10.0


class BloomNode(BaseNode):
    """
    Particle scatter controller.

    Choose a scatter algorithm (Sunflower / Orbital) via the combobox,
    optionally connect an ImageNode as the icon source, then press the
    bloom button to scatter particles across the canvas.
    """
    _has_depth_toggle = True

    def __init__(self, data: BloomNodeData | None = None):
        if data is None:
            data = BloomNodeData()
        super().__init__(data)

        self.setBrush(self._bg_color())
        self._apply_depth()

        # ── Scatter mode combobox ─────────────────────────────────────────
        self._combo = QComboBox()
        self._combo.addItems(["Sunflower", "Orbital"])
        self._combo.setCurrentIndex(0 if data.scatter_mode == "sprinkle" else 1)
        self._combo.currentIndexChanged.connect(self._on_mode_changed)
        self._combo.setStyleSheet(f"""
            QComboBox {{
                background: {Theme.backDrop};
                color: {Theme.textPrimary};
                border: 1px solid {Theme.primaryBorder};
                border-radius: 4px;
                padding: 3px 8px;
                font-family: '{Theme.healthFontFamily}';
                font-size: {Theme.healthFontSizeLabel}pt;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 18px;
            }}
            QComboBox QAbstractItemView {{
                background: {Theme.windowBg};
                color: {Theme.textPrimary};
                border: 1px solid {Theme.primaryBorder};
                selection-background-color: {Theme.primaryBorder};
            }}
        """)

        self._combo_proxy = QGraphicsProxyWidget(self)
        self._combo_proxy.setWidget(self._combo)

        # ── Particle count spinbox ────────────────────────────────────────
        self._spin = QSpinBox()
        self._spin.setRange(100, 999999)
        self._spin.setSingleStep(500)
        self._spin.setValue(data.particle_count)
        self._spin.setSuffix("  particles")
        self._spin.valueChanged.connect(self._on_count_changed)
        self._spin.setStyleSheet(f"""
            QSpinBox {{
                background: {Theme.backDrop};
                color: {Theme.textPrimary};
                border: 1px solid {Theme.primaryBorder};
                border-radius: 4px;
                padding: 3px 8px;
                font-family: '{Theme.healthFontFamily}';
                font-size: {Theme.healthFontSizeLabel}pt;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 16px;
                border: none;
            }}
        """)

        self._spin_proxy = QGraphicsProxyWidget(self)
        self._spin_proxy.setWidget(self._spin)
        self._position_widgets()

    # ─────────────────────────────────────────────────────────────────────────

    def _bg_color(self) -> QColor:
        tint = getattr(self.data, 'node_tint', '')
        c = QColor(tint) if tint and QColor(tint).isValid() else QColor(
            Theme.aboutBgColorFront if self.data.depth_front else Theme.aboutBgColor
        )
        c.setAlpha(Theme.aboutBgAlpha)
        return c

    def _apply_depth(self) -> None:
        super()._apply_depth()
        self.setBrush(self._bg_color())

    # ─────────────────────────────────────────────────────────────────────────
    # LAYOUT
    # ─────────────────────────────────────────────────────────────────────────

    def _combo_rect(self) -> QRectF:
        r = self.rect()
        return QRectF(
            r.left() + _PAD,
            r.top() + self._BUTTON_ZONE_H + 8,
            r.width() - _PAD * 2,
            28,
        )

    def _spin_rect(self) -> QRectF:
        r = self.rect()
        return QRectF(
            r.left() + _PAD,
            r.top() + self._BUTTON_ZONE_H + 42,
            r.width() - _PAD * 2,
            28,
        )

    def _position_widgets(self) -> None:
        self._combo_proxy.setGeometry(self._combo_rect())
        self._spin_proxy.setGeometry(self._spin_rect())

    def setRect(self, rect) -> None:
        super().setRect(rect)
        if hasattr(self, '_combo_proxy') and self._combo_proxy:
            self._position_widgets()

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        super()._build_buttons()
        from nodes.NodeButton import NodeButton

        bloom_pix = Theme.icon(Theme.iconBloom, fallback_color="#d87a9e")
        bloom_btn = NodeButton(self, bloom_pix, self._fire_scatter)
        bloom_btn.setToolTip("Bloom — scatter particles")
        self._buttons.append(bloom_btn)

    # ─────────────────────────────────────────────────────────────────────────
    # SCATTER
    # ─────────────────────────────────────────────────────────────────────────

    def _on_mode_changed(self, index: int) -> None:
        self.data.scatter_mode = "sprinkle" if index == 0 else "orbital"

    def _on_count_changed(self, value: int) -> None:
        self.data.particle_count = value
        self.update()  # refresh the info label

    def _get_input_image_name(self) -> str | None:
        """Read the connected ImageNode's source filename for the icon cache."""
        from nodes.ImageNode import ImageNode
        for conn in self.connections:
            other = conn.end_node if conn.start_node is self else conn.start_node
            if other and isinstance(other, ImageNode):
                sp = getattr(other.data, 'source_path', '')
                if sp:
                    return Path(sp).name
        return None

    def _fire_scatter(self) -> None:
        """Trigger a particle scatter at this node's center."""
        scene = self.scene()
        if not scene:
            return
        center = self.mapToScene(self.rect().center())
        icon_name = self._get_input_image_name()
        count = self.data.particle_count

        from graphics.Particles import sprinkle, orbital_burst
        if self.data.scatter_mode == "orbital":
            orbital_burst(scene, center, count=count, icon_name=icon_name)
        else:
            sprinkle(scene, center, count=count, icon_name=icon_name)

        _log.info(f"[Bloom] fired {self.data.scatter_mode} ×{count}"
                  f"{f' icon={icon_name}' if icon_name else ''}")

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        painter.save()
        r = self.rect()
        pad = self._CONTENT_PAD
        top = self._content_top()

        # Title
        title_font = QFont(self._TITLE_FONT, max(1, Theme.aboutFontSize + self._TITLE_FONT_BUMP))
        title_font.setStyleName(self._TITLE_STYLE)
        painter.setFont(title_font)
        painter.setPen(QColor("#d87a9e"))
        painter.drawText(
            QRectF(r.left() + pad, r.top() + top, r.width() - pad * 2, self._TITLE_HEIGHT),
            Qt.AlignLeft | Qt.AlignTop,
            "Bloom",
        )

        # Info label below spinbox
        info_y = self._spin_rect().bottom() + 8
        body_font = QFont(self._BODY_FONT, max(1, Theme.aboutFontSize + self._BODY_FONT_BUMP))
        painter.setFont(body_font)
        painter.setPen(QColor(Theme.nodeFontColor))
        painter.setOpacity(0.6)

        icon_name = self._get_input_image_name()
        info = f"×{self.data.particle_count}"
        if icon_name:
            info += f"  ·  {icon_name}"
        else:
            info += "  ·  heart.png"

        painter.drawText(
            QRectF(r.left() + pad, info_y, r.width() - pad * 2, 20),
            Qt.AlignLeft | Qt.AlignVCenter,
            info,
        )
        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        try:
            self._combo.currentIndexChanged.disconnect(self._on_mode_changed)
        except RuntimeError:
            pass
        try:
            self._spin.valueChanged.disconnect(self._on_count_changed)
        except RuntimeError:
            pass
        if self._combo_proxy:
            self._combo_proxy.setWidget(None)
            self._combo_proxy = None
        if self._spin_proxy:
            self._spin_proxy.setWidget(None)
            self._spin_proxy = None
        self._combo = None
        self._spin = None
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def sync_data(self) -> None:
        super().sync_data()
        if self._combo:
            self.data.scatter_mode = "sprinkle" if self._combo.currentIndex() == 0 else "orbital"
        if self._spin:
            self.data.particle_count = self._spin.value()

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'BloomNode':
        return BloomNode(BloomNodeData.from_dict(data))

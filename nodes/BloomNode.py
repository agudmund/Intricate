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
from PySide6.QtWidgets import QComboBox, QSpinBox, QGraphicsProxyWidget, QSlider

from nodes.BaseNode import BaseNode
from data.BloomNodeData import BloomNodeData
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.utils.logger import setup_logger

_log = setup_logger("bloom")

_PAD = 10.0
_ROW_H = 34    # vertical spacing per widget row


def _widget_css() -> str:
    """Shared stylesheet for embedded controls."""
    return f"""
        QComboBox, QSpinBox {{
            background: {Theme.backDrop};
            color: {Theme.textPrimary};
            border: 1px solid {Theme.primaryBorder};
            border-radius: 4px;
            padding: 3px 8px;
            font-family: '{Theme.healthFontFamily}';
            font-size: {Theme.healthFontSizeLabel}pt;
        }}
        QComboBox::drop-down {{ border: none; width: 18px; }}
        QComboBox QAbstractItemView {{
            background: {Theme.windowBg};
            color: {Theme.textPrimary};
            border: 1px solid {Theme.primaryBorder};
            selection-background-color: {Theme.primaryBorder};
        }}
        QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; border: none; }}
    """


class BloomNode(BaseNode):
    """
    Particle scatter controller — Houdini-inspired.

    Parameters:
        Algorithm   — Sunflower (golden-angle spiral) or Orbital (torus knot)
        Count       — number of particles (uncapped)
        Seed        — reproducible scatter randomisation
        Density     — Uniform / Center-heavy / Edge-heavy radial distribution
        Stiffness   — orbital convergence rate (lerp_rate, 0.01 = floaty, 1.0 = snappy)

    Connect an ImageNode as the icon source, then press the bloom button.
    """
    _has_depth_toggle = True

    def __init__(self, data: BloomNodeData | None = None):
        if data is None:
            data = BloomNodeData()
        super().__init__(data)

        self.setBrush(self._bg_color())
        self._apply_depth()

        css = _widget_css()

        # ── Row 1: scatter algorithm ──────────────────────────────────────
        self._combo = QComboBox()
        self._combo.addItems(["Sunflower", "Orbital"])
        self._combo.setCurrentIndex(0 if data.scatter_mode == "sprinkle" else 1)
        self._combo.currentIndexChanged.connect(self._on_mode_changed)
        self._combo.setStyleSheet(css)
        self._combo_proxy = QGraphicsProxyWidget(self)
        self._combo_proxy.setWidget(self._combo)

        # ── Row 2: particle count ─────────────────────────────────────────
        self._count_spin = QSpinBox()
        self._count_spin.setRange(100, 999999)
        self._count_spin.setSingleStep(500)
        self._count_spin.setValue(data.particle_count)
        self._count_spin.setSuffix("  particles")
        self._count_spin.valueChanged.connect(self._on_count_changed)
        self._count_spin.setStyleSheet(css)
        self._count_proxy = QGraphicsProxyWidget(self)
        self._count_proxy.setWidget(self._count_spin)

        # ── Row 3: seed ───────────────────────────────────────────────────
        self._seed_spin = QSpinBox()
        self._seed_spin.setRange(0, 999999)
        self._seed_spin.setSingleStep(1)
        self._seed_spin.setValue(data.seed)
        self._seed_spin.setPrefix("seed  ")
        self._seed_spin.valueChanged.connect(self._on_seed_changed)
        self._seed_spin.setStyleSheet(css)
        self._seed_proxy = QGraphicsProxyWidget(self)
        self._seed_proxy.setWidget(self._seed_spin)

        # ── Row 4: density falloff ────────────────────────────────────────
        self._density_combo = QComboBox()
        self._density_combo.addItems(["Uniform", "Center Heavy", "Edge Heavy"])
        _density_idx = {"uniform": 0, "center": 1, "edge": 2}.get(data.density_falloff, 0)
        self._density_combo.setCurrentIndex(_density_idx)
        self._density_combo.currentIndexChanged.connect(self._on_density_changed)
        self._density_combo.setStyleSheet(css)
        self._density_proxy = QGraphicsProxyWidget(self)
        self._density_proxy.setWidget(self._density_combo)

        # ── Row 5: stiffness slider (orbital lerp_rate) ───────────────────
        self._stiffness_slider = QSlider(Qt.Horizontal)
        self._stiffness_slider.setRange(1, 100)   # maps to 0.01–1.0
        self._stiffness_slider.setValue(int(data.stiffness * 100))
        self._stiffness_slider.valueChanged.connect(self._on_stiffness_changed)
        self._stiffness_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {Theme.backDrop};
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {Theme.primaryBorder};
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }}
        """)
        self._stiffness_proxy = QGraphicsProxyWidget(self)
        self._stiffness_proxy.setWidget(self._stiffness_slider)

        slider_css = self._stiffness_slider.styleSheet()

        # ── Row 6: speed slider (orbital flow speed) ──────────────────────
        self._speed_slider = QSlider(Qt.Horizontal)
        self._speed_slider.setRange(1, 300)    # maps to 0.01–3.0
        self._speed_slider.setValue(int(data.speed * 100))
        self._speed_slider.valueChanged.connect(self._on_speed_changed)
        self._speed_slider.setStyleSheet(slider_css)
        self._speed_proxy = QGraphicsProxyWidget(self)
        self._speed_proxy.setWidget(self._speed_slider)

        # ── Row 7: distance slider (scatter radius) ──────────────────────
        self._distance_slider = QSlider(Qt.Horizontal)
        self._distance_slider.setRange(50, 3000)   # scene pixels
        self._distance_slider.setValue(int(data.distance))
        self._distance_slider.valueChanged.connect(self._on_distance_changed)
        self._distance_slider.setStyleSheet(slider_css)
        self._distance_proxy = QGraphicsProxyWidget(self)
        self._distance_proxy.setWidget(self._distance_slider)

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

    def _row_rect(self, row: int) -> QRectF:
        r = self.rect()
        return QRectF(
            r.left() + _PAD,
            r.top() + self._BUTTON_ZONE_H + 8 + row * _ROW_H,
            r.width() - _PAD * 2,
            28,
        )

    def _position_widgets(self) -> None:
        self._combo_proxy.setGeometry(self._row_rect(0))
        self._count_proxy.setGeometry(self._row_rect(1))
        self._seed_proxy.setGeometry(self._row_rect(2))
        self._density_proxy.setGeometry(self._row_rect(3))
        self._stiffness_proxy.setGeometry(self._row_rect(4))
        self._speed_proxy.setGeometry(self._row_rect(5))
        self._distance_proxy.setGeometry(self._row_rect(6))

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
    # PARAMETER CALLBACKS
    # ─────────────────────────────────────────────────────────────────────────

    def _on_mode_changed(self, index: int) -> None:
        self.data.scatter_mode = "sprinkle" if index == 0 else "orbital"

    def _on_count_changed(self, value: int) -> None:
        self.data.particle_count = value
        self.update()

    def _on_seed_changed(self, value: int) -> None:
        self.data.seed = value

    def _on_density_changed(self, index: int) -> None:
        self.data.density_falloff = ["uniform", "center", "edge"][index]

    def _on_stiffness_changed(self, value: int) -> None:
        self.data.stiffness = value / 100.0
        self.update()

    def _on_speed_changed(self, value: int) -> None:
        self.data.speed = value / 100.0
        self.update()

    def _on_distance_changed(self, value: int) -> None:
        self.data.distance = float(value)
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # SCATTER
    # ─────────────────────────────────────────────────────────────────────────

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

    def _get_scatter_origin(self):
        """Read position from a connected NullNode, or fall back to own center."""
        from nodes.NullNode import NullNode
        for conn in self.connections:
            other = conn.end_node if conn.start_node is self else conn.start_node
            if other and isinstance(other, NullNode):
                return other.mapToScene(other.rect().center())
        return self.mapToScene(self.rect().center())

    def _fire_scatter(self) -> None:
        """Trigger a particle scatter at the scatter origin."""
        scene = self.scene()
        if not scene:
            return
        center = self._get_scatter_origin()
        icon_name = self._get_input_image_name()
        count = self.data.particle_count

        from graphics.Particles import sprinkle, orbital_burst
        if self.data.scatter_mode == "orbital":
            orbital_burst(scene, center, count=count, icon_name=icon_name,
                          stiffness=self.data.stiffness,
                          speed=self.data.speed,
                          distance=self.data.distance)
        else:
            sprinkle(scene, center, count=count, icon_name=icon_name,
                     seed=self.data.seed,
                     density_falloff=self.data.density_falloff,
                     distance=self.data.distance)

        _log.info(f"[Bloom] fired {self.data.scatter_mode} ×{count}"
                  f" seed={self.data.seed} density={self.data.density_falloff}"
                  f" stiffness={self.data.stiffness:.2f}"
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

        # Slider labels
        body_font = QFont(self._BODY_FONT, max(1, Theme.aboutFontSize + self._BODY_FONT_BUMP))
        painter.setFont(body_font)
        painter.setPen(QColor(Theme.nodeFontColor))
        painter.setOpacity(0.5)

        for row, label in [
            (4, f"stiffness  {self.data.stiffness:.2f}"),
            (5, f"speed  {self.data.speed:.2f}"),
            (6, f"distance  {self.data.distance:.0f}px"),
        ]:
            ly = self._row_rect(row).top() - 14
            painter.drawText(
                QRectF(r.left() + pad, ly, r.width() - pad * 2, 14),
                Qt.AlignLeft | Qt.AlignVCenter,
                label,
            )

        # Info line at bottom
        info_y = self._row_rect(6).bottom() + 6
        icon_name = self._get_input_image_name()
        info = icon_name if icon_name else "heart.png"
        painter.drawText(
            QRectF(r.left() + pad, info_y, r.width() - pad * 2, 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"icon  ·  {info}",
        )
        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        for signal, slot in [
            (self._combo.currentIndexChanged,        self._on_mode_changed),
            (self._count_spin.valueChanged,          self._on_count_changed),
            (self._seed_spin.valueChanged,           self._on_seed_changed),
            (self._density_combo.currentIndexChanged, self._on_density_changed),
            (self._stiffness_slider.valueChanged,    self._on_stiffness_changed),
            (self._speed_slider.valueChanged,        self._on_speed_changed),
            (self._distance_slider.valueChanged,     self._on_distance_changed),
        ]:
            try:
                signal.disconnect(slot)
            except RuntimeError:
                pass
        for proxy in (self._combo_proxy, self._count_proxy, self._seed_proxy,
                      self._density_proxy, self._stiffness_proxy,
                      self._speed_proxy, self._distance_proxy):
            if proxy:
                proxy.setWidget(None)
        self._combo_proxy = self._count_proxy = self._seed_proxy = None
        self._density_proxy = self._stiffness_proxy = None
        self._speed_proxy = self._distance_proxy = None
        self._combo = self._count_spin = self._seed_spin = None
        self._density_combo = self._stiffness_slider = None
        self._speed_slider = self._distance_slider = None
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def sync_data(self) -> None:
        super().sync_data()
        if self._combo:
            self.data.scatter_mode = "sprinkle" if self._combo.currentIndex() == 0 else "orbital"
        if self._count_spin:
            self.data.particle_count = self._count_spin.value()
        if self._seed_spin:
            self.data.seed = self._seed_spin.value()
        if self._density_combo:
            self.data.density_falloff = ["uniform", "center", "edge"][self._density_combo.currentIndex()]
        if self._stiffness_slider:
            self.data.stiffness = self._stiffness_slider.value() / 100.0
        if self._speed_slider:
            self.data.speed = self._speed_slider.value() / 100.0
        if self._distance_slider:
            self.data.distance = float(self._distance_slider.value())

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'BloomNode':
        return BloomNode(BloomNodeData.from_dict(data))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/PaletteNode.py PaletteNode class
-A swatch board: collect hex values and see their colors side by side for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import json as _json
import random as _random
from pathlib import Path

from PySide6.QtWidgets import (
    QGraphicsProxyWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QPushButton, QScrollArea, QLabel,
)
from pretty_widgets.PrettyMenu import StyledLineEdit as QLineEdit
from PySide6.QtCore import Qt, QRectF, QMimeData, QPoint, QByteArray, QEvent
from PySide6.QtGui import QPainter, QColor, QDrag, QPixmap

from nodes.BaseNode import BaseNode
from data.PaletteNodeData import PaletteNodeData
from pretty_widgets.graphics.Theme import Theme


PADDING      = 6.0
TITLE_GAP    = 4.0
SWATCH_W     = 110
SWATCH_H     = 70
CELL_SPACING = 10
COLUMNS      = 2
_MIME_TYPE   = "application/x-intricate-palette-color"


# ─────────────────────────────────────────────────────────────────────────────
# SWATCH CELL  — one color entry: label, swatch box, hex value
# ─────────────────────────────────────────────────────────────────────────────

class _SwatchCell(QWidget):
    """
    Single palette entry.

    Layout (top to bottom):
        editable label   — human description ("Background", "Border" …)
        color swatch     — large outlined rectangle
        editable hex     — color value ("#363646")
    """

    def __init__(self, label: str, hex_color: str, on_change, on_remove):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        # ── Label ─────────────────────────────────────────────────────────────
        self._label = QLineEdit(label)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet(f"""
            QLineEdit {{
                background:  transparent;
                color:       {Theme.textPrimary};
                border:      none;
                font-family: 'Chandler42';
                font-weight: 500;
                font-style:  italic;
                font-size:   8pt;
                padding:     0;
            }}
        """)
        layout.addWidget(self._label)

        # ── Swatch ────────────────────────────────────────────────────────────
        self._swatch = QFrame()
        self._swatch.setFixedSize(SWATCH_W, SWATCH_H)
        self._update_swatch(hex_color)
        layout.addWidget(self._swatch, 0, Qt.AlignHCenter)

        # ── Hex input ─────────────────────────────────────────────────────────
        self._hex = QLineEdit(hex_color)
        self._hex.setAlignment(Qt.AlignRight)
        self._hex.setMaxLength(9)
        self._hex.setStyleSheet(f"""
            QLineEdit {{
                background:  transparent;
                color:       {Theme.textPrimary};
                border:      none;
                font-family: 'Chandler42';
                font-weight: 500;
                font-style:  italic;
                font-size:   8pt;
                padding:     0;
            }}
        """)
        layout.addWidget(self._hex)

        # ── Remove button (subtle, top-right) ────────────────────────────────
        self._rm_btn = QPushButton("×")
        self._rm_btn.setFixedSize(16, 16)
        self._rm_btn.setCursor(Qt.PointingHandCursor)
        self._rm_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color:      {Theme.primaryBorder};
                border:     none;
                font-size:  10pt;
                padding:    0;
            }}
            QPushButton:hover {{ color: {Theme.nodeBorderSelected}; }}
        """)
        self._rm_btn.setParent(self)
        self._rm_btn.move(self.width() - 18, 2)
        self._rm_btn.clicked.connect(lambda: on_remove(self))
        self._rm_btn.hide()

        # ── Signals ───────────────────────────────────────────────────────────
        self._hex.textChanged.connect(self._on_hex_changed)
        self._hex.textChanged.connect(lambda _: on_change())
        self._label.textChanged.connect(lambda _: on_change())

    # ── Drag support — two gestures, modifier-disambiguated ────────────────
    #
    # Plain drag (no modifier) on the swatch → HSL-lightness shift, live.
    # Same gentle touch the Settlers config uses on its theme swatches: up
    # to lighten, down to darken.  No threshold; small motions land small
    # adjustments.  Hex field cascades through textChanged so the data
    # model and visible #hex update together.
    #
    # Ctrl+drag past 15 px → cross-palette QDrag (the classic move-or-
    # duplicate gesture).  Drop on the same palette duplicates (CopyAction);
    # drop on a different palette moves (MoveAction).  Modifier state is
    # latched at press time — releasing Ctrl mid-drag doesn't switch modes.
    #
    # Earlier rev tried to disambiguate by motion direction (vertical =
    # lightness, horizontal past 15 px = QDrag).  Worked in principle but
    # leaked: a vertical lightness drag with any horizontal drift could
    # accidentally arm the QDrag once it crossed 15 px Manhattan distance.
    # Ctrl as the explicit gate is unambiguous and matches the platform
    # convention for "this drag is special."

    _PX_PER_LIGHTNESS_UNIT = 1.5  # Settlers value — ~100 px covers two-thirds of HSL range

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._swatch.geometry().contains(event.pos()):
            self._drag_start = event.pos()
            self._drag_base_color = QColor(self._hex.text())
            if not self._drag_base_color.isValid():
                self._drag_base_color = QColor("#888888")
            self._ctrl_drag_active = bool(event.modifiers() & Qt.ControlModifier)
            event.accept()
            return
        self._drag_start = None
        self._ctrl_drag_active = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start is None or not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
        delta = event.pos() - self._drag_start
        if self._ctrl_drag_active:
            # Ctrl held at press → cross-palette QDrag mode.  Wait until we
            # cross the Qt-conventional 15-px threshold before initiating
            # so a stationary Ctrl+click doesn't fire a degenerate drag.
            if delta.manhattanLength() > 15:
                self._initiate_drag()
                self._drag_start = None
            return
        # Plain drag → vertical-axis lightness shift, live.
        self._apply_lightness_shift(delta.y())
        event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_start = None
        self._ctrl_drag_active = False
        super().mouseReleaseEvent(event)

    def _apply_lightness_shift(self, dy: float) -> None:
        """Up = lighter, down = darker.  Same HSL math the Settlers swatches use."""
        delta = int(-dy / self._PX_PER_LIGHTNESS_UNIT)
        h, s, _, _ = self._drag_base_color.getHsl()
        base_l = self._drag_base_color.lightness()
        new_l  = max(0, min(255, base_l + delta))
        if h < 0:        # grey: hue is -1, restore to 0 so QColor doesn't reset to red
            h = 0
        new_color = QColor()
        new_color.setHsl(h, s, new_l, self._drag_base_color.alpha())
        new_hex = "#{:02X}{:02X}{:02X}".format(
            new_color.red(), new_color.green(), new_color.blue(),
        )
        # setText cascades into _on_hex_changed (validates + repaints swatch)
        # and the on_change lambda (propagates colours up to PaletteNode.data).
        self._hex.setText(new_hex)

    def _initiate_drag(self) -> None:
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(_MIME_TYPE, QByteArray(_json.dumps(self.get_data()).encode()))
        drag.setMimeData(mime)

        # Render swatch as drag pixmap
        pix = QPixmap(self._swatch.size())
        self._swatch.render(pix)
        drag.setPixmap(pix)

        result = drag.exec(Qt.MoveAction | Qt.CopyAction)
        if result == Qt.MoveAction:
            # Walk up to the parent _PaletteWidget and remove this cell
            p = self.parent()
            while p and not isinstance(p, _PaletteWidget):
                p = p.parent()
            if p:
                p._remove_cell(self)

    _drag_start = None
    _ctrl_drag_active = False

    def _on_hex_changed(self, text: str) -> None:
        # Auto-prepend "#" when a bare hex value lands in the field — covers
        # the in-a-hurry paste case ("282828" instead of "#282828").  Only
        # acts on lengths 6 and 8 so character-by-character typing of those
        # forms isn't second-guessed before the user finishes.  The setText
        # call cascades back into this slot with the corrected value and
        # falls through to the validator below.
        if (text and not text.startswith("#")
                and len(text) in (6, 8)
                and all(ch in "0123456789abcdefABCDEF" for ch in text)):
            self._hex.setText("#" + text)
            self._hex.setCursorPosition(len(text) + 1)
            return
        c = QColor(text)
        if c.isValid():
            self._update_swatch(text)

    def _update_swatch(self, hex_color: str) -> None:
        self._swatch.setStyleSheet(
            f"background: {hex_color};"
            f"border: 1px solid {Theme.primaryBorder};"
            f"border-radius: 4px;"
        )

    def enterEvent(self, event):
        self._rm_btn.move(self.width() - 18, 2)
        self._rm_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._rm_btn.hide()
        super().leaveEvent(event)

    def get_data(self) -> dict:
        return {"label": self._label.text(), "hex": self._hex.text()}


# ─────────────────────────────────────────────────────────────────────────────
# PALETTE WIDGET  — scrollable 2-up grid of swatch cells
# ─────────────────────────────────────────────────────────────────────────────

class _PaletteWidget(QWidget):

    def __init__(self, colors: list, on_change):
        super().__init__()
        self._on_change = on_change
        self._cells: list[_SwatchCell] = []

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self.setAcceptDrops(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # ── Scroll area ───────────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 5px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {Theme.primaryBorder}; border-radius: 2px; min-height: 16px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        self._container = QWidget()
        self._container.setAttribute(Qt.WA_TranslucentBackground)
        self._container.setStyleSheet("background: transparent;")
        # Viewport intercepts drag events before the container — install an
        # event filter so we catch drops without subclassing QScrollArea.
        self._scroll.setAcceptDrops(True)
        self._scroll.viewport().setAcceptDrops(True)
        self._scroll.viewport().installEventFilter(self)
        self._grid = QGridLayout(self._container)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setHorizontalSpacing(CELL_SPACING)
        self._grid.setVerticalSpacing(CELL_SPACING)

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll, 1)

        # ── Add button ────────────────────────────────────────────────────────
        add_btn = QPushButton("+ add color")
        add_btn.setFixedHeight(22)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background:    transparent;
                color:         {Theme.textPrimary};
                border:        1px solid {Theme.primaryBorder};
                border-radius: 4px;
                font-family:   'Chandler42';
                font-size:     8pt;
                padding:       0 6px;
            }}
            QPushButton:hover {{
                border-color: {Theme.nodeBorderSelected};
                color:        {Theme.nodeBorderSelected};
            }}
        """)
        add_btn.clicked.connect(lambda: self.add_color())
        outer.addWidget(add_btn)

        for c in colors:
            self._append_cell(c.get("label", "Color"), c.get("hex", "#888888"))

    # ── Drag and drop ──────────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        """Intercept drag events on the scroll-area viewport."""
        if obj is self._scroll.viewport():
            t = event.type()
            if t == QEvent.DragEnter:
                if event.mimeData().hasFormat(_MIME_TYPE):
                    event.setDropAction(Qt.MoveAction)
                    event.accept()
                return True
            if t == QEvent.DragMove:
                if event.mimeData().hasFormat(_MIME_TYPE):
                    event.setDropAction(Qt.MoveAction)
                    event.accept()
                return True
            if t == QEvent.Drop:
                if event.mimeData().hasFormat(_MIME_TYPE):
                    data = _json.loads(bytes(event.mimeData().data(_MIME_TYPE)).decode())
                    vp_pos = event.position().toPoint()
                    cpos   = self._container.mapFrom(self._scroll.viewport(), vp_pos)
                    idx    = self._index_at_container_pos(cpos)
                    self._insert_cell_at(data.get("label", "Color"), data.get("hex", "#888888"), idx)
                    # Drop on the same palette → duplicate (CopyAction so the
                    # source's MoveAction post-check skips the remove step).
                    # Drop on a different palette → move, original goes away
                    # at the source.
                    src_palette = event.source()
                    while src_palette and not isinstance(src_palette, _PaletteWidget):
                        src_palette = src_palette.parent()
                    if src_palette is self:
                        event.setDropAction(Qt.CopyAction)
                    else:
                        event.setDropAction(Qt.MoveAction)
                    event.accept()
                return True
        return super().eventFilter(obj, event)

    def _index_at_container_pos(self, pos: QPoint) -> int:
        """Insertion index from a position already in _container coordinates."""
        for i, cell in enumerate(self._cells):
            geo = cell.geometry()
            if pos.y() < geo.center().y():
                return i
            if pos.y() < geo.bottom() and pos.x() < geo.center().x():
                return i
        return len(self._cells)

    def _insert_cell_at(self, label: str, hex_color: str, index: int) -> None:
        cell = _SwatchCell(label, hex_color, self._fire_change, self._remove_cell)
        self._cells.insert(index, cell)
        self._relayout()
        self._fire_change()

    # ── Cell management ───────────────────────────────────────────────────────

    def _append_cell(self, label: str, hex_color: str) -> None:
        cell = _SwatchCell(label, hex_color, self._fire_change, self._remove_cell)
        self._cells.append(cell)
        self._relayout()

    def _remove_cell(self, cell: _SwatchCell) -> None:
        if cell in self._cells:
            self._cells.remove(cell)
            cell.setParent(None)
            cell.deleteLater()
            self._relayout()
            self._fire_change()

    def _relayout(self) -> None:
        # Clear grid without destroying widgets
        while self._grid.count():
            self._grid.takeAt(0)
        for i, cell in enumerate(self._cells):
            row = i // COLUMNS
            col = i %  COLUMNS
            self._grid.addWidget(cell, row, col, Qt.AlignTop)

    def _fire_change(self) -> None:
        self._on_change(self.get_colors())

    def add_color(self, label: str = "Color", hex_color: str | None = None) -> None:
        # Default → sample a random colour from Intricate's live tint palette
        # (color_registry.toml).  Same source the node tint cycle uses and
        # the Settlers' Color Picker category curates, so new swatches
        # arrive in colours that already belong to the user's rotation.  The
        # Settlers owns curation; PaletteNode is a pure consumer.  Whatever
        # the user has the registry set to at any point — that's the pool
        # we sample from, automatically, via the live-watched module.
        if hex_color is None:
            from utils.persistence import color_registry
            pool = color_registry.get_all()
            hex_color = _random.choice(pool) if pool else "#888888"
        self._append_cell(label, hex_color)
        self._fire_change()

    # ── Data access ───────────────────────────────────────────────────────────

    def get_colors(self) -> list:
        return [cell.get_data() for cell in self._cells]

    def set_colors(self, colors: list) -> None:
        for cell in list(self._cells):
            cell.setParent(None)
            cell.deleteLater()
        self._cells.clear()
        for c in colors:
            self._append_cell(c.get("label", "Color"), c.get("hex", "#888888"))



# ─────────────────────────────────────────────────────────────────────────────
# PALETTE NODE
# ─────────────────────────────────────────────────────────────────────────────

class PaletteNode(BaseNode):
    _has_depth_toggle = True
    """
    A swatch board for collecting and editing hex colors.

    Each cell shows a label, a large color swatch, and an editable hex field.
    Colors are arranged in a 2-column grid matching the Photoshop palette style.
    """

    _MIN_PALETTE_W = 280.0
    _MIN_PALETTE_H = 300.0

    # Resize-handle shelf coupling — same asymmetric thresholds AboutNode
    # uses so the gesture feels uniform across both nodes.  Reveal demands
    # a deliberate yank, hide is lighter so the user can dial the height
    # down tight without the shelf clinging on.
    _RESIZE_SHELF_REVEAL_THRESHOLD = 75.0
    _RESIZE_SHELF_HIDE_THRESHOLD   = 30.0

    def __init__(self, data: PaletteNodeData | None = None):
        if data is None:
            data = PaletteNodeData()
        # Enforce minimum size for the 2-column layout on session restore
        if data.width < self._MIN_PALETTE_W:
            data.width = 300.0
        if data.height < self._MIN_PALETTE_H:
            data.height = 420.0
        super().__init__(data)
        self._min_width  = self._MIN_PALETTE_W
        self._min_height = self._MIN_PALETTE_H

        # Start with the shelf collapsed — PaletteNode adopts AboutNode's
        # resize-handle reveal/hide gesture (mouseMoveEvent below) in place
        # of the default double-click toggle.  Buttons surface only when
        # the user yanks the resize handle past the reveal threshold.
        self._buttons_visible = False
        self._anim_top_offset = self._HIDDEN_TOP_OFFSET
        for btn in self._buttons:
            btn.hide()
        self._shelf_anchor_h: float | None = None

        self._palette: _PaletteWidget | None = None
        self._palette_proxy: QGraphicsProxyWidget | None = None
        self._build_palette_view()

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        from nodes.NodeButton import NodeButton
        super()._build_buttons()
        snap_pix = Theme.icon(Theme.iconPush, fallback_color="#8cbea0")
        snap_btn = NodeButton(self, snap_pix, self._snapshot_to_png)
        snap_btn.setToolTip("Export the palette")
        self._buttons.append(snap_btn)

    def _snapshot_to_png(self) -> None:
        """Render the entire node (border, title, swatches) to a PNG."""
        from utils.helpers import snapshot_node
        path = snapshot_node(self)
        if path:
            views = self.scene().views() if self.scene() else []
            if views:
                win = views[0].window()
                if hasattr(win, 'show_info'):
                    win.show_info(f"{path.name} exported")

    # ─────────────────────────────────────────────────────────────────────────
    # LAYOUT
    # ─────────────────────────────────────────────────────────────────────────

    def _body_rect(self) -> QRectF:
        # Tracks _anim_top_offset (not _BUTTON_ZONE_H) so the swatch grid
        # slides up with the shelf when it collapses, keeping a constant
        # visual gap between title and body across both shelf states.
        r   = self.rect()
        top = r.y() + self._anim_top_offset + TITLE_GAP + PADDING
        return QRectF(
            r.x()  + PADDING,
            top,
            r.width()  - PADDING * 2,
            r.height() - (top - r.y()) - PADDING,
        )

    def _build_palette_view(self) -> None:
        self._palette = _PaletteWidget(
            colors    = list(self.data.colors),
            on_change = self._on_colors_changed,
        )
        self._palette_proxy = QGraphicsProxyWidget(self)
        self._palette_proxy.setWidget(self._palette)
        self._palette_proxy.setAcceptDrops(True)
        self._palette_proxy.setGeometry(self._body_rect())
        self._palette_proxy.show()

    def _on_colors_changed(self, colors: list) -> None:
        self.data.colors = colors

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────────────
    # SHELF GESTURE  — resize-handle reveal/hide, same pattern as AboutNode
    # ─────────────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        # Seed the shelf anchor at every press so the first threshold
        # check in mouseMoveEvent measures from press-time height.
        self._shelf_anchor_h = self.rect().height()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        # BaseNode resize must run first so self.rect() reflects the
        # updated geometry before we measure the delta.
        super().mouseMoveEvent(event)
        if not self._is_resizing:
            return
        if self._shelf_anchor_h is None:
            self._shelf_anchor_h = self.rect().height()
        delta_h = self.rect().height() - self._shelf_anchor_h
        if not self._buttons_visible and delta_h > self._RESIZE_SHELF_REVEAL_THRESHOLD:
            self._toggle_shelf()
            self._shelf_anchor_h = self.rect().height()
        elif self._buttons_visible and delta_h < -self._RESIZE_SHELF_HIDE_THRESHOLD:
            self._toggle_shelf()
            self._shelf_anchor_h = self.rect().height()

    def _on_shelf_tick(self, value: float) -> None:
        # Reposition the palette proxy every animation frame so the swatch
        # grid follows the sliding _anim_top_offset.  Without this hook the
        # body would jump to its final position only at animation end.
        super()._on_shelf_tick(value)
        if self._palette_proxy:
            self._palette_proxy.setGeometry(self._body_rect())

    def _on_shelf_done(self) -> None:
        super()._on_shelf_done()
        if self._palette_proxy:
            self._palette_proxy.setGeometry(self._body_rect())

    # ─────────────────────────────────────────────────────────────────────────
    # TITLE EDITING
    # ─────────────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        """Double-click on the title row → inline edit the node title.

        Shelf zone (when revealed) is reserved for shelf interactions; below
        the title row the event is consumed so it does NOT fall through to
        BaseNode's default top-strip shelf-toggle — PaletteNode now uses the
        resize-handle gesture for hide/reveal instead.
        """
        if self._buttons_visible and event.pos().y() < self._anim_top_offset:
            event.accept()
            return
        if event.pos().y() < self._anim_top_offset + self._BODY_OFFSET:
            self._start_title_edit()
            event.accept()
            return
        event.accept()

    def _start_title_edit(self) -> None:
        if hasattr(self, '_title_proxy') and self._title_proxy and self._title_proxy.isVisible():
            return
        # BaseNode._title_rect returns a rect spanning the whole body height
        # (it's used as a clip area for paint, not an edit overlay).  A
        # QLineEdit set to that geometry vertically-centres its text and
        # cursor inside the body — the title-edit field then floats in the
        # middle of the node between the swatch rows.  Clamp the height to
        # one title row (BODY_OFFSET) so the edit overlay sits exactly
        # where the painted title sits.
        full = self._title_rect()
        tr = QRectF(full.left(), full.top(), full.width(), self._BODY_OFFSET)
        edit = QLineEdit(self.data.title)
        edit.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                color:      {Theme.textPrimary};
                border:     none;
                font-family: '{Theme.aboutFontFamily}';
                font-size:   {max(1, Theme.aboutFontSize)}pt;
                padding:     0;
            }}
        """)
        edit.selectAll()

        self._title_proxy = QGraphicsProxyWidget(self)
        self._title_proxy.setWidget(edit)
        self._title_proxy.setGeometry(tr)
        self._title_proxy.show()
        edit.setFocus()

        def _commit():
            self.data.title = edit.text().strip() or "Palette"
            self._title_proxy.hide()
            self._title_proxy = None
            self.update()

        edit.editingFinished.connect(_commit)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        if hasattr(self, '_title_proxy') and self._title_proxy and self._title_proxy.isVisible():
            return
        super().paint_content(painter)

    # ─────────────────────────────────────────────────────────────────────────
    # RESIZE
    # ─────────────────────────────────────────────────────────────────────────

    def setRect(self, rect: QRectF) -> None:
        super().setRect(rect)
        if self._palette_proxy:
            self._palette_proxy.setGeometry(self._body_rect())

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    # Proxy teardown (including scene-rect invalidate for stylesheet-
    # backed inner widgets) is handled by the crew from these decls.
    _demolition_proxies = ['_title_proxy', '_palette_proxy']

    def _demolition_post(self) -> None:
        # _palette was the inner widget of _palette_proxy — the crew
        # tore it down via setParent(None) + deleteLater(). Null ref.
        self._palette = None

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        if self._palette:
            self.data.colors = self._palette.get_colors()
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'PaletteNode':
        return PaletteNode(PaletteNodeData.from_dict(data))

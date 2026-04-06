#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - The Pretty Checkbox
-The last of the pretty checkboxes knew that it could become all that it was destined to be, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QWidget
from graphics.Theme import Theme
from widgets.PrettyLabel import PrettyLabel
import utils.settings as settings


class PrettyCheckbox(QWidget):
    """
    Composite checkbox: a PrettyLabel paired with a bare indicator QCheckBox.

    The label and indicator are independent widgets in a QHBoxLayout, giving
    full layout control over text alignment while the indicator floats
    immediately after the text.

    When added to a PrettyCheckboxGroup the composite's own layout is bypassed —
    the group places _label and _box directly into a QGridLayout so every
    indicator in the group shares the same column and aligns automatically.

    indicator_right=True  (default) → Label | Indicator
    indicator_right=False           → Indicator | Label
    """

    toggled      = Signal(bool)
    stateChanged = Signal(int)
    clicked      = Signal(bool)

    def __init__(self, text: str = "", indicator_right: bool = True, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._indicator_right = indicator_right

        self._label = PrettyLabel(text.capitalize(), clickable=True)
        self._label.clicked.connect(self._on_label_clicked)
        self._box   = QCheckBox()
        self._apply_indicator_style()

        # Standalone layout — used when NOT inside a PrettyCheckboxGroup
        self._standalone_layout = QHBoxLayout(self)
        self._standalone_layout.setContentsMargins(0, 0, 0, 0)
        self._standalone_layout.setSpacing(5)
        if indicator_right:
            self._standalone_layout.addWidget(self._label)
            self._standalone_layout.addWidget(self._box)
        else:
            self._standalone_layout.addWidget(self._box)
            self._standalone_layout.addWidget(self._label)

        # Forward checkbox signals
        self._box.toggled.connect(self.toggled)
        self._box.stateChanged.connect(self.stateChanged)
        self._box.clicked.connect(self.clicked)

    # ── Indicator styling ─────────────────────────────────────────────────────

    def _apply_indicator_style(self) -> None:
        off_path = self._resolve_icon("checkbox_disabled")
        on_path  = self._resolve_icon("checkbox_enabled")

        if off_path and on_path:
            # PNG icons — scale to 11×11 to match the drawn fallback size
            self._box.setStyleSheet(
                f"""
                QCheckBox {{ spacing: 0px; }}
                QCheckBox::indicator {{
                    width:  11px;
                    height: 11px;
                }}
                QCheckBox::indicator:unchecked {{
                    image: url({off_path});
                }}
                QCheckBox::indicator:checked {{
                    image: url({on_path});
                }}
                """
            )
        else:
            # Drawn fallback — solid border box
            self._box.setStyleSheet(
                f"""
                QCheckBox {{ spacing: 0px; }}
                QCheckBox::indicator {{
                    width:  11px;
                    height: 11px;
                    border: 1px solid {Theme.primaryBorder};
                    border-radius: 2px;
                    background: transparent;
                }}
                QCheckBox::indicator:checked {{
                    background: {Theme.primaryBorder};
                }}
                """
            )

    @staticmethod
    def _resolve_icon(key: str) -> str | None:
        """Return a forward-slash URL string for a theme icon, or None."""
        filename = settings.get_nested("theme", "icons", key, None)
        if not filename:
            return None
        path = Theme._resolve_icon_path(filename)
        if not path:
            return None
        return str(path).replace("\\", "/")

    def update_style(self) -> None:
        """Re-apply all styles after a theme reload."""
        self._label._apply_style()
        self._apply_indicator_style()

    # ── Click anywhere on the composite toggles the box ──────────────────────

    def _on_label_clicked(self) -> None:
        self._box.toggle()

    def mousePressEvent(self, event) -> None:
        # Handles clicks on the widget background (gap between label and box).
        # Label clicks are handled by _on_label_clicked to avoid double-toggle.
        self._box.toggle()
        super().mousePressEvent(event)

    # ── QCheckBox API passthrough ─────────────────────────────────────────────

    def isChecked(self) -> bool:
        return self._box.isChecked()

    def setChecked(self, value: bool) -> None:
        self._box.setChecked(value)

    def checkState(self):
        return self._box.checkState()


class PrettyCheckboxGroup(QWidget):
    """
    Container that aligns a column of PrettyCheckboxes so every indicator
    lands at the same x position regardless of label length.

    Internally uses a QGridLayout — labels in column 0, indicators in column 1.
    Qt sizes column 0 to the widest label automatically, so the indicators
    always share a single column edge.

    Usage:
        group = checkbox_group()
        group.add(pretty_checkbox("Alpha", toggled=...))
        group.add(pretty_checkbox("Fade"))
        group.add(pretty_checkbox("Loop"))
    """

    def __init__(self, spacing: int = 2, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(5)
        self._grid.setVerticalSpacing(spacing)
        self._row        = 0
        self._checkboxes: list[PrettyCheckbox] = []

    def add(self, cb: PrettyCheckbox) -> PrettyCheckbox:
        """
        Add a PrettyCheckbox to the group.  The checkbox's own standalone
        layout is bypassed — _label and _box are lifted into the group's
        QGridLayout directly.  Returns the checkbox so callers can store it.
        """
        if cb._indicator_right:
            self._grid.addWidget(cb._label, self._row, 0,
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._grid.addWidget(cb._box,   self._row, 1,
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        else:
            self._grid.addWidget(cb._box,   self._row, 0,
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._grid.addWidget(cb._label, self._row, 1,
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._row += 1
        self._checkboxes.append(cb)
        return cb

    def update_style(self) -> None:
        for cb in self._checkboxes:
            cb.update_style()


def checkbox(
    text: str = "",
    indicator_right: bool = True,
    parent=None,
    **kwargs,
) -> PrettyCheckbox:
    """
    Create a themed PrettyCheckbox.

    Args:
        indicator_right: True  → label on left, indicator on right (default).
                         False → indicator on left, label on right.

    Common kwargs:
        checked        = bool      → setChecked(bool)
        toggled        = callable  → toggled.connect(callable)
        clicked        = callable  → clicked.connect(callable)
    """
    cb = PrettyCheckbox(text, indicator_right=indicator_right, parent=parent)

    for signal_name in ("toggled", "clicked", "stateChanged"):
        if signal_name in kwargs:
            slot = kwargs.pop(signal_name)
            if slot:
                getattr(cb, signal_name).connect(slot)

    for key, value in kwargs.items():
        if not key:
            continue
        setter_name = f"set{key[0].upper()}{key[1:]}"
        setter = getattr(cb, setter_name, None)
        if setter:
            setter(value)
        else:
            print(f"Warning: PrettyCheckbox has no setter for '{key}' (tried {setter_name})")

    return cb


def checkbox_group(spacing: int = 2, parent=None) -> PrettyCheckboxGroup:
    """Create a PrettyCheckboxGroup that auto-aligns indicator columns."""
    return PrettyCheckboxGroup(spacing=spacing, parent=parent)

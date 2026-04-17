#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/PremiereBridgeNode.py PremiereBridgeNode class
-Live wire between Intricate and Premiere Pro's CEP panel, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QFont

from nodes.BaseNode import BaseNode
from nodes.NodeButton import EmojiButton
from data.PremiereBridgeNodeData import PremiereBridgeNodeData
from utils.premiere_transport import (
    WebSocketTransport,
    STATUS_CONNECTED, STATUS_CONNECTING,
    STATUS_DISCONNECTED, STATUS_ERROR,
)
from pretty_widgets.graphics.Theme import Theme
from pretty_widgets.utils.logger import setup_logger

logger = setup_logger("premiere_bridge")


# Status dot colours — shares the progress-bar gradient vocabulary so the
# visual language stays consistent with joy bar and playback scrub.
_STATUS_COLORS = {
    STATUS_DISCONNECTED: "#5c3e4f",
    STATUS_CONNECTING:   "#a56a85",
    STATUS_CONNECTED:    "#d87a9e",
    STATUS_ERROR:        "#e27c7c",
}


class PremiereBridgeNode(BaseNode):
    """A node that opens a live wire to Premiere Pro's CEP panel.

    Phase 1: a "Ping 👋" button fires a TXT packet across the wire.
    The CEP panel echoes ``[Intricate] Hello 👋`` into Premiere's
    ExtendScript console and Events panel.

    Phase 2+: direct keyframe injection into Motion/Opacity components,
    handshake + heartbeat, per-packet ACK throttling, serial transport
    swap to match Adobe's paid-SDK security story.
    """

    def __init__(self, data: PremiereBridgeNodeData | None = None):
        if data is None:
            data = PremiereBridgeNodeData()
        super().__init__(data)

        self.setBrush(QColor(Theme.nodeBg))

        # ── Transport ────────────────────────────────────────────────────
        # parent=None — transport manages its own lifetime; we sever signals
        # explicitly in _prepare_for_removal. A QGraphicsRectItem cannot
        # parent a QObject anyway, so this is also a structural constraint.
        self._transport = WebSocketTransport(host=data.host, port=data.port)
        self._transport.status_changed.connect(self._on_status_changed)
        self._transport.message_received.connect(self._on_message_received)
        self._current_status = STATUS_DISCONNECTED
        self._last_ack: str  = ""

        # Open the wire immediately — if Premiere isn't up yet, the
        # reconnect timer keeps trying every 2.5s, so the bridge just
        # attaches the moment the CEP panel comes online.
        self._transport.open()

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        """Add the Ping 👋 button alongside the base buttons."""
        super()._build_buttons()

        # Ping 👋 — the Phase 1 first-light action.
        # EmojiButton's set_emoji callback is invoked on click; we repurpose
        # it as our "fire packet" trigger and ignore the new emoji value.
        self._ping_emoji = "\U0001f44b"   # 👋
        self._ping_btn = EmojiButton(
            self,
            get_emoji=lambda: self._ping_emoji,
            set_emoji=lambda _: self._fire_ping(),
        )
        self._ping_btn.setToolTip("Ping Premiere — send Hello 👋 down the wire")
        # Slot right after the accent emoji (index 0) so the button is
        # visually prominent on the strip.
        self._buttons.insert(1, self._ping_btn)

    # ─────────────────────────────────────────────────────────────────────────
    # ACTIONS
    # ─────────────────────────────────────────────────────────────────────────

    def _fire_ping(self) -> None:
        """Send a ``TXT|Hello 👋|track|clip`` packet down the wire."""
        d = self.data
        ok = self._transport.send_packet("TXT", "Hello 👋", d.target_track, d.target_clip)
        if ok:
            logger.info("ping → Premiere (track=%d clip=%d)", d.target_track, d.target_clip)
            self._last_ack = "sent: Hello 👋"
        else:
            logger.info("ping skipped — transport %s", self._current_status)
            self._last_ack = f"not connected ({self._current_status})"
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # TRANSPORT CALLBACKS
    # ─────────────────────────────────────────────────────────────────────────

    def _on_status_changed(self, status: str) -> None:
        self._current_status = status
        logger.debug("transport status → %s", status)
        self.update()

    def _on_message_received(self, text: str) -> None:
        """Handle ACK / response text from the CEP panel."""
        self._last_ack = text
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def paint_content(self, painter: QPainter) -> None:
        # Title row (emoji + title) inherited from BaseNode
        super().paint_content(painter)

        painter.save()
        r   = self.rect()
        pad = 16.0
        y0  = r.top() + self._body_top() + 4.0

        # ── Status dot ────────────────────────────────────────────────────
        dot_color = QColor(_STATUS_COLORS.get(self._current_status, "#5c3e4f"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(dot_color)
        painter.drawEllipse(QRectF(r.left() + pad, y0 + 3, 10, 10))

        # ── Status label ──────────────────────────────────────────────────
        label_font = QFont(
            getattr(Theme, 'healthFontFamily', "Segoe UI"),
            max(1, Theme.aboutFontSize - 1),
        )
        painter.setFont(label_font)
        painter.setPen(QColor("#d6c9b5"))
        painter.drawText(
            QRectF(r.left() + pad + 16, y0, r.width() - pad * 2 - 16, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            self._current_status,
        )

        # ── Target address ────────────────────────────────────────────────
        addr_font = QFont(label_font)
        addr_font.setPointSize(max(1, label_font.pointSize() - 1))
        painter.setFont(addr_font)
        painter.setPen(QColor("#8a7a68"))
        painter.drawText(
            QRectF(r.left() + pad, y0 + 22, r.width() - pad * 2, 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"ws://{self.data.host}:{self.data.port}",
        )
        painter.drawText(
            QRectF(r.left() + pad, y0 + 40, r.width() - pad * 2, 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"track {self.data.target_track} · clip {self.data.target_clip}",
        )

        # ── Last message ──────────────────────────────────────────────────
        if self._last_ack:
            painter.setPen(QColor("#72b8b8"))
            painter.drawText(
                QRectF(r.left() + pad, y0 + 60, r.width() - pad * 2, 16),
                Qt.AlignLeft | Qt.AlignVCenter,
                "last: " + self._last_ack[:48],
            )

        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _prepare_for_removal(self) -> None:
        # Sever transport signals BEFORE the base class starts its teardown,
        # matching the contract from AboutNode._prepare_for_removal.
        for sig, slot in (
            (self._transport.status_changed,   self._on_status_changed),
            (self._transport.message_received, self._on_message_received),
        ):
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        try:
            self._transport.disconnect_all()
        except Exception:
            pass
        super()._prepare_for_removal()

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'PremiereBridgeNode':
        return PremiereBridgeNode(PremiereBridgeNodeData.from_dict(data))

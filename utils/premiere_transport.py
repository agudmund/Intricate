#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/premiere_transport.py Premiere bridge transport layer
-Abstracts the wire between Intricate and Premiere's CEP panel, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

from abc import abstractmethod
from PySide6.QtCore import QObject, Signal, QUrl, QTimer
from PySide6.QtWebSockets import QWebSocket

from pretty_widgets.utils.logger import setup_logger

logger = setup_logger("premiere_bridge")


# Transport status vocabulary — every transport speaks these four strings.
STATUS_DISCONNECTED = "disconnected"
STATUS_CONNECTING   = "connecting"
STATUS_CONNECTED    = "connected"
STATUS_ERROR        = "error"


class PacketTransport(QObject):
    """Abstract wire between Intricate and Premiere's CEP receiver.

    All transports speak the same packet format: ``Prop|Val|Track|Clip``.
    Subclasses (WebSocket, Serial, NamedPipe) own only the wire mechanics —
    nodes talk to this abstraction and never care which transport is live.

    Signals:
        status_changed(str)   — one of STATUS_* constants
        message_received(str) — raw text frame from the receiver
    """

    status_changed   = Signal(str)
    message_received = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._status = STATUS_DISCONNECTED

    # ── Status ───────────────────────────────────────────────────────────────

    @property
    def status(self) -> str:
        return self._status

    def _set_status(self, status: str) -> None:
        if status != self._status:
            self._status = status
            self.status_changed.emit(status)

    # ── Interface ────────────────────────────────────────────────────────────

    @abstractmethod
    def open(self) -> None:
        """Begin listening/connecting. Safe to call multiple times."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Hang up. Safe to call even when not open."""
        ...

    @abstractmethod
    def send_raw(self, line: str) -> bool:
        """Transmit a raw text frame. Returns True if handed to the wire."""
        ...

    # ── Packet helper ────────────────────────────────────────────────────────

    def send_packet(self, prop: str, val, track: int = 0, clip: int = 0) -> bool:
        """Format a packet and send it.

        Packet format:  ``Prop|Val|Track|Clip``
        Phase 1 ping:   ``TXT|Hello 👋|0|0``
        Phase 2 scale:  ``Scale|120|0|0``

        Parse contract (honoured by every receiver in the family):

        - ``Track`` and ``Clip`` are always the LAST two fields and must
          be integer-parseable. Receivers split on ``|`` and pull them
          from the end by position.
        - ``Val`` is everything between ``Prop`` and ``Track`` — so it
          may safely contain literal ``|`` characters without escaping.
          The receiver rejoins the middle slice with ``|``.
        - ``Prop`` is the first field and should not contain ``|``.

        This contract means ``Scale|120|0|0``, ``TXT|Hello|world|0|0``
        (val = "Hello|world"), and ``LUT|/path/to/file.cube|0|0`` all
        parse unambiguously.
        """
        return self.send_raw(f"{prop}|{val}|{track}|{clip}")


# ═════════════════════════════════════════════════════════════════════════════
# WEBSOCKET TRANSPORT
# ═════════════════════════════════════════════════════════════════════════════

class WebSocketTransport(PacketTransport):
    """WebSocket client targeting ``ws://host:port``.

    Auto-reconnects every RECONNECT_INTERVAL_MS when the socket is open-wanted
    but disconnected. Safe to call ``open()`` and ``close()`` repeatedly.

    The CEP receiver in Premiere runs a WebSocketServer on the same address
    (see ``com.intricate.bridge/index.html``).
    """

    RECONNECT_INTERVAL_MS = 2500

    def __init__(self, host: str = "127.0.0.1", port: int = 9914, parent=None):
        super().__init__(parent)
        self._host = host
        self._port = port
        self._url  = QUrl(f"ws://{host}:{port}")

        self._ws = QWebSocket()
        self._ws.connected.connect(self._on_connected)
        self._ws.disconnected.connect(self._on_disconnected)
        self._ws.errorOccurred.connect(self._on_error)
        self._ws.textMessageReceived.connect(self._on_text)

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(self.RECONNECT_INTERVAL_MS)
        self._reconnect_timer.setSingleShot(False)
        self._reconnect_timer.timeout.connect(self._attempt_connect)

        self._want_open = False

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def open(self) -> None:
        self._want_open = True
        self._attempt_connect()
        if not self._reconnect_timer.isActive():
            self._reconnect_timer.start()

    def close(self) -> None:
        self._want_open = False
        self._reconnect_timer.stop()
        try:
            self._ws.close()
        except RuntimeError:
            pass

    def send_raw(self, line: str) -> bool:
        if self._status != STATUS_CONNECTED:
            logger.debug("ws send dropped (status=%s): %s", self._status, line)
            return False
        try:
            self._ws.sendTextMessage(line)
            logger.debug("ws ← %s", line)
            return True
        except Exception as e:
            logger.warning("ws send failed: %s", e)
            return False

    # ── Internal ─────────────────────────────────────────────────────────────

    def _attempt_connect(self) -> None:
        if not self._want_open:
            return
        if self._status in (STATUS_CONNECTING, STATUS_CONNECTED):
            return
        logger.debug("ws connecting to %s", self._url.toString())
        self._set_status(STATUS_CONNECTING)
        self._ws.open(self._url)

    def _on_connected(self) -> None:
        logger.info("ws connected to %s", self._url.toString())
        self._set_status(STATUS_CONNECTED)

    def _on_disconnected(self) -> None:
        # QWebSocket emits disconnected both on graceful close and after
        # a failed connect. Either way we want to drop to DISCONNECTED so
        # the reconnect timer can try again.
        logger.debug("ws disconnected from %s", self._url.toString())
        self._set_status(STATUS_DISCONNECTED)

    def _on_error(self, _err) -> None:
        msg = self._ws.errorString() if hasattr(self._ws, 'errorString') else "unknown"
        logger.debug("ws error: %s", msg)
        # Don't flip to ERROR permanently — the reconnect timer keeps trying,
        # which is the desired behaviour when Premiere's panel is starting up.

    def _on_text(self, text: str) -> None:
        logger.debug("ws → %s", text)
        self.message_received.emit(text)

    # ── Teardown — called by the owning node before removal ──────────────────

    def disconnect_all(self) -> None:
        """Sever every signal connection this transport holds.

        Called from the owning node's ``_prepare_for_removal`` so the
        QWebSocket and timer don't keep the node alive after it leaves
        the scene.
        """
        self._reconnect_timer.stop()
        for sig, slot in (
            (self._reconnect_timer.timeout,   self._attempt_connect),
            (self._ws.connected,              self._on_connected),
            (self._ws.disconnected,           self._on_disconnected),
            (self._ws.errorOccurred,          self._on_error),
            (self._ws.textMessageReceived,    self._on_text),
        ):
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        try:
            self._ws.close()
        except RuntimeError:
            pass

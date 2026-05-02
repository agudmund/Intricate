#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/premiere_transport.py Premiere bridge transport layer
-Abstracts the wire between Intricate and Premiere's CEP panel, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import json
from abc import abstractmethod
from PySide6.QtCore import QObject, Signal, QUrl, QTimer
from PySide6.QtWebSockets import QWebSocket

from shared_braincell.logger import setup_logger

logger = setup_logger("premiere_bridge")


# Transport status vocabulary — every transport speaks these four strings.
STATUS_DISCONNECTED = "disconnected"
STATUS_CONNECTING   = "connecting"
STATUS_CONNECTED    = "connected"
STATUS_ERROR        = "error"

# Protocol version — bumped when the HELLO / READY JSON shape changes.
# Echoed in every HELLO so the CEP side can log drift between node and panel.
PROTOCOL_VERSION = 1


class PacketTransport(QObject):
    """Abstract wire between Intricate and Premiere's CEP receiver.

    All transports speak the same packet format: ``Prop|Val|Track|Clip``.
    Subclasses (WebSocket, Serial, NamedPipe) own only the wire mechanics —
    nodes talk to this abstraction and never care which transport is live.

    Signals:
        status_changed(str)       — one of STATUS_* constants
        message_received(str)     — raw text frame, still fired for every frame
                                    so any legacy TXT-echo receiver keeps working
        handshake_ready(dict)     — parsed READY payload from the CEP side
                                    (project / sequence / clip census)
        handshake_error(str, dict) — (reason, details_dict) from an ERROR frame
        pong_received(dict)       — parsed PONG payload from a heartbeat
    """

    status_changed    = Signal(str)
    message_received  = Signal(str)
    handshake_ready   = Signal(dict)
    handshake_error   = Signal(str, dict)
    pong_received     = Signal(dict)

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
          may safely contain literal ``|`` characters without escaping,
          including embedded JSON payloads (used by HELLO / READY / PONG).
          The receiver rejoins the middle slice with ``|``.
        - ``Prop`` is the first field and should not contain ``|``.

        This contract means ``Scale|120|0|0``, ``TXT|Hello|world|0|0``
        (val = "Hello|world"), and ``LUT|/path/to/file.cube|0|0`` all
        parse unambiguously.
        """
        return self.send_raw(f"{prop}|{val}|{track}|{clip}")

    # ── Handshake + heartbeat helpers ────────────────────────────────────────

    def send_hello(self, expected_project: str, expected_sequence: str,
                   track: int = 0, clip: int = 0,
                   client_id: str = "", intricate_version: str = "") -> bool:
        """Send a HELLO handshake packet.

        The Val slot carries a JSON blob of Intricate-side expectations.
        CEP calls ``handshakeReport`` in ``script.jsx`` and replies with
        either a READY frame (full census) or an ERROR frame (reason +
        details). Both replies are routed through the specialized signals
        (``handshake_ready`` / ``handshake_error``) by ``_route_frame``.
        """
        payload = {
            "expectedProject":  expected_project or "",
            "expectedSequence": expected_sequence or "",
            "protocolVersion":  PROTOCOL_VERSION,
            "clientId":         client_id,
            "intricateVersion": intricate_version,
        }
        return self.send_packet("HELLO", json.dumps(payload, separators=(",", ":")),
                                track, clip)

    def send_ping(self) -> bool:
        """Send a heartbeat ping. CEP replies PONG with a cheap liveness census."""
        return self.send_packet("PING", "", 0, 0)

    # ── Frame routing — subclasses call this on every received line ──────────

    def _route_frame(self, line: str) -> None:
        """Classify an incoming frame and emit the right specialized signal.

        ``message_received`` is still emitted for every frame so the
        simple TXT-echo readout on the node keeps working. Handshake
        and heartbeat frames additionally fire the structured signals.
        """
        self.message_received.emit(line)

        parts = line.split("|")
        if len(parts) < 4:
            return  # malformed; leave it for the raw-text receiver
        # Validate the trailing Track/Clip positions per the parse contract
        # — even though this router doesn't use them, we honour the format.
        try:
            int(parts[-1])
            int(parts[-2])
        except ValueError:
            return
        prop = parts[0]
        val  = "|".join(parts[1:-2])

        if prop == "READY":
            data = self._parse_json_val(val)
            if data is not None:
                self.handshake_ready.emit(data)
        elif prop == "ERROR":
            data = self._parse_json_val(val) or {}
            reason = data.get("reason", "unknown") if isinstance(data, dict) else "unknown"
            details = data.get("details", {}) if isinstance(data, dict) else {}
            self.handshake_error.emit(reason, details if isinstance(details, dict) else {})
        elif prop == "PONG":
            data = self._parse_json_val(val) or {}
            if isinstance(data, dict):
                self.pong_received.emit(data)

    @staticmethod
    def _parse_json_val(val: str):
        """Parse the Val slot as JSON; log and return None on failure."""
        if not val:
            return None
        try:
            return json.loads(val)
        except (ValueError, TypeError) as e:
            logger.warning("failed to parse JSON val (%s): %.80s", e, val)
            return None


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
            # Don't log heartbeat sends at debug — they'd flood the log.
            if not line.startswith("PING|"):
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
        # Skip the heartbeat-pong log noise; everything else goes through.
        if not text.startswith("PONG|"):
            logger.debug("ws → %s", text)
        self._route_frame(text)

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

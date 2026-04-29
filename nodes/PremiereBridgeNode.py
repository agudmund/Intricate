#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - nodes/PremiereBridgeNode.py PremiereBridgeNode class
-Live wire between Intricate and Premiere Pro's CEP panel, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import time
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QRectF, QPointF, QTimer
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


# ─── Status dot colour vocabulary ─────────────────────────────────────────────
# Shares the progress-bar gradient so the visual language stays consistent
# with the joy bar and playback scrub. "ready" is a sub-state of connected
# (the handshake has completed), hence its own colour leaning green-cream.
_DOT_DISCONNECTED = "#5c3e4f"   # deep rose
_DOT_CONNECTING   = "#a56a85"   # warm mauve
_DOT_CONNECTED    = "#d87a9e"   # bright pink (wire up, no handshake yet)
_DOT_READY        = "#b8e0b0"   # pale leaf (handshake complete)
_DOT_ERROR        = "#e27c7c"   # warm red

_HANDSHAKE_IDLE    = "idle"
_HANDSHAKE_PENDING = "pending"
_HANDSHAKE_READY   = "ready"
_HANDSHAKE_ERROR   = "error"

# Setup-state reasons aren't really errors — the wire is up, Premiere is
# awake, the user just hasn't yet created the thing the bridge needs to
# paint on. Treat them as friendly hints (bright-pink "connected" dot,
# friendlier status line, no scary "ERROR" prefix in the readout) rather
# than the warm-red error path used for genuine mismatches and exceptions.
_SETUP_STATE_REASONS = frozenset({"no_project_open", "no_active_sequence"})

# Friendly status-line wording for each setup state — short enough to fit
# the "connected — …" status pill without truncation.
_SETUP_STATE_STATUS = {
    "no_project_open":    "open a project to begin",
    "no_active_sequence": "create a sequence to begin",
}

# Heartbeat cadence. 5s is slow enough that it doesn't flood CEP's jsx
# engine, fast enough that a dead wire is caught inside 15s (3 strikes).
_HEARTBEAT_MS       = 5000
_MISSED_PONGS_LIMIT = 3

# ─── Error poetry ─────────────────────────────────────────────────────────────
# Registry-tone one-liners. Surface on the chained AboutNode when the
# handshake comes back with ok=false. The structural details (expected
# vs actual) get appended after the poetic line so both layers are visible.
_ERROR_POETRY = {
    "no_project_open":
        "Premiere is awake but no project is loaded — a theatre with no play.",
    "no_active_sequence":
        "The project's here but no sequence is on the timeline — nothing to paint on.",
    "project_mismatch":
        "The project open in Premiere isn't the one this bridge was waiting for.",
    "sequence_mismatch":
        "The sequence on the timeline isn't the one the bridge was listening for.",
    "extendscript_exception":
        "Something tripped on the ExtendScript side — the engine threw before it could answer.",
    "heartbeat_exception":
        "The heartbeat check raised on the ExtendScript side — probably transient.",
    "wire_silent":
        "The wire was up but went quiet — three heartbeats passed without a pong. Letting go.",
    "unknown":
        "Something's off and Premiere isn't saying what.",
}


class PremiereBridgeNode(BaseNode):
    """A node that opens a live wire to Premiere Pro's CEP panel.

    Phase 1 (done): 👋 button fires TXT packet, round-trip to toast + ACK.
    Phase 2a (done): clean packet parser, ACK/NACK distinction.
    Phase 2b (this): handshake + heartbeat.
        - On CONNECTED, send HELLO with expected project / sequence.
        - CEP replies READY (full census) or ERROR (reason + details).
        - On READY, start 5s heartbeat; 3 missed PONGs → wire silent.
        - On any ERROR or wire_silent, spawn an AboutNode chained to
          the bridge so the reason is visible on the canvas itself
          rather than hidden in a log.
    Phase 2c (next): actual keyframe injection.
    """

    def __init__(self, data: PremiereBridgeNodeData | None = None):
        if data is None:
            data = PremiereBridgeNodeData()
        super().__init__(data)

        self.setBrush(QColor(Theme.nodeBg))

        # ── Transport ────────────────────────────────────────────────────
        # parent=None — transport manages its own lifetime; signals severed
        # explicitly in _prepare_for_removal.
        self._transport = WebSocketTransport(host=data.host, port=data.port)
        self._transport.status_changed.connect(self._on_status_changed)
        self._transport.message_received.connect(self._on_message_received)
        self._transport.handshake_ready.connect(self._on_handshake_ready)
        self._transport.handshake_error.connect(self._on_handshake_error)
        self._transport.pong_received.connect(self._on_pong_received)

        # ── State ────────────────────────────────────────────────────────
        self._current_status    = STATUS_DISCONNECTED
        self._handshake_state   = _HANDSHAKE_IDLE
        self._last_ack          = ""
        self._last_error_reason = ""   # used to de-duplicate AboutNode spawns
        self._last_rtt_ms       = 0.0
        self._missed_pongs      = 0
        self._ping_sent_at      = 0.0

        # ── Heartbeat ────────────────────────────────────────────────────
        self._heartbeat_timer = QTimer()
        self._heartbeat_timer.setInterval(_HEARTBEAT_MS)
        self._heartbeat_timer.setSingleShot(False)
        self._heartbeat_timer.timeout.connect(self._tick_heartbeat)

        # Open the wire immediately. Reconnect timer keeps retrying if
        # Premiere's panel isn't up yet.
        self._transport.open()

    # ─────────────────────────────────────────────────────────────────────────
    # BUTTONS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        """Add 👋 ping and 🔄 re-handshake buttons alongside the base set."""
        super()._build_buttons()

        # 👋 — the Phase 1 first-light action (send TXT down the wire).
        self._ping_emoji = "\U0001f44b"   # 👋
        self._ping_btn = EmojiButton(
            self,
            get_emoji=lambda: self._ping_emoji,
            set_emoji=lambda _: self._fire_ping(),
        )
        self._ping_btn.setToolTip("Ping Premiere — send Hello 👋 down the wire")
        self._buttons.insert(1, self._ping_btn)

        # 🔄 — re-fire HELLO. Useful after fixing a project/sequence mismatch
        # without needing to bounce the CEP panel.
        self._rehandshake_emoji = "\U0001f504"   # 🔄
        self._rehandshake_btn = EmojiButton(
            self,
            get_emoji=lambda: self._rehandshake_emoji,
            set_emoji=lambda _: self._fire_handshake(),
        )
        self._rehandshake_btn.setToolTip(
            "Re-handshake — ask Premiere what's open and validate expectations"
        )
        self._buttons.insert(2, self._rehandshake_btn)

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

    def _fire_handshake(self) -> None:
        """Send (or re-send) a HELLO packet, kicking off the handshake."""
        if self._current_status != STATUS_CONNECTED:
            logger.info("handshake skipped — transport %s", self._current_status)
            self._last_ack = f"can't handshake ({self._current_status})"
            self.update()
            return
        d = self.data
        client_id = getattr(d, "uuid", "") or ""
        ok = self._transport.send_hello(
            expected_project  = d.expected_project,
            expected_sequence = d.expected_sequence,
            track             = d.target_track,
            clip              = d.target_clip,
            client_id         = client_id,
            intricate_version = "0.2b",  # bump when we cut a release tag
        )
        if ok:
            self._handshake_state = _HANDSHAKE_PENDING
            logger.info("HELLO → Premiere (strict=%s / %s)",
                        d.expected_project or "*", d.expected_sequence or "*")
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # TRANSPORT CALLBACKS
    # ─────────────────────────────────────────────────────────────────────────

    def _on_status_changed(self, status: str) -> None:
        prev = self._current_status
        self._current_status = status
        logger.debug("transport status: %s → %s", prev, status)

        if status == STATUS_CONNECTED:
            # Wire just came up — fire the handshake immediately.
            self._fire_handshake()
        else:
            # Wire dropped (or never came up): reset everything handshake-side
            # so the next CONNECTED triggers a fresh HELLO.
            self._handshake_state   = _HANDSHAKE_IDLE
            self._missed_pongs      = 0
            self._last_rtt_ms       = 0.0
            self._heartbeat_timer.stop()

        self.update()

    def _on_message_received(self, text: str) -> None:
        """Raw-text receiver — surface ACKs and the like on the paint readout."""
        # Structural frames (READY/ERROR/PONG) are handled through their
        # dedicated signals. Only update the readout for the other traffic
        # so the user can still see ACK|TXT after a 👋 ping.
        prop = text.split("|", 1)[0] if "|" in text else text
        if prop in ("READY", "ERROR", "PONG"):
            return
        self._last_ack = text
        self.update()

    def _on_handshake_ready(self, census: dict) -> None:
        """READY received — full census delivered. Lock in last-known state."""
        self._handshake_state   = _HANDSHAKE_READY
        self._last_error_reason = ""
        self._missed_pongs      = 0

        d = self.data
        proj = census.get("project", {}) or {}
        seq  = census.get("sequence", {}) or {}
        clip = census.get("selectedClip", {}) or {}

        d.last_project_path  = str(proj.get("path", "") or "")
        d.last_fps           = float(seq.get("fps", 0) or 0)
        d.last_width         = int(seq.get("width", 0) or 0)
        d.last_height        = int(seq.get("height", 0) or 0)
        d.last_video_tracks  = int(seq.get("videoTracks", 0) or 0)
        d.last_audio_tracks  = int(seq.get("audioTracks", 0) or 0)
        d.last_end_seconds   = float(seq.get("endSeconds") or 0.0)
        d.last_clip_name     = str((clip or {}).get("name", "") or "")
        d.last_premiere_ver  = str(census.get("premiereVersion", "") or "")
        d.last_handshake_at  = datetime.now(timezone.utc).isoformat(timespec="seconds")

        logger.info("READY — %s · %s · %.2ffps · %dx%d",
                    proj.get("name", "?"), seq.get("name", "?"),
                    d.last_fps, d.last_width, d.last_height)

        # Start the heartbeat now that we've got a good wire.
        if not self._heartbeat_timer.isActive():
            self._heartbeat_timer.start()

        self._last_ack = "READY · " + str(proj.get("name", "?"))
        self.update()

    def _on_handshake_error(self, reason: str, details: dict) -> None:
        """ERROR received — paint red and chain a poetic AboutNode.

        Setup-state reasons (no_project_open / no_active_sequence) skip
        the red-error treatment — they're friendly setup hints, not
        failures. The dot stays bright-pink "connected" and the readout
        uses encouraging wording.
        """
        self._handshake_state = _HANDSHAKE_ERROR
        self._heartbeat_timer.stop()
        is_setup = reason in _SETUP_STATE_REASONS
        if is_setup:
            logger.info("setup hint — %s (%s)", reason, details)
        else:
            logger.info("ERROR — %s (%s)", reason, details)

        # De-duplicate: only spawn a fresh AboutNode when the reason changes.
        # Re-firing the same error (user clicked 🔄 without fixing anything)
        # shouldn't litter the canvas.
        if reason != self._last_error_reason:
            self._spawn_error_about(reason, details)
        self._last_error_reason = reason
        if is_setup:
            self._last_ack = _SETUP_STATE_STATUS.get(reason, reason)
        else:
            self._last_ack = "ERROR · " + reason
        self.update()

    def _on_pong_received(self, payload: dict) -> None:
        """Heartbeat PONG — reset missed counter, record RTT."""
        if self._ping_sent_at:
            self._last_rtt_ms = (time.monotonic() - self._ping_sent_at) * 1000.0
        self._missed_pongs = 0
        # No paint update on every pong — would flicker. The next status
        # change or manual action repaints.

    # ─────────────────────────────────────────────────────────────────────────
    # HEARTBEAT
    # ─────────────────────────────────────────────────────────────────────────

    def _tick_heartbeat(self) -> None:
        """Called every _HEARTBEAT_MS once handshake is READY."""
        if self._handshake_state != _HANDSHAKE_READY:
            self._heartbeat_timer.stop()
            return

        # If the last ping didn't get a pong before this tick, count the miss.
        # Reset counter on pong arrival (see _on_pong_received).
        if self._ping_sent_at and self._last_rtt_ms == 0.0:
            self._missed_pongs += 1
        self._last_rtt_ms = 0.0  # require the NEXT pong to refresh

        if self._missed_pongs >= _MISSED_PONGS_LIMIT:
            # Wire went quiet. Flag the condition, drop the socket so the
            # reconnect timer takes over, spawn an AboutNode once.
            logger.warning("heartbeat — %d missed pongs, letting go", self._missed_pongs)
            self._heartbeat_timer.stop()
            self._handshake_state = _HANDSHAKE_ERROR
            if self._last_error_reason != "wire_silent":
                self._spawn_error_about("wire_silent",
                    {"missed": self._missed_pongs, "limit": _MISSED_PONGS_LIMIT})
                self._last_error_reason = "wire_silent"
            # Close the socket — reconnect timer on the transport picks up.
            try:
                self._transport.close()
                self._transport.open()
            except Exception as e:
                logger.warning("transport reopen after silent wire failed: %s", e)
            self.update()
            return

        # Fire a fresh ping.
        self._ping_sent_at = time.monotonic()
        self._transport.send_ping()

    # ─────────────────────────────────────────────────────────────────────────
    # ABOUTNODE — chained error message
    # ─────────────────────────────────────────────────────────────────────────

    def _spawn_error_about(self, reason: str, details: dict) -> None:
        """Spawn an AboutNode chained to this node with the error reason.

        Matches the pattern GitNode uses for offline-failure feedback:
        passive messaging via a chained sticky, not a log line or toast.
        """
        scene = self.scene()
        if scene is None:
            return

        poetry = _ERROR_POETRY.get(reason, _ERROR_POETRY["unknown"])

        # Build a human-readable tail from details — the "did you mean" layer.
        tail_bits = []
        if reason == "project_mismatch":
            exp = details.get("expected", "?")
            act = details.get("actual",   "?")
            tail_bits.append(f"expected “{exp}”, found “{act}”")
        elif reason == "sequence_mismatch":
            exp = details.get("expected", "?")
            act = details.get("actual",   "?")
            tail_bits.append(f"expected “{exp}”, found “{act}”")
            avail = details.get("availableSequences") or []
            if avail:
                tail_bits.append("available: " + ", ".join(avail[:5]))
        elif reason == "no_active_sequence":
            avail = details.get("availableSequences") or []
            if avail:
                tail_bits.append("available: " + ", ".join(avail[:5]))
        elif reason == "wire_silent":
            tail_bits.append(f"{details.get('missed', '?')} missed heartbeats "
                             f"over {_MISSED_PONGS_LIMIT * _HEARTBEAT_MS // 1000}s")
        elif reason in ("extendscript_exception", "heartbeat_exception"):
            msg = details.get("message", "")
            if msg:
                tail_bits.append(str(msg)[:120])

        label = poetry
        if tail_bits:
            label = label + "\n\n" + "\n".join(tail_bits)

        # Position 30px to the right of the node, at centre-y — same offset
        # as the GitNode pattern so the visual rhyme carries across the family.
        r   = self.rect()
        pos = self.mapToScene(QPointF(r.right() + 30, r.center().y()))
        try:
            about = scene.add_about_node(pos=pos, label=label)
        except Exception as e:
            logger.warning("add_about_node failed: %s", e)
            return

        try:
            from graphics.Connection import Connection
            wire = Connection(self, about)
            scene.addItem(wire)
        except Exception as e:
            logger.warning("chain wire failed: %s", e)

    # ─────────────────────────────────────────────────────────────────────────
    # PAINT
    # ─────────────────────────────────────────────────────────────────────────

    def _dot_color(self) -> QColor:
        if self._current_status == STATUS_ERROR:
            return QColor(_DOT_ERROR)
        if self._current_status == STATUS_DISCONNECTED:
            return QColor(_DOT_DISCONNECTED)
        if self._current_status == STATUS_CONNECTING:
            return QColor(_DOT_CONNECTING)
        # CONNECTED — further refined by handshake state.
        if self._handshake_state == _HANDSHAKE_READY:
            return QColor(_DOT_READY)
        if self._handshake_state == _HANDSHAKE_ERROR:
            # Setup-state reasons stay on the bright-pink connected dot —
            # the wire is up and the bridge is happy, the user just hasn't
            # finished setting Premiere up yet.
            if self._last_error_reason in _SETUP_STATE_REASONS:
                return QColor(_DOT_CONNECTED)
            return QColor(_DOT_ERROR)
        return QColor(_DOT_CONNECTED)

    def _status_line(self) -> str:
        """Blend transport status and handshake state into one human string."""
        if self._current_status != STATUS_CONNECTED:
            return self._current_status
        hs = self._handshake_state
        if hs == _HANDSHAKE_READY:   return "ready — wire is warm"
        if hs == _HANDSHAKE_PENDING: return "connected — handshaking…"
        if hs == _HANDSHAKE_ERROR:
            reason = self._last_error_reason
            if reason in _SETUP_STATE_REASONS:
                return "connected — " + _SETUP_STATE_STATUS[reason]
            return "connected but " + (reason or "not happy")
        return "connected"

    def paint_content(self, painter: QPainter) -> None:
        super().paint_content(painter)

        painter.save()
        r   = self.rect()
        pad = 16.0
        y   = r.top() + self._body_top() + 4.0
        w   = r.width() - pad * 2

        # ── Status dot + primary status line ──────────────────────────────
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._dot_color())
        painter.drawEllipse(QRectF(r.left() + pad, y + 3, 10, 10))

        label_font = QFont(
            getattr(Theme, 'healthFontFamily', "Segoe UI"),
            max(1, Theme.aboutFontSize - 1),
        )
        painter.setFont(label_font)
        painter.setPen(QColor("#d6c9b5"))
        painter.drawText(
            QRectF(r.left() + pad + 16, y, w - 16, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            self._status_line(),
        )
        y += 18

        # ── Wire target ───────────────────────────────────────────────────
        small = QFont(label_font)
        small.setPointSize(max(1, label_font.pointSize() - 1))
        painter.setFont(small)
        painter.setPen(QColor("#8a7a68"))
        painter.drawText(
            QRectF(r.left() + pad, y, w, 14),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"ws://{self.data.host}:{self.data.port}",
        )
        y += 14

        # ── Strictness indicator ──────────────────────────────────────────
        d = self.data
        if d.expected_project or d.expected_sequence:
            expect = "strict: "
            if d.expected_project:  expect += d.expected_project
            if d.expected_sequence: expect += f" · {d.expected_sequence}"
            painter.setPen(QColor("#c89060"))  # amber — discipline colour
        else:
            expect = "permissive (any project/sequence)"
            painter.setPen(QColor("#6a8a7a"))
        painter.drawText(
            QRectF(r.left() + pad, y, w, 14),
            Qt.AlignLeft | Qt.AlignVCenter,
            expect,
        )
        y += 14

        # ── Last-known census (populated after first READY) ───────────────
        if d.last_fps > 0 or d.last_width > 0:
            census = f"{d.last_fps:.2f}fps · {d.last_width}×{d.last_height}"
            if d.last_video_tracks or d.last_audio_tracks:
                census += f" · {d.last_video_tracks}V/{d.last_audio_tracks}A"
            painter.setPen(QColor("#72b8b8"))
            painter.drawText(
                QRectF(r.left() + pad, y, w, 14),
                Qt.AlignLeft | Qt.AlignVCenter,
                census,
            )
            y += 14

        # ── Clip address + last-known clip name ───────────────────────────
        clip_line = f"track {d.target_track} · clip {d.target_clip}"
        if d.last_clip_name:
            clip_line += f" · {d.last_clip_name}"
        painter.setPen(QColor("#8a7a68"))
        painter.drawText(
            QRectF(r.left() + pad, y, w, 14),
            Qt.AlignLeft | Qt.AlignVCenter,
            clip_line,
        )
        y += 14

        # ── Heartbeat readout ─────────────────────────────────────────────
        if self._handshake_state == _HANDSHAKE_READY:
            if self._missed_pongs > 0:
                heart = f"♥ {self._missed_pongs} miss"
                painter.setPen(QColor("#c89060"))
            elif self._last_rtt_ms > 0:
                heart = f"♥ {self._last_rtt_ms:.0f}ms"
                painter.setPen(QColor("#6a8a7a"))
            else:
                heart = "♥ …"
                painter.setPen(QColor("#6a7080"))
            painter.drawText(
                QRectF(r.left() + pad, y, w, 14),
                Qt.AlignLeft | Qt.AlignVCenter,
                heart,
            )
            y += 14

        # ── Last ACK line ─────────────────────────────────────────────────
        if self._last_ack:
            painter.setPen(QColor("#72b8b8"))
            painter.drawText(
                QRectF(r.left() + pad, y, w, 14),
                Qt.AlignLeft | Qt.AlignVCenter,
                "last: " + self._last_ack[:48],
            )

        painter.restore()

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    _demolition_timers = [('_heartbeat_timer', '_tick_heartbeat')]

    def _demolition_pre(self) -> None:
        # Transport signals target bespoke slot methods on self, so
        # declare them inline rather than via the workers manifest
        # (which uses disconnect() without slot specificity).
        for sig, slot in (
            (getattr(self._transport, 'status_changed', None),   self._on_status_changed),
            (getattr(self._transport, 'message_received', None), self._on_message_received),
            (getattr(self._transport, 'handshake_ready', None),  self._on_handshake_ready),
            (getattr(self._transport, 'handshake_error', None),  self._on_handshake_error),
            (getattr(self._transport, 'pong_received', None),    self._on_pong_received),
        ):
            if sig is None:
                continue
            try: sig.disconnect(slot)
            except (RuntimeError, TypeError): pass
        try:
            self._transport.disconnect_all()
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        self.sync_data()
        return self.data.to_dict()

    @staticmethod
    def from_dict(data: dict) -> 'PremiereBridgeNode':
        return PremiereBridgeNode(PremiereBridgeNodeData.from_dict(data))

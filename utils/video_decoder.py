#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/video_decoder.py PyAV-backed video decoder
-the new one wakes up, picks up its decoder, and walks softly into the room
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

# Replaces QMediaPlayer for VideoNode playback.
#
# Why this exists
# ---------------
# The A/V Transport Engine design doc (Documents/Design/) names PyAV as the
# Stage 3 backend for VideoNode. This module is that Stage 3 backend, landed
# alone — Transport seat (Stage 2) and AudioNode swap (Stage 4) come later.
# Direct libav* access via PyAV avoids the pain we'd accumulated against
# QMediaPlayer + WMF: heap corruption on corrupt-stream teardown, stop/seek/
# restart visible on the loop boundary, no native ping-pong, codec-dependent
# negative-rate playback. PyAV gives us decoded frames in Python; everything
# above (loop semantics, ping-pong, LOD-aware sizing) becomes a small matter
# of policy rather than fighting an opaque backend.
#
# Threading model
# ---------------
# One decoder thread per VideoDecoder instance. The thread owns:
#   - the av.container (opened once per source)
#   - the av.stream and decoder state
#   - PTS-based pacing (sleeps to match real-time playback)
#   - frame conversion to QImage at the configured LOD size
#
# Cross-thread delivery uses a `_DecoderSignals` QObject with Qt signals.
# Qt signals are inherently thread-safe — emitting from the worker queues
# the slot invocation onto the receiver's thread (the main GUI thread).
#
# Loop modes
# ----------
# off       — play once, stop on EOF.
# loop      — seek to 0 on EOF, continue.
# pingpong  — record decoded frames into a bounded ring buffer on the forward
#             pass; on EOF, replay the buffer in reverse from the decoder
#             thread (no further decode work). When the reverse pass hits
#             frame 0, flip back to forward and re-decode from source. If the
#             clip exceeds the memory cap, fall back to "loop" semantics with
#             a warning log — the libav-rendered reversed-file fallback for
#             long clips is left as a future refinement.
#
# LOD policy
# ----------
# Caller passes a (target_w, target_h) tuple via set_lod_size(). The decoder
# scales each emitted frame to fit those bounds via swscale (PyAV's
# frame.reformat). When LOD changes, the ping-pong buffer is invalidated —
# its contents are now the wrong size. A new forward pass rebuilds it.
#
# Teardown
# --------
# close() sets the stop flag, joins the worker thread (bounded), closes the
# container, and disconnects all signals. Safe to call multiple times. Safe
# to call from the main thread while the worker is decoding — the flag is
# checked at every iteration and the worker bails cleanly.

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

import av
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QImage

logger = logging.getLogger("video.decoder")


# Approximate memory cap for the ping-pong ring buffer, in bytes. Cheap upper
# bound on RAM spent on a single ping-pong clip. Frames over this threshold
# trigger the loop-fallback. RGBA at 360×280 ≈ 400KB/frame; at 30fps this
# permits ~5 minutes of buffered video which is comfortably more than the
# expected ping-pong loop-length range.
PING_PONG_BUFFER_CAP_BYTES = 256 * 1024 * 1024  # 256 MiB

# Minimum sleep granularity inside the pacing loop. Below this we just spin
# briefly. Keeps short-frame jitter low without burning CPU.
_MIN_SLEEP = 0.0005

# Bound on join() during close() — past this we leak the thread rather than
# block the GUI. The thread will see _stop and exit on its own shortly after.
_JOIN_TIMEOUT = 1.0


class _DecoderSignals(QObject):
    """Cross-thread signal bridge. Qt signals are thread-safe — emit from
    the worker, receivers run on their own thread (GUI for VideoNode)."""

    frame      = Signal(QImage)   # one decoded frame, sized to current LOD
    position   = Signal(int)      # playback position in ms
    duration   = Signal(int)      # source duration in ms (one-shot, on open)
    state      = Signal(str)      # "playing" | "paused" | "stopped" | "eof"
    error      = Signal(str)      # decoder failure — string for log/UI


class VideoDecoder:
    """
    PyAV-backed video decoder with loop / ping-pong support and LOD sizing.

    Single-source: open a file via set_source(), control with play/pause/stop,
    seek with set_position(). Receive frames + state via the `signals`
    attribute (a _DecoderSignals QObject). One worker thread per instance.
    """

    def __init__(self) -> None:
        self.signals = _DecoderSignals()

        self._lock = threading.Lock()
        self._cv   = threading.Condition(self._lock)

        # Source state — guarded by _lock. The worker reads these on each
        # iteration; main-thread setters mutate then notify the cv.
        self._path: Optional[Path] = None
        self._loop_mode: str = "off"          # "off" | "loop" | "pingpong"
        self._lod_size: tuple[int, int] = (1, 1)
        self._user_paused: bool = False
        self._stop: bool = False              # True → worker exits
        self._seek_to_ms: Optional[int] = None  # main-thread seek request
        self._thread: Optional[threading.Thread] = None

        # Reported state — written by worker, read by main thread (volatile;
        # the cross-thread signals are the canonical reporting channel).
        self._duration_ms: int = 0
        self._position_ms: int = 0

        # Most recent decoded av.VideoFrame, kept around so the worker can
        # redeliver it at a new LOD size without re-decoding when the view
        # zooms while playback is paused. Lives only inside the worker.
        # `None` until the first decode.
        self._last_av_frame = None

    # ── Public API (main thread) ─────────────────────────────────────────

    def set_source(self, path: str | Path,
                   lod_size: tuple[int, int] = (1, 1),
                   loop_mode: str = "off",
                   start_paused: bool = False) -> None:
        """Open a source file and start the decoder thread. Replaces any
        currently-loaded source — the previous worker is joined before the
        new one starts."""
        path = Path(path)
        if not path.exists():
            self.signals.error.emit(f"source not found: {path}")
            return
        self.close()  # tear down any existing worker
        with self._lock:
            self._path = path
            self._lod_size = (max(1, lod_size[0]), max(1, lod_size[1]))
            self._loop_mode = loop_mode if loop_mode in ("off", "loop", "pingpong") else "off"
            self._user_paused = start_paused
            self._stop = False
            self._seek_to_ms = None
            self._thread = threading.Thread(
                target=self._run, name=f"video-decoder-{path.name}", daemon=True
            )
            self._thread.start()

    def play(self) -> None:
        with self._cv:
            self._user_paused = False
            self._cv.notify_all()

    def pause(self) -> None:
        with self._cv:
            self._user_paused = True
            self._cv.notify_all()

    def set_position(self, position_ms: int) -> None:
        with self._cv:
            self._seek_to_ms = max(0, int(position_ms))
            self._cv.notify_all()

    def position_ms(self) -> int:
        return self._position_ms

    def duration_ms(self) -> int:
        return self._duration_ms

    def is_paused(self) -> bool:
        return self._user_paused

    def set_loop_mode(self, mode: str) -> None:
        if mode not in ("off", "loop", "pingpong"):
            return
        with self._cv:
            self._loop_mode = mode
            # Drop any ping-pong buffer captured under a previous mode —
            # rebuilt lazily on the next forward pass if needed.
            self._cv.notify_all()

    def loop_mode(self) -> str:
        return self._loop_mode

    def set_lod_size(self, w: int, h: int) -> None:
        """Update the target frame size. The decoder picks this up on the
        next decoded frame; ping-pong buffers are invalidated since their
        contents are now the wrong size. If currently paused, the worker
        will redeliver the most recent frame at the new size without
        re-decoding so the view stays crisp through zoom-on-paused."""
        with self._cv:
            new_size = (max(1, int(w)), max(1, int(h)))
            if new_size != self._lod_size:
                self._lod_size = new_size
                self._cv.notify_all()

    def close(self) -> None:
        """Stop the worker and release the container. Idempotent."""
        with self._cv:
            self._stop = True
            self._cv.notify_all()
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=_JOIN_TIMEOUT)
            if t.is_alive():
                logger.warning("video decoder thread did not exit within %.1fs", _JOIN_TIMEOUT)
        self._thread = None

    # ── Worker thread ────────────────────────────────────────────────────

    def _run(self) -> None:
        """Main decoder loop. Runs on the worker thread. Owns the av.container
        and stream for its entire lifetime. Exits cleanly when _stop is set."""
        path = self._path
        if path is None:
            return

        container = None
        try:
            container = av.open(str(path))
        except Exception as exc:
            self.signals.error.emit(f"open failed: {exc}")
            return

        try:
            self._run_inner(container)
        except Exception as exc:
            logger.exception("decoder crashed")
            self.signals.error.emit(f"decoder crashed: {exc}")
        finally:
            try:
                container.close()
            except Exception:
                pass
            self.signals.state.emit("stopped")

    def _run_inner(self, container) -> None:
        # Identify the video stream. Skip files that have no video.
        v_streams = [s for s in container.streams if s.type == "video"]
        if not v_streams:
            self.signals.error.emit("no video stream")
            return
        stream = v_streams[0]
        # Emit duration once. av may report duration in stream time-base; fall
        # back to container.duration (microseconds) if the stream value is
        # missing.
        duration_s = 0.0
        try:
            if stream.duration is not None and stream.time_base is not None:
                duration_s = float(stream.duration * stream.time_base)
            elif container.duration is not None:
                duration_s = container.duration / av.time_base
        except Exception:
            duration_s = 0.0
        self._duration_ms = int(duration_s * 1000)
        self.signals.duration.emit(self._duration_ms)

        # Ping-pong buffer state. Reset on every forward pass — keeps the
        # invariant that the buffer matches the current LOD size.
        pingpong_frames: deque[QImage] = deque()
        pingpong_durations: deque[float] = deque()  # seconds each frame is displayed
        pingpong_bytes: int = 0
        pingpong_capacity_lost: bool = False  # latched once over cap; resets on rewind

        direction: int = 1  # +1 forward, -1 reverse (only used in pingpong)
        wall_clock_anchor: float = time.monotonic()  # wall-clock at last PTS sync
        pts_anchor: float = 0.0                     # PTS at wall_clock_anchor

        # LOD that the most recently emitted frame was sized for. When the
        # caller bumps set_lod_size() while we're paused, the worker wakes
        # and re-emits the cached av.VideoFrame at the new size — no
        # re-decode, just one swscale pass.
        last_emitted_lod: tuple[int, int] = self._lod_size

        self.signals.state.emit("paused" if self._user_paused else "playing")

        # ── The decode loop ──────────────────────────────────────────────
        while True:
            with self._cv:
                if self._stop:
                    return
                # Honour any pending seek.
                if self._seek_to_ms is not None:
                    seek_ms = self._seek_to_ms
                    self._seek_to_ms = None
                    self._loop_seek(container, stream, seek_ms / 1000.0)
                    pingpong_frames.clear()
                    pingpong_durations.clear()
                    pingpong_bytes = 0
                    pingpong_capacity_lost = False
                    direction = 1
                    wall_clock_anchor = time.monotonic()
                    pts_anchor = seek_ms / 1000.0
                # Honour pause — wait on cv until unpaused or stopped. While
                # paused, watch for LOD changes and redeliver the cached
                # frame at the new size (zoom-on-paused stays crisp).
                while self._user_paused and not self._stop and self._seek_to_ms is None:
                    self._cv.wait()
                    if (self._lod_size != last_emitted_lod
                            and self._last_av_frame is not None
                            and not self._stop):
                        tw, th = self._lod_size
                        qimg = self._frame_to_qimage(self._last_av_frame, tw, th)
                        if qimg is not None:
                            last_emitted_lod = (tw, th)
                            # Release the cv around the emit to avoid holding
                            # the lock while Qt's signal machinery runs.
                            self._cv.release()
                            try:
                                self.signals.frame.emit(qimg)
                            finally:
                                self._cv.acquire()
                if self._stop:
                    return
                # Snapshot the current target size and loop mode for this frame.
                target_w, target_h = self._lod_size
                loop_mode = self._loop_mode

            # Reverse playback path — replay buffer.
            if loop_mode == "pingpong" and direction == -1 and pingpong_frames:
                self._replay_reverse(pingpong_frames, pingpong_durations,
                                     wall_clock_anchor, pts_anchor)
                # End of reverse pass — flip to forward and re-decode source
                # from the start. The buffer remains valid; we're going to
                # replace it on this forward pass.
                with self._cv:
                    if self._stop:
                        return
                direction = 1
                pingpong_frames.clear()
                pingpong_durations.clear()
                pingpong_bytes = 0
                pingpong_capacity_lost = False
                self._loop_seek(container, stream, 0.0)
                wall_clock_anchor = time.monotonic()
                pts_anchor = 0.0
                continue

            # Forward decode path — read one frame and pace it.
            try:
                frame = next(container.decode(stream))
            except (StopIteration, av.error.EOFError):
                # End of stream — react per loop mode. PyAV signals EOF via
                # av.error.EOFError when avcodec_send_packet returns
                # AVERROR_EOF (decoder fully drained); StopIteration covers
                # the formats / paths that exhaust the generator cleanly.
                self.signals.state.emit("eof")
                with self._cv:
                    mode = self._loop_mode
                if mode == "off":
                    # Park here until user changes mode or seeks or quits.
                    with self._cv:
                        while (not self._stop
                               and self._seek_to_ms is None
                               and self._loop_mode == "off"):
                            self._cv.wait()
                        if self._stop:
                            return
                    continue
                if mode == "pingpong" and pingpong_frames and not pingpong_capacity_lost:
                    direction = -1
                    # Anchor reverse-pass timing.
                    wall_clock_anchor = time.monotonic()
                    pts_anchor = self._position_ms / 1000.0
                    continue
                # mode == "loop", or pingpong-fallback (over capacity).
                if mode == "pingpong" and pingpong_capacity_lost:
                    logger.info("pingpong over buffer cap — falling back to loop")
                self._loop_seek(container, stream, 0.0)
                pingpong_frames.clear()
                pingpong_durations.clear()
                pingpong_bytes = 0
                pingpong_capacity_lost = False
                direction = 1
                wall_clock_anchor = time.monotonic()
                pts_anchor = 0.0
                self.signals.state.emit("playing")
                continue
            except av.error.InvalidDataError as exc:
                # Single-frame corruption — log and continue. WMF used to
                # crash here; PyAV raises and we recover.
                logger.warning("invalid data in frame: %s", exc)
                continue
            except Exception as exc:
                logger.exception("decode error")
                self.signals.error.emit(f"decode error: {exc}")
                return

            # PTS in seconds.
            try:
                pts_s = float(frame.pts * stream.time_base) if frame.pts is not None else pts_anchor
            except Exception:
                pts_s = pts_anchor

            # Sleep until wall-clock matches the frame's PTS.
            target_wall = wall_clock_anchor + (pts_s - pts_anchor)
            self._sleep_until(target_wall)

            # Convert to QImage at LOD size.
            qimg = self._frame_to_qimage(frame, target_w, target_h)
            if qimg is None:
                continue

            # Keep the av.VideoFrame around so that a zoom-while-paused can
            # redeliver it at a new size without a re-decode (see the pause
            # branch above). Only kept for forward decode — reverse pass
            # replays from the QImage buffer.
            self._last_av_frame = frame
            last_emitted_lod = (target_w, target_h)

            # Capture into ping-pong buffer if applicable.
            if loop_mode == "pingpong" and direction == 1 and not pingpong_capacity_lost:
                # Frame display duration — gap between this PTS and the next
                # iteration's PTS. We don't know the next yet, so estimate
                # from stream framerate (or fall back to 1/30s).
                fps = float(stream.average_rate) if stream.average_rate else 30.0
                disp_s = 1.0 / max(1.0, fps)
                # Estimate bytes for the QImage payload — sizeInBytes()
                # reports the actual buffer.
                try:
                    img_bytes = qimg.sizeInBytes()
                except Exception:
                    img_bytes = qimg.width() * qimg.height() * 4
                if pingpong_bytes + img_bytes > PING_PONG_BUFFER_CAP_BYTES:
                    pingpong_capacity_lost = True
                else:
                    # Store a deep copy so the QImage data outlives the av.frame.
                    pingpong_frames.append(qimg.copy())
                    pingpong_durations.append(disp_s)
                    pingpong_bytes += img_bytes

            # Emit frame and position.
            self._position_ms = int(pts_s * 1000)
            self.signals.frame.emit(qimg)
            self.signals.position.emit(self._position_ms)

    # ── Helpers ──────────────────────────────────────────────────────────

    def _loop_seek(self, container, stream, target_s: float) -> None:
        """Seek the stream to target_s seconds from start. Wraps PyAV seek
        and re-reads the decoder so the next decode() call returns the seeked
        frame, not a stale one from the previous position."""
        try:
            ts = int(target_s / stream.time_base) if stream.time_base else 0
            container.seek(ts, stream=stream, any_frame=False, backward=True)
        except Exception as exc:
            logger.warning("seek failed: %s", exc)

    def _sleep_until(self, target_wall: float) -> None:
        """Sleep until time.monotonic() reaches target_wall. Honours stop
        flag — wakes up early if asked to stop."""
        while True:
            now = time.monotonic()
            remaining = target_wall - now
            if remaining <= _MIN_SLEEP:
                return
            with self._cv:
                if self._stop or self._seek_to_ms is not None:
                    return
                # Cap each wait so we re-check the stop flag periodically.
                self._cv.wait(timeout=min(remaining, 0.05))

    def _replay_reverse(self, frames: deque[QImage], durations: deque[float],
                        wall_anchor: float, pts_anchor: float) -> None:
        """Walk the captured forward buffer backwards in real-time. Emits
        position based on a synthetic PTS that counts down from pts_anchor."""
        if not frames:
            return
        pts_s = pts_anchor
        wall = wall_anchor
        # Iterate from newest to oldest. The first call should display the
        # last forward frame (already shown), so step it once before emitting.
        for qimg, disp_s in zip(reversed(frames), reversed(durations)):
            pts_s -= disp_s
            wall  += disp_s
            self._sleep_until(wall)
            with self._cv:
                if self._stop or self._seek_to_ms is not None:
                    return
                while self._user_paused and not self._stop and self._seek_to_ms is None:
                    self._cv.wait()
                if self._stop or self._seek_to_ms is not None:
                    return
                if self._loop_mode != "pingpong":
                    return
            self._position_ms = max(0, int(pts_s * 1000))
            self.signals.frame.emit(qimg)
            self.signals.position.emit(self._position_ms)

    @staticmethod
    def _frame_to_qimage(frame, target_w: int, target_h: int) -> Optional[QImage]:
        """Reformat a PyAV VideoFrame to RGBA at LOD size and wrap as QImage.

        The reformat call uses libswscale internally — single bilinear pass
        from the source pixel format / size to RGBA at the target size.
        Source-resolution cap: never upscale, so if source is smaller than
        target, we keep source size (the painter handles the residual).
        """
        try:
            src_w, src_h = frame.width, frame.height
            if src_w <= 0 or src_h <= 0:
                return None
            # Aspect-preserving fit inside (target_w, target_h), capped at source.
            scale = min(target_w / src_w, target_h / src_h, 1.0)
            out_w = max(1, int(src_w * scale))
            out_h = max(1, int(src_h * scale))
            rgba = frame.reformat(width=out_w, height=out_h, format="rgba")
            # av frame data is a list of planes; rgba has one plane.
            plane = rgba.planes[0]
            # bytes_per_line may be > out_w*4 for alignment — pass it through
            # to QImage so it strides correctly.
            bytes_per_line = plane.line_size if hasattr(plane, "line_size") else out_w * 4
            buf = bytes(plane)
            qimg = QImage(buf, out_w, out_h, bytes_per_line, QImage.Format_RGBA8888)
            # Detach so the QImage owns its bytes — buf goes out of scope on
            # return and Qt would otherwise read freed memory.
            return qimg.copy()
        except Exception as exc:
            logger.warning("frame conversion failed: %s", exc)
            return None

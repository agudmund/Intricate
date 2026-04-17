# The Premiere Bridge Node

A live wire between Intricate's canvas and Adobe Premiere Pro's timeline. Drop the node, click 👋, and a packet travels across a WebSocket, lands inside Premiere's CEP panel, gets routed through ExtendScript, and surfaces as a toast in Premiere's Events panel — with an ACK flowing back the other way, all inside a few milliseconds.

The node is deliberately small in Phase 1: one button, one wire, one ping. The architecture under it is sized for everything that comes next — handshake, heartbeat, keyframe injection, and eventually BezierNode curves streaming directly into Motion/Opacity property tracks on a selected clip.

## What It Does

Phase 1 fires a single `TXT|Hello 👋|0|0` packet across a localhost WebSocket when you click the 👋 emoji button. The receiver inside Premiere (a CEP extension) echoes the payload to both `$.writeln` (ExtendScript console) and `app.setSDKEventMessage` (the Events panel toast), then sends an `ACK|TXT` back down the wire. Intricate's node dot flips pink on connect and the readout shows the last ACK received.

That's it. No keyframes yet, no handshake, no heartbeat. The point of Phase 1 is to prove the wire exists and both ends can talk.

## The Packet Format

Every transport speaks the same frame:

```
Prop|Val|Track|Clip
```

- **Prop** — what property we're touching (`TXT` for ping, `Scale`, `Position`, `Opacity`, etc.)
- **Val** — the value (string for TXT, number for most others)
- **Track** — which video/audio track (0-indexed)
- **Clip** — which clip on that track (0-indexed)

This format is transport-agnostic by design. Phase 2b swaps the WebSocket for a Serial transport over a `com0com` virtual pair without touching the packet format — the abstraction lives in `utils/premiere_transport.py` as `PacketTransport(QObject)` with `WebSocketTransport` as the current implementation and `SerialTransport` reserved.

## Status Dot Colours

The node status dot shares the progress-bar gradient vocabulary, so the visual language stays consistent with the joy bar and playback scrub:

- **`#5c3e4f` deep rose** — disconnected. Panel not open, or Premiere not running.
- **`#a56a85` warm mauve** — connecting. Reconnect timer trying every 2.5s.
- **`#d87a9e` bright pink** — connected. Packets flowing.
- **`#e27c7c` warm red** — error. Rare; see the CEP log for detail.

The CEP panel's own status dot on the Premiere side uses the same palette, so "is the wire up" is readable from either end at a glance.

## The 👋 Button

Slot 1 on the button strip, right after the accent emoji. Implemented as an `EmojiButton` with the 👋 glyph baked in as the `get_emoji` callback and the fire-the-packet action wired to `set_emoji` (we ignore the new emoji value — the click itself is the trigger). A tooltip of "Ping Premiere — send Hello 👋 down the wire" appears on hover.

If the wire is down when the button is clicked, the node updates its readout to `not connected (<status>)` rather than silently dropping. This is the informative-failure principle — the node tells you what didn't work and why.

## The Transport Layer

`utils/premiere_transport.py` holds the whole wire abstraction.

**`PacketTransport(QObject)`** — abstract base with two signals:
- `status_changed(str)` — one of `STATUS_DISCONNECTED`, `STATUS_CONNECTING`, `STATUS_CONNECTED`, `STATUS_ERROR`
- `message_received(str)` — raw text frame from the receiver

And three abstract methods: `open()`, `close()`, `send_raw(line) -> bool`.

A concrete `send_packet(prop, val, track, clip)` lives on the base and formats the `Prop|Val|Track|Clip` frame before delegating to `send_raw`.

**`WebSocketTransport(PacketTransport)`** — wraps a `QWebSocket` targeting `ws://127.0.0.1:9914`. Auto-reconnects every 2.5s while `_want_open` is true, so if Premiere isn't up when Intricate opens the wire, the bridge silently attaches the moment the CEP panel comes online. `disconnect_all()` severs every signal — called from the node's `_prepare_for_removal()` to avoid reference cycles.

## The CEP Receiver (Premiere side)

The Premiere side is an unsigned (well, self-signed) CEP extension living at:

```
%APPDATA%\Adobe\CEP\extensions\com.intricate.bridge\
├── CSXS\manifest.xml              — Premiere sees this, registers the panel
├── index.html                     — panel UI + Node.js WebSocket server
├── script.jsx                     — ExtendScript side, runs inside Premiere's JS engine
├── lib\CSInterface.js             — Adobe's JS↔ExtendScript bridge
├── node_modules\ws\               — pure-JS WebSocket library
├── mimetype
└── META-INF\signatures.xml        — self-signed signature (Phase 1's unplanned sidequest)
```

`index.html` boots a `WebSocketServer` on `127.0.0.1:9914` inside Premiere's Node.js runtime (enabled via the manifest's `--enable-nodejs --mixed-context --no-sandbox` flags). On receiving a packet, `routePacket()` splits on `|`, extracts the `Prop`, and for `TXT`/`PING` calls `csInterface.evalScript('consoleLog("' + payload + '")')` to hand execution to ExtendScript.

`script.jsx` defines `consoleLog(msg)` which calls both `$.writeln("[Intricate] " + msg)` (goes to the ExtendScript Toolkit console if attached) and `app.setSDKEventMessage("[Intricate] " + msg, "info")` (surfaces in Premiere's own Events panel, `Window → Events`). It also defines a reserved-for-Phase-2 `validateAndGetFPS(projectName, sequenceName)` stub that does project + sequence validation and returns the sequence FPS computed from `seq.getSettings().videoFrameRate.ticks / 254016000000`.

## The Signing Step

Premiere Pro 2026 / CEP 12 hardened its extension loader: `PlayerDebugMode=1` in `HKCU\Software\Adobe\CSXS.12` gets the menu entry under `Window → Extensions` to appear, but the panel still fails to instantiate with `"Signature verification failed"` in `%LOCALAPPDATA%\Temp\CEP12-PPRO.log` if the extension is truly unsigned. Self-signed is fine.

**To rebuild from scratch:**

1. Download `ZXPSignCmd.exe` from `Adobe-CEP/CEP-Resources` on GitHub (`/ZXPSignCMD/4.1.1/win64/`).
2. Generate a self-signed cert:
   ```
   ZXPSignCmd -selfSignedCert US CA "Intricate" "Aevar" <password> intricate_dev.p12
   ```
3. Sign the extension folder to a `.zxp`:
   ```
   ZXPSignCmd -sign <extensionDir> intricate_bridge.zxp intricate_dev.p12 <password>
   ```
4. The `.zxp` is a signed zip — extract it back over the extension directory. This adds the `META-INF/signatures.xml` file alongside the existing code.
5. Verify: `ZXPSignCmd -verify <extensionDir>` should return `Signature verified successfully`.

**Critical:** keep the `.p12`, the `.zxp`, and `ZXPSignCmd.exe` itself **outside** the `extensions/` folder, otherwise CEP will hash them as part of the extension and reject the signature. The current dev-machine tooling lives at `%APPDATA%\Adobe\CEP\_intricate_signing\`.

## First Light

Working end-to-end on **Friday 2026-04-17, 06:54 Reykjavik**. The CEP panel log at that moment:

```
06:53:46  WebSocket server up
06:53:47  client connected
06:54:02  ← TXT|Hello 👋|0|0
06:54:02  jsx → OK
```

Simultaneously the Premiere Events panel popped `[Intricate] Hello 👋|0|0` as a toast and the Intricate node's readout flipped to `last: ACK|TXT`. Closed loop, both directions, exactly the milestone criterion set at session start: *"a node inside of intricate that echoes into premiere console output 'Hello 👋', just a ping to confirm its connected."*

## Serialization

The node persists only the wire target and clip address — connection status is runtime-only and re-establishes itself on load.

```python
@dataclass
class PremiereBridgeNodeData(NodeData):
    node_type: str = "premiere_bridge"
    host: str = "127.0.0.1"
    port: int = 9914
    target_track: int = 0
    target_clip:  int = 0
```

Phase 2+ will likely add handshake state cache, last-known FPS, and expected project/sequence names for validation on reconnect.

## Known Leaks

- **The toast trailing** — `routePacket` in `index.html` rejoins everything after `parts[0]` with `|`, so the toast reads `Hello 👋|0|0` instead of just `Hello 👋`. The rejoin is defensive against payloads containing pipes, but noisy for simple `TXT`. Two-line fix deferred to Phase 2.
- **No heartbeat** — if Premiere crashes or the panel is closed mid-session, Intricate's status dot will stay pink until the next packet attempt discovers the wire is dead. Fine for Phase 1, formalized in Phase 2's handshake step.

## Phase 2 Trajectory

Ordered by dependency:

1. **Packet cleanup in `routePacket`** — fix the `|0|0` trailing bleed on `TXT`.
2. **Handshake + heartbeat** — on `connected`, Intricate sends `HELLO|<expectedProject>|<expectedSequence>`; CEP calls `validateAndGetFPS` (already stubbed in `script.jsx`) and returns `READY|<fps>|<project>|<sequence>` or `ERROR|<reason>`. 5-second heartbeat pings detect silent disconnects.
3. **Keyframe injection — Motion / Opacity** — CEP reads `Scale|120|0|0` → `seq.videoTracks[track].clips[clip].components[1].properties["Scale"].setValueAtKey(...)`. The first real payload; the moment the bridge stops being a ping and starts being useful.
4. **Serial transport swap (Phase 2b)** — `SerialTransport(PacketTransport)` using `QtSerialPort` against a `com0com` virtual pair. Zero node-side changes if the abstraction is sound. Aligns with Adobe's paid-SDK security posture for IP compliance.
5. **ACK throttling** — per-packet ACK is fine at click rates; 60Hz keyframe streams need batched or heartbeat-only ACK.
6. **BezierNode → Premiere keyframe track** — the destination. Design a curve spatially in Intricate, stream it into Premiere as an interpolated Motion/Opacity keyframe sequence on the selected clip. The Lyria-equivalent first-contact moment for the Adobe branch of the family.

## Technical Notes

- **Transport parent** — `WebSocketTransport` is constructed with `parent=None` because `QGraphicsRectItem` (the BaseNode base class) is not a `QObject` and cannot parent one. Lifetime is managed by explicit `disconnect_all()` in `_prepare_for_removal()`.
- **Reconnect cadence** — 2500ms via a `QTimer`. Fast enough that "open Premiere after Intricate" feels instant, slow enough that the reconnect doesn't flood the log with connecting/failed cycles when the panel is genuinely offline.
- **Signal teardown** — `_prepare_for_removal()` severs `status_changed` and `message_received` from the transport, then calls `transport.disconnect_all()` which also stops the reconnect timer and closes the underlying `QWebSocket`.
- **Packet encoding** — `QWebSocket.sendTextMessage` sends the frame as UTF-8 by default; the 👋 emoji survives the wire intact (confirmed at first light).
- **CEP manifest host range** — `<Host Name="PPRO" Version="[24.0,99.9]" />` gives headroom for future Premiere versions without needing a manifest edit every year.
- **ExtendScript event surface** — `app.setSDKEventMessage(msg, "info")` is the visible channel. `$.writeln(msg)` only surfaces if the ExtendScript Toolkit debugger is attached, which is a developer-only setup. The bridge uses both so the message shows up regardless of debug state.

## File Map

| File | Role |
|---|---|
| `nodes/PremiereBridgeNode.py` | Qt-side node, button, paint, lifecycle |
| `data/PremiereBridgeNodeData.py` | Pure-Python dataclass, serialization |
| `utils/premiere_transport.py` | `PacketTransport` ABC + `WebSocketTransport` |
| `icons/premiere_bridge.ico` | Cream suspension-bridge silhouette |
| `icons/make_premiere_bridge_icon.py` | Pillow recipe that generated the icon |
| `Documents/Claude Plans/Premiere Bridge Phase 1.md` | The session plan + first-light addendum |
| `%APPDATA%\Adobe\CEP\extensions\com.intricate.bridge\` | CEP receiver (outside repo) |
| `%APPDATA%\Adobe\CEP\_intricate_signing\` | ZXPSignCmd + self-signed cert (outside repo) |

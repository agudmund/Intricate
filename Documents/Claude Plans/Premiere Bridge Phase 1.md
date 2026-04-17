# Premiere Bridge — Phase 1

**Milestone:** Click "Ping 👋" in an Intricate `PremiereBridgeNode`, see `"[Intricate] Hello 👋"` in Premiere's CEP panel log and ExtendScript console.

**Background:** Live Gemini planning session archived in `Documents/data/_transcript.txt` (linearized from `session.intricate`). The full SDK architecture lives there: CEP manifest flags, ExtendScript keyframe injection, handshake + heartbeat, property ID cheat sheet, no-undo buffer trick.

---

## Architecture

```
┌──────────────────────────────┐        ┌──────────────────────────────┐
│ Intricate (PySide6)          │        │ Premiere CEP panel           │
│                              │        │                              │
│  PremiereBridgeNode          │        │  index.html (Node host)      │
│    └─ WebSocketTransport ────┼── ws:// ┼─→ ws server on 127.0.0.1    │
│       (serial swap later)    │  9914  │   │                          │
│                              │        │   ▼                          │
│                              │        │  csInterface.evalScript      │
│                              │        │   │                          │
│                              │        │   ▼                          │
│                              │        │  script.jsx consoleLog()     │
│                              │        │   └→ $.writeln               │
└──────────────────────────────┘        └──────────────────────────────┘
```

**Packet format** (same for WS now and serial later): `Prop|Val|Track|Clip`
- Phase 1 ping: `TXT|Hello 👋|0|0`
- Later: `Scale|120|0|0`, `Position|0.5|0.5|0|0`, `rot|45|0|0`, etc.

---

## Transport Decision

Phase 1 uses **WebSocket on `ws://127.0.0.1:9914`**. Reasoning:
- No admin install needed (com0com driver dance deferred)
- CEP Node side uses pure-JS `ws` package — no `@electron/rebuild` against Premiere's ABI
- PySide6's `QtWebSockets.QWebSocket` on Intricate side — no extra pip
- Packet format is transport-agnostic, so serial swap later is a single `PacketTransport` subclass

Serial (via `com0com` virtual null-modem pair) is **Phase 2b** — once we've proven the wire and the injection loop, we switch transports to align with Adobe's paid-SDK security story and the physical-hardware future.

---

## Preflight (one-time machine setup)

| Item | Action |
|---|---|
| **Node.js LTS** | Download MSI → install (UAC) — needed for `npm install ws` |
| **CEP extensions folder** | Auto-created at `%APPDATA%\Adobe\CEP\extensions\com.intricate.bridge\` |
| **PlayerDebugMode** | Set `HKCU\Software\Adobe\CSXS.11\PlayerDebugMode = "1"` and same for `CSXS.12` |
| **Premiere 2026** | Already installed |
| **PySide6.QtSerialPort** | Already installed (not used Phase 1, reserved for Phase 2b) |

---

## Step-by-Step

### A — CEP Receiver (Premiere side)

1. Create `%APPDATA%\Adobe\CEP\extensions\com.intricate.bridge\`
2. Write `CSXS/manifest.xml`
   - `<Host Name="PPRO" Version="[26.0,29.9]">`
   - CEP 12.0, AutoVisible, Panel UI 420×300
   - `--enable-nodejs --mixed-context --no-sandbox`
3. Download `lib/CSInterface.js` from Adobe's official CEP repo
4. Write `index.html`
   - Minimal dark UI: status dot + rolling log
   - Node `require('ws')` → `WebSocket.Server` on port 9914
   - On message: parse packet, route `TXT` → `csInterface.evalScript(\`consoleLog("\${msg}")\`)`
5. Write `script.jsx`
   - `function consoleLog(msg) { $.writeln("[Intricate] " + msg); }`
6. `npm init -y && npm install ws` in the extension folder
7. Set registry `PlayerDebugMode=1` for CSXS.11 and CSXS.12
8. Launch Premiere → `Window > Extensions > Intricate Bridge` → panel should appear

### B — Intricate Sender (PremiereBridgeNode)

1. `data/PremiereBridgeNodeData.py` — dataclass
   - `host: str = "127.0.0.1"`
   - `port: int = 9914`
   - `target_track: int = 0`
   - `target_clip: int = 0`
   - `last_status: str = "disconnected"`
2. `utils/premiere_transport.py` — abstraction
   - `PacketTransport` ABC: `open()`, `close()`, `send_packet(prop, val, track, clip)`, `is_connected → bool`, `connected_changed` signal
   - `WebSocketTransport(PacketTransport)` wraps `QWebSocket`
   - `SerialTransport(PacketTransport)` — stub for Phase 2b
3. `nodes/PremiereBridgeNode.py`
   - Subclass `BaseNode`
   - One prominent **Ping 👋** button (emoji-family)
   - Status dot in header (grey / yellow / green)
   - `paint_content` draws status line + target address
4. Icon: Pillow recipe → `icons/premiere_bridge.png/.ico` (bridge silhouette, cream on transparent, outer ring)
5. Register:
   - `_KNOWN_TYPES` in `utils/session.py` → `"premiere_bridge"`
   - `IntricateScene.add_premiere_bridge_node(pos)` factory
   - Sidebar button in `main_window.py`
   - `[theme.icons]` entry `premiereBridge = "premiere_bridge.ico"` in `SingleSharedBraincell_Settings.toml`

### C — End-to-end verification

1. Launch Intricate
2. Drop a `PremiereBridgeNode` on canvas
3. Launch Premiere, open Intricate Bridge panel
4. Click "Ping 👋"
5. Confirm:
   - Intricate node status dot goes green
   - CEP panel log reads: `Received: TXT|Hello 👋|0|0`
   - ExtendScript console shows: `[Intricate] Hello 👋`

---

## Phase 1 exit criteria

- [x] Plan archived
- [x] Node.js installed
- [x] CEP extension scaffolded, panel visible in Premiere
- [x] `PremiereBridgeNode` renders and pings
- [x] Ping reaches Premiere console end-to-end

When those five are checked, Phase 1 is complete and we move to Phase 2: actual keyframe injection against Motion/Opacity components.

---

## First Light — achieved 2026-04-17 06:54 Reykjavik

End-to-end working. Observed trace from the CEP panel log at the moment of first light:

```
06:53:46  WebSocket server up
06:53:47  client connected                    ← Intricate's WebSocketTransport latched on
06:54:02  ← TXT|Hello 👋|0|0                   ← packet arrived from 👋 button
06:54:02  jsx → OK                             ← evalScript round-trip returned
```

Simultaneously in Premiere:
- **Events panel toast:** `[Intricate] Hello 👋|0|0`
- **ExtendScript console:** `[Intricate] Hello 👋|0|0` (via `$.writeln`)

And in Intricate:
- Node dot flipped from mauve (`#a56a85` connecting) to bright pink (`#d87a9e` connected)
- `last: ACK|TXT` appeared in the node's paint readout

Full closed loop: Intricate → WS → CEP JS → evalScript → ExtendScript → Events toast → jsx return → ACK → Intricate.

### CEP 12 signing — unplanned extra step

The original plan assumed `PlayerDebugMode=1` was sufficient. **It isn't on Premiere Pro 2026 / CEP 12.** The menu entry appears under `Window → Extensions`, but clicking it silently fails with `"Signature verification failed for extension com.intricate.bridge.panel"` in `%LOCALAPPDATA%\Temp\CEP12-PPRO.log`.

Adobe's docs are slightly behind reality here. In CEP 12, the extension must carry *some* signature — self-signed is fine under `PlayerDebugMode=1`, but truly unsigned is rejected.

**Fix (one-time, for future rebuilds):**

1. Download `ZXPSignCmd.exe` from `Adobe-CEP/CEP-Resources/ZXPSignCMD/4.1.1/win64/` (same provenance as `CSInterface.js`).
2. Create self-signed cert: `ZXPSignCmd -selfSignedCert US CA "Intricate" "Aevar" <password> intricate_dev.p12`
3. Sign the extension folder to a `.zxp`: `ZXPSignCmd -sign <extensionDir> intricate_bridge.zxp intricate_dev.p12 <password>`
4. The `.zxp` is a signed zip — extract it back over the extension directory. This adds `META-INF/signatures.xml`.
5. Verify: `ZXPSignCmd -verify <extensionDir>` → `Signature verified successfully`.

**Critical:** keep the `.p12`, the `.zxp`, and `ZXPSignCmd.exe` **outside** the `extensions/` scan path, otherwise they'll be included in the hash manifest and the verifier will reject stale state. Current home: `%APPDATA%\Adobe\CEP\_intricate_signing\`.

### Known Phase 1 leaks (deferred, not blockers)

- `routePacket` in `index.html` rejoins all `parts[1:]` with `|`, so the Events toast shows the full tail `Hello 👋|0|0` instead of just `Hello 👋`. Defensive against pipes in payload, but noisy. Two-line fix in Phase 2.
- No heartbeat yet — if Premiere crashes mid-session, Intricate's status dot will lag until the next packet attempt. Fine for Phase 1, formalized in Phase 2's handshake.

---

## Phase 2 roadmap (for the next session)

Ordered by dependency, not priority:

1. **Packet cleanup in `routePacket`** — extract `Val` as `parts[1]` for TXT, keep the full rejoin only for packet types that legitimately carry pipes.
2. **Handshake + heartbeat** — on `connected`, Intricate sends `HELLO|<expectedProject>|<expectedSequence>`; CEP calls `validateAndGetFPS` (already stubbed in `script.jsx` line 29) and returns `READY|<fps>|<project>|<sequence>` or `ERROR|…`. Ping every 5s to detect silent disconnects.
3. **Keyframe injection — Motion/Opacity** — CEP side reads packet `Scale|120|0|0` → `seq.videoTracks[track].clips[clip].components[1].properties["Scale"].setValueAtKey(...)`. Property ID cheat sheet in `_transcript.txt`.
4. **Serial transport swap (Phase 2b)** — `SerialTransport(PacketTransport)` using `QtSerialPort` against a `com0com` virtual pair. Same packet format, no node-side changes. Aligns with Adobe's paid-SDK security posture for future IP compliance.
5. **ACK throttling** — per-packet ACK is fine at human-click rates, but at 60Hz keyframe streams we'd flood the log. Batched ACK or heartbeat-only ACK.

BezierNode → scale keyframe pipeline is the ultimate Phase 2 payoff: design a curve spatially in Intricate, stream it into Premiere as an interpolated keyframe track on a selected clip.

---

## Phase 2a — Packet cleanup (closed 2026-04-17 ~07:18 Reykjavik)

Small, honest fixes to the Phase 1 wire before layering the handshake on top.

- `routePacket` in `index.html` now honours the parse contract: Track/Clip are pulled from the **end** by position, Val is the middle slice rejoined with `|`. The Events toast reads `Hello 👋` instead of `Hello 👋|0|0`.
- ACK/NACK distinction introduced. TXT-echo gets `ACK|TXT|0|0`. Malformed or unknown props get `NACK|<prop>|0|0`.
- Transport's `send_raw` and the CEP receiver's logger both filter `PING|` / `PONG|` out of the debug log so heartbeat traffic doesn't flood.

---

## Phase 2b — Handshake + heartbeat (closed 2026-04-17 ~07:53 Reykjavik)

The wire is now fully instrumented. Everything below is live; canonical node writeup is `Documents/Nodes/The Premiere Bridge Node.md` — read that for anything beyond history.

**Frame vocabulary added:** `HELLO`, `READY`, `ERROR`, `PING`, `PONG` — each carries a JSON blob in the Val slot, which the parse contract supports for free because Track/Clip are positional-from-end.

**Python side (`utils/premiere_transport.py`):**
- `PacketTransport` grew three signals: `handshake_ready(dict)`, `handshake_error(str, dict)`, `pong_received(dict)`.
- `send_hello(project, sequence, …)` and `send_ping()` helpers.
- `_route_frame(line)` parses READY/ERROR/PONG JSON and emits the typed signals in addition to the raw `message_received`.

**Python side (`nodes/PremiereBridgeNode.py`):**
- State machine with transport status orthogonal to handshake state (`IDLE` / `PENDING` / `READY` / `ERROR`).
- `_HEARTBEAT_MS = 5000`, `_MISSED_PONGS_LIMIT = 3`. Three missed pongs → close + reopen socket; the 2.5s reconnect timer takes over.
- On `ERROR`, spawns a chained AboutNode (same passive-messaging pattern GitNode uses for offline guard). De-duplicated by reason code. Eight-entry `_ERROR_POETRY` dictionary in registry voice.
- Two buttons on strip: 👋 TXT echo (Phase 1 liveness), 🔄 re-fire `HELLO` on demand.
- Five-colour dot vocabulary mirroring the CEP panel — deep rose / warm mauve / bright pink / pale leaf / warm red.

**Python side (`data/PremiereBridgeNodeData.py`):**
- Maximalist field set. Persists transport target, strict-mode expectations, and the full last-known census so the paint readout survives a cold start.

**CEP side (`%APPDATA%\Adobe\CEP\extensions\com.intricate.bridge\`):**
- `script.jsx` — `_icJson(v)` hand-rolled ES3 encoder (no JSON polyfill needed), `handshakeReport(expectedProject, expectedSequence, track, clip)` returns full census, `heartbeatReport()` returns cheap liveness.
- `index.html` — `handleHello` / `handleHeartbeat` evalScript into jsx, send `READY|`/`ERROR|`/`PONG|` prefixed JSON back on the wire.

**Verified live:** pale-leaf dot on both ends, matching census readout (24.00 fps · 1280×768 · 3V/3A · "The Majestic.mp4"), ~4 ms heartbeat RTT, `ready — wire is warm` status line.

**Still untested (implementation exists, defensive paths):** strict-mode mismatch spawning AboutNode, silent-wire three-strikes, 🔄 retry round-trip.

---

## Phase 2c — Keyframe injection (next)

The real payload. Frame type `Scale|<value>|<track>|<clip>` → CEP routes to `seq.videoTracks[track].clips[clip].components[1].properties["Scale"].setValueAtKey(...)`. Property ID cheat sheet: component 1 is Motion (Scale / Position / Anchor Point / Rotation), component 0 is Opacity. Pseudocode and design notes continue in the canonical Nodes writeup.

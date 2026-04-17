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
- [ ] Node.js installed
- [ ] CEP extension scaffolded, panel visible in Premiere
- [ ] `PremiereBridgeNode` renders and pings
- [ ] Ping reaches Premiere console end-to-end

When those five are checked, Phase 1 is complete and we move to Phase 2: actual keyframe injection against Motion/Opacity components.

# The Premiere Bridge Node

A live wire between Intricate's canvas and Adobe Premiere Pro's timeline. The node owns a WebSocket client to a CEP extension running inside Premiere. Frames travel across as `Prop|Val|Track|Clip` tuples, the CEP panel routes them through ExtendScript into the open project, and the answers flow back the same wire with full project/sequence census attached.

This is the canonical writeup for the node — read **just this doc** to pick up work without replaying the session it was built in. The architecture was planned in `Documents/Claude Plans/Premiere Bridge Phase 1.md`, which still holds the original reasoning and phase-ordering; this document tracks what's built and how to keep building.

## Current Phase

| Phase | What | Status |
|---|---|---|
| 1 | Wire exists, 👋 round-trips to Premiere's Events toast | ✅ First light 2026-04-17 06:54 |
| 2a | Packet parser honest (no `|0|0` trailing), ACK/NACK distinction | ✅ 2026-04-17 ~07:18 |
| 2b | Handshake + heartbeat, full census exposure, AboutNode error chain | ✅ 2026-04-17 ~07:53 |
| 2c | **Keyframe injection — Motion / Opacity** | ⏭ Next |
| 2d | ACK throttling for 60Hz keyframe streams | later |
| 3  | Serial transport (`com0com` pair), matches Adobe's paid-SDK posture | later |
| 4  | BezierNode → Premiere Motion/Opacity keyframe track | the destination |

## What It Does (as of Phase 2b)

- Opens a WebSocket client to `ws://127.0.0.1:9914`. Auto-reconnects every 2.5s while open-wanted.
- On connect, sends a `HELLO` frame carrying a JSON blob of expectations (project / sequence / client id / protocol version).
- CEP calls `handshakeReport()` in ExtendScript, which introspects the open Premiere project and returns either a `READY` frame (full census) or an `ERROR` frame (reason + details).
- On `READY`, the node starts a 5s heartbeat (`PING` → `PONG`). Three missed pongs in a row (~15s of silence) closes the socket and spawns a "the wire went quiet" AboutNode.
- On `ERROR`, the node spawns a chained AboutNode with a poetic description + the structural tail (expected X, found Y, available sequences are …). De-duplicated by reason so clicking 🔄 without changing anything doesn't litter the canvas.
- 👋 button still sends the Phase 1 `TXT|Hello 👋|0|0` packet — pure echo, still useful as a liveness check.
- 🔄 button re-fires `HELLO` on demand — for when you've fixed a mismatch in Premiere without bouncing anything.

## The Packet Format

Every transport speaks the same frame:

```
Prop|Val|Track|Clip
```

Parse contract (honoured by every receiver, Python and JS alike):

- **Track** and **Clip** are always the **last two** fields and must parse as integers. Receivers pull them from the end by position.
- **Val** is everything between `Prop` and `Track` — rejoined with `|` so it may safely carry literal pipe characters, including embedded JSON blobs. This is what lets `HELLO|{"expectedProject":"X","expectedSequence":"Y"}|0|0` parse cleanly.
- **Prop** is the first field and should not contain `|`.

### Frame vocabulary

| Prop | Direction | Val payload | Notes |
|---|---|---|---|
| `TXT`   | Intricate → CEP | plain string | Echoes to ExtendScript console + Events toast. Phase 1 first-light frame. |
| `HELLO` | Intricate → CEP | JSON blob    | Opens handshake. See payload shape below. |
| `READY` | CEP → Intricate | JSON blob    | Handshake success. Full census. |
| `ERROR` | CEP → Intricate | JSON blob    | Handshake failure. `{ok:false, reason, details}`. |
| `PING`  | Intricate → CEP | empty        | Heartbeat request. |
| `PONG`  | CEP → Intricate | JSON blob    | Heartbeat reply. Cheap liveness census. |
| `ACK`   | CEP → Intricate | prop name    | Received-and-routed, TXT only. |
| `NACK`  | CEP → Intricate | prop name    | Received but rejected (malformed / unknown). |

Future frames (`Scale`, `Position`, `Opacity`, `LUT`, …) will all carry a numeric Val and target a specific `track`/`clip` cell.

## The Handshake — HELLO → READY | ERROR

**HELLO payload (Intricate side, maximalist-on-purpose):**

```json
{
  "expectedProject":  "Nameless",
  "expectedSequence": "Sequence 01",
  "protocolVersion":  1,
  "clientId":         "<node uuid>",
  "intricateVersion": "0.2b"
}
```

Empty `expectedProject` or `expectedSequence` means permissive — accept whatever's open. Any non-empty value flips the node into **strict mode** and a mismatch returns `ERROR|project_mismatch` (or `sequence_mismatch`). This is the casually-expose-then-apply-strictness design — permissive by default, army-discipline by opt-in.

**READY payload (CEP side, full census):**

```json
{
  "ok": true,
  "premiereVersion": "26.1",
  "project":  { "name": "...", "path": "...", "matches": true },
  "sequence": { "name": "...", "matches": true,
                "fps": 29.97, "width": 1920, "height": 1080,
                "videoTracks": 4, "audioTracks": 6,
                "endSeconds": 120.5 },
  "selectedClip": { "track": 0, "clip": 0, "name": "...",
                    "inPoint": 0.0, "outPoint": 4.2, ... } | null,
  "availableSequences": ["...", ...]
}
```

**ERROR payload:**

```json
{
  "ok": false,
  "reason": "project_mismatch" | "sequence_mismatch" | "no_project_open"
          | "no_active_sequence" | "extendscript_exception"
          | "heartbeat_exception",
  "details": { "expected": "...", "actual": "...",
               "availableSequences": [...] }
}
```

The CEP HTML side prepends `READY|` or `ERROR|` to the JSON blob based on the `ok` flag — one code path, the jsx layer owns the truth.

## The Heartbeat — PING → PONG

Once `READY` is received, a `QTimer` on the node fires `PING||0|0` every 5s. CEP calls `heartbeatReport()` and returns a tiny liveness census:

```json
{ "ok": true, "projectOpen": true, "sequenceOpen": true, "projectName": "..." }
```

The transport tracks `_last_rtt_ms` and resets `_missed_pongs` on each arrival. If three ticks pass with no pong, the node:

1. Spawns a chained AboutNode reading *"The wire was up but went quiet — three heartbeats passed without a pong. Letting go."*
2. Closes the socket (transport.close → transport.open) so the 2.5s reconnect timer takes over.
3. Next successful connect sends a fresh `HELLO`, re-establishing the census.

Dead-wire detection window: ~15s. Tunable via `_HEARTBEAT_MS` and `_MISSED_PONGS_LIMIT` at the top of `nodes/PremiereBridgeNode.py`.

## The State Machine

```
                             STATUS_DISCONNECTED
                                     │
                                     ▼  open()
                             STATUS_CONNECTING
                                     │
                                     ▼  wire up
                             STATUS_CONNECTED
                             (handshake: IDLE)
                                     │
                                     ▼  auto-send HELLO on connect
                             handshake: PENDING
                                     │
                            ┌────────┴────────┐
                            ▼                 ▼
                      handshake: READY   handshake: ERROR
                      ♥ 5s heartbeat     AboutNode chained
                            │                 │ 🔄 retry →
                            ▼ 3 missed pongs  │ back to PENDING
                      close + reopen ──────┘
```

Transport status (`disconnected` / `connecting` / `connected` / `error`) is orthogonal to handshake state (`idle` / `pending` / `ready` / `error`). The node blends them into a single human string via `_status_line()` and paints the dot colour via `_dot_color()`.

## Status Dot Colours

Shares the progress-bar gradient vocabulary so the visual language stays consistent with the joy bar and playback scrub:

- **`#5c3e4f` deep rose** — disconnected. Panel not open, or Premiere not running.
- **`#a56a85` warm mauve** — connecting. Reconnect timer trying every 2.5s.
- **`#d87a9e` bright pink** — connected, handshake not yet complete.
- **`#b8e0b0` pale leaf** — ready. Handshake complete, heartbeat active.
- **`#e27c7c` warm red** — error. Either transport error or handshake mismatch; see chained AboutNode for reason.

Both the CEP panel and the Intricate node use the same colour vocabulary, so "where are we in the lifecycle" is readable from either end at a glance.

## Buttons on the Strip

Slot layout (after the accent emoji at slot 0):

- **Slot 1 — 👋** — Fires `TXT|Hello 👋|track|clip`. Phase 1 echo, still the simplest liveness check. Tooltip: *"Ping Premiere — send Hello 👋 down the wire"*.
- **Slot 2 — 🔄** — Re-fires `HELLO`. Useful after fixing a project/sequence mismatch without bouncing the CEP panel. Tooltip: *"Re-handshake — ask Premiere what's open and validate expectations"*.

Both implemented as `EmojiButton` with the glyph in the `get_emoji` callback and the action wired to `set_emoji` (the click triggers; the new-emoji argument is discarded).

## Error Messaging — The AboutNode Chain

This is the same pattern GitNode uses for offline-failure feedback: passive messaging via a chained sticky, not a log line or toast. On any `ERROR` response (or a silent-wire timeout), the node:

1. Spawns an `AboutNode` 30px right of itself, centre-y — `pos = self.mapToScene(QPointF(r.right() + 30, r.center().y()))`.
2. Draws a `Connection` wire between the bridge node and the new AboutNode (physical, visible, not a port connection).
3. The AboutNode label carries the poetic one-liner + a structural tail.

**Error poetry dictionary** (`_ERROR_POETRY` at the top of `nodes/PremiereBridgeNode.py`). Keep new entries on-tone — registry voice, warm, anthropomorphic, slightly world-weary:

| Reason | Poetic surface |
|---|---|
| `no_project_open` | *"Premiere is awake but no project is loaded — a theatre with no play."* |
| `no_active_sequence` | *"The project's here but no sequence is on the timeline — nothing to paint on."* |
| `project_mismatch` | *"The project open in Premiere isn't the one this bridge was waiting for."* |
| `sequence_mismatch` | *"The sequence on the timeline isn't the one the bridge was listening for."* |
| `extendscript_exception` | *"Something tripped on the ExtendScript side — the engine threw before it could answer."* |
| `heartbeat_exception` | *"The heartbeat check raised on the ExtendScript side — probably transient."* |
| `wire_silent` | *"The wire was up but went quiet — three heartbeats passed without a pong. Letting go."* |
| `unknown` | *"Something's off and Premiere isn't saying what."* |

**De-duplication:** the node only spawns a fresh AboutNode when the reason code *changes*. Re-firing the same error won't add another sticky. On a successful `READY` the reason clears, so the next failure will re-spawn cleanly.

## The Transport Layer

`utils/premiere_transport.py` holds the whole wire abstraction.

**`PacketTransport(QObject)`** — abstract base with five signals:

| Signal | Emitted when |
|---|---|
| `status_changed(str)`        | Transport moves between DISCONNECTED / CONNECTING / CONNECTED / ERROR. |
| `message_received(str)`      | Every frame, raw. Node filters out structural frames. |
| `handshake_ready(dict)`      | `READY` parsed. Payload is the full census. |
| `handshake_error(str, dict)` | `ERROR` parsed. Args are (reason, details). |
| `pong_received(dict)`        | `PONG` parsed. Payload is the liveness census. |

And helpers: `send_packet(prop, val, track, clip)`, `send_hello(project, sequence, track, clip, client_id, intricate_version)`, `send_ping()`.

`_route_frame(line)` is called by subclasses on every received frame. It emits `message_received` unconditionally, then parses and emits the structured signal if the Prop matches READY/ERROR/PONG. Malformed frames are silently ignored at the structured level — the raw receiver still sees them for debugging.

**`WebSocketTransport(PacketTransport)`** — wraps a `QWebSocket` targeting `ws://127.0.0.1:9914`. Auto-reconnects every 2.5s while `_want_open` is true. `disconnect_all()` severs every signal — called from the node's `_prepare_for_removal()` to avoid reference cycles.

## The CEP Receiver (Premiere side)

Lives at `%APPDATA%\Adobe\CEP\extensions\com.intricate.bridge\`:

```
com.intricate.bridge\
├── CSXS\manifest.xml        — Premiere sees this, registers the panel
├── index.html               — panel UI + Node.js WebSocket server
├── script.jsx               — ExtendScript, runs inside Premiere's JS engine
├── lib\CSInterface.js       — Adobe's JS↔ExtendScript bridge
├── node_modules\ws\         — pure-JS WebSocket library
├── mimetype
└── META-INF\signatures.xml  — self-signed signature (mandatory on CEP 12)
```

**`index.html`** boots a `WebSocketServer` on `127.0.0.1:9914` inside Premiere's Node.js runtime (enabled via `--enable-nodejs --mixed-context --no-sandbox` in the manifest). On each frame:

- `parsePacket(line)` returns `{prop, val, track, clip}` or `null` for malformed.
- `handleHello(line, p, socket)` parses `p.val` as JSON, calls `handshakeReport(...)` via `csInterface.evalScript`, and sends `READY|<json>|0|0` or `ERROR|<json>|0|0` based on the jsx reply's `ok` flag.
- `handleHeartbeat(line, p, socket)` calls `heartbeatReport()` and sends `PONG|<json>|0|0`. Heartbeat traffic logs dimly (`.hb` CSS class) so it doesn't drown the interesting traffic.
- `TXT` follows the Phase 1 path — `consoleLog(val)` + `ACK|TXT` reply.
- Unknown props get `NACK|<prop>`.

**`script.jsx`** (ExtendScript, ES3-ish, no native JSON) defines:

- `_icJson(v)` — tiny hand-rolled JSON encoder. No polyfill needed, no extra file to hash into the signature.
- `consoleLog(msg)` — writes to `$.writeln` + `app.setSDKEventMessage` so the message surfaces regardless of debugger state.
- `handshakeReport(expectedProject, expectedSequence, track, clip)` — introspects `app.project`, `app.project.activeSequence`, iterates `availableSequences`, censuses the clip at `(track, clip)`, returns a JSON string.
- `heartbeatReport()` — cheap liveness probe. Returns `{ok, projectOpen, sequenceOpen, projectName}`.
- `_clipCensus(seq, trackIdx, clipIdx)` — helper that returns name / inPoint / outPoint / start / end / disabled, or `null` if out of range.

## The Signing Step

Premiere Pro 2026 / CEP 12 hardened its extension loader. `PlayerDebugMode=1` in `HKCU\Software\Adobe\CSXS.12` gets the menu entry to appear under `Window → Extensions`, but the panel still fails to instantiate with `"Signature verification failed"` in `%LOCALAPPDATA%\Temp\CEP12-PPRO.log` if the extension is truly unsigned. **Self-signed is fine.**

**Day-to-day iteration:** after any edit to the CEP-side files (`index.html`, `script.jsx`, `manifest.xml`, etc.) the signature is invalidated. Run `resign.ps1` in the signing folder — it clears stale `META-INF`, re-signs, extracts the fresh `.zxp` back over the extension dir, and verifies in one pass:

```
powershell -ExecutionPolicy Bypass -File %APPDATA%\Adobe\CEP\_intricate_signing\resign.ps1
```

Then close and re-open the Intricate Bridge panel from `Window → Extensions` — Premiere picks up the new code without a full app restart, and Intricate's WebSocket transport reconnects within 2.5s.

**Critical:** keep the `.p12`, the `.zxp`, and `ZXPSignCmd.exe` **outside** the `extensions/` folder — otherwise CEP hashes them as part of the extension and rejects the signature. The current dev-machine tooling lives at `%APPDATA%\Adobe\CEP\_intricate_signing\`.

**Full from-scratch rebuild** (only needed if the .p12 is lost):

1. Download `ZXPSignCmd.exe` from `Adobe-CEP/CEP-Resources/ZXPSignCMD/4.1.1/win64/`.
2. Generate self-signed cert: `ZXPSignCmd -selfSignedCert US CA "Intricate" "Aevar" <pw> intricate_dev.p12`.
3. Sign: `ZXPSignCmd -sign <extensionDir> intricate_bridge.zxp intricate_dev.p12 <pw>`.
4. Extract the `.zxp` (signed zip) back over the extension directory to add `META-INF/signatures.xml`.
5. Verify: `ZXPSignCmd -verify <extensionDir>` → `Signature verified successfully`.

`resign.ps1` automates steps 3–5. Self-contained — manually iterates zip entries (PS5 / .NET Framework 4.x lacks the `ExtractToDirectory(overwrite)` overload) and uses `--` ASCII separators throughout (PS5 reads UTF-8 without BOM as CP-1252, so em-dashes corrupt).

## Serialization

```python
@dataclass
class PremiereBridgeNodeData(NodeData):
    node_type: str = "premiere_bridge"
    # Transport target
    host: str = "127.0.0.1"
    port: int = 9914
    # Clip address
    target_track: int = 0
    target_clip:  int = 0
    # Handshake expectations — empty = permissive, non-empty = strict
    expected_project:  str = ""
    expected_sequence: str = ""
    # Last-known census (from most recent READY) — overwritten on each handshake
    last_project_path:  str   = ""
    last_fps:           float = 0.0
    last_width:         int   = 0
    last_height:        int   = 0
    last_video_tracks:  int   = 0
    last_audio_tracks:  int   = 0
    last_end_seconds:   float = 0.0
    last_clip_name:     str   = ""
    last_premiere_ver:  str   = ""
    last_handshake_at:  str   = ""   # ISO timestamp
```

The `last_*` fields are persisted so the paint readout can show meaningful state even before a fresh handshake completes — useful after reload, when the wire is briefly down, and for debugging drift between sessions.

## Testing Recipes

| Test | Setup | Expected outcome |
|---|---|---|
| Permissive handshake | Open any project + sequence in Premiere. Drop a fresh Premiere Bridge node. | Pale-leaf dot on both ends inside ~500ms. Census line populated. Log shows `HELLO expected="*"`, `→ READY`, then dim `♥ ping / pong` every 5s. |
| Strict project match | Edit session JSON → `expected_project = "YourProject"`. Reload Intricate. | Same as above if match; otherwise red dot + chained AboutNode with *"The project open in Premiere isn't the one this bridge was waiting for"* + expected/actual. |
| Strict sequence match | Same but `expected_sequence`. | Mismatch AboutNode also lists `available: Sequence 01, Sequence 02, …`. |
| 🔄 retry | Trigger a mismatch, fix it in Premiere, click 🔄. | Handshake re-fires, AboutNode stays (user dismisses), dot goes pale-leaf. |
| Silent-wire detection | While handshake is ready, close the CEP panel. | After ~15s, AboutNode reads *"The wire was up but went quiet — three heartbeats passed without a pong. Letting go."* Reconnect timer takes over. |

## First Light (historical)

Phase 1 round-trip achieved **Friday 2026-04-17 06:54 Reykjavik**. CEP panel log at that moment:

```
06:53:46  WebSocket server up
06:53:47  client connected
06:54:02  ← TXT|Hello 👋|0|0
06:54:02  jsx → OK
```

Simultaneously the Premiere Events panel popped `[Intricate] Hello 👋|0|0` as a toast, node dot flipped pink, readout showed `last: ACK|TXT`. Phase 1 milestone criterion met: *"a node inside of intricate that echoes into premiere console output 'Hello 👋', just a ping to confirm its connected."*

## Next Step — Phase 2c (Keyframe injection)

The bridge is now fully instrumented. The next frame type to wire up is `Scale|<value>|<track>|<clip>` — the first *real* payload that actually changes something in Premiere. Pseudocode on the jsx side:

```javascript
function setScaleKey(track, clip, value) {
    var seq = app.project.activeSequence;
    var c   = seq.videoTracks[track].clips[clip];
    var motion = c.components[1];               // Motion component is index 1
    var scaleProp = motion.properties["Scale"];
    scaleProp.setValueAtKey(seq.getPlayerPosition(), value, true);
}
```

The node side: new button (or direct wire from a ValueNode / BezierNode port) that calls `self._transport.send_packet("Scale", value, track, clip)`. CEP's `index.html` gets a new handler block alongside `handleHello` / `handleHeartbeat` that routes property frames into the appropriate jsx call.

Property ID cheat sheet (from the Gemini planning session, in `_transcript.txt`): component index 1 is Motion (Scale, Position, Anchor Point, Rotation); index 0 is Opacity. Property names are exact strings.

## Technical Notes

- **Transport parent** — `WebSocketTransport` is constructed with `parent=None` because `QGraphicsRectItem` (the BaseNode base class) is not a `QObject` and cannot parent one. Lifetime managed by explicit `disconnect_all()` in `_prepare_for_removal()`.
- **Reconnect cadence** — 2500ms via a `QTimer`. Fast enough that "open Premiere after Intricate" feels instant, slow enough that the reconnect doesn't flood the log when Premiere is genuinely offline.
- **Signal teardown** — `_prepare_for_removal()` severs all five transport signals (status_changed, message_received, handshake_ready, handshake_error, pong_received) plus the heartbeat timer's timeout, then calls `transport.disconnect_all()`. All five signal connections must be severed individually — Qt's C++ side keeps them alive past `.stop()` otherwise.
- **Packet encoding** — `QWebSocket.sendTextMessage` sends the frame as UTF-8 by default; the 👋 emoji survives the wire intact. JSON blobs with embedded pipes are tolerated by both sides' parsers because Track/Clip are pulled from the end by position, not by split count.
- **CEP manifest host range** — `<Host Name="PPRO" Version="[24.0,99.9]" />` gives headroom for future Premiere versions without a manifest edit every year.
- **ExtendScript event surface** — `app.setSDKEventMessage(msg, "info")` is the visible channel. `$.writeln(msg)` only surfaces with the ExtendScript Toolkit debugger attached. The bridge uses both so messages show up regardless of debug state.
- **Heartbeat first-tick guard** — `_tick_heartbeat` checks `if self._ping_sent_at` before counting a miss, so the very first tick (when no ping has been sent yet) doesn't spuriously increment `_missed_pongs`.

## File Map

| File | Role |
|---|---|
| `nodes/PremiereBridgeNode.py` | Qt-side node. State machine, heartbeat timer, AboutNode spawn, paint. |
| `data/PremiereBridgeNodeData.py` | Pure-Python dataclass. Transport target, expectations, last-known census. |
| `utils/premiere_transport.py` | `PacketTransport` ABC + `WebSocketTransport` + frame routing. |
| `icons/premiere_bridge.ico` | Cream suspension-bridge silhouette. |
| `icons/make_premiere_bridge_icon.py` | Pillow recipe that generated the icon. |
| `Documents/Claude Plans/Premiere Bridge Phase 1.md` | Session plan + first-light + 2a/2b addendum. |
| `%APPDATA%\Adobe\CEP\extensions\com.intricate.bridge\index.html`  | CEP panel UI + WebSocket server (outside repo). |
| `%APPDATA%\Adobe\CEP\extensions\com.intricate.bridge\script.jsx`  | ExtendScript (outside repo). |
| `%APPDATA%\Adobe\CEP\extensions\com.intricate.bridge\CSXS\manifest.xml` | Panel registration (outside repo). |
| `%APPDATA%\Adobe\CEP\_intricate_signing\resign.ps1` | One-command re-sign after CEP edits (outside repo). |
| `%APPDATA%\Adobe\CEP\_intricate_signing\intricate_dev.p12` | Self-signed cert (outside repo, do not lose). |

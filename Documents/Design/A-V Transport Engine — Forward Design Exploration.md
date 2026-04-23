# A/V Transport Engine — Forward Design Exploration

A forward-looking design exploration rather than a design brief for current implementation. Seeded from an evening conversation that started at a seemingly-small performance observation — *why does per-node mute cost more than app-level mute?* — and ended at the architectural destination for Intricate's playback layer.

The horizon is measured in months-to-years, not weeks. The conversation that produced this document was the work; nothing here is implemented. This is the captured intent, available to be picked up fresh on a random early morning when the time is right.

---

## How the conversation arrived here

The trigger was pedestrian: with twenty-ish VideoNodes on a canvas all muted via their per-node volume slider, the app ran noticeably heavier than the same twenty VideoNodes with the sidebar's global app-mute toggled on. Same silent outcome, measurably different cost.

The mechanical cause is straightforward. Per-node slider at 0 calls `QAudioOutput.setVolume(0.0)` — the output stage keeps mixing and pushing silent samples to the OS audio device. Global app-mute calls `QAudioOutput.setMuted(True)`, which short-circuits the output stage and lets WMF propagate "no one is listening" further upstream. Neither actually stops audio *decode* — but setMuted is cheaper because more of the downstream pipeline idles.

The architectural cause, which is what this document is actually about, is that **every VideoNode runs its own audio decoder pipeline whether or not anyone is listening**. In the user's dominant workflow, VideoNodes are paired with a sister AudioNode that plays the same file's audio — and the AudioNode is the one actually consulted. The VideoNode's entire audio pipeline is pure waste in the common case.

Naming that out loud raised a principled question: *should VideoNodes carry audio at all?* Professional A/V authoring tools — Avid, Pro Tools, Premiere's timeline layering — always keep audio and video on separate tracks that happen to be synced, not fused. The single-container format (.mp4, .mov) is a *delivery* convention, not an *authoring* one. Single-container playback belongs to consumer tools: YouTube, Instagram, X, VLC. It does not belong to an authoring environment that treats itself as a craft-first instrument.

The consequence: **VideoNode should carry no audio whatsoever**. The audio pipeline becomes AudioNode's exclusive domain. VideoNode becomes a pure visual citizen.

From that principled cut, the next question arrived on its own — *how do paired Video + Audio stay in sync?* — and the answer required thinking at a different scale.

---

## Design Principles

Six invariants. Everything else is consequence.

### 1. Audio and video are separate pipelines, always

Single-container A/V is a delivery format. Intricate is an authoring environment. The pipelines are separate by construction: VideoNode decodes and presents video only; AudioNode decodes and presents audio only. No VideoNode anywhere in Intricate carries an audio output. No AudioNode anywhere in Intricate carries a video sink.

This is the architectural cut that makes every subsequent principle possible.

### 2. One clock, many readers

All temporal coordination flows from a single **Transport** singleton. Transport owns the wall-clock (or beat-clock, when beat/bar semantics are active) position. Every media node is a **server** answering the question *what do you look/sound like at transport time T?* — not a player with its own decoder clock.

Two separate clocks drift by physics; one clock does not. The drift problem dissolves not by being solved but by being eliminated.

### 3. Media nodes are frame-servers and sample-servers

VideoNode is a frame-server. AudioNode is a sample-server. Neither owns playback state in the traditional QMediaPlayer sense. Both expose a narrow interface: *given transport time T, produce the frame/sample block matching T, modulo my loop length.*

This is the shape of Resolume's engine, minus the features Intricate does not need. It is also the shape most professional A/V engines converge on for the same reason: it is the only architecture that gives sample-accurate multi-channel synchronization.

### 4. The audio device's sample clock is the transport clock

When the engine is in its final form, Transport does not run on a `QTimer` or CPU timer. It derives its position from the audio output device's actual sample clock — the authoritative source of "now" in any system with audio running. Video frame presentation is driven off that clock. This is what makes sync *real* rather than merely *tight*.

### 5. Cueing is expressed in the node graph, timing is expressed in Transport

The node graph expresses *what plays on what channel*: VideoNode wired to ConductorNode wired to AudioNode means "this video and this audio share this conductor's play/pause and, later, this conductor's cue slot." Transport expresses *when things happen*: "at beat 32, fire all cues armed on channel 3."

The graph is the score. Transport is the conductor's baton. Keep them orthogonal.

### 6. Gallery-not-trench carries through to performance mode

Even when Intricate is a performable instrument at a nightclub set, the visual grammar stays gentle. No performance-mode HUD that overwrites the authoring canvas with heavy ruckus. Cue triggers are whispers, not shouts. The aesthetic that makes Intricate Intricate survives the addition of professional-grade capability.

---

## The Architecture

### Transport

A singleton, app-scoped. Holds:

- Current position in seconds (later: beats, bars, phrase).
- Playback state (playing, paused, stopped).
- Tempo, optional — null means free-running wall-clock mode.
- Subscribers list — every frame-server and sample-server registers to receive per-tick position updates.
- A clock source — initially a high-resolution `QElapsedTimer`, later the audio device's sample clock via `QAudioSink` callback.

Transport is the only object in Intricate that knows what time it is. Every other time-aware component asks Transport.

### VideoNode as frame-server

Post-migration, VideoNode does not use QMediaPlayer. It uses:

- **PyAV** (ffmpeg Python bindings) for decoding to raw frames.
- A **ring buffer** of decoded frames, sized for the node's loop length at its playback resolution.
- A `QVideoSink` for presentation to the scene.
- A **present callback** subscribed to Transport: *on each tick, pick the frame whose PTS matches `T mod loop_length` and push it to the sink.*

No audio anywhere. No `QAudioOutput`. No `setMuted`. No volume slider. No fade animations. The entire audio dimension of the current VideoNode file disappears — somewhere between 150 and 250 lines of complexity, gone.

### AudioNode as sample-server

Post-migration, AudioNode uses:

- **PyAV** for decoding to raw PCM.
- A **ring buffer** of decoded sample blocks.
- A `QAudioSink` for output.
- A **present callback** subscribed to Transport, same shape as VideoNode's, but producing sample blocks instead of frames.

When the audio device's sample clock is the transport clock, this callback doubles as Transport's own tick source. AudioNode becomes structurally load-bearing: Transport's existence at all depends on at least one AudioNode being present to provide the clock. In performance mode, this is always true. In canvas-browsing mode where no audio is loaded, Transport falls back to `QElapsedTimer`.

### ConductorNode (working name — user will choose)

Tooltip: *"I'm the prettiest button so I belong on top"* — this is load-bearing and must ship verbatim.

A chromeless StickerNode-lineage node, auto-spawned when a VideoNode and AudioNode pair is created (auto-spawn of the AudioNode itself happens on VideoNode load; the conductor appears in the chain between them). Visually a Play.png sticker. Click to play, click to pause. Cute.

Semantically: a channel controller. Its click publishes `transport.play()` / `transport.pause()` to Transport, optionally scoped to a channel. When cueing arrives in later stages, long-press or a secondary affordance arms a cue slot; trigger-at-next-beat fires it.

### The chain

```
VideoNode ──wire── ConductorNode ──wire── AudioNode
```

Wires are relationships, not containers. Shake-delete any one citizen; the other two persist. Delete the conductor; video and audio become independent citizens, just no longer jointly cueable. This is consistent with every other cascading-vs-independent decision in Intricate.

---

## Staging

Five stages. Each is independently usable; each leaves room for the next.

### Stage 1 — A/V split + auto-spawn + conductor (browsing-grade sync)

The stage that the instigating conversation is actually asking for.

- VideoNode amputates its audio pipeline entirely. QAudioOutput, setMuted, volume slider, fade animations, is_muted consultation, muted/volume data fields — all gone.
- New `utils/audio_extract.py` (a fresh, small, Intricate-local implementation; not a call into `_util/bin/`) handles single-file ffmpeg extraction to `{source_parent}/Audio Samples/{stem}.wav`, matching the layout the user's personal bulk script already produces. Idempotent — existing WAV is reused if found.
- VideoNode's `load_from_path` kicks off a background extraction worker; on completion, the main-thread poll spawns a sister AudioNode via the existing scatter-spawn seat algorithm, wired to the VideoNode, and a ConductorNode appearing in the chain.
- Conductor uses `player.play()` / `player.pause()` fan-out to the two QMediaPlayers. **This is browsing-grade sync, explicitly not VJ-grade.** Drift over long plays exists and is known. Acceptable for the "headphones on, graph open, browsing" use case that prompted the conversation.
- Session back-compat: old sessions' VideoNode `volume` / `muted` fields are ignored silently on load. No migration tooling needed.

Stage 1 resolves the original performance question (no VideoNode audio pipeline means nothing to mute), delivers the user's dominant paired-workflow ergonomically, and cleans ~200 lines of complexity out of VideoNode — without committing to the harder engineering of the transport migration.

### Stage 2 — Transport seat

Introduce `utils/transport.py` — the Transport singleton, initially doing nothing but holding position and broadcasting play/pause events.

- ConductorNode migrates to publishing `Transport.play()` / `Transport.pause()` instead of calling the QMediaPlayers directly.
- VideoNode and AudioNode subscribe to Transport's play/pause and relay to their still-QMediaPlayer-backed players internally.
- No behaviour change. Zero performance change. Zero sync change. Purely architectural: the seat exists, the contract exists, everything downstream can be swapped without changing what the node graph means.

Stage 2 is the "leave room for the real thing" stage. It's cheap, it's safe, it's the most important stage for long-horizon flexibility.

### Stage 3 — Video frame-server migration

VideoNode swaps QMediaPlayer for PyAV + frame buffer + Transport-driven present callback.

- Video is now sample-accurate against Transport.
- Audio is still QMediaPlayer-backed; audio-vs-video drift still exists but within much narrower bounds (video is locked to Transport, audio is not).
- Transport's clock source is still CPU-timer-based; the audio-device-clock tie happens in Stage 4.

### Stage 4 — Audio sample-server migration

AudioNode swaps QMediaPlayer for PyAV + QAudioSink + Transport-driven present callback. Transport's clock source becomes the audio device sample clock.

At this stage, sync is *real*. Sub-sample accuracy between any number of Video and Audio citizens. The drift problem is dead. Booth-grade sync is achieved without the booth.

### Stage 5 — VJ features proper

Beat grid. Quantized cue triggers (launch-next-beat, launch-next-bar, launch-next-phrase). Channel routing via the node graph. Tempo tap. Optional **Ableton Link** integration — Intricate becomes a peer on the Link network alongside the DJ's rekordbox / Traktor / Ableton Live, inheriting tempo and phase from the room.

At this stage, Intricate becomes a performable instrument in the literal sense. Five hours of continuous VJ set at a nightclub, cues triggered by gentle touch, every frame on beat.

---

## What this is not

- **Not a full Resolume competitor.** Resolume has decades of features around effects chains, MIDI mapping, arena-scale output matrixing, etc. Intricate does not need those — it needs the sync engine underneath them, applied to its own node-graph paradigm.
- **Not a replacement for hardware sync.** Some contexts (large festival rigs, broadcast) will continue to need dedicated SMPTE/genlock hardware. Intricate reaches a performable sync standard for single-operator nightclub-scale work. Beyond that, the booth still exists.
- **Not a general-purpose media framework.** The Transport engine is tuned specifically to Intricate's node-graph shape. It is not intended to be extracted into Shared Braincell as a generic library — the coupling to the graph is the point.
- **Not an "all at once" migration.** The stages exist precisely because each one must be independently shippable and usable. A user who sits at Stage 1 forever still has a cleaner, faster, better-shaped Intricate than they have today.

---

## Honest limits

- **PyAV as a dependency.** PyInstaller bundling of PyAV on Windows is non-trivial. The build system will need to learn to carry ffmpeg DLLs correctly. This is solvable, documented, and done by other Python projects — but it is not free.
- **Raw audio output latency.** `QAudioSink` has a typical 20–50ms buffer latency on Windows with WASAPI shared mode. For cueing-against-beat, this is audible. WASAPI exclusive mode (5–10ms) is achievable but excludes other audio on the machine. Stage 5 will need to settle this.
- **Video decode cost at scale.** PyAV decoding 30 simultaneous HD video streams at 60fps is feasible on modern hardware, but not universal. A grid of 100 1080p clips needs proxy rendering (low-res decode paths) to stay realtime — which is a Stage 5 feature Resolume has and Intricate would need.
- **Loop-boundary artifacts in Stages 1–3.** Until Stage 4 closes the audio-device-clock loop, loop restart of a video against a separate audio clock may have a one-frame jitter at the boundary. Acceptable for browsing, not acceptable for performance.

---

## What was decided in the conversation itself

- The A/V pipeline separation is committed. Stage 1 is go.
- The Transport engine is a legitimate long-horizon destination. Stage 2 onwards is on the roadmap, not shelved.
- Browsing-grade sync in Stage 1 is explicitly acceptable; VJ-grade sync awaits Stage 4. This is written down here so the gap is not a bug later — it is a known, deliberate stage-boundary.
- Ableton Link is a yes. Stage 5 will include it.
- The ConductorNode's tooltip is immutable. *"I'm the prettiest button so I belong on top."* This is canonical and shall not be paraphrased.

---

## One closing note

The conversation began at "the app feels heavier than it should with muted videos" and ended at "Intricate grows a transport engine." That arc — from a surface symptom to an architectural commitment — is the shape of good conversations about Intricate specifically. The app has always been capable of becoming what its users discover they need it to be, because its architectural foundations have stayed honest about that as a possibility.

Nothing on these pages is urgent. Everything on these pages is buildable. The early morning when this is picked up fresh is the right time; until then, Stage 1 is the useful first move, and the rest waits patiently.

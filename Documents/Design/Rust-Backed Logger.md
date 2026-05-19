# Rust-Backed Logger

The `intricate-log` repo is a sibling crate that compiles to a Python extension module (`.pyd`) and is imported by every app in the Single Shared Braincell family as `intricate_log`. It is the family's first Rust module — written when the cost of logging from the UI thread became visible on the canvas, and kept because the design that solved it has paid off in places we didn't originally aim for.

This document accounts for it. The repo itself has a [README](../../../intricate-log/README.md) for surface-level orientation; this brief sits one layer in, explaining why the piece exists and what shape the decisions took.

## Why it exists

The standard library logger writes on the calling thread. `logger.info("…")` resolves a format string, builds a `LogRecord`, walks the handler list, encodes UTF-8, and writes to disk — all before returning. At the volumes Intricate emits during a pulse-heavy scene (per-frame TRACE in some subsystems, per-node DEBUG during repaints), that overhead lands directly on the Qt event loop and the canvas feels it.

The fix has a well-known shape: producer enqueues a structured record, a consumer thread does the formatting and I/O. Python's `QueueHandler` + `QueueListener` implements exactly that pattern in the stdlib. We used it for a long time. It works.

The reason we rewrote it in Rust anyway:

1. **`queue.Queue` still acquires a lock on every put.** Under contention with the GIL, the lock cost shows up as 1–3 ms tail latencies on hot frames. Not crippling — but visible in a tool whose entire selling point is the cursor-sweep pulse animation responding immediately.
2. **Each `LogRecord` allocates.** A dict, a frozen format-args tuple, an attribute dict on the record itself, the formatted message string at handler time. None of it is large, but the allocator pressure was non-trivial during sustained DEBUG runs.
3. **We were already paying for one Rust dependency** (the [Pretty Widgets](../../../Pretty%20Widgets/) project had begun pulling in compiled extensions). Standing up a build pipeline for a second one had a fixed cost we'd already eaten.

So the rewrite was about *removing variance* from the hot path. Not about throughput — Python's QueueListener is fast enough on throughput. It was about making the producer side genuinely allocation-free and lock-free, so that even pathological log storms can't choke the UI thread.

## Architecture

```
┌────────────────────────────┐       ┌──────────────────────────────────┐
│ Python UI thread (producer)│       │ Rust consumer thread             │
│                            │       │                                  │
│ log(level, event, **kv)    │──────▶│ drain ring buffer                │
│                            │       │ format each event                │
│   • acquire write slot     │       │ dispatch to sinks                │
│   • write fields directly  │       │   ├─ file sink (rotating)        │
│   • commit (atomic store)  │       │   ├─ console sink (stdout)       │
│                            │       │   └─ event-log sink (Windows)    │
│ no formatting, no I/O      │       │                                  │
│ no GIL release needed      │       │ wait on condvar; loop            │
└────────────────────────────┘       └──────────────────────────────────┘
```

A pre-allocated array of `LogEvent` slots forms a single-producer single-consumer ring buffer. Each slot is a fixed-size record: timestamp, level byte, logger index byte, an inline event-name buffer (128 bytes), and an inline KV data region (512 bytes). No heap allocation per event. The producer never blocks; the only synchronisation is atomic store/load on the write and read indices, and a condvar to wake the consumer when the buffer was empty.

The consumer drains in batches: pull every available event, format each into a reusable `String` buffer, hand the formatted line to every sink whose minimum level admits it, then flush sinks once per batch (not once per event). The flush coalescing matters — sustained log runs amortise the `fsync` cost across many events instead of paying it on each one.

## Hot-path discipline

The producer's job in the original design was small, and we keep it small on purpose. Three categories of work are forbidden on the calling thread:

- **String formatting.** The event identifier is passed as a literal (`"bridge_debounce_fired"`); KV pairs travel as typed values, packed into the slot's `kv_data` buffer as length-prefixed bytes. The consumer formats `key=value` strings; the producer never does.
- **File I/O.** Even the timestamp comes from `SystemTime::now()`, which on every platform we ship to is a vDSO call — no syscall.
- **GIL release.** The whole `log()` call body fits inside one GIL acquisition. No `Py_BEGIN_ALLOW_THREADS`, no scheduling fences. The producer thread keeps the GIL and exits faster than a stdlib `logger.info` call could acquire its `RLock`.

The cost on the producer side is now: one atomic fetch-and-add (to acquire a slot index), a handful of direct field writes into the slot's struct, the kwargs packing loop (small, bounded by the 512-byte KV region), one atomic store (to mark the slot ready), one condvar notify. Under contention it stays the same — there is no contention, because there is only one producer in practice and the protocol assumes that.

## Drop-oldest, not blocking

When the producer outruns the consumer, *something* must give. The two honest choices are *block the producer* or *drop events*. We chose drop-oldest with a counter.

The reasoning is that the worst thing a logger can do is make the application slower than it would have been without logging. A blocking producer means a slow disk or a stalled consumer thread back-pressures the UI thread directly — the cure becomes the disease. Drop-oldest means that in an overflow we silently lose the oldest unread events and increment a counter that surfaces in the consumer's output, so the user knows logs were dropped without the application freezing to deliver them.

This matches Intricate's broader stance: the visible app always comes first, and instrumentation that cannot keep up with the visible app yields, never the other way around.

## Dual backend — Rust native + Python fallback

The Python package `intricate_log` is two implementations behind one import:

```python
try:
    from intricate_log._native import init, log, flush, …
    BACKEND = "rust"
except ImportError:
    from intricate_log._fallback import init, log, flush, …
    BACKEND = "python"
```

The fallback is a real implementation, not a stub. It uses `queue.Queue` + a worker thread + the same three sinks and writes to the same log-file path with the same rotation. The reason it exists:

- **Fresh clones on machines without a Rust toolchain still get a working logger.** Devs don't have to install `rustup` and `maturin` before running `python main.py` for the first time. The application boots, the fallback handles output, and the only visible difference is that `intricate_log.BACKEND` reads `"python"`.
- **Frozen builds that fail to bundle the `.pyd` degrade gracefully** instead of crashing at import. We bundle the `.pyd` in normal builds, but a misconfigured PyInstaller spec used to be a failure cliff. Now it's a fall-through.
- **The fallback is a behavioural reference.** When the Rust side changes (new sink, new KV type, new level), the Python fallback gets the same change. Comparing the two outputs is how we keep the contract honest.

The fallback is slower than the native module by exactly the amount the Rust rewrite saved — a few milliseconds of tail latency during heavy logging. On a dev machine that's invisible; on a deployed build it would be visible during pulse-heavy scenes, which is why we ship the `.pyd`.

## Sinks

Three sinks live behind the consumer, all written in Rust, all running on the consumer thread:

- **File sink** writes a fresh timestamped file per process run (`intricate_YYYYMMDD-HH.MM.SS.log`) and retains the most recent N runs. Configurable through `init()`; default is 7. The directory is normally `[shared] log_dir` from `settings.toml`, which the calling app resolves before handing the path to `init()`.
- **Console sink** writes to stdout. It accepts a `has_console=False` flag for frozen GUI builds where stdout is detached and writes would silently fail or, worse, fault the process — in that case the sink becomes a no-op.
- **Event Log sink** is Windows-only and writes via `windows-sys` directly into the Windows Application Event Log under a registered source. The default minimum level is `ERROR`, so the system event log doesn't fill up with INFO chatter — it sees only the things a system administrator would want to see.

Each sink filters by its own minimum level. `set_log_level()` from Python updates the file and console levels live; the Event Log sink keeps the level it was given at `init()` (so a developer who lowers the runtime level to DEBUG doesn't accidentally flood the OS event log).

## The 20-name logger table

Each event carries a logger name. Most events tag themselves with a stable, known name — `"warmnode"`, `"session"`, `"theme"`, `"chat"` — and the set of known names is small. So the slot stores a single-byte index into a static table (`LOGGER_NAMES` in `src/event.rs`) rather than a string. Unknown names get index `255` and surface as `"unknown"` in the formatted output.

This is a small optimisation, but it has a side benefit: the table is *also* the family roster. Looking at it tells you which subsystems exist at all. When we add a logger name we add it here; when a name disappears it falls out. The table doubled as documentation by accident, and now we maintain it that way.

## Place in the logger redundancy scheme

`intricate_log` is one layer of a deliberately redundant logging arrangement:

1. **stdlib logging** — used by libraries we import that don't know about `intricate_log`. Pretty Widgets' `logger.py` is the adapter shim that bridges stdlib `logger.info` calls into `intricate_log.log` so library code lands in the same files.
2. **`intricate_log`** — first-class structured logging for the app's own code.
3. **`crash.txt`** — a separate Python-side crash handler writes a forensic dump to `crash.txt` independently of the logger if the process is unwinding.
4. **`fault.txt`** — Qt's `faulthandler` writes native faults (segfaults, access violations) to `fault.txt`, bypassing Python entirely.

The duplication is load-bearing. When `intricate_log` itself misbehaves, the older layers still produce something on disk. When the Python process is unwinding past the point where the consumer thread can flush, `crash.txt` is already written by a handler that doesn't depend on the consumer. We validated this empirically on 2026-05-08, when the stdlib log truncated mid-traceback during the AudioNode crash and `crash.txt` carried the forensics that diagnosed it.

So `intricate_log` is not the only logger by design. It is the *fast* logger — the one that has to keep up with the UI thread — and it sits inside a wider arrangement where multiple independent writers cover for one another.

## What the README does not say

A few decisions worth recording where this brief lives:

- **The KV data region is 512 bytes per event.** That sounds tight, but the structured fields we log fit comfortably inside it — typically two to four key=value pairs. Overflow truncates from the end of the kwargs list rather than from inside a value, so individual values are never half-written.
- **The event name is capped at 128 bytes.** Event names are identifiers, not messages. Long descriptive sentences belong in a string-typed kwarg; the event name should always be a short, grep-able token like `"bridge_debounce_fired"` or `"image_extracted"`.
- **The consumer thread joins on `flush()`.** That call is wired into the app's vaporize sequence so that the last events are always on disk before the process exits.
- **Levels are bytes, not enums.** `TRACE=5`, `DEBUG=10`, `INFO=20`, `WARNING=30`, `ERROR=40`, `CRITICAL=50` — the values match the stdlib `logging` module exactly so the adapter shim doesn't have to translate.
- **The build is one-shot via `python install.py`** in the repo root. The script checks Python/Rust/maturin, builds the release wheel, installs it into the active interpreter with `--force-reinstall --no-deps`, and verifies the Rust backend loaded. The family runs against system Python with no venv, which means `maturin develop` isn't usable here (it insists on a venv); the wheel-then-pip flow the installer wraps is the canonical path. See the repo's README for the manual flow underneath.

## Forward direction

The piece is stable; no rewrites planned. The two foreseeable extensions:

- **A binary log format.** The on-disk file is currently human-readable text. A binary log would cut file size and make structured queries faster, but would also force tooling to ship alongside — and the current readability is genuinely useful when something has gone wrong on a user's machine and they need to paste a tail into chat. We will not change this unless there is a concrete reason.
- **A second producer thread.** The SPSC protocol assumes one producer in practice (because the GIL serialises Python callers). Some future arrangement where a Rust-side subsystem also logs would require either lifting that assumption (MPSC ring), routing the second producer through the Python entry point, or giving it its own ring. We have not needed to decide.

Until those become real questions, the logger is what it is: a small, focused piece that disappears from the UI thread's cost profile entirely, and quietly keeps the file on disk current.

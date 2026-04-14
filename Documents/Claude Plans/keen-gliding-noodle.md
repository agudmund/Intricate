# Session schema validation — harden deserialization against untrusted data

## Context

Security audit item 6: `session.json` is deserialized via `json.load()` with minimal validation. The existing `validate_session_data()` in `utils/session.py` checks structure (nodes is list, connections is list, UUIDs exist) but doesn't sanitise values. Every `from_dict()` across 27 NodeData subclasses trusts all incoming values — `float()` coercion with no error handling, strings with no length limits, paths with no traversal checks. With AWS deployment anticipated, session data could traverse a network and must be treated as untrusted.

**Approach:** Extend the existing `validate_session_data()` to sanitise node dicts *before* they reach `from_dict()`. No new dependencies — just tighten the gate that already exists.

## Changes — `utils/session.py`

### Extend `validate_session_data()` (lines 238-296)

Add three sanitisation passes after the existing structural checks:

**1. Whitelist `node_type`**
```python
_KNOWN_TYPES = frozenset({
    "warm", "about", "bezier", "health", "claude", "claude_response",
    "text", "cushions", "code", "log", "image", "video", "sequence",
    "tree", "info", "git", "audio", "merge", "audio_hold", "palette",
    "sticker", "value", "perf", "claude_info", "fbx",
})
```
Drop any node with an unknown `node_type` and log a warning.

**2. Sanitise geometry fields**
For `x`, `y`, `width`, `height`, `z_value`:
- Wrap in `float()` with try/except — replace failures with defaults
- Reject `NaN` and `Inf` (replace with defaults)
- Clamp `width`/`height` to `[10.0, 10_000.0]` — prevents DoS via absurdly large nodes

**3. Sanitise string fields**
- `uuid`: strip to alphanumeric + hyphens, reject if empty (assign fresh uuid)
- `title`, `emoji`: truncate to reasonable max lengths (title 500, emoji 32)
- `node_type`: already whitelisted above

**4. Sanitise path fields**
For nodes that carry paths (`source_path`, `project_path`, `folder_path`):
- Reject if the string contains null bytes
- Log a warning (don't strip — the path may be legitimately long or unusual, but log it for audit)

### Add `_sanitise_node(node: dict) -> dict | None`

A helper called per-node inside `validate_session_data()`. Returns the sanitised dict, or `None` to drop the node. Keeps the validation function readable.

## Files modified

| File | Change |
|------|--------|
| `utils/session.py` | Add `_KNOWN_TYPES` frozenset, add `_sanitise_node()` helper, extend `validate_session_data()` to call it per-node |

## What we are NOT doing

- Not adding `pydantic` or `jsonschema` — no new dependencies for a desktop app
- Not adding per-node-type field schemas — the 27 `from_dict()` methods already handle missing fields with `.get(key, default)`. The validator focuses on values that could crash or exploit, not completeness
- Not modifying any `from_dict()` methods — the sanitiser runs upstream in session.py before data reaches them

## Verification

1. Launch Intricate, load a normal session — everything restores correctly
2. Manually corrupt a session.json with bad values (NaN geometry, unknown node_type, huge strings, null bytes in paths) and load it — verify warnings logged and bad nodes dropped/sanitised without crashes
3. Verify checksum validation still works (corrupt data after checksum → rejected)

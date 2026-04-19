#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/audit/image_stamps.py image stamp + cache validation audit
-Scans every ImageNode for source/cache drift and stamp-placement anomalies, for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

# Validation audit for ImageNode ↔ source file ↔ media cache consistency.
#
# Context.  PNG files carry a tEXt chunk stamp under the "intricate_vision"
# key once the vision pipeline captions them.  The stamp lives on the
# SOURCE file on disk; after writing, ImageNode.stamp_source_file re-
# hashes the source bytes and points data.cache_key at the fresh stamped
# copy so cache mirrors source.  A recurring class of bug: the stamp
# ends up on the CACHE copy instead of the source — usually because
# data.source_path somehow points at a cache path, or because an older
# code path wrote to the cache directly.  The session file appears
# intact; the user's originals on disk silently never got stamped.
#
# This module does NOT heal — it reports.  Per the drift-accountability
# project memory: "Surface the signal, don't auto-heal."  The audit
# produces a structured AuditReport that the caller can log, render to
# a canvas chain, or write to disk.  The user decides per-case what to
# do with each finding.

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pretty_widgets.utils.logger import setup_logger

from utils.persistence.media_cache import (
    cache_dir, cached_bytes, cached_path, hash_file, key_hash,
)
from utils.persistence.png_stamp import (
    _INTRICATE_VISION_KEY, read_png_stamp,
)

logger = setup_logger("audit.image_stamps")


# ─────────────────────────────────────────────────────────────────────────
# FINDING SHAPES
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class Finding:
    """One anomaly (or clean result) for a single ImageNode.

    category: stable machine-readable tag — see AuditReport buckets below.
    detail:   human-readable explanation of the specific anomaly.
    """
    uuid:        str
    source_path: str | None
    cache_key:   str | None
    category:    str
    detail:      str


@dataclass
class AuditReport:
    """Structured result of a full scene audit.  Each bucket holds the
    Findings for one category.  ``clean`` holds nodes that passed every
    check; everything else is a specific anomaly.

    Naming convention: bucket name matches Finding.category, so report
    rendering can iterate fields uniformly.
    """
    total_image_nodes:       int            = 0
    clean:                   list[Finding]  = field(default_factory=list)
    missing_source:          list[Finding]  = field(default_factory=list)
    missing_cache:           list[Finding]  = field(default_factory=list)
    cache_hash_mismatch:     list[Finding]  = field(default_factory=list)
    source_cache_drift:      list[Finding]  = field(default_factory=list)
    stamp_only_on_cache:     list[Finding]  = field(default_factory=list)
    source_inside_cache_dir: list[Finding]  = field(default_factory=list)
    no_source_no_cache:      list[Finding]  = field(default_factory=list)

    # ── Ordered severity: the canary pathology is first. ─────────────────
    _CRITICAL_BUCKETS = (
        'stamp_only_on_cache',
        'source_inside_cache_dir',
        'cache_hash_mismatch',
    )
    _WARN_BUCKETS = (
        'missing_source',
        'missing_cache',
        'source_cache_drift',
    )
    _INFO_BUCKETS = (
        'no_source_no_cache',
    )

    def is_clean(self) -> bool:
        """True when no anomalies of any kind were found."""
        return all(
            not getattr(self, bucket)
            for bucket in self._CRITICAL_BUCKETS + self._WARN_BUCKETS + self._INFO_BUCKETS
        )

    def has_critical(self) -> bool:
        """True when any critical-severity bucket has findings.  The
        stamp-only-on-cache and source-inside-cache-dir buckets are the
        canary signals for the exact pathology the audit exists to
        catch — critical because they indicate stamping is silently
        failing on the originals."""
        return any(getattr(self, b) for b in self._CRITICAL_BUCKETS)

    def summary_line(self) -> str:
        """One-line human-readable summary suitable for an InfoBar whisper
        or a log message."""
        n = self.total_image_nodes
        if n == 0:
            return "[audit] no ImageNodes in scene"
        if self.is_clean():
            return f"[audit] all {n} ImageNode(s) clean — sources stamped correctly, cache mirrors source"
        parts = []
        for bucket in self._CRITICAL_BUCKETS + self._WARN_BUCKETS + self._INFO_BUCKETS:
            items = getattr(self, bucket)
            if items:
                parts.append(f"{bucket}={len(items)}")
        return f"[audit] {n} ImageNode(s) scanned — {', '.join(parts)}"

    def format_report(self) -> str:
        """Multi-line human-readable report.  Each bucket lists its
        findings with uuid, paths, and the specific detail.  Empty
        buckets are omitted so the report only shows what matters."""
        lines = [self.summary_line(), ""]
        for bucket in self._CRITICAL_BUCKETS + self._WARN_BUCKETS + self._INFO_BUCKETS:
            items = getattr(self, bucket)
            if not items:
                continue
            severity = ("CRITICAL" if bucket in self._CRITICAL_BUCKETS
                        else "WARN"  if bucket in self._WARN_BUCKETS
                        else "INFO")
            lines.append(f"── {severity}: {bucket} ({len(items)}) ──")
            for f in items:
                src = f.source_path or "<none>"
                key = f.cache_key[:16] + "…" if f.cache_key else "<none>"
                lines.append(f"  {f.uuid[:8]}  {f.detail}")
                lines.append(f"           source: {src}")
                lines.append(f"           cache:  {key}")
            lines.append("")
        if self.clean:
            lines.append(f"── clean: {len(self.clean)} ImageNode(s) passed every check ──")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────
# AUDIT
# ─────────────────────────────────────────────────────────────────────────

def audit_image_stamps(scene) -> AuditReport:
    """Walk every ImageNode in *scene* and produce an AuditReport.

    Checks, in order per node:

    1. **source_inside_cache_dir** — ``data.source_path`` resolves to a
       path inside the cache directory.  The node thinks the cache IS
       the source, so any stamp write will land on the cache copy
       instead of a real original.  Usually the upstream cause of the
       stamp-only-on-cache pathology.

    2. **missing_source** — ``source_path`` set but the file doesn't
       exist on disk.  Source moved/deleted externally.  Cache may
       still be intact so the node still loads, but drift detection
       can't run and stamps can't be re-applied.

    3. **missing_cache** — ``cache_key`` set but the cache file is gone.
       Someone cleaned the cache externally; loads fall back to source
       or the legacy ``image_b64`` blob.

    4. **cache_hash_mismatch** — the cache file on disk exists but its
       actual SHA-256 doesn't match the hash embedded in ``cache_key``.
       Manual file swap or cache corruption.  Serious integrity issue.

    5. **source_cache_drift** — source and cache both exist, both
       hashable, but their hashes differ.  Usually means the source
       was edited externally (including legitimate re-stamping from
       outside Intricate).  Expected drift per the drift-accountability
       memory; surfaced for visibility, not treated as an error.

    6. **stamp_only_on_cache** — the canary signal.  Cache file (if
       PNG) carries an ``intricate_vision`` tEXt stamp, but the source
       PNG does NOT.  That's the exact pathology: stamp went to the
       cache and missed the original.  The user wanted 103% confidence
       this can't happen silently — this bucket is how we find it if
       it does.

    7. **no_source_no_cache** — informational.  Node has neither source
       nor cache set.  Usually a freshly-pasted or generated image
       that hasn't been saved yet; harmless but surfaced so the user
       isn't surprised by it.
    """
    from nodes.ImageNode import ImageNode

    report = AuditReport()

    try:
        items = list(scene.items())
    except Exception as exc:
        logger.warning(f"[audit] scene.items() raised: {exc}")
        return report

    cache_root = cache_dir().resolve()

    for item in items:
        if not isinstance(item, ImageNode):
            continue
        report.total_image_nodes += 1

        uuid = getattr(item.data, 'uuid', '') or '?'
        src  = getattr(item.data, 'source_path', '') or ''
        key  = getattr(item.data, 'cache_key',   '') or ''

        if not src and not key:
            report.no_source_no_cache.append(Finding(
                uuid=uuid, source_path=None, cache_key=None,
                category='no_source_no_cache',
                detail='node has neither source_path nor cache_key',
            ))
            continue

        src_path    = Path(src) if src else None
        src_exists  = bool(src_path and src_path.exists())
        cache_path  = cached_path(key) if key else None
        cache_ok    = cache_path is not None  # already verified to exist

        # ── 1: source_inside_cache_dir ────────────────────────────────────
        # Tripping this implies every subsequent finding for this node is
        # downstream of the misrouted path; still run the other checks so
        # the full picture is captured.
        source_misrouted = False
        if src_path:
            try:
                resolved = src_path.resolve()
                # Path.is_relative_to is Python 3.9+; try/except for robustness
                # against symlinks + Windows drive mismatches
                try:
                    source_misrouted = resolved.is_relative_to(cache_root)
                except AttributeError:
                    resolved_str = str(resolved).lower()
                    source_misrouted = resolved_str.startswith(str(cache_root).lower())
            except Exception:
                pass
        if source_misrouted:
            report.source_inside_cache_dir.append(Finding(
                uuid=uuid, source_path=src, cache_key=key,
                category='source_inside_cache_dir',
                detail='source_path resolves inside the cache directory — stamp writes will hit the cache copy',
            ))

        # ── 2: missing_source ────────────────────────────────────────────
        if src and not src_exists:
            report.missing_source.append(Finding(
                uuid=uuid, source_path=src, cache_key=key,
                category='missing_source',
                detail='source_path set but file not found on disk',
            ))

        # ── 3: missing_cache ─────────────────────────────────────────────
        if key and not cache_ok:
            report.missing_cache.append(Finding(
                uuid=uuid, source_path=src, cache_key=key,
                category='missing_cache',
                detail='cache_key set but cache file not found',
            ))

        # ── 4: cache_hash_mismatch ───────────────────────────────────────
        # Only meaningful when the cache file exists.  Compare the file's
        # actual SHA-256 against the hash embedded in the key.
        if cache_ok:
            expected_hash = key_hash(key)
            actual_hash   = hash_file(cache_path) if cache_path else None
            if actual_hash and expected_hash and actual_hash != expected_hash:
                report.cache_hash_mismatch.append(Finding(
                    uuid=uuid, source_path=src, cache_key=key,
                    category='cache_hash_mismatch',
                    detail=f'cache file SHA-256 mismatch (expected {expected_hash[:12]}…, got {actual_hash[:12]}…)',
                ))

        # ── 5: source_cache_drift ────────────────────────────────────────
        # Both must exist AND both must hash successfully.
        if src_exists and cache_ok:
            src_hash   = hash_file(src_path)
            cache_hash = hash_file(cache_path)
            if src_hash and cache_hash and src_hash != cache_hash:
                report.source_cache_drift.append(Finding(
                    uuid=uuid, source_path=src, cache_key=key,
                    category='source_cache_drift',
                    detail=f'source and cache hashes differ (src={src_hash[:12]}…, cache={cache_hash[:12]}…)',
                ))

        # ── 6: stamp_only_on_cache (the canary) ──────────────────────────
        # Only applicable to PNG sources (tEXt chunks are PNG-specific).
        # Stamp is expected on both source and cache (stamp writes to
        # source → source re-hashed into cache, cache inherits stamp).
        # Finding fires when cache has a stamp but source doesn't —
        # indicates the write routed to the cache directly, bypassing
        # the source.
        if src_exists and cache_ok and src_path.suffix.lower() == '.png' and cache_path.suffix.lower() == '.png':
            src_stamp   = read_png_stamp(src_path,   _INTRICATE_VISION_KEY)
            cache_stamp = read_png_stamp(cache_path, _INTRICATE_VISION_KEY)
            if cache_stamp and not src_stamp:
                report.stamp_only_on_cache.append(Finding(
                    uuid=uuid, source_path=src, cache_key=key,
                    category='stamp_only_on_cache',
                    detail=f'cache carries vision stamp but source does not — stamp went to wrong target',
                ))

        # If this node hit NO anomaly buckets, count it as clean.  The
        # informational no_source_no_cache above early-returns so we
        # don't reach here for that category.
        node_anomaly_buckets = (
            report.source_inside_cache_dir,
            report.missing_source,
            report.missing_cache,
            report.cache_hash_mismatch,
            report.source_cache_drift,
            report.stamp_only_on_cache,
        )
        if not any(f.uuid == uuid for bucket in node_anomaly_buckets for f in bucket):
            report.clean.append(Finding(
                uuid=uuid, source_path=src, cache_key=key,
                category='clean',
                detail='all checks passed',
            ))

    return report


# ─────────────────────────────────────────────────────────────────────────
# LOG HELPER — one-call audit-and-log from a menu action or debug hook
# ─────────────────────────────────────────────────────────────────────────

def audit_and_log(scene, full_report: bool = True) -> AuditReport:
    """Run the audit and log the result.  Summary line always logs at
    INFO; full report logs at INFO when any critical finding is present,
    DEBUG otherwise (so a clean audit doesn't clutter the session log).

    Returns the AuditReport so the caller can present it in the UI too.
    """
    report = audit_image_stamps(scene)
    logger.info(report.summary_line())
    if full_report:
        if report.has_critical():
            for line in report.format_report().splitlines():
                logger.info(line)
        elif not report.is_clean():
            for line in report.format_report().splitlines():
                logger.debug(line)
    return report

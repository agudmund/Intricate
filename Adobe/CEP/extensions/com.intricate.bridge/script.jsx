// ───────────────────────────────────────────────────────────────────────────
//  Intricate Bridge — ExtendScript side (script.jsx)
//  Runs inside Premiere Pro's ExtendScript engine (ES3-ish, no JSON native).
//
//  Exposes:
//    consoleLog(msg)                              — echo to console + Events
//    handshakeReport(expectedProj, expectedSeq)   — full census JSON string
//    heartbeatReport()                            — tiny liveness JSON string
// ───────────────────────────────────────────────────────────────────────────

// ─── Tiny JSON encoder ──────────────────────────────────────────────────────
// ExtendScript is ES3; no JSON.stringify. Hand-rolled so we don't need a
// polyfill file in the extension bundle (and another thing for ZXPSignCmd
// to hash into the signature).
function _icJson(v) {
    if (v === null || v === undefined) return "null";
    var t = typeof v;
    if (t === "boolean") return v ? "true" : "false";
    if (t === "number")  return isFinite(v) ? String(v) : "null";
    if (t === "string") {
        return '"' + v.replace(/\\/g, "\\\\")
                      .replace(/"/g, '\\"')
                      .replace(/\n/g, "\\n")
                      .replace(/\r/g, "\\r")
                      .replace(/\t/g, "\\t") + '"';
    }
    if (v instanceof Array) {
        var parts = [];
        for (var i = 0; i < v.length; i++) parts.push(_icJson(v[i]));
        return "[" + parts.join(",") + "]";
    }
    if (t === "object") {
        var kparts = [];
        for (var k in v) {
            if (v.hasOwnProperty(k)) kparts.push('"' + k + '":' + _icJson(v[k]));
        }
        return "{" + kparts.join(",") + "}";
    }
    return "null";
}

// ─── Console echo (Phase 1 behaviour, unchanged) ────────────────────────────
// $.writeln surfaces if the ExtendScript Toolkit debugger is attached.
// app.setSDKEventMessage shows up in Premiere's Events panel (Window > Events)
// regardless of debug state — that's the visible channel.
function consoleLog(msg) {
    try { $.writeln("[Intricate] " + msg); } catch (e) {}
    try {
        if (typeof app !== "undefined" && app.setSDKEventMessage) {
            app.setSDKEventMessage("[Intricate] " + msg, "info");
        }
    } catch (e) {}
    return "OK";
}

// ─── Strip .prproj suffix for display / comparison ──────────────────────────
function _stripExt(name) {
    if (!name) return "";
    return String(name).replace(/\.prproj$/i, "");
}

// ─── Available sequence names — for "did you mean" on mismatch ──────────────
function _listSequences() {
    var names = [];
    try {
        if (app && app.project && app.project.sequences) {
            var n = app.project.sequences.numSequences;
            for (var i = 0; i < n; i++) {
                names.push(app.project.sequences[i].name);
            }
        }
    } catch (e) {}
    return names;
}

// ─── Clip census at (track, clip) — null if out of range ────────────────────
function _clipCensus(seq, trackIdx, clipIdx) {
    try {
        if (!seq || !seq.videoTracks) return null;
        if (trackIdx < 0 || trackIdx >= seq.videoTracks.numTracks) return null;
        var track = seq.videoTracks[trackIdx];
        if (!track || !track.clips) return null;
        if (clipIdx < 0 || clipIdx >= track.clips.numItems) return null;
        var c = track.clips[clipIdx];
        if (!c) return null;
        return {
            name:     c.name,
            inPoint:  (c.inPoint  && c.inPoint.seconds  != null) ? c.inPoint.seconds  : null,
            outPoint: (c.outPoint && c.outPoint.seconds != null) ? c.outPoint.seconds : null,
            start:    (c.start    && c.start.seconds    != null) ? c.start.seconds    : null,
            end:      (c.end      && c.end.seconds      != null) ? c.end.seconds      : null,
            disabled: c.disabled ? true : false
        };
    } catch (e) {
        return null;
    }
}

// ─── Full handshake census — called by CEP side on HELLO ────────────────────
// Returns a JSON string. Shape when things are well:
//
//   {
//     "ok": true,
//     "premiereVersion": "...",
//     "project":  { "name": "...", "path": "...", "matches": true  },
//     "sequence": { "name": "...", "matches": true,
//                   "fps": 29.97, "width": 1920, "height": 1080,
//                   "videoTracks": 4, "audioTracks": 6,
//                   "endSeconds": 120.5 },
//     "selectedClip": { track, clip, name, inPoint, outPoint, ... } | null,
//     "availableSequences": ["...", ...]
//   }
//
// When things are not well:
//
//   { "ok": false, "reason": "no_project_open" | "no_active_sequence"
//                          | "project_mismatch" | "sequence_mismatch"
//                          | "extendscript_exception",
//     "details": { ...whatever we know... } }
function handshakeReport(expectedProject, expectedSequence, trackIdx, clipIdx) {
    try {
        if (typeof app === "undefined" || !app.project) {
            return _icJson({ ok: false, reason: "no_project_open", details: {} });
        }

        var actualProject = _stripExt(app.project.name);
        var projectPath   = (app.project.path != null) ? String(app.project.path) : "";
        var expectedProj  = _stripExt(expectedProject || "");
        var projectMatches = !expectedProj || (actualProject === expectedProj);

        if (!projectMatches) {
            return _icJson({
                ok: false,
                reason: "project_mismatch",
                details: {
                    expected: expectedProj,
                    actual:   actualProject,
                    path:     projectPath
                }
            });
        }

        var seq = app.project.activeSequence;
        if (!seq) {
            return _icJson({
                ok: false,
                reason: "no_active_sequence",
                details: { availableSequences: _listSequences() }
            });
        }

        var actualSeq = seq.name;
        var sequenceMatches = !expectedSequence || (actualSeq === expectedSequence);

        if (!sequenceMatches) {
            return _icJson({
                ok: false,
                reason: "sequence_mismatch",
                details: {
                    expected:           expectedSequence,
                    actual:             actualSeq,
                    availableSequences: _listSequences()
                }
            });
        }

        // Sequence measurements
        var settings = seq.getSettings();
        var fps      = (settings && settings.videoFrameRate)
                       ? (254016000000 / settings.videoFrameRate.ticks)
                       : 0;
        var width    = (settings && settings.videoFrameWidth)  ? settings.videoFrameWidth  : 0;
        var height   = (settings && settings.videoFrameHeight) ? settings.videoFrameHeight : 0;
        var endSec   = (seq.end && seq.end.seconds != null)    ? seq.end.seconds           : null;
        var vTracks  = (seq.videoTracks) ? seq.videoTracks.numTracks : 0;
        var aTracks  = (seq.audioTracks) ? seq.audioTracks.numTracks : 0;

        // Parse track/clip indices (they arrive as strings from evalScript)
        var tIdx = parseInt(trackIdx, 10); if (isNaN(tIdx)) tIdx = 0;
        var cIdx = parseInt(clipIdx,  10); if (isNaN(cIdx)) cIdx = 0;
        var clipInfo = _clipCensus(seq, tIdx, cIdx);

        var premVer = (typeof app.version !== "undefined") ? String(app.version) : "";

        return _icJson({
            ok: true,
            premiereVersion: premVer,
            project: {
                name:    actualProject,
                path:    projectPath,
                matches: true
            },
            sequence: {
                name:        actualSeq,
                matches:     true,
                fps:         Math.round(fps * 1000) / 1000,
                width:       width,
                height:      height,
                videoTracks: vTracks,
                audioTracks: aTracks,
                endSeconds:  endSec
            },
            selectedClip: (clipInfo ? {
                track:    tIdx,
                clip:     cIdx,
                name:     clipInfo.name,
                inPoint:  clipInfo.inPoint,
                outPoint: clipInfo.outPoint,
                start:    clipInfo.start,
                end:      clipInfo.end,
                disabled: clipInfo.disabled
            } : null),
            availableSequences: _listSequences()
        });
    } catch (e) {
        return _icJson({
            ok: false,
            reason: "extendscript_exception",
            details: { message: String(e.message || e), line: e.line || null }
        });
    }
}

// ─── Heartbeat census — called by CEP on PING, cheap liveness probe ─────────
// Intentionally minimal: if we ping Premiere every 5s, the answer should be
// nearly free. Anything expensive (clip iteration, settings lookups) stays in
// handshakeReport, not here.
function heartbeatReport() {
    try {
        var projOpen = !!(app && app.project);
        var seqOpen  = !!(projOpen && app.project.activeSequence);
        return _icJson({
            ok:          true,
            projectOpen: projOpen,
            sequenceOpen: seqOpen,
            projectName: projOpen ? _stripExt(app.project.name) : ""
        });
    } catch (e) {
        return _icJson({ ok: false, reason: "heartbeat_exception",
                         details: { message: String(e.message || e) } });
    }
}

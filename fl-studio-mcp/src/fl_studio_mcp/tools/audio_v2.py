"""fl_audio — audio FILES: analyse (tempo / key / chords / root note), cut, split L/R, load.

Built 2026-10-06 from "10 Things I Wish I Knew When I Started FL Studio" (In The Mix):
  tip 5 detect a sample's tempo    -> analyze: two tempo estimators, agreement flagged
  tip 6 find a sample's note / key -> analyze: root note (spectrum) + key (chroma profiles)
  tip 7 work out a chord's notes   -> analyze: chord timeline (per-beat triad match)
  tip 2 keep a cut section         -> extract(start, end): a new WAV (no clipboard dance)
  tip 3 isolate the left/right     -> split(side): a mono WAV of one channel
  + load(path, name, pan, pitch)   -> a new Sampler channel holding it, pan/pitch by API

Analysis is pure numpy in-process (audio/analysis.py): no models, no extra envs.
Files go to fl-studio-mcp/.generated/audio/ (git-ignored; audio is never committed).
Analysis gaps (tempo disagreement, weak key, unsure chords) are REPORTED, never hidden.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

PKG = Path(__file__).resolve().parents[3]                 # fl-studio-mcp/
OUT = PKG / ".generated" / "audio"
ACTIONS = ("analyze", "extract", "split", "load", "recorder")
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _ff() -> str:
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg not on PATH")
    return ff


def _src(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise ValueError(f"no such file: {p}")
    return p


def _tag(p: Path, extra: str = "") -> str:
    h = hashlib.sha256(f"{p}:{p.stat().st_mtime}:{extra}".encode()).hexdigest()[:8]
    return f"{p.stem[:40]}-{h}"


def _wav(p: Path, extra_af: str | None = None, ss: float | None = None,
         to: float | None = None, mono: bool = False, tag: str = "") -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{_tag(p, tag + str(extra_af) + str(ss) + str(to))}.wav"
    if out.exists():
        return out
    cmd = [_ff(), "-y", "-loglevel", "error"]
    if ss is not None:
        cmd += ["-ss", str(ss)]
    cmd += ["-i", str(p)]
    if to is not None:
        cmd += ["-t", str(max(0.01, to - (ss or 0.0)))]
    if extra_af:
        cmd += ["-af", extra_af]
    cmd += ["-ar", "44100", "-ac", "1" if mono else "2", "-c:a", "pcm_s24le", str(out)]
    subprocess.run(cmd, check=True, timeout=300)
    return out


# ------------------------------------------------------------------ analysis

def chord_name(lab: str) -> str:
    """'F:maj' -> 'F', 'A:min' -> 'Am', 'C:maj7' -> 'Cmaj7', 'N' -> '-'."""
    if not lab or lab in ("N", "X"):
        return "-"
    root, _, q = lab.partition(":")
    q = q.split("/")[0]
    return root + {"": "", "maj": "", "min": "m", "maj7": "maj7", "min7": "m7", "7": "7",
                   "dim": "dim", "aug": "aug", "sus4": "sus4", "sus2": "sus2",
                   "min6": "m6", "maj6": "6", "hdim7": "m7b5", "dim7": "dim7"}.get(q, q)


def root_note(wav: Path) -> dict:
    """Fundamental of a (mostly) monophonic sample - an 808, a bass hit, a vocal note -
    via a harmonic-product spectrum over 30-1200 Hz (numpy only)."""
    import numpy as np
    raw = subprocess.run([_ff(), "-loglevel", "error", "-i", str(wav), "-t", "3", "-ac", "1",
                          "-ar", "22050", "-f", "f32le", "-"], capture_output=True,
                         timeout=60).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    if x.size < 2048:
        return {"error": "too short"}
    i0 = int(np.argmax(np.abs(x) > 0.1 * np.max(np.abs(x))))     # skip leading silence
    seg = x[i0 + 441: i0 + 441 + 32768]                           # past the click
    if seg.size < 4096:
        seg = x[i0:i0 + 32768]
    spec = np.abs(np.fft.rfft(seg * np.hanning(seg.size), n=1 << 16))
    freqs = np.fft.rfftfreq(1 << 16, 1 / 22050)
    hps = spec.copy()
    for h in (2, 3):
        dec = spec[::h]
        hps[:dec.size] *= dec
    band = (freqs >= 30) & (freqs <= 1200)
    f0 = float(freqs[band][np.argmax(hps[band])])
    midi = 69 + 12 * math.log2(f0 / 440.0)
    m = int(round(midi))
    return {"note": f"{NOTES[m % 12]}{m // 12 - 1}", "midi": m, "hz": round(f0, 2),
            "cents_off": round((midi - m) * 100)}


def analyze(path: str, what: list[str] | None = None) -> dict:
    from fl_studio_mcp.audio import analysis as an
    p = _src(path)
    what = what or ["tempo", "key", "chords", "note"]
    wav = _wav(p)
    x = an.load(wav)
    out: dict[str, Any] = {"action": "analyze", "file": str(p)}
    gaps: list[str] = []
    bpm = None
    if "tempo" in what or "chords" in what:
        t = an.tempo(x)
        bpm = t["bpm"]
        if "tempo" in what:
            out["tempo"] = t
            if not t["agree"]:
                gaps.append(f"tempo estimators disagree ({t['autocorr']} vs {t['tempogram']}): "
                            "check by ear / tap")
    if "key" in what:
        k = an.key(x)
        out["key"] = {"key": f"{k['key']} {k['scale']}" if k["key"] else None,
                      "strength": k["strength"]}
        if (k["strength"] or 0) < 0.5:
            gaps.append(f"weak key estimate (strength {k['strength']})")
    if "chords" in what:
        merged: list[dict] = []
        for c in an.chords(x, bpm):
            name = chord_name(c["chord"])
            if merged and merged[-1]["chord"] == name:
                merged[-1]["end"] = round(c["end"], 2)
                if c["score"] is not None:
                    merged[-1]["score"] = min(merged[-1]["score"] or 1.0, c["score"])
            else:
                merged.append({"chord": name, "start": round(c["start"], 2),
                               "end": round(c["end"], 2), "score": c["score"]})
        out["chords"] = merged[:200]
        unsure = sum(1 for c in merged if c["score"] is not None and c["score"] < 0.8)
        if unsure:
            gaps.append(f"{unsure} chord segment(s) below 0.8 match (triads only; "
                        "7ths/sus chords show as their nearest triad)")
    if "note" in what:
        out["note"] = root_note(wav)
    out["gaps"] = gaps
    out["success"] = True
    return out


# ------------------------------------------------------------------ edit + load

def extract(path: str, start: float, end: float) -> dict:
    p = _src(path)
    if not 0 <= float(start) < float(end):
        return {"action": "extract", "success": False, "error": "need 0 <= start < end (seconds)"}
    out = _wav(p, ss=float(start), to=float(end), tag="extract")
    return {"action": "extract", "success": True, "file": str(out),
            "seconds": round(float(end) - float(start), 3)}


def split(path: str, side: str) -> dict:
    """One channel of a stereo file as MONO (FL: Edison 'convert left/right to mono')."""
    p = _src(path)
    s = side.lower()
    if s not in ("left", "right"):
        return {"action": "split", "success": False, "error": "side: left | right"}
    af = "pan=mono|c0=FL" if s == "left" else "pan=mono|c0=FR"
    out = _wav(p, extra_af=af, mono=True, tag=s)
    return {"action": "split", "success": True, "side": s, "file": str(out)}


def load(conn, path: str, name: str = "", pan: float | None = None,
         pitch: float | None = None) -> dict:
    """New Sampler channel (Add menu) holding `path`; pan -1..1 and pitch (semitones)
    set through the API and read back."""
    from fl_studio_mcp.tools.channel_v2 import fl_channel
    from fl_studio_mcp.tools.genre_v2 import _channel_index
    from fl_studio_mcp.tools.mixer_v2 import _exec
    from fl_studio_mcp.utils.sampler_load import load_sample_retry as load_sample
    p = _src(path)
    label = name or p.stem[:24]
    idx = _channel_index(conn, label)          # idempotent: reuse a channel of that name
    if idx is None:
        r = fl_channel("add", conn=conn, plugin="Sampler", name=label)
        if not r.get("success", r.get("ok")):
            return {"action": "load", "success": False, "error": f"add Sampler: {r.get('error')}"}
        # fl_channel returns the index nested in "result" (live 2026-10-06: int(None))
        got = r.get("index", (r.get("result") or {}).get("index"))
        idx = int(got) if got is not None else _channel_index(conn, label)
    if idx is None:
        return {"action": "load", "success": False, "error": f"channel {label!r} not found after add"}
    ls = load_sample(conn, idx, str(p), label=label, log=lambda m: None)
    out: dict[str, Any] = {"action": "load", "channel": idx, "name": label,
                           "sample_loaded": bool(ls.get("ok")), "error": ls.get("error")}
    if pan is not None:
        _exec(conn, f"import channels\nchannels.setChannelPan({idx}, {float(pan)})\nprint(1)")
    if pitch is not None:
        _exec(conn, f"import channels\nchannels.setChannelPitch({idx}, {float(pitch)}, 1)\nprint(1)")
    rb = json.loads(_exec(conn, f"import json, channels\nprint(json.dumps([channels.getChannelPan({idx}), "
                                f"channels.getChannelPitch({idx}, 1)]))"))
    out.update(pan=round(rb[0], 3), pitch=rb[1])
    ok = out["sample_loaded"] and (pan is None or abs(rb[0] - float(pan)) < 0.02) and \
        (pitch is None or abs(float(rb[1]) - float(pitch)) < 0.51)
    out["success"] = ok
    return out


def recorder(conn, on: bool = True, track: int = 0) -> dict:
    """Tip 9: Edison on the master, always capturing what plays ("On input" is
    Edison's default mode, live 2026-10-06). Edison is inserted when missing (picker
    by index); Record is a plain API param (index 1) - armed/disarmed and read back.
    FL's hint bar then says "Waiting for audio input..." until audio arrives."""
    from fl_studio_mcp.tools.mixer_tracks import list_fx
    from fl_studio_mcp.tools.mixer_v2 import _exec
    slot = next((x["slot"] for x in list_fx(conn, track) if x["plugin"].lower() == "edison"), None)
    inserted = False
    if slot is None:
        if not on:
            return {"action": "recorder", "success": True, "on": False, "note": "no Edison on that track"}
        from fl_studio_mcp.utils.add_effect import add_effect
        r = add_effect(track, "Edison", conn=conn, log=lambda m: None)
        if not r.get("ok"):
            return {"action": "recorder", "success": False, "error": f"insert Edison: {r.get('error')}"}
        slot, inserted = int(r["slot"]), True
    v = 1.0 if on else 0.0
    _exec(conn, f"import plugins, midi\nplugins.setParamValue({v}, 1, {track}, {slot}, midi.PIM_None, True)\nprint(1)")
    got = float(_exec(conn, f"import plugins\nprint(plugins.getParamValue(1, {track}, {slot}, True))"))
    ok = abs(got - v) < 0.01
    return {"action": "recorder", "success": ok, "on": got >= 0.5, "track": track, "slot": slot,
            "inserted": inserted,
            **({} if ok else {"error": f"Record read back {got}, wanted {v}"}),
            "note": "Edison records what reaches the master while armed (mode: On input)"}


def fl_audio(action: str, conn=None, **p: Any) -> dict:
    if action not in ACTIONS:
        return {"success": False, "error": f"unknown action {action!r}", "valid_actions": list(ACTIONS)}
    try:
        if action == "recorder":
            if conn is None:
                from fl_studio_mcp.utils.connection import get_connection
                conn = get_connection()
            return recorder(conn, p.get("on", True) is not False, int(p.get("track", 0) or 0))
        if not p.get("path"):
            return {"success": False, "error": f"{action}: path required"}
        if action == "analyze":
            return analyze(p["path"], p.get("what"))
        if action == "extract":
            return extract(p["path"], p.get("start", 0.0), p.get("end", 0.0))
        if action == "split":
            return split(p["path"], p.get("side", ""))
        if conn is None:
            from fl_studio_mcp.utils.connection import get_connection
            conn = get_connection()
        return load(conn, p["path"], p.get("name", ""), p.get("pan"), p.get("pitch"))
    except Exception as e:
        return {"action": action, "success": False, "error": str(e)}


def register_audio_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def fl_audio(action: str, path: str | None = None, what: list[str] | None = None,
                 start: float | None = None, end: float | None = None, side: str | None = None,
                 name: str | None = None, pan: float | None = None,
                 pitch: float | None = None, on: bool | None = None,
                 track: int | None = None) -> dict:
        """Audio FILES: analyze | extract | split | load | recorder.

        analyze(path, [what=tempo,key,chords,note]) -> tempo (two estimators + agreement),
        key, chord timeline, root note (808s, bass hits); gaps are reported.
        extract(path, start, end) -> a WAV of that section. split(path, side=left|right)
        -> a mono WAV of one channel. load(path, [name], [pan -1..1], [pitch semitones])
        -> a new Sampler channel holding it (pan/pitch read back).
        recorder([on=true], [track=0]) -> Edison on the master (inserted if missing)
        armed/disarmed to keep capturing what plays; read back.
        """
        args = {k: v for k, v in locals().items() if k != "action" and v is not None}
        from fl_studio_mcp.tools.audio_v2 import fl_audio as _impl
        return _impl(action, **args)

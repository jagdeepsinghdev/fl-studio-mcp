"""B3: fl_mixer — one tool for mixer-track control.

Actions: set_vol | set_pan | route | sends | add_fx | get_info | get_sends |
get_peaks | fix_clipping | get_eq | set_eq | eq_preset.
**remove_fx is NOT here** — it is destructive and lives in fl_delete
(target=fx). (plan §4 rule 3: destructive actions move to the delete tool.)

- set_vol / set_pan / route: writes, same-trip state_after + one undo.
- sends: write (setRouteTo + setRouteToLevel); src != dst enforced.
- add_fx: routes to the native Add-FX menu (the only reliable way to insert
  a plugin by name; the MCP has no importable add-plugin API — hard rule
  "no channels.add()", same gap). Documented as UI/menu method.

Schema: flat params + server-side validation (A6 oneOf pending).
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from fl_studio_mcp.tools.transport_v2 import _safe_send, shape_response  # reuse the safety send

ACTIONS = ("set_vol", "set_pan", "route", "sends", "add_fx",
           "get_info", "get_sends", "get_peaks", "fix_clipping",
           "get_eq", "set_eq", "eq_preset", "fx_on",
           # mixer_tracks.py (server-side via probe.exec, 2026-10-05)
           "name", "color", "mute", "solo", "stereo_sep",
           "route_only", "unroute", "list_fx", "add_tracks")
_TRACK_ACTIONS = ACTIONS[-9:]

_PARAM_SPEC = {
    "set_vol": (("track", "int", 0, None), ("volume", "float", 0.0, 1.0)),
    "set_pan": (("track", "int", 0, None), ("pan", "float", -1.0, 1.0)),
    "route": (("track", "int", 0, None), ("to", "int", 0, None)),
    "sends": (("track", "int", 0, None), ("to", "int", 0, None),
              ("level", "float", 0.0, 1.0)),
    "add_fx": (("track", "int", 0, None), ("plugin", "str", None, None)),
    "get_info": (("track", "int", 0, None),),
    "get_sends": (("track", "int", 0, None),),
    "get_peaks": (),          # track / window optional (checked below)
    "fix_clipping": (),       # track (default 0 = master), target_db, window
    "get_eq": (("track", "int", 0, None),),
    "set_eq": (("track", "int", 0, None), ("band", "int", 0, None)),
    "eq_preset": (("track", "int", 0, None), ("preset", "str", None, None)),
    "fx_on": (("track", "int", 0, None),),   # + on (bool), optional slot
}

#: eq_preset moves: (band selector, gain_db or None, freq_hz or None).
#: "low" = band 0, "mid" = band 1 (band 0 if only one), "top" = last band.
#: CONVENTION, NOT AUDITIONED: the band roles (low shelf / mid / high shelf)
#: and the dB/Hz numbers are starting points, not measured to sound right.
EQ_PRESETS: dict[str, list[tuple[str, float | None, float | None]]] = {
    "cut_mud": [("mid", -4.0, 250.0)],
    "high_pass_ish": [("low", -12.0, None)],
    "air": [("top", 3.0, 10000.0)],
    "reset": [("all", 0.0, None)],
}


def validate(action: str, params: dict[str, Any]) -> list[str]:
    if action not in ACTIONS:
        return [f"unknown action {action!r}. Valid: {', '.join(ACTIONS)}"]
    if action in _TRACK_ACTIONS:
        from fl_studio_mcp.tools.mixer_tracks import validate_track
        return validate_track(action, params)
    errs = []
    for name, kind, lo, hi in _PARAM_SPEC[action]:
        if name not in params:
            errs.append(f"{action}: missing required param '{name}'")
            continue
        v = params[name]
        if kind == "float":
            try:
                v = float(v)
            except (TypeError, ValueError):
                errs.append(f"{action}.{name}: not a number ({v!r})")
                continue
            if lo is not None and v < lo:
                errs.append(f"{action}.{name}: {v} < {lo}")
            if hi is not None and v > hi:
                errs.append(f"{action}.{name}: {v} > {hi}")
        elif kind == "int":
            if not isinstance(v, int) or isinstance(v, bool):
                errs.append(f"{action}.{name}: not an int ({v!r})")
            elif lo is not None and v < lo:
                errs.append(f"{action}.{name}: {v} < {lo}")
        elif kind == "str":
            if not isinstance(v, str) or not v.strip():
                errs.append(f"{action}.{name}: non-empty string required")
    if action == "get_peaks":
        t = params.get("track")
        if t is not None and (not isinstance(t, int) or isinstance(t, bool) or t < 0):
            errs.append(f"get_peaks.track: a mixer track index >= 0 ({t!r})")
        w = params.get("window", 0.5)
        try:
            if not 0.0 <= float(w) <= 5.0:
                errs.append(f"get_peaks.window: 0-5 seconds ({w})")
        except (TypeError, ValueError):
            errs.append(f"get_peaks.window: not a number ({w!r})")
    if action == "set_eq":
        given = [k for k in ("gain", "freq", "bw") if params.get(k) is not None]
        if not given:
            errs.append("set_eq: give at least one of gain/freq/bw (0-1 normalized)")
        for k in given:
            try:
                if not 0.0 <= float(params[k]) <= 1.0:
                    errs.append(f"set_eq.{k}: 0-1 normalized, got {params[k]}")
            except (TypeError, ValueError):
                errs.append(f"set_eq.{k}: not a number ({params[k]!r})")
    if action == "eq_preset" and isinstance(params.get("preset"), str) \
            and params["preset"] not in EQ_PRESETS:
        errs.append(f"eq_preset.preset: {params['preset']!r} unknown; "
                    f"valid: {', '.join(EQ_PRESETS)}")
    if action == "fix_clipping":
        t = params.get("track", 0)
        if not isinstance(t, int) or isinstance(t, bool) or t < 0:
            errs.append(f"fix_clipping.track: a mixer track index >= 0 ({t!r})")
        try:
            if not -24.0 <= float(params.get("target_db", -1.0)) <= 0.0:
                errs.append("fix_clipping.target_db: -24..0 dBFS")
        except (TypeError, ValueError):
            errs.append("fix_clipping.target_db: not a number")
    if action == "fx_on":
        if not isinstance(params.get("on"), bool):
            errs.append("fx_on.on: true (enable) or false (bypass) required")
        sl = params.get("slot")
        if sl is not None and (not isinstance(sl, int) or isinstance(sl, bool)
                               or not 0 <= sl <= 9):
            errs.append(f"fx_on.slot: 0-9 ({sl!r}); omit for every loaded slot")
    # sends: src != dst (the controller enforces too, but reject early)
    if action == "sends" and params.get("track") == params.get("to"):
        errs.append("sends: track and to must differ (src == dst)")
    if action == "route" and params.get("track") == params.get("to"):
        errs.append("route: track and to must differ")
    return errs


def _route(action: str, p: dict[str, Any]) -> tuple[str, dict]:
    if action == "set_vol":
        return "mixer.setTrackVolume", {"track": int(p["track"]),
                                       "volume": float(p["volume"])}
    if action == "set_pan":
        return "mixer.setTrackPan", {"track": int(p["track"]),
                                    "pan": float(p["pan"])}
    if action == "route":
        # route = enable the send to the target. Keep an existing send's level
        # (fl_mixer injects `_level`); 1.0 only for a brand-new route. A fixed
        # 1.0 silently raised the 808's master send 0.8 -> 1.0 (live L1).
        return "mixer.setSendLevel", {"track": int(p["track"]),
                                     "to": int(p["to"]),
                                     "level": float(p.get("_level", 1.0))}
    if action == "sends":
        return "mixer.setSendLevel", {"track": int(p["track"]),
                                     "to": int(p["to"]),
                                     "level": float(p.get("level", 1.0))}
    if action == "add_fx":
        # add_fx has no importable API; this is the UI/menu method.
        return "mixer.addFx", {"track": int(p["track"]),
                              "plugin": str(p["plugin"])}
    if action == "get_info":
        return "mixer.getTrackInfo", {"track": int(p["track"])}
    if action == "get_sends":
        return "mixer.getSends", {"track": int(p["track"])}
    if action == "get_peaks":
        return "mixer.getPeaks", {"track": int(p.get("track", -1))}
    if action == "get_eq":
        return "mixer.getEq", {"track": int(p["track"])}
    if action == "set_eq":
        out = {"track": int(p["track"]), "band": int(p["band"])}
        out.update({k: float(p[k]) for k in ("gain", "freq", "bw")
                    if p.get(k) is not None})
        return "mixer.setEq", out
    raise ValueError(f"unhandled action {action!r}")


# ---------------------------------------------------------------------------
# Per-track EQ (controller v10.4h — needs the FL restart deploy)
# ---------------------------------------------------------------------------

_EQ_NOT_DEPLOYED = ("controller v10.4h not deployed: restart FL after syncing the "
                    "controller (mixer.getEq/setEq answered 'Unknown action')")


def _is_unknown_action(r: Any) -> bool:
    return "unknown action" in str((r or {}).get("error", "")).lower()


def _read_eq(conn, track: int) -> dict:
    """mixer.getEq -> the controller payload; raises RuntimeError (clear text
    when the controller predates v10.4h)."""
    r = conn.send_command("mixer.getEq", {"track": int(track)})
    if _is_unknown_action(r):
        raise RuntimeError(_EQ_NOT_DEPLOYED)
    if not (isinstance(r, dict) and r.get("success")):
        raise RuntimeError((r or {}).get("error") or "mixer.getEq failed")
    return r


def _write_eq(conn, track: int, band: int, **vals: float) -> dict:
    ca, cp = _route("set_eq", {"track": track, "band": band, **vals})
    r = _safe_send(ca, cp, conn)
    if _is_unknown_action(r):
        raise RuntimeError(_EQ_NOT_DEPLOYED)
    if not r.get("success"):
        raise RuntimeError(r.get("error") or "mixer.setEq failed")
    return r


def _band(eq: dict, band: int) -> dict:
    for b in eq.get("bands") or []:
        if int(b.get("band", -1)) == int(band):
            return b
    raise RuntimeError(f"band {band} not in the read-back (band_count {eq.get('band_count')})")


def eq_get(conn, track: int) -> dict:
    try:
        eq = _read_eq(conn, track)
    except Exception as e:
        return {"action": "get_eq", "success": False, "error": str(e)}
    out = {"action": "get_eq", "success": True, "track": track,
           "band_count": eq.get("band_count"), "bands": eq.get("bands")}
    if eq.get("errors"):
        out["errors"] = eq["errors"]       # signature oracle (TypeError texts)
    return out


def eq_set(conn, track: int, band: int, gain=None, freq=None, bw=None) -> dict:
    """Set one band (normalized 0-1), then read it back in a SEPARATE trip."""
    vals = {k: float(v) for k, v in (("gain", gain), ("freq", freq), ("bw", bw))
            if v is not None}
    try:
        before = _band(_read_eq(conn, track), band)
        w = _write_eq(conn, track, band, **vals)
        after_eq = _read_eq(conn, track)
        after = _band(after_eq, band)
    except Exception as e:
        return {"action": "set_eq", "success": False, "error": str(e)}
    out = {"action": "set_eq", "success": True, "track": track, "band": band,
           "set": vals, "before": before, "after": after}
    if w.get("undo_saved"):
        out["undo_saved"] = w["undo_saved"]
    errs = (w.get("errors") or []) + (after_eq.get("errors") or [])
    if errs:
        out["errors"] = errs
    return out


def _solve(conn, track: int, band: int, kind: str, target: float,
           iters: int = 12) -> dict:
    """Find the NORMALIZED gain/freq whose real unit (gain_db / freq_hz, the
    mode=1 getter) equals `target`, by bisection (assumes monotonic). Each
    probe is set in one trip, read in the next. Leaves the band at the best
    value; `exact` False when the target is outside the range or unreachable."""
    unit = "gain_db" if kind == "gain" else "freq_hz"
    tol = 0.1 if kind == "gain" else abs(target) * 0.02
    cur = _band(_read_eq(conn, track), band)
    if cur.get(unit) is not None and abs(cur[unit] - target) <= tol:
        return {"norm": cur[kind], unit: cur[unit], "exact": True, "probes": 0}
    lo, hi = 0.0, 1.0
    best = None
    probes = 0
    for _ in range(iters):
        mid = (lo + hi) / 2
        _write_eq(conn, track, band, **{kind: mid})
        probes += 1
        got = _band(_read_eq(conn, track), band).get(unit)
        if got is None:
            raise RuntimeError(f"getter returned no {unit}: cannot solve (see get_eq errors)")
        if best is None or abs(got - target) < abs(best[1] - target):
            best = (mid, got)
        if abs(got - target) <= tol:
            break
        if got < target:
            lo = mid
        else:
            hi = mid
    if abs(best[1] - target) > tol:         # restore the best probe, not the last
        _write_eq(conn, track, band, **{kind: best[0]})
    return {"norm": best[0], unit: best[1], "exact": abs(best[1] - target) <= tol,
            "probes": probes}


def eq_preset(conn, track: int, preset: str) -> dict:
    """Named EQ moves (CONVENTION, NOT AUDITIONED). The neutral/target values
    are looked up through the getter's real-unit mode, never hard-coded."""
    moves = EQ_PRESETS[preset]
    try:
        eq = _read_eq(conn, track)
        n = int(eq.get("band_count") or 0)
        if n < 1:
            raise RuntimeError("track reports 0 EQ bands")
        sel = {"low": [0], "mid": [1 if n > 1 else 0], "top": [n - 1],
               "all": list(range(n))}
        done = []
        for which, gain_db, freq_hz in moves:
            for b in sel[which]:
                step = {"band": b}
                if freq_hz is not None:
                    step["freq"] = _solve(conn, track, b, "freq", freq_hz)
                if gain_db is not None:
                    step["gain"] = _solve(conn, track, b, "gain", gain_db)
                done.append(step)
        after = _read_eq(conn, track)
    except Exception as e:
        return {"action": "eq_preset", "success": False, "error": str(e)}
    return {"action": "eq_preset", "success": True, "track": track, "preset": preset,
            "convention": "starting point, not auditioned: band roles assumed "
                          "low/mid/high; verify by ear",
            "moves": done, "exact": all(v.get("exact") for s_ in done
                                         for v in s_.values() if isinstance(v, dict)),
            "after": after.get("bands")}


# v10.4f controllers have no mixer.getPeaks: the same read via the generic
# probe.exec (a fixed, read-only snippet; precedent: markers / delete).
_PEAKS_SNIPPET = """
import json, mixer, transport
t = {track}
tracks = range(mixer.trackCount()) if t < 0 else [t]
print(json.dumps({{"peaks": [[i, mixer.getTrackPeaks(i, 0), mixer.getTrackPeaks(i, 1)]
                            for i in tracks],
                  "master_last": [mixer.getLastPeakVol(0), mixer.getLastPeakVol(1)],
                  "playing": bool(transport.isPlaying())}}))
"""
_PEAK_INTERVAL = 0.1


def _read_peaks(conn, track: int) -> dict:
    r = conn.send_command("mixer.getPeaks", {"track": track})
    if isinstance(r, dict) and r.get("success") and "peaks" in r:
        return {**r, "via": "mixer.getPeaks"}
    if "unknown action" not in str((r or {}).get("error", "")).lower():
        raise RuntimeError((r or {}).get("error") or "mixer.getPeaks failed")
    import json
    r = conn.send_command("probe.exec", {"code": _PEAKS_SNIPPET.format(track=int(track))})
    if not (isinstance(r, dict) and r.get("success")):
        raise RuntimeError((r or {}).get("error") or "probe.exec failed")
    return {**json.loads(r.get("stdout", "").strip().splitlines()[-1]),
            "via": "probe.exec"}


def _db(x: float) -> float | None:
    import math
    return round(20 * math.log10(x), 2) if x > 0 else None


def get_peaks(conn, track: int | None = None, window: float = 0.5,
              sleep=None, interval: float = _PEAK_INTERVAL) -> dict:
    """Sample the meters every 0.1 s for `window` seconds and keep each
    track's maximum (the meters decay within ~0.2 s, so one read misses
    transients). Linear amplitude: 1.0 = 0 dBFS; > 1.0 = clipping."""
    import time
    sleep = sleep or time.sleep
    n = max(1, int(round(float(window) / interval)) + 1)
    best: dict[int, list[float]] = {}
    last = [0.0, 0.0]
    playing = False
    via = None
    for k in range(n):
        r = _read_peaks(conn, -1 if track is None else int(track))
        via = r["via"]
        playing = playing or bool(r.get("playing"))
        for i, left, right in r["peaks"]:
            b = best.setdefault(int(i), [0.0, 0.0])
            b[0], b[1] = max(b[0], float(left)), max(b[1], float(right))
        ml = r.get("master_last") or [0.0, 0.0]
        last = [max(last[0], float(ml[0])), max(last[1], float(ml[1]))]
        if k + 1 < n:
            sleep(interval)
    tracks = []
    for i, (left, right) in sorted(best.items()):
        pk = max(left, right)
        tracks.append({"track": i, "peak": round(pk, 4), "left": round(left, 4),
                       "right": round(right, 4), "dbfs": _db(pk),
                       "clipping": pk > 1.0})
    out = {"action": "get_peaks", "success": True, "window_s": float(window),
           "samples": n, "playing": playing, "via": via,
           "clipping": any(t["clipping"] for t in tracks),
           "master_last": [round(v, 4) for v in last]}
    if track is None:
        out["tracks"] = [t for t in tracks if t["peak"] > 0 or t["track"] == 0]
    else:
        out["tracks"] = tracks
    if not playing and all(t["peak"] == 0 for t in tracks):
        out["note"] = "silent: FL is not playing (meters read 0 when nothing sounds)"
    return out


# FL applies mixer.setTrackVolume AFTER the script trip returns: a read in
# the SAME trip returns the previous value (live 2026-10-02: set 0.5 -> read
# 0.6, the prior set; a one-trip binary search drove the master fader to 0 =
# silence). So every fader step is set in one trip and read in the NEXT.
def _set_fader(conn, track: int, v: float) -> None:
    conn.send_command("probe.exec", {"code": (
        f"import mixer\nmixer.setTrackVolume({int(track)}, {float(v)!r})")})


def _fader_for_db(conn, track: int, want_db: float, hi: float,
                  steps: int = 14) -> dict:
    """Binary-search fader in [0, hi] whose dB (read next trip) <= want_db;
    leaves the fader there. Never ends louder than it started."""
    lo = 0.0
    best = None
    for _ in range(steps):
        mid = (lo + hi) / 2
        _set_fader(conn, track, mid)
        db = _fader(conn, track)["db"]
        if db > want_db:
            hi = mid
        else:
            lo, best = mid, mid
    final = best if best is not None else lo
    _set_fader(conn, track, final)
    return _fader(conn, track)


def _fader(conn, track: int) -> dict:
    import json
    r = conn.send_command("probe.exec", {"code": (
        "import json, mixer\n"
        f"print(json.dumps({{'fader': mixer.getTrackVolume({int(track)}), "
        f"'db': mixer.getTrackVolume({int(track)}, 1)}}))")})
    return json.loads(r.get("stdout", "").strip().splitlines()[-1])


def _loop_seconds(conn) -> float:
    """One full loop of the active pattern (pattern length x beat length)."""
    st = (conn.send_command("state.snapshot", {}) or {}).get("state") or {}
    bpm = float(st.get("bpm") or 120.0)
    sel = st.get("selected_pattern") or 1
    beats = next((p.get("length_beats") for p in st.get("patterns") or []
                  if p.get("pattern") == sel), None) or 16
    return float(beats) * 60.0 / bpm


def fix_clipping(conn, track: int = 0, target_db: float = -1.0,
                 window: float | None = None, passes: int = 2,
                 sleep=None) -> dict:
    """Keep the track's OUTPUT peak at or below `target_db`.

    Live facts (2026-10-02): FL's track meter (getTrackPeaks) reads BEFORE
    the track's own fader (a 5 dB master-fader cut moved it ~1 dB, i.e.
    noise), and a decaying meter sampled every 0.1 s varies about ±1 dB
    between loops. So: measure the pre-fader peak as the max over `passes`
    full loops from the top at 0.05 s sampling, then set the fader so that
    pre-fader peak + fader dB = target (exact, via the fader's dB read-back
    on the NEXT trip). The output peak is computed, not re-metered: no
    post-fader meter exists in the API. Runs automatically after fl_preset loads.
    """
    import time
    sleep = sleep or time.sleep
    st = conn.send_command("state.snapshot", {})
    was_playing = bool(((st or {}).get("state") or {}).get("transport", {}).get("is_playing"))
    win = float(window) if window else min(30.0, _loop_seconds(conn) + 0.3)

    def measure_pre() -> float | None:
        best = 0.0
        for _ in range(max(1, passes)):
            conn.send_command("transport.stop", {})
            conn.send_command("transport.setPosition", {"position": 0.0, "mode": 2})
            conn.send_command("transport.start", {})
            sleep(0.3)
            r = get_peaks(conn, track, win, sleep=sleep, interval=0.05)
            if r.get("tracks"):
                best = max(best, r["tracks"][0]["peak"])
        return _db(best) if best > 0 else None

    start = _fader(conn, track)
    out = {"action": "fix_clipping", "success": True, "track": track,
           "target_db": target_db, "window_s": round(win, 2), "passes": passes,
           "fader_before_db": round(start["db"], 2)}
    try:
        pre = measure_pre()
        out["prefader_peak_dbfs"] = pre
        if pre is None:
            out["note"] = "silent: nothing to measure (no sound on this track)"
            return out
        out_before = round(pre + start["db"], 2)
        out["output_peak_before_dbfs"] = out_before
        if out_before <= target_db:
            out.update(changed=False, note=f"output peak {out_before} dBFS already <= {target_db}")
            return out
        want = target_db - pre
        new = _fader_for_db(conn, track, want, hi=max(float(start["fader"]), 1.0))
        if new["db"] < start["db"] - 24:      # never silence a track
            _set_fader(conn, track, float(start["fader"]))
            out.update(success=False, changed=False,
                       error="fader search went below -24 dB; restored the original fader")
            return out
        out.update(changed=True, fader_after_db=round(new["db"], 2),
                   gain_change_db=round(new["db"] - start["db"], 2),
                   output_peak_after_dbfs=round(pre + new["db"], 2),
                   verified=round(pre + new["db"], 2) <= target_db,
                   method="pre-fader peak (max of passes) + fader dB; computed, "
                          "not re-metered (no post-fader meter in the API)")
        return out
    finally:
        conn.send_command("transport.stop", {})
        if was_playing:
            conn.send_command("transport.start", {})


def _exec(conn, code: str) -> str:
    r = conn.send_command("probe.exec", {"code": code}, timeout=10.0)
    if not (isinstance(r, dict) and r.get("success")):
        raise RuntimeError((r or {}).get("error") or "probe.exec failed")
    return (r.get("stdout") or "").strip().splitlines()[-1]


def fx_on(conn, track: int, on: bool, slot: int | None = None,
          sleep=None) -> dict:
    """Enable (on=True) or bypass (on=False) effect slots — A/B by ear.

    Uses FL's documented REC event `pluginId + midi.REC_Plug_Mute` via
    general.processRECEvent (value 1 = slot ON). NOT mixer.setPluginMuteState:
    live 2026-10-03 it switched slots OFF but never back ON (value 0/1/True).
    Read-back: mixer.getPluginMuteState (1 = on), in a separate trip.
    """
    import json
    import time
    sleep = sleep or time.sleep
    slots = list(range(10)) if slot is None else [int(slot)]
    loaded = json.loads(_exec(conn, (
        "import json, plugins\n"
        f"print(json.dumps([[s, plugins.getPluginName({track}, s)] for s in {slots} "
        f"if plugins.isValid({track}, s)]))")))
    if not loaded:
        return {"action": "fx_on", "success": False, "track": track,
                "error": f"no plugin in slot(s) {slots} on track {track}"}
    idx = [s for s, _ in loaded]
    _exec(conn, (
        "import mixer, midi, general\n"
        f"for s in {idx}:\n"
        f"    general.processRECEvent(mixer.getTrackPluginId({track}, s) + "
        f"midi.REC_Plug_Mute, {1 if on else 0}, "
        "midi.REC_UpdateValue | midi.REC_UpdateControl)\n"
        "print('ok')"))
    sleep(0.4)   # FL applies after the trip; read in the next one
    state = json.loads(_exec(conn, (
        "import json, mixer\n"
        f"print(json.dumps([mixer.getPluginMuteState({track}, s) for s in {idx}]))")))
    after = [{"slot": s, "plugin": n, "on": bool(v)}
             for (s, n), v in zip(loaded, state)]
    ok = all(a["on"] == on for a in after)
    return {"action": "fx_on", "success": ok, "track": track, "on": on,
            "slots": after,
            **({} if ok else {"error": "read-back disagrees (see slots)"})}


def fl_mixer(action: str, conn=None, **params: Any) -> dict:
    """Control a FL Studio mixer track (one tool, 8 actions).

    Actions:
      set_vol (track, volume 0-1)
      set_pan (track, pan -1..1)
      route (track, to) — enable the send (keeps an existing send's level;
          1.0 for a new route)
      sends (track, to, level 0-1) — a partial send; src != dst
      add_fx (track, plugin) — insert an effect by name via the native
          Add ▸ Effect ▸ More plugins… picker; verified by the slot read-back
          (returns track, slot, plugin, slots). FL frontmost, mouse untouched.
      get_info (track) — name, volume (0-1 and dB), pan, mute/solo/arm
      get_sends (track) — [{to, level}] of the track's active sends
      get_peaks ([track], [window=0.5]) — peak meters sampled over `window`
          seconds: per track peak (linear, 1.0 = 0 dBFS), dbfs, clipping
          (> 1.0); no track = every track that made sound + the master (0)
      fix_clipping ([track=0], [target_db=-1.0], [window=one loop]) — measure
          the real peak over one full loop from the top, lower the fader by
          exactly the excess (dB read-back), re-measure the same loop (up to 3
          rounds); runs automatically after every fl_preset load
      get_eq (track) — the track's parametric EQ: per band normalized gain/freq/bw
          plus gain_db / freq_hz (needs controller v10.4h deployed)
      set_eq (track, band, [gain], [freq], [bw]) — normalized 0-1; read back in a
          separate trip (needs controller v10.4h deployed)
      eq_preset (track, preset: cut_mud|high_pass_ish|air|reset) — named band moves
          solved through the real-unit getters (convention, not auditioned)

    remove_fx is NOT here: it is destructive and lives in fl_delete
    (target=fx). Writes carry same-trip state_after + one named undo.
    """
    errs = validate(action, params)
    if errs:
        return {"success": False, "error": "; ".join(errs),
                "valid_actions": list(ACTIONS)}


    if conn is None:
        from fl_studio_mcp.utils.connection import get_connection
        conn = get_connection()

    if action in _TRACK_ACTIONS:
        from fl_studio_mcp.tools.mixer_tracks import run_track_action
        try:
            return run_track_action(action, conn, params)
        except Exception as e:
            return {"action": action, "success": False, "error": str(e)}

    if action == "add_fx":
        # No importable add-plugin API in v45: the native Add ▸ Effect ▸ More
        # plugins… picker (utils/add_effect.py), verified by the slot read-back.
        # (L2: the old controller route hit "Unknown action" + a spurious undo.)
        import sys
        if sys.platform != "darwin":
            return {"action": action, "success": False,
                    "error": "add_fx drives the macOS menus (darwin only)"}
        from fl_studio_mcp.utils.add_effect import add_effect
        try:
            r = add_effect(int(params["track"]), str(params["plugin"]), conn=conn,
                           log=lambda m: None)
        except Exception as e:
            return {"action": action, "success": False, "error": str(e)}
        out = {"action": action, "success": bool(r.get("ok")),
               **{k: v for k, v in r.items() if k != "ok"}}
        return out

    if action == "get_eq":
        return eq_get(conn, int(params["track"]))
    if action == "set_eq":
        return eq_set(conn, int(params["track"]), int(params["band"]),
                      params.get("gain"), params.get("freq"), params.get("bw"))
    if action == "eq_preset":
        return eq_preset(conn, int(params["track"]), str(params["preset"]))

    if action == "fx_on":
        try:
            return fx_on(conn, int(params["track"]), bool(params["on"]),
                         params.get("slot"))
        except Exception as e:
            return {"action": action, "success": False, "error": str(e)}

    if action == "fix_clipping":
        try:
            return fix_clipping(conn, int(params.get("track", 0)),
                                float(params.get("target_db", -1.0)),
                                params.get("window"))
        except Exception as e:
            return {"action": action, "success": False, "error": str(e)}

    if action == "get_peaks":
        try:
            return get_peaks(conn, params.get("track"),
                             float(params.get("window", 0.5)))
        except Exception as e:
            return {"action": action, "success": False, "error": str(e)}

    if action == "route":
        cur = conn.send_command("mixer.getSends", {"track": int(params["track"])})
        for snd in (cur.get("sends") or []) if isinstance(cur, dict) else []:
            if int(snd.get("to", -1)) == int(params["to"]) and snd.get("level") is not None:
                params = dict(params, _level=float(snd["level"]))
                break

    ca, cparams = _route(action, params)
    try:
        res = _safe_send(ca, cparams, conn)
    except Exception as e:
        return {"action": action, "success": False, "error": str(e)}

    return shape_response(action, res)


def register_mixer_tools_v2(mcp: FastMCP) -> None:
    """Register the B3 fl_mixer tool."""
    from fl_studio_mcp.tools.mixer_v2 import fl_mixer as _impl

    @mcp.tool()
    def fl_mixer(
        action: str,
        track: int | None = None,
        volume: float | None = None,
        pan: float | None = None,
        to: int | None = None,
        level: float | None = None,
        plugin: str | None = None,
        window: float | None = None,
        target_db: float | None = None,
        band: int | None = None,
        gain: float | None = None,
        freq: float | None = None,
        bw: float | None = None,
        preset: str | None = None,
        on: bool | None = None,
        slot: int | None = None,
        name: str | None = None,
        color: str | None = None,
        value: float | None = None,
        count: int | None = None,
    ) -> dict:
        """Control a FL Studio mixer track (one tool, 21 actions).

        Actions: set_vol(track, volume 0-1) | set_pan(track, pan -1..1) |
        route(track, to) (keeps an existing send level) |
        sends(track, to, level 0-1) | get_info(track) | get_sends(track) |
        add_fx(track, plugin) (native picker, slot-verified) |
        get_peaks([track], [window=0.5 s]) — peak meters: linear peak
        (1.0 = 0 dBFS), dbfs, clipping; no track = all sounding tracks + master |
        fix_clipping([track=0], [target_db=-1]) — measure while playing, lower
        the fader by exactly the excess, re-measure (auto after preset loads).
        get_eq(track) | set_eq(track, band, [gain], [freq], [bw] — 0-1 normalized) |
        eq_preset(track, cut_mud|high_pass_ish|air|reset) — per-track parametric
        EQ; needs controller v10.4h deployed (FL restart); presets are convention,
        not auditioned.
        fx_on(track, on, [slot]) — enable (true) / bypass (false) a track's effect
        slots (all loaded ones when slot is omitted), read back — A/B by ear.
        Track housekeeping (read back next trip): name(track, name) |
        color(track, color "#RRGGBB") | mute(track, on) | solo(track, on) |
        stereo_sep(track, value -1 mono..1 wide) | route_only(track, to) — FL's
        "route to this track only" (all other routes incl. master OFF) |
        unroute(track, to) | list_fx(track) — slots: plugin, on |
        add_tracks(count) — new inserts via the mixer "+" (hint-confirmed, trackCount proof).
        remove_fx is NOT here (destructive → fl_delete target=fx).
        Writes carry same-trip state_after + one named undo.
        """
        p = {k: v for k, v in {"name": name, "color": color, "value": value, "count": count,
             "track": track, "volume": volume, "pan": pan,
             "to": to, "level": level, "plugin": plugin,
             "window": window, "target_db": target_db, "band": band,
             "gain": gain, "freq": freq, "bw": bw, "preset": preset,
             "on": on, "slot": slot}.items() if v is not None}
        return _impl(action, **p)

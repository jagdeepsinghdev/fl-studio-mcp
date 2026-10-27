"""fl_preset(action="load_song"): a song folder into FL in one call.

The folder holds ready presets plus a ``song.json`` manifest (paths relative to
the folder; any producer may write it, e.g. an analysis app or a hand-made set):

    {"label": "MySong", "bpm": 93.75,
     "beat": "beat.json", "melody": "melody.json",
     "bass": "bass.json",                          # FLEX bass line (fallback)
     "bass_sample": "bass-sample.json",            # bass line mapped to the sample
     "bass_sample_wav": "bass-hit.wav"}            # the original bass hit
    (every key optional except at least one of beat / melody / bass)

Steps, each verified by the tool it reuses:
  1. tempo = bpm
  2. beat -> the 808 rack (tiled to the pattern)
  3. melody -> "<label> Melody" (FLEX; created + routed when missing)
  4. bass -> "<label> Bass" Sampler holding bass_sample_wav, loaded through the
     Sampler's own Open panel (utils/sampler_load; verified by FL renaming the
     channel after the file); FLEX + "bass" when there is no sample
  5. fl_mixer fix_clipping on the master
FL must be frontmost and the mouse untouched (steps 3-4 use FL's menus).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

MANIFEST = "song.json"
PRESET_KEYS = ("beat", "melody", "bass", "bass_sample", "bass_sample_wav")


def _channel_index(conn, name: str) -> int | None:
    chans = conn.send_command("channels.getAll").get("channels", [])
    return next((c["index"] for c in chans
                 if (c.get("name") or "").strip().lower() == name.lower()), None)


def _channel(conn, name: str) -> dict | None:
    chans = conn.send_command("channels.getAll").get("channels", [])
    return next((c for c in chans
                 if (c.get("name") or "").strip().lower() == name.lower()), None)


def _ensure_channel(conn, name: str, plugin: str, log) -> dict:
    ch = _channel(conn, name)
    if ch is not None:
        log(f"channel '{name}' exists (#{ch['index']})")
        return {"ok": True, "index": ch["index"], "name": name,
                "mixer_track": ch.get("target_fx_track")}
    from fl_studio_mcp.utils.add_channel import setup_instrument
    r = setup_instrument(plugin, name)
    log(f"channel '{name}' ({plugin}) added: {r.get('ok')} #{r.get('index')}")
    return {**r, "name": name}


def read_manifest(d: Path) -> dict[str, Any]:
    """song.json with preset paths resolved against the folder; raises ValueError."""
    f = d / MANIFEST
    if not f.is_file():
        raise ValueError(f"no {MANIFEST} in {d} (see fl_preset load_song docs for the format)")
    m = json.loads(f.read_text())
    if not any(m.get(k) for k in ("beat", "melody", "bass")):
        raise ValueError(f"{f} lists none of beat / melody / bass")
    for k in PRESET_KEYS:
        if m.get(k):
            p = Path(m[k]).expanduser()
            p = p if p.is_absolute() else d / p
            if not p.is_file():
                raise ValueError(f"{MANIFEST} '{k}': no such file {p}")
            m[k] = str(p)
    return m


def _bass_sample_into(conn, ch: dict, wav: str, log) -> dict:
    """Edison route: open on the channel's mixer track, load the cut, send it
    to the Sampler, then take Edison back out of that track."""
    from fl_studio_mcp.utils import edison_flow as ef
    from fl_studio_mcp.utils.add_effect import select_track, track_slots
    from fl_studio_mcp.utils.remove_effect import remove_effect
    track = int(ch.get("mixer_track") or 0)
    select_track(conn, track)
    steps = {"open": ef.open_edison(),}
    if steps["open"]["ok"]:
        steps["load"] = ef.load_regions(wav, [], clear_regions=True)
    if steps.get("load", {}).get("ok"):
        steps["send"] = ef.send_to_channel(channel=ch["index"], expected=0)
    if steps.get("send", {}).get("ok"):
        # FL renames a Sampler after its new file ('mysong-bass-25_2'):
        # put the label back so the next load_song finds this channel again
        conn.send_command("channels.setName", {"index": ch["index"],
                                               "name": ch["name"], "use_global": True})
    slots = track_slots(conn, track)
    if "Edison" in slots:
        remove_effect(track, slots.index("Edison"), expect="Edison", conn=conn,
                      log=lambda m: None)
    ok = all(s.get("ok") for s in steps.values()) and len(steps) == 3
    log(f"bass sample -> '{ch['index']}': {ok} "
        f"({ {k: v.get('error') for k, v in steps.items() if not v.get('ok')} })")
    return {"ok": ok, "wav": steps.get("send", {}).get("wav"),
            **({} if ok else {"error": next(v.get("error") for v in steps.values()
                                             if not v.get("ok"))})}


def _clear_editors() -> None:
    """Before piano-roll work: no plugin editor over the roll (fl_panels)."""
    from fl_studio_mcp.utils.fl_panels import clear_plugins
    clear_plugins()


def _notes_with_retry(pv, path: str, pattern: int, channel: int, log) -> dict:
    """load_melody; when the roll script did not run (selection lost, roll
    covered — seen 2026-10-02 even after a clean run), re-select the script
    for THIS channel once and retry. The failed attempt already withdrew its
    queued notes, so a retry cannot double-write."""
    r = pv.load_melody(path=path, target_pattern=pattern, channel_index=channel,
                       auto_level=False)
    if r.get("ok") or r.get("script_ran", True):
        return r
    log(f"script did not run for channel {channel}: re-selecting and retrying once")
    from fl_studio_mcp.tools.select_script import fl_select_script
    _clear_editors()
    fl_select_script(channel_index=channel)
    return pv.load_melody(path=path, target_pattern=pattern, channel_index=channel,
                          auto_level=False)


def load_song(song_dir: str, label: str = "", target_pattern: int = 1,
              conn=None, log=print) -> dict[str, Any]:
    from fl_studio_mcp.tools import preset_v2 as pv
    from fl_studio_mcp.tools.mixer_v2 import fix_clipping
    if conn is None:
        from fl_studio_mcp.utils.connection import get_connection
        conn = get_connection()
    d = Path(song_dir).expanduser()
    try:
        pre = read_manifest(d)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    label = (label or pre.get("label") or d.name).strip()
    steps: dict[str, Any] = {}

    st0 = (conn.send_command("state.snapshot", {}) or {}).get("state") or {}
    was_playing = bool((st0.get("transport") or {}).get("is_playing"))

    bpm = pre.get("bpm")
    if bpm:
        conn.send_command("transport.setBPM", {"bpm": float(bpm)})
        steps["tempo"] = {"ok": True, "bpm": bpm}

    if pre.get("beat"):
        r = pv.load_beat(path=pre["beat"], target_pattern=target_pattern,
                         auto_level=False)
        steps["beat"] = {k: r.get(k) for k in ("ok", "written", "filled_to_steps", "error")}

    if pre.get("melody"):
        ch = _ensure_channel(conn, f"{label} Melody", "FLEX", log)
        if ch.get("ok"):
            _clear_editors()
            r = _notes_with_retry(pv, pre["melody"], target_pattern, ch["index"], log)
            steps["melody"] = {"channel": ch["index"],
                               **{k: r.get(k) for k in ("ok", "notes_queued", "script_ran", "error")}}
        else:
            steps["melody"] = {"ok": False, "error": ch.get("error")}

    if pre.get("bass_sample") and pre.get("bass_sample_wav"):
        ch = _ensure_channel(conn, f"{label} Bass", "Sampler", log)
        if ch.get("ok"):
            # the Sampler's own Open panel (utils/sampler_load) — not Edison:
            # the plugin picker twice confirmed the wrong row (2026-10-02)
            from fl_studio_mcp.utils.sampler_load import load_sample
            s = load_sample(conn, ch["index"], pre["bass_sample_wav"],
                            label=ch.get("name") or f"{label} Bass", log=log)
            if not s.get("ok"):          # one retry (panel timing, 2026-10-02)
                log(f"sample load failed ({s.get('error')}); retrying once")
                s = load_sample(conn, ch["index"], pre["bass_sample_wav"],
                                label=ch.get("name") or f"{label} Bass", log=log)
            _clear_editors()
            r = (_notes_with_retry(pv, pre["bass_sample"], target_pattern, ch["index"], log)
                 if s["ok"] else {"ok": False, "error": s.get("error")})
            steps["bass"] = {"channel": ch["index"], "source": "original sample",
                             "sample_sent": s["ok"],
                             **{k: r.get(k) for k in ("ok", "notes_queued", "error")}}
    elif pre.get("bass"):
        ch = _ensure_channel(conn, f"{label} Bass", "FLEX", log)
        if ch.get("ok"):
            _clear_editors()
            r = _notes_with_retry(pv, pre["bass"], target_pattern, ch["index"], log)
            steps["bass"] = {"channel": ch["index"], "source": "FLEX (no sample)",
                             **{k: r.get(k) for k in ("ok", "notes_queued", "error")}}

    time.sleep(0.5)
    lvl = fix_clipping(conn, 0, -1.0)
    steps["level"] = {k: lvl.get(k) for k in ("changed", "output_peak_before_dbfs",
                                              "fader_after_db", "output_peak_after_dbfs",
                                              "note", "error") if lvl.get(k) is not None}
    if not was_playing:          # leave the transport the way we found it
        conn.send_command("transport.stop", {})
    ok = all(v.get("ok", True) for v in steps.values() if isinstance(v, dict))
    return {"ok": ok, "label": label, "steps": steps}

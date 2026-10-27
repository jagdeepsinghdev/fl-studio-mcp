"""fl_preset — load beat and melody presets. The legacy
fl_list_presets / fl_load_beat / fl_load_melody were retired 2026-10-01
(end of their one migration cycle); `fl_preset` is the first-class path
for the §3 "build a track" recipe:

    fl_preset(action="load_beat",  preset="trap", target_pattern=1)
    fl_preset(action="load_melody", preset="a-minor-pop", target_pattern=1)

Actions:
  list        list preset ids (registry + .generated/)
  load_beat   write each drum part to the matching channel (exact-name,
              then keyword match) in `target_pattern`, then — S2.3 — apply
              the preset's per-step velocities/shifts/repeats arrays as FL
              step parameters (P4's setStepParameter; active steps only).
              repeats -> pRepeat (v45 constant 8, P4-CLOSED) — best effort;
              the result reports applied vs failed counts (known issue #1).
              Tempo: base_bpm>0 sets the playback-speed multiplier to reach
              the preset BPM; base_bpm=0 (default) leaves tempo untouched
              (safe for live sessions — the speed multiplier STACKS with
              the real BPM, CLAUDE.md §2.1).
  load_melody select `target_pattern`, queue the melody notes + chord hits
              to the active channel's piano roll through the ComposeWithLLM
              request queue, and (best-effort) trigger the script.

macOS-only behavior is inherited from the connection layer; everything is
one shared MCP command/response pair (sequential trips, never parallel).
"""

from __future__ import annotations

import subprocess
import sys
import time
from typing import Any

from fl_studio_mcp.preset_paths import list_presets, resolve_preset
from fl_studio_mcp.utils.connection import get_connection

#: drum-ish channel names (the clear-all pass targets these)
_DRUM_KEYWORDS = ("kick", "snare", "clap", "hat", "808", "drum", "perc", "shaker", "rim")

#: generated-preset per-step arrays -> FL step-param names.
#: pVelocity=1, pShift=7 (P4; official midi stubs define exactly these 8
#: types — pPitch..pShift — there is NO pRepeat; the channel-rack "step
#: repeat" UI feature has no Python API in v45). A param only takes effect
#: on an ACTIVE step, so non-hit steps and zero values are never written.
#:
#: LIVE FINDING (2026-10-02, 808-rack session, v10.4d): persistence is
#: PER-CHANNEL-INSTANCE — in that session velocity stuck on all 5 channels
#: but shift/pan stuck only on ch0/ch4 and were silently dropped on
#: ch1/ch2/ch3 (writes raise no error; same-trip read-back = -1). The
#: writer issues all writes; interpret read-backs per channel.
_STEP_PARAM_ARRAYS = (
    ("velocities", "pVelocity"),
    ("shifts", "pShift"),
    ("repeats", "pRepeat"),
)


def _apply_step_params(conn, channel_index: int, pattern: list[bool],
                       spec: dict[str, Any], target_pattern: int
                       ) -> tuple[dict[str, int], list[str]]:
    """Write a part's per-step parameters onto the ACTIVE steps.
    Returns ({param_name: writes_issued}, [error messages]).
    Plain presets (no arrays) = no-op. (v10.4f+ issue #1: repeats now go
    through pRepeat, v45 constant 8 — the old code skipped them as 'no API'.)"""
    counts: dict[str, int] = {}
    errors: list[str] = []
    for arr_key, param_name in _STEP_PARAM_ARRAYS:
        arr = spec.get(arr_key)
        if not isinstance(arr, list):
            continue
        for i, bit in enumerate(pattern):
            if not bit or i >= len(arr):
                continue
            val = int(arr[i] or 0)
            if val <= 0:
                continue
            r = conn.send_command(
                "channels.setStepParameter",
                {"channel": channel_index, "step": i, "param": param_name,
                 "value": val, "target_pattern": target_pattern},
                timeout=5.0,
            )
            if r.get("success", True) and "error" not in r:
                counts[param_name] = counts.get(param_name, 0) + 1
            else:
                errors.append(f"{param_name}@{i}: {r.get('error', 'no success')}")
    return counts, errors


def _resolve_channel(spec: dict, part: str,
                     name_to_idx: dict[str, int]) -> int:
    """Exact channel-name match first, then a part-keyword fallback."""
    idx = name_to_idx.get((spec.get("name") or "").strip().lower(), -1)
    if idx >= 0:
        return idx
    for nm, i in name_to_idx.items():
        if part in nm:
            return i
    return -1


def preset_list(kind: str = "beats") -> dict[str, Any]:
    """List preset ids (registry + generated)."""
    if kind not in ("beats", "melodies"):
        return {"ok": False, "error": "kind must be 'beats' or 'melodies'"}
    return {"ok": True, "kind": kind, "presets": list_presets(kind)}


def _tile(seq: list, total: int) -> list:
    """Repeat `seq` to `total` items (total must be a multiple of len(seq))."""
    return [seq[i % len(seq)] for i in range(total)] if seq else seq


AUTO_LEVEL_TARGET_DB = -1.5   # one loop measured (±1 dB noise) -> 0.5 dB margin


def _auto_level(conn) -> dict:
    """After a load: keep the master's output peak <= AUTO_LEVEL_TARGET_DB
    (fl_mixer fix_clipping, one loop). Owner 2026-10-02: 'fix and for next
    time ... automated' (a song load clipped the master at +0.93)."""
    try:
        from fl_studio_mcp.tools.mixer_v2 import fix_clipping
        r = fix_clipping(conn, 0, AUTO_LEVEL_TARGET_DB, passes=1)
        return {k: r.get(k) for k in ("changed", "output_peak_before_dbfs",
                                      "fader_after_db", "output_peak_after_dbfs",
                                      "note", "error") if r.get(k) is not None}
    except Exception as e:  # never fail a load because of the level check
        return {"error": f"auto-level skipped: {e}"}


def load_beat(preset: str = "trap", target_pattern: int = 1,
              path: str = "", base_bpm: float = 0.0,
              fill: bool = True, auto_level: bool = True,
              channel_map: dict[str, str] | None = None) -> dict[str, Any]:
    """Load a beat preset into the drum channels of `target_pattern`.

    channel_map {part: channel name} (e.g. {"kick": "Kick AFRO"}) sends a part to that
    channel instead of the preset's own name (the default kit's "808 Kick"): fl_genre
    load_kit uses it so a genre kit plays the beat (owner 2026-10-11: no default kit).

    base_bpm=0 (default) leaves the tempo untouched; base_bpm>0 sets the
    playback-speed multiplier so the preset's BPM plays at that real tempo.
    fill=True (default) repeats the preset's steps (and per-step arrays)
    across the whole pattern: a 1-bar beat in a 4-bar pattern otherwise
    plays bar 1 and then 3 bars of silence under the piano roll
    (2026-10-02, a song loop).
    """
    data, err = resolve_preset("beats", preset, path)
    if not data:
        return {"ok": False,
                "error": (err or f"no beat preset '{preset}'. "
                          f"available: {', '.join(list_presets('beats'))}")}
    conn = get_connection()

    allch = conn.send_command("channels.getAll").get("channels", [])
    name_to_idx = {(c.get("name", "") or "").strip().lower(): c.get("index", -1)
                   for c in allch}

    total = None   # steps in the target pattern (fill)
    if fill:
        lr = conn.send_command("patterns.getLength",
                               {"index": int(target_pattern) - 1})
        try:
            lb = int(float(lr.get("length_beats") or 0))
        except (TypeError, ValueError):
            lb = 0
        total = lb * 4 if lb > 0 else None

    # Clear all drum channels first (no residue from a previous preset).
    for c in allch:
        nm = (c.get("name", "") or "").lower()
        if any(k in nm for k in _DRUM_KEYWORDS):
            conn.send_command(
                "channels.setStepSequence",
                {"channel": c.get("index", 0),
                 "pattern": [False] * max(16, total or 16),
                 "target_pattern": target_pattern},
            )

    written: list[str] = []
    skipped: list[str] = []
    repeats_applied: list[str] = []
    repeats_failed: list[str] = []
    for part, spec in data.get("channels", {}).items():
        if channel_map and part in channel_map:
            spec = {**spec, "name": channel_map[part]}
        elif channel_map:                     # a kit without this part: don't fall back
            skipped.append(f"{part}(not in kit)")   # to the default kit's channel
            continue
        idx = _resolve_channel(spec, part, name_to_idx)
        if idx < 0:
            skipped.append(f"{part}({spec.get('name')})")
            continue
        pattern = [bool(x) for x in spec.get("pattern", [0] * 16)]
        if total and len(pattern) < total and total % len(pattern) == 0:
            pattern = _tile(pattern, total)
            spec = {k: (_tile(v, total) if isinstance(v, list)
                        and k != "pattern" and len(v) and total % len(v) == 0 else v)
                    for k, v in spec.items()}
        r = conn.send_command(
            "channels.setStepSequence",
            {"channel": idx, "pattern": pattern,
             "target_pattern": target_pattern},
            timeout=10.0,
        )
        if r.get("success", False) or "error" not in r:
            written.append(f"{spec.get('name')} -> steps {sum(pattern)}")
            counts, sp_errors = _apply_step_params(
                conn, idx, pattern, spec, target_pattern)
            n_params = sum(counts.values())
            if n_params:
                written[-1] += f" + {n_params} step-params"
            if spec.get("repeats") and any(int(x or 0) for x in spec["repeats"]):
                if counts.get("pRepeat"):
                    repeats_applied.append(
                        f"{spec.get('name')} ({counts['pRepeat']})")
                else:
                    first_err = sp_errors[0] if sp_errors else "no active-step write"
                    repeats_failed.append(f"{spec.get('name')}: {first_err}")
        else:
            skipped.append(f"{spec.get('name')}: {r.get('error')}")

    result: dict[str, Any] = {
        "ok": True,
        "preset": data.get("name", preset),
        "written": written,
        "skipped": skipped,
        "pattern": target_pattern,
        "filled_to_steps": total,
    }
    if auto_level and written:
        result["auto_level"] = _auto_level(conn)
    bpm = data.get("bpm")
    if bpm and base_bpm and base_bpm > 0:
        mult = bpm / base_bpm
        conn.send_command("transport.setPlaybackSpeed",
                          {"multiplier": round(mult, 4)})
        result["tempo"] = f"{base_bpm} x{round(mult, 3)} -> ~{bpm} BPM"
    if data.get("swing"):
        result["swing_note"] = (
            f"preset wants {data['swing']*100:.0f}% swing — use "
            "fl_transport(action='set_swing')")
    if repeats_applied:
        result["repeats"] = ("applied as pRepeat (v45 step-param constant 8, "
                             f"P4-CLOSED): {', '.join(repeats_applied)}")
    if repeats_failed:
        result["repeats_failed"] = (
            "pRepeat write failed "
            f"({', '.join(repeats_failed)}) — rolls skipped for those parts")
    return result


def _step_to_time(step: int) -> float:
    # 16th-note grid -> quarter-note units
    return round(step / 4.0, 3)


def load_melody(preset: str = "a-minor-pop", target_pattern: int = 1,
                path: str = "", channel_index: int | None = None,
                auto_trigger: bool = True, auto_level: bool = True) -> dict[str, Any]:
    """Queue a melody/chord preset to the active pattern's piano roll.

    Selects `channel_index` (default: the current one) and `target_pattern`,
    then queues [clear, add_notes] through the ComposeWithLLM request file
    and (best-effort) triggers the script — the §0 handshake must already be
    done (fl_select_script) or the notes will not land.
    """
    data, err = resolve_preset("melodies", preset, path)
    if not data:
        return {"ok": False,
                "error": (err or f"no melody preset '{preset}'. "
                          f"available: {', '.join(list_presets('melodies'))}")}

    conn = get_connection()
    if channel_index is not None:
        # selectOne alone does NOT retarget an open roll (live-verified) —
        # notes would land in whichever roll is open. Retarget + confirm.
        from fl_studio_mcp.utils.roll_session import open_roll_for_channel
        r = open_roll_for_channel(int(channel_index))
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error")}
    sel = conn.send_command("patterns.select",
                            {"pattern": int(target_pattern)}, timeout=6.0)
    if sel.get("error"):
        return {"ok": False, "error": f"select pattern: {sel['error']}"}

    from fl_studio_mcp.tools.piano_roll import _write_request, trigger_fl_studio

    all_notes: list[dict] = []
    for n in data.get("melody", []):
        note = {
            "midi": int(n["note"]),
            "duration": round(float(n.get("dur", 1)) / 4.0, 3),
            "time": _step_to_time(n.get("step", 0)),
            "velocity": round(float(n.get("vel", 80)) / 127.0, 3),
        }
        if n.get("slide"):
            note["slide"] = True  # FL slide note (808 glide) — script sets flp.Note.slide
        all_notes.append(note)
    for ch in data.get("chords", []):
        t = _step_to_time(ch.get("step", 0))
        dur = round(float(ch.get("dur", 4)) / 4.0, 3)
        for midi in ch.get("notes", []):
            all_notes.append({"midi": int(midi), "duration": dur,
                              "time": t, "velocity": 0.7})
    if not all_notes:
        return {"ok": False, "error": "preset has no notes"}

    from fl_studio_mcp.utils import roll_session
    before = roll_session.state_mtime()
    _write_request([{"action": "clear"},
                    {"action": "add_notes", "notes": all_notes}])

    triggered = False
    if auto_trigger:
        try:
            if sys.platform == "darwin":   # (was os.name == "darwin": never true)
                subprocess.run(["osascript", "-e",
                                "tell application \"FL Studio 2026\" to activate"],
                               timeout=3, capture_output=True)
                time.sleep(0.3)
            triggered = bool(trigger_fl_studio())
        except Exception:
            triggered = False

    if auto_trigger:
        # The keystroke being sent is not proof: the script must have RUN
        # (state file rewritten). 2026-10-02: 'triggered: true' while the
        # queue still held [clear, add_notes] — the next trigger in ANY roll
        # would have cleared it. Never leave a write queued (rule 6b).
        if not roll_session.ran_since(before):
            _write_request([])
            return {"ok": False, "triggered": triggered, "script_ran": False,
                    "error": ("the ComposeWithLLM script did not run (not "
                              "selected, or FL not frontmost); the queue was "
                              "cleared so nothing lands later. Run "
                              "fl_select_script(channel_index=...) and retry.")}
    level = _auto_level(conn) if (auto_level and auto_trigger) else None
    return {
        "ok": True,
        "preset": data.get("name", preset),
        "pattern": target_pattern,
        "notes_queued": len(all_notes),
        "triggered": triggered,
        "script_ran": bool(auto_trigger),
        **({"auto_level": level} if level is not None else {}),
        "hint": ("notes drain into the ACTIVE piano roll (the §0 script "
                 "must be selected — fl_select_script); verify with "
                 "fl_state / fl_notes read_steps"),
    }


def _preset_dispatch(action: str, preset: str | None = None,
                     target_pattern: int = 1, path: str = "",
                     kind: str = "beats", base_bpm: float = 0.0,
                     channel_index: int | None = None,
                     auto_trigger: bool = True, fill: bool = True,
                     auto_level: bool = True, song_dir: str = "",
                     label: str = "") -> dict[str, Any]:
    """Dispatch the fl_preset actions (see module docstring)."""
    a = (action or "").lower().strip()
    if a == "load_song":
        if not song_dir:
            return {"ok": False, "error": "load_song needs song_dir (a folder with "
                                          "song.json + its presets)"}
        from fl_studio_mcp.utils.song_loader import load_song
        return load_song(song_dir, label=label, target_pattern=target_pattern,
                         log=lambda m: None)
    if a in ("list", "ls"):
        return preset_list(kind)
    if a == "load_beat":
        return load_beat(preset or "", target_pattern, path, base_bpm, fill,
                         auto_level)
    if a == "load_melody":
        return load_melody(preset or "", target_pattern, path,
                           channel_index, auto_trigger, auto_level)
    return {"ok": False,
            "error": f"unknown action {action!r} (list | load_beat | load_melody | load_song)"}


def register_preset_tools(mcp) -> None:
    @mcp.tool()
    def fl_preset(action: str, preset: str | None = None,
                  target_pattern: int = 1, path: str = "",
                  kind: str = "beats", base_bpm: float = 0.0,
                  channel_index: int | None = None,
                  auto_trigger: bool = True, fill: bool = True,
                  auto_level: bool = True, song_dir: str = "",
                  label: str = "") -> dict:
        """Load a beat or melody PRESET, or a whole analysed song (the legacy fl_load_beat /
        fl_load_melody / fl_list_presets were retired 2026-10-01).

        Actions:
          list        list preset ids (kind='beats'|'melodies'; registry +
                      .generated variations).
          load_beat   write the beat's parts to the matching channels of
                      target_pattern (exact-name match, then keyword), and
                      apply per-step velocities/shifts/repeats as FL step
                      parameters (S2.3). base_bpm=0 leaves tempo untouched;
                      base_bpm>0 sets the speed multiplier for the preset BPM.
                      fill=True (default) repeats the beat across the whole
                      pattern (a 1-bar beat in a 4-bar pattern = 4 bars).
          load_song   ONE CALL for a song folder (song_dir with a song.json
                      manifest: bpm + beat/melody/bass preset files, optional
                      bass_sample_wav): tempo + beat + melody on '<label> Melody'
                      + the bass line on '<label> Bass' (the original bass hit in
                      a Sampler, else FLEX) + clipping fix. Channels are created
                      when missing.
          load_melody select channel_index + target_pattern, queue the
                      melody+chords through the ComposeWithLLM script queue,
                      and best-effort trigger. The §0 selection (fl_select_script)
                      must be done first or the notes will not land.

        Args:
            action: list | load_beat | load_melody | load_song
            preset: preset id (or path= an explicit file in the work dir)
            target_pattern: 1-based pattern number
            path: explicit preset file (restricted to the fl-studio-mcp work dir)
            kind: for list — 'beats' or 'melodies'
            base_bpm: load_beat only — the project's real BPM (0 = don't touch tempo)
            channel_index: load_melody only — select this channel first
            auto_trigger: load_melody only — trigger the script after queueing
            fill: load_beat only — tile the beat to the pattern length
            auto_level: after a load, keep the master's output peak <= -1.5
                dBFS (fl_mixer fix_clipping; plays one loop to measure)
            song_dir: load_song — folder with song.json (format: utils/song_loader.py)
            label: load_song — channel prefix, e.g. 'Demo' -> 'Demo Melody' / 'Demo Bass'
                (default: song.json "label", else the folder name)
        """
        return _preset_dispatch(action, preset=preset,
                                target_pattern=target_pattern, path=path,
                                kind=kind, base_bpm=base_bpm,
                                channel_index=channel_index,
                                auto_trigger=auto_trigger, fill=fill,
                                auto_level=auto_level, song_dir=song_dir,
                                label=label)

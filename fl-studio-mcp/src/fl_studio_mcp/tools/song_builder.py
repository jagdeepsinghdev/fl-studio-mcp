"""Song-builder tools: fixed drum/melody setup, only the numbers change.

The manual recipe (see skills/fl-genres/references/trap.md) is many low-level calls. These tools
wrap it so a caller only supplies the *variable* parts:

  * drums  -> per-bar step numbers (1-16, 1-based) for kick / snare / hat / clap
  * melody -> per-bar note names ("A4") or MIDI numbers, one per grid step

Everything else (64-step arrays, channel lookup by name, pattern length = bars*4,
exclusive channel selection + verification, queue + trigger) is done here.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP

STEPS_PER_BAR = 16
BEATS_PER_BAR = 4
# Channel-name keyword for each drum part (matched case-insensitively).
DRUM_PARTS = ("kick", "snare", "hat", "clap")
_NOTE_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d)$")
_SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_REST = {None, "", "-", "r", "R", "rest"}


def parse_note(n: Any) -> int | None:
    """'A4' / 'C#5' / 'Bb3' / 69 -> MIDI number; rest tokens -> None."""
    if n in _REST:
        return None
    if isinstance(n, int) and not isinstance(n, bool):
        return n
    m = _NOTE_RE.match(str(n).strip())
    if not m:
        raise ValueError(f"bad note '{n}' (use e.g. 'A4', 'C#5', 'Bb3', a MIDI number, or '-' for rest)")
    letter, acc, octave = m.group(1).upper(), m.group(2), int(m.group(3))
    return (octave + 1) * 12 + _SEMITONE[letter] + (1 if acc == "#" else -1 if acc == "b" else 0)


def expand_steps(spec: Any, bars: int) -> list[bool]:
    """Per-bar 1-based step lists -> one flat bool row (bars*16).

    `spec` is either a list of `bars` lists (a different pattern each bar) or a
    single flat list of ints (same pattern repeated every bar). None -> silent.
    """
    row = [False] * (bars * STEPS_PER_BAR)
    if not spec:
        return row
    per_bar = spec if isinstance(spec[0], (list, tuple)) else [spec] * bars
    if len(per_bar) > bars:
        raise ValueError(f"got {len(per_bar)} bars of steps for bars={bars}")
    if len(per_bar) < bars:  # a shorter cycle repeats to fill (and is cut at) `bars`
        per_bar = [per_bar[i % len(per_bar)] for i in range(bars)]
    for b, steps in enumerate(per_bar):
        for s in steps:
            if not 1 <= int(s) <= STEPS_PER_BAR:
                raise ValueError(f"step {s} out of range 1-{STEPS_PER_BAR} (bar {b + 1})")
            row[b * STEPS_PER_BAR + int(s) - 1] = True
    return row


def melody_to_notes(melody: list[list[Any]], step_beats: float, note_beats: float | None,
                    velocity: float, bars: int | None = None) -> list[dict]:
    """Per-bar note lists (one token per grid step) -> fl_send_notes note dicts.

    Tokens: a note name / MIDI int, a list (chord), '-' (rest), or '~' (hold: extend the
    previous note(s) by one step, for sustained 808s). If `bars` is given and the melody
    has fewer bars, it repeats (a cycle) to fill `bars`; more bars than that is an error.
    """
    if bars is not None:
        if len(melody) > bars:
            raise ValueError(f"melody has {len(melody)} bars but bars={bars}")
        melody = [melody[i % len(melody)] for i in range(bars)]
    dur = note_beats if note_beats is not None else step_beats
    notes: list[dict] = []
    last: list[dict] = []
    for b, bar in enumerate(melody):
        for i, token in enumerate(bar):
            if isinstance(token, str) and token.strip() == "~":
                for n in last:
                    n["duration"] = round(n["duration"] + step_beats, 4)
                continue
            last = []
            # A list/tuple entry is a chord: all its notes start on the same step.
            for one in (token if isinstance(token, (list, tuple)) else [token]):
                midi = parse_note(one)
                if midi is None:
                    continue
                n = {
                    "midi": midi,
                    "time": round(b * BEATS_PER_BAR + i * step_beats, 4),
                    "duration": dur,
                    "velocity": velocity,
                }
                notes.append(n)
                last.append(n)
    return notes


def register_song_builder_tools(mcp: FastMCP) -> None:
    """Register the song-builder tools with the MCP server."""
    from fl_studio_mcp.tools.patterns import select_pattern
    from fl_studio_mcp.tools.piano_roll import _write_request, trigger_fl_studio
    from fl_studio_mcp.utils.connection import get_connection

    def _channels() -> list[dict]:
        return get_connection().send_command("channels.getAll").get("channels", [])

    def _find(part: str, chans: list[dict]) -> int:
        for c in chans:
            if part in (c.get("name") or "").lower():
                return c.get("index", -1)
        return -1

    def _set_length(pattern: int, bars: int) -> None:
        get_connection().send_command(
            "patterns.setLength", {"index": pattern - 1, "beats": bars * BEATS_PER_BAR}
        )

    def _write_row(idx: int, row: list[bool], pattern: int) -> dict:
        # long rows (92 bars = 1472 steps) take FL more than the 2 s default to acknowledge
        return get_connection().send_command(
            "channels.setStepSequence", {"channel": idx, "pattern": row, "target_pattern": pattern},
            timeout=10.0,
        )

    def _drums(parts: dict[str, Any], bars: int, pattern: int) -> dict[str, Any]:
        chans = _channels()
        out: dict[str, Any] = {"written": [], "missing": []}
        for part in DRUM_PARTS:
            idx = _find(part, chans)
            if idx < 0:
                out["missing"].append(part)
                continue
            row = expand_steps(parts.get(part), bars)
            r = _write_row(idx, row, pattern)
            if r.get("error"):
                out["missing"].append(f"{part}: {r['error']}")
            else:
                out["written"].append(f"{part} (ch {idx}): {sum(row)}/{len(row)} steps")
        return out

    def _melody(melody: list[list[Any]], channel_name: str, pattern: int, step_beats: float,
                note_beats: float | None, velocity: float, replace: bool,
                channel_index: int | None = None, bars: int | None = None,
                notes_override: list[dict] | None = None) -> dict[str, Any]:
        notes = notes_override if notes_override is not None else melody_to_notes(
            melody, step_beats, note_beats, velocity, bars)
        if not notes:
            return {"ok": False, "error": "melody has no notes"}
        conn = get_connection()
        chans = _channels()
        if channel_index is not None:
            idx = channel_index if any(c.get("index") == channel_index for c in chans) else -1
        else:
            idx = _find(channel_name.lower(), chans)
        if idx < 0:
            return {"ok": False, "error": (
                f"no channel named like '{channel_name}'. Add one first: "
                f"fl_setup_instrument('FLEX', '{channel_name}')")}
        if pattern:
            sel = select_pattern(pattern)
            if sel.get("error"):
                return {"ok": False, "error": sel["error"]}
        conn.send_command("channels.selectOne", {"index": idx})
        # Verify: ONLY the target channel may be selected (known FL gotcha: the
        # selection call can succeed while another channel stays selected).
        selected = [c.get("index") for c in _channels() if c.get("is_selected")]
        if selected != [idx]:
            return {"ok": False, "error": (
                f"channel '{channel_name}' (ch {idx}) is not the only selected channel "
                f"(selected: {selected}); refusing to write notes to the wrong channel. Retry.")}
        # Selection alone does NOT retarget an already-open roll (live-verified);
        # the script writes to the OPEN roll. Retarget + confirm via the caption.
        from fl_studio_mcp.utils.roll_session import open_roll_for_channel
        roll = open_roll_for_channel(idx)
        if not roll.get("ok"):
            return {"ok": False, "error": roll.get("error")}
        reqs: list[dict] = [{"action": "clear"}] if replace else []
        reqs.append({"action": "add_notes", "notes": notes})
        _write_request(reqs)
        try:
            trigger_fl_studio()
        except Exception:
            pass
        return {"ok": True, "channel": f"{channel_name} (ch {idx})", "notes_queued": len(notes),
                "beats_covered": (round(max(n["time"] + n["duration"] for n in notes), 2)
                                  if notes_override is not None
                                  else (bars or len(melody)) * BEATS_PER_BAR),
                "verify": "fl_get_piano_roll_state -> noteCount should equal notes_queued"}

    @mcp.tool()
    def fl_write_drums(
        kick: list | None = None,
        snare: list | None = None,
        hat: list | None = None,
        clap: list | None = None,
        bars: int = 4,
        target_pattern: int = 1,
        set_pattern_length: bool = True,
    ) -> dict[str, Any]:
        """Write a multi-bar drum pattern; you only supply WHICH STEPS hit.

        Channels are found by name (kick/snare/hat/clap), rows are built at
        bars*16 steps, and the pattern length is set to bars*4 beats. A part left
        as None is cleared (silent).

        Each part is either
          * a list of per-bar lists of 1-based steps, e.g.
            kick=[[1,7,12],[1,8,11],[1,7,15],[1,6,11]]. If it has FEWER lists than
            `bars` it is a cycle: it repeats to fill all bars (a 4-bar or 8-bar
            pattern for 92 bars), and is cut at `bars`. More lists than `bars` is an error. Or
          * one flat list of steps, repeated every bar, e.g. hat=[1,3,5,7,9,11,13,15].

        Step numbers are 1-16 per bar (16th-note grid; 1, 5, 9, 13 = the beats).

        Args:
            bars: number of bars (4 beats each).
            target_pattern: pattern number (1-based) to write into.
            set_pattern_length: also set the pattern to bars*4 beats.
        """
        try:
            if set_pattern_length:
                _set_length(target_pattern, bars)
            out = _drums({"kick": kick, "snare": snare, "hat": hat, "clap": clap}, bars, target_pattern)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        out["ok"] = not out["missing"]
        out["pattern_length_beats"] = bars * BEATS_PER_BAR if set_pattern_length else None
        return out

    @mcp.tool()
    def fl_clean_drums(bars: int = 4, target_pattern: int = 1) -> dict[str, Any]:
        """Clear every drum row (kick/snare/hat/clap) in a pattern: the 'start over' button.

        Does NOT touch melody/piano-roll notes (use fl_clear_piano_roll for those).
        """
        out = _drums({}, bars, target_pattern)
        out["ok"] = not out["missing"]
        return out

    @mcp.tool()
    def fl_write_melody(
        melody: list[list],
        channel_name: str = "Guitar",
        step_beats: float = 0.5,
        note_beats: float | None = None,
        velocity: float = 0.8,
        target_pattern: int = 1,
        replace: bool = True,
        channel_index: int | None = None,
        bars: int | None = None,
    ) -> dict[str, Any]:
        """Write a multi-bar melody into a named channel; you only supply the NOTES.

        One list per bar; each entry is one grid step (default 0.5 beat = an eighth
        note, so 8 entries fill a bar). Entries are note names ('A4', 'C#5', 'Bb3'),
        MIDI numbers, or '-' for a rest; a list is a CHORD (["C3","G3","E4"] = 3 notes on
        one step). Works for ANY instrument channel (piano, bass, pad, lead, guitar...).
        Example (Am, then F):
            [["A4","E5","C5","E5","A4","E5","C5","B4"],
             ["F4","C5","A4","C5","F4","C5","A4","G4"]]

        Selects ONLY the named channel and verifies it before writing, so notes can't
        land on the wrong channel. ComposeWithLLM must be the selected piano-roll
        script (manual, once per FL session). Then fl_get_piano_roll_state to confirm.

        Args:
            channel_name: channel to write into (must exist; matched by name).
            step_beats: beats per grid entry (0.5 = eighth, 0.25 = sixteenth).
            note_beats: note length in beats (default = step_beats).
            velocity: 0.0-1.0.
            target_pattern: pattern (1-based) to write into (0 = active).
            replace: clear the channel's existing notes first.
            channel_index: address the channel by index instead of name (FLEX renames
                channels to their preset, so names change; overrides channel_name).
            bars: total bars to fill; a shorter `melody` repeats as a cycle (an 8-bar bass
                line over 92 bars). Use '~' as a token to HOLD the previous note one more
                step (sustained 808s: ["C2","~","~","-", ...] at step_beats=0.25).
        """
        try:
            return _melody(melody, channel_name, target_pattern, step_beats, note_beats, velocity, replace,
                           channel_index, bars)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    @mcp.tool()
    def fl_write_notes_file(
        file_path: str,
        channel_index: int,
        target_pattern: int = 1,
        replace: bool = True,
    ) -> dict[str, Any]:
        """Queue a LARGE note list from a JSON file (no pasting hundreds of notes).

        The file holds a list of {"midi": int, "time": beats, "duration": beats, "velocity": 0-1}
        (quarter-note beats, C4 = 60), e.g. a transcription exported by another tool.
        Same safety as fl_write_melody: selects ONLY channel_index and verifies it before queueing.
        The script still applies notes to the piano roll that is OPEN - do the roll handshake
        (skills/fl-melody) first, then read the counts back from mcp_response.json.

        Args:
            file_path: JSON file with the note list.
            channel_index: channel to write into (0-based, from fl_get_all_channels).
            target_pattern: pattern (1-based) to write into (0 = active).
            replace: clear the channel's existing notes first.
        """
        import json as _json
        from pathlib import Path as _Path

        try:
            notes = _json.loads(_Path(file_path).expanduser().read_text())
        except (OSError, ValueError) as e:
            return {"ok": False, "error": f"cannot read notes file: {e}"}
        if not isinstance(notes, list) or not notes:
            return {"ok": False, "error": "notes file must be a non-empty JSON list"}
        for i, n in enumerate(notes):
            if not isinstance(n, dict) or not all(k in n for k in ("midi", "time", "duration")):
                return {"ok": False, "error": f"note {i} needs midi, time and duration"}
            n.setdefault("velocity", 0.8)
        return _melody([], "", target_pattern, 0.5, None, 0.8, replace, channel_index, None, notes)

    @mcp.tool()
    def fl_build_track(
        bpm: float = 140.0,
        bars: int = 4,
        drums: dict | None = None,
        melody: list[list] | None = None,
        melody_channel: str = "Guitar",
        step_beats: float = 0.5,
        target_pattern: int = 1,
        play: bool = False,
        melody_channel_index: int | None = None,
    ) -> dict[str, Any]:
        """Whole track in ONE call: tempo, length, drums and melody. Only the numbers vary.

        Does: real BPM + speed 1.0, pattern length = bars*4, drums via fl_write_drums
        rules, melody via fl_write_melody rules, loop mode 'pattern', optional play
        (only starts if not already playing, so it never toggles playback off).

        Args:
            bpm: real tempo.
            bars: number of 4-beat bars; melody must have exactly this many bars.
            drums: {"kick": <steps>, "snare": ..., "hat": ..., "clap": ...} — see
                fl_write_drums for the step formats. Omit a part to leave it silent.
            melody: per-bar note lists — see fl_write_melody. None = drums only.
            melody_channel: existing channel to receive the melody.
            step_beats: beats per melody entry (0.5 = eighth).
            play: start playback at the end.
            melody_channel_index: address the melody channel by index (overrides the name).

        The melody channel must already exist (fl_setup_instrument) and ComposeWithLLM
        must be selected (manual, once per FL session).
        """
        conn = get_connection()
        report: dict[str, Any] = {}
        try:
            if melody is not None and len(melody) != bars:
                return {"ok": False, "error": f"melody has {len(melody)} bars but bars={bars}"}
            conn.send_command("transport.setBPM", {"bpm": bpm})
            conn.send_command("transport.setPlaybackSpeed", {"speed": 1.0})
            _set_length(target_pattern, bars)
            report["tempo"] = f"{bpm} BPM, speed 1.0, pattern {target_pattern} = {bars * BEATS_PER_BAR} beats"
            report["drums"] = _drums(drums or {}, bars, target_pattern)
            if melody is not None:
                report["melody"] = _melody(melody, melody_channel, target_pattern, step_beats,
                                           None, 0.8, True, melody_channel_index)
        except ValueError as e:
            return {"ok": False, "error": str(e), "partial": report}
        conn.send_command("transport.setLoopMode", {"mode": "pattern"})
        if play:
            if not conn.send_command("transport.getStatus").get("is_playing"):
                conn.send_command("transport.start")
        report["ok"] = not report["drums"]["missing"] and report.get("melody", {}).get("ok", True)
        return report

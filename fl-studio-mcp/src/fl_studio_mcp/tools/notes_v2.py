"""B6: fl_notes — one tool for piano-roll note control.

The piano-roll note path is DIFFERENT from the other domain tools: there is
NO controller action for it. Notes are written by a QUEUE FILE
(`mcp_request.json`) that the **ComposeWithLLM** piano-roll script consumes
when triggered (Cmd+Opt+Y), then the script exports the roll to
`piano_roll_state.json`. So this tool routes to the queue+trigger path, not
the MIDI controller.

CRITICAL handshake (CLAUDE.md §6b — never write notes without it):
  1. Open the target channel's roll (select it, F7)
  2. Confirm via fl_state which roll is open (piano_roll note_count)
  3. THEN write
  This tool takes `open_roll_verified: bool` — you must have done step 1-2
  (a ComposeWithLLM-triggered fl_state) before writing; otherwise the notes
  land in the WRONG roll.

Actions:
  write_steps (notes, mode=add|replace, [target_pattern]) — queue + trigger
  read_steps — read the piano_roll_state.json (via the fl_state mtime guard)
  import_midi (channel_index, notes|path) — C3, PROVEN 2026-10-01: FL's own
      piano-roll File > Import MIDI file into an existing channel (replaces
      its notes in the pattern); UI driven by utils/import_midi.py
  live_play (notes) — UNVERIFIED: real-time note-on/off via the roll
  quantize (step, [range]) — UNVERIFIED: the roll's quantize menu
  cut_all — **NOT here**: destructive → fl_delete (target=roll_notes)

Verified: write_steps, read_steps, import_midi. live_play / quantize are
registered but return a clear "not yet verified".
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from fl_studio_mcp.tools.transport_v2 import _safe_send

ACTIONS = ("write_steps", "read_steps", "clear", "clear_queue", "import_midi",
           "live_play", "quantize", "write_chords", "capture")

# actions that have a live path vs. are still unverified
_VERIFIED = {"write_steps", "read_steps", "import_midi"}
_UNVERIFIED = {
    "live_play": "live (real-time) note-on/off through the roll is not yet wired.",
    "quantize": "the roll's quantize menu is not yet automated (needs the native "
                "quantize UI or a verified API).",
}


def _validate(action: str, params: dict[str, Any]) -> list[str]:
    if action not in ACTIONS:
        return [f"unknown action {action!r}. Valid: {', '.join(ACTIONS)}"]
    errs = []
    if action == "write_steps":
        notes = params.get("notes")
        if notes is not None and params.get("melody") is not None:
            return ["write_steps: give 'notes' OR 'melody', not both"]
        if params.get("melody") is not None:
            return errs  # converted (and validated) by _melody_to_params first
        if not isinstance(notes, list) or not notes:
            errs.append("write_steps: 'notes' (or 'melody') must be a non-empty list")
        else:
            for i, n in enumerate(notes):
                if not isinstance(n, dict) or "midi" not in n or "duration" not in n:
                    errs.append(f"write_steps.notes[{i}]: needs 'midi' and 'duration'")
        if params.get("mode") not in (None, "add", "replace"):
            errs.append("write_steps.mode: must be 'add' or 'replace'")
    elif action in ("read_steps", "clear", "clear_queue"):
        pass  # no required params
    elif action == "read_steps":
        pass  # no params
    elif action == "import_midi":
        if params.get("channel_index") is None:
            errs.append("import_midi: 'channel_index' is required (the target channel)")
        notes, path = params.get("notes"), params.get("path")
        if bool(notes) == bool(path):
            errs.append("import_midi: give exactly one of 'notes' or 'path' (.mid)")
        elif notes:
            if not isinstance(notes, list):
                errs.append("import_midi: 'notes' must be a list")
            else:
                for i, n in enumerate(notes):
                    if not isinstance(n, dict) or "midi" not in n or "duration" not in n:
                        errs.append(f"import_midi.notes[{i}]: needs 'midi' and 'duration'")
        elif not str(path).lower().endswith((".mid", ".midi")):
            errs.append("import_midi: 'path' must be a .mid/.midi file")
    elif action == "live_play":
        notes = params.get("notes")
        if not isinstance(notes, list) or not notes:
            errs.append("live_play: 'notes' must be a non-empty list")
    elif action == "quantize":
        step = params.get("step")
        if step is None:
            errs.append("quantize: 'step' is required")
    return errs


def _melody_to_params(params: dict[str, Any]) -> str | None:
    """S7: turn `melody=[[token,...],...]` (+ step_beats/note_beats/velocity)
    into `params["notes"]` using the legacy song-builder helpers. Returns an
    error string or None. Tokens: note name ("C#4") / MIDI int, "-" rest,
    "~" hold (extends the previous note by one step), list = chord. One
    token per grid step, one inner list per bar (4 beats)."""
    from fl_studio_mcp.tools.song_builder import melody_to_notes
    melody = params.get("melody")
    if not isinstance(melody, list) or not melody or not all(
            isinstance(b, (list, tuple)) for b in melody):
        return "write_steps: 'melody' must be a non-empty list of per-bar token lists"
    try:
        step = float(params.get("step_beats", 0.25))
        nb = params.get("note_beats")
        vel = params.get("velocity")
        params["notes"] = melody_to_notes(
            [list(b) for b in melody], step,
            None if nb is None else float(nb),
            0.8 if vel is None else float(vel))
    except (ValueError, TypeError) as e:
        return f"write_steps.melody: {e}"
    if not params["notes"]:
        return "write_steps.melody: no notes (all rests?)"
    params.pop("melody", None)
    return None


def _clear_queue(action: str) -> dict:
    """S3: drop every pending ComposeWithLLM request. The queue file is
    BACKED UP (timestamped copy next to it) before `[]` is written, so a
    mistaken clear is recoverable. Returns how many requests were dropped."""
    import json
    import shutil
    import time

    from fl_studio_mcp.tools import piano_roll as pr
    f = pr._get_request_file()
    dropped, backup = 0, None
    if f.exists():
        try:
            data = json.loads(f.read_text() or "[]")
            dropped = len(data) if isinstance(data, list) else (1 if data else 0)
        except (json.JSONDecodeError, OSError):
            dropped = 0
        backup = f.with_name(f"{f.stem}.{time.strftime('%Y%m%d-%H%M%S')}"
                             f"{f.suffix}")
        n = 1
        while backup.exists():  # two clears in one second must not collide
            backup = f.with_name(f"{f.stem}.{time.strftime('%Y%m%d-%H%M%S')}-{n}{f.suffix}")
            n += 1
        shutil.copy2(f, backup)
    f.write_text("[]")
    return {"action": action, "success": True, "dropped": dropped,
            "backup": None if backup is None else str(backup)}


def _write_steps_via_queue(notes: list, mode: str, auto_trigger: bool,
                           target_pattern: int) -> str:
    """Route write_steps through the existing ComposeWithLLM queue path."""
    from fl_studio_mcp.tools.piano_roll import _get_trigger_info, _write_request
    from fl_studio_mcp.utils.fl_trigger import get_trigger, trigger_fl_studio
    # normalize
    for n in notes:
        n.setdefault("time", 0)
        n.setdefault("velocity", 0.8)
    reqs = []
    if mode == "replace":
        reqs.append({"action": "clear"})
    reqs.append({"action": "add_notes", "notes": notes})
    _write_request(reqs)
    info = _get_trigger_info(auto_trigger)
    if auto_trigger:
        trig = get_trigger()
        if trig.is_supported and trigger_fl_studio():
            return f"Triggered {len(notes)} note(s) into the roll. Re-run fl_state to confirm."
    return f"Queued {len(notes)} note(s) (mode={mode}).{info}"


def _midi_note_count(path) -> int:
    import mido
    return sum(1 for tr in mido.MidiFile(str(path)).tracks for m in tr
               if m.type == "note_on" and m.velocity > 0)


def _import_midi(params: dict[str, Any], conn) -> dict:
    """C3 (proven live 2026-10-01): FL's own piano-roll File > Import MIDI file
    into an EXISTING channel. REPLACES that channel's notes in the active
    pattern. Every UI step is located on screen and verified
    (utils/import_midi.py); the result is read back and compared. No
    ComposeWithLLM queue is involved in the write."""
    from fl_studio_mcp.utils import import_midi as im
    from fl_studio_mcp.utils.roll_session import open_roll_for_channel
    if conn is None:
        from fl_studio_mcp.utils.connection import get_connection
        conn = get_connection()
    ch = int(params["channel_index"])
    if params.get("path"):
        from fl_studio_mcp.preset_paths import resolve_preset_path
        mid, err = resolve_preset_path(str(params["path"]))
        if err:
            return {"action": "import_midi", "success": False, "error": err}
    else:
        mid = im.write_midi(params["notes"], name=f"import-ch{ch}",
                            bpm=float(params.get("bpm") or 120))
    expected = _midi_note_count(mid)

    was_active = None
    target = int(params.get("target_pattern") or 0)
    if target:
        try:
            was_active = int(conn.send_command("probe.patterns").get("active_pattern"))
        except Exception:  # noqa: BLE001
            was_active = None
        sel = _safe_send("patterns.select", {"pattern": target}, conn)
        if sel.get("error"):
            return {"action": "import_midi", "success": False,
                    "error": f"select pattern {target}: {sel['error']}"}

    out: dict = {"action": "import_midi", "file": str(mid), "expected_notes": expected}
    try:
        r = im.import_midi_file(ch, mid)
        out["steps"] = r.get("steps", [])
        if not r.get("ok"):
            out.update(success=False, error=r.get("error"))
            return out
        # Read back: reopen the target roll (proven), run the script on an
        # empty queue so it exports the roll, compare the count.
        roll = open_roll_for_channel(ch)
        from fl_studio_mcp.tools.piano_roll import _write_request
        from fl_studio_mcp.tools.state import _read_piano_roll
        from fl_studio_mcp.utils import roll_session as rs
        from fl_studio_mcp.utils.fl_trigger import trigger_fl_studio
        before = rs.state_mtime()
        if roll.get("ok"):
            _write_request([])
            trigger_fl_studio()
        pr = _read_piano_roll(600)
        fresh = rs.ran_since(before)
        out["verified"] = bool(roll.get("ok") and fresh
                               and pr.get("note_count") == expected)
        out["read_back"] = {"note_count": pr.get("note_count"),
                            "summary": pr.get("summary"), "fresh": fresh}
        out["success"] = out["verified"]
        if not out["verified"]:
            out["error"] = (f"imported, but the read-back did not confirm it "
                            f"(expected {expected} notes, read {pr.get('note_count')}, "
                            f"fresh={fresh}, roll proof={roll.get('ok')})")
        return out
    finally:
        if target and was_active and was_active != target:
            conn.send_command("patterns.select", {"pattern": was_active})
            out["active_restored"] = was_active


def fl_notes(action: str, conn=None, **params: Any) -> dict:
    """Control piano-roll notes (one tool, 7 actions).

    **The write handshake (do not skip):** before `write_steps`, open the
    target channel's roll (select it, F7) and confirm with `fl_state` which
    roll is open. Pass `open_roll_verified=True` once you've done that.
    Without it, notes land in whatever roll is currently open.

    Actions:
      write_steps (notes | melody, mode=add|replace, [target_pattern],
                  [channel_index], [auto_trigger=True], [open_roll_verified=False])
          melody=[[tok,...], ...] (S7, instead of notes; both = error): one
          inner list per bar, one token per grid step of `step_beats` (default
          0.25), token = note name ("C#4", "Bb3") / MIDI int / "-" rest /
          "~" hold (extends the previous note one step) / list = chord.
          Optional note_beats (duration, default = step_beats), velocity 0-1.
          e.g. melody=[["C#4","G#4","C#5","G#4"]], step_beats=0.5 -> MIDI
          61,68,73,68 at beats 0,0.5,1,1.5.
          notes: {midi, duration, [time], [velocity 0-1], [slide: bool]} —
          slide=True = FL slide note (808 glides: a short slide note
          overlapping the tail of the sounding note bends it to its pitch).
          channel_index: the server switches the open roll to that channel
          and proves it (else refuses) — no open_roll_verified needed.
      read_steps — the current roll's notes (mtime-guarded via fl_state)
      import_midi (channel_index, notes | path, [target_pattern], [bpm]) —
          C3, proven live: FL's own piano-roll File > Import MIDI file into an
          EXISTING channel. REPLACES that channel's notes in the pattern. No
          ComposeWithLLM queue. UI steps located on screen (OCR) + verified;
          result read back and compared (`verified`). The previously active
          pattern is restored. Slow (~15 s): prefer write_steps for small edits.
      clear_queue — S3: drop every pending ComposeWithLLM request in
          mcp_request.json (a timestamped backup copy is written next to it
          first); returns {dropped, backup}. Touches no roll.
      live_play (notes) — not yet wired
      quantize (step, [range]) — not yet wired

    cut_all is NOT here (destructive → fl_delete target=roll_notes).
    """
    if action == "capture":
        # tip 8: Tools > Dump score log to selected pattern, guarded (utils/score_log.py)
        from fl_studio_mcp.utils.score_log import capture as _cap
        if conn is None:
            from fl_studio_mcp.utils.connection import get_connection
            conn = get_connection()
        return _cap(conn, int(params.get("seconds") or 120), params.get("target_pattern"))
    if action == "write_chords":
        # chord TEXT -> notes -> the proven write_steps path (same roll handshake).
        # Owner's tip 4 ("text to chord progression", 2026-10-06).
        from fl_studio_mcp.utils.chords import symbol_notes
        text = params.pop("text", None)
        if not (isinstance(text, str) and text.strip()):
            return {"success": False, "error": "write_chords: text like 'Am F C G' required",
                    "valid_actions": list(ACTIONS)}
        try:
            params["notes"] = symbol_notes(text, float(params.pop("beats_per_chord", 4.0) or 4.0),
                                           int(params.pop("octave", 4) or 4),
                                           float(params.get("velocity") or 0.7),
                                           params.pop("bass", True) is not False)
        except ValueError as e:
            return {"success": False, "error": str(e), "valid_actions": list(ACTIONS)}
        if params.pop("humanize", None) is not False:   # default ON: a flat block sounds stiff
            from fl_studio_mcp.utils.humanize import humanize_chords
            params["notes"] = humanize_chords(params["notes"], text)
        params.setdefault("mode", "replace")
        action = "write_steps"
    if action == "write_steps" and params.get("melody") is not None:
        if params.get("notes") is not None:
            return {"success": False, "error": "write_steps: give 'notes' OR "
                    "'melody', not both", "valid_actions": list(ACTIONS)}
        hum = params.pop("humanize", None)
        err = _melody_to_params(params)
        if err:
            return {"success": False, "error": err, "valid_actions": list(ACTIONS)}
        if hum is not False:   # default ON for token melodies (a 16th grid at one velocity is a metronome)
            from fl_studio_mcp.utils.humanize import humanize_melody
            params["notes"] = humanize_melody(
                params["notes"], repr([(n["midi"], n["time"]) for n in params["notes"]]))
    params.pop("humanize", None)   # never forward to the roll (explicit notes= stay exactly as given)
    errs = _validate(action, params)
    if errs:
        return {"success": False, "error": "; ".join(errs),
                "valid_actions": list(ACTIONS)}

    if action == "clear_queue":
        return _clear_queue(action)

    # channel_index: the server retargets the roll itself and PROVES it
    # (roll_session.open_roll_for_channel), which replaces the caller's
    # open_roll_verified attestation. Refuses if it cannot prove it.
    if action in ("write_steps", "clear") and params.get("channel_index") is not None:
        from fl_studio_mcp.utils.roll_session import open_roll_for_channel
        roll = open_roll_for_channel(int(params["channel_index"]))
        if not roll.get("ok"):
            return {"action": action, "success": False, "error": roll.get("error")}
        params["open_roll_verified"] = True

    # write_steps with an unverified open roll is the classic bug — warn loudly
    if action == "write_steps" and not params.get("open_roll_verified", False):
        return {"success": False, "error":
                "write_steps refused: open_roll_verified is False. Open the target "
                "channel's roll (select it, F7), confirm with fl_state that the "
                "right roll is open (piano_roll.note_count), then re-call with "
                "open_roll_verified=True. (CLAUDE.md §6b: never write notes into "
                "an unconfirmed roll.)"}

    if action == "import_midi":
        return _import_midi(params, conn)

    if action in _UNVERIFIED:
        return {"success": False, "error": _UNVERIFIED[action],
                "status": "not_verified_yet"}

    if action == "write_steps":
        if conn is None:
            from fl_studio_mcp.utils.connection import get_connection
            conn = get_connection()
        target_pattern = int(params.get("target_pattern", 0))
        # select the target pattern first (the queue lands in the active roll)
        if target_pattern != 0:
            try:
                _safe_send("patterns.select", {"pattern": target_pattern}, conn)
            except Exception as e:
                return {"action": action, "success": False, "error": f"select: {e}"}
        msg = _write_steps_via_queue(
            params["notes"], params.get("mode", "add"),
            params.get("auto_trigger", True), target_pattern)
        # S4 part ledger: record the notes we just wrote so fl_state / fl_pattern
        # chain can read back this channel without re-opening its roll. Best-effort.
        if conn is not None:
            try:
                from fl_studio_mcp.utils import ledger
                chans = conn.send_command("channels.getAll").get("channels", [])
                ci = params.get("channel_index")
                if ci is None:
                    # open_roll_verified path: the roll's channel is the selected one
                    sel = next((c for c in chans
                                if c.get("is_selected", c.get("selected"))), None)
                    ci = None if sel is None else sel.get("index", sel.get("number"))
                if ci is not None:
                    chname = next((c.get("name") for c in chans
                                   if c.get("index", c.get("number")) == int(ci)), None)
                    ledger.record_notes(
                        None, target_pattern, int(ci), chname, params["notes"],
                        {"notes_added": len(params["notes"]),
                         "mode": params.get("mode", "add")},
                        mode=("add" if params.get("mode", "add") == "add" else "replace"))
            except Exception:  # noqa: BLE001 - ledger is best-effort
                pass
        return {"action": action, "success": True, "result": msg}

    if action == "read_steps":
        from fl_studio_mcp.tools.state import _read_piano_roll
        pr = _read_piano_roll(600)
        return {"action": action, "success": True, "piano_roll": pr}

    if action == "clear":
        # queue a clear of the CURRENTLY OPEN roll's notes. Destructive, but the
        # low-level roll path: it only affects whichever roll is open, so it is
        # gated by the same open_roll_verified attestation as write_steps.
        if not params.get("open_roll_verified", False):
            return {"action": action, "success": False,
                    "error": ("clear refused: pass open_roll_verified=True after "
                             "confirming (read_steps) which roll is open.")}
        from fl_studio_mcp.tools.piano_roll import _get_trigger_info, _write_request
        # 2026-10-11: a clear with target_pattern=1 emptied the ACTIVE pattern 5 (the guitar of a
        # 20-bar song) because the target was ignored. Select the target first, and say which
        # pattern was active so a wrong target is visible in the reply.
        if conn is None:
            from fl_studio_mcp.utils.connection import get_connection
            conn = get_connection()
        tp = params.get("target_pattern")
        if tp is not None:
            sel = conn.send_command("patterns.select", {"pattern": int(tp)})
            if sel.get("error") or sel.get("success") is False:
                return {"action": action, "success": False,
                        "error": f"clear refused: could not select pattern {tp} ({sel.get('error')})"}
        try:
            active = int(conn.send_command("probe.patterns").get("active_pattern"))
        except (TypeError, ValueError):
            active = None
        if tp is not None and active is not None and active != int(tp):
            return {"action": action, "success": False,
                    "error": f"clear refused: pattern {active} is active, not the requested {tp}"}
        _write_request([{"action": "clear"}])
        info = _get_trigger_info(params.get("auto_trigger", True))
        return {"action": action, "success": True, "cleared_pattern": active,
                "result": f"Queued a clear of the open roll (pattern {active}).{info}"}

    return {"action": action, "success": False, "error": "unhandled"}


def register_notes_tools_v2(mcp: FastMCP) -> None:
    """Register the B6 fl_notes tool."""
    from fl_studio_mcp.tools.notes_v2 import fl_notes as _impl

    @mcp.tool()
    def fl_notes(
        action: str,
        notes: list | None = None,
        melody: list | None = None,
        step_beats: float | None = None,
        note_beats: float | None = None,
        velocity: float | None = None,
        mode: str | None = None,
        target_pattern: int | None = None,
        auto_trigger: bool | None = None,
        open_roll_verified: bool | None = None,
        channel_index: int | None = None,
        path: str | None = None,
        step: float | None = None,
        bpm: float | None = None,
        text: str | None = None,
        beats_per_chord: float | None = None,
        octave: int | None = None,
        bass: bool | None = None,
        seconds: int | None = None,
        humanize: bool | None = None,
    ) -> dict:
        """Control FL Studio piano-roll notes (one tool, 9 actions).

        Actions: write_steps | write_chords | read_steps | clear | clear_queue |
        import_midi | live_play | quantize. write_chords(text="Am F C G" /
        "Cmaj7 | Fm9 | G7sus4" / "C/E", channel_index, [beats_per_chord=4], [octave=4],
        [bass=true], [humanize=true]) -> chord names to notes (root + slash bass) via write_steps.
        humanize (default ON for write_chords and for melody= tokens; explicit notes= are never
        changed): strongest bass, softer upper notes, light strum, chords a bit shorter than the
        slot / accented bar starts, softer off-beats, tiny timing drift. Pass humanize=false for
        exact grid notes.
        capture([seconds=120], [target_pattern]) -> dump what was PLAYED IN (score log)
        into the pattern; FL's empty-log warning is dismissed and reported; proof = undo +1. write_steps and clear need either channel_index (the server
        switches the roll to that channel and proves it) or
        open_roll_verified=True (you confirmed the open roll — §6b).
        Notes: {midi, duration, time, velocity 0-1, slide?}.
        Or melody=[[token,...] per bar] + step_beats (default 0.25) [+
        note_beats, velocity]: tokens = "C#4" / MIDI int / "-" rest / "~" hold /
        [chord list]; give notes OR melody, not both.
        clear_queue: empties the pending script queue (timestamped backup of
        mcp_request.json first; returns dropped + backup path).
        import_midi(channel_index, notes | path=.mid, [target_pattern], [bpm]):
        FL's own roll Import MIDI into an EXISTING channel — REPLACES its notes
        in that pattern, no script queue; read back + compared ("verified");
        ~15 s, so prefer write_steps for small edits. cut_all is NOT here
        (destructive → fl_delete target=roll_notes).
        """
        p = {k: v for k, v in {"notes": notes, "melody": melody,
             "step_beats": step_beats, "note_beats": note_beats,
             "velocity": velocity, "mode": mode,
             "target_pattern": target_pattern, "auto_trigger": auto_trigger,
             "open_roll_verified": open_roll_verified,
             "channel_index": channel_index, "path": path,
             "step": step, "bpm": bpm, "text": text, "beats_per_chord": beats_per_chord,
             "octave": octave, "bass": bass, "seconds": seconds,
             "humanize": humanize}.items() if v is not None}
        return _impl(action, **p)

"""B1: fl_state — one read that answers "what session am I looking at?".

The #1 root cause of bad FL behavior in prior sessions was acting on STALE
context: the agent assumed which pattern was selected, which channel was
open, whether notes had landed — and the piano-roll state file (which is
only refreshed when the ComposeWithLLM script runs) can be HOURS old
(the 11.8h incident, P4). `fl_state` gives the agent a fresh snapshot in
one trip, and its `piano_roll` section carries an **mtime guard**: the
file's last-modified time is returned and flagged stale when older than
`fresh_seconds`, so a stale note list can never be mistaken for live.

One MIDI trip, one command file, read-only (tier=read; no undo, no writes).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastmcp import FastMCP

from fl_studio_mcp.utils.connection import get_connection

# The FL scripts directory (where piano_roll_state.json lives).
_FL_SCRIPTS_DIR = Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings" / "Piano roll scripts"
_FALLBACK_SCRIPTS_DIR = Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings" / "Hardware" / "FLStudioMCP"


def _state_file() -> Path:
    for d in (_FL_SCRIPTS_DIR, _FALLBACK_SCRIPTS_DIR):
        p = d / "piano_roll_state.json"
        if p.exists():
            return p
    return _FL_SCRIPTS_DIR / "piano_roll_state.json"


def _compact_note(n: dict) -> dict:
    """The fields an agent verifies with; drops the 10 constant per-note
    fields (pan/fcut/fres/color/ticks/...) that made a 42-note roll ~15 KB (L6)."""
    out = {"midi": n.get("midi", n.get("number")), "time": n.get("time"),
           "duration": n.get("duration"),
           "velocity": round(float(n.get("velocity") or 0), 3)}
    for flag in ("slide", "porta", "muted"):
        if n.get(flag):
            out[flag] = True
    return out


def _read_piano_roll(fresh_seconds: int, max_notes: int | None = None) -> dict:
    """The piano-roll mtime guard (P4): state-file mtime, age, stale flag.
    Isolated so tests can exercise it without any FL round trip.

    Notes are compacted (L6). `max_notes` caps the list (fl_state passes a cap;
    fl_notes read_steps passes None = all); a capped list carries a summary
    (pitch range, end beat) and `notes_truncated: true`."""
    pr: dict = {}
    sf = _state_file()
    try:
        mtime = sf.stat().st_mtime
        age = max(0.0, time.time() - mtime)
        st = json.loads(sf.read_text())
        raw = st.get("notes") or []
        notes = [_compact_note(n) for n in raw]
        pr = {
            "ppq": st.get("ppq"),
            "note_count": len(raw),
            "notes": notes if max_notes is None else notes[:max_notes],
            "state_file_mtime": mtime,
            "age_seconds": round(age, 1),
            "stale": age > fresh_seconds if fresh_seconds > 0 else True,
        }
        if notes:
            pitches = [n["midi"] for n in notes if n["midi"] is not None]
            pr["summary"] = {
                "pitch_range": [min(pitches), max(pitches)] if pitches else None,
                "end_beat": max((n["time"] or 0) + (n["duration"] or 0) for n in notes),
                "slides": sum(1 for n in notes if n.get("slide")),
            }
        if max_notes is not None and len(notes) > max_notes:
            pr["notes_truncated"] = True
        # L18 (live 2026-10-01): after an FL restart a 4-minute-old state file
        # still passed the age check, but it described the PREVIOUS session's
        # roll. A file written before the running FL started is always stale.
        from fl_studio_mcp.utils.roll_session import fl_started_at
        started = fl_started_at()
        if started is not None and mtime < started:
            pr["stale"] = True
            pr["from_previous_fl_session"] = True
        if pr["stale"]:
            pr["warning"] = (
                "piano roll state was written by a PREVIOUS FL session (FL restarted "
                "since); " if pr.get("from_previous_fl_session") else ""
            ) + (
                f"piano roll state is {pr['age_seconds']}s old (> {fresh_seconds}s); "
                "it reflects the LAST ComposeWithLLM export, not the current roll. "
                "Re-trigger the script (and select ComposeWithLLM if FL was restarted) "
                "before trusting these notes."
            )
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        pr = {"note_count": 0, "stale": True,
              "warning": f"no piano roll state file ({e}); it is created by the ComposeWithLLM script"}
    return pr


def take_state_snapshot(fresh_seconds: int = 600) -> dict:
    """Get a single-trip snapshot of the FL Studio session.

    Everything here is read-only (no undo is taken; no state is changed).
    The `piano_roll` section is the guard against acting on stale note data:
    it reports the state file's mtime, its age in seconds, and whether it is
    STALE (older than `fresh_seconds`). A stale file means the last ComposeWithLLM
    export is old — re-trigger the script before trusting the note list.

    Args:
        fresh_seconds: a piano-roll state newer than this is "fresh"
            (default 600s = 10 min; pass 0 to always treat it as stale).
    """
    out: dict = {
        "piano_roll": _read_piano_roll(fresh_seconds, max_notes=16),
    }

    # The FL-side snapshot (bpm/transport/patterns/channels) is one MIDI trip.
    # send_command() adds the protocol-v2 envelope (request_id + protocol_version)
    # itself, so we pass the plain action string + params — NOT a pre-built dict
    # (passing a dict here double-wraps `action` and the controller can't parse it).
    conn = get_connection()
    result = conn.send_command("state.snapshot", {})
    out["success"] = bool(result.get("success", False))
    # protocol v2 = the response echoed our request_id (pre-v2 controllers
    # return no id; _legacy_response is set by the transport in that case).
    out["protocol_v2"] = result.get("request_id") is not None
    if not out["success"]:
        out["error"] = result.get("error") or result.get("_debug_error")
        return out

    state = result.get("state", {})

    # --- the rest straight from FL --------------------------------------
    out["bpm"] = state.get("bpm")
    out["transport"] = state.get("transport", {})
    out["patterns"] = state.get("patterns", [])
    out["selected_pattern"] = state.get("selected_pattern")
    # active_pattern + active_is_default (controller v10.4h+): the pattern
    # FL is actually reading/writing right now.  _named_patterns() in the
    # controller skips default (empty) patterns, so the active pattern can
    # be a default that does not appear in `patterns`.  When
    # active_is_default is true the agent should not trust empty step reads
    # (fl-patterns skill: "a select can report success while the active
    # pattern drifts back to an empty default").
    out["active_pattern"] = state.get("active_pattern", state.get("selected_pattern"))
    out["active_is_default"] = bool(state.get("active_is_default", False))
    out["channel_count"] = state.get("channel_count")
    out["selected_channel"] = state.get("selected_channel")

    # The project title + path (scratch detection depends on it).
    proj = state.get("project") or {}
    out["project"] = {
        "title": proj.get("title"),
        "path": proj.get("path"),
    }
    out["fl_version"] = state.get("fl_version") or _fl_version(conn)

    # S4 part ledger: which patterns have parts this server has written, and
    # how many channels/notes per pattern. This is the read-back that lets an
    # agent (and fl_pattern chain) know what is already in each pattern without
    # opening every roll.
    try:
        from fl_studio_mcp.utils import ledger as L
        pats = L.known_patterns(None)
        out["parts"] = [
            {"pattern": pt, "channels": len(L.get_pattern_parts(None, pt))}
            for pt in pats
        ]
    except Exception:  # noqa: BLE001 - ledger is best-effort
        out["parts"] = []

    return out


_VERSION_CACHE: dict[str, str] = {}


def _fl_version(conn) -> str | None:
    """L7: state.snapshot leaves fl_version null on this controller; the
    proven ui.getVersion safe-read has it ('Producer Edition v26.1.6 [build
    5406]'). One extra trip, cached for the server process."""
    if "v" in _VERSION_CACHE:
        return _VERSION_CACHE["v"]
    try:
        r = conn.send_command("ui.call", {"name": "getVersion"}, timeout=5.0)
    except Exception:  # noqa: BLE001
        return None
    if isinstance(r, dict) and r.get("success") and r.get("result"):
        _VERSION_CACHE["v"] = str(r["result"]).strip("' \"")
        return _VERSION_CACHE["v"]
    return None


def register_state_tools(mcp: FastMCP) -> None:
    """Register the B1 fl_state tool."""
    from fl_studio_mcp.tools.state import take_state_snapshot as _impl

    @mcp.tool(name="fl_state")
    def fl_state(fresh_seconds: int = 600) -> dict:
        """One-trip snapshot of the FL Studio session (read-only).

        Returns in a single MIDI trip: bpm, transport (playing/recorded/
        position), all patterns with the active one marked, channel count,
        the selected channel, FL version, and the piano-roll state with an
        **mtime guard** — the note list's last-export time, its age in
        seconds, and a `stale` flag (true when older than `fresh_seconds`).
        A stale piano roll means the notes reflect the last ComposeWithLLM
        export, not what's in the roll now: re-trigger the script before
        trusting them (the 11.8-hour stale-file incident, P4).

        Use this FIRST after every FL restart or before any write batch —
        it is the guard against acting on assumed context.

        Args:
            fresh_seconds: piano-roll states older than this are flagged
                stale (default 600; 0 = always stale).
        """
        return _impl(fresh_seconds=fresh_seconds)

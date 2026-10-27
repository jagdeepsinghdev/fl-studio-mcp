"""fl_launchpad — Launchpad (LP) as a human-in-the-loop grid for FL.

One tool, 5 actions (server-side only: no controller restart needed):

  status    — input monitor state (new notes since last apply), mapping,
              output port presence.
  map       — set the grid mapping (rows, cols, first_note, pattern_row,
              channels per row). Persisted to lp_mapping.json in the
              FLStudioMCP hardware dir.
  calibrate — press any LP pad; the tool anchors first_note to the note it
              actually saw (model-agnostic: MK1/MK2/Pro/FLkey grids all use
              plain note messages).
  apply     — consume NEW notes from the controller's input log
              (input_notes.jsonl, written by the v10.1 input monitor) and
              translate them to FL actions: pattern-row taps select
              patterns; grid taps toggle the step-sequencer bit for the
              mapped channel in the active/target pattern.
  light     — display side: for each mapped channel's active steps, send
              note-on/off to the LP via the "FL Studio MCP Out" MIDI port.

Data path (all pieces already exist):
  LP pad → FL's MIDI input (one-time manual pick, see LAUNCHPAD-SETUP.md)
         → our controller's virtual port → input_notes.jsonl
         → fl_launchpad(apply) → channels.setGridBit / patterns.jumpToPattern
  FL state → fl_launchpad(light) → "FL Studio MCP Out" → (IAC/USB) → LP pads.

Mapping model: an R×C grid addressed row-major by plain note numbers:
  note = first_note + row*cols + col.  One optional `pattern_row` (default 0)
  turns that row into pattern launch (col = pattern number). Remaining rows
  map to channels: `channels` list (indices or names) is applied top-to-
  bottom starting at the first non-pattern row; if fewer names than rows,
  later rows are ignored by apply/light.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths & persistence
# ---------------------------------------------------------------------------

HARDWARE_DIR = Path(os.path.expanduser(
    "~/Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP"))
MAPPING_FILE = HARDWARE_DIR / "lp_mapping.json"
STATE_FILE = HARDWARE_DIR / "lp_state.json"
INPUT_LOG = HARDWARE_DIR / "input_notes.jsonl"
MIDI_OUT_PORT = "FL Studio MCP Out"

DEFAULT_MAPPING: dict[str, Any] = {
    "rows": 8,
    "cols": 8,
    "first_note": 0,
    "pattern_row": 0,
    "channels": [0, 1, 2, 3, 4, 5, 6, 7],
}

# ---------------------------------------------------------------------------
# Pure mapping math (unit-testable)
# ---------------------------------------------------------------------------


def pad_to_cell(note: int, first_note: int, cols: int,
                rows: int = 128) -> tuple[int, int] | None:
    """Note → (row, col) for a row-major grid, or None if outside the
    rows×cols box."""
    rel = int(note) - int(first_note)
    if rel < 0:
        return None
    row, col = divmod(rel, int(cols))
    if row >= rows:
        return None
    return (row, col)


def cell_to_pad(row: int, col: int, first_note: int,
                cols: int) -> int:
    """(row, col) → note for a row-major grid."""
    return int(first_note) + int(row) * int(cols) + int(col)


def resolve_target(cell: tuple[int, int],
                   mapping: dict[str, Any]) -> tuple[str, int, int]:
    """(row, col) → ("pattern", pattern_number, 0) for the pattern row,
    else ("step", channel_index, col). Pattern numbers are 1-based
    (col+1); the channel value is the mapping list entry for that row.
    """
    row, col = cell
    if row == int(mapping.get("pattern_row", 0)):
        return ("pattern", col + 1, 0)
    chans = mapping.get("channels", [])
    step_rows = [r for r in range(int(mapping.get("rows", 8)))
                 if r != int(mapping.get("pattern_row", 0))]
    idx = step_rows.index(row) if row in step_rows else None
    if idx is None or idx >= len(chans):
        raise ValueError(
            f"row {row} has no mapped channel (channels={chans})")
    return ("step", chans[idx], col)


def parse_input_event(line: str) -> dict | None:
    """One JSONL line from input_notes.jsonl → record dict (or None)."""
    try:
        rec = json.loads(line)
        return {"status": int(rec.get("status", 0)),
                "note": int(rec.get("note", 0)),
                "vel": int(rec.get("vel", 0))}
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def note_to_action(record: dict, mapping: dict[str, Any]) -> dict | None:
    """A note record → the FL action it represents (None if not a grid pad).

    Only note-ON with velocity > 0 acts (tap = toggle). The same pad tapped
    again returns the same action; the toggle itself is resolved against
    current state at apply time (read-modify-write), so repeats toggle.
    """
    if record.get("status") != 0x90 or record.get("vel", 0) <= 0:
        return None
    cell = pad_to_cell(record["note"], mapping.get("first_note", 0),
                       mapping.get("cols", 8), mapping.get("rows", 8))
    if cell is None:
        return None
    kind, a, b = resolve_target(cell, mapping)
    if kind == "pattern":
        return {"kind": "pattern", "pattern": a}
    return {"kind": "step", "channel": a, "step": b}

# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        pass
    return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def get_mapping() -> dict[str, Any]:
    m = dict(DEFAULT_MAPPING)
    m.update(_load_json(MAPPING_FILE, {}))
    return m


def set_mapping(**kw: Any) -> dict[str, Any]:
    m = get_mapping()
    for k, v in kw.items():
        if v is not None and k in (
                "rows", "cols", "first_note", "pattern_row", "channels"):
            m[k] = int(v) if k in ("rows", "cols", "first_note", "pattern_row") else v
    _save_json(MAPPING_FILE, m)
    return m


def _state() -> dict[str, Any]:
    return _load_json(STATE_FILE, {"last_offset": 0})


def _save_state(s: dict[str, Any]) -> None:
    _save_json(STATE_FILE, s)


def read_new_input_records() -> list[dict]:
    """Records appended to input_notes.jsonl since the last consumed offset.
    The offset is advanced only by `apply` (not by status/calibrate)."""
    s = _state()
    offset = int(s.get("last_offset", 0))
    out: list[dict] = []
    if not INPUT_LOG.exists():
        return out
    with open(INPUT_LOG, "r") as f:
        f.seek(offset)
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = parse_input_event(line)
            if rec:
                out.append(rec)
    return out


def pending_count() -> int:
    """Number of grid-pad note-ONs waiting to be applied (for status)."""
    m = get_mapping()
    return sum(1 for r in read_new_input_records() if note_to_action(r, m))


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def _action_status() -> dict[str, Any]:
    m = get_mapping()
    log_info = {"exists": INPUT_LOG.exists()}
    if INPUT_LOG.exists():
        try:
            st = INPUT_LOG.stat()
            log_info["bytes"] = st.st_size
            log_info["mtime_age_s"] = round(time.time() - st.st_mtime, 1)
        except Exception:  # noqa: BLE001
            pass
    return {
        "action": "status",
        "success": True,
        "mapping": m,
        "input_log": log_info,
        "pending_note_ons": pending_count(),
        "state_file": str(STATE_FILE),
        "note": ("input log is written by the v10.1 controller once it has "
                 "processed its first command; FL's MIDI input must be set "
                 "to the Launchpad (or an IAC bus feeding it) — see "
                 "LAUNCHPAD-SETUP.md"),
    }


def _action_map(params: dict[str, Any]) -> dict[str, Any]:
    m = set_mapping(**{k: v for k, v in params.items() if k in (
        "rows", "cols", "first_note", "pattern_row", "channels")})
    return {"action": "map", "success": True, "mapping": m,
            "persisted_to": str(MAPPING_FILE)}


def _action_calibrate() -> dict[str, Any]:
    """Anchor first_note to the most recent note-ON actually observed."""
    recs = read_new_input_records()
    ons = [r for r in recs if r.get("status") == 0x90 and r.get("vel", 0) > 0]
    if not ons:
        return {"action": "calibrate", "success": False,
                "error": ("no note-ONs in the input log yet — press a pad "
                          "now (FL's MIDI input must be the Launchpad). "
                          "Is the v10.1 controller loaded? (fl_connect "
                          "status)")}
    note = ons[-1]["note"]
    m = set_mapping(first_note=note)
    return {"action": "calibrate", "success": True,
            "first_note": note,
            "mapping": m,
            "note": "grid anchored to the last pad you pressed; tap the "
                    "top-left pad of your grid if it wasn't that one"}


def _action_apply(conn=None) -> dict[str, Any]:
    """Consume pending pad taps → step toggles / pattern selects.

    Toggle = read the channel's current step sequence, flip the target bit,
    write it back (one controller round trip per pad). Pattern taps select
    via patterns.jumpToPattern (refused for non-existent patterns by the
    controller)."""
    from fl_studio_mcp.tools.channel_v2 import fl_channel as _ch
    from fl_studio_mcp.tools.pattern_v2 import fl_pattern as _pat

    m = get_mapping()
    recs = read_new_input_records()
    actions = [a for a in (note_to_action(r, m) for r in recs) if a]

    # advance the offset regardless (consumed = consumed; failures reported)
    s = _state()
    if INPUT_LOG.exists():
        s["last_offset"] = INPUT_LOG.stat().st_size
    _save_state(s)

    applied, errors = [], []
    for a in actions:
        try:
            if a["kind"] == "pattern":
                r = _pat("select", pattern=a["pattern"], conn=conn)
            else:
                seq = _ch("get_steps", index=a["channel"], conn=conn)
                cur = (seq.get("result") or {}).get("sequence", [])
                n = max(len(cur), a["step"] + 1)
                bits = [1 if i < len(cur) and cur[i] else 0 for i in range(n)]
                bits[a["step"]] = 1 - bits[a["step"]]
                r = _ch("set_steps", index=a["channel"], steps=bits,
                        conn=conn)
            ok = bool(r.get("success"))
            (applied if ok else errors).append({"tap": a,
                                                "result": r.get("error") or ok})
        except Exception as e:  # noqa: BLE001
            errors.append({"tap": a, "error": str(e)[:200]})
    return {"action": "apply", "success": True,
            "consumed": len(actions), "applied": len(applied),
            "errors": errors,
            "next": "fl_launchpad(action='light') to refresh the grid"}


def _action_light() -> dict[str, Any]:
    """Send pad display: note-on for active steps, note-off for the rest.
    Uses the loop's "FL Studio MCP Out" virtual port (routed to the LP via
    IAC or direct USB selection). Never touches the controller."""
    import rtmidi

    from fl_studio_mcp.tools.channel_v2 import fl_channel as _ch

    m = get_mapping()
    rows = int(m.get("rows", 8))
    cols = int(m.get("cols", 8))
    pr = int(m.get("pattern_row", 0))
    chans = m.get("channels", [])

    out = rtmidi.MidiOut()
    try:
        names = [str(p) for p in (out.get_ports() or [])]
        match = [p for p in names if p.startswith(MIDI_OUT_PORT)]
        if not match:
            return {"action": "light", "success": False,
                    "error": f"no MIDI output port named {MIDI_OUT_PORT!r} "
                             "(is the fl-midi-loop agent running?)",
                    "available_ports": names}
        out.open_port(names.index(match[0]))
        sent = 0
        step_rows = [r for r in range(rows) if r != pr]
        for i, ch in enumerate(chans):
            if i >= len(step_rows):
                break
            row = step_rows[i]
            if isinstance(ch, str):
                # name → index via a channel list read (best effort)
                res = _ch("get_steps", index=0, conn=None)  # noqa: F841
                return {"action": "light", "success": False,
                        "error": "channel names in the mapping are not "
                                 "resolved yet; use channel indices"}
            try:
                seq = _ch("get_steps", index=int(ch), conn=None)
                cur = (seq.get("result") or {}).get("sequence", [])
            except Exception:  # noqa: BLE001
                cur = []
            for c in range(cols):
                note = cell_to_pad(row, c, m.get("first_note", 0), cols)
                on = c < len(cur) and bool(cur[c])
                out.send_message([0x9B if on else 0x8B, note,
                                  96 if on else 0])
                sent += 1
        return {"action": "light", "success": True, "notes_sent": sent}
    except Exception as e:  # noqa: BLE001
        return {"action": "light", "success": False, "error": str(e)[:200]}
    finally:
        try:
            out.close()
        except Exception:  # noqa: BLE001
            pass

# ---------------------------------------------------------------------------
# Tool surface
# ---------------------------------------------------------------------------

ACTIONS = ("status", "map", "calibrate", "apply", "light")


def fl_launchpad(action: str, conn=None, **params: Any) -> dict:
    """Control a Novation-style Launchpad grid against FL's step sequencer.

    Actions:
      status    — mapping + input-monitor state (pending pad taps).
      map       — rows, cols, first_note, pattern_row, channels=[…].
      calibrate — press a pad first; anchors the grid to the note seen.
      apply     — consume pending pad taps → step toggles / pattern selects.
      light     — light the grid to match FL's current step state.

    LP input reaches the controller's virtual port (input_notes.jsonl);
    FL's MIDI input must be the Launchpad (one-time manual pick — see
    LAUNCHPAD-SETUP.md). No controller restart is needed for this tool.
    """
    if action not in ACTIONS:
        return {"success": False,
                "error": f"unknown action {action!r}",
                "valid_actions": list(ACTIONS)}
    if action == "status":
        return _action_status()
    if action == "map":
        return _action_map(params)
    if action == "calibrate":
        return _action_calibrate()
    if action == "apply":
        return _action_apply(conn)
    if action == "light":
        return _action_light()
    raise ValueError(f"unhandled action {action!r}")  # pragma: no cover


def register_launchpad_tools(mcp) -> None:
    """Register the fl_launchpad MCP tool."""
    from fl_studio_mcp.tools.launchpad import fl_launchpad as _impl

    @mcp.tool()
    def fl_launchpad(action: str, rows: int | None = None,
                     cols: int | None = None,
                     first_note: int | None = None,
                     pattern_row: int | None = None,
                     channels: list | None = None) -> dict:
        """Control a Launchpad-style 8x8 grid against FL's step sequencer.

        Actions: status | map | calibrate | apply | light.
        map(rows, cols, first_note, pattern_row, channels=[…]) persists the
        grid mapping; calibrate anchors first_note to the pad you press;
        apply consumes pending pad taps into step toggles / pattern
        selects; light refreshes the pads to match FL's current steps.
        Requires the v10.1 controller (input monitor) and FL's MIDI input
        set to the Launchpad — see LAUNCHPAD-SETUP.md.
        """
        return _impl(action, rows=rows, cols=cols,
                     first_note=first_note,
                     pattern_row=pattern_row,
                     channels=channels)

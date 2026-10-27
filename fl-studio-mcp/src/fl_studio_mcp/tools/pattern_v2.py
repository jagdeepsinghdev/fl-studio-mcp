"""B5: fl_pattern — one tool for pattern control.

Actions: create | select | rename | set_len | clone.
**NO clear** — clearing a pattern's data is destructive and lives in
fl_delete (target=pattern_data). (plan §4 rule 3.)

CRITICAL (C4, live-verified 2026-10-01): `patterns.setPatternName` is
**2-arg `(index, name)`** in live v45. The 3-arg call with `flags`
**CRASHES FL** (EAccessViolation). rename routes to the existing controller
`patterns.create`/`patterns.setName` path which already uses the 2-arg form.

- create: names the next free slot (no jump → no blocking rename dialog),
  optional length/color.
- select: refuses non-existent (default) patterns (jumping to an empty
  pattern opens a blocking modal dialog — §2.4).
- clone: into slot+1 (later patterns shift up — re-list after).
"""

from __future__ import annotations

import json
from typing import Any

from fastmcp import FastMCP

from fl_studio_mcp.tools.transport_v2 import _safe_send, shape_response

ACTIONS = ("create", "select", "rename", "set_len", "clone", "chain")

_PARAM_SPEC = {
    "create": (("name", "str", None, None),
               ("length_beats", "int", 0, None),
               ("color", "int", 0, None)),
    "select": (("pattern", "int", 1, None),),
    "rename": (("pattern", "int", 1, None), ("name", "str", None, None)),
    "set_len": (("pattern", "int", 1, None), ("beats", "int", 1, None)),
    "clone": (("pattern", "int", 1, None), ("name", "str", None, None)),
    "chain": (("name", "str", None, None), ("sections", "list", None, None)),
}

_OPTIONAL = {("create", "length_beats"), ("create", "color"),
             ("clone", "name")}


def validate(action: str, params: dict[str, Any]) -> list[str]:
    if action not in ACTIONS:
        return [f"unknown action {action!r}. Valid: {', '.join(ACTIONS)}"]
    errs = []
    for name, kind, lo, hi in _PARAM_SPEC[action]:
        if (action, name) in _OPTIONAL and name not in params:
            continue
        if name not in params:
            errs.append(f"{action}: missing required param '{name}'")
            continue
        v = params[name]
        if kind == "int":
            if not isinstance(v, int) or isinstance(v, bool):
                errs.append(f"{action}.{name}: not an int ({v!r})")
            elif (lo is not None and v < lo) or (hi is not None and v > hi):
                errs.append(f"{action}.{name}: {v} out of range [{lo}, {hi}]")
        elif kind == "str":
            if not isinstance(v, str) or not v.strip():
                errs.append(f"{action}.{name}: non-empty string required")
        elif kind == "list":
            if not isinstance(v, list) or not v:
                errs.append(f"{action}.{name}: non-empty list required")
    # chain: validate each section shape
    if action == "chain":
        for i, sec in enumerate(params.get("sections", [])):
            if not isinstance(sec, dict):
                errs.append(f"chain.sections[{i}]: must be an object {{pattern, repeat}}")
                continue
            if not isinstance(sec.get("pattern"), int) or isinstance(sec.get("pattern"), bool) or sec.get("pattern", 0) < 1:
                errs.append(f"chain.sections[{i}].pattern: positive int required")
            rep = sec.get("repeat", 1)
            if not isinstance(rep, int) or isinstance(rep, bool) or rep < 1:
                errs.append(f"chain.sections[{i}].repeat: positive int required")
    return errs


def _route(action: str, p: dict[str, Any]) -> tuple[str, dict]:
    if action == "create":
        cparams: dict[str, Any] = {"name": str(p["name"])}
        if "length_beats" in p:
            cparams["length_beats"] = int(p["length_beats"])
        if "color" in p:
            cparams["color"] = int(p["color"])
        return "patterns.create", cparams
    if action == "select":
        return "patterns.select", {"pattern": int(p["pattern"])}
    if action == "rename":
        # 2-arg setPatternName in the controller (C4: 3-arg crashes FL)
        return "patterns.setName", {"pattern": int(p["pattern"]),
                                   "name": str(p["name"])}
    if action == "set_len":
        # controller reads a 0-based `index` (Pattern 1 = 0); `pattern` was
        # ignored, so every set_len resized Pattern 1 (audit 2026-10-01)
        return "patterns.setLength", {"index": int(p["pattern"]) - 1,
                                     "beats": int(p["beats"])}
    if action == "clone":
        cparams = {"pattern": int(p["pattern"])}
        if p.get("name"):
            cparams["name"] = str(p["name"])
        return "patterns.clone", cparams
    raise ValueError(f"unhandled action {action!r}")


def _read_step_params(conn, pat: int, rows: dict[int, list[bool]]) -> dict[int, dict]:
    """{channel: {step: (velocity, shift)}} for the ACTIVE steps of pattern `pat` (one exec trip;
    getCurrentStepParam reads the active pattern, so `pat` is selected first). -1 = unset."""
    want = {ci: [i for i, on in enumerate(r) if on] for ci, r in rows.items()}
    if not want:
        return {}
    from fl_studio_mcp.tools.mixer_v2 import _exec
    conn.send_command("patterns.select", {"pattern": int(pat)})
    code = ("import channels, json\n"
            f"W = {json.dumps({str(k): v for k, v in want.items()})}\n"
            "print(json.dumps({c: [[channels.getCurrentStepParam(int(c), s, 1, True), "
            "channels.getCurrentStepParam(int(c), s, 7, True)] for s in st] for c, st in W.items()}))")
    try:
        got = json.loads(_exec(conn, code))
    except Exception:  # noqa: BLE001 — feel is best effort; steps still chain
        return {}
    return {int(c): {s: tuple(v) for s, v in zip(want[int(c)], vals)} for c, vals in got.items()}


def _write_step_params(conn, pat: int, items: list[tuple[int, int, int, int]]) -> int:
    """Set (channel, step, param, value) step params in pattern `pat` in one exec trip."""
    if not items:
        return 0
    from fl_studio_mcp.tools.mixer_v2 import _exec
    code = ("import channels\n"
            f"for c, s, p, v in {json.dumps(items)}:\n"
            f"    channels.setStepParameterByIndex(c, {int(pat)}, s, p, v, True)\n"
            "print(1)")
    try:
        _exec(conn, code)
        return len(items)
    except Exception:  # noqa: BLE001
        return 0


def _chain(params: dict, conn, *, trigger=None, open_roll=None, invalidate=None,
           roll_read=None, state_mtime=None, ran_since=None, ledger_pid=None,
           ensure_script=None) -> dict:
    """S5: build one "Full" pattern from a chain of section patterns.

    Every section pattern must already have been written through this server
    (fl_notes write_steps / fl_channel set_steps / batch) so its parts are in
    the ledger; FL can only read back the OPEN roll, so the ledger is the only
    way to place another channel's notes. Refuses, listing the missing parts,
    if a section has no recorded part.

    The side-effect collaborators (trigger, roll selection, script selection,
    roll read-back, the mtime oracle) are injectable so the offset/concat math
    is unit-testable offline with no FL.
    """
    from fl_studio_mcp.tools.piano_roll import _write_request
    from fl_studio_mcp.tools.state import _read_piano_roll
    from fl_studio_mcp.utils import ledger as L
    from fl_studio_mcp.utils import roll_session as rs
    from fl_studio_mcp.utils.fl_trigger import get_trigger

    trigger = trigger or get_trigger().trigger
    # channels.selectOne does NOT retarget an already-open roll (rule 6b):
    # open_roll_for_channel selects + proves the roll title on screen.
    open_roll = open_roll or rs.open_roll_for_channel
    ensure_script = ensure_script or rs.ensure_script_selected
    invalidate = invalidate or rs.invalidate
    state_mtime = state_mtime or rs.state_mtime
    ran_since = ran_since or rs.ran_since
    roll_read = roll_read or (lambda: _read_piano_roll(600))
    if ledger_pid is None:
        from fl_studio_mcp.utils.roll_session import fl_pid
        ledger_pid = fl_pid()

    sections = params["sections"]

    # 1. section lengths (beats) + step row lengths from FL (read-only)
    info = []
    for sec in sections:
        pat = int(sec["pattern"])
        rep = int(sec.get("repeat", 1))
        lp = conn.send_command("patterns.getLength", {"index": pat - 1})
        beats = int(lp.get("length_beats") or 0)
        if beats <= 0:
            return {"success": False, "error":
                    f"section pattern {pat} has no length ({lp.get('error')})"}
        info.append((pat, rep, beats))

    total_beats = sum(b * r for (pat, r, b) in info)
    total_steps = total_beats * 4

    # notes: from the ledger, placed at each section's CUMULATIVE start and
    # repeated. Validated BEFORE anything is created so a refusal leaves
    # nothing behind.
    missing: list[str] = []
    per_ch: dict[int, list[dict]] = {}
    section_start = 0.0
    for (pat, rep, beats) in info:
        parts = L.get_pattern_parts(ledger_pid, pat)
        if not parts:
            missing.append(f"pattern {pat} (has {rep} repeat(s)) — no recorded part")
        for i in range(rep):
            for part in parts:
                notes = L.notes_at([part], section_start + i * beats)
                per_ch.setdefault(part["channel_index"], []).extend(notes)
        section_start += rep * beats
    # step rows (+ velocity/shift step params) of every section, read BEFORE anything is
    # created: a step-sequencer-only section (drums, a Sampler loop) is a valid section
    # (2026-10-11: an Afrobeats intro/beat chain was refused for having no roll notes).
    channels = conn.send_command("channels.getAll").get("channels", [])
    sec_rows: dict[int, dict[int, list[bool]]] = {}
    sec_params: dict[int, dict] = {}
    for (pat, rep, beats) in info:
        rows = {}
        # live 2026-10-11: getStepSequence read the ACTIVE pattern whatever target_pattern said, so
        # every section came back as the active one's rows (a Song with the kick in the intro).
        # Select the section first, then read.
        conn.send_command("patterns.select", {"pattern": int(pat)})
        for ch in channels:
            ci = ch.get("index", ch.get("number"))
            g = conn.send_command("channels.getStepSequence",
                                  {"channel": ci, "steps": beats * 4, "target_pattern": pat})
            seq = (list(g.get("sequence") or []) + [False] * (beats * 4))[:beats * 4]
            if any(seq):
                rows[ci] = seq
        sec_rows[pat] = rows
        sec_params[pat] = _read_step_params(conn, pat, rows)
    missing = [m for m, (pat, _, _) in zip(missing, [i for i in info
               if not L.get_pattern_parts(ledger_pid, i[0])]) if not sec_rows.get(pat)]
    if missing:
        return {"action": "chain", "success": False,
                "error": "refused — these section patterns have no notes in the ledger and "
                         "no steps (write them first): " + ", ".join(missing),
                "missing": missing, "note": "nothing was created"}

    # 2. new pattern
    was_active = None
    try:
        was_active = int(conn.send_command("probe.patterns").get("active_pattern"))
    except Exception:  # noqa: BLE001
        was_active = None
    create = conn.send_command("patterns.create",
                               {"name": str(params["name"]),
                                "length_beats": total_beats})
    if not create.get("success") and create.get("error"):
        return {"action": "chain", "success": False, "error": create["error"]}
    newp = int(create.get("pattern") or 0)
    if not newp:
        return {"action": "chain", "success": False,
                "error": f"patterns.create returned no pattern index ({create})"}
    conn.send_command("patterns.select", {"pattern": newp})

    # 3. steps: concat+repeat each channel's section rows into the new pattern, then the
    #    velocity/shift step params at their new positions (one trip)
    ch_rows = []
    params_out: list[tuple[int, int, int, int]] = []
    for ch in channels:
        ci = ch.get("index", ch.get("number"))
        row: list[bool] = []
        for (pat, rep, beats) in info:
            seq = sec_rows[pat].get(ci) or [False] * (beats * 4)
            for i in range(rep):
                base = len(row)
                row.extend(seq)
                for step, (vel, shift) in sec_params[pat].get(ci, {}).items():
                    if vel is not None and vel >= 0:
                        params_out.append((ci, base + step, 1, vel))
                    if shift is not None and shift > 0:
                        params_out.append((ci, base + step, 7, shift))
        if len(row) != total_steps:
            row = (row + [False] * total_steps)[:total_steps]
        if any(row):
            conn.send_command("channels.setStepSequence",
                              {"channel": ci, "pattern": row,
                               "target_pattern": newp})
        ch_rows.append((ci, ch.get("name"), row))
    params_written = _write_step_params(conn, newp, params_out)

    ok = True
    refused: list[dict] = []
    written = 0
    script_ready = False
    for ci, chname, row in ch_rows:
        notes = per_ch.get(ci)
        if not notes:
            continue
        if not script_ready:  # selection persists per FL process: once, not forced
            try:
                ensure_script()
            except Exception:  # noqa: BLE001
                pass
            script_ready = True
        conn.send_command("patterns.select", {"pattern": newp})
        roll = open_roll(ci)
        if not roll.get("ok"):
            ok = False
            refused.append({"channel": ci, "name": chname, "error": roll.get("error")})
            continue
        conn.send_command("patterns.select", {"pattern": newp})
        invalidate()
        before = state_mtime()
        _write_request([{"action": "clear"},
                        {"action": "add_notes", "notes": notes}])
        trigger()
        pr = roll_read()
        verified = bool(ran_since(before)
                        and pr.get("note_count") == len(notes))
        L.record_notes(ledger_pid, newp, ci, chname, notes,
                       {"notes_added": len(notes), "verified": verified},
                       mode="replace")
        written += 1
        if not verified:
            ok = False

    if was_active and was_active != newp:
        conn.send_command("patterns.select", {"pattern": was_active})
    summary = {}
    for ci, chname, row in ch_rows:
        bits = "steps" if any(row) else "-"
        n = f" + {len(per_ch[ci])} notes" if ci in per_ch else ""
        summary[f"ch{ci} {chname or '?'}"] = bits + n
    return {"action": "chain", "success": bool(ok),
            "new_pattern": newp, "total_beats": total_beats,
            "total_steps": total_steps, "channels": summary,
            "notes_written": written, "step_params_written": params_written,
            "active_restored": was_active,
            "refused_channels": refused}


def fl_pattern(action: str, conn=None, **params: Any) -> dict:
    """Control FL Studio patterns (one tool, 6 actions).

    Actions:
      create (name, [length_beats], [color]) — names the next free slot
          (no jump → no blocking dialog); optional length/color
      select (pattern 1-based) — refuses non-existent patterns
      rename (pattern, name) — 2-arg setPatternName (3-arg CRASHES FL, C4)
      set_len (pattern, beats)
      clone (pattern, [name]) — into slot+1 (later patterns shift up); the
          previously active pattern stays active (L8)
      chain (name, sections=[{pattern, repeat}]) — build one "Full" pattern:
          concat every channel's step row (read live) and place every
          channel's notes (from the S4 part ledger) with per-section offsets,
          writing each roll and verifying notes_added. Refuses (lists the
          missing parts) if a section has no recorded part.

    clear is NOT here (destructive → fl_delete target=pattern_data).
    Writes carry same-trip state_after + one named undo.
    """
    errs = validate(action, params)
    if errs:
        return {"success": False, "error": "; ".join(errs),
                "valid_actions": list(ACTIONS)}

    if conn is None:
        from fl_studio_mcp.utils.connection import get_connection
        conn = get_connection()

    if action == "chain":
        return _chain(params, conn)

    # L8: clone makes the copy the ACTIVE pattern (controller behaviour),
    # which changes what is playing. Remember the active pattern and put it
    # back afterwards (shifted by one if the clone landed at or before it).
    was_active = None
    if action == "clone":
        try:
            was_active = int(conn.send_command("probe.patterns").get("active_pattern"))
        except Exception:  # noqa: BLE001
            was_active = None

    ca, cparams = _route(action, params)
    try:
        res = _safe_send(ca, cparams, conn)
    except Exception as e:
        return {"action": action, "success": False, "error": str(e)}

    if action == "clone" and was_active and res.get("success"):
        new = res.get("pattern") or (res.get("result") or {}).get("pattern")
        restore = was_active + 1 if new and int(new) <= was_active else was_active
        if not new or int(new) != restore:
            conn.send_command("patterns.select", {"pattern": restore})
        res = dict(res, active_restored=restore)

    return shape_response(action, res)


def register_pattern_tools_v2(mcp: FastMCP) -> None:
    """Register the B5 fl_pattern tool."""
    from fl_studio_mcp.tools.pattern_v2 import fl_pattern as _impl

    @mcp.tool()
    def fl_pattern(
        action: str,
        name: str | None = None,
        pattern: int | None = None,
        beats: int | None = None,
        length_beats: int | None = None,
        color: int | None = None,
        sections: list | None = None,
    ) -> dict:
        """Control FL Studio patterns (one tool, 6 actions).

        Actions: create | select | rename | set_len | clone | chain.
        rename uses 2-arg setPatternName (3-arg CRASHES FL — C4).
        chain(name, sections=[{pattern, repeat}]) builds one "Full" pattern
        from section patterns: concats every channel's step row and places
        every channel's notes (from the S4 part ledger) with per-section
        offsets, writing + verifying each roll. clear is NOT here
        (destructive → fl_delete target=pattern_data).
        """
        p = {k: v for k, v in {"name": name, "pattern": pattern, "beats": beats,
             "length_beats": length_beats, "color": color, "sections": sections}.items()
             if v is not None}
        return _impl(action, **p)

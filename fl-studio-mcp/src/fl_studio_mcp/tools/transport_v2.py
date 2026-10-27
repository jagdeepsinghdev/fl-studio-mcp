"""B2: fl_transport — one tool for all transport control.

Actions: play | stop | record | set_bpm | set_timesig | set_speed | set_swing |
loop | position. Every write is verified same-trip (the controller re-reads the
affected value in the same MIDI trip and returns `state_after`; the
dispatcher cross-checks it — never trust a success message, P5) and undoable
(one named saveUndo per write via the safety layer).

Schema: flat params (A6 pilot verdict pending — flat params + server-side
action validation is the safe default; the oneOf shape lands if the pilot
passes ≥95%). Unknown actions and bad params are rejected HERE, before
anything touches FL, with an error naming the valid actions/params.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from fl_studio_mcp.safety import SafeDispatcher, SessionState
from fl_studio_mcp.utils.connection import get_connection

ACTIONS = ("play", "stop", "record", "set_bpm", "set_timesig", "set_speed",
           "set_swing", "loop", "position")

# per-action param spec: (name, kind, lo, hi); kind in float|int|str|bool
# for str, the range is a tuple of allowed values.
_PARAM_SPEC = {
    "play": (),
    "stop": (),
    "record": (("armed", "bool", None, None),),
    "set_bpm": (("bpm", "float", 20.0, 300.0),),
    "set_timesig": (("numerator", "int", 1, 32), ("denominator", "int", 1, 32)),
    "set_speed": (("speed", "float", 0.25, 4.0),),
    "set_swing": (("swing", "float", 0.0, 1.0),),
    "loop": (("mode", "str", ("pattern", "song"), None),),
    "position": (("value", "float", 0.0, None),
                 ("unit", "str", ("seconds", "beats", "minutes"), None)),
}

# optional params (may be absent; unit defaults to seconds)
_OPTIONAL = {("position", "unit")}


def validate(action: str, params: dict[str, Any]) -> list[str]:
    """Return a list of param errors (empty = valid)."""
    if action not in ACTIONS:
        return [f"unknown action {action!r}. Valid: {', '.join(ACTIONS)}"]
    errors = []
    for name, kind, lo, hi in _PARAM_SPEC[action]:
        if (action, name) in _OPTIONAL and name not in params:
            continue
        if name not in params:
            errors.append(f"{action}: missing required param '{name}'")
            continue
        v = params[name]
        if kind == "float":
            try:
                v = float(v)
            except (TypeError, ValueError):
                errors.append(f"{action}.{name}: not a number ({v!r})")
                continue
            if lo is not None and v < lo:
                errors.append(f"{action}.{name}: {v} < {lo}")
            if hi is not None and v > hi:
                errors.append(f"{action}.{name}: {v} > {hi}")
        elif kind == "int":
            if not isinstance(v, int) or isinstance(v, bool):
                errors.append(f"{action}.{name}: not an int ({v!r})")
            elif (lo is not None and v < lo) or (hi is not None and v > hi):
                errors.append(f"{action}.{name}: {v} out of range [{lo}, {hi}]")
        elif kind == "bool":
            if not isinstance(v, bool):
                errors.append(f"{action}.{name}: not a bool ({v!r})")
        elif kind == "str":
            if v not in lo:
                errors.append(f"{action}.{name}: {v!r} not in {lo}")
    return errors


def _route(action: str, p: dict[str, Any]) -> tuple[str, dict]:
    """Map (action, params) → (controller action, controller params)."""
    if action == "play":
        return "transport.start", {}
    if action == "stop":
        return "transport.stop", {}
    if action == "record":
        return "transport.record", {"armed": bool(p.get("armed", False))}
    if action == "set_bpm":
        return "transport.setBPM", {"bpm": float(p["bpm"])}
    if action == "set_timesig":
        return "transport.setTimesig", {"numerator": int(p["numerator"]),
                                        "denominator": int(p["denominator"])}
    if action == "set_speed":
        return "transport.setPlaybackSpeed", {"speed": float(p["speed"])}
    if action == "set_swing":
        # global (project-wide) swing; channels.setSwing in the controller
        return "transport.setSwing", {"swing": float(p["swing"])}
    if action == "loop":
        return "transport.setLoopMode", {"mode": p["mode"]}
    if action == "position":
        # controller: setSongPos(position, mode) with mode 2 = seconds; it
        # reads position/mode (value/unit were ignored -> always jumped to 0).
        unit = p.get("unit", "seconds")
        secs = float(p["value"])
        if unit == "minutes":
            secs *= 60.0
        elif unit == "beats":
            secs *= 60.0 / float(p["_bpm"])  # fl_transport injects the live BPM
        return "transport.setPosition", {"position": secs, "mode": 2}
    raise ValueError(f"unhandled action {action!r}")


def _safe_send(action: str, params: dict, conn) -> dict:
    """Route a controller action through the safety dispatcher.

    The safety layer (A3) attaches the per-tier undo plan and validates the
    response evidence (undo_saved for writes, identity_ok for destructive).
    For transport actions (all writes, none destructive) this gives one
    named saveUndo per write and cross-checks state_after.
    """
    from fl_studio_mcp.dispatcher import DispatchContext, Dispatcher

    # Build a minimal dispatch context that uses our connection.
    ctx = DispatchContext(send=conn.send_command)

    # Build the registry with the controller action.
    registry = Dispatcher()

    def _handler(ctx2, params2):
        return ctx2.send(action, params2)

    registry.register(action, _handler)

    session = SessionState()
    safe = SafeDispatcher(registry, session)
    result = safe.dispatch(ctx, action, params)
    return result.response


_ENVELOPE = ("success", "error", "state_after", "undo_saved", "request_id",
             "protocol_version", "_legacy_response")


def shape_response(action: str, res: dict) -> dict:
    """Uniform domain-tool result: success/error/result/state_after/undo_saved.

    Read actions in this controller generation return their payload at the
    TOP level (no "result" wrapper) — e.g. plugins.getParams -> {"params": …}.
    Lift it into "result" so reads never come back as a bare success.
    """
    out: dict = {"action": action, "success": bool(res.get("success"))}
    if res.get("error"):
        out["error"] = res["error"]
    if res.get("result"):
        out["result"] = res["result"]
    elif res.get("success") and not res.get("error"):
        payload = {k: v for k, v in res.items() if k not in _ENVELOPE}
        if payload:
            out["result"] = payload
    if res.get("state_after"):
        out["state_after"] = res["state_after"]
    if res.get("undo_saved"):
        out["undo_saved"] = res["undo_saved"]
    return out


def fl_transport(action: str, conn=None, **params: Any) -> dict:
    """Control FL Studio playback and tempo.

    Actions:
      play, stop — start/stop playback
      record (armed: bool) — start/stop recording (arm first if armed)
      set_bpm (bpm: 20–300) — set the REAL tempo (not a speed multiplier)
      set_timesig (numerator, denominator: 1–32)
      set_speed (speed: 0.25–4.0) — playback speed multiplier (does NOT
          change the BPM; reset to 1.0 after using it)
      set_swing (swing: 0.0–1.0) — global project swing (typical groove 0.1–0.3)
      loop (mode: "pattern"|"song")
      position (value >= 0, unit: seconds|beats|minutes)

    Writes are verified same-trip (state_after) and undoable (one named
    saveUndo per write). Invalid actions/params are rejected before
    anything touches FL.

    Args:
        action: one of the actions above
        conn: optional connection override (tests)
        **params: action-specific (all validated here before FL is touched)
    """
    errs = validate(action, params)
    if errs:
        return {"success": False, "error": "; ".join(errs),
                "valid_actions": list(ACTIONS)}

    if conn is None:
        conn = get_connection()

    if action == "position" and params.get("unit") == "beats":
        bpm = conn.send_command("transport.getBPM").get("bpm")
        if not bpm:
            return {"action": action, "success": False,
                    "error": "position in beats needs the live BPM; transport.getBPM failed"}
        params = dict(params, _bpm=float(bpm))

    ca, cparams = _route(action, params)
    try:
        res = _safe_send(ca, cparams, conn)
    except Exception as e:
        return {"action": action, "success": False, "error": str(e)}

    return shape_response(action, res)


def register_transport_tools_v2(mcp: FastMCP) -> None:
    """Register the B2 fl_transport tool (the legacy fl_play/fl_stop/... are
    unregistered at B10; this is the replacement surface)."""
    from fl_studio_mcp.tools.transport_v2 import fl_transport as _impl

    @mcp.tool()
    def fl_transport(
        action: str,
        armed: bool | None = None,
        bpm: float | None = None,
        numerator: int | None = None,
        denominator: int | None = None,
        speed: float | None = None,
        swing: float | None = None,
        mode: str | None = None,
        value: float | None = None,
        unit: str | None = None,
    ) -> dict:
        """Control FL Studio playback and tempo (one tool, 9 actions).

        Actions: play | stop | record(armed) | set_bpm(20-300) |
        set_timesig(n,d) | set_speed(0.25-4.0) | set_swing(0.0-1.0, global) |
        loop(pattern|song) |
        position(value, unit=seconds|beats|minutes).

        Writes are verified same-trip (state_after) + one named undo.
        Invalid actions/params are rejected before FL is touched.
        """
        p = {k: v for k, v in {"armed": armed, "bpm": bpm, "numerator": numerator,
             "denominator": denominator, "speed": speed, "swing": swing, "mode": mode,
             "value": value, "unit": unit}.items() if v is not None}
        return _impl(action, **p)

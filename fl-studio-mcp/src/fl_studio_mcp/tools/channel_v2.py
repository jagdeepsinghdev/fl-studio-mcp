"""B4: fl_channel — one tool for channel (instrument) control.

Actions: set_vol | set_pan | rename | route | mute | solo | clone | add.

- set_vol / set_pan / mute / solo / rename / route: writes → same-trip
  state_after + one named undo.
- clone: NO importable channels.clone API in live v45 (probed). This is the
  UI/menu method (duplicate a channel in the Channel Rack) — registered but
  returns "Unknown action" until the native-menu automation exists (same gap
  as mixer.addFx). Documented in fl_help.
- add: the native Add-menu (the ONLY channel-creation path — there is no
  importable channels.add(); hard rule). Registered as the UI/menu method.

Schema: flat params + server-side validation (A6 oneOf pending).
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from fl_studio_mcp.tools.transport_v2 import _safe_send, shape_response

ACTIONS = ("list", "set_vol", "set_pan", "rename", "route", "mute", "solo",
           "clone", "add", "set_steps", "get_steps",
           "get_step_param", "set_step_param", "load_sample", "group")

_PARAM_SPEC = {
    "list": (),
    "set_vol": (("index", "int", 0, None), ("volume", "float", 0.0, 1.0)),
    "set_pan": (("index", "int", 0, None), ("pan", "float", -1.0, 1.0)),
    "rename": (("index", "int", 0, None), ("name", "str", None, None)),
    "route": (("index", "int", 0, None), ("to", "int", 0, None)),
    "mute": (("index", "int", 0, None), ("muted", "bool", None, None)),
    "solo": (("index", "int", 0, None), ("solo", "bool", None, None)),
    "clone": (("index", "int", 0, None), ("name", "str", None, None)),
    "add": (("name", "str", None, None), ("plugin", "str", None, None)),
    "load_sample": (("index", "int", 0, None), ("path", "str", None, None)),
    "group": (("name", "str", None, None), ("indices", "list", None, None)),
    "set_steps": (("index", "int", 0, None), ("steps", "list", None, None),
                 ("bars", "list", None, None), ("n_bars", "int", 1, None),
                 ("pattern", "int", 1, None)),
    "get_steps": (("index", "int", 0, None), ("steps", "int", 1, None),
                 ("pattern", "int", 1, None)),
    "get_step_param": (("index", "int", 0, None), ("step", "int", 0, None),
                      ("param", "any", "pVelocity", None),
                      ("pattern", "int", 1, None),
                      ("use_global", "bool", None, None)),
    "set_step_param": (("index", "int", 0, None), ("step", "int", 0, None),
                      ("param", "any", "pVelocity", None),
                      ("value", "int", 0, 127),
                      ("pattern", "int", 1, None),
                      ("use_global", "bool", None, None)),
}

_OPTIONAL = {("set_steps", "steps"), ("set_steps", "bars"), ("set_steps", "n_bars"),
             ("mute", "muted"), ("solo", "solo"), ("add", "name"),
             ("clone", "name"), ("set_steps", "pattern"),
             ("get_steps", "steps"), ("get_steps", "pattern"),
             ("get_step_param", "param"), ("get_step_param", "pattern"),
             ("get_step_param", "use_global"),
             ("set_step_param", "param"), ("set_step_param", "pattern"),
             ("set_step_param", "use_global")}


def _bars_to_row(bars: Any, n_bars: int | None = None) -> list[bool]:
    """S7: `bars=[[1,7],[1,13],...]` (1-based steps, 16 per bar) -> bool row,
    via the legacy tools/song_builder.expand_steps. A list shorter than
    `n_bars` CYCLES to fill it (default n_bars = len(bars): no cycling); a
    flat int list means "the same bar every bar" and needs n_bars."""
    from fl_studio_mcp.tools.song_builder import expand_steps
    if not isinstance(bars, list) or not bars:
        raise ValueError("must be a non-empty list of per-bar step lists")
    n = n_bars if n_bars is not None else (
        len(bars) if isinstance(bars[0], (list, tuple)) else 1)
    return expand_steps(bars, int(n))


def validate(action: str, params: dict[str, Any]) -> list[str]:
    if action not in ACTIONS:
        return [f"unknown action {action!r}. Valid: {', '.join(ACTIONS)}"]
    errs = []
    if action == "set_steps":
        # S7: exactly one of steps (bool row) / bars (1-based steps per bar)
        if "steps" in params and "bars" in params:
            return ["set_steps: give 'steps' OR 'bars', not both"]
        if "steps" not in params and "bars" not in params:
            errs.append("set_steps: missing required param 'steps' (or 'bars')")
        elif "bars" in params:
            try:
                params["steps"] = _bars_to_row(params["bars"], params.get("n_bars"))
            except (ValueError, TypeError, IndexError) as e:
                return [f"set_steps.bars: {e}"]
    for name, kind, lo, hi in _PARAM_SPEC[action]:
        if (action, name) in _OPTIONAL and name not in params:
            continue
        if name not in params:
            # add: plugin is required, name optional (defaults to plugin)
            if not (action == "add" and name == "name"):
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
            elif hi is not None and v > hi:
                errs.append(f"{action}.{name}: {v} > {hi}")
        elif kind == "bool":
            if not isinstance(v, bool):
                errs.append(f"{action}.{name}: not a bool ({v!r})")
        elif kind == "str":
            if not isinstance(v, str) or not v.strip():
                errs.append(f"{action}.{name}: non-empty string required")
        elif kind == "list":
            if not isinstance(v, list):
                errs.append(f"{action}.{name}: must be a list of booleans/ints")
    return errs


def _route(action: str, p: dict[str, Any]) -> tuple[str, dict]:
    if action == "list":
        # L11: the 21-tool surface had no way to list channels
        return "channels.getAll", {}
    if action == "set_vol":
        return "channels.setVolume", {"index": int(p["index"]),
                                     "volume": float(p["volume"])}
    if action == "set_pan":
        return "channels.setPan", {"index": int(p["index"]),
                                  "pan": float(p["pan"])}
    if action == "rename":
        return "channels.setName", {"index": int(p["index"]),
                                   "name": str(p["name"])}
    if action == "route":
        # controller reads channel_index / mixer_track (index/to were ignored:
        # every route silently sent channel 0 to the master — audit 2026-10-01)
        return "channels.routeToMixer", {"channel_index": int(p["index"]),
                                        "mixer_track": int(p["to"])}
    if action == "mute":
        return "channels.mute", {"index": int(p["index"]),
                                "muted": bool(p.get("muted", True))}
    if action == "solo":
        return "channels.solo", {"index": int(p["index"]),
                                "solo": bool(p.get("solo", True))}
    if action == "clone":
        # no importable clone API (v45); native-menu method
        return "channels.clone", {"index": int(p["index"]),
                                 "name": p.get("name", "")}
    if action == "add":
        # the ONLY channel-creation path is the native Add menu
        return "channels.add", {"plugin": str(p.get("plugin", "FL Keys")),
                                "name": str(p.get("name") or p.get("plugin", "FL Keys"))}
    if action == "set_steps":
        # controller reads 'channel' + 'pattern' (the step list) for setStepSequence
        steps = [bool(x) for x in p["steps"]]
        cparams = {"channel": int(p["index"]), "pattern": steps}
        if p.get("pattern"):
            cparams["target_pattern"] = int(p["pattern"])
        return "channels.setStepSequence", cparams
    if action == "get_steps":
        # controller reads 'channel' + 'steps' (count) for getStepSequence
        cparams = {"channel": int(p["index"]), "steps": int(p.get("steps", 16))}
        if p.get("pattern"):
            cparams["target_pattern"] = int(p["pattern"])
        return "channels.getStepSequence", cparams
    if action == "get_step_param":
        # v10.2 (P4): one step parameter via getStepParameterByIndex.
        # param passes through raw: str = midi constant name (resolved by
        # the controller, which self-teaches on unknown names), int = a raw
        # param-type id (probes the built-in's accepted range).
        # v10.4e (S2.3): use_global is the symmetric flag (default True on
        # both SET and GET; the old GET=False/SET=True asymmetry was the
        # prime suspect for per-channel shift/pan drops).
        cparams = {"channel": int(p["index"]), "step": int(p["step"]),
                   "param": p.get("param", "pVelocity")}
        if p.get("pattern"):
            cparams["target_pattern"] = int(p["pattern"])
        if p.get("use_global") is not None:
            cparams["use_global"] = bool(p["use_global"])
        return "channels.getStepParameter", cparams
    if action == "set_step_param":
        # v10.4e: the response carries read_back + persisted (same-trip,
        # same-flag read-back — P5: a silent drop is reported, not success).
        cparams = {"channel": int(p["index"]), "step": int(p["step"]),
                   "param": p.get("param", "pVelocity"),
                   "value": int(p["value"])}
        if p.get("pattern"):
            cparams["target_pattern"] = int(p["pattern"])
        if p.get("use_global") is not None:
            cparams["use_global"] = bool(p["use_global"])
        return "channels.setStepParameter", cparams
    raise ValueError(f"unhandled action {action!r}")


def fl_channel(action: str, conn=None, **params: Any) -> dict:
    """Control a FL Studio channel (one tool, 12 actions).

    Actions:
      list — every channel: index, name, muted, selected, mixer track
      set_steps (index, steps=[bool] | bars=[[1,7],[1,13],...], [n_bars], [pattern])
          bars (S7): 1-based steps per bar (16/bar) -> the bool row; a list
          shorter than n_bars cycles to fill it (default n_bars = len(bars));
          'steps' and 'bars' together = error.
      set_vol (index, volume 0-1)
      set_pan (index, pan -1..1)
      rename (index, name)
      route (index, to) — set the channel's target mixer track
      mute (index, muted=True/False)
      solo (index, solo=True/False)
      clone (index, name) — FL's channel menu > Clone (no clone API in v45);
          verified by the channel count; the clone gets `name`
      load_sample (index, path, [name]) — load a WAV into a Sampler channel via
          its own Open panel (editor opened panel-aware, verified; the label
          is restored after FL renames the channel after the file)
      add (plugin, name) — the native Add menu (the ONLY channel-creation path);
          also routes to a free mixer track, renames and selects it. plugin =
          exact Add-menu name, e.g. "3x Osc", "FLEX", "Sytrus", "Fruit Kick".
      get_step_param (index, step, [param], [pattern]) — v10 (P4)
      set_step_param (index, step, value, [param], [pattern]) — v10 (P4)

    Writes carry same-trip state_after + one named undo.
    """
    errs = validate(action, params)
    if errs:
        return {"success": False, "error": "; ".join(errs),
                "valid_actions": list(ACTIONS)}

    if action == "clone":
        # Server-side: the channel button's right-click menu > Clone
        # (utils/clone_channel) — v45 has no clone API ("channels.clone"
        # never existed in the controller). Panel-aware, verified by count.
        import sys
        if sys.platform != "darwin":
            return {"action": action, "success": False,
                    "error": "clone drives FL's channel menu (macOS only)"}
        from fl_studio_mcp.utils.clone_channel import clone_channel
        if conn is None:
            from fl_studio_mcp.utils.connection import get_connection
            conn = get_connection()
        r = clone_channel(conn, int(params["index"]), str(params.get("name") or ""),
                          log=lambda m: None)
        return {"action": action, "success": bool(r.get("ok")),
                **{k: v for k, v in r.items() if k != "ok"}}

    if action == "group":
        # Server-side (utils/channel_group): API select + focus, Alt+G, PASTE the
        # name (Cmd+V reaches FL's text box), Return; proven on screen. Tip 10.
        if conn is None:
            from fl_studio_mcp.utils.connection import get_connection
            conn = get_connection()
        from fl_studio_mcp.utils.channel_group import group as _group
        return _group(conn, [int(i) for i in params["indices"]], str(params["name"]))

    if action == "load_sample":
        # Server-side: the Sampler's own Open panel (utils/sampler_load) —
        # panel-aware editor opening, accessibility-driven panel, verified.
        import sys
        if sys.platform != "darwin":
            return {"action": action, "success": False,
                    "error": "load_sample drives the macOS Open panel (darwin only)"}
        from fl_studio_mcp.utils.sampler_load import load_sample_retry as load_sample
        if conn is None:
            from fl_studio_mcp.utils.connection import get_connection
            conn = get_connection()
        r = load_sample(conn, int(params["index"]), str(params["path"]),
                        label=params.get("name") or "", log=lambda m: None)
        return {"action": action, "success": bool(r.get("ok")),
                **{k: v for k, v in r.items() if k != "ok"}}

    if action == "add":
        # Server-side (System Events clicks Add > <plugin>), not a controller
        # action: v45 has no channel-creation API. Routes/renames/selects too.
        from fl_studio_mcp.utils.add_channel import setup_instrument
        plugin = str(params.get("plugin") or "FL Keys")
        r = setup_instrument(plugin, params.get("name") or plugin)
        out = {"action": action, "success": bool(r.get("ok"))}
        if r.get("ok"):
            out["result"] = {k: r[k] for k in ("index", "name", "instrument",
                                               "mixer_track", "channel_count")}
        else:
            out["error"] = r.get("error")
        return out

    if conn is None:
        from fl_studio_mcp.utils.connection import get_connection
        conn = get_connection()

    ca, cparams = _route(action, params)
    try:
        res = _safe_send(ca, cparams, conn)
    except Exception as e:
        return {"action": action, "success": False, "error": str(e)}

    # S4 part ledger: a set_steps write is a drum part the server wrote, so it
    # is recorded (pid-scoped) and readable via fl_state / used by fl_pattern
    # chain. Look up the channel name once (best-effort; a failure to name the
    # channel must not fail the write).
    if action == "set_steps" and res.get("success"):
        try:
            from fl_studio_mcp.utils import ledger
            name = conn.send_command("channels.getAll").get("channels", [])
            chname = next((c.get("name") for c in name
                           if c.get("index", c.get("number")) == int(params["index"])),
                          None)
            v = res.get("state_after") or {}
            ledger.record_steps(None, int(params.get("pattern") or 0),
                                int(params["index"]), chname,
                                [bool(x) for x in params["steps"]],
                                v if isinstance(v, dict) else None)
        except Exception:  # noqa: BLE001 - ledger is best-effort
            pass

    out = shape_response(action, res)
    # v10.4e (L14): the controller now reads channel volume back as linear
    # 0-1 (the old getChannelVolume(index, True) call passed True as the dB
    # MODE arg; v10.4e passes (index, False, True)). The L4 volume_db
    # relabel is retired with it — the read-back matches the 0-1 input.
    return out


def register_channel_tools_v2(mcp: FastMCP) -> None:
    """Register the B4 fl_channel tool."""
    from fl_studio_mcp.tools.channel_v2 import fl_channel as _impl

    @mcp.tool()
    def fl_channel(
        action: str,
        index: int | None = None,
        volume: float | None = None,
        pan: float | None = None,
        name: str | None = None,
        to: int | None = None,
        muted: bool | None = None,
        solo: bool | None = None,
        plugin: str | None = None,
        steps: list | int | None = None,
        bars: list | None = None,
        n_bars: int | None = None,
        pattern: int | None = None,
        step: int | None = None,
        param: str | int | None = None,
        value: int | None = None,
        use_global: bool | None = None,
        path: str | None = None,
        indices: list[int] | None = None,
    ) -> dict:
        """Control a FL Studio channel (one tool, 15 actions).

        Actions: list | set_vol | set_pan | rename | route | mute | solo | clone |
        add | set_steps | get_steps | get_step_param | set_step_param |
        load_sample(index, path) — a WAV into a Sampler (its own Open panel).
        group(indices=[..], name) — a Channel rack filter GROUP (Alt+G + pasted name,
        proven on screen; no API exists).
        add = the native Add menu (the ONLY channel-creation path).
        clone(index, name) = FL's channel menu > Clone, count-verified.
        set_steps(index, steps=[bool] | bars=[[1,7],[1,13],..] (1-based steps per
        bar, shorter than n_bars cycles; not both), [n_bars], [pattern]) /
        get_steps(index,
        [steps=16], [pattern]) = the step sequencer (drums).
        get_step_param/set_step_param(index, step, [value], [param=
        "pVelocity"], [pattern]) = per-step parameters (v10/P4; on an
        unknown param name the error lists the real midi constants).
        Writes carry same-trip state_after + one named undo.
        """
        p = {k: v for k, v in {"index": index, "volume": volume, "pan": pan,
             "name": name, "to": to, "muted": muted, "solo": solo,
             "plugin": plugin, "steps": steps, "bars": bars,
             "n_bars": n_bars, "pattern": pattern,
             "step": step, "param": param, "value": value,
             "use_global": use_global, "path": path, "indices": indices}.items()
             if v is not None}
        return _impl(action, **p)

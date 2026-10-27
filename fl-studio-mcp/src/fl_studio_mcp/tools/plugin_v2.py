"""B7: fl_plugin — one tool for plugin (FX) control.

Actions: list_params | set_param | load_preset | echo | reverb | chorus | get_fx.

- set_param's `param` may be an int knob number OR a NAME (case/space-insensitive
    exact match against list_params; "Not Used"/empty/ambiguous names refuse
    with the candidate list)
- echo / reverb / chorus (index, [slot_index], fields...) — named per-channel FX
    knobs (FLEX: "Delay*", "Reverb*", "Chorus"); only given fields change; each
    field reports before/after value_string (after = a SEPARATE read, since FL
    applies a set after the trip returns)
- get_fx (index, [slot_index]) — current echo/reverb/chorus settings

- list_params (index, [slot_index]) — the plugin's params (name/value/range)
- set_param (index, param, value, [slot_index]) — writes, same-trip state_after + undo
- load_preset (index, preset, [slot_index]) — **UNVERIFIED**: the v45 API has
    no importable preset-load (only getPresetCount/nextPreset/prevPreset were
    probed). Registered with a clear status until a load-by-name path is
    verified (likely the native preset menu, like the Add-menu gap).

FLEX-family plugins are the primary target (per plan: document per-type
capability in fl_help; 808-type params are often invisible to the param API).
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from fl_studio_mcp.tools.transport_v2 import _safe_send, shape_response

ACTIONS = ("list_params", "set_param", "load_preset",
           "echo", "reverb", "chorus", "get_fx",
           "dial", "find_preset",     # plugin_dial.py (2026-10-05)
           "preset_ui",               # utils/plugin_preset_ui.py: the editor's preset menu
           "snapshot", "restore")     # full knob state as a named preset (API only)

_PARAM_SPEC = {
    "list_params": (("index", "int", 0, None), ("slot_index", "int", -1, None)),
    "set_param": (("index", "int", 0, None), ("param", "int", 0, None),
                  ("value", "float", None, None),
                  ("slot_index", "int", -1, None)),
    "load_preset": (("index", "int", 0, None), ("preset", "int", 0, None),
                    ("slot_index", "int", -1, None)),
    "echo": (("index", "int", 0, None), ("slot_index", "int", -1, None)),
    "reverb": (("index", "int", 0, None), ("slot_index", "int", -1, None)),
    "chorus": (("index", "int", 0, None), ("slot_index", "int", -1, None)),
    "get_fx": (("index", "int", 0, None), ("slot_index", "int", -1, None)),
    "dial": (("index", "int", 0, None), ("slot_index", "int", -1, None)),
    "find_preset": (("index", "int", 0, None), ("slot_index", "int", -1, None)),
    "preset_ui": (("index", "int", 0, None), ("slot_index", "int", 0, None)),
    "snapshot": (("index", "int", 0, None), ("slot_index", "int", 0, None)),
    "restore": (("index", "int", 0, None), ("slot_index", "int", 0, None)),
}

# fx action -> {field: (exact knob names tried first, keyword fallback)}.
# FLEX has the exact names; an effect in a mixer slot (Fruity Delay 3, ...)
# is matched by keyword and refused when ambiguous.
_FX_FIELDS: dict[str, dict[str, tuple[tuple[str, ...], tuple[str, ...]]]] = {
    "echo": {"on": (("Delay",), ()),
             "mix": (("Delay mix",), ("wet", "mix")),
             "feedback": (("Delay feedback",), ("feedback", "fdbk")),
             "time": (("Delay time",), ("time",))},
    "reverb": {"on": (("Reverb",), ()),
               "mix": (("Reverb mix",), ("wet", "mix")),
               "decay": (("Reverb decay",), ("decay",)),
               "size": (("Reverb size",), ("size", "room"))},
    "chorus": {"amount": (("Chorus",), ("chorus",))},
}
_FX_OPTIONAL = {"on", "mix", "feedback", "time", "decay", "size", "amount"}

_OPTIONAL = {(a, "slot_index") for a in ACTIONS}


def _validate(action: str, params: dict[str, Any]) -> list[str]:
    if action not in ACTIONS:
        return [f"unknown action {action!r}. Valid: {', '.join(ACTIONS)}"]
    errs = []
    if action == "set_param" and isinstance(params.get("param"), str):
        if not params["param"].strip():
            errs.append("set_param.param: empty name")
        params = dict(params, param=0)      # name checked; the int rule is moot
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
            elif lo is not None and v < lo:
                errs.append(f"{action}.{name}: {v} < {lo}")
        elif kind == "float":
            try:
                float(v)
            except (TypeError, ValueError):
                errs.append(f"{action}.{name}: not a number ({v!r})")
    if action == "dial":
        if params.get("param") is None or params.get("target") is None:
            errs.append("dial: param (knob name/number) and target (e.g. '4:1', "
                        "'10 ms', '-20 dB', '1.2 kHz') required")
    if action in ("snapshot", "restore") and not (isinstance(params.get("query"), str)
                                                  and params["query"].strip()):
        errs.append(f"{action}: query (the snapshot name, e.g. 'a' or 'MCP Vocal Body') required")
    if action == "preset_ui" and not (isinstance(params.get("query"), str) and params["query"].strip()):
        errs.append("preset_ui: query (the EXACT preset menu item, e.g. 'De-esser narrow-band') required")
    if action == "find_preset":
        if not (isinstance(params.get("query"), str) and params["query"].strip()):
            errs.append("find_preset: query (part of the preset name) required")
    if action in _FX_FIELDS:
        allowed = _FX_FIELDS[action]
        given = [k for k in params if k in _FX_OPTIONAL]
        bad = [k for k in given if k not in allowed]
        if bad:
            errs.append(f"{action}: unknown field(s) {bad}; valid: {sorted(allowed)}")
        if not given:
            errs.append(f"{action}: give at least one of {sorted(allowed)}")
        for k in given:
            if k not in allowed:
                continue
            v = params[k]
            if k == "on":
                if isinstance(v, bool) or v in (0, 1):
                    continue
                errs.append(f"{action}.on: true/false (or 1/0), got {v!r}")
                continue
            try:
                if not 0.0 <= float(v) <= 1.0:
                    errs.append(f"{action}.{k}: 0-1 normalized, got {v}")
            except (TypeError, ValueError):
                errs.append(f"{action}.{k}: not a number ({v!r})")
    return errs


def _route(action: str, p: dict[str, Any]) -> tuple[str, dict]:
    slot = int(p.get("slot_index", -1))
    if action == "list_params":
        return "plugins.getParams", {"index": int(p["index"]),
                                     "slot_index": slot}
    if action == "set_param":
        # the controller's handler reads plugin_index / param_index — sending
        # index/param made every set silently target channel 0, param 0
        # (2026-10-01 live: "Plugin not valid" on the 808 Kick sampler).
        return "plugins.setParamValue", {"plugin_index": int(p["index"]),
                                        "param_index": int(p["param"]),
                                        "value": float(p["value"]),
                                        "slot_index": slot}
    if action == "load_preset":
        # no verified importable preset-load; native-menu method
        return "plugins.loadPreset", {"index": int(p["index"]),
                                     "preset": int(p["preset"]),
                                     "slot_index": slot}
    raise ValueError(f"unhandled action {action!r}")


# ---------------------------------------------------------------------------
# Named knobs (resolved against list_params at call time)
# ---------------------------------------------------------------------------

_UNUSED = "notused"


def _norm(name: Any) -> str:
    return "".join(str(name or "").split()).lower()


def _list_params(conn, index: int, slot: int) -> list[dict]:
    """The plugin's params (max_params raised: the controller default is 50)."""
    res = _safe_send("plugins.getParams", {"index": int(index), "slot_index": int(slot),
                                          "max_params": 512}, conn)
    if not res.get("success"):
        raise RuntimeError(res.get("error") or "plugins.getParams failed")
    return list(res.get("params") or [])


def _candidates(plist: list[dict], needle: str = "") -> list[str]:
    n = _norm(needle)
    names = [f"{p['index']}:{p.get('name')}" for p in plist
             if _norm(p.get("name")) and _norm(p.get("name")) != _UNUSED]
    near = [x for x in names if n and n in _norm(x.split(":", 1)[1])]
    return (near or names)[:20]


def resolve_param(plist: list[dict], name: str) -> dict:
    """Exact case/space-insensitive name match -> the param dict. Raises
    ValueError (with candidates) on 0 / >1 matches or an unused/empty name."""
    n = _norm(name)
    if not n or n == _UNUSED:
        raise ValueError(f"param name {name!r} is empty/'Not Used': refuse. "
                         f"Candidates: {_candidates(plist)}")
    hits = [p for p in plist if _norm(p.get("name")) == n]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"no param named {name!r}. Candidates: {_candidates(plist, name)}")
    raise ValueError(f"param name {name!r} is ambiguous ({len(hits)} matches): "
                     f"{[p['index'] for p in hits]}. Use the knob number")


# words that mark a knob as belonging to another effect family (a keyword
# fallback for echo "mix" must never grab "Reverb mix")
_FAMILY_WORDS = {"echo": ("delay", "echo"), "reverb": ("reverb",), "chorus": ("chorus",)}


def _resolve_fx_field(plist: list[dict], exact: tuple[str, ...],
                      keywords: tuple[str, ...], label: str) -> dict:
    fx = label.split(".", 1)[0]
    foreign = tuple(w for f, ws in _FAMILY_WORDS.items() if f != fx for w in ws)
    for nm in exact:
        hits = [p for p in plist if _norm(p.get("name")) == _norm(nm)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise ValueError(f"{label}: knob {nm!r} is ambiguous "
                             f"({[p['index'] for p in hits]})")
    if keywords:
        hits = [p for p in plist
                if _norm(p.get("name")) not in ("", _UNUSED)
                and not any(w in _norm(p.get("name")) for w in foreign)
                and any(k in _norm(p.get("name")) for k in keywords)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise ValueError(f"{label}: ambiguous, {len(hits)} knobs match "
                             f"{list(keywords)}: {[p['index'] for p in hits]}. "
                             f"Use fl_plugin set_param with the knob number")
    raise ValueError(f"{label}: no knob found (tried {list(exact)}"
                     f"{' / keywords ' + str(list(keywords)) if keywords else ''}). "
                     f"Candidates: {_candidates(plist)}")


def _set_value(conn, index: int, slot: int, pidx: int, value: float) -> dict:
    ca, cp = _route("set_param", {"index": index, "param": pidx, "value": value,
                                  "slot_index": slot})
    return _safe_send(ca, cp, conn)


def _by_index(plist: list[dict]) -> dict[int, dict]:
    return {int(p["index"]): p for p in plist}


def _fx_set(conn, action: str, p: dict) -> dict:
    index, slot = int(p["index"]), int(p.get("slot_index", -1))
    plist = _list_params(conn, index, slot)
    fields = {k: v for k, v in p.items() if k in _FX_FIELDS[action]}
    try:      # resolve EVERYTHING before the first write (all-or-nothing)
        resolved = {k: _resolve_fx_field(plist, *_FX_FIELDS[action][k],
                                         f"{action}.{k}") for k in fields}
    except ValueError as e:
        return {"action": action, "success": False, "error": str(e)}
    before = _by_index(plist)
    out_fields: dict[str, dict] = {}
    for k, v in fields.items():
        val = (1.0 if v else 0.0) if k == "on" else float(v)
        par = resolved[k]
        res = _set_value(conn, index, slot, int(par["index"]), val)
        out_fields[k] = {"param": int(par["index"]), "name": par.get("name"),
                         "set": val,
                         "before": before[int(par["index"])].get("value_string"),
                         "ok": bool(res.get("success"))}
        if not res.get("success"):
            out_fields[k]["error"] = res.get("error")
    # read back in a SEPARATE command (FL applies a set after the trip)
    after = _by_index(_list_params(conn, index, slot))
    for k, f in out_fields.items():
        a = after.get(f["param"], {})
        f["after"] = a.get("value_string")
        f["value"] = a.get("value")
    return {"action": action, "success": all(f["ok"] for f in out_fields.values()),
            "index": index, "fields": out_fields}


def _fx_get(conn, p: dict) -> dict:
    index, slot = int(p["index"]), int(p.get("slot_index", -1))
    plist = _list_params(conn, index, slot)
    result: dict[str, dict] = {}
    for fx, fields in _FX_FIELDS.items():
        got = {}
        for k, (exact, kws) in fields.items():
            try:
                par = _resolve_fx_field(plist, exact, kws, f"{fx}.{k}")
            except ValueError:
                continue                       # only the knobs that exist
            got[k] = par.get("value_string")
        if got:
            result[fx] = got
    return {"action": "get_fx", "success": True, "index": index, "result": result}


def _set_param_named(conn, p: dict) -> dict:
    index, slot = int(p["index"]), int(p.get("slot_index", -1))
    plist = _list_params(conn, index, slot)
    try:
        par = resolve_param(plist, p["param"])
    except ValueError as e:
        return {"action": "set_param", "success": False, "error": str(e)}
    res = _set_value(conn, index, slot, int(par["index"]), float(p["value"]))
    out = shape_response("set_param", res)
    out["resolved_index"] = int(par["index"])
    out["name"] = par.get("name")
    out["before"] = par.get("value_string")
    if out["success"]:
        a = _by_index(_list_params(conn, index, slot)).get(int(par["index"]), {})
        out["value_string"] = a.get("value_string")
        out["value"] = a.get("value")
    return out


def fl_plugin(action: str, conn=None, **params: Any) -> dict:
    """Control a FL Studio plugin (one tool, 3 actions).

    Actions:
      list_params (index, [slot_index]) — the plugin's params
      set_param (index, param, value, [slot_index]) — a write (state_after + undo);
          param = knob number OR name (exact, case/space-insensitive)
      echo (index, [slot_index], on?, mix?, feedback?, time?) — delay knobs by name
      reverb (index, [slot_index], on?, mix?, decay?, size?)
      chorus (index, [slot_index], amount?)
      get_fx (index, [slot_index]) — current echo/reverb/chorus value strings
      load_preset (index, preset, [slot_index]) — NOT YET VERIFIED (no importable
          preset-load in v45; native-menu method)

    FLEX-family plugins are the primary target; 808-type params are often
    invisible to the param API (documented in fl_help).
    """
    errs = _validate(action, params)
    if errs:
        return {"success": False, "error": "; ".join(errs),
                "valid_actions": list(ACTIONS)}

    if action == "load_preset":
        return {"success": False, "status": "not_verified_yet",
                "error": "load_preset: the v45 API has no importable preset-load "
                         "(only getPresetCount/nextPreset/prevPreset were probed). "
                         "This is the native preset-menu method; it is not wired "
                         "until a load-by-name path is verified."}

    if conn is None:
        from fl_studio_mcp.utils.connection import get_connection
        conn = get_connection()

    try:
        if action in ("snapshot", "restore"):
            from fl_studio_mcp.tools.mixer_v2 import _exec as _mx
            from fl_studio_mcp.utils import plugin_preset_ui as pu
            i, sl = int(params["index"]), int(params["slot_index"])
            plug = _mx(conn, f"import plugins\nprint('T=' + plugins.getPluginName({i}, {sl}))")[2:]
            if action == "snapshot":
                return {"action": action, "success": True,
                        **pu.record_fingerprint(conn, i, sl, plug, params["query"])}
            return pu.restore_fingerprint(conn, i, sl, plug, params["query"])
        if action == "preset_ui":
            from fl_studio_mcp.utils.plugin_preset_ui import pick_preset_ui
            return pick_preset_ui(conn, int(params["index"]), int(params["slot_index"]),
                                  params["query"])
        if action in ("dial", "find_preset"):
            from fl_studio_mcp.tools import plugin_dial as _pd
            idx, slot = int(params["index"]), int(params.get("slot_index", -1))
            if action == "dial":
                return _pd.dial(conn, idx, slot, params["param"], params["target"],
                                params.get("tol"))
            return _pd.find_preset(conn, idx, slot, params["query"],
                                   keep=params.get("keep", True))
        if action in _FX_FIELDS:
            return _fx_set(conn, action, params)
        if action == "get_fx":
            return _fx_get(conn, params)
        if action == "set_param" and isinstance(params.get("param"), str):
            return _set_param_named(conn, params)
    except Exception as e:
        return {"action": action, "success": False, "error": str(e)}

    ca, cparams = _route(action, params)
    try:
        res = _safe_send(ca, cparams, conn)
    except Exception as e:
        return {"action": action, "success": False, "error": str(e)}

    return shape_response(action, res)


def register_plugin_tools_v2(mcp: FastMCP) -> None:
    """Register the B7 fl_plugin tool."""
    from fl_studio_mcp.tools.plugin_v2 import fl_plugin as _impl

    @mcp.tool()
    def fl_plugin(
        action: str,
        index: int | None = None,
        param: int | str | None = None,
        value: float | None = None,
        slot_index: int | None = None,
        preset: int | None = None,
        on: bool | None = None,
        mix: float | None = None,
        feedback: float | None = None,
        time: float | None = None,
        decay: float | None = None,
        size: float | None = None,
        amount: float | None = None,
        target: str | float | None = None,
        tol: float | None = None,
        query: str | None = None,
        keep: bool | None = None,
    ) -> dict:
        """Control a FL Studio plugin (one tool, 9 actions).

        Actions: list_params | set_param (param = knob number or NAME) |
        load_preset | echo(on,mix,feedback,time) | reverb(on,mix,decay,size) |
        chorus(amount) | get_fx. Echo/reverb/chorus values are 0-1 normalized,
        on = true/false; only the given fields change; before/after
        value_string per field. FLEX-family primary target; load_preset not
        yet verified.
        dial(index, param, target, [slot_index], [tol]) — set a knob in REAL
        units ("4:1", "10 ms", "-20 dB", "1.2 kHz") by searching FL's own display
        string; read back. find_preset(index, query, [slot_index], [keep=true])
        — step presets until the name contains query (mixer slots: unverified).
        preset_ui(index, slot_index, query) — pick from the editor's own preset
        MENU by exact item name (UI + OCR, ~3 s, FL brought to front, verified by
        the header). Use for Maximus/Patcher and anything without API names.
        snapshot(index, slot_index, query=name) — save the plugin's FULL knob state as a
        named preset; restore(index, slot_index, query=name) — apply it in ONE API call,
        proven by read-back (no menu/OCR; not for Patcher patches).
        """
        p = {k: v for k, v in {"target": target, "tol": tol, "query": query,
             "keep": keep, "index": index, "param": param, "value": value,
             "slot_index": slot_index, "preset": preset, "on": on, "mix": mix,
             "feedback": feedback, "time": time, "decay": decay, "size": size,
             "amount": amount}.items() if v is not None}
        return _impl(action, **p)

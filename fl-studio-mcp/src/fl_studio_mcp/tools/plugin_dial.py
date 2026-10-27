"""fl_plugin dial / find_preset — set knobs in REAL units, pick presets by name.

dial(index, param, target, [slot_index]) — "set the ratio to 4:1", "attack 10 ms",
"threshold -20 dB", "freq 1.2 kHz". FL's param API is 0-1 normalized and every
plugin maps it differently (log, stepped, inverted). Instead of hard-coding curves
we SEARCH: set a normalized value, read FL's own display string, parse the number,
and bisect toward the target. Plugin-agnostic; the display string is the oracle.

  1. one in-engine trip: scan a 33-point grid (set + read) and restore the start
     value. If every string comes back identical, strings are not refreshed inside
     a trip -> fall back to one trip per probe (slower, same algorithm).
  2. pick the grid bracket that contains the target, bisect inside it.
  3. final set in its own trip, read back in a SEPARATE trip (P5: never trust
     a success message).

find_preset(index, query, [slot_index]) — step nextPreset on the plugin
(channel or MIXER SLOT), read plugins.getName(..., FPN_Preset) after each step,
stop at the first substring match. Mixer-slot preset names: NOT live-verified.

Both built 2026-10-05, offline-tested only.
"""
from __future__ import annotations

import json
import math
import re
import time
from typing import Any, Callable

from fl_studio_mcp.tools.mixer_v2 import _exec

_NUM = re.compile(r"[-+−]?\s*(?:\d+(?:\.\d*)?|\.\d+)")
GRID = 33
BISECT = 14


def parse_display(s: Any) -> float | None:
    """'4.0:1' -> 4.0 · '-20.0 dB' -> -20 · '1.2 kHz' -> 1200 · '-inf dB' -> -inf ·
    '12 ms' -> 12 · 'Off'/'' -> None. A bare number passes through."""
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        return float(s)
    if not isinstance(s, str):
        return None
    t = s.strip().lower().replace("−", "-")
    if "inf" in t:
        return -math.inf if "-" in t else math.inf
    m = _NUM.search(t)
    if not m:
        return None
    v = float(m.group(0).replace(" ", ""))
    tail = t[m.end():].strip()
    if tail.startswith("khz") or (tail.startswith("k") and not tail.startswith("knee")):
        v *= 1e3
    return v


def _target_units(target: Any, sample: str | None) -> float:
    """A target in the same unit system as the display. '1.5 s' against a display
    in ms is converted; otherwise the parsed number is used as-is."""
    v = parse_display(target)
    if v is None:
        raise ValueError(f"target {target!r} has no number")
    if isinstance(target, str) and isinstance(sample, str):
        tt, ss = target.lower(), sample.lower()
        if re.search(r"\d\s*s\b", tt) and "ms" in ss:
            v *= 1e3
        if "ms" in tt and re.search(r"\d\s*s\b", ss):
            v /= 1e3
    return v


def _scan_code(index: int, slot: int, pidx: int, values: list[float]) -> str:
    return (
        "import json, plugins, midi\n"
        f"i, s, p = {index}, {slot}, {pidx}\n"
        "g = True\n"
        "start = plugins.getParamValue(p, i, s, g)\n"
        "out = []\n"
        f"for v in {values}:\n"
        "    plugins.setParamValue(v, p, i, s, midi.PIM_None, g)\n"
        "    out.append([v, plugins.getParamValueString(p, i, s, g)])\n"
        "plugins.setParamValue(start, p, i, s, midi.PIM_None, g)\n"
        "print(json.dumps(out))")


def _set_code(index: int, slot: int, pidx: int, v: float) -> str:
    return ("import plugins, midi\n"
            f"plugins.setParamValue({v}, {pidx}, {index}, {slot}, midi.PIM_None, True)\n"
            "print('ok')")


def _read_code(index: int, slot: int, pidx: int) -> str:
    return ("import json, plugins\n"
            f"print(json.dumps([plugins.getParamValue({pidx}, {index}, {slot}, True), "
            f"plugins.getParamValueString({pidx}, {index}, {slot}, True), "
            f"plugins.getParamName({pidx}, {index}, {slot}, True)]))")


def _norm_txt(t: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(t).lower())


def _dial_choice(conn, index: int, slot: int, pidx: int, name: str, s0: str,
                 target: str, sleep: Callable) -> dict:
    """Stepped/text knobs ("Delay type" = "Ping pong"): scan 65 points in one trip,
    pick the value whose display text matches, set it, read back."""
    grid = [k / 64 for k in range(65)]
    rows = json.loads(_exec(conn, _scan_code(index, slot, pidx, grid)))
    if len({st for _, st in rows}) <= 1:
        # display text not refreshed inside one trip (live 2026-10-05: Delay 3
        # "Delay type" read 'Fake Stereo' at all 65 points): one trip per probe
        v0 = json.loads(_exec(conn, _read_code(index, slot, pidx)))[0]
        rows = []
        for v in [k / 32 for k in range(33)]:
            _exec(conn, _set_code(index, slot, pidx, v))
            sleep(0.05)
            rows.append([v, json.loads(_exec(conn, _read_code(index, slot, pidx)))[1]])
        _exec(conn, _set_code(index, slot, pidx, v0))
    want = _norm_txt(target)
    hits = [v for v, st in rows if _norm_txt(st) == want] or \
           [v for v, st in rows if want and want in _norm_txt(st)]
    choices = sorted({st for _, st in rows})
    if not hits:
        return {"action": "dial", "success": False, "param": name, "index": pidx,
                "error": f"no setting shows {target!r}", "choices": choices[:40]}
    v = hits[len(hits) // 2]                     # middle of the matching range
    _exec(conn, _set_code(index, slot, pidx, v))
    sleep(0.15)
    v1, s1, _ = json.loads(_exec(conn, _read_code(index, slot, pidx)))
    ok = _norm_txt(s1) == want or want in _norm_txt(s1)
    return {"action": "dial", "success": ok, "param": name, "index": pidx, "mode": "choice",
            "target": target, "before": s0, "after": s1, "value": v1,
            **({} if ok else {"error": f"read back {s1!r}", "choices": choices[:40]})}


def dial(conn, index: int, slot: int, param: int | str, target: Any,
         tol: float | None = None, sleep: Callable = time.sleep) -> dict:
    from fl_studio_mcp.tools.plugin_v2 import _list_params, resolve_param
    if isinstance(param, str):
        par = resolve_param(_list_params(conn, index, slot), param)
        pidx = int(par["index"])
    else:
        pidx = int(param)
    v0, s0, name = json.loads(_exec(conn, _read_code(index, slot, pidx)))
    if isinstance(target, str) and parse_display(target) is None:
        return _dial_choice(conn, index, slot, pidx, name, s0, target, sleep)
    want = _target_units(target, s0)

    def probe_many(values: list[float]) -> list[tuple[float, float | None, str]]:
        rows = json.loads(_exec(conn, _scan_code(index, slot, pidx, values)))
        return [(v, parse_display(st), st) for v, st in rows]

    grid = [k / (GRID - 1) for k in range(GRID)]
    rows = probe_many(grid)
    mode = "in_trip"
    if len({st for _, _, st in rows}) <= 1:        # strings not refreshed inside a trip
        mode = "per_trip"

        def probe_many(values):                    # noqa: F811 - slower fallback
            out = []
            for v in values:
                _exec(conn, _set_code(index, slot, pidx, v))
                sleep(0.05)
                _, st, _ = json.loads(_exec(conn, _read_code(index, slot, pidx)))
                out.append((v, parse_display(st), st))
            _exec(conn, _set_code(index, slot, pidx, v0))
            return out
        rows = probe_many(grid[::4])               # 9 points, not 33

    pts = [(v, x) for v, x, _ in rows if x is not None and math.isfinite(x)]
    if len(pts) < 2:
        return {"action": "dial", "success": False, "param": name, "index": pidx,
                "error": "display strings carry no usable numbers",
                "samples": [st for _, _, st in rows][:8]}
    lo_x, hi_x = min(x for _, x in pts), max(x for _, x in pts)
    if not lo_x <= want <= hi_x:
        return {"action": "dial", "success": False, "param": name, "index": pidx,
                "error": f"target {want} outside the knob's range [{lo_x}, {hi_x}]",
                "range": [lo_x, hi_x]}
    # bracket: adjacent grid points whose displayed values straddle the target
    best = min(pts, key=lambda p: abs(p[1] - want))
    a = b = best
    for (va, xa), (vb, xb) in zip(pts, pts[1:]):
        if (xa - want) * (xb - want) <= 0:
            a, b = (va, xa), (vb, xb)
            break
    for _ in range(BISECT if a != b else 0):
        mid = (a[0] + b[0]) / 2
        (_, xm, _), = probe_many([mid])
        if xm is None:
            break
        if abs(xm - want) < abs(best[1] - want):
            best = (mid, xm)
        if (a[1] - want) * (xm - want) <= 0:
            b = (mid, xm)
        else:
            a = (mid, xm)
    _exec(conn, _set_code(index, slot, pidx, best[0]))
    sleep(0.15)
    v1, s1, _ = json.loads(_exec(conn, _read_code(index, slot, pidx)))
    got = parse_display(s1)
    span = max(abs(hi_x - lo_x), 1e-9)
    tol = tol if tol is not None else max(0.02 * abs(want), 0.005 * span)
    ok = got is not None and abs(got - want) <= tol
    return {"action": "dial", "success": ok, "param": name, "index": pidx,
            "target": target, "target_value": want, "mode": mode,
            "before": s0, "after": s1, "value": v1, "tolerance": tol,
            **({} if ok else {"error": f"closest reachable display {s1!r} "
                                       f"(stepped knob or non-monotonic map)"})}


#: plugins whose presets are whole PATCHES (other plugins inside): one step =
#: a heavy, ASYNC load on FL's main thread. Live 2026-10-05: 176 next + 176 prev
#: on Patcher queued ~350 patch loads; the main thread sat 100% in
#: Patcher_x64.dylib for minutes, memory 0.56 -> 1.6 GB, every MCP call timed out.
HEAVY_PRESETS = ("patcher",)


def preset_matches(name: str, query: str) -> bool:
    """Exact name, or the query as a whole word/prefix — never a bare substring for
    short queries (live 2026-10-05: query "A" matched "Default")."""
    n, q = str(name).strip().lower(), query.strip().lower()
    if not q:
        return False
    if n == q:
        return True
    if len(q) <= 2:
        return False
    return n.startswith(q) or (" " + q) in (" " + n) or q in n
STEP_SETTLE = 3.0      # max seconds to wait for ONE preset step to show up
BUDGET = 45.0          # max seconds for the whole search
RESTORE_MAX = 25       # walk back at most this many steps (each one is a real load)


def find_preset(conn, index: int, slot: int, query: str, max_steps: int = 60,
                keep: bool = True, force: bool = False, sleep: Callable = time.sleep,
                clock: Callable = time.monotonic) -> dict:
    """Step presets until the name contains `query` — PACED: every step waits until
    FL reports the new preset name before the next one, so no load queue builds up.
    Stops at the first step FL has not applied within STEP_SETTLE (backlog / no
    names), at max_steps, or at BUDGET seconds."""
    rd = ("import json, plugins, midi\n"
          f"print(json.dumps([plugins.getPresetCount({index}, {slot}, True), "
          f"plugins.getName({index}, {slot}, midi.FPN_Preset, 0, True), "
          f"plugins.getPluginName({index}, {slot})]))")
    nxt = f"import plugins\nplugins.nextPreset({index}, {slot}, True)\nprint('ok')"
    prv = f"import plugins\nplugins.prevPreset({index}, {slot}, True)\nprint('ok')"
    count, name, plugin = json.loads(_exec(conn, rd))
    base = {"action": "find_preset", "query": query, "plugin": plugin, "preset_count": count}
    if not force and any(h in str(plugin).lower() for h in HEAVY_PRESETS):
        return {**base, "success": False, "current": name,
                "error": (f"{plugin} presets are whole patches (heavy async loads): stepping "
                          "them is refused — pick it from the plugin's own preset menu "
                          "(UI) or pass force=true for a short list")}
    t0 = clock()

    def step(code: str, prev_name: str) -> str | None:
        _exec(conn, code)
        waited = 0.0
        while waited < STEP_SETTLE:
            sleep(0.1)
            waited += 0.1
            _, nm, _ = json.loads(_exec(conn, rd))
            if nm != prev_name:
                return nm
        return None                     # FL did not apply it in time: stop here

    names, q, steps, found, why = [name], query.strip().lower(), 0, None, None
    if preset_matches(name, q):
        found = 0
    limit = min(max_steps, int(count or 0))
    while found is None and steps < limit - 1:
        if clock() - t0 > BUDGET:
            why = f"time budget {BUDGET:.0f}s used"
            break
        nm = step(nxt, names[-1])
        if nm is None:
            why = "preset name did not change within %.0fs (no names, or FL busy)" % STEP_SETTLE
            break
        steps += 1
        names.append(nm)
        if preset_matches(nm, q):
            found = steps
    restored = None
    if (found is None or not keep) and steps:
        if steps <= RESTORE_MAX:
            back = 0
            for _ in range(steps):
                if step(prv, names[-1 - back]) is None:
                    break
                back += 1
            restored = back == steps
        else:
            restored = False
    out = {**base, "success": found is not None, "steps_scanned": steps,
           "names": names[:60]}
    if found is not None:
        out.update(match=names[found], selected=keep)
    if restored is not None:
        out["restored_start_preset"] = restored
        if not restored:
            out["current"] = names[-1]
    if found is None:
        out["error"] = why or f"no preset containing {query!r} in {steps + 1} presets"
    return out

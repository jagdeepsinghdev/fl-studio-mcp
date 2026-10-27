"""fl_vocal — vocal chains, vocal/reverb/delay buses and loudness, from JSON recipes.

Knowledge: skills/fl-mixing/references/vocal-chain.md, vocal-bus-routing.md,
mastering-stock.md. Recipes: fl-studio-mcp/presets/vocal/*.json (data, no code:
edit a recipe and call again — the improvement loop).

Actions
  recipes                       list recipe files
  show(recipe)                  the recipe JSON
  status(track)                 loaded slots + every named knob's display value
  learn(track, slot)            save the slot plugin's REAL knob names to
                                presets/vocal/knobs/<plugin>.json (fix recipes from it)
  apply(recipe, track, [steps], [add_missing=false], [dry_run=false])
                                for each chain step: find the plugin on the track (nth
                                occurrence in slot order), optionally insert it
                                (fl_mixer add_fx: CLICKS, FL frontmost), optional
                                preset by name, then knobs: `target` (real units, via
                                fl_plugin dial) or `value` (0-1). Never stops at the
                                first miss: returns per-step results + a `misses` list.
  buses(recipe, vocal, vocal_bus, reverb_bus, delay_bus, [fx_tracks], [dry_run])
                                names/colours tracks, vocal -> vocal bus ONLY,
                                fx tracks -> their bus ONLY, buses -> master, sends.
  run(ops, [stop_on_error=true]) ONE call for many steps: ops = [{"tool": "mixer"|
                                "plugin"|"vocal", "action": ..., <params>}, ...] run
                                in order, server-side; compact per-op results. Saves
                                MCP round-trips (owner request 2026-10-05).
  loudness(path, [reference], [target_lufs])
                                integrated LUFS / LRA / true peak via ffmpeg ebur128;
                                compares to the reference and the target.

Status: built 2026-10-05, offline-tested; NOT live-verified. Every write reads back.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

PKG_ROOT = Path(__file__).resolve().parents[3]          # fl-studio-mcp/
RECIPES = PKG_ROOT / "presets" / "vocal"
KNOBS = RECIPES / "knobs"
#: plugins whose presets are picked from the editor's preset menu (see apply()).
UI_PRESET_PLUGINS = {"maximus", "patcher"}
ACTIONS = ("recipes", "show", "status", "learn", "apply", "buses", "loudness", "run",
           "setup", "onboard")


# ------------------------------------------------------------------ recipes

def load_recipe(name: str) -> dict:
    f = RECIPES / (name if name.endswith(".json") else f"{name}.json")
    if not f.is_file():
        raise ValueError(f"no recipe {name!r}; have: {list_recipes()}")
    return json.loads(f.read_text())


def list_recipes() -> list[str]:
    return sorted(p.stem for p in RECIPES.glob("*.json"))


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _plugin_matches(loaded: str, wanted: str) -> bool:
    a, b = _norm(loaded), _norm(wanted)
    return bool(a) and (a == b or a.startswith(b) or b.startswith(a))


def assign_slots(chain: list[dict], slots: list[dict]) -> list[int | None]:
    """Map chain steps to loaded slots: the nth step asking for plugin P gets the
    nth slot holding P, in slot order. None = not on the track."""
    used: set[int] = set()
    out: list[int | None] = []
    for step in chain:
        hit = next((s["slot"] for s in slots if s["slot"] not in used
                    and _plugin_matches(s["plugin"], step["plugin"])), None)
        if hit is not None:
            used.add(hit)
        out.append(hit)
    return out


def resolve_knob(plist: list[dict], names: list[str] | str) -> dict | None:
    """First candidate name that matches exactly (case/space/punct-insensitive)."""
    names = [names] if isinstance(names, str) else list(names)
    by = {}
    for p in plist:
        by.setdefault(_norm(p.get("name")), []).append(p)
    for n in names:
        hits = by.get(_norm(n)) or []
        if len(hits) == 1:
            return hits[0]
    return None


def _named(plist: list[dict]) -> list[str]:
    return [p.get("name") for p in plist
            if _norm(p.get("name")) not in ("", "notused")]


# ------------------------------------------------------------------ FL actions

def _conn(conn):
    if conn is None:
        from fl_studio_mcp.utils.connection import get_connection
        conn = get_connection()
    return conn


def status(conn, track: int, max_knobs: int = 40) -> dict:
    from fl_studio_mcp.tools.mixer_tracks import list_fx
    from fl_studio_mcp.tools.plugin_v2 import _list_params
    slots = list_fx(conn, track)
    for s in slots:
        plist = _list_params(conn, track, s["slot"])
        s["knobs"] = {p["name"]: p.get("value_string") for p in plist
                      if _norm(p.get("name")) not in ("", "notused")}
        if len(s["knobs"]) > max_knobs:
            s["knobs"] = dict(list(s["knobs"].items())[:max_knobs])
            s["knobs_truncated"] = True
    return {"action": "status", "success": True, "track": track, "slots": slots}


def learn(conn, track: int, slot: int) -> dict:
    from fl_studio_mcp.tools.mixer_tracks import list_fx
    from fl_studio_mcp.tools.plugin_v2 import _list_params
    row = next((s for s in list_fx(conn, track) if s["slot"] == slot), None)
    if row is None:
        return {"action": "learn", "success": False, "error": f"slot {slot} on track {track} is empty"}
    plist = _list_params(conn, track, slot)
    knobs = [{"index": p["index"], "name": p.get("name"), "value_string": p.get("value_string")}
             for p in plist if _norm(p.get("name")) not in ("", "notused")]
    KNOBS.mkdir(parents=True, exist_ok=True)
    f = KNOBS / f"{_norm(row['plugin']) or 'unknown'}.json"
    f.write_text(json.dumps({"plugin": row["plugin"], "knobs": knobs}, indent=1) + "\n")
    return {"action": "learn", "success": True, "plugin": row["plugin"], "knobs": len(knobs),
            "file": str(f.relative_to(PKG_ROOT)), "names": [k["name"] for k in knobs][:80]}


def apply(conn, recipe: dict, track: int, steps: list[str] | None = None,
          add_missing: bool = False, dry_run: bool = False) -> dict:
    from fl_studio_mcp.tools import plugin_dial as pd
    from fl_studio_mcp.tools.mixer_tracks import list_fx
    from fl_studio_mcp.tools.plugin_v2 import _by_index, _list_params, _set_value

    chain = recipe.get("chain") or []
    chosen = [s for s in chain if not steps or s.get("step") in steps]
    slots = list_fx(conn, track)
    where = assign_slots(chosen, slots)
    results, misses = [], []

    if dry_run:
        plan = [{"step": s["step"], "plugin": s["plugin"], "slot": w,
                 "action": "configure" if w is not None else
                           ("insert + configure" if add_missing else "MISSING (add_missing=false)"),
                 "preset": s.get("preset"), "knobs": s.get("params", [])}
                for s, w in zip(chosen, where)]
        return {"action": "apply", "success": True, "dry_run": True, "track": track,
                "recipe": recipe.get("name"), "loaded": slots, "plan": plan}

    used_slots: list[int] = []
    for step, slot in zip(chosen, where):
        r: dict[str, Any] = {"step": step["step"], "plugin": step["plugin"]}
        if slot is None and add_missing:
            from fl_studio_mcp.utils.add_effect import add_effect
            ins = add_effect(track, step["plugin"], conn=conn, log=lambda m: None)
            if not ins.get("ok") and not any(k in str(ins.get("error")) for k in
                                             ("FL not ready", "could not select mixer track")):
                # live 2026-10-05: Patcher failed once inside setup, the identical
                # retry picked it by index at once -> one automatic retry. But FIRST
                # re-read the slots: a late-landing insert must not become a duplicate.
                now = list_fx(conn, track)
                late = [x for x in assign_slots(chosen, now) if x is not None]
                had = [x for x in where if x is not None]
                fresh = sorted(set(late) - set(had) - set(used_slots))
                if fresh:
                    ins = {"ok": True, "slot": fresh[0]}
                    r["late_insert"] = True
                else:
                    ins = add_effect(track, step["plugin"], conn=conn, log=lambda m: None)
                    r["retried"] = True
            if ins.get("ok"):
                slot = int(ins["slot"])
                used_slots.append(slot)
                r["inserted"] = True
                try:                       # save real knob names now: no extra learn call
                    r["learned"] = learn(conn, track, slot).get("file")
                except Exception:
                    pass
            else:
                r["error"] = f"add_fx failed: {ins.get('error')}"
        if slot is None:
            r.setdefault("error", "plugin not on the track (pass add_missing=true, or fl_mixer add_fx)")
            misses.append({"step": step["step"], "what": "plugin", "detail": r["error"]})
            results.append(r)
            if any(k in r["error"] for k in ("FL not ready", "could not select mixer track")):
                # one cause, one report (live 2026-10-05: 9 identical failures)
                rest = [s["step"] for s in chosen[len(results):]]
                misses.append({"step": "(stopped)", "what": "blocked",
                               "detail": f"{r['error']} -> skipped {rest}; fix it and re-run"})
                break
            continue
        r["slot"] = slot
        if step.get("preset"):
            # 1) a stored knob SNAPSHOT of this preset -> one API trip, proven by
            #    read-back (2026-10-06: Maximus 'a' in 0.94 s; no menu, no OCR)
            from fl_studio_mcp.utils.plugin_preset_ui import restore_fingerprint
            pname = step["preset"].rpartition("/")[2].strip() or step["preset"]
            snap = restore_fingerprint(conn, track, slot, step["plugin"], pname)
            # 2) Maximus has no FPN_Preset names and Patcher presets are heavy async
            #    patch loads: both go to the editor's preset MENU (UI + OCR).
            ui_first = _norm(step["plugin"]) in UI_PRESET_PLUGINS
            pr = ({"success": True, "match": pname, "via": "snapshot"} if snap.get("success")
                  else {"success": False} if ui_first
                  else pd.find_preset(conn, track, slot, step["preset"]))
            if not pr.get("success"):
                from fl_studio_mcp.utils.plugin_preset_ui import pick_preset_ui
                api_err = pr.get("error")
                pr = pick_preset_ui(conn, track, slot, step["preset"])
                if not pr.get("success") and "FL not" not in str(pr.get("error")):
                    pr = pick_preset_ui(conn, track, slot, step["preset"])   # one retry
                    pr["retried"] = True
                pr["match"] = pr.get("after") if pr.get("success") else None
                pr["via"] = "menu"
                if api_err:
                    pr["api_error"] = api_err
            r["preset"] = {"query": step["preset"], "ok": pr.get("success"),
                           "match": pr.get("match"), "via": pr.get("via", "api"),
                           "error": pr.get("error"), "menu_items": pr.get("menu_items")}
            if not pr.get("success"):
                misses.append({"step": step["step"], "what": "preset", "detail": pr.get("error")})
        plist = _list_params(conn, track, slot)
        knobs = []
        for k in step.get("params", []):
            kr: dict[str, Any] = {"param": k["param"]}
            par = resolve_knob(plist, k["param"])
            if par is None:
                kr["error"] = "no knob with that name"
                kr["candidates"] = _named(plist)[:40]
                misses.append({"step": step["step"], "what": "knob", "detail": k["param"],
                               "candidates": kr["candidates"]})
            elif "target" in k:
                d = pd.dial(conn, track, slot, int(par["index"]), k["target"], k.get("tol"))
                kr.update(name=par["name"], target=k["target"], ok=d.get("success"),
                          before=d.get("before"), after=d.get("after"), error=d.get("error"))
                if not d.get("success"):
                    misses.append({"step": step["step"], "what": "dial", "detail": f"{par['name']}: {d.get('error')}"})
            else:
                pi, want = int(par["index"]), float(k["value"])
                _set_value(conn, track, slot, pi, want)
                a = _by_index(_list_params(conn, track, slot)).get(pi, {})
                if abs(float(a.get("value", -1)) - want) > 0.02:
                    # live 2026-10-05: a Limiter knee write reported success but read
                    # back unchanged. Retry once via the in-engine path dial uses.
                    pd._exec(conn, pd._set_code(track, slot, pi, want))
                    a = _by_index(_list_params(conn, track, slot)).get(pi, {})
                ok = abs(float(a.get("value", -1)) - want) <= 0.02
                kr.update(name=par["name"], value=want, before=par.get("value_string"),
                          after=a.get("value_string"), ok=ok)
                if not ok:
                    misses.append({"step": step["step"], "what": "write",
                                   "detail": f"{par['name']}: read back {a.get('value')!r}, wanted {want}"})
            knobs.append(kr)
        r["knobs"] = knobs
        results.append(r)
    if not steps and add_missing and not any(m["what"] == "blocked" for m in misses):
        # ORDER proof (live 2026-10-06: FL inserts into the SELECTED slot, so Pitcher
        # landed in slot 10 and the chain ran in the wrong order while every plugin
        # "existed"). The recipe's plugins must sit in recipe order.
        final = assign_slots(chosen, list_fx(conn, track))
        placed = [x for x in final if x is not None]
        # order only has to be INCREASING: other plugins may legitimately come first
        if placed != sorted(placed) and len(placed) == len(final):
            # fix it: verified 'Move up' steps via the slot menu (live 2026-10-06)
            from fl_studio_mcp.utils.plugin_options import reorder
            ro = reorder(conn, track, [s["plugin"] for s in chosen])
            final = assign_slots(chosen, list_fx(conn, track))
            placed = [x for x in final if x is not None]
            results.append({"step": "(reorder)", "plugin": "-", "moves": ro.get("moves"),
                            "ok": ro.get("success"), "error": ro.get("error")})
        if placed != sorted(placed) or len(placed) != len(final):
            misses.append({"step": "(chain)", "what": "order",
                           "detail": f"slots in recipe order are {final}, not increasing",
                           "loaded": [x["plugin"] for x in list_fx(conn, track)]})
    return {"action": "apply", "success": not misses, "track": track,
            "recipe": recipe.get("name"), "steps": results, "misses": misses,
            "next": ("all knobs set: A/B with fl_mixer fx_on, listen, refine the recipe JSON"
                     if not misses else
                     "fix the recipe from `candidates` (or fl_vocal learn) and re-apply")}


def buses(conn, recipe: dict, vocal: int, vocal_bus: int, reverb_bus: int, delay_bus: int,
          fx_tracks: dict[str, int] | None = None, dry_run: bool = False) -> dict:
    """Wire the ITM layout (skills/fl-mixing/references/vocal-bus-routing.md)."""
    from fl_studio_mcp.tools.mixer_tracks import run_track_action
    from fl_studio_mcp.tools.mixer_v2 import fl_mixer
    rt = recipe.get("routing") or {}
    fx_tracks = fx_tracks or {}
    colors = rt.get("colors", {})
    ops: list[tuple[str, dict]] = []
    for role, t in (("vocal", vocal), ("vocal_bus", vocal_bus),
                    ("reverb_bus", reverb_bus), ("delay_bus", delay_bus)):
        ops.append(("name", {"track": t, "name": rt.get("names", {}).get(role, role.replace("_", " ").title())}))
        if role in colors:
            ops.append(("color", {"track": t, "color": colors[role]}))
    ops.append(("route_only", {"track": vocal, "to": vocal_bus}))
    for bus in (vocal_bus, reverb_bus, delay_bus):
        ops.append(("route_only", {"track": bus, "to": 0}))
    for label, t in fx_tracks.items():
        bus = reverb_bus if "reverb" in label.lower() else delay_bus
        ops.append(("name", {"track": t, "name": label}))
        ops.append(("route_only", {"track": t, "to": bus}))
        lvl = (rt.get("send_levels") or {}).get(label, rt.get("default_send", 0.6))
        ops.append(("sends", {"track": vocal, "to": t, "level": float(lvl)}))
    if dry_run:
        return {"action": "buses", "success": True, "dry_run": True,
                "ops": [{"op": o, **p} for o, p in ops]}
    done, errs = [], []
    for op, p in ops:
        r = (fl_mixer("sends", conn=conn, **p) if op == "sends"
             else run_track_action(op, conn, p))
        done.append({"op": op, **p, "ok": bool(r.get("success")), "error": r.get("error")})
        if not r.get("success"):
            errs.append(done[-1])
    return {"action": "buses", "success": not errs, "ops": done, "failed": errs,
            "note": "Fruity Send (pre-fader, per-slot) is NOT used: plain sends from the vocal "
                    "track. Insert Fruity Send by hand when you need pre-effects sends."}


# ------------------------------------------------------------------ setup (one word)

def free_block(conn, n: int = 5) -> int | None:
    """First of n consecutive inserts that are untouched: default name 'Insert N',
    no plugins, no channel routed into them."""
    from fl_studio_mcp.tools.mixer_v2 import _exec
    rows = json.loads(_exec(conn, (
        "import json, mixer, channels, plugins\n"
        "used = set(channels.getTargetFxTrack(i) for i in range(channels.channelCount()))\n"
        "out = []\n"
        "for t in range(1, mixer.trackCount()):\n"
        "    nm = mixer.getTrackName(t)\n"
        "    out.append([t, nm, any(plugins.isValid(t, s) for s in range(10)), t in used])\n"
        "print(json.dumps(out))")))
    free = {t for t, nm, fx, used in rows if nm == f"Insert {t}" and not fx and not used}
    return next((t for t in sorted(free) if all(t + k in free for k in range(n))), None)


def unique_names(conn, rec: dict, mine: set[int]) -> dict:
    """Give this layout's tracks names no OTHER track already has ("Vocal 2", ...).
    Live 2026-10-05: a second setup reused "Vocal"/"Vocal Bus"... and the screen
    check ("Mixer - Vocal") could no longer tell track 6 from track 12."""
    import copy

    from fl_studio_mcp.tools.mixer_v2 import _exec
    taken = set(json.loads(_exec(conn, (
        "import json, mixer\n"
        f"print(json.dumps([mixer.getTrackName(t) for t in range(1, mixer.trackCount()) "
        f"if t not in {sorted(mine)}]))"))))
    rec = copy.deepcopy(rec)
    names = rec.setdefault("routing", {}).setdefault("names", {})
    base = {"vocal": "Vocal", "vocal_bus": "Vocal Bus", "reverb_bus": "Reverb Bus",
            "delay_bus": "Delay Bus"}
    all_names = [names.get(k, b) for k, b in base.items()] + ["Hall Reverb"]
    n = 1
    while any((f"{x} {n}" if n > 1 else x) in taken for x in all_names):
        n += 1
    if n > 1:
        for k, b in base.items():
            names[k] = f"{names.get(k, b)} {n}"
        rec["_fx_label"] = f"Hall Reverb {n}"
    return rec


def setup(conn, vocal: int | None = None, chain: str = "vocal-clean-stock",
          bus_recipe: str = "vocal-buses", dry_run: bool = False) -> dict:
    """ONE call: buses + vocal chain + reverb (+duck) + delay + sends, on 5 inserts
    (vocal, vocal bus, reverb bus, delay bus, reverb fx). success = 0 misses."""
    import time as _t
    t0 = _t.time()
    v = vocal if vocal is not None else free_block(conn, 5)
    if v is None and vocal is None:
        # no 5 free inserts (live 2026-10-06: the owner deleted all inserts): add them
        from fl_studio_mcp.tools.mixer_tracks import add_tracks
        at = add_tracks(conn, 5)
        v = free_block(conn, 5) if at.get("success") else None
    if v is None:
        return {"action": "setup", "success": False,
                "error": "no 5 free consecutive inserts (default name, empty, unrouted); pass vocal=N"}
    tracks = {"vocal": v, "vocal_bus": v + 1, "reverb_bus": v + 2, "delay_bus": v + 3, "reverb_fx": v + 4}
    rec = load_recipe(bus_recipe)
    rec = unique_names(conn, rec, set(tracks.values()))
    send = float((rec.get("routing") or {}).get("delay_bus_send", 0.45))
    fx_label = rec.get("_fx_label", "Hall Reverb")
    plan = [("buses", lambda: buses(conn, rec, v, v + 1, v + 2, v + 3, {fx_label: v + 4})),
            ("vocal chain", lambda: apply(conn, load_recipe(chain), v, None, True, False)),
            ("reverb + duck", lambda: apply(conn, rec, v + 4, ["reverb", "duck"], True, False)),
            ("delay", lambda: apply(conn, rec, v + 3, ["delay"], True, False))]
    if dry_run:
        return {"action": "setup", "success": True, "dry_run": True, "tracks": tracks,
                "steps": [n for n, _ in plan] + [f"send vocal -> delay bus {send}"]}
    report, misses = [], []
    for name, fn in plan:
        r = _call_guarded(lambda a, conn=None, **k: fn(), name, conn, {})
        ok = bool(r.get("success"))
        report.append({"step": name, "ok": ok})
        misses += [{"step": name, **m} for m in r.get("misses") or []]
        misses += [{"step": name, "what": "op", "detail": f.get("error")} for f in r.get("failed") or []]
        if not ok and not (r.get("misses") or r.get("failed")):
            misses.append({"step": name, "what": "error", "detail": r.get("error")})
    from fl_studio_mcp.tools.mixer_v2 import fl_mixer
    sr = fl_mixer("sends", conn=conn, track=v, to=v + 3, level=send)
    report.append({"step": "send vocal -> delay bus", "ok": bool(sr.get("success"))})
    if not sr.get("success"):
        misses.append({"step": "send", "what": "op", "detail": sr.get("error")})
    return {"action": "setup", "success": not misses, "tracks": tracks, "steps": report,
            "misses": misses, "seconds": round(_t.time() - t0, 1)}


# ------------------------------------------------------------------ onboarding

PLUGINS_DIR = RECIPES / "plugins"


def onboard(conn, plugin: str, track: int | None = None) -> dict:
    """New plugin -> ready for recipes: insert it (picker index route; the picker
    order rebuilds itself for unknown names), save its REAL knob names + current
    display values, read its preset menu, write presets/vocal/plugins/<plugin>.json
    with a recipe-step stub. Nothing is configured; the slot stays for auditioning."""
    from fl_studio_mcp.tools.mixer_tracks import list_fx
    from fl_studio_mcp.utils.plugin_preset_ui import list_presets_ui
    t = track if track is not None else free_block(conn, 1)
    if t is None:
        return {"action": "onboard", "success": False, "error": "no free insert; pass track=N"}
    slot = next((s["slot"] for s in list_fx(conn, t) if _plugin_matches(s["plugin"], plugin)), None)
    inserted = False
    if slot is None:
        from fl_studio_mcp.utils.add_effect import add_effect
        ins = add_effect(t, plugin, conn=conn, log=lambda m: None)
        if not ins.get("ok"):
            return {"action": "onboard", "success": False, "track": t,
                    "error": f"insert failed: {ins.get('error')}", "log": ins.get("log")}
        slot, inserted = int(ins["slot"]), True
    knobs = learn(conn, t, slot)
    pres = list_presets_ui(conn, t, slot)
    from fl_studio_mcp.tools.plugin_v2 import _list_params
    plist = [p for p in _list_params(conn, t, slot) if _norm(p.get("name")) not in ("", "notused")]
    stub = {"step": _norm(plugin) or "step", "plugin": plugin,
            "params": [{"param": [p["name"]], "target": p.get("value_string")} for p in plist[:8]
                       if p.get("value_string")],
            "note": "stub from onboarding: keep the knobs you need, set targets in real units"}
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    f = PLUGINS_DIR / f"{_norm(plugin)}.json"
    f.write_text(json.dumps({"plugin": plugin, "knobs": [p["name"] for p in plist],
                             "presets": pres.get("presets") or [],
                             "recipe_step_stub": stub}, indent=1) + "\n")
    return {"action": "onboard", "success": bool(knobs.get("success")), "track": t, "slot": slot,
            "inserted": inserted, "knobs": len(plist),
            "presets": len(pres.get("presets") or []), "presets_error": pres.get("error"),
            "file": str(f.relative_to(PKG_ROOT)), "stub": stub}


# ------------------------------------------------------------------ loudness (no FL)

_EBU = {"I": re.compile(r"I:\s*(-?[\d.]+|-inf)\s*LUFS"),
        "LRA": re.compile(r"LRA:\s*(-?[\d.]+)\s*LU"),
        "peak": re.compile(r"Peak:\s*(-?[\d.]+|-inf)\s*dBFS")}


def parse_ebur128(text: str) -> dict:
    tail = text[text.rfind("Summary:"):] if "Summary:" in text else text
    out = {}
    for k, rx in _EBU.items():
        m = rx.search(tail)
        if m:
            out[k] = float(m.group(1)) if m.group(1) != "-inf" else float("-inf")
    return out


def measure(path: str) -> dict:
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg not on PATH")
    p = subprocess.run([ff, "-hide_banner", "-nostats", "-i", path, "-af",
                        "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=600)
    m = parse_ebur128(p.stderr)
    if "I" not in m:
        raise RuntimeError(f"ffmpeg gave no loudness for {path}: {p.stderr[-300:]}")
    return {"integrated_lufs": m["I"], "lra_lu": m.get("LRA"), "true_peak_dbfs": m.get("peak")}


def loudness(path: str, reference: str | None = None, target_lufs: float | None = None) -> dict:
    for f in filter(None, (path, reference)):
        if not Path(f).is_file():
            return {"action": "loudness", "success": False, "error": f"no file {f}"}
    out: dict[str, Any] = {"action": "loudness", "success": True, "mix": measure(path)}
    advice = []
    if reference:
        out["reference"] = measure(reference)
        d = round(out["mix"]["integrated_lufs"] - out["reference"]["integrated_lufs"], 1)
        out["delta_vs_reference_lu"] = d
        advice.append(f"mix is {abs(d)} LU {'quieter' if d < 0 else 'louder'} than the reference")
    if target_lufs is not None:
        d = round(out["mix"]["integrated_lufs"] - float(target_lufs), 1)
        out["delta_vs_target_lu"] = d
        if d < -0.5:
            advice.append("too quiet: cut more low end in the EQs, then raise Maximus pre/post gain")
    tp = out["mix"].get("true_peak_dbfs")
    if tp is not None and tp > -1.0:
        advice.append(f"true peak {tp} dBFS > -1: lower the ceiling (streaming encoders clip)")
    out["advice"] = advice
    return out


# ------------------------------------------------------------------ run (batch)

_KEEP = ("track", "slot", "plugin", "param", "name", "target", "before", "after",
         "match", "misses", "routes_after", "value_string", "error")
MAX_OPS = 60


def _compact(r: dict) -> dict:
    out = {k: r[k] for k in _KEEP if r.get(k) not in (None, [], {})}
    if isinstance(r.get("after"), dict):          # mixer track actions: before/after dicts
        out.pop("before", None)
    return out


def _call_guarded(fn, action: str, conn, kw: dict) -> dict:
    """Call; on 'Operation unsafe' / controller timeout run ui_guard.recover once
    and retry (live 2026-10-05: a leftover picker/dialog failed every later op)."""
    from fl_studio_mcp.utils.ui_guard import is_blocked_error, recover
    for attempt in (1, 2):
        try:
            r = fn(action, conn=conn, **kw)
        except Exception as e:                       # one bad op never kills the report
            r = {"success": False, "error": str(e)}
        if r.get("success") or attempt == 2 or not is_blocked_error(r.get("error")):
            return r
        rec = recover(conn)
        r["recovered"] = rec.get("steps")
        if not rec.get("success"):
            return r
    return r


def run_ops(conn, ops: list[dict], stop_on_error: bool = True) -> dict:
    from fl_studio_mcp.tools.mixer_v2 import fl_mixer
    from fl_studio_mcp.tools.plugin_v2 import fl_plugin
    tools = {"mixer": fl_mixer, "plugin": fl_plugin,
             "vocal": lambda action, conn=None, **kw: fl_vocal(action, conn=conn, **kw)}
    if not isinstance(ops, list) or not ops:
        return {"action": "run", "success": False, "error": "run: ops must be a non-empty list"}
    if len(ops) > MAX_OPS:
        return {"action": "run", "success": False, "error": f"run: max {MAX_OPS} ops per call"}
    bad = [i for i, o in enumerate(ops)
           if not isinstance(o, dict) or o.get("tool") not in tools or not o.get("action")
           or (o.get("tool") == "vocal" and o.get("action") == "run")]
    if bad:
        return {"action": "run", "success": False,
                "error": f"ops {bad}: need tool mixer|plugin|vocal + action (no nested run)"}
    results, failed = [], 0
    for i, op in enumerate(ops):
        kw = {k: v for k, v in op.items() if k not in ("tool", "action")}
        r = _call_guarded(tools[op["tool"]], op["action"], conn, kw)
        ok = bool(r.get("success"))
        results.append({"i": i, "op": f"{op['tool']}.{op['action']}", "ok": ok, **_compact(r)})
        if not ok:
            failed += 1
            if stop_on_error:
                break
    return {"action": "run", "success": failed == 0 and len(results) == len(ops),
            "done": len(results), "of": len(ops), "failed": failed, "results": results}


# ------------------------------------------------------------------ dispatcher

def fl_vocal(action: str, conn=None, **p: Any) -> dict:
    if action not in ACTIONS:
        return {"success": False, "error": f"unknown action {action!r}", "valid_actions": list(ACTIONS)}
    try:
        if action == "recipes":
            return {"action": action, "success": True, "recipes": list_recipes(),
                    "knob_catalogs": sorted(f.stem for f in KNOBS.glob("*.json"))}
        if action == "show":
            return {"action": action, "success": True, "recipe": load_recipe(p["recipe"])}
        if action == "run":
            return run_ops(_conn(conn), p.get("ops"), p.get("stop_on_error", True))
        if action == "setup":
            return setup(_conn(conn), p.get("vocal"), p.get("recipe") or "vocal-clean-stock",
                         p.get("bus_recipe") or "vocal-buses", bool(p.get("dry_run")))
        if action == "onboard":
            if not p.get("plugin"):
                return {"success": False, "error": "onboard: plugin (exact picker name) required"}
            return onboard(_conn(conn), p["plugin"], p.get("track"))
        if action == "loudness":
            if not p.get("path"):
                return {"success": False, "error": "loudness: path required"}
            return loudness(p["path"], p.get("reference"), p.get("target_lufs"))
        need = {"status": ("track",), "learn": ("track", "slot"),
                "apply": ("recipe", "track"),
                "buses": ("recipe", "vocal", "vocal_bus", "reverb_bus", "delay_bus")}[action]
        miss = [k for k in need if p.get(k) is None]
        if miss:
            return {"success": False, "error": f"{action}: missing {miss}"}
        if action == "buses" and len({p["vocal"], p["vocal_bus"], p["reverb_bus"], p["delay_bus"], 0}) < 5:
            return {"success": False, "error": "buses: vocal / buses must be 4 distinct non-master tracks"}
        conn = _conn(conn)
        if action == "status":
            return status(conn, int(p["track"]))
        if action == "learn":
            return learn(conn, int(p["track"]), int(p["slot"]))
        # apply / buses are idempotent (targets, plugin detection): on a blocked FL
        # ('Operation unsafe' / timeout) recover once and re-run the whole thing.
        if action == "apply":
            return _call_guarded(lambda a, conn=None, **k: apply(
                conn, load_recipe(p["recipe"]), int(p["track"]), p.get("steps"),
                bool(p.get("add_missing")), bool(p.get("dry_run"))), action, conn, {})
        return _call_guarded(lambda a, conn=None, **k: buses(
            conn, load_recipe(p["recipe"]), int(p["vocal"]), int(p["vocal_bus"]),
            int(p["reverb_bus"]), int(p["delay_bus"]), p.get("fx_tracks"),
            bool(p.get("dry_run"))), action, conn, {})
    except Exception as e:
        return {"action": action, "success": False, "error": str(e)}


def register_vocal_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def fl_vocal(
        action: str,
        recipe: str | None = None,
        track: int | None = None,
        slot: int | None = None,
        steps: list[str] | None = None,
        add_missing: bool | None = None,
        dry_run: bool | None = None,
        vocal: int | None = None,
        vocal_bus: int | None = None,
        reverb_bus: int | None = None,
        delay_bus: int | None = None,
        fx_tracks: dict[str, int] | None = None,
        path: str | None = None,
        reference: str | None = None,
        target_lufs: float | None = None,
        ops: list[dict] | None = None,
        stop_on_error: bool | None = None,
        plugin: str | None = None,
        bus_recipe: str | None = None,
    ) -> dict:
        """Vocal mixing from JSON recipes (presets/vocal/): chains, buses, loudness.

        recipes | show(recipe) | status(track) — slots + knob display values |
        learn(track, slot) — save the plugin's real knob names (fix recipes) |
        apply(recipe, track, [steps], [add_missing], [dry_run]) — configure the
        chain's plugins (knobs in real units via fl_plugin dial); returns misses |
        buses(recipe, vocal, vocal_bus, reverb_bus, delay_bus, [fx_tracks
        {"Hall reverb": 12, ...}], [dry_run]) — names/colours, route-only, sends |
        run(ops, [stop_on_error=true]) ONE call for many steps: ops = [{"tool": "mixer"|
                                "plugin"|"vocal", "action": ..., <params>}, ...] run
                                in order, server-side; compact per-op results. Saves
                                MCP round-trips (owner request 2026-10-05).
  loudness(path, [reference], [target_lufs]) — ffmpeg LUFS/LRA/true peak.
        Skill: fl-mixing (references/vocal-chain.md). Convention, not auditioned.
        """
        args = {k: v for k, v in locals().items() if k != "action" and v is not None}
        from fl_studio_mcp.tools.vocal_v2 import fl_vocal as _impl
        return _impl(action, **args)

"""fl_ui_script — scriptable, mouse-free FL UI routines (controller v10.4i).

FL's Python API has NO plugin-loading call (mixer/plugins probed live
2026-10-03; the official il-group stubs agree). What it does have is the
`ui` module: in-engine key events, window focus, the browser and an
undocumented `ui.showPicker`. This tool scripts those calls.

Split of work (why routines need no FL restart):
  * controller `ui.steps` — runs a bounded list of ALLOWLISTED calls in one
    trip (ui getters/keys/navigation, mixer track selection, plugin-slot
    getters). Only a new FUNCTION on that allowlist needs a restart.
  * this tool — the sequencing: variables, waits, oracle checks (`expect`),
    reads, cleanup. Routines are JSON files in `fl-studio-mcp/ui_routines/`
    (edit/add one, call again — no reload of anything).

Step kinds (one dict each):
  {"call": "ui.showPicker", "args": [1, 0]}   one allowlisted call, own trip
  {"call": [{"fn": ..., "args": [...]}, ...]} several calls in ONE trip
  {"read": "ui.getFocusedFormCaption", "as": "caption"}   record, never fails
  {"expect": "ui.isInPopupMenu", "equals": true | "contains": "Picker",
   "retries": 5, "interval": 0.2}             oracle; fails the run on miss
  {"wait": 0.3}                               seconds (MCP-side sleep)
Strings like "{track}" are replaced by the run's vars (whole-string → typed).

Safety: KEY events that act on a focused form (enter/up/down/left/right/
yes/no/jog/next/previous) are refused until an `expect` step has passed in
the same run — the §0 rule (keys land on whatever has focus, e.g. the
user's browser panel). `escape` is always allowed. On any failure the
routine's `on_fail` steps run (default: one `ui.escape`).
"""
from __future__ import annotations

import ast
import json
import re
import time
from pathlib import Path
from typing import Any

ROUTINES_DIR = Path(__file__).resolve().parents[3] / "ui_routines"
ACTIONS = ("list", "show", "run", "steps")

# Must mirror the controller's _STEP_FNS (tests keep them in sync).
STEP_FNS = {
    "ui": frozenset({
        # safe reads
        "getProgTitle", "getVersion", "getFocused", "getFocusedFormID",
        "getFocusedFormCaption", "getFocusedNodeCaption",
        "getFocusedNodeFileType", "getFocusedPluginName", "getHintMsg",
        "getHintValue", "getSnapMode", "getStepEditMode", "getTimeDispMin",
        "isBrowserAutoHide", "isClosing", "isInPopupMenu", "getVisible",
        # key events
        "enter", "escape", "up", "down", "left", "right",
        "jog", "jog2", "previous", "next",
        # v10.4i navigation tier
        "showPicker", "setFocused", "showWindow", "hideWindow",
        "closeActivePopupMenu", "closeAllMenu",
        "navigateBrowser", "navigateBrowserMenu", "navigateBrowserTabs",
        "toggleBrowserNode", "previewBrowserMenuItem", "yes", "no",
    }),
    "mixer": frozenset({
        "trackNumber", "setTrackNumber", "selectTrack", "setActiveTrack",
        "isTrackSelected", "focusEditor", "getActiveEffectIndex",
        "getTrackPluginId", "isTrackPluginValid", "getTrackName",
    }),
    "plugins": frozenset({"isValid", "getPluginName", "getName"}),
}
GUARDED_KEYS = frozenset({"ui.enter", "ui.up", "ui.down", "ui.left",
                          "ui.right", "ui.yes", "ui.no", "ui.jog",
                          "ui.jog2", "ui.next", "ui.previous"})
MAX_STEPS = 40
_VAR = re.compile(r"\{(\w+)\}")


# --------------------------------------------------------------- pure helpers

def _allowed(fn: str) -> bool:
    mod, _, name = str(fn).partition(".")
    return name in STEP_FNS.get(mod, ())


def _subst(value: Any, vars_: dict) -> Any:
    """Replace {name} placeholders; a whole-string placeholder keeps its type."""
    if isinstance(value, str):
        m = _VAR.fullmatch(value)
        if m and m.group(1) in vars_:
            return vars_[m.group(1)]
        return _VAR.sub(lambda mm: str(vars_.get(mm.group(1), mm.group(0))),
                        value)
    if isinstance(value, list):
        return [_subst(v, vars_) for v in value]
    if isinstance(value, dict):
        return {k: _subst(v, vars_) for k, v in value.items()}
    return value


def _calls_of(step: dict) -> list[dict]:
    """The controller calls a step makes (empty for wait)."""
    if "call" in step:
        c = step["call"]
        if isinstance(c, list):
            return [{"fn": x.get("fn"), "args": x.get("args", [])} for x in c]
        return [{"fn": c, "args": step.get("args", [])}]
    if "read" in step:
        return [{"fn": step["read"], "args": step.get("args", [])}]
    if "expect" in step:
        return [{"fn": step["expect"], "args": step.get("args", [])}]
    return []


def validate(steps: Any) -> list[str]:
    """Static checks before anything is sent. Empty list = OK."""
    errs: list[str] = []
    if not isinstance(steps, list) or not steps:
        return ["steps must be a non-empty list"]
    if len(steps) > MAX_STEPS:
        errs.append(f"too many steps ({len(steps)} > {MAX_STEPS})")
    guarded = False
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            errs.append(f"step {i}: not an object")
            continue
        kinds = [k for k in ("call", "read", "expect", "wait") if k in s]
        if len(kinds) != 1:
            errs.append(f"step {i}: needs exactly one of call/read/expect/wait")
            continue
        if "wait" in s:
            try:
                if not 0 <= float(s["wait"]) <= 5:
                    errs.append(f"step {i}: wait must be 0-5 s")
            except (TypeError, ValueError):
                errs.append(f"step {i}: wait must be a number")
            continue
        if "expect" in s and not ("equals" in s or "contains" in s):
            errs.append(f"step {i}: expect needs equals or contains")
        for c in _calls_of(s):
            if not _allowed(c["fn"]):
                errs.append(f"step {i}: {c['fn']!r} is not on the allowlist")
            if not isinstance(c["args"], list):
                errs.append(f"step {i}: args must be a list")
            if c["fn"] in GUARDED_KEYS and not guarded:
                errs.append(f"step {i}: key {c['fn']} before any expect "
                            "(keys hit whatever has focus — add an expect "
                            "that proves the target is open first)")
        if "expect" in s:
            guarded = True
    return errs


def _value(result_repr: Any) -> Any:
    """Controller results are repr() strings — turn them back into values."""
    if not isinstance(result_repr, str):
        return result_repr
    try:
        return ast.literal_eval(result_repr)
    except (ValueError, SyntaxError):
        return result_repr


def _matches(step: dict, value: Any) -> bool:
    if "equals" in step:
        want = step["equals"]
        if isinstance(want, bool) and isinstance(value, int):
            return bool(value) == want
        return value == want
    return str(step["contains"]).lower() in str(value).lower()


# ------------------------------------------------------------------ routines

def _load(name: str) -> dict:
    if not re.fullmatch(r"[\w-]+", name or ""):
        raise ValueError(f"bad routine name {name!r}")
    path = ROUTINES_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"no routine {name!r}; have: {sorted(_names())}")
    return json.loads(path.read_text())


def _names() -> list[str]:
    return sorted(p.stem for p in ROUTINES_DIR.glob("*.json"))


def _resolve_vars(routine: dict, given: dict | None) -> tuple[dict, list[str]]:
    given = dict(given or {})
    out: dict = {}
    missing: list[str] = []
    for name, spec in (routine.get("vars") or {}).items():
        spec = spec or {}
        if name in given:
            v = given.pop(name)
        elif "default" in spec:
            v = spec["default"]
        else:
            missing.append(name)
            continue
        if spec.get("type") == "int":
            v = int(v)
        out[name] = v
    if given:
        missing.append(f"unknown vars: {sorted(given)}")
    return out, missing


# ------------------------------------------------------------------- runner

def _send(conn, calls: list[dict]) -> dict:
    try:
        return conn.send_command("ui.steps", {"steps": calls}, timeout=10.0)
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": str(e)[:300]}


def _not_deployed(res: dict) -> bool:
    return "unknown action" in str(res.get("error", "")).lower()


def execute(steps: list, conn, on_fail: list | None = None,
            sleep=time.sleep) -> dict:
    """Run validated, var-substituted steps. Returns a per-step log."""
    log: list[dict] = []
    reads: dict = {}

    def fail(i: int, why: str, res: dict | None = None) -> dict:
        cleanup = []
        for s in (on_fail if on_fail is not None
                  else [{"call": "ui.escape"}]):
            r = _send(conn, _calls_of(s))
            cleanup.append({"step": s, "success": bool(r.get("success"))})
        out = {"success": False, "failed_step": i, "error": why,
               "log": log, "reads": reads, "cleanup": cleanup}
        if res and _not_deployed(res):
            out["error"] = ("controller v10.4i (ui.steps) not deployed: sync "
                            "the controller and restart FL")
        return out

    for i, s in enumerate(steps):
        if "wait" in s:
            sleep(float(s["wait"]))
            log.append({"step": i, "wait": s["wait"]})
            continue
        calls = _calls_of(s)
        tries = int(s.get("retries", 1)) if "expect" in s else 1
        for attempt in range(max(1, tries)):
            res = _send(conn, calls)
            if not res.get("success"):
                return fail(i, res.get("error") or "call failed", res)
            executed = res.get("executed") or []
            value = _value(executed[-1].get("result")) if executed else None
            if "expect" not in s or _matches(s, value):
                break
            if attempt + 1 < tries:
                sleep(float(s.get("interval", 0.2)))
        entry = {"step": i, "calls": [c["fn"] for c in calls],
                 "value": value}
        log.append(entry)
        if "read" in s:
            reads[s.get("as") or s["read"]] = value
        if "expect" in s and not _matches(s, value):
            return fail(i, f"expect {s['expect']} "
                           f"{'==' if 'equals' in s else 'contains'} "
                           f"{s.get('equals', s.get('contains'))!r}, "
                           f"got {value!r}")
    return {"success": True, "log": log, "reads": reads}


def fl_ui_script(action: str, routine: str | None = None,
                 vars: dict | None = None, steps: list | None = None,
                 dry_run: bool = False, conn=None) -> dict:
    if action not in ACTIONS:
        return {"success": False, "error": f"unknown action {action!r}",
                "valid_actions": list(ACTIONS)}
    if action == "list":
        out = []
        for n in _names():
            try:
                r = _load(n)
                out.append({"name": n, "status": r.get("status", "?"),
                            "description": r.get("description", "")})
            except Exception as e:  # noqa: BLE001
                out.append({"name": n, "error": str(e)[:120]})
        return {"success": True, "routines": out,
                "dir": str(ROUTINES_DIR)}
    on_fail = None
    if action in ("show", "run"):
        try:
            r = _load(routine or "")
        except Exception as e:  # noqa: BLE001
            return {"success": False, "error": str(e)}
        if action == "show":
            return {"success": True, "routine": r}
        resolved, missing = _resolve_vars(r, vars)
        if missing:
            return {"success": False, "error": f"vars: {missing}",
                    "vars": r.get("vars")}
        steps = _subst(r.get("steps"), resolved)
        if "on_fail" in r:
            on_fail = _subst(r["on_fail"], resolved)
    else:
        steps = _subst(steps, vars or {})
    errs = validate(steps) + (validate(on_fail) if on_fail else [])
    if errs:
        return {"success": False, "error": "invalid steps", "problems": errs}
    if dry_run:
        return {"success": True, "dry_run": True, "steps": steps}
    if conn is None:
        from fl_studio_mcp.utils.connection import get_connection
        conn = get_connection()
    return execute(steps, conn, on_fail=on_fail)


def register_ui_script_tools(mcp) -> None:
    """Register fl_ui_script (scriptable mouse-free UI routines)."""
    from fl_studio_mcp.tools.ui_script_v2 import fl_ui_script as _impl

    @mcp.tool()
    def fl_ui_script(action: str, routine: str | None = None,
                     vars: dict | None = None, steps: list | None = None,
                     dry_run: bool = False) -> dict:
        """Run mouse-free FL UI routines (in-engine ui/mixer calls; no clicks).

        Actions: list | show(routine) | run(routine, vars, dry_run) |
        steps(steps, vars, dry_run) — ad-hoc steps.
        Routines = JSON in fl-studio-mcp/ui_routines/ (edit/add, no restart).
        Step kinds: {"call": "ui.fn", "args": []} | {"call": [{fn,args},..]}
        (one trip) | {"read": "ui.getter", "as": name} | {"expect": "ui.getter",
        "equals"|"contains": v, "retries", "interval"} | {"wait": s}.
        Key events (enter/up/down/...) need a passed expect first; escape
        is always allowed; on failure on_fail runs (default ui.escape).
        Needs controller v10.4i (ui.steps) — FL restart after syncing.
        """
        return _impl(action, routine=routine, vars=vars, steps=steps,
                     dry_run=dry_run)

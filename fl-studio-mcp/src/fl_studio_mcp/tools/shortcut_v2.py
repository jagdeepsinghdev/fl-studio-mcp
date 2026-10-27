"""fl_shortcut — FL Studio's own keyboard shortcuts as a guarded MCP tool.

Source: the manual's shortcut page (basics_shortcuts.htm), Mac-mapped, kept as
data in `fl-studio-mcp/shortcuts/catalog.json` (edit/add entries, no reload).

Why keystrokes work here when §5 says they don't: macOS keystrokes do not
reach FL's custom-drawn TEXT FIELDS / toolbar widgets, but FL's own hotkey
table does receive them while FL is frontmost — the ComposeWithLLM trigger
(Cmd+Opt+Y via System Events, `utils/fl_trigger.py`) has relied on that for
months. Shortcuts that open a text field (F2 rename) are still useless.

Guards, in order (every one refuses rather than guesses):
  1. risk   — view/toggle run; edit runs after the context proof;
              confirm (dialogs, deletes, renders) needs confirm=True —
              a modal blocks the controller thread (CLAUDE.md §5).
  2. front  — FL must be the frontmost app (keys go to the front app).
  3. focus  — the focused FL form's caption (ui.getFocusedFormCaption) must
              match the entry's context ("S" = solo in the mixer, slip tool
              in the playlist). focus=True first shows + focuses the window
              in-engine (ui.showWindow / ui.setFocused via ui.steps).
              Global entries refuse when focus sits in a window listed in
              `not_in` (Cmd+M = metronome, but Import MIDI in the roll).
  4. verify — optional oracle: {"changes": "ui.getter", "args": [...]}
              must read differently after the key ("or_focused": ctx also
              accepts the window coming to focus — F5-F9 on a visible,
              unfocused window focus it instead of hiding it).
"""
from __future__ import annotations

import ast
import json
import re
import time
from pathlib import Path
from typing import Any

CATALOG = Path(__file__).resolve().parents[3] / "shortcuts" / "catalog.json"
ACTIONS = ("list", "show", "run", "batch")
MAX_BATCH = 30
RISKS = ("view", "toggle", "edit", "confirm")

# context -> (caption fragment, ui window id for showWindow/setFocused)
CONTEXTS = {
    "mixer": ("mixer", 0),
    "channel_rack": ("channel rack", 1),
    "playlist": ("playlist", 2),
    "piano_roll": ("piano roll", 3),
    "browser": ("browser", 4),
}

MODS = {"cmd": "command down", "opt": "option down",
        "shift": "shift down", "ctrl": "control down"}
# macOS virtual key codes (key code N) for non-character keys
KEY_CODES = {
    "F1": 122, "F2": 120, "F3": 99, "F4": 118, "F5": 96, "F6": 97,
    "F7": 98, "F8": 100, "F9": 101, "F10": 109, "F11": 103, "F12": 111,
    "space": 49, "return": 36, "enter": 76, "tab": 48, "esc": 53,
    "backspace": 51, "fwddel": 117, "home": 115, "end": 119,
    "pgup": 116, "pgdn": 121,
    "left": 123, "right": 124, "down": 125, "up": 126,
    "num0": 82, "num1": 83, "num2": 84, "num3": 85, "num4": 86,
    "num5": 87, "num6": 88, "num7": 89, "num8": 91, "num9": 92,
    "num_star": 67, "num_plus": 69, "num_minus": 78, "num_slash": 75,
}
_CHAR = re.compile(r"[a-z0-9]")


# --------------------------------------------------------------- pure helpers

def parse_keys(keys: str) -> tuple[list[str], str]:
    """'cmd+shift+s' -> (['cmd', 'shift'], 's'). Raises ValueError."""
    parts = [p for p in str(keys).split("+") if p]
    if not parts:
        raise ValueError("empty key spec")
    *mods, key = parts
    bad = [m for m in mods if m not in MODS]
    if bad:
        raise ValueError(f"unknown modifier(s) {bad} in {keys!r}")
    if len(set(mods)) != len(mods):
        raise ValueError(f"repeated modifier in {keys!r}")
    if key not in KEY_CODES and not _CHAR.fullmatch(key):
        raise ValueError(f"unknown key {key!r} in {keys!r}")
    return mods, key


def applescript(keys: str) -> str:
    """The System Events line that sends `keys` to the frontmost app."""
    mods, key = parse_keys(keys)
    using = (" using {" + ", ".join(MODS[m] for m in mods) + "}") if mods else ""
    if key in KEY_CODES:
        press = f"key code {KEY_CODES[key]}{using}"
    else:
        press = f'keystroke "{key}"{using}'
    return f'tell application "System Events" to {press}'


def load_catalog(path: Path = CATALOG) -> list[dict]:
    return json.loads(path.read_text())["shortcuts"]


def validate_catalog(entries: list[dict]) -> list[str]:
    errs: list[str] = []
    seen: set[str] = set()
    for e in entries:
        i = e.get("id", "?")
        if i in seen:
            errs.append(f"{i}: duplicate id")
        seen.add(i)
        try:
            parse_keys(e.get("keys", ""))
        except ValueError as ex:
            errs.append(f"{i}: {ex}")
        if e.get("context") != "global" and e.get("context") not in CONTEXTS:
            errs.append(f"{i}: unknown context {e.get('context')!r}")
        if e.get("risk") not in RISKS:
            errs.append(f"{i}: unknown risk {e.get('risk')!r}")
        for c in e.get("not_in", []):
            if c not in CONTEXTS:
                errs.append(f"{i}: unknown not_in context {c!r}")
    return errs


def context_of(caption: str) -> str | None:
    low = str(caption or "").lower()
    for ctx, (frag, _) in CONTEXTS.items():
        if frag in low:
            return ctx
    return None


def _value(result_repr: Any) -> Any:
    if not isinstance(result_repr, str):
        return result_repr
    try:
        return ast.literal_eval(result_repr)
    except (ValueError, SyntaxError):
        return result_repr


def _brief(e: dict) -> dict:
    out = {k: e[k] for k in ("id", "keys", "action", "priority")
           if k in e}
    if e.get("risk") in ("edit", "confirm"):
        out["risk"] = e["risk"]
    if str(e.get("status", "")).startswith("verified"):
        out["verified"] = True
    if e.get("prefer"):
        out["prefer"] = e["prefer"]
    return out


# ------------------------------------------------------------- side effects

class _Live:
    """Real FL / macOS I/O. Tests pass a fake with the same methods."""

    def __init__(self, conn=None):
        self._conn = conn

    @property
    def conn(self):
        if self._conn is None:
            from fl_studio_mcp.utils.connection import get_connection
            self._conn = get_connection()
        return self._conn

    def fl_front(self) -> tuple[bool, str]:
        from fl_studio_mcp.utils import custom_menu as cm
        ok = cm.require_fl_front()
        return ok, ("" if ok else cm.frontmost_app())

    def ui_steps(self, calls: list[dict]) -> dict:
        try:
            return self.conn.send_command("ui.steps", {"steps": calls},
                                          timeout=10.0)
        except Exception as ex:  # noqa: BLE001
            return {"success": False, "error": str(ex)[:300]}

    def read(self, fn: str, args: list | None = None) -> Any:
        res = self.ui_steps([{"fn": fn, "args": list(args or [])}])
        if not res.get("success"):
            raise RuntimeError(res.get("error") or f"{fn} failed")
        executed = res.get("executed") or []
        return _value(executed[-1].get("result")) if executed else None

    def send_keys(self, keys: str) -> tuple[bool, str]:
        from fl_studio_mcp.utils import custom_menu as cm
        rc, _, err = cm.osa(applescript(keys))
        return rc == 0, err

    def sleep(self, s: float) -> None:
        time.sleep(s)

    def roll_snapshot(self) -> dict:
        """Re-export the OPEN roll via an empty ComposeWithLLM trigger and
        return its notes. Refuses when the queue holds notes (the trigger
        would apply them). A plain read_steps after a shortcut returns the
        PREVIOUS export (live 2026-10-04: legato looked like a no-op)."""
        from fl_studio_mcp.utils import roll_session as rs
        from fl_studio_mcp.utils.fl_trigger import FLStudioTrigger
        d = rs._scripts_dir()
        try:
            queued = json.loads((d / "mcp_request.json").read_text() or "[]")
        except (OSError, ValueError):
            queued = None
        if queued:
            return {"error": "queue not empty - not triggering (it would "
                             "apply queued notes); fl_notes(clear_queue) first"}
        before = rs.state_mtime()
        FLStudioTrigger()._trigger_macos()
        for _ in range(15):
            if rs.ran_since(before):
                break
            time.sleep(0.2)
        else:
            return {"error": "script did not re-export (state file unchanged)"}
        data = json.loads((d / "piano_roll_state.json").read_text())
        notes = [{"midi": n.get("number", n.get("midi")), "time": n.get("time"),
                  "duration": n.get("length", n.get("duration"))}
                 for n in data.get("notes", [])]
        return {"note_count": len(notes), "notes": notes[:64]}


def _focus(io, ctx: str, current: str | None = None) -> dict:
    """Hide then show: live 2026-10-04, showWindow on an already VISIBLE
    window and setFocused leave focus where it was (a View-menu toggle and a
    title-bar click did too); showing a HIDDEN window always focuses it.
    Once the Browser holds focus only the CHANNEL RACK can take it back
    (live 3/3), so the escape route is: hide Browser -> hide+show rack ->
    hide+show the target (side effect: the rack ends up visible)."""
    def hs(w):
        return [{"fn": "ui.hideWindow", "args": [w]},
                {"fn": "ui.showWindow", "args": [w]}]
    wid = CONTEXTS[ctx][1]
    steps = []
    if current == "browser" and ctx != "browser":
        steps.append({"fn": "ui.hideWindow", "args": [CONTEXTS["browser"][1]]})
        if ctx != "channel_rack":
            steps += hs(CONTEXTS["channel_rack"][1])
    steps += hs(wid)
    return io.ui_steps(steps)


def run_entry(e: dict, io, confirm: bool = False, focus: bool = False,
              settle: float = 0.4, readback: bool = True) -> dict:
    base = {"id": e.get("id"), "keys": e["keys"], "action": e.get("action")}
    if e.get("prefer"):
        base["prefer"] = e["prefer"]
    risk = e.get("risk", "confirm")
    if e.get("reach") == "no" and not confirm:
        return {**base, "success": False, "refused": "reach",
                "error": ("bare/shift letter and digit keys never reach FL "
                          "from macOS (live 2026-10-04: d, y, shift+1 did "
                          "nothing); pass confirm=true only to re-test")}
    if risk == "confirm" and not confirm:
        return {**base, "success": False, "refused": "confirm",
                "error": ("this shortcut opens a dialog or is destructive "
                          "(a modal blocks the controller); pass confirm=true "
                          "if you mean it" + (f"; or use {e['prefer']}"
                                              if e.get("prefer") else ""))}
    ok, front = io.fl_front()
    if not ok:
        return {**base, "success": False, "refused": "front",
                "error": f"FL Studio is not frontmost ({front!r})"}

    ctx = e.get("context", "global")
    try:
        caption = io.read("ui.getFocusedFormCaption")
    except RuntimeError as ex:
        return {**base, "success": False, "refused": "focus",
                "error": f"cannot read focused form: {ex}"}
    if ctx != "global" and context_of(caption) != ctx:
        if not focus:
            return {**base, "success": False, "refused": "focus",
                    "focused": caption,
                    "error": (f"needs {ctx} focused, focus is {caption!r}; "
                              "pass focus=true to show+focus it first")}
        res = _focus(io, ctx, context_of(caption))
        io.sleep(settle)
        caption = io.read("ui.getFocusedFormCaption")
        if not res.get("success") or context_of(caption) != ctx:
            return {**base, "success": False, "refused": "focus",
                    "focused": caption,
                    "error": f"could not focus {ctx} ({res.get('error') or caption!r})"}
    if ctx == "global" and context_of(caption) in e.get("not_in", []):
        return {**base, "success": False, "refused": "collision",
                "focused": caption,
                "error": (f"in the {context_of(caption)} this key means "
                          "something else; focus another window first")}

    verify = e.get("verify")
    before = None
    if verify:
        before = io.read(verify["changes"], verify.get("args"))
    roll_edit = ctx == "piano_roll" and risk == "edit"
    roll_before = io.roll_snapshot() if roll_edit and readback else None
    if roll_before and roll_before.get("error"):
        return {**base, "success": False, "refused": "readback",
                "error": roll_before["error"]}
    sent, err = io.send_keys(e["keys"])
    if not sent:
        return {**base, "success": False, "error": f"keystroke failed: {err}"}
    out = {**base, "success": True, "focused": caption}
    if verify:
        io.sleep(settle)
        after = io.read(verify["changes"], verify.get("args"))
        out["verify"] = {"read": verify["changes"], "before": before,
                         "after": after, "changed": before != after}
        # window toggles on a visible-but-unfocused window FOCUS it instead
        # of hiding it (live 2026-10-04: F9 with the rack focused) — the
        # window coming to focus is the shortcut landing too.
        landed_ctx = verify.get("or_focused")
        if before == after and landed_ctx:
            now = io.read("ui.getFocusedFormCaption")
            out["verify"]["focused_after"] = now
            if context_of(now) == landed_ctx:
                out["verify"]["changed"] = "focused"
                return out
        if before == after:
            out["success"] = False
            out["error"] = ("key sent but the oracle did not change — the "
                            "shortcut did not land (wrong focus, or FL Mac "
                            "maps it differently)")
    elif roll_before is not None:
        io.sleep(settle)
        after = io.roll_snapshot()
        out["roll"] = {"before": roll_before, "after": after,
                       "changed": after.get("notes") != roll_before.get("notes")}
        if after.get("error") or not out["roll"]["changed"]:
            out["success"] = False
            out["error"] = after.get("error") or (
                "roll notes unchanged - nothing selected, or the key did not land")
    else:
        out["unverified"] = "no oracle for this shortcut; check fl_state / a screenshot"
    return out


def run_batch(items: Any, io=None, confirm: bool = False,
              focus: bool = False, stop_on_fail: bool = True,
              dry_run: bool = False, pause: float = 0.3) -> dict:
    """Run several shortcuts in order in ONE tool call. Each item is an id
    or {"id"|"keys", "context", "focus", "confirm"}; every item passes the
    full guard chain (keys are OS keystrokes, so there is no single-trip
    form like fl_batch's). Validated up front; stops at the first failure
    unless stop_on_fail=False."""
    if not isinstance(items, list) or not items:
        return {"success": False, "error": "items must be a non-empty list"}
    if len(items) > MAX_BATCH:
        return {"success": False,
                "error": f"too many items ({len(items)} > {MAX_BATCH})"}
    norm, bad = [], []
    for it in items:
        d = {"id": it} if isinstance(it, str) else it
        if not isinstance(d, dict) or not (d.get("id") or d.get("keys")):
            bad.append(repr(it)[:60])
            continue
        norm.append(d)
    if bad:
        return {"success": False, "error": f"bad items: {bad}"}
    # validate everything before the first key
    for d in norm:
        r = fl_shortcut("show", id=d.get("id"), keys=d.get("keys"),
                        context=d.get("context"))
        if not r.get("success"):
            return {"success": False, "error": f"item {d}: {r.get('error')}",
                    "did_you_mean": r.get("did_you_mean")}
    if dry_run:
        return {"success": True, "dry_run": True,
                "items": [fl_shortcut("show", id=d.get("id"),
                                      keys=d.get("keys"),
                                      context=d.get("context"))["shortcut"]
                          for d in norm]}
    io = io or _Live()
    results = []
    for n, d in enumerate(norm):
        r = fl_shortcut("run", id=d.get("id"), keys=d.get("keys"),
                        context=d.get("context"),
                        confirm=bool(d.get("confirm", confirm)),
                        focus=bool(d.get("focus", focus)),
                        readback=bool(d.get("readback", True)), io=io)
        results.append(r)
        if not r.get("success") and stop_on_fail:
            return {"success": False, "stopped_at": n, "results": results,
                    "not_run": [x.get("id") or x.get("keys")
                                for x in norm[n + 1:]]}
        io.sleep(pause)
    ok = sum(1 for r in results if r.get("success"))
    return {"success": ok == len(results), "ran": len(results), "ok": ok,
            "results": results}


def fl_shortcut(action: str, id: str | None = None, keys: str | None = None,
                context: str | None = None, query: str | None = None,
                risk: str | None = None, confirm: bool = False,
                focus: bool = False, dry_run: bool = False,
                items: list | None = None, stop_on_fail: bool = True,
                limit: int = 10, offset: int = 0, priority: int | None = None,
                include_unreachable: bool = False, readback: bool = True,
                io=None) -> dict:
    if action not in ACTIONS:
        return {"success": False, "error": f"unknown action {action!r}",
                "valid_actions": list(ACTIONS)}
    if action == "batch":
        return run_batch(items, io=io, confirm=confirm, focus=focus,
                         stop_on_fail=stop_on_fail, dry_run=dry_run)
    try:
        entries = load_catalog()
    except Exception as ex:  # noqa: BLE001
        return {"success": False, "error": f"catalog: {ex}"}
    by_id = {e["id"]: e for e in entries}

    if action == "list":
        words = (query or "").lower().split()
        hits = [e for e in entries
                if (not context or e["context"] == context)
                and (not risk or e["risk"] == risk)
                and (priority is None or e.get("priority", 3) <= priority)
                and (include_unreachable or e.get("reach") != "no")
                and all(w in (e["id"] + " " + e["action"]).lower()
                        for w in words)]
        # production-first: priority, then verified, then catalog order
        hits.sort(key=lambda e: (e.get("priority", 3),
                                 not str(e.get("status", "")).startswith("verified")))
        lim = len(hits) if limit == 0 else max(1, limit)
        page = hits[offset:offset + lim]
        out = {"success": True, "total": len(hits), "shown": len(page),
               "shortcuts": [_brief(e) for e in page]}
        if offset + lim < len(hits):
            out["more"] = f"offset={offset + lim} (or limit=0 for all)"
        return out

    if keys and not id:
        # ad-hoc key spec (not in the catalog): treated as confirm-tier
        try:
            parse_keys(keys)
        except ValueError as ex:
            return {"success": False, "error": str(ex)}
        if context and context != "global" and context not in CONTEXTS:
            return {"success": False, "error": f"unknown context {context!r}"}
        e = {"id": None, "keys": keys, "context": context or "global",
             "action": "ad-hoc", "risk": "confirm"}
    else:
        e = by_id.get(id or "")
        if e is None:
            near = [i for i in by_id if (id or "").lower() in i.lower()][:10]
            return {"success": False, "error": f"no shortcut {id!r}",
                    "did_you_mean": near}

    if action == "show":
        return {"success": True, "shortcut": e,
                "applescript": applescript(e["keys"])}
    if dry_run:
        return {"success": True, "dry_run": True, "shortcut": _brief(e),
                "applescript": applescript(e["keys"])}
    return run_entry(e, io or _Live(), confirm=confirm, focus=focus,
                     readback=readback)


def register_shortcut_tools(mcp) -> None:
    """Register fl_shortcut (FL's keyboard shortcuts, guarded)."""
    from fl_studio_mcp.tools.shortcut_v2 import fl_shortcut as _impl

    @mcp.tool()
    def fl_shortcut(action: str, id: str | None = None,
                    keys: str | None = None, context: str | None = None,
                    query: str | None = None, risk: str | None = None,
                    confirm: bool = False, focus: bool = False,
                    dry_run: bool = False, items: list | None = None,
                    stop_on_fail: bool = True, limit: int = 10,
                    offset: int = 0, priority: int | None = None) -> dict:
        """Press one of FL Studio's own keyboard shortcuts (226 from the manual).

        Actions: list(query?, context?, priority?, limit=10, offset) — top
        matches, production-first (priority 1 = core beat/song work) | show(id) |
        run(id, focus?, confirm?, dry_run?) | run(keys="cmd+shift+s",
        context=..., confirm=true) for an ad-hoc key spec |
        batch(items=["mixer", {"id": "piano_roll.glue", "focus": true}, ...],
        stop_on_fail=true, dry_run?) — up to 30 in order, one call.
        Piano-roll EDIT shortcuts re-export the open roll before+after and
        fail if the notes didn't change (needs an empty queue; per item
        {"readback": false} skips it, e.g. for a middle step).
        Contexts: global, channel_rack, piano_roll, playlist, mixer, browser
        — the focused FL window must match (focus=true shows+focuses it).
        risk: view/toggle run; edit runs after the focus proof; confirm
        (dialogs/deletes/renders) needs confirm=true. Prefer the entry's
        `prefer` API tool when one exists. Bare/shift letter+digit keys
        don't reach FL (refused). FL must be frontmost; never use while
        the user is typing. Skill: skills/fl-studio/references/shortcuts.md.
        """
        return _impl(action, id=id, keys=keys, context=context, query=query,
                     risk=risk, confirm=confirm, focus=focus, dry_run=dry_run,
                     items=items, stop_on_fail=stop_on_fail, limit=limit,
                     offset=offset, priority=priority)

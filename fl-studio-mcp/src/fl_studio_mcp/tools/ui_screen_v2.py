"""fl_ui_screen — call allowlisted FL `ui.*` / `screen.*` functions (PE era).

2026-10-02: Producer Edition no longer aborts on ui/screen calls (the
trial build's libLicenceEngine was the blocker). The v10.4 controller
exposes two allowlisted actions — `ui.call` / `screen.call` — taking a
function name + positional args; FL's own exception text comes back when
the args are wrong, so signatures are self-teaching (the P4 method).

Targets (the two remaining manual steps in the project):
  * §0 — the web-rendered piano-roll SCRIPT DROPDOWN:
    screen.menuItemClick / ui.navigateBrowser / ui.setFocused.
  * P2 / LAUNCHPAD — the Options → MIDI settings INPUT PICK:
    ui.navigateBrowser / ui.selectBrowserMenuItem / ui.setFocused.

UI-level operations only: they touch focus, menus and navigation — never
project data — so there is no undo and they sit in the read-only batching
tier (a mis-fire is at worst a stray click; the crash guard auto-reverts
the controller if anything misbehaves).
"""
from __future__ import annotations

# 2026-10-02 crash: the FIRST live screen.* call (menuShowing, no args)
# killed FL (EAccessViolation, side thread, FLEngine_x64.dylib). screen.*
# is QUARANTINED end-to-end until functions are proven one by one.
# ui.* is exposed here as its pure-getter subset only (v10.4b controller
# enforces the same gate a second time).
MODULES = ("ui",)

_UI_SAFE_READS = frozenset({
    "getProgTitle", "getVersion", "getFocused", "getFocusedFormID",
    "getFocusedFormCaption", "getFocusedNodeCaption",
    "getFocusedNodeFileType", "getFocusedPluginName", "getHintMsg",
    "getHintValue", "getSnapMode", "getStepEditMode", "getTimeDispMin",
    "isBrowserAutoHide", "isClosing", "isInPopupMenu", "getVisible",
})
# v10.4c second tier: keyboard/navigation events (dispatch to the
# focused form; no focus = no-op). Browser/window fns stay gated.
_UI_KEY_EVENTS = frozenset({
    "enter", "escape", "up", "down", "left", "right",
    "jog", "jog2", "previous", "next",
})


def fl_ui_screen(module: str, action: str, args: list | None = None,
                 conn=None) -> dict:
    """Call one allowlisted ui.*/screen.* function with positional args.

    module: "ui" (enter/yes/no/jog/… navigateBrowser/setFocused/…) or
            "screen" (menuItemClick/menuNext/menuShowing/…).
    action: the function name (must be on the controller's allowlist).
    args:   positional arguments as a JSON list. Wrong arity/type →
            FL's own exception text is returned as `error` — it is the
            signature oracle; feed it back to learn the right shape.
    """
    if module not in MODULES:
        if module == "screen":
            return {"success": False,
                    "error": ("screen.* is quarantined: menuShowing() "
                              "crashed FL (EAccessViolation, side thread, "
                              "2026-10-02). No screen calls until "
                              "per-function testing is done."),
                    "asked_for": action}
        return {"success": False,
                "error": f"unknown module {module!r} (use 'ui')"}
    if module == "ui" and action in ("panels", "set_panels"):
        # panel awareness (utils/fl_panels): the 5 main panels via
        # ui.getVisible / showWindow / hideWindow — server-side, no pixels
        from fl_studio_mcp.utils import fl_panels as fp
        if conn is None:
            from fl_studio_mcp.utils.connection import get_connection
            conn = get_connection()
        names = {"mixer": fp.MIXER, "channel_rack": fp.CHANNEL_RACK,
                 "playlist": fp.PLAYLIST, "piano_roll": fp.PIANO_ROLL,
                 "browser": fp.BROWSER}
        try:
            if action == "set_panels":
                want = (args or [{}])[0] if args else {}
                bad = [k for k in want if k not in names]
                if bad or not isinstance(want, dict) or not want:
                    return {"success": False, "error": (
                        f"set_panels args = [{{panel: bool}}], panels: {sorted(names)}"
                        + (f"; unknown: {bad}" if bad else ""))}
                fp.set_visible(conn, {names[k]: bool(v) for k, v in want.items()})
            vis = fp.visible(conn)
        except Exception as e:  # noqa: BLE001
            return {"module": module, "action": action, "success": False, "error": str(e)}
        return {"module": module, "action": action, "success": True,
                "result": {k: vis[w] for k, w in names.items()}}
    if action not in (_UI_SAFE_READS | _UI_KEY_EVENTS):
        return {"success": False,
                "error": (f"ui.{action} is not callable in v10.4c. "
                          "Allowed now: "
                          + ", ".join(sorted(_UI_SAFE_READS | _UI_KEY_EVENTS)))}
    args = list(args or [])
    if conn is None:
        from fl_studio_mcp.utils.connection import get_connection
        conn = get_connection()

    from fl_studio_mcp.tools.channel_v2 import _safe_send
    try:
        res = _safe_send(f"{module}.call",
                         {"name": action, "args": args}, conn)
    except Exception as e:  # noqa: BLE001
        return {"module": module, "action": action, "args": args,
                "success": False, "error": str(e)}
    out = {"module": module, "action": action, "args": args,
           "success": bool(res.get("success")) and not res.get("error")}
    if res.get("error"):
        out["error"] = res["error"]
        out["note"] = ("FL's complaint is the signature answer — adjust "
                       "args and retry (start with []).")
    if res.get("result"):
        out["result"] = res["result"]
    elif res.get("success") and not res.get("error"):
        # read actions: the controller's payload dict arrives at the top
        # level of the dispatcher response — lift it through
        _ENVELOPE = ("success", "error", "state_after", "undo_saved",
                     "request_id", "protocol_version", "note")
        payload = {k: v for k, v in res.items() if k not in _ENVELOPE}
        if payload:
            out["result"] = payload
    return out


def register_ui_screen_tools(mcp) -> None:
    """Register the fl_ui_screen tool (PE-era ui/screen call layer)."""
    from fl_studio_mcp.tools.ui_screen_v2 import fl_ui_screen as _impl

    @mcp.tool()
    def fl_ui_screen(module: str, action: str,
                     args: list | None = None) -> dict:
        """Call one allowlisted FL ui.* getter (PE-era unlock; v10.4b safe set).

        Panel awareness: action="panels" -> {mixer, channel_rack, playlist,
        piano_roll, browser: visible?}; action="set_panels", args=[{"piano_roll":
        false, "mixer": false}] shows/hides them (returns the read-back).

        module: "ui" — the pure-getter subset (getProgTitle, getVersion,
        getFocused*, getHintMsg, getSnapMode, getStepEditMode,
        getVisible, is* …). "screen" is QUARANTINED (menuShowing()
        crashed FL on 2026-10-02 — EAccessViolation, side thread).
        action: the getter name. Not in the safe set → the error lists
        what IS allowed.
        args: positional arguments (JSON list). Wrong arity → FL's own
        exception text is returned — it is the signature oracle.
        Requires the v10.4b controller (ui.call action).
        """
        return _impl(module, action, args)

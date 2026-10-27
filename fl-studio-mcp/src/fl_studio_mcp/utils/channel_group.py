"""Channel rack FILTER GROUPS in one call (tip 10 of "10 things in FL Studio").

No API exists (the 50+ channels.* calls have no group function, live 2026-10-06).
Proven route, every step checked:
  1 select the channels (API)            channels.deselectAll / selectChannel
  2 focus the Channel rack (API)          ui.showWindow + ui.setFocused(widChannelRack);
                                          required: focused caption == "Channel rack"
                                          (with the piano roll focused, Alt+G went there)
  3 Alt+G (FL hotkey, FL frontmost)       -> OS window "Filter group name" (no AX tree)
  4 PASTE the name: clipboard + Cmd+V     typed keystrokes never reach FL's custom text
                                          fields, but Cmd+V DOES (live: "MCP Group|");
                                          the owner's clipboard is saved and restored
  5 OCR proof the box holds the name, then Return
  6 proof: the dialog closed and the rack's filter header shows the name
"""
from __future__ import annotations

import subprocess
import time
from typing import Any

from fl_studio_mcp.utils import custom_menu as cm

DIALOG = "Filter group name"


def _osa(script: str) -> None:
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)


def paste_text(text: str) -> None:
    """Cmd+V `text` into FL's focused text box, restoring the owner's clipboard."""
    old = subprocess.run(["pbpaste"], capture_output=True, timeout=5).stdout
    subprocess.run(["pbcopy"], input=text.encode(), timeout=5)
    try:
        _osa('tell application "System Events" to keystroke "v" using command down')
        time.sleep(0.6)
    finally:
        subprocess.run(["pbcopy"], input=old, timeout=5)


def group(conn, indices: list[int], name: str, sleep=time.sleep) -> dict[str, Any]:
    from fl_studio_mcp.tools.mixer_v2 import _exec
    from fl_studio_mcp.utils.ui_guard import ensure_ready, fl_window_titles
    out: dict[str, Any] = {"action": "group", "name": name, "indices": list(indices)}
    if not name.strip() or not indices:
        return {**out, "success": False, "error": "need channel indices and a group name"}
    ready = ensure_ready(conn, need_front=True)
    if not ready["ready"]:
        return {**out, "success": False, "error": f"FL not ready: {ready['blockers'] or ready['front']}"}
    # GLOBAL indices: a filter-group view re-indexes the channel API (live 2026-10-06)
    sel = _exec(conn, "import json, channels\nchannels.deselectAll()\n" +
                "".join(f"channels.selectChannel({int(i)}, 1, True)\n" for i in indices) +
                "print(json.dumps([channels.getChannelName(i, True) for i in range(channels.channelCount(1)) "
                "if channels.isChannelSelected(i, True)]))")
    out["selected"] = sel
    cap = _exec(conn, "import ui, midi\nui.showWindow(midi.widChannelRack)\n"
                      "ui.setFocused(midi.widChannelRack)\nprint('T=' + ui.getFocusedFormCaption())")[2:]
    sleep(0.3)
    cap = _exec(conn, "import ui\nprint('T=' + ui.getFocusedFormCaption())")[2:]
    if "channel rack" not in cap.lower():
        return {**out, "success": False, "error": f"Channel rack not focused ({cap!r}); nothing sent"}
    if not cm.require_fl_front(retry_focus=False):
        return {**out, "success": False, "error": "FL lost the front; nothing sent"}
    _osa('tell application "System Events" to keystroke "g" using option down')
    for _ in range(10):
        sleep(0.2)
        if DIALOG in fl_window_titles():
            break
    else:
        return {**out, "success": False, "error": "Alt+G did not open the group-name box"}
    if not cm.require_fl_front(retry_focus=False):
        return {**out, "success": False, "error": "FL lost the front; the group box is still open"}
    paste_text(name)
    bx = cm.ocr_boxes(cm.shot())
    lab = next((b for b in bx if DIALOG.lower() in b.text.lower()), None)
    typed = [b.text for b in bx if lab and abs(b.cy - (lab.cy - 24)) < 14 and abs(b.cx - lab.cx) < 180]
    key = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())
    if not any(key(name) in key(t) for t in typed):
        _osa('tell application "System Events" to key code 53')       # Esc: cancel the box
        return {**out, "success": False, "error": f"name not in the box (saw {typed}); cancelled"}
    _osa('tell application "System Events" to key code 36')           # Return = accept
    sleep(1.0)
    closed = DIALOG not in fl_window_titles()
    header = [b.text for b in cm.ocr_boxes(cm.shot()) if b.cy < 160]
    shown = any(key(name) in key(t) for t in header)
    # FL now shows ONLY the new group; put the rack back to "All" so every tool's
    # channel numbers stay right (the group stays selectable in the filter)
    restored = show_all_channels(conn).get("success") if closed and shown else None
    return {**out, "success": closed and shown, "dialog_closed": closed, "rack_shows_group": shown,
            "rack_back_to_all": restored,
            **({} if closed and shown else {"error": "group not confirmed on screen"})}


def rack_filtered(conn) -> tuple[int, int]:
    """(shown, total) channels: a FILTER GROUP view makes the channel API index the
    filtered list (live 2026-10-06: channelCount() 2 vs channelCount(1) 7) - every
    tool addressing channels by number would hit the wrong channel."""
    import json

    from fl_studio_mcp.tools.mixer_v2 import _exec
    shown, total = json.loads(_exec(conn, "import json, channels\n"
                                          "print(json.dumps([channels.channelCount(), channels.channelCount(1)]))"))
    return int(shown), int(total)


def show_all_channels(conn, max_steps: int = 16, sleep=time.sleep) -> dict[str, Any]:
    """Channel rack filter back to "All": focus the rack (API), then PgUp (FL's own
    "Channel display filter PgUp/PgDn" hotkey) until every channel is shown."""
    from fl_studio_mcp.tools.mixer_v2 import _exec
    shown, total = rack_filtered(conn)
    if shown == total:
        return {"action": "show_all", "success": True, "steps": 0, "channels": total}
    _exec(conn, "import ui, midi\nui.showWindow(midi.widChannelRack)\n"
                "ui.setFocused(midi.widChannelRack)\nprint('T=' + ui.getFocusedFormCaption())")
    sleep(0.3)
    for k in range(max_steps):
        if not cm.require_fl_front():
            return {"action": "show_all", "success": False, "steps": k,
                    "error": f"FL not frontmost ({cm.frontmost_app()!r}); filter left as is"}
        _osa('tell application "System Events" to key code 116')        # Page Up
        sleep(0.35)
        shown, total = rack_filtered(conn)
        if shown == total:
            return {"action": "show_all", "success": True, "steps": k + 1, "channels": total}
    return {"action": "show_all", "success": False, "steps": max_steps,
            "error": f"still {shown} of {total} channels shown"}

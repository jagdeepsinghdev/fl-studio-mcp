"""fl_channel(action="clone"): duplicate a channel through FL's own menu.

v45 has no clone API. The channel button's right-click menu has "Clone"
(live 2026-10-02: Piano roll, Graph editor, Rename…, Insert, Replace,
Patcherize, Clone, Delete…). Panel-aware like the other screen steps:
the channel rack is made visible and plugin windows closed first; the
button is found by OCR (the rack shortens long names: 'Sapphi..Melody');
the menu row is located by OCR (exact 'Clone' — never 'Delete…' next to
it); proof = one more channel; the clone is found by comparing the name lists
(FL inserts it after the source and shifts later channels), then renamed.
"""

from __future__ import annotations

import time
from typing import Any

from fl_studio_mcp.utils import custom_menu as cm
from fl_studio_mcp.utils import fl_panels as fp


def _channels(conn) -> list[dict]:
    return conn.send_command("channels.getAll").get("channels", [])


def rack_label_matches(ocr: str, name: str) -> bool:
    """The rack draws long names shortened with '..' ('Sapphi..Melody')."""
    o, n = ocr.strip().lower(), name.strip().lower()
    if o == n:
        return True
    if ".." in o:
        head, tail = o.split("..", 1)
        return bool(head) and n.startswith(head) and n.endswith(tail)
    return False


def clone_channel(conn, index: int, new_name: str = "", log=print) -> dict[str, Any]:
    chans = _channels(conn)
    src = next((c for c in chans if c.get("index") == index), None)
    if src is None:
        return {"ok": False, "error": f"no channel {index}"}
    name = src.get("name") or ""
    same = [c for c in chans if (c.get("name") or "").lower() == name.lower()]
    if len(same) > 1:
        return {"ok": False, "error": f"{len(same)} channels are named {name!r}; rename "
                                      "one first so the right button is clicked"}
    if not cm.require_fl_front():
        return {"ok": False, "error": f"FL Studio is not frontmost ({cm.frontmost_app()!r})"}
    fp.clear_plugins()
    fp.set_visible(conn, {fp.CHANNEL_RACK: True})
    btn = next((b for b in cm.ocr_boxes(cm.shot())
                if b.x < 500 and rack_label_matches(b.text, name)), None)
    if btn is None:
        return {"ok": False, "error": f"channel button '{name}' not visible in the rack "
                                      "(scrolled off?); nothing was clicked"}
    clicked = cm.menu_cascade(btn.cx, btn.cy, [["Clone"]],
                              region=(btn.x, btn.y - 200, 700, 700), log=log)
    if clicked is None:
        return {"ok": False, "error": "no 'Clone' in the channel menu (menu dismissed)"}
    after = chans
    for _ in range(12):
        time.sleep(0.25)
        after = _channels(conn)
        if len(after) > len(chans):
            break
    if len(after) <= len(chans):
        return {"ok": False, "error": "the clone did not appear in the channel list"}
    # FL inserts the clone RIGHT AFTER its source and shifts every later
    # channel down one (live 2026-10-02: picking "the index that did not
    # exist before" renamed the shifted last channel). The clone is the first
    # position where the name lists stop matching.
    before_names = [c.get("name") for c in sorted(chans, key=lambda c: c["index"])]
    after_sorted = sorted(after, key=lambda c: c["index"])
    pos = next((i for i, c in enumerate(after_sorted)
                if i >= len(before_names) or c.get("name") != before_names[i]),
               len(after_sorted) - 1)
    new = after_sorted[pos]
    if new_name:
        conn.send_command("channels.setName", {"index": new["index"], "name": new_name,
                                               "use_global": True})
        new = next(c for c in _channels(conn) if c["index"] == new["index"])
    fp.clear_plugins()      # a clone opens its editor; keep the screen clean
    log(f"cloned '{name}' -> #{new['index']} '{new.get('name')}'")
    return {"ok": True, "source": index, "index": new["index"], "name": new.get("name"),
            "channel_count": len(after)}


def delete_channel(conn, index: int, expect_name: str, log=print) -> dict[str, Any]:
    """Delete a channel through its menu ("Delete…" + FL's confirm). v45 has
    no channels.deleteChannel (live 2026-10-02: AttributeError), so
    fl_delete(target=channel) could never work. Identity first: the channel
    at `index` must be named `expect_name` (else nothing is clicked); proof =
    one channel fewer and that name gone from the list."""
    chans = _channels(conn)
    src = next((c for c in chans if c.get("index") == index), None)
    if src is None or (src.get("name") or "").lower() != (expect_name or "").lower():
        return {"ok": False, "error": f"channel {index} is {src and src.get('name')!r}, "
                                      f"not {expect_name!r}; nothing was deleted"}
    if sum((c.get("name") or "").lower() == expect_name.lower() for c in chans) > 1:
        return {"ok": False, "error": f"several channels are named {expect_name!r}; "
                                      "rename one first"}
    if not cm.require_fl_front():
        return {"ok": False, "error": f"FL Studio is not frontmost ({cm.frontmost_app()!r})"}
    fp.clear_plugins()
    fp.set_visible(conn, {fp.CHANNEL_RACK: True})
    btn = next((b for b in cm.ocr_boxes(cm.shot())
                if b.x < 500 and rack_label_matches(b.text, expect_name)), None)
    if btn is None:
        return {"ok": False, "error": f"channel button '{expect_name}' not visible; "
                                      "nothing was clicked"}
    clicked = cm.menu_cascade(btn.cx, btn.cy, [["Delete...", "Delete"]],   # OCR reads "Delete.."
                              region=(btn.x, btn.y - 200, 700, 700), log=log)
    if clicked is None:
        return {"ok": False, "error": "no 'Delete...' in the channel menu (menu dismissed)"}
    # FL's confirm (live 2026-10-02): "Confirm" / "The selected channel is
    # about to be deleted." / Ok · Cancel. Ok is only clicked when that
    # sentence is on screen, and only the Ok below it.
    msg = ok_btn = None
    for _ in range(8):
        time.sleep(0.25)
        dlg = cm.ocr_boxes(cm.shot())
        msg = next((b for b in dlg if "about to be deleted" in b.text.lower()), None)
        if msg is not None:
            ok_btn = next((b for b in dlg if b.text.strip().lower() == "ok"
                           and msg.y < b.y < msg.y + 250 and abs(b.cx - msg.cx) < 300), None)
            break
    if msg is None or ok_btn is None:
        cm.dismiss_menu()
        return {"ok": False, "error": "FL's delete confirmation did not appear; nothing deleted"}
    cm._click(ok_btn.cx, ok_btn.cy)
    after = chans
    for _ in range(12):
        time.sleep(0.25)
        after = _channels(conn)
        if len(after) < len(chans):
            break
    gone = not any((c.get("name") or "").lower() == expect_name.lower() for c in after)
    if len(after) != len(chans) - 1 or not gone:
        return {"ok": False, "error": f"the channel is still there ({len(after)} channels)"}
    log(f"deleted channel '{expect_name}'")
    return {"ok": True, "deleted": expect_name, "channel_count": len(after)}

"""Remove an effect from a mixer track slot (FL's own slot menu).

v45 has no remove-plugin API (plugins/mixer expose only mute, mix level and
colour per slot — probed 2026-10-02), and the controller's delete.fx called a
non-existent plugins.removeInsert. FL's path, live-proven 2026-10-02:
select the track -> the mixer's insert panel lists the slots -> the slot's
arrow ("FX slot N options") -> "Delete..." -> Confirm ("The selected plugin is
about to be deleted.") -> Ok -> the slot read-back must be empty.
Identity first: the slot must hold the expected plugin, or nothing is clicked.
"""

from __future__ import annotations

import time
from typing import Any

from fl_studio_mcp.utils import custom_menu as cm
from fl_studio_mcp.utils.add_effect import _exec, select_track, track_slots

ARROW_DX = -9          # slot arrow is just left of the plugin name text


def _slot_row(plugin: str, track: int, track_name: str = "", occurrence: int = 0):
    """OCR the mixer insert panel ("Mixer - <track name>") for the plugin's row.
    Matches the panel title by the track's REAL name (live 2026-10-05: a track
    renamed "Vocal" broke the old "Insert N" match); "Insert N"/"Master" fallback."""
    import re
    key = lambda t: re.sub(r"[^a-z0-9]", "", str(t).lower())
    boxes = cm.ocr_boxes(cm.shot())
    labels = {key(track_name)} if track_name else set()
    labels.add("master" if track == 0 else f"insert{track}")   # track 0 = "Mixer - Master"
    labels.discard("")
    from fl_studio_mcp.utils.add_effect import names_match
    title = next((b for b in boxes if b.text.lower().lstrip().startswith("mixer")
                  and "-" in b.text and any(names_match(b.text.split("-", 1)[1], l)
                                            for l in labels)), None)
    if title is None:
        return None, None
    want = plugin.strip().lower()
    rows = sorted((b for b in boxes if b.x >= title.x - 30 and b.y > title.y
                   and (want in b.text.lower() or key(want) in key(b.text))), key=lambda b: b.cy)
    # live 2026-10-05: two "Fruity Limiter" slots on one track -> the FIRST row was
    # taken for slot 7 (the hint check refused). Take the n-th same-named row.
    row = rows[occurrence] if len(rows) > occurrence else None
    return title, row


def remove_effect(track: int, slot: int, expect: str = "", conn=None,
                  log=print) -> dict[str, Any]:
    if conn is None:
        from fl_studio_mcp.utils.connection import get_connection
        conn = get_connection()
    lines: list[str] = []

    def _log(m):
        lines.append(m)
        log(m)

    def fail(msg, **kw):
        _log(msg)
        return {"ok": False, "error": msg, "log": lines, **kw}

    from fl_studio_mcp.utils.ui_guard import ensure_ready
    ready = ensure_ready(conn, need_front=True)          # picker/dialog/popup cleared
    if not ready["ready"]:
        return fail(f"FL not ready: {ready['blockers'] or ready['front']}")
    before = track_slots(conn, track)
    name = before[slot] if 0 <= slot < len(before) else ""
    if not name:
        return fail(f"track {track} slot {slot} is empty", slots=before)
    if expect and expect.strip().lower() not in name.lower():
        return fail(f"track {track} slot {slot} holds {name!r}, not {expect!r}; "
                    "nothing was deleted", slots=before)
    if not select_track(conn, track):
        return fail(f"could not select mixer track {track}")
    time.sleep(0.5)
    tname = _exec(conn, f"import json, mixer\nprint(json.dumps(mixer.getTrackName({int(track)})))")
    occ = sum(1 for n in before[:slot] if n.strip().lower() == name.strip().lower())
    title, row = _slot_row(name, track, tname, occ)
    if title is None:                       # mixer hidden: open it once
        cm.menu_bar_click("View", "Mixer")
        time.sleep(1.5)
        title, row = _slot_row(name, track, tname, occ)
    if row is None:
        return fail(f"'{name}' row not visible in the mixer insert panel "
                    "(mixer collapsed or covered); nothing was clicked")
    # OCR sometimes folds the arrow glyph into the box ("- Fruity Limiter"):
    # start from where the NAME begins, then a short hint-confirmed scan
    i = max(0, row.text.lower().find(name.strip().lower()[:6]))
    tx = row.x + int(row.w * i / max(1, len(row.text)))
    ay, ax, hint = row.cy, None, ""
    for dx in (0, -4, 4, -8, 8, -12):
        x = tx + ARROW_DX + dx
        hint = cm.hint_at(x, ay)
        if hint.lower().startswith(f"fx slot {slot + 1} options"):
            ax = x
            break
    if ax is None:
        return fail(f"slot arrow not confirmed near ({tx + ARROW_DX},{ay}): "
                    f"hint={hint!r}; nothing was clicked")
    cm._click(ax, ay)
    time.sleep(1.0)
    # the menu opens below the arrow for top slots but is shifted up for low
    # ones (slot 10 at y≈468): search the full-height column right of it
    mx = max(0, ax - 40)
    menu = cm.ocr_region(mx, 100, min(480, 1920 - mx), 880)
    item = cm.match_box(menu, ["Delete..."]) or cm.match_box(menu, ["Delete"])
    if item is None:
        cm.dismiss_menu()
        return fail("no 'Delete...' in the slot menu; menu dismissed")
    cm._click(item.cx, item.cy)
    time.sleep(1.2)
    dlg = cm.ocr_boxes(cm.shot())
    if not any("about to be deleted" in b.text.lower() for b in dlg):
        return fail("FL's delete confirmation did not appear")
    ok = next((b for b in dlg if b.text.strip().lower() == "ok"), None)
    if ok is None:
        return fail("confirmation 'Ok' button not found (dialog left open)")
    cm._click(ok.cx, ok.cy)
    time.sleep(1.0)
    after = track_slots(conn, track)
    if after[slot]:
        return fail(f"slot {slot} still holds {after[slot]!r}", slots=after)
    _log(f"removed {name!r} from track {track} slot {slot}")
    return {"ok": True, "track": track, "slot": slot, "removed": name,
            "slots": after, "log": lines}

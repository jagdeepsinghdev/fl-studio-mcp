"""A mixer plugin's "Plugin options" menu (the ▸ arrow left of its editor title).

Live 2026-10-06 (Patcher, PE 26.1.6): the arrow sits ~26 px left of the OCR'd title
and FL's hint bar names it "Plugin options" (the gear between them is "Detailed
settings", a toggle - not a menu). Items: Replace ▸, Delete..., Patcherize,
Patcherize all, Presets ▸, Browse presets, Save preset as..., Add to plugin
database, Display preset name..., Store in spare state, Flip with spare state,
Link all parameters..., Browse parameters, Allow threaded processing, Smart
disable, Make editor thumbnail, Rename color and icon..., Change color..., ...

Rules: the arrow is accepted ONLY when its hint says "Plugin options"; the menu is
read from its own column (zoomed tiles - dense menus drop lines in plain OCR);
the menu and the editor are ALWAYS closed again (finally), even on errors.
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable

from fl_studio_mcp.utils import custom_menu as cm

ARROW_HINT = "plugin options"


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _title(conn, track: int, slot: int, sleep: Callable):
    from fl_studio_mcp.tools.mixer_v2 import _exec
    from fl_studio_mcp.utils.plugin_preset_ui import SETTLE, find_title
    caption = _exec(conn, f"import mixer, plugins\nmixer.focusEditor({track}, {slot})\n"
                          f"print('T=' + plugins.getPluginName({track}, {slot}) + ' ('"
                          f" + mixer.getTrackName({track}) + ')')")[2:]
    sleep(SETTLE + 0.5)
    if not cm.require_fl_front():
        return None, f"FL not frontmost ({cm.frontmost_app()!r})"
    img = cm.shot()
    t = find_title(cm.ocr_boxes(img), caption, img)
    return (t, caption) if t else (None, f"editor title {caption!r} not on screen")


def _arrow(title) -> tuple[int, int] | None:
    for dx in range(-20, -40, -3):
        if ARROW_HINT in cm.hint_at(title.x + dx, title.cy, settle=0.3).lower():
            return title.x + dx, title.cy
    return None


def menu_items(img: str, title, region_w: int = 260) -> list:
    """Menu rows in the column under the arrow, zoom-read in tiles."""
    from fl_studio_mcp.utils.plugin_preset_ui import zoom_ocr
    x0, y0 = title.x - 40, title.y + title.h
    rows, ty = [], y0
    while ty < y0 + 620:
        rows += zoom_ocr(img, (x0, ty, region_w, 160), scale=3)
        ty += 130
    uniq: list = []
    for b in sorted(rows, key=lambda b: b.cy):
        if not any(_key(b.text) == _key(u.text) and abs(b.cy - u.cy) <= 10 for u in uniq):
            uniq.append(b)
    return uniq


def read_menu(conn, track: int, slot: int, submenu: str | None = None,
              sleep: Callable = time.sleep) -> dict[str, Any]:
    """Open Plugin options (and optionally hover a submenu like 'Presets'), return the
    item names. Selects NOTHING; always closes the menu and the editor."""
    from fl_studio_mcp.utils.plugin_preset_ui import close_editor, close_popups, settled_shot
    out: dict[str, Any] = {"action": "plugin_options", "track": track, "slot": slot}
    try:
        t, cap = _title(conn, track, slot, sleep)
        if t is None:
            return {**out, "success": False, "error": cap}
        a = _arrow(t)
        if a is None:
            return {**out, "success": False, "error": "no 'Plugin options' hint left of the title"}
        cm._click(*a)
        img, _ = settled_shot(sleep=sleep)
        items = menu_items(img, t)
        out["items"] = [b.text for b in items]
        if submenu:
            hit = next((b for b in items if _key(b.text).startswith(_key(submenu))), None)
            if hit is None:
                return {**out, "success": False, "error": f"no {submenu!r} item in the menu"}
            cm.move(hit.cx, hit.cy)
            sleep(1.2)
            img2, _ = settled_shot(sleep=sleep)
            from fl_studio_mcp.utils.plugin_preset_ui import zoom_ocr
            sub, ty = [], hit.y - 20
            while ty < hit.y + 600:
                sub += zoom_ocr(img2, (hit.x + 160, ty, 320, 160), scale=3)
                ty += 130
            out["submenu"] = [b.text for b in sorted(sub, key=lambda b: b.cy)]
        return {**out, "success": True}
    finally:
        close_popups(conn)
        close_editor(conn, track, slot)


def read_slot_menu(conn, track: int, slot: int, sleep: Callable = time.sleep) -> dict[str, Any]:
    """Open a mixer SLOT's own menu (the arrow on its row, hint 'FX slot N options'),
    return its items. Selects NOTHING; always closes the menu."""
    from fl_studio_mcp.utils import remove_effect as rm
    from fl_studio_mcp.utils.add_effect import _exec, select_track, track_slots
    from fl_studio_mcp.utils.plugin_preset_ui import close_popups, settled_shot, zoom_ocr
    out: dict[str, Any] = {"action": "slot_menu", "track": track, "slot": slot}
    try:
        slots = track_slots(conn, track)
        name = slots[slot] if 0 <= slot < len(slots) else ""
        if not name:
            return {**out, "success": False, "error": f"slot {slot} is empty"}
        if not select_track(conn, track):
            return {**out, "success": False, "error": f"could not select track {track}"}
        tname = _exec(conn, f"import json, mixer\nprint(json.dumps(mixer.getTrackName({int(track)})))")
        occ = sum(1 for n in slots[:slot] if n.strip().lower() == name.strip().lower())
        _, row = rm._slot_row(name, track, tname, occ)
        if row is None:
            return {**out, "success": False, "error": f"'{name}' row not on screen"}
        i = max(0, row.text.lower().find(name.strip().lower()[:6]))
        tx = row.x + int(row.w * i / max(1, len(row.text)))
        ax = next((tx + rm.ARROW_DX + d for d in (0, -4, 4, -8, 8, -12)
                   if cm.hint_at(tx + rm.ARROW_DX + d, row.cy).lower()
                   .startswith(f"fx slot {slot + 1} options")), None)
        if ax is None:
            return {**out, "success": False, "error": "slot arrow not confirmed by its hint"}
        if not cm.require_fl_front(retry_focus=False):
            return {**out, "success": False, "error": "FL not frontmost"}
        cm._click(ax, row.cy)
        img, _ = settled_shot(sleep=sleep)
        mx = max(0, ax - 40)
        rows, ty = [], 100
        while ty < 980:
            rows += zoom_ocr(img, (mx, ty, min(480, 1920 - mx), 160), scale=2)
            ty += 130
        uniq: list = []
        for b in sorted(rows, key=lambda b: b.cy):
            if not any(_key(b.text) == _key(u.text) and abs(b.cy - u.cy) <= 10 for u in uniq):
                uniq.append(b)
        return {**out, "success": True, "plugin": name, "items": [b.text for b in uniq]}
    finally:
        close_popups(conn)


def _menu_boxes(img: str, ax: int) -> list:
    from fl_studio_mcp.utils.plugin_preset_ui import zoom_ocr
    mx = max(0, ax - 40)
    rows, ty = [], 100
    while ty < 980:
        rows += zoom_ocr(img, (mx, ty, min(480, 1920 - mx), 160), scale=2)
        ty += 130
    uniq: list = []
    for b in sorted(rows, key=lambda b: b.cy):
        if not any(_key(b.text) == _key(u.text) and abs(b.cy - u.cy) <= 10 for u in uniq):
            uniq.append(b)
    return uniq


def move_slot(conn, track: int, slot: int, direction: str,
              sleep: Callable = time.sleep) -> dict[str, Any]:
    """Move a mixer slot's plugin one place up/down via the SLOT menu ('Move up' /
    'Move down', live 2026-10-06). Proven by the slot read-back (swap)."""
    from fl_studio_mcp.utils import remove_effect as rm
    from fl_studio_mcp.utils.add_effect import _exec, select_track, track_slots
    from fl_studio_mcp.utils.plugin_preset_ui import close_popups, settled_shot
    want = {"up": "moveup", "down": "movedown"}[direction]
    out: dict[str, Any] = {"action": "move_slot", "track": track, "slot": slot, "dir": direction}
    try:
        before = track_slots(conn, track)
        name = before[slot] if 0 <= slot < len(before) else ""
        if not name:
            return {**out, "success": False, "error": f"slot {slot} is empty"}
        if (direction == "up" and slot == 0) or (direction == "down" and slot == len(before) - 1):
            return {**out, "success": False, "error": "already at the edge"}
        if not select_track(conn, track):
            return {**out, "success": False, "error": f"could not select track {track}"}
        tname = _exec(conn, f"import json, mixer\nprint(json.dumps(mixer.getTrackName({int(track)})))")
        occ = sum(1 for n in before[:slot] if n.strip().lower() == name.strip().lower())
        _, row = rm._slot_row(name, track, tname, occ)
        if row is None:
            return {**out, "success": False, "error": f"'{name}' row not on screen"}
        i = max(0, row.text.lower().find(name.strip().lower()[:6]))
        tx = row.x + int(row.w * i / max(1, len(row.text)))
        ax = next((tx + rm.ARROW_DX + d for d in (0, -4, 4, -8, 8, -12)
                   if cm.hint_at(tx + rm.ARROW_DX + d, row.cy).lower()
                   .startswith(f"fx slot {slot + 1} options")), None)
        if ax is None or not cm.require_fl_front(retry_focus=False):
            return {**out, "success": False, "error": "slot arrow not confirmed / FL not front"}
        cm._click(ax, row.cy)
        img, _ = settled_shot(sleep=sleep)
        item = next((b for b in _menu_boxes(img, ax) if _key(b.text) == want), None)
        if item is None:
            return {**out, "success": False, "error": f"no '{direction}' item in the slot menu"}
        cm._click(item.cx, item.cy)
        sleep(0.8)
        after = track_slots(conn, track)
        j = slot - 1 if direction == "up" else slot + 1
        ok = after[j] == name and after[slot] == before[j]
        return {**out, "success": ok, "before": before, "after": after,
                **({} if ok else {"error": "read-back shows no swap"})}
    finally:
        close_popups(conn)


def reorder(conn, track: int, wanted: list[str], log: Callable = lambda m: None) -> dict:
    """Bring the plugins named in `wanted` (recipe order) to slots 0..n-1 with verified
    'Move up' steps (selection sort; nth occurrence for repeated names)."""
    from fl_studio_mcp.utils.add_effect import track_slots
    moves = 0
    for i, name in enumerate(wanted):
        slots = track_slots(conn, track)
        # the occurrence of `name` that belongs at position i = first one at/after i
        j = next((k for k in range(i, len(slots))
                  if slots[k].strip().lower() == name.strip().lower()), None)
        if j is None:
            return {"action": "reorder", "success": False, "moves": moves,
                    "error": f"'{name}' not found at or after slot {i}"}
        while j > i:
            r = move_slot(conn, track, j, "up")
            if not r.get("success"):
                return {"action": "reorder", "success": False, "moves": moves,
                        "error": f"move {name!r} {j}->{j-1}: {r.get('error')}"}
            moves += 1
            j -= 1
            log(f"moved {name} to slot {j}")
    return {"action": "reorder", "success": True, "moves": moves,
            "slots": track_slots(conn, track)}

"""Pick a plugin preset BY NAME from the plugin window's own preset menu (UI + OCR).

Why: the API route (plugins.nextPreset + FPN_Preset name) fails for Maximus (no
names via FPN_Preset) and is dangerous for Patcher (each step is a heavy async
patch load; live 2026-10-05 it queued ~350 loads and froze the controller for
minutes). FL's wrapper header shows the current preset name; clicking it opens
the full, categorised preset menu (verified live 2026-10-05 on Maximus: groups
"De-essing", "Mastering", "Soundgoodizer presets" a/b/c/d, ...).

One call, ~3-4 s, no manual steps:
  1. mixer.focusEditor(track, slot) via probe.exec (no click) + focused caption
  2. screenshot + OCR -> the editor's title row ("Maximus (Vocal)"); if several
     editors share the title, the FOCUSED one is the brightest title text
  3. click the preset label on that row (the first text right of the title)
  4. OCR the menu, click the exact item (case/space/punct-insensitive), never a
     guess: 0 or >1 matches -> Escape, refuse, list what was seen
  5. re-OCR the header row: proof that the preset name changed
Every click/key first checks FL is frontmost (cm.require_fl_front).
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Callable

from fl_studio_mcp.utils import custom_menu as cm

ROW_TOL = 7          # px: boxes on the same header row
SETTLE = 0.8


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _brightness(img: str, b: cm.Box) -> float:
    """Mean luminance of the box (focused FL window titles are drawn brighter)."""
    try:
        import Quartz
        from Foundation import NSURL
        src = Quartz.CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(img), None)
        im = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
        crop = Quartz.CGImageCreateWithImageInRect(im, Quartz.CGRectMake(b.x, b.y, b.w, b.h))
        data = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(crop))
        bpr, bpp = Quartz.CGImageGetBytesPerRow(crop), Quartz.CGImageGetBitsPerPixel(crop) // 8
        raw = bytes(data)
        tot = n = 0
        for yy in range(Quartz.CGImageGetHeight(crop)):
            row = raw[yy * bpr: yy * bpr + Quartz.CGImageGetWidth(crop) * bpp]
            for i in range(0, len(row) - 2, bpp * 2):          # every other pixel is plenty
                tot += row[i] + row[i + 1] + row[i + 2]
                n += 3
        return tot / max(n, 1)
    except Exception:
        return 0.0


def find_title(boxes: list[cm.Box], caption: str, img: str | None = None) -> cm.Box | None:
    k = _key(caption)
    hits = [b for b in boxes if k and k in _key(b.text)]
    if len(hits) <= 1 or img is None:
        return hits[0] if hits else None
    return max(hits, key=lambda b: _brightness(img, b))


#: the window-control glyphs (- □ ×) sit in the last ~70 px of an editor's title row
CONTROLS_W = 70


def _screen_w() -> int:
    try:        # CoreGraphics, NOT AppKit (AppKit made Python a focus-stealing app)
        import Quartz
        return int(Quartz.CGDisplayBounds(Quartz.CGMainDisplayID()).size.width)
    except Exception:
        return 1920


def preset_label(boxes: list[cm.Box], title: cm.Box) -> cm.Box | None:
    """First real text right of the title on its row. Live 2026-10-05: a MAXIMISED
    editor put the preset name at the far right and the window buttons ('- •',
    '• x') were read as the label -> skip glyph-only boxes and the control strip."""
    edge = _screen_w() - CONTROLS_W
    row = [b for b in boxes if abs(b.cy - title.cy) <= ROW_TOL and b.x > title.x + title.w + 40
           and b.x < edge and re.search(r"[A-Za-z0-9]{1,}", b.text.replace("x", "", 0))
           and _key(b.text) not in ("x", "")]
    return min(row, key=lambda b: b.x) if row else None


def pick_menu_item(before: list[cm.Box], after: list[cm.Box], preset: str) -> tuple[cm.Box | None, list[str]]:
    """Exact (normalised) match among the boxes that appeared with the menu."""
    old = {(b.text, b.cx, b.cy) for b in before}
    menu = [b for b in after if (b.text, b.cx, b.cy) not in old]
    want = _key(preset)
    exact = [b for b in menu if _key(b.text) == want]
    seen = [b.text for b in menu][:80]
    return (exact[0] if len(exact) == 1 else None), seen


def zoom_ocr(img: str, region: tuple[int, int, int, int], scale: int = 3) -> list[cm.Box]:
    """OCR a region enlarged `scale`x and map boxes back to screen coords. Vision
    OCR skips lone short items ("a" .. "d" in Maximus' Soundgoodizer group, live
    2026-10-05); at 3x they read fine."""
    import subprocess
    import tempfile
    x, y, w, h = (max(0, int(v)) for v in region)
    out = tempfile.mktemp(suffix=".png")
    subprocess.run(["sips", "-c", str(h), str(w), "--cropOffset", str(y), str(x), img,
                    "--out", out], capture_output=True, timeout=20)
    subprocess.run(["sips", "-z", str(h * scale), str(w * scale), out], capture_output=True,
                   timeout=20)
    return [cm.Box(x + b.x // scale, y + b.y // scale, max(1, b.w // scale),
                   max(1, b.h // scale), b.text) for b in cm.ocr_boxes(out)]


def close_popups(conn, sleep: Callable = time.sleep) -> bool:
    """Close any open FL popup menu IN-ENGINE and prove it (ui.isInPopupMenu == 0).
    Live 2026-10-05: Escape did NOT close the preset menu; the leftover menu then
    overlapped the editor title row and the next run read a MENU ITEM as the
    preset label and clicked it ('1 band drums limiter' got selected)."""
    from fl_studio_mcp.tools.mixer_v2 import _exec
    for _ in range(3):
        if str(_exec(conn, "import ui\nprint(int(ui.isInPopupMenu()))")).strip() == "0":
            return True
        _exec(conn, "import ui\nui.closeActivePopupMenu()\nprint('ok')")
        sleep(0.3)
    return str(_exec(conn, "import ui\nprint(int(ui.isInPopupMenu()))")).strip() == "0"


def zoom_row(img: str, title: cm.Box) -> list[cm.Box]:
    """OCR the header row right of the title, zoomed. Live 2026-10-05: a bare 'a'
    reads only with ~8 px padding above/below at 3x (8 px total padding read nothing)."""
    x0 = title.x + title.w + 40
    width = max(80, _screen_w() - CONTROLS_W - x0)       # the WHOLE row (maximised editors)
    for scale, pad in ((3, 16), (4, 24)):
        z = [b for b in zoom_ocr(img, (x0, title.y - pad // 2, width, title.h + pad), scale=scale)
             if _key(b.text) not in ("x", "")]
        if z:
            return z
    return []


FINGERPRINTS = Path(__file__).resolve().parents[3] / "presets" / "vocal" / "knobs" / "preset_fingerprints.json"


def _params(conn, track: int, slot: int) -> dict[str, float]:
    from fl_studio_mcp.tools.plugin_v2 import _list_params
    return {f"{p['index']}:{p.get('name')}": round(float(p.get("value", 0.0)), 4)
            for p in _list_params(conn, track, slot)
            if _key(p.get("name")) not in ("", "notused")}


def record_fingerprint(conn, track: int, slot: int, plugin: str, preset: str) -> dict:
    """Save the knob values of a preset the owner/agent CONFIRMED on screen.
    Used to verify presets whose names OCR cannot read (Maximus 'a', 2026-10-05)."""
    import json
    data = json.loads(FINGERPRINTS.read_text()) if FINGERPRINTS.exists() else {}
    data.setdefault(_key(plugin), {})[_key(preset)] = _params(conn, track, slot)
    FINGERPRINTS.parent.mkdir(parents=True, exist_ok=True)
    FINGERPRINTS.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    return {"plugin": plugin, "preset": preset, "knobs": len(data[_key(plugin)][_key(preset)])}


def matches_fingerprint(conn, track: int, slot: int, plugin: str, preset: str) -> bool | None:
    """True/False against a stored fingerprint; None when there is none."""
    import json
    if not FINGERPRINTS.exists():
        return None
    fp = json.loads(FINGERPRINTS.read_text()).get(_key(plugin), {}).get(_key(preset))
    if not fp:
        return None
    now = _params(conn, track, slot)
    same = sum(1 for k, v in fp.items() if k in now and abs(now[k] - v) <= 0.01)
    return same >= 0.95 * len(fp)


def settled_shot(timeout: float = 4.0, sleep: Callable = time.sleep):
    """Screenshot + OCR once the screen STOPS changing (two reads with the same item
    count). Patcher's 4-column preset menu draws slowly and variably (owner +
    live 2026-10-06); a fixed delay sometimes read a half-drawn menu."""
    sleep(SETTLE)
    img = cm.shot()
    boxes = cm.ocr_boxes(img)
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        sleep(0.4)
        img2 = cm.shot()
        b2 = cm.ocr_boxes(img2)
        if abs(len(b2) - len(boxes)) <= 1:
            return img2, b2
        img, boxes = img2, b2
    return img, boxes


def close_editor(conn, track: int, slot: int) -> None:
    """Close a plugin editor in-engine: focus it, then ui.escape (live 2026-10-05:
    the window's title disappeared from the screen; Escape needs no mouse/front).
    Every tool that opens an editor (mixer.focusEditor) closes it again - the owner
    found 3-4 leftover editor windows covering the screen."""
    from fl_studio_mcp.tools.mixer_v2 import _exec
    try:
        _exec(conn, f"import mixer, ui\nmixer.focusEditor({int(track)}, {int(slot)})\n"
                    "ui.escape()\nprint(1)")
    except Exception:
        pass


def pick_preset_ui(conn, track: int, slot: int, preset: str, log: Callable = lambda m: None,
                   sleep: Callable = time.sleep) -> dict[str, Any]:
    try:
        return _pick_preset_ui(conn, track, slot, preset, log, sleep)
    finally:
        close_editor(conn, track, slot)


def _pick_preset_ui(conn, track: int, slot: int, preset: str, log: Callable = lambda m: None,
                   sleep: Callable = time.sleep) -> dict[str, Any]:
    from fl_studio_mcp.tools.mixer_v2 import _exec
    out: dict[str, Any] = {"action": "preset_ui", "track": track, "slot": slot, "preset": preset}
    group, _, item_name = preset.rpartition("/")       # "Soundgoodizer presets/a"
    preset = item_name.strip() or preset
    from fl_studio_mcp.utils.ui_guard import ensure_ready
    ready = ensure_ready(conn)                            # picker/dialog/busy cleared
    if not ready["ready"]:
        return {**out, "success": False, "error": f"FL not ready: {ready['blockers']}"}
    if not close_popups(conn):
        return {**out, "success": False, "error": "an FL popup menu is open and would not close"}
    # the editor title FL draws = "<plugin> (<track name>)". Built from the API, not
    # ui.getFocusedFormCaption (live: it came back EMPTY once focus had moved).
    caption = _exec(conn, f"import mixer, plugins\nmixer.focusEditor({track}, {slot})\n"
                          f"print('T=' + plugins.getPluginName({track}, {slot}) + ' ('"
                          f" + mixer.getTrackName({track}) + ')')")[2:]
    out["editor"] = caption
    sleep(SETTLE)
    if not cm.require_fl_front():
        return {**out, "success": False, "error": f"FL not frontmost ({cm.frontmost_app()!r})"}
    img = cm.shot()
    boxes = cm.ocr_boxes(img)
    title = find_title(boxes, caption, img)
    if title is None:
        return {**out, "success": False, "error": f"editor title {caption!r} not found on screen"}
    plugin = caption.split(" (")[0]
    if matches_fingerprint(conn, track, slot, plugin, preset):
        return {**out, "success": True, "after": preset, "note": "already selected (knob fingerprint)"}
    label = preset_label(boxes, title)
    if label is None:                 # a 1-3 letter preset name ("a"): zoom the row
        z = zoom_row(img, title)
        label = min(z, key=lambda b: b.x) if z else None
    if label is None:
        return {**out, "success": False, "error": "no preset label on the editor's title row"}
    out["before"] = label.text
    if _key(label.text) == _key(preset):
        return {**out, "success": True, "after": label.text, "note": "already selected"}
    cm._click(label.cx, label.cy)
    img_menu, after = settled_shot(sleep=sleep)
    item, seen = pick_menu_item(boxes, after, preset)
    if item is None:
        # live 2026-10-05: Patcher's big preset menu was OCR'd before FL finished
        # drawing it inside a setup run; the same call alone found the item.
        sleep(SETTLE)
        img_menu = cm.shot()
        after = cm.ocr_boxes(img_menu)
        item, seen = pick_menu_item(boxes, after, preset)
    if item is None:
        # zoom EVERY menu column on its own strip. Live 2026-10-05: Patcher's preset
        # menu has 4 columns and Vision OCR dropped 'Intelligent Deesser' (read only
        # 'LITE'); the old fallback zoomed column 1 only. Short items ('a') and grey
        # group headers also only read zoomed.
        from collections import Counter
        old = {(b.text, b.cx, b.cy) for b in boxes}
        menu = [b for b in after if (b.text, b.cx, b.cy) not in old]
        counts = Counter(b.x // 4 * 4 for b in menu)
        # a REAL column = >= 5 rows starting at the same x (live: four '... LITE'
        # fragments at x=1292 made a fake column; real columns had 5-44 rows and sit
        # only 120 px apart, so the gap rule must stay small)
        cols = sorted(x for x, n in counts.items() if n >= 5)
        merged: list[int] = []
        for x in cols:
            if not merged or x - merged[-1] > 60:
                merged.append(x)
        found: list[cm.Box] = []
        group_rows: list[cm.Box] = []
        for i, colx in enumerate(merged):
            nxt = merged[i + 1] if i + 1 < len(merged) else 10_000
            col = [b for b in menu if colx - 10 <= b.x < nxt - 10]
            if not col:
                continue
            width = (merged[i + 1] - colx) if i + 1 < len(merged) else 240
            y0, y1 = min(b.y for b in col) - 30, max(b.y + b.h for b in col) + 30
            # TILES ~150 px tall with overlap: one tall zoomed strip made Vision skip
            # lines (live: a 930 px strip missed 'Intelligent Deesser', 100 px read it)
            z, ty = [], y0
            while ty < y1:
                z += zoom_ocr(img_menu, (colx - 20, ty, width + 10, min(160, y1 - ty)), scale=3)
                ty += 130
            uniq: list[cm.Box] = []
            for b in z:                       # overlap rows are read twice: keep one
                if not any(_key(b.text) == _key(u.text) and abs(b.cy - u.cy) <= 10 for u in uniq):
                    uniq.append(b)
            z = uniq
            exact = sorted((b for b in z if _key(b.text) == _key(preset)), key=lambda b: b.cy)
            if group.strip():
                # the grey group header narrows the match when OCR reads it; when it
                # does not (live 2026-10-06: Maximus 'a' lost), keep the exact hits
                hdr = [b for b in z if _key(group) in _key(b.text)]
                if hdr:
                    exact = [b for b in exact if b.cy > hdr[0].cy][:1]
                    under = sorted((b for b in z if b.cy > hdr[0].cy + 4), key=lambda b: b.cy)
                    group_rows = group_rows or under[:6]
            found += exact
            seen = seen + [f"(zoom col {i + 1}) {b.text}" for b in z
                           if len(_key(b.text)) <= 3 or (group and _key(group) in _key(b.text))][:10]
        # one item read in two overlapping tiles = ONE match (within a few px)
        dedup: list[cm.Box] = []
        for b in sorted(found, key=lambda b: (b.cx, b.cy)):
            if not any(abs(b.cy - d.cy) <= 10 and abs(b.cx - d.cx) <= 40 for d in dedup):
                dedup.append(b)
        if len(dedup) == 1:
            item = dedup[0]
        elif len(dedup) > 1:
            seen = seen + [f"(ambiguous) {b.text} @({b.cx},{b.cy})" for b in dedup]
    if item is None and group.strip() and group_rows and \
            matches_fingerprint(conn, track, slot, plugin, preset) is not None:
        # OCR found the group but not the short item (live 2026-10-06: 'a' read as
        # 'e'). Try the rows under the group header in order; FL's own knob values
        # (fingerprint) prove which one is right. No fingerprint -> refuse below.
        for cand in group_rows:
            if not cm.require_fl_front(retry_focus=False):
                break
            cm._click(cand.cx, cand.cy)
            sleep(SETTLE + 0.4)
            close_popups(conn)
            if matches_fingerprint(conn, track, slot, plugin, preset):
                return {**out, "success": True, "after": preset,
                        "via_fingerprint": True, "row_text": cand.text}
            cm._click(label.cx, label.cy)            # reopen the menu for the next row
            settled_shot(sleep=sleep)
    if item is None:
        close_popups(conn)            # in-engine; Escape does not close this menu
        return {**out, "success": False, "menu_items": seen,
                "error": f"no unique menu item {preset!r} (see menu_items for exact names)"}
    if not cm.require_fl_front(retry_focus=False):
        return {**out, "success": False, "error": "FL lost focus before the item click"}
    cm._click(item.cx, item.cy)
    sleep(SETTLE + 0.4)
    close_popups(conn)                # a missed click must never leave the menu up
    img2 = cm.shot()
    boxes2 = cm.ocr_boxes(img2)
    t2 = find_title(boxes2, caption, img2) or title
    lab2 = preset_label(boxes2, t2)
    out["after"] = lab2.text if lab2 else None
    if matches_fingerprint(conn, track, slot, plugin, preset):      # API proof first
        return {**out, "success": True, "after": preset, "via_fingerprint": True}
    got = _key(lab2.text) if lab2 else ""
    want = _key(preset)
    if got != want and len(want) <= 3:          # short names: zoom the header row
        z = zoom_row(img2, t2)
        if any(_key(b.text) == want for b in z):
            lab2 = next(b for b in z if _key(b.text) == want)
            got = want
            out["after"] = lab2.text
    ok = bool(lab2) and (got == want if len(want) <= 3 else want in got)
    return {**out, "success": ok,
            **({} if ok else {"error": f"header shows {out['after']!r} after the click"})}


def list_presets_ui(conn, track: int, slot: int, sleep: Callable = time.sleep) -> dict[str, Any]:
    try:
        return _list_presets_ui(conn, track, slot, sleep)
    finally:
        close_editor(conn, track, slot)


def _list_presets_ui(conn, track: int, slot: int, sleep: Callable = time.sleep) -> dict[str, Any]:
    """Read a plugin's preset MENU (names only; nothing is selected). Used by
    plugin onboarding (fl_vocal onboard). Opens the menu like pick_preset_ui, OCRs the
    menu's own column, closes it in-engine (Escape does not close it)."""
    from collections import Counter

    from fl_studio_mcp.tools.mixer_v2 import _exec
    from fl_studio_mcp.utils.ui_guard import ensure_ready
    out: dict[str, Any] = {"action": "list_presets", "track": track, "slot": slot}
    if not ensure_ready(conn)["ready"] or not close_popups(conn):
        return {**out, "success": False, "error": "FL not ready / a popup would not close"}
    caption = _exec(conn, f"import mixer, plugins\nmixer.focusEditor({track}, {slot})\n"
                          f"print('T=' + plugins.getPluginName({track}, {slot}) + ' ('"
                          f" + mixer.getTrackName({track}) + ')')")[2:]
    sleep(SETTLE)
    if not cm.require_fl_front():
        return {**out, "success": False, "error": f"FL not frontmost ({cm.frontmost_app()!r})"}
    img = cm.shot()
    boxes = cm.ocr_boxes(img)
    title = find_title(boxes, caption, img)
    if title is None:
        return {**out, "success": False, "error": f"editor title {caption!r} not on screen"}
    label = preset_label(boxes, title)
    if label is None:
        z = zoom_row(img, title)
        label = min(z, key=lambda b: b.x) if z else None
    if label is None:
        return {**out, "success": False, "error": "no preset label on the editor's title row"}
    cm._click(label.cx, label.cy)
    sleep(SETTLE)
    after = cm.ocr_boxes(cm.shot())
    close_popups(conn)
    old = {(b.text, b.cx, b.cy) for b in boxes}
    menu = [b for b in after if (b.text, b.cx, b.cy) not in old]
    if not menu:
        return {**out, "success": False, "error": "the preset menu did not open"}
    colx = Counter(b.x // 4 * 4 for b in menu).most_common(1)[0][0]
    names = [b.text.strip() for b in sorted(menu, key=lambda b: b.cy)
             if abs(b.x - colx) <= 8 and b.text.strip()]
    return {**out, "success": True, "plugin": caption.split(" (")[0], "current": label.text,
            "presets": names}


INDEX_CACHE = Path(__file__).resolve().parents[3] / "presets" / "vocal" / "knobs" / "preset_menu_index.json"


def _open_preset_menu(conn, track: int, slot: int, sleep: Callable) -> tuple[bool, str]:
    """Focus the editor, click its preset label, prove the popup is open (API)."""
    from fl_studio_mcp.tools.mixer_v2 import _exec
    if not close_popups(conn):
        return False, "a popup would not close"
    caption = _exec(conn, f"import mixer, plugins\nmixer.focusEditor({track}, {slot})\n"
                          f"print('T=' + plugins.getPluginName({track}, {slot}) + ' ('"
                          f" + mixer.getTrackName({track}) + ')')")[2:]
    sleep(SETTLE)
    if not cm.require_fl_front():
        return False, f"FL not frontmost ({cm.frontmost_app()!r})"
    img = cm.shot()
    boxes = cm.ocr_boxes(img)
    title = find_title(boxes, caption, img)
    if title is None:
        return False, f"editor title {caption!r} not on screen"
    label = preset_label(boxes, title)
    if label is None:
        z = zoom_row(img, title)
        label = min(z, key=lambda b: b.x) if z else None
    if label is None:
        return False, "no preset label on the editor's title row"
    cm._click(label.cx, label.cy)
    sleep(SETTLE)
    if str(_exec(conn, "import ui\nprint(int(ui.isInPopupMenu()))")).strip() != "1":
        return False, "the preset menu did not open (isInPopupMenu = 0)"
    return True, caption.split(" (")[0]


def pick_preset_by_keys(conn, track: int, slot: int, preset: str, index: int,
                        spread: int = 2, sleep: Callable = time.sleep) -> dict[str, Any]:
    """Select a preset by its POSITION in the plugin's preset menu with in-engine keys:
    open the menu, `ui.down` x index + `ui.enter` in ONE trip, prove it with the knob
    fingerprint. Tries index, then index±1..±spread; remembers the index that worked.
    For names OCR cannot read (live 2026-10-06: Maximus 'a' read as 'e'). Requires a
    fingerprint: without one there is no proof, so it refuses."""
    import json

    from fl_studio_mcp.tools.mixer_v2 import _exec
    out: dict[str, Any] = {"action": "preset_keys", "track": track, "slot": slot, "preset": preset}
    name = preset.rpartition("/")[2].strip() or preset
    try:
        plugin = _exec(conn, f"import plugins\nprint('T=' + plugins.getPluginName({track}, {slot}))")[2:]
        if matches_fingerprint(conn, track, slot, plugin, name) is None:
            return {**out, "success": False, "error": f"no knob fingerprint for {plugin} '{name}': no proof"}
        if matches_fingerprint(conn, track, slot, plugin, name):
            return {**out, "success": True, "note": "already selected (knob fingerprint)"}
        tries = [index] + [index + d for k in range(1, spread + 1) for d in (-k, k)]
        for n in tries:
            if n < 1:
                continue
            ok, info = _open_preset_menu(conn, track, slot, sleep)
            if not ok:
                return {**out, "success": False, "error": info}
            _exec(conn, f"import ui\nfor _ in range({n}): ui.down()\nui.enter()\nprint(1)")
            sleep(SETTLE + 0.4)
            close_popups(conn)
            if matches_fingerprint(conn, track, slot, plugin, name):
                data = json.loads(INDEX_CACHE.read_text()) if INDEX_CACHE.exists() else {}
                data.setdefault(_key(plugin), {})[_key(name)] = n
                INDEX_CACHE.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
                return {**out, "success": True, "index": n, "via": "keys + fingerprint"}
        return {**out, "success": False, "error": f"no menu position in {tries} matched the fingerprint"}
    finally:
        close_popups(conn)
        close_editor(conn, track, slot)


def restore_fingerprint(conn, track: int, slot: int, plugin: str, preset: str) -> dict[str, Any]:
    """Apply a stored knob snapshot through FL's API in ONE trip, then prove it.
    No menu, no OCR, no mouse (2026-10-06: Maximus 'a' could not be picked from its
    menu - unreadable 1-letter label, maximised editor). The snapshot IS the preset
    for plugins whose state lives in their params (Maximus, Limiter, EQ ...); NOT for
    Patcher (its patch is not params) - use the menu route there."""
    import json

    from fl_studio_mcp.tools.mixer_v2 import _exec
    if not FINGERPRINTS.exists():
        return {"success": False, "error": "no fingerprints stored"}
    fp = json.loads(FINGERPRINTS.read_text()).get(_key(plugin), {}).get(_key(preset))
    if not fp:
        return {"success": False, "error": f"no snapshot for {plugin} '{preset}'"}
    pairs = [[int(k.split(":", 1)[0]), float(v)] for k, v in fp.items()]
    _exec(conn, "import plugins, midi\n"
                f"for i, v in {pairs}:\n"
                f"    plugins.setParamValue(v, i, {int(track)}, {int(slot)}, midi.PIM_None, True)\n"
                "print(1)")
    time.sleep(0.3)
    ok = bool(matches_fingerprint(conn, track, slot, plugin, preset))
    return {"action": "preset_snapshot", "success": ok, "track": track, "slot": slot,
            "plugin": plugin, "preset": preset, "knobs": len(pairs), "via": "API snapshot",
            **({} if ok else {"error": "read-back does not match the snapshot"})}

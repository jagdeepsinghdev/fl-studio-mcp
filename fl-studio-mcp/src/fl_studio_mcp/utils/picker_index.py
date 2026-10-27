"""Select a plugin in FL's "Select effect plugin" picker BY INDEX with in-engine keys.

Why (live 2026-10-05): after an FL restart the picker opened 975 px tall, FL ignored
the resize, and its bottom (the Find field) sat under the macOS Dock; plugins below
the first screen (Maximus, Patcher, Pitcher, Reeverb 2) could not be reached by OCR.
Proven the same day: while the picker is open FL still answers probe.exec, the
focused form is "Select effect plugin", and `ui.down` x3 from a fresh picker
highlighted the 3rd row (Edison). So: N downs = row N (1-based).

The ORDER comes from the picker itself (FL's plugin-database folders do not match it:
79 / 228 entries vs the picker's 114): page through with `ui.down`, OCR the Name
column, merge, cache in .generated/picker_order.json.

Never confirms blind: after the downs, the highlighted row (blue background, read
with Quartz) must name the wanted plugin; one correction from the cached order,
else refuse. Confirm = in-engine `ui.enter`; the caller's slot read-back proves it.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from fl_studio_mcp.utils import custom_menu as cm

PICKER = "Select effect plugin"
CACHE = Path(__file__).resolve().parents[3] / ".generated" / "picker_order.json"


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


_OCR = str.maketrans({"q": "o", "0": "o"})   # live: 'EQ2' read as 'E02' / 'EU2'


def _pk(s: str) -> str:
    """Picker key: alnum lowercase with OCR's usual confusions folded (Q/0 -> o)."""
    return _key(s).translate(_OCR)


def _similar(a: str, b: str) -> float:
    import difflib
    return difflib.SequenceMatcher(None, _pk(a), _pk(b)).ratio()


def _match(a: str, b: str) -> bool:
    """Same plugin name despite OCR slips; digits must still agree ('Delay 2' != 3)."""
    pa, pb = _pk(a), _pk(b)
    if not pa or not pb:
        return False
    if re.findall(r"\d+", pa) != re.findall(r"\d+", pb):
        return False
    return pa == pb or _similar(a, b) >= 0.9


def _keys(conn, key: str, n: int) -> None:
    """n in-engine key presses (ui.down / ui.up) in ONE trip."""
    from fl_studio_mcp.utils.add_effect import _exec
    if n > 0:
        _exec(conn, f"import json, ui\nfor _ in range({int(n)}): ui.{key}()\nprint(json.dumps(1))")


def visible_bottom() -> int:
    """Lowest screen y not covered by the Dock (top-left coords).
    Live 2026-10-05: rows read under the Dock came back as junk ('Kelan', ...).
    2026-10-06: NOT via AppKit NSScreen — importing AppKit turned our Python into a
    GUI app (Dock rocket icon 'Python') that could steal focus from FL. The Dock's
    own position comes from System Events; the screen height from CoreGraphics."""
    import subprocess
    try:
        import Quartz
        screen_h = int(Quartz.CGDisplayBounds(Quartz.CGMainDisplayID()).size.height)
    except Exception:
        screen_h = 10_000
    try:
        out = subprocess.run(["osascript", "-e", 'tell application "System Events" to tell '
                              'process "Dock" to get position of list 1'],
                             capture_output=True, text=True, timeout=5).stdout
        x, y = (int(float(v)) for v in out.strip().split(","))
        return y if screen_h // 2 < y < screen_h else screen_h   # bottom Dock only
    except Exception:
        return screen_h


def name_rows(img: str, win: tuple[int, int, int, int]) -> list[cm.Box]:
    """OCR boxes of the picker's Name column, top to bottom (above the Dock)."""
    x, y, w, h = win
    h = min(h, visible_bottom() - y - 12)
    rows = [b for b in cm.ocr_boxes(img)
            if x + 25 <= b.x <= x + int(w * 0.40) and y + 50 <= b.cy <= y + h - 10
            and b.text.strip() and b.text.strip().lower() not in ("name", "f")]
    return sorted(rows, key=lambda b: b.cy)


def _is_blue(img: str, px: int, py: int) -> bool:
    try:
        import Quartz
        from Foundation import NSURL
        src = Quartz.CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(img), None)
        im = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
        crop = Quartz.CGImageCreateWithImageInRect(im, Quartz.CGRectMake(px, py, 1, 1))
        raw = bytes(Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(crop)))
        b0, b1, b2 = raw[0], raw[1], raw[2]         # BGRA or RGBA: blue is the outlier
        hi, lo = max(b0, b2), min(b0, b2)
        return hi > 140 and hi - lo > 70 and hi - b1 > 30
    except Exception:
        return False


def highlighted(img: str, win: tuple[int, int, int, int]) -> str | None:
    """Name of the highlighted (blue) row, or None."""
    x = win[0] + 14                                   # left margin inside the list
    for b in name_rows(img, win):
        if _is_blue(img, x, b.cy):
            return b.text.strip()
    return None


def _same_row(a: str, b: str) -> bool:
    """Two OCR reads of the SAME row (digits agree, >= 80 % similar)."""
    if re.findall(r"\d+", _pk(a)) != re.findall(r"\d+", _pk(b)):
        return False
    return _pk(a) == _pk(b) or _similar(a, b) >= 0.8


def wrapped(order: list[str], rows: list[str]) -> bool:
    """The new page shares no overlap with the END of `order`, yet most of its rows
    are already known -> the selection wrapped to the top of the list."""
    if len(order) < 10 or not rows:
        return False
    if merge(order, rows) != order + rows:          # a real overlap -> not wrapped
        return False
    known = sum(any(_match(r, o) for o in order) for r in rows)
    return known >= 0.6 * len(rows)


def merge(order: list[str], rows: list[str]) -> list[str]:
    """Append a new page, skipping only the OVERLAP: the longest suffix of `order`
    that matches a prefix of `rows` row-by-row. Live 2026-10-05: a global
    'similar name' filter dropped real neighbours (Pitcher/Patcher, Delay 2/3) and a
    plain exact filter re-added misreads ('truity Parametric EU2')."""
    # tolerate a misread row inside the overlap (live: a strict row-by-row check
    # missed one overlap and re-appended a whole page: 143 names for 114 effects)
    for k in range(min(len(order), len(rows)), 0, -1):
        hits = sum(_same_row(order[-k + i], rows[i]) for i in range(k))
        if hits == k or (k >= 3 and hits >= 0.8 * k):
            return order + rows[k:]
    return order + rows


def build_order(conn, win: tuple[int, int, int, int], log: Callable = lambda m: None,
                sleep: Callable = time.sleep) -> list[str]:
    """Page through the open picker with ui.down and OCR every name, in order."""
    order: list[str] = []
    rows = name_rows(cm.shot(), win)
    page = max(5, len(rows) - 3)
    stale = 0
    _keys(conn, "down", 1)
    for _ in range(12):
        sleep(0.4)
        new = 0
        rows = [b.text.strip() for b in name_rows(cm.shot(), win)]
        if wrapped(order, rows):
            # live 2026-10-05: ui.down WRAPS from the last row to the first; without
            # this the list was re-appended per lap (296 names, Pitcher x5)
            log("picker list wrapped to the top: order complete")
            break
        before = len(order)
        order[:] = merge(order, rows)
        new = len(order) - before
        stale = stale + 1 if new == 0 else 0
        if stale >= 2:
            break
        _keys(conn, "down", page)
    log(f"picker order: {len(order)} names")
    return order


def load_cache() -> list[str]:
    try:
        return list(json.loads(CACHE.read_text()).get("order") or [])
    except Exception:
        return []


def save_cache(order: list[str]) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"order": order, "built": time.strftime("%Y-%m-%d %H:%M")},
                                indent=1) + "\n")


def select_by_index(conn, name: str, order: list[str], log: Callable = lambda m: None,
                    sleep: Callable = time.sleep) -> dict[str, Any]:
    """Picker must be OPEN with nothing selected. Highlight `name`, verify, Enter."""
    from fl_studio_mcp.utils.add_effect import _exec
    win = cm.window_by_name(PICKER)
    if win is None:
        return {"ok": False, "error": "picker not open"}
    idx = next((i for i, o in enumerate(order) if _match(o, name)), None)
    if idx is None:
        return {"ok": False, "error": f"{name!r} not in the cached picker order", "stale": True}
    _keys(conn, "down", idx + 1)
    for attempt in range(2):
        sleep(0.5)
        img = cm.shot()
        hl = highlighted(img, win)
        log(f"after downs: highlighted {hl!r} (want {name!r})")
        if hl is not None and _match(hl, name):
            _exec(conn, "import json, ui\nui.enter()\nprint(json.dumps(1))")
            sleep(1.5)
            return {"ok": True, "index": idx, "highlighted": hl}
        if hl is None or attempt == 1:
            break
        cur = next((i for i, o in enumerate(order) if _match(o, hl)), None)
        if cur is None:
            break
        delta = idx - cur
        _keys(conn, "down" if delta > 0 else "up", abs(delta))
    return {"ok": False, "error": f"highlight did not reach {name!r} (saw {hl!r})", "stale": True}

"""fl_select_script — automate the piano-roll *script* selection.

This is the automation for the one manual step that used to block note-writing
(CLAUDE.md §0): FL resets the active piano-roll script to the default on every
launch, and there is **no controller action, no preference file, and no in-
process API** that sets it. The only way to choose it is the **web-rendered
script dropdown** in the piano-roll toolbar (the wrench icon).

Layers used (PE era — see docs/UI-AUTOMATION.md §1 for the full picture):
  * The wrench is a self-drawn toolbar glyph with no AX tree, so OPENING the
    menu is one synthesized click (cliclick) — the only pixel dependency.
  * The menu itself is navigated with in-engine key events (`ui.keySeq`,
    up×6 + enter; v10.4d), sent ONLY after `ui.isInPopupMenu` confirms the
    menu is open (keys go to the focused form). The trial-era claims that
    in-process `ui` crashes FL and that row clicks are the only way are
    obsolete on the licensed PE build; `screen.*` stays quarantined.
  * Normally you do not call this tool: `roll_session.ensure_script_selected`
    runs it automatically once per FL process before the first note write.

What this tool does:
  1. Ensures FL is frontmost and the piano roll for the target channel is open
     (select the channel, open the roll via the native View menu).
  2. Screenshots the roll toolbar and locates the **wrench** (script) button —
     its x is *not* stable across FL versions/layouts, so it is located by
     pixel search for the wrench glyph, with a configurable override.
  3. Clicks the wrench to open the script list, screenshots it, and clicks the
     requested script (default **ComposeWithLLM**) by locating its label in the
     screenshot.
  4. Reports success and (optionally) verifies by re-opening the dropdown.

This is a macOS-only, coordinate-based automation. It degrades gracefully: if
it cannot locate a target it returns the coordinates it *would* use plus a
screenshot path so a human can confirm and pass explicit coordinates.

**v10.4d (PE era, 2026-10-02):** on a licensed build the DEFAULT method is
now **key navigation** — the only pixel dependency left is the wrench click
itself. In-engine `ui` key events reach the web-rendered toolbar (proven:
up/down moved the roll's zoom; the trial-era CGEvent wall does not exist on
PE), so the selection is committed with `ui.keySeq(["up"]*N + ["enter"])` in
ONE controller trip (the wrench menu is a flat 27-item list; up from the
empty state wraps to the LAST item; 6 ups = 0ComposeWithLLM). If the keySeq
is unavailable (controller predates v10.4d) the tool falls back to the old
row click automatically (`method="click"` forces it; the row model is
trial-era — 30 px rows — and misses on the PE layout, so it's fallback
only). macOS only; no-op-safe elsewhere.
"""

from __future__ import annotations

import os
import platform
import subprocess
import tempfile
from typing import Any

# ---------------------------------------------------------------------------
# Configuration / constants
# ---------------------------------------------------------------------------

FL_APP = os.environ.get("FL_STUDIO_APP", "FL Studio 2026")
FL_PROC = os.environ.get("FL_STUDIO_PROC", "OsxFL")
CLICLICK = os.environ.get("FL_CLICLICK", "/opt/homebrew/bin/cliclick")

# The script we select by default (the note-writing script).
DEFAULT_SCRIPT = os.environ.get("FL_PIANO_ROLL_SCRIPT", "ComposeWithLLM")

# The toolbar row we search. The roll title bar sits ~y205-226 on a 1920x1080
# display with FL maximized; we search a generous band and locate the wrench
# within it.
TOOLBAR_Y = int(os.environ.get("FL_TOOLBAR_Y", "214"))
TOOLBAR_BAND_TOP = int(os.environ.get("FL_TOOLBAR_TOP", "205"))
TOOLBAR_BAND_H = int(os.environ.get("FL_TOOLBAR_H", "22"))
# Horizontal search span for the toolbar icons (the roll is the right panel).
TOOLBAR_X_MIN = int(os.environ.get("FL_TOOLBAR_XMIN", "985"))
TOOLBAR_X_MAX = int(os.environ.get("FL_TOOLBAR_XMAX", "1665"))

# The script list, once open, appears just below-right of the wrench. We search
# a wide box for the requested script's text.
LIST_X_MIN = int(os.environ.get("FL_LIST_XMIN", "985"))
LIST_X_MAX = int(os.environ.get("FL_LIST_XMAX", "1620"))
LIST_Y_MIN = int(os.environ.get("FL_LIST_YMIN", "220"))
LIST_Y_MAX = int(os.environ.get("FL_LIST_YMAX", "560"))


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], timeout: float = 15.0) -> tuple[int, str, str]:
    """Run a shell command; return (rc, stdout, stderr). Never raises."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:  # noqa: BLE001
        return 1, "", str(e)


def _osascript(script: str, timeout: float = 15.0) -> tuple[int, str, str]:
    return _run(["osascript", "-e", script], timeout=timeout)


def _fl_running() -> bool:
    rc, out, _ = _run(["pgrep", "-f", FL_PROC])
    return rc == 0 and bool(out.strip())


def _activate_fl() -> None:
    _osascript(f'tell application "{FL_APP}" to activate')


def _frac(v: str | float) -> float:
    """Parse a fraction ("a/b") or float string/number into a float, safely."""
    try:
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip()
        if "/" in s:
            a, b = s.split("/")
            return float(a) / float(b)
        return float(s)
    except (ValueError, ZeroDivisionError):
        return 0.0


def _script_row_index(script: str) -> int:
    """Index (0-based) of `script` in FL's user-script list order. Unknown -> 1
    (the ComposeWithLLM slot)."""
    # 2026-10-02: our script was renamed 0ComposeWithLLM (sorts FIRST in the
    # merged user+factory list — the default selection is "none", so being
    # first = shortest/most stable click target = row 0). The old name is an
    # alias for the same (only) user script.
    if script in ("ComposeWithLLM", "ComposeWithLLM.pyscript"):
        script = "0ComposeWithLLM"
    order = ["0ComposeWithLLM", "Arpeggiator", "Euclidean", "Humanize",
             "Note repeater sprinkler", "Select by velocity and more"]
    try:
        return order.index(script)
    except ValueError:
        return 0  # unknown -> our script (now first in the merged list)


def _keyseq_keys(up_steps: int) -> list[str]:
    """The §0 key sequence for the wrench menu: N up-presses then enter.

    The menu is ONE flat list (19 built-ins + 8 scripts = 27 items in the
    default 2026 layout); from the open-but-unhighlighted state `up` wraps
    to the LAST item, so N ups lands on item (28 - N). 6 ups = item 22 =
    0ComposeWithLLM (the 3rd entry of the Scripts column — "Run last
    script again" and "Open script folder..." count as items too). Bounded
    to the controller's 12-max.
    """
    n = max(0, min(11, int(up_steps)))
    return ["up"] * n + ["enter"]


def _send_keyseq(keys: list[str]) -> dict:
    """One-trip ui.keySeq via the controller; never raises."""
    try:
        from fl_studio_mcp.utils.connection import get_connection
        return get_connection().send_command(
            "ui.keySeq", {"keys": keys}, timeout=10.0)
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": str(e)[:200]}


def _window_frame() -> tuple[int, int, int, int] | None:
    """Return (left, top, right, bottom) of FL's main window in *screen* coords,
    or None. This is the machine-independent anchor: the roll panel, its
    toolbar, and the script dropdown are positioned relative to this frame, so
    deriving click points as fractions of it makes the tool work on any screen
    size / window size / display scale (not just a specific resolution).
    """
    rc, out, _ = _osascript(
        f'tell application "System Events" to tell process "{FL_PROC}" '
        "to get {position, size} of window 1"
    )
    if rc != 0 or not out:
        return None
    # out looks like: "0, 30, 1920, 963"  (x, y, w, h)
    try:
        x, y, w, h = (int(v) for v in out.split(","))
    except ValueError:
        return None
    return (x, y, x + w, y + h)


def _click(x: int, y: int) -> None:
    _run([CLICLICK, f"c:{int(x)},{int(y)}"], timeout=5)


def _move(x: int, y: int) -> None:
    _run([CLICLICK, f"m:{int(x)},{int(y)}"], timeout=5)


def _open_roll_via_menu() -> tuple[bool, str]:
    """Open (toggle on) the piano roll via the native View menu. Returns
    (ok, note). The View > Piano roll item is a toggle, so we detect whether it
    is currently open by reading the menu item's 'enabled'/menu state is not
    reliable; instead we toggle and then verify via a screenshot + the roll
    title text. Callers that already have the roll open can skip this.
    """
    script = (
        'tell application "System Events" to tell process "'
        f'{FL_PROC}" to click menu item "Piano roll" of menu "View" of menu bar 1'
    )
    rc, out, err = _osascript(script)
    if rc != 0:
        return False, err or out or "could not open View > Piano roll"
    return True, "toggled View > Piano roll"


def _roll_open_from_shot(png: str) -> bool:
    """Heuristic: the roll is open when its title 'Piano roll' text is present in
    a toolbar-region crop. We can't OCR reliably without deps, so instead we
    detect the roll by checking whether the channel-rack region shows the roll
    panel — but the most reliable signal we captured empirically is that the
    toolbar with the wrench exists. We fall back to 'assume open if the wrench
    is found' inside _locate_wrench. Returns True/False only when a fast signal
    is available; None means 'undetermined'.
    """
    return None  # undetermined; _locate_wrench is the real gate


# ---------------------------------------------------------------------------
# image helpers (pure-stdlib BMP/tiff are fiddly; use sips -> ppm if possible,
# else fall back to 'not found' and let the caller pass explicit coordinates)
# ---------------------------------------------------------------------------


def _capture_to(path: str) -> bool:
    rc, out, err = _run(["screencapture", "-x", path])
    return rc == 0


def _crop(src: str, dst: str, top: int, left: int, w: int, h: int) -> bool:
    # sips -c <H> <W> --cropOffset <top> <left>
    rc, _, _ = _run([
        "sips", "-c", str(h), str(w),
        "--cropOffset", str(top), str(left),
        src, "--out", dst,
    ], timeout=15)
    return rc == 0 and os.path.exists(dst)


def _crop_to_ppm(src: str, dst_ppm: str, top: int, left: int, w: int, h: int) -> bool:
    """Crop a region and convert to PPM (P6) so we can read pixels with no deps."""
    tmp = dst_ppm + ".raw.png"
    if not _crop(src, tmp, top, left, w, h):
        return False
    rc, _, _ = _run(["sips", "-s", "format", "ppm", tmp, "--out", dst_ppm], timeout=15)
    ok = rc == 0 and os.path.exists(dst_ppm)
    try:
        os.unlink(tmp)
    except OSError:
        pass
    return ok


def _read_ppm(path: str) -> tuple[int, int, list[int]] | None:
    """Parse a P6 PPM; return (w, h, rgb-list) or None."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    if not data.startswith(b"P6"):
        return None
    # parse header tokens
    toks = []
    i = 2
    while len(toks) < 3 and i < len(data):
        # skip whitespace/comments
        while i < len(data) and (data[i:i + 1].isspace() or data[i:i + 1] == b"#"):
            if data[i:i + 1] == b"#":
                i = data.index(b"\n", i) + 1
            else:
                i += 1
        if i >= len(data):
            break
        j = i
        while j < len(data) and not data[j:j + 1].isspace():
            j += 1
        toks.append(int(data[i:j]))
        i = j
    if len(toks) < 3:
        return None
    w, h, maxval = toks
    pix = data[i + 1:i + 1 + w * h * 3]  # +1 for the single whitespace after maxval
    if len(pix) < w * h * 3:
        pix = data[i + 1:]
    return w, h, list(pix)


def _locate_wrench(png: str) -> int | None:
    """Find the x of the wrench (script) button in the roll toolbar.

    Strategy: the wrench is the *second* toolbar icon (after a small 'back'
    arrow) and is drawn in FL's accent/orange color when it is the highlighted
    tool. We scan the toolbar band for the leftmost cluster of distinctly
    non-background pixels and return the cluster centers; the caller/overrider
    picks. To stay robust without OCR we return the leftmost icon-cluster center
    that is clearly separated from the very-left edge (skipping the 'back'
    arrow), which empirically is the wrench.

    Returns a screen x, or None if the toolbar can't be read.
    """
    ppm = os.path.join(tempfile.gettempdir(), "fltb.ppm")
    if not _crop_to_ppm(png, ppm, TOOLBAR_BAND_TOP, TOOLBAR_X_MIN,
                        TOOLBAR_X_MAX - TOOLBAR_X_MIN, TOOLBAR_BAND_H):
        return None
    got = _read_ppm(ppm)
    if not got:
        return None
    w, h, pix = got
    if w <= 0 or h <= 0:
        return None

    def col_brightness(x: int) -> float:
        best = 0.0
        for y in range(h):
            o = (y * w + x) * 3
            r, g, b = pix[o], pix[o + 1], pix[o + 2]
            best = max(best, 0.299 * r + 0.587 * g + 0.114 * b)
        return best

    cols = [col_brightness(x) for x in range(w)]
    mean = sum(cols) / len(cols)
    # A button is a run of columns brighter than the dark toolbar background.
    runs: list[tuple[int, int]] = []
    cur = None
    for x, v in enumerate(cols):
        if v > mean + 15:
            cur = [x, x] if cur is None else [cur[0], x]
        else:
            if cur and (cur[1] - cur[0]) >= 4:
                runs.append(tuple(cur))
            cur = None
    if cur and (cur[1] - cur[0]) >= 4:
        runs.append(tuple(cur))
    if not runs:
        return None
    # skip the very first run if it is tiny (the 'back' arrow); the wrench is the
    # next clearly-separated cluster. Prefer the 2nd run, else the 1st.
    target = runs[1] if len(runs) >= 2 else runs[0]
    center = TOOLBAR_X_MIN + (target[0] + target[1]) // 2
    return int(center)


# ---------------------------------------------------------------------------
# high-level flow
# ---------------------------------------------------------------------------


def _roll_open() -> bool:
    """Detect whether the piano-roll window is currently open.

    PRIMARY (v10.4d): the roll is a SEPARATE OS window — its title starts
    with "Piano roll" (e.g. "Piano roll - 808 Kick"). Checking OsxFL's
    window list is deterministic and resolution-independent, unlike pixels.
    FALLBACK: the pixel variance detectors below (toolbar-band + content
    region) for the case where the window title can't be read.

    History: the pixel-only detector misfired twice on PE — first it
    reported an open roll as closed and the toggle then CLOSED it
    (11:4x incident); then a nearly-empty roll (one note, flat grid) had
    variance below the threshold (12:07 incident, harmless because the
    View-menu toggle was a no-op mid-restore). Window names don't lie.
    """
    rc, out, _ = _osascript(
        'tell application "System Events" to tell process "' + FL_PROC +
        '" to get name of windows'
    )
    if rc == 0 and out:
        for name in (w.strip() for w in out.split(",")):
            if name.lower().startswith("piano roll"):
                return True
        # No roll window in the list (or the list is empty mid-restore):
        # fall through to the pixel fallback below.
    # --- pixel fallback (unchanged logic) ---
    import tempfile
    shot = os.path.join(tempfile.gettempdir(), "fl_rollcheck.png")
    if not _capture_to(shot):
        return False
    # The roll toolbar sits in the upper-right region. Sample a horizontal band
    # there; an open roll has a row of distinct icon pixels, a closed one is
    # flat (mixer/playlist background).
    ppm = os.path.join(tempfile.gettempdir(), "fl_rollcheck.ppm")
    # band: x from ~1040..1400, y ~205..225 (the toolbar row)
    if not _crop_to_ppm(shot, ppm, TOOLBAR_BAND_TOP, 1040,
                        360, TOOLBAR_BAND_H):
        return False
    got = _read_ppm(ppm)
    if not got:
        return False
    w, h, pix = got
    if w <= 0 or h <= 0:
        return False
    # variance of column-brightness: icons => high variance; flat bg => low
    cols = []
    for x in range(0, w, 3):
        best = 0
        for y in range(0, h, 2):
            o = (y * w + x) * 3
            best = max(best, 0.299 * pix[o] + 0.587 * pix[o + 1] + 0.114 * pix[o + 2])
        cols.append(best)
    if not cols:
        return False
    mean = sum(cols) / len(cols)
    var = sum((c - mean) ** 2 for c in cols) / len(cols)
    # A toolbar row of icons has notably higher variance than a flat panel.
    if var > 350:
        return True
    # 2026-10-02: the toolbar-band detector misfired on PE (dark toolbar,
    # low contrast) and CLOSED an open roll. Second, stronger signal: the
    # roll CONTENT region (piano keys + grid) has far more variance than a
    # flat mixer/playlist background.
    shot2 = os.path.join(tempfile.gettempdir(), "fl_rollcheck2.png")
    if not _capture_to(shot2):
        return False
    ppm2 = os.path.join(tempfile.gettempdir(), "fl_rollcheck2.ppm")
    # content region: the roll window sits right of centre (measured on the
    # 1920-wide screen: native x ~1040..1900, y ~240..800).
    if not _crop_to_ppm(shot2, ppm2, 240, 1040, 860, 560):
        return False
    got2 = _read_ppm(ppm2)
    if not got2:
        return False
    w2, h2, pix2 = got2
    if w2 <= 0 or h2 <= 0:
        return False
    vals = []
    for y in range(0, h2, 4):
        for x in range(0, w2, 4):
            o = (y * w2 + x) * 3
            vals.append(0.299 * pix2[o] + 0.587 * pix2[o + 1] + 0.114 * pix2[o + 2])
    if not vals:
        return False
    mean2 = sum(vals) / len(vals)
    var2 = sum((v - mean2) ** 2 for v in vals) / len(vals)
    return var2 > 800


def _roll_focused() -> bool | None:
    """Ask the ENGINE whether the focused form is the piano roll.

    `ui.getFocusedFormCaption()` (a proven v10.4c safe-read) returns e.g.
    'Piano roll - 808 Kick' when the roll window is the focused one. This is
    the deterministic oracle the pixel detectors never could be: the roll is
    a web-docked panel that is INVISIBLE to System Events (it never appears
    in the OS window list — verified 2026-10-02), and a nearly-empty roll
    defeats pixel-variance thresholds.

    Returns True (focused form is a roll), False (focused form is something
    else), or None (undetermined — controller unreachable / pre-v10.4c).
    Retries once: right after a native View-menu toggle the controller thread
    is still settling (menu-blocked) and the first ui.call can time out.
    """
    import time
    for attempt in (1, 2):
        try:
            from fl_studio_mcp.utils.connection import get_connection
            r = get_connection().send_command(
                "ui.call", {"name": "getFocusedFormCaption"},
                timeout=8.0)
            if not isinstance(r, dict) or not r.get("success"):
                if attempt == 1:
                    time.sleep(1.0)
                    continue
                return None
            cap = str(r.get("result", "")).strip("' \"")
            if not cap:
                return None
            return cap.lower().startswith("piano roll")
        except Exception:  # noqa: BLE001
            if attempt == 1:
                time.sleep(1.0)
                continue
            return None
    return None


def _menu_open() -> bool | None:
    """Is a popup menu currently open? — `ui.isInPopupMenu()`, a proven
    v10.4c safe-read (1 while a menu is up, 0 otherwise).

    This is the deterministic oracle the pixel detectors never could be,
    and it has **no focus dependency**: the wrench's script menu is the
    thing we care about, not which form has keyboard focus. Used to verify
    that the wrench click actually opened the script menu (and therefore
    that the roll is open) before key events are sent — keySeq with no
    menu open would land on whatever form is focused (harmful).

    Returns True/False, or None (undetermined — controller unreachable /
    pre-v10.4c).
    """
    import time
    for attempt in (1, 2):
        try:
            from fl_studio_mcp.utils.connection import get_connection
            r = get_connection().send_command(
                "ui.call", {"name": "isInPopupMenu"}, timeout=8.0)
            if not isinstance(r, dict) or not r.get("success"):
                if attempt == 1:
                    time.sleep(1.0)
                    continue
                return None
            val = str(r.get("result", "")).strip()
            if val in ("1", "0"):
                return val == "1"
            return None
        except Exception:  # noqa: BLE001
            if attempt == 1:
                time.sleep(1.0)
                continue
            return None
    return None


# The wrench sits on the roll's title row, this far left of the title text
# ("Piano roll - <channel>"). Measured on the floating roll 2026-10-02:
# title x=1363, wrench (hint "Tools") x=1031 → -332; the old fixed fraction
# (x=1041, y=214+16) hit the "Color group / MIDI channel" selector instead,
# whose popup satisfied the isInPopupMenu probe and took the keys.
WRENCH_FROM_TITLE_DX = -332


# Floating roll (2026-10-03 fixtures, 1280-wide screenshots): the title text
# is LEFT-aligned in the title/toolbar row at x~1087-1090 whatever the channel
# name's length, and the wrench is the left end of that same row at x~768 ->
# wrench_x = title_box.x - 321. ASSUMPTION: the floating roll keeps its
# default width/placement; the hover hint ("Tools") confirms before any click.
WRENCH_FROM_FLOATING_TITLE_DX = -321


def wrench_point_from_boxes(boxes: list[dict], channel_names: list[str]) -> dict | None:
    """Pure: expected wrench point from OCR boxes of a full-screen shot.

    y = vertical centre of the roll title box (the toolbar row IS the title
    row on a floating roll). x = the offset from the title (docked: measured
    from where "Piano" starts, -332; floating: from the box's left edge,
    -321). None when no roll title is found (the caller must refuse).
    """
    from fl_studio_mcp.utils.roll_session import roll_title_match
    m = roll_title_match(boxes, channel_names)
    if m is None:
        return None
    name, box, docked = m
    y = int(box["y"] + box["h"] / 2)
    if docked:
        i = box["text"].lower().find("piano")
        tx = box["x"] + int(box["w"] * max(0, i) / max(1, len(box["text"])))
        x = tx + WRENCH_FROM_TITLE_DX
    else:
        x = box["x"] + WRENCH_FROM_FLOATING_TITLE_DX
    return {"x": int(x), "y": y, "title": name, "docked": docked}


def _channel_names() -> list[str]:
    try:
        from fl_studio_mcp.utils.connection import get_connection
        chans = get_connection().send_command("channels.getAll").get("channels", [])
        return [c.get("name") or "" for c in chans]
    except Exception:  # noqa: BLE001
        return []


def _wrench_from_title(wrench_x: int | None = None) -> tuple[int, int] | None:
    """Locate the wrench from the roll title (OCR; docked 'Piano roll - X' or a
    floating roll's bare channel-name title) and CONFIRM it by its hover hint
    ("Tools") before anyone clicks it. With an explicit `wrench_x` only the y
    (title row) is derived and x is returned unchanged. None = not found /
    not confirmed."""
    try:
        from fl_studio_mcp.utils import custom_menu as cm
        from fl_studio_mcp.utils.roll_session import parse_ocr_boxes  # noqa: F401
        names = _channel_names()
        pt = None
        # 1x full screen reads the title; 3x only as the fallback for a dim one.
        for boxes in (lambda: cm.ocr_boxes(cm.shot()),
                      lambda: cm.ocr_region(0, 100, 1920, 900, scale=3)):
            dicts = [{"x": b.x, "y": b.y, "w": b.w, "h": b.h,
                      "text": b.text.replace("roll-", "roll -")} for b in boxes()]
            pt = wrench_point_from_boxes(dicts, names)
            if pt is None:
                # docked title with a leading icon glyph ("4 Piano roll-X")
                for d in dicts:
                    if "piano roll" in d["text"].lower():
                        pt = wrench_point_from_boxes([d], names + [""]) or {
                            "x": d["x"] + WRENCH_FROM_TITLE_DX,
                            "y": int(d["y"] + d["h"] / 2), "docked": True}
                        break
            if pt is not None:
                break
        if pt is None:
            return None
        y = pt["y"]
        if wrench_x is not None:
            return int(wrench_x), y
        for dx in (0, -10, 10, -20, 20, -30, 30):
            x = pt["x"] + dx
            if cm.hint_at(x, y).strip().lower().startswith("tools"):
                return x, y
    except Exception:  # noqa: BLE001 - fall back to the frame fractions
        return None
    return None


def _open_wrench_menu(wrench: int, toolbar_y: int) -> tuple[bool, str]:
    """Click the wrench and VERIFY the script menu opened (isInPopupMenu).

    The wrench glyph only exists in the roll toolbar, so a menu-opening
    click proves the roll is open; a click that hits background (roll
    closed) opens no menu. If the first click opens nothing, the roll is
    closed — open it via the native View menu and click again. Max one
    blind toggle, always verified. Returns (opened, note).
    """
    _activate_fl()
    _click(wrench, toolbar_y)
    _run(["sleep", "1.2"])
    opened = _menu_open()
    if opened is True:
        return True, "wrench clicked; script menu confirmed open (roll was open)"
    # No menu: the roll was closed (click hit background) — or the getter
    # is undetermined. If undetermined, assume the (likely) open case and
    # do NOT toggle blindly; only toggle when we have a negative answer.
    if opened is False:
        ok, note = _open_roll_via_menu()
        _run(["sleep", "2.0"])
        _activate_fl()
        _click(wrench, toolbar_y)
        _run(["sleep", "1.2"])
        opened2 = _menu_open()
        if opened2 is True:
            return True, (f"{note}; wrench click then opened the script menu "
                          "(roll opened and focused)")
        return False, (f"{note}; the script menu still did not open after the "
                       "toggle — the wrench location may be wrong on this "
                       "layout (pass explicit wrench_x); check the screenshot")
    return True, ("wrench clicked; menu state undetermined "
                  "(controller pre-v10.4c?) — assuming open")


def _ensure_roll_open(channel_index: int | None) -> dict:
    """Select the channel and make sure the roll is OPEN — toggle-until-focused.

    The View > Piano roll menu item is a TOGGLE, so a blind click either
    opens the roll or CLOSES the open one (the 11:4x incident). The fix is
    deterministic: toggle, then ask the engine which form is focused
    (`ui.getFocusedFormCaption` — the roll is web-docked and invisible to
    the OS window list, but the engine knows its own forms). If the focused
    form is the roll we're done; if not, one more toggle converges it. Max
    two toggles; the pixel detector is only the last-resort reporter.
    """
    _activate_fl()
    steps = []
    if channel_index is not None:
        try:
            from fl_studio_mcp.utils.connection import get_connection
            conn = get_connection()
            r = conn.send_command("channels.selectOne", {"index": int(channel_index)},
                                  timeout=6.0)
            ok = bool(r.get("success"))
            steps.append(f"selected channel {channel_index}: {ok}"
                         + (f" ({r.get('error')})" if not ok else ""))
            if not ok:
                steps.append("note: channel index out of range; continuing with the current roll target")
        except Exception as e:  # noqa: BLE001
            steps.append(f"select channel failed: {e}")
    _run(["sleep", "0.6"])
    # v10.4d: the roll is no longer pre-toggled here. The wrench click is its
    # own detector (see _open_wrench_menu): the script menu opens only when
    # the roll is open, so the old blind-toggle race is gone. The caption/
    # pixel helpers above remain available for diagnostics.
    steps.append("roll state deferred to the wrench-click probe (v10.4d)")
    return {"steps": steps}


def fl_select_script(
    script: str | None = None,
    channel_index: int | None = None,
    ensure_open: bool = True,
    verify: bool = False,
    wrench_x: int | None = None,
    script_x: int | None = None,
    script_y: int | None = None,
    screenshot_dir: str | None = None,
    scale: bool = True,
    open_only: bool = False,
    method: str = "keys",
    up_steps: int = 6,
) -> dict:
    """Select the active piano-roll script (default: 0ComposeWithLLM).

    Automates the §0 per-session step. DEFAULT (PE builds): key navigation —
    select channel, open the roll (detect-first), click the wrench (the only
    pixel dependency), then commit the selection with one in-engine
    `ui.keySeq` trip: `up_steps` up-presses (default 6 = 0ComposeWithLLM in
    the 27-item flat menu) + enter. Falls back to the old row click when
    keySeq is unavailable. `method="click"` forces the row-click path.

    Params:
      script           — script name to select (default ComposeWithLLM; the
                         old name is an alias of 0ComposeWithLLM).
      channel_index    — select this channel and open its roll first.
      ensure_open      — open the roll via the native View menu first (default
                         True). Set False if you've already opened it.
      scale            — derive click points as fractions of the live FL window
                         frame (default True) so it adapts to any screen / window
                         / display scale. Set False to use the raw verified pixels.
      wrench_x         — explicit screen x of the wrench (overrides auto-detect).
      script_x/y       — explicit screen coords to click for the script (used verbatim).
      screenshot_dir   — where to stash debug screenshots (default /tmp).
      open_only        — click the wrench to OPEN the dropdown and stop (no
                         selection change). For manual key driving.
      method           — "keys" (default; ui.keySeq, one controller trip) or
                         "click" (the trial-era row-click model).
      up_steps         — number of up-presses in keys mode (default 6 =
                         0ComposeWithLLM; re-count if you add/remove scripts).
    """
    if platform.system() != "Darwin":
        return {"success": False,
                "error": "fl_select_script is macOS-only (native menu + cliclick)."}
    script = script or DEFAULT_SCRIPT
    shot_dir = screenshot_dir or tempfile.gettempdir()
    result: dict[str, Any] = {"action": "select_script", "script": script,
                              "success": False}

    if not _fl_running():
        result["error"] = "FL Studio is not running."
        return result

    # Resolve the live FL window frame (machine-independent anchor). All
    # auto-derived coordinates are expressed as fractions of this frame so the
    # tool works on any screen size / window size / display scale. Explicit
    # wrench_x / script_x / script_y always win over auto-derived values.
    frame = _window_frame() if scale else None
    ref = frame or (0, 30, 1920, 993)  # fallback = the layout we verified on
    fl, ft, fr, fb = ref
    fw, fh = fr - fl, fb - ft

    # Verified anchor fractions (from the 1920x1080 layout, frame 0,30,1920,993):
    #   wrench center  x=1041 -> fx=1041/1920 ; toolbar y=214 -> fy=(214-30)/963
    #   script col     x=1302 -> fx=1302/1920
    #   ComposeWithLLM y=315  -> fy=(315-30)/963 ; row height 30 -> 30/963
    WRENCH_FX = _frac(os.environ.get("FL_WRENCH_FX", "1041/1920"))
    TOOLBAR_FY = _frac(os.environ.get("FL_TOOLBAR_FY", "184/963"))
    SCRIPT_FX = _frac(os.environ.get("FL_SCRIPT_FX", "1302/1920"))
    SCRIPT_ANCHOR_FY = _frac(os.environ.get("FL_SCRIPT_ANCHOR_FY", "285/963"))
    ROW_H_FY = _frac(os.environ.get("FL_SCRIPT_ROW_H_FY", "30/963"))

    # 1) bring FL front + ensure the roll is open (never blind-toggle)
    if ensure_open:
        result["setup"] = _ensure_roll_open(channel_index)
    else:
        _activate_fl()
    _run(["sleep", "1.0"])

    # 2) locate the wrench (screen x) — auto by pixel, else scaled default
    shot = os.path.join(shot_dir, "fl_wrench.png")
    _capture_to(shot)
    wrench = wrench_x
    if wrench is None:
        wrench = _locate_wrench(shot)
        if wrench is None:
            wrench = int(fl + fw * _frac(WRENCH_FX))
            result["wrench_x_note"] = ("auto-detect failed; using window-relative "
                                        f"default x={wrench} (frame={frame})")
    toolbar_y = int(ft + fh * _frac(TOOLBAR_FY))
    if wrench_x is not None:
        # S2: an explicit x still needs the right ROW — on a floating roll the
        # toolbar row is the roll's title row (the frame fraction hit y=145
        # while the wrench was at y~178). Take y from the title OCR if found.
        loc = _wrench_from_title(wrench_x)
        if loc is not None:
            toolbar_y = loc[1]
            result["wrench_source"] = "explicit wrench_x + roll-title row"
        else:
            result["wrench_y_note"] = ("roll title not found; y from the window-"
                                       "frame fraction (may miss on a floating roll)")
    if wrench_x is None:
        # Title-anchored + hint-confirmed (docked or floating). NEVER click an
        # unconfirmed spot: the old fixed fraction hit the roll's colour-group
        # selector, whose popup passed the menu probe and took the keys
        # (2026-10-02, twice). Not visible -> open the roll once, look again.
        loc = _wrench_from_title()
        if loc is None and ensure_open:
            _open_roll_via_menu()
            _run(["sleep", "2.0"])
            loc = _wrench_from_title()
        if loc is None:
            result["success"] = False
            result["error"] = ("could not find the piano-roll wrench (title OCR + "
                               "hover hint 'Tools'); nothing was clicked and no keys "
                               "were sent. Make sure the roll is visible, or pass "
                               "wrench_x (+ the screenshot) explicitly.")
            return result
        wrench, toolbar_y = loc
        result["wrench_source"] = "roll title + hint 'Tools'"
    result["wrench_x"] = wrench
    result["wrench_y"] = toolbar_y
    result["window_frame"] = list(frame) if frame else None

    # 3) click the wrench and VERIFY the script menu actually opened
    #    (v10.4d: the menu only exists when the roll is open, so this one
    #    probe both opens the menu and detects the roll state)
    if ensure_open:
        menu_open, menu_note = _open_wrench_menu(wrench, toolbar_y)
        result["setup"].setdefault("steps", []).append(menu_note)
    else:
        _activate_fl()
        _click(wrench, toolbar_y)
        _run(["sleep", "1.2"])
        menu_open = None  # manual mode (ensure_open=False): no verification
    result["menu_open"] = menu_open

    # 4a) v10.4d: commit the selection with in-engine key events (one trip)
    keys_done = False
    if method == "keys" and not open_only:
        if menu_open is False:
            # NEVER send key events with no menu open — they would land on
            # whatever form has focus (the user's browser, a text field...)
            result["success"] = False
            result["error"] = ("the wrench did not open the script menu (roll closed "
                               "or wrench mislocated); key events were NOT sent. "
                               "Check the screenshot; pass explicit wrench_x if the "
                               "wrench moved on this layout.")
            return result
        keys = _keyseq_keys(up_steps)
        ks = _send_keyseq(keys)
        result["keyseq"] = ks
        keys_done = bool(ks.get("success"))
        if not keys_done:
            result["keyseq_note"] = (
                "ui.keySeq unavailable or failed "
                f"({ks.get('error', 'unknown')}) — falling back to the row click")

    # 4b) click the requested script in the list (skipped when open_only —
    # the dropdown stays open for the caller to drive; skipped when keys
    # committed the selection)
    if open_only:
        if script_x is not None and script_y is not None:
            sx, sy = int(script_x), int(script_y)
        else:
            sx = int(fl + fw * _frac(SCRIPT_FX))
            idx = _script_row_index(script)
            sy = int(ft + fh * _frac(SCRIPT_ANCHOR_FY)
                     + (idx - 1) * fh * _frac(ROW_H_FY))
        result["script_click"] = {"x": sx, "y": sy,
                                  "clicked": False,
                                  "note": "open_only — dropdown left open"}
        result["toolbar_y"] = toolbar_y
        result["success"] = True
        result["note"] = (
            "Wrench clicked — dropdown OPEN, no selection made. Row for "
            f"{script!r} would be at ({sx},{sy}). Drive it with ui key "
            "events (up/down/enter) or click; escape closes unchanged.")
        return result
    if keys_done:
        # v10.4d: the enter committed the selection (the script runs once at
        # selection time — piano_roll_state.json updates). Park the mouse and
        # leave the roll open for note-writing.
        _activate_fl()
        _move(960, 900)
        _run(["sleep", "0.8"])
        result["script_click"] = {"x": None, "y": None, "mode": "keys",
                                  "note": "selection committed by ui.keySeq, not a click"}
        result["toolbar_y"] = toolbar_y
        result["success"] = True
        result["note"] = (
            f"Selected {script!r} for channel {channel_index} via KEY NAVIGATION "
            f"(wrench click at ({wrench},{toolbar_y}) + ui.keySeq {keys}); roll left "
            "open. The selection is committed by the enter — the script ran once "
            "at selection time (state file updated). Confirm with fl_state / the "
            "state file, then write notes via fl_notes. If the user adds/removes "
            "scripts, re-count up_steps (6 = 0ComposeWithLLM in the default "
            "27-item menu).")
        return result
    if script_x is not None and script_y is not None:
        sx, sy = int(script_x), int(script_y)
    else:
        # window-relative position for the requested script's row
        sx = int(fl + fw * _frac(SCRIPT_FX))
        idx = _script_row_index(script)
        sy = int(ft + fh * _frac(SCRIPT_ANCHOR_FY) + (idx - 1) * fh * _frac(ROW_H_FY))
    if menu_open is False:
        result["menu_warning"] = (
            "the wrench did not open the menu — this row click will hit the "
            "background; the selection almost certainly did NOT take")
    # Hover first (so FL highlights the row) then click, to reduce misclicks.
    _activate_fl()
    _move(sx, sy)
    _run(["sleep", "0.6"])
    _click(sx, sy)
    # Give FL a full settle gap AFTER the selection click so it commits the
    # active-script change before we touch anything else. (Clicking the row can
    # also *run* the script once; the settle lets that finish and the selection
    # register.) Too short a gap here was racing the commit.
    _run(["sleep", "2.0"])
    _activate_fl()
    # Park the mouse away from the roll so it can't obscure or stray-click a
    # note cell. Deliberately do NOT send Escape here: a stray Escape has closed
    # the roll / cancelled the selection in some layouts. The dropdown closes
    # on its own after a valid selection.
    _move(960, 900)
    _run(["sleep", "0.5"])

    result["script_click"] = {"x": sx, "y": sy}
    result["toolbar_y"] = toolbar_y

    # 5) FUNCTIONAL verification (OPT-IN): the selection click is the thing that
    #    matters (you can see ComposeWithLLM highlighted). The trigger-based proof
    #    is focus-flaky and, when it fires, injects a marker note that must be
    #    cleaned up — so it is OFF by default. Pass verify=True to run it.
    if verify:
        confirmed, detail = _verify_selection(script, shot_dir, frame)
        result["verified"] = confirmed
        result["verify_detail"] = detail
    result["success"] = True
    result["note"] = (
        f"Selected {script!r} for channel {channel_index} via ROW CLICK (wrench at "
        f"({wrench},{toolbar_y}), script row at ({sx},{sy})); roll left open. The "
        f"selection is committed by the click — confirm by re-opening the wrench. "
        "NOTE: the row model is trial-era (30 px rows); on the PE layout this can "
        "miss — prefer method='keys' (v10.4d). Note-writing via fl_notes will now "
        "drain into this roll."
        + ("" if not verify else f" | verify: {detail}"))
    if verify and not result.get("verified", False):
        result["warning"] = (
            "The automatic trigger check did not confirm the selection (Cmd+Opt+Y focus "
            "caveat). If a later fl_notes write returns note_count 0, re-call with explicit "
            "wrench_x / script_x / script_y. Failure screenshot saved for inspection.")
        vshot = os.path.join(shot_dir, "fl_select_script_check.png")
        _activate_fl()
        _capture_to(vshot)
        result["failure_screenshot"] = vshot
    return result


def _verify_selection(script: str, shot_dir: str, frame) -> tuple[bool, str]:
    """Functionally confirm `script` is the active piano-roll script.

    Queues a single low-velocity marker note, triggers the piano-roll script, and
    checks whether the script's state file was produced/updated (which only
    happens if that script is the one FL runs on trigger). Cleans up the marker
    after. Returns (confirmed, detail). Never raises.

    NOTE: the ComposeWithLLM script writes its files into its OWN directory
    (get_script_dir()), which is the *Piano roll scripts* folder — NOT the
    Hardware/FLStudioMCP folder. We search both so this stays robust across
    installs.
    """
    try:
        import json
        import time

        from fl_studio_mcp.utils.connection import get_connection
        from fl_studio_mcp.utils.fl_trigger import get_trigger, trigger_fl_studio

        home = os.path.expanduser("~/Documents/Image-Line/FL Studio/Settings")
        candidates = [
            os.path.join(home, "Piano roll scripts"),
            os.path.join(home, "Hardware", "FLStudioMCP"),
        ]
        # pick the dir that actually contains the script's files
        base = next((d for d in candidates if os.path.exists(
            os.path.join(d, "mcp_request.json"))), candidates[0])
        req = os.path.join(base, "mcp_request.json")
        st = os.path.join(base, "piano_roll_state.json")

        # clear any stale state so we can detect a fresh write
        try:
            if os.path.exists(st):
                os.unlink(st)
        except OSError:
            pass

        marker = [{"midi": 60, "time": 0.0, "duration": 0.25, "velocity": 40}]
        with open(req, "w") as f:
            json.dump([{"action": "clear"},
                       {"action": "add_notes", "notes": marker}], f)

        conn = get_connection()
        conn.send_command("channels.selectOne", {"index": 0}, timeout=5.0)
        _activate_fl(); time.sleep(0.4)
        _run(["sleep", "0.5"])

        trig = get_trigger()
        # Focus the roll window before triggering: the Cmd+Opt+Y keystroke goes
        # to whichever window is key, so click inside the roll (right panel) and
        # re-activate FL immediately before sending.
        _activate_fl(); time.sleep(0.3)
        sent = (trig.is_supported and trigger_fl_studio()) or False
        time.sleep(2.0)

        ran = os.path.exists(st)
        # clean up the marker note we just added (queue a clear, trigger again)
        try:
            with open(req, "w") as f:
                json.dump([{"action": "clear"}], f)
            _activate_fl(); time.sleep(0.3)
            if trig.is_supported:
                trigger_fl_studio()
                time.sleep(0.8)
        except Exception:
            pass

        if ran:
            return True, (f"trigger sent={sent}; {script!r} script ran "
                          "(piano_roll_state.json written) -> selection confirmed.")
        return False, (
            f"trigger sent={sent}, but the script did NOT produce a state file -> "
            f"{script!r} is not the active script (the click likely missed the row).")
    except Exception as e:  # noqa: BLE001
        return False, f"verification error: {e}"


def register_select_script_tool(mcp) -> None:
    """Register the fl_select_script tool."""
    from fl_studio_mcp.tools.select_script import fl_select_script as _impl

    @mcp.tool()
    def fl_select_script(
        script: str | None = None,
        channel_index: int | None = None,
        ensure_open: bool = True,
        scale: bool = True,
        verify: bool = False,
        wrench_x: int | None = None,
        script_x: int | None = None,
        script_y: int | None = None,
        open_only: bool = False,
        method: str = "keys",
        up_steps: int = 6,
    ) -> dict:
        """Select the active piano-roll script (default: 0ComposeWithLLM) for ANY channel.

        Automates the §0 per-session step: selects `channel_index`, ensures the
        roll is open (never blindly toggles it shut), opens the wrench, and
        commits the selection. PE builds: method='keys' (default) — in-engine
        ui.keySeq (up_steps up-presses + enter, one controller trip; the
        wrench click is the only pixel dependency). method='click' = the
        trial-era row-click fallback (can miss on the PE layout). open_only
        leaves the dropdown open for manual key driving.

        Params:
          script        — script name (default ComposeWithLLM = alias of 0ComposeWithLLM).
          channel_index — select this channel and open its roll first.
          ensure_open   — make sure the roll is open first (default True; safe, no blind toggle).
          scale         — adapt coordinates to this machine's window size (default True).
          verify        — run the trigger-based confirmation (off by default; it
                          injects+cleans a marker note and is focus-flaky).
          wrench_x      — explicit wrench screen x (override auto-detect).
          script_x/y    — explicit script-row screen coords (used verbatim).
          open_only     — open the dropdown and stop (no selection; returns row coords).
          method        — 'keys' (default) or 'click'.
          up_steps      — up-presses in keys mode (default 6 = 0ComposeWithLLM).
        """
        return _impl(script=script, channel_index=channel_index,
                     ensure_open=ensure_open, scale=scale, verify=verify,
                     wrench_x=wrench_x, script_x=script_x, script_y=script_y,
                     open_only=open_only, method=method, up_steps=up_steps)

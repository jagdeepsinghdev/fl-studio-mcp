"""Server-side automation primitives for FL's custom-drawn UI surfaces.

FL 2026 (macOS) draws its plugin windows, toolbars and context menus
itself — they have NO accessibility tree (System Events sees the window
title and nothing else). What DOES work (all proven live, 2026-10-01):

  * menus in the macOS menu bar are native (System Events clicks)
  * native AppKit panels (Open/Save/go-to) accept accessibility writes
  * the plugin-picker window takes synthetic KEY events in its Find field
  * FL's custom menus are clickable by COORDINATE, and their rows can be
    LOCATED with the macOS Vision OCR (scripts/ocr_text.swift --boxes)

This module bundles those primitives so tool code (L16 native-menu paths,
the Edison run, …) stops ad-hoc-ing cliclick/osascript in shell.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass

FL_PROC = "OsxFL"
OCR_BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "..", "..", ".generated", "bin", "ocr_text")


# ---------------------------------------------------------------- screen ---

def shot(path: str = "/tmp/fl_auto.png") -> str:
    """Full-screen screenshot; returns the path."""
    subprocess.run(["screencapture", "-x", path], timeout=15)
    return path


def fl_window_id() -> int | None:
    """CGWindow id of FL's main window (title ends 'FL Studio 2026'), or None."""
    import Quartz  # pyobjc; imported lazily (tests and non-mac stay clean)
    wins = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll,
                                             Quartz.kCGNullWindowID) or []
    best = None
    for w in wins:
        if w.get("kCGWindowOwnerName") not in (FL_PROC, "FL Studio", "FL Studio 2026"):
            continue
        if "FL Studio" in str(w.get("kCGWindowName") or ""):
            area = (w["kCGWindowBounds"]["Width"] * w["kCGWindowBounds"]["Height"])
            if best is None or area > best[0]:
                best = (area, int(w["kCGWindowNumber"]))
    return best[1] if best else None


def fl_window_shot(path: str = "/tmp/fl_window.png") -> str | None:
    """Capture ONLY FL's main window — works while FL is behind other apps
    (no focus change, no click). Coordinates are window-relative and at
    Retina pixel scale, so use it to LOOK, not to compute click points."""
    wid = fl_window_id()
    if wid is None:
        return None
    subprocess.run(["screencapture", "-x", "-o", f"-l{wid}", path], timeout=15)
    return path


@dataclass
class Box:
    x: int
    y: int
    w: int
    h: int
    text: str

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2


def ocr_boxes(img: str) -> list[Box]:
    p = subprocess.run([OCR_BIN, img, "--boxes"],
                       capture_output=True, text=True, timeout=30)
    out: list[Box] = []
    for line in p.stdout.splitlines():
        if line.startswith("#image") or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 5:
            continue
        try:
            x, y, w, h = (int(v) for v in parts[:4])
        except ValueError:
            continue
        out.append(Box(x, y, w, h, parts[4].strip()))
    return out


def ocr_region(x: int, y: int, w: int, h: int, scale: int = 3,
               path: str = "/tmp/fl_auto_region.png") -> list[Box]:
    """OCR a screen region upscaled `scale`x (screencapture -R + sips), with
    boxes mapped back to screen coordinates. FL's custom-drawn menus use
    small text that full-screen OCR misreads (Edison's context menu over a
    spectrogram: 'Tools' -> 'nnis'); upscaling fixes it."""
    subprocess.run(["screencapture", "-x", "-R", f"{x},{y},{w},{h}", path],
                   timeout=15)
    p = subprocess.run(["sips", "-g", "pixelWidth", path],
                       capture_output=True, text=True, timeout=15)
    try:
        px = int(p.stdout.split("pixelWidth:")[1].split()[0])
    except (IndexError, ValueError):
        return []
    subprocess.run(["sips", "-z", str(int(h * px / w) * scale),
                    str(px * scale), path],
                   capture_output=True, timeout=15)
    k = w / (px * scale)
    return [Box(x + int(b.x * k), y + int(b.y * k), max(1, int(b.w * k)),
                max(1, int(b.h * k)), b.text) for b in ocr_boxes(path)]


def find_box(img: str, text: str, contains: bool = True) -> Box | None:
    """First OCR box whose text matches (exact, or `contains` substring)."""
    for b in ocr_boxes(img):
        if (b.text == text if not contains else text.lower() in b.text.lower()):
            return b
    return None


def click_text(img: str, text: str, double: bool = False,
               contains: bool = True) -> bool:
    b = find_box(img, text, contains=contains)
    if b is None:
        return False
    if double:
        _click(b.cx, b.cy, double=True)
    else:
        _click(b.cx, b.cy)
    return True


# ---------------------------------------------------------------- mouse ----

def _click(x: int, y: int, double: bool = False,
           button: str = "left") -> None:
    if button == "right":
        cmd = f"rc:{x},{y}"
    elif double:
        cmd = f"dc:{x},{y}"
    else:
        cmd = f"c:{x},{y}"
    subprocess.run(["cliclick", cmd], timeout=10)


def scroll(x: int, y: int, lines: int) -> None:
    """Mouse-wheel scroll at (x, y): lines > 0 scrolls the content DOWN (towards
    later rows). Quartz scroll-wheel events (cliclick has no wheel)."""
    import Quartz
    move(x, y)
    time.sleep(0.1)
    ev = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 1, -int(lines))
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def move(x: int, y: int) -> None:
    subprocess.run(["cliclick", f"m:{x},{y}"], timeout=10)


# ---------------------------------------------------------------- keys -----

_US_KEYCODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
    "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16,
    "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23,
    "9": 25, "7": 26, "8": 28, "0": 29, "o": 31, "u": 32, "i": 34,
    "p": 35, "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
    "/": 44, ".": 47, ",": 43, "-": 27, "=": 24, "'": 39, "[": 33,
    "]": 30, "\\": 42, "`": 50, " ": 49,
}


def _quartz():
    import Quartz  # noqa: F401
    return Quartz


def key(char: str) -> None:
    """Press one US-layout key (upper or lower case) via CGEvent; the
    picker Find field and native panels accept these (proven live)."""
    q = _quartz()
    upper = char.isupper()
    kc = _US_KEYCODES.get(char.lower())
    if kc is None:
        raise ValueError(f"no keycode mapping for {char!r}")
    flags = (q.kCGEventFlagMaskShift if upper else 0)
    down = q.CGEventCreateKeyboardEvent(None, kc, True)
    up = q.CGEventCreateKeyboardEvent(None, kc, False)
    if flags:
        q.CGEventSetFlags(down, flags)
        q.CGEventSetFlags(up, flags)
    q.CGEventPost(q.kCGHIDEventTap, down)
    time.sleep(0.02)
    q.CGEventPost(q.kCGHIDEventTap, up)
    time.sleep(0.02)


def type_text(s: str) -> None:
    for ch in s:
        key(ch)


def keypress(name: str) -> None:
    """Named key via cliclick (esc/enter/return/tab/arrows/…)."""
    subprocess.run(["cliclick", f"kp:{name}"], timeout=10)


# ------------------------------------------------------------- windows -----

def osa(script: str) -> tuple[int, str, str]:
    p = subprocess.run(["osascript", "-e", script],
                       capture_output=True, text=True, timeout=20)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def focus_fl() -> None:
    osa(f'tell application "System Events" to set frontmost of process '
        f'"{FL_PROC}" to true')


def window_by_name(fragment: str) -> tuple[int, int, int, int] | None:
    """(x, y, w, h) of the first FL window whose name contains fragment."""
    script = (
        'tell application "System Events"\n'
        f'  tell process "{FL_PROC}"\n'
        '    set n to count of windows\n'
        '    repeat with i from 1 to n\n'
        '      if (name of window i as text) contains "' + fragment + '" then\n'
        '        set p to position of window i\n'
        '        return (i as text) & "," & (item 1 of p)\n'
        '      end if\n'
        '    end repeat\n'
        '  end tell\n'
        '  return "none"\n'
        'end tell')
    _, out, _ = osa(script)
    if out.startswith("none"):
        return None
    idx, _ = out.split(",", 1)
    script2 = (
        f'tell application "System Events" to tell process "{FL_PROC}"\n'
        f"  set p to position of window {idx}\n"
        f"  set s to size of window {idx}\n"
        '  return ((item 1 of p) as text) & "," & (item 2 of p) & "," & '
        '        (item 1 of s) & "," & (item 2 of s)\n'
        'end tell')
    _, out2, _ = osa(script2)
    try:
        vals = [int(v) for v in out2.split(",")]
    except ValueError:
        return None
    return (vals[0], vals[1], vals[2], vals[3])


def move_window(fragment: str, x: int, y: int,
                w: int | None = None, h: int | None = None) -> bool:
    """Move/resize an FL window by (substring) name; raises it."""
    if window_by_name(fragment) is None:
        return False
    lines = [
        f'tell application "System Events" to tell process "{FL_PROC}"',
        "  repeat with i from 1 to (count of windows)",
        '    if (name of window i as text) contains "' + fragment + '" then',
        f"      set position of window i to {{{x}, {y}}}",
    ]
    if w and h:
        lines.append(f"      set size of window i to {{{w}, {h}}}")
    lines += [
        '      perform action "AXRaise" of window i',
        "      exit repeat",
        "    end if",
        "  end repeat",
        "end tell",
    ]
    rc, _, _ = osa("\n".join(lines))
    return rc == 0


# -------------------------------------------------- native panel (C3) -----

def native_open_panel_select(path: str) -> bool:
    """Drive a native macOS Open panel that is already open: go-to the
    file's folder, select the file, confirm. (C3 pattern: the go-to field
    is set via accessibility, not keystrokes — typed digits drop.)"""
    parent = os.path.dirname(path)
    base = os.path.basename(path)
    # 1. open "Go to the folder"
    subprocess.run(["osascript", "-e",
                    'tell application "System Events" to keystroke "g" '
                    'using {command down, shift down}'], timeout=10)
    time.sleep(0.6)
    # 2. set the go-to field's value directly (AX), confirm
    r, _, err = osa(
        'tell application "System Events"\n'
        "  tell (first process whose frontmost is true)\n"
        "    tell window 1\n"
        "      repeat with w in windows\n"
        f'        try\n'
        f'          set value of text field 1 of sheet 1 of w to "{parent}"\n'
        "          keystroke return\n"
        "          return 0\n"
        "        end try\n"
        "      end repeat\n"
        "    end tell\n"
        "  end tell\n"
        "end tell\n"
        "return 1")
    if r != 0:
        # fallback: type into the focused field (works for letters, digits
        # can drop — the AX path above is the reliable one)
        type_text(parent)
        keypress("return")
        time.sleep(0.6)
    # 3. type the file name (letters mostly; digits may drop — retry via AX)
    type_text(base)
    keypress("return")
    time.sleep(0.8)
    return True


# ------------------------------------------------------------ menus --------

def menu_bar_click(*path: str) -> bool:
    """Click a nested macOS menu-bar path, e.g.
    menu_bar_click("Add", "Effect", "More plugins...").

    System Events' menu model: level 0 items are `menu bar item`s of
    `menu bar 1`; level i (i>=1) items are `menu item`s inside
    `menu 1 of <the parent element>`. We click each level in order so each
    parent opens before its child is targeted, then the final click fires.
    """
    if not path:
        return False
    def esc(s: str) -> str:
        return s.replace('"', '\\"')

    def elem_ref(i: int) -> str:
        """Reference to the UI element path[i] itself."""
        if i == 0:
            return f'menu bar item "{esc(path[i])}" of menu bar 1'
        return f'menu item "{esc(path[i])}" of menu 1 of ' + elem_ref(i - 1)

    def click_ref(i: int) -> str:
        return f'click {elem_ref(i)}'

    lines = [f'tell application "System Events" to tell process "{FL_PROC}"']
    for i in range(len(path)):
        lines.append(f'  {click_ref(i)}')
        if i < len(path) - 1:
            lines.append('  delay 0.3')
    lines.append("end tell")
    p = subprocess.run(["osascript", "-e", "\n".join(lines)],
                       capture_output=True, text=True, timeout=20)
    if p.returncode != 0:
        return False
    time.sleep(0.5)
    return True


def ocr_dump(img: str) -> list[str]:
    """Log-friendly OCR text (for failure diagnosis)."""
    return [b.text for b in ocr_boxes(img)]


def context_menu_items(x: int, y: int) -> list[Box]:
    """Right-click at (x,y) and return the OCR boxes of the resulting
    (custom-drawn) context menu, cropped to the menu region."""
    _click(x, y, button="right")
    time.sleep(0.9)
    img = shot()
    return ocr_boxes(img)


# ------------------------------------------- matching / cascades (2026-10-01) -

# FL's hint bar (top-left, under the user name): hovering any control shows
# its name here. It is the cheapest "what is this button?" oracle.
# Only the hint row (y≈91-107, right of the PLUS badge at x<24): the badge
# and the user-name row above it OCR as noise ("Pus", "PLL5", "[name]").
HINT_BAR = (24, 90, 270, 18)
# An empty toolbar strip (top right). Clicking it closes FL's custom menus
# (Esc does NOT) without hitting anything: an open submenu can cover any
# window title bar (a title-bar dismiss once hit "Vocal denoiser").
SAFE_DISMISS = (1650, 60)


def norm_text(s: str) -> str:
    """Normalize OCR text for matching: lower case, trailing submenu arrows
    stripped, and the letter o folded into 0 (Vision reads "0MCP" as "OMCP")."""
    return s.strip().rstrip(">›").strip().lower().replace("o", "0")


def match_box(boxes: list[Box], texts: list[str] | str) -> Box | None:
    """Best OCR box for any of `texts`. Exact (normalized) matches win over
    substring matches, and substring matching skips "Edit …" rows: the
    folder "Workbench" must not hit "Edit last script: 0MCP-Workbench"."""
    wants = [norm_text(t) for t in ([texts] if isinstance(texts, str) else texts)]
    for b in boxes:
        if norm_text(b.text) in wants:
            return b
    for b in boxes:
        t = norm_text(b.text)
        if t.startswith("edit"):
            continue
        if any(len(w) > 4 and w in t for w in wants):
            return b
    return None


def frontmost_app() -> str:
    _, out, _ = osa('tell application "System Events" to get name of '
                    'first process whose frontmost is true')
    return out


FRONT_WAIT_S = 30.0


def require_fl_front(retry_focus: bool = True) -> bool:
    """True when FL is the frontmost app (focusing it once if not). Clicks
    and keys go to whatever app is in front: Chrome coming forward made an
    Add-menu click silently miss (2026-10-01)."""
    if frontmost_app() == FL_PROC:
        return True
    if retry_focus:
        # 2026-10-05: never steal focus mid-typing (the owner switched to iTerm
        # three times during a run). Wait; bring FL forward only once the user
        # has been idle ~3 s (ui_guard.wait_for_front). Max wait FRONT_WAIT_S.
        from fl_studio_mcp.utils.ui_guard import wait_for_front
        return bool(wait_for_front(timeout=FRONT_WAIT_S)["front"])
    return False


def mouse_up(x: int | None = None, y: int | None = None) -> None:
    """Send a lone mouse-up. Releases a drag FL thinks is still in progress
    (symptom: every click in FL is ignored, the engine still answers MCP)."""
    if x is None or y is None:
        subprocess.run(["cliclick", "du:."], timeout=10)
    else:
        subprocess.run(["cliclick", f"du:{x},{y}"], timeout=10)


def dismiss_menu() -> None:
    """Close an open FL custom menu by clicking the empty toolbar strip."""
    _click(*SAFE_DISMISS)
    time.sleep(0.4)


def hint_at(x: int, y: int, settle: float = 0.7) -> str:
    """Hover (x, y) and return FL's hint-bar text: names a control without
    clicking it."""
    move(x, y)
    time.sleep(settle)
    return " ".join(b.text for b in ocr_region(*HINT_BAR))


def menu_cascade(x: int, y: int, chain: list[list[str] | str],
                 button: str = "right", region: tuple[int, int, int, int] | None = None,
                 settle: float = 1.2, log=print) -> list[Box] | None:
    """Open a custom-drawn FL menu at (x, y) and walk `chain`, locating each
    level by upscaled OCR before clicking it. Returns the clicked boxes, or
    None after dismissing the menu safely (with an OCR dump in the log).

    region: the area to OCR (default: right of / below the click; FL's own
    menu bar also has items like "Tools" at y≈14 that must never match).
    """
    rx, ry = max(0, x - 40), max(0, y - 400)
    region = region or (rx, ry, 1920 - rx, 1080 - ry)
    _click(x, y, button=button)
    time.sleep(settle)
    clicked: list[Box] = []
    for level, texts in enumerate(chain):
        boxes = ocr_region(*region)
        b = match_box(boxes, texts)
        if b is None:
            shot("/tmp/fl_menu_fail.png")
            log(f"menu level {level} {texts!r}: not found "
                "(shot: /tmp/fl_menu_fail.png); OCR saw:")
            for bb in boxes:
                log(f"    {bb.x:5d} {bb.y:5d}  {bb.text!r}")
            dismiss_menu()
            return None
        log(f"menu level {level}: {b.text!r} at ({b.cx},{b.cy})")
        _click(b.cx, b.cy)
        clicked.append(b)
        time.sleep(settle)
    return clicked

#!/usr/bin/env python3
"""screen.py — look at the screen and drive the mouse the way the agent does.

One CLI over fl_studio_mcp.utils.custom_menu. The method is always:
LOOK (screenshot) -> READ (OCR, upscaled) -> LOCATE (match text -> coords)
-> ACT (click) -> VERIFY (look again). Never click a coordinate you have not
just read off the screen. Guide: docs/SCREEN-CONTROL.md.

    uv run python scripts/screen.py look                      # screenshot -> /tmp/screen.png
    uv run python scripts/screen.py ocr --region 700,470,520,170
    uv run python scripts/screen.py find "Edison (Master" --dim
    uv run python scripts/screen.py hint 838 711              # what is this button?
    uv run python scripts/screen.py click-text OK --region 700,470,520,170
    uv run python scripts/screen.py menu 555 544 Tools "Run script" Workbench 0MCP-Workbench
    uv run python scripts/screen.py mouse-up                  # FL ignores all clicks? try this

Every command that clicks or types first checks that FL Studio is the
frontmost app (pass --any-app to drive another app) and supports --dry-run
(locate and print, do not act).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fl_studio_mcp.utils import custom_menu as cm  # noqa: E402

FULL = (0, 0, 1920, 1080)


def _region(s: str | None) -> tuple[int, int, int, int] | None:
    if not s:
        return None
    try:
        x, y, w, h = (int(v) for v in s.split(","))
    except ValueError:
        raise SystemExit(f"--region wants x,y,w,h (got {s!r})")
    return (x, y, w, h)


def _boxes(region, scale: int, dim: bool):
    """OCR boxes: full screen at 1x unless a region / --dim asks for upscaling
    (small or dimmed text — menus, unfocused titles, the OK button — needs it)."""
    if region is None and not dim:
        return cm.ocr_boxes(cm.shot())
    return cm.ocr_region(*(region or FULL), scale=scale if region else 2)


def _guard(args) -> None:
    if args.any_app or args.dry_run:
        return
    if not cm.require_fl_front():
        raise SystemExit(f"refusing: frontmost app is {cm.frontmost_app()!r}, "
                         "not FL Studio (focus it, or pass --any-app)")


def cmd_look(a):
    if a.fl_window:
        out = cm.fl_window_shot(a.out)
        if out is None:
            raise SystemExit("FL's main window not found (is FL running?)")
        print(out)
        return
    print(cm.shot(a.out))


def cmd_ocr(a):
    for b in _boxes(_region(a.region), a.scale, a.dim):
        if a.grep and a.grep.lower() not in b.text.lower():
            continue
        print(f"{b.x:5d} {b.y:5d} {b.w:4d} {b.h:3d}  center=({b.cx},{b.cy})  {b.text}")


def cmd_find(a):
    b = cm.match_box(_boxes(_region(a.region), a.scale, a.dim), a.text)
    if b is None:
        raise SystemExit(f"not found: {a.text!r} (try --dim or a --region)")
    print(f"{b.cx} {b.cy}  # {b.text!r}")


def cmd_hint(a):
    print(cm.hint_at(a.x, a.y) or "(no hint)")


def cmd_click(a):
    _guard(a)
    print(f"{a.button}{' double' if a.double else ''} click at ({a.x},{a.y})")
    if not a.dry_run:
        cm._click(a.x, a.y, double=a.double, button=a.button)


def cmd_click_text(a):
    _guard(a)
    b = cm.match_box(_boxes(_region(a.region), a.scale, a.dim), a.text)
    if b is None:
        raise SystemExit(f"not found: {a.text!r} — nothing clicked")
    print(f"found {b.text!r} at ({b.cx},{b.cy})")
    if not a.dry_run:
        cm._click(b.cx, b.cy, double=a.double, button=a.button)


def cmd_menu(a):
    _guard(a)
    if a.dry_run:
        print(f"would {a.button}-click ({a.x},{a.y}) then walk {a.chain}")
        return
    clicked = cm.menu_cascade(a.x, a.y, a.chain, button=a.button,
                              region=_region(a.region))
    if clicked is None:
        raise SystemExit("menu walk failed (menu dismissed; see OCR dump above)")


def cmd_menubar(a):
    _guard(a)
    print("ok" if cm.menu_bar_click(*a.path) else "failed")


def cmd_move(a):
    cm.move(a.x, a.y)


def cmd_key(a):
    _guard(a)
    if not a.dry_run:
        cm.keypress(a.name)


def cmd_type(a):
    _guard(a)
    if not a.dry_run:
        cm.type_text(a.text)


def cmd_mouse_up(a):
    cm.mouse_up()
    print("sent mouse-up")


def cmd_dismiss(a):
    _guard(a)
    cm.dismiss_menu()


def cmd_focus(a):
    cm.focus_fl()
    time.sleep(0.5)
    print(cm.frontmost_app())


def cmd_front(a):
    print(cm.frontmost_app())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        p = sub.add_parser(name, help=help_)
        p.set_defaults(fn=fn)
        p.add_argument("--any-app", action="store_true",
                       help="allow acting when FL is not frontmost")
        p.add_argument("--dry-run", action="store_true",
                       help="locate and print, do not click/type")
        return p

    def ocr_opts(p):
        p.add_argument("--region", help="x,y,w,h screen area to OCR (upscaled)")
        p.add_argument("--scale", type=int, default=3, help="upscale for --region")
        p.add_argument("--dim", action="store_true",
                       help="upscale the full screen 2x (dim/small text)")

    def mouse_opts(p):
        p.add_argument("--right", dest="button", action="store_const",
                       const="right", default="left")
        p.add_argument("--double", action="store_true")

    p = add("look", cmd_look, "screenshot (open it to see the screen)")
    p.add_argument("--out", default="/tmp/screen.png")
    p.add_argument("--fl-window", action="store_true",
                   help="capture only FL's window, even behind other apps")
    p = add("ocr", cmd_ocr, "list text boxes with coordinates")
    ocr_opts(p)
    p.add_argument("--grep", help="only rows containing this text")
    p = add("find", cmd_find, "print the center of the best text match")
    p.add_argument("text")
    ocr_opts(p)
    p = add("hint", cmd_hint, "hover x y and read FL's hint bar")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p = add("click", cmd_click, "click a coordinate")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    mouse_opts(p)
    p = add("click-text", cmd_click_text, "find text by OCR, click its center")
    p.add_argument("text")
    ocr_opts(p)
    mouse_opts(p)
    p = add("menu", cmd_menu, "open a custom menu at x y and walk a chain")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p.add_argument("chain", nargs="+")
    p.add_argument("--left", dest="button", action="store_const",
                   const="left", default="right")
    p.add_argument("--region", help="x,y,w,h area the menu opens in")
    p = add("menubar", cmd_menubar, "click a macOS menu-bar path (native)")
    p.add_argument("path", nargs="+")
    p = add("move", cmd_move, "move the pointer (no click)")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p = add("key", cmd_key, "press a named key (esc, return, arrow-down, …)")
    p.add_argument("name")
    p = add("type", cmd_type, "type text (US layout, CGEvent)")
    p.add_argument("text")
    add("mouse-up", cmd_mouse_up, "release a stuck drag")
    add("dismiss", cmd_dismiss, "close an open FL custom menu safely")
    add("focus", cmd_focus, "bring FL Studio to the front")
    add("front", cmd_front, "print the frontmost app")

    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()

"""fl_screen — vision for agents: see FL and act on what is ON SCREEN (macOS Vision OCR).

The same OCR the internal tools use (scripts/ocr_text.swift via utils/custom_menu),
exposed as one MCP tool so any agent can look, read, find and click without custom
scripts. Built 2026-10-06 (owner request). Speed rules learned live:
  * OCR a REGION, not the whole screen, when you know where to look;
  * small / dense / grey text (1-letter preset names, 4-column menus) reads only
    ZOOMED, in TILES ~150 px tall (a tall zoomed strip makes Vision skip lines);
  * the hint bar names a control without clicking it (`hint`).

Actions
  look([fl_window])                    -> screenshot path (+ size)
  ocr([region x,y,w,h], [zoom], [tile]) -> [{text, x, y, w, h, cx, cy}]
  find(text, [region], [zoom])          -> best matches (OCR-tolerant), auto-zoom retry
  hint(x, y)                            -> FL hint-bar text at that point (hover only)
  click_text(text, [region], [double], [button])
                                        -> find + click; refuses unless FL is frontmost
"""
from __future__ import annotations

import difflib
import re
from typing import Any

from fastmcp import FastMCP

ACTIONS = ("look", "ocr", "find", "hint", "click_text")


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _box(b) -> dict:
    return {"text": b.text, "x": b.x, "y": b.y, "w": b.w, "h": b.h, "cx": b.cx, "cy": b.cy}


def _read(img: str, region: list[int] | None, zoom: int, tile: int) -> list:
    from fl_studio_mcp.utils import custom_menu as cm
    from fl_studio_mcp.utils.plugin_preset_ui import zoom_ocr
    if not region:
        boxes = cm.ocr_boxes(img)
        return boxes if zoom <= 1 else boxes        # whole screen: plain read
    x, y, w, h = (int(v) for v in region)
    if zoom <= 1:
        return [b for b in cm.ocr_boxes(img) if x <= b.cx <= x + w and y <= b.cy <= y + h]
    out, ty = [], y
    step = max(40, tile - 20) if tile else h
    while ty < y + h:
        out += zoom_ocr(img, (x, ty, w, min(tile or h, y + h - ty)), scale=zoom)
        ty += step
    uniq: list = []
    for b in out:                                   # overlapping tiles read rows twice
        if not any(_key(b.text) == _key(u.text) and abs(b.cy - u.cy) <= 10 for u in uniq):
            uniq.append(b)
    return uniq


def _score(seen: str, want: str) -> float:
    a, b = _key(seen), _key(want)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if b in a:
        return 0.9
    return difflib.SequenceMatcher(None, a, b).ratio()


def fl_screen(action: str, **p: Any) -> dict:
    from fl_studio_mcp.utils import custom_menu as cm
    if action not in ACTIONS:
        return {"success": False, "error": f"unknown action {action!r}", "valid_actions": list(ACTIONS)}
    try:
        if action == "hint":
            if p.get("x") is None or p.get("y") is None:
                return {"success": False, "error": "hint: x and y required"}
            return {"action": action, "success": True,
                    "hint": cm.hint_at(int(p["x"]), int(p["y"]))}
        if action == "look":
            if p.get("fl_window"):
                import subprocess
                import sys
                from pathlib import Path
                root = Path(__file__).resolve().parents[3]
                out = "/tmp/fl_screen_window.png"
                subprocess.run([sys.executable, str(root / "scripts" / "screen.py"), "look",
                                "--fl-window", "--out", out], capture_output=True, timeout=30)
                return {"action": action, "success": Path(out).exists(), "path": out}
            path = cm.shot("/tmp/fl_screen.png")
            return {"action": action, "success": True, "path": path,
                    "frontmost": cm.frontmost_app()}
        region = p.get("region")
        zoom = int(p.get("zoom") or 1)
        tile = int(p.get("tile") or (150 if zoom > 1 else 0))
        img = cm.shot("/tmp/fl_screen.png")
        if action == "ocr":
            boxes = _read(img, region, zoom, tile)
            return {"action": action, "success": True, "count": len(boxes),
                    "boxes": [_box(b) for b in sorted(boxes, key=lambda b: (b.cy, b.cx))][:400]}
        want = str(p.get("text") or "")
        if not want.strip():
            return {"success": False, "error": f"{action}: text required"}
        boxes = _read(img, region, zoom, tile)
        best = sorted(((round(_score(b.text, want), 3), b) for b in boxes),
                      key=lambda t: -t[0])
        best = [(s, b) for s, b in best if s >= 0.8]
        if not best and region and zoom <= 1:       # auto-zoom retry on a region
            boxes = _read(img, region, 3, 150)
            best = [(s, b) for s, b in sorted(((round(_score(b.text, want), 3), b) for b in boxes),
                                               key=lambda t: -t[0]) if s >= 0.8]
        matches = [{"score": s, **_box(b)} for s, b in best[:10]]
        if action == "find":
            return {"action": action, "success": bool(matches), "matches": matches,
                    **({} if matches else {"error": f"{want!r} not on screen (try region + zoom)"})}
        # click_text
        if not matches:
            return {"action": action, "success": False, "error": f"{want!r} not on screen"}
        if len([m for m in matches if m["score"] >= matches[0]["score"] - 0.01]) > 1:
            return {"action": action, "success": False, "matches": matches,
                    "error": "ambiguous: several equally good matches; pass a region"}
        if not cm.require_fl_front(retry_focus=False):
            return {"action": action, "success": False,
                    "error": f"FL not frontmost ({cm.frontmost_app()!r}); nothing clicked"}
        m = matches[0]
        cm._click(m["cx"], m["cy"], double=bool(p.get("double")),
                  button=str(p.get("button") or "left"))
        return {"action": action, "success": True, "clicked": m}
    except Exception as e:
        return {"action": action, "success": False, "error": str(e)}


def register_screen_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def fl_screen(
        action: str,
        text: str | None = None,
        region: list[int] | None = None,
        zoom: int | None = None,
        tile: int | None = None,
        x: int | None = None,
        y: int | None = None,
        double: bool | None = None,
        button: str | None = None,
        fl_window: bool | None = None,
    ) -> dict:
        """Vision on FL's screen (macOS OCR): look | ocr | find | hint | click_text.

        look([fl_window]) -> screenshot path. ocr([region=[x,y,w,h]], [zoom=3],
        [tile=150]) -> text boxes with coordinates; zoom small/dense text (tiles keep
        tall regions readable). find(text, [region], [zoom]) -> OCR-tolerant matches,
        auto-zoom retry on a region. hint(x, y) -> FL hint-bar text (hover only, names
        a control). click_text(text, [region], [double], [button=left|right]) -> find
        + click; refuses when FL is not frontmost or the match is ambiguous.
        Prefer FL's API tools for state; use this to SEE and for UI-only controls.
        """
        args = {k: v for k, v in locals().items() if k != "action" and v is not None}
        from fl_studio_mcp.tools.screen_v2 import fl_screen as _impl
        return _impl(action, **args)

"""C3: write notes into an EXISTING channel via the piano roll's own
File > Import MIDI file (proven live 2026-10-01; route in DEV-TASKS.md C3).

Why this exists: it writes a whole phrase from a standard .mid with no
ComposeWithLLM queue. It is the UI-heaviest note path, so every step is
located by what is ON SCREEN (macOS Vision OCR with boxes) and verified by
the next observation — never by fixed pixel offsets alone:

  1. retarget the roll to the channel (roll_session.open_roll_for_channel —
     screen-title proof), optionally after selecting the pattern;
  2. open the roll's ▸ menu: click left of the OCR'd roll title; accept only
     if ui.isInPopupMenu = 1 AND OCR shows the roll menu ("Target channel");
     otherwise Escape and refuse;
  3. hover the OCR'd "File" row, click the OCR'd "Import MIDI file" row;
  4. the NATIVE Open panel appears (System Events window "Open"): Cmd+Shift+G,
     set the go-to field by ACCESSIBILITY (typed keystrokes drop digits; Return
     and a single click don't confirm), DOUBLE-click the last suggestion row
     (row 1 is the "Go to:" header) -> the sheet closes with the file selected,
     then click the OCR'd "Open" button next to "Cancel";
  5. wait for the panel to close (FL imports; the roll closes).
Import REPLACES the channel's notes in the active pattern (live: 4 notes ->
exactly the 2 imported).
The caller verifies the result by reading the roll back.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from fl_studio_mcp.utils import roll_session as rs

FL_PROC = rs.FL_PROC
_MIDI_DIR = rs._REPO / ".generated" / "midi"
# ▸ menu arrow sits this many points left of the OCR'd roll-title box
# (measured on the PE 1920-pt layout: title box x=1339, arrow x=1010).
TITLE_TO_ARROW_DX = 329


# --------------------------------------------------------------------- MIDI

def write_midi(notes: list[dict], name: str = "import", bpm: float = 120.0,
               ppq: int = 96) -> Path:
    """notes: [{midi, time (beats), duration (beats), velocity 0-1}] -> .mid"""
    import mido
    events: list[tuple[int, int, int, int]] = []  # (tick, order, note, vel)
    for n in notes:
        on = int(round(float(n.get("time", 0)) * ppq))
        off = on + max(1, int(round(float(n["duration"]) * ppq)))
        vel = max(1, min(127, int(round(float(n.get("velocity", 0.8)) * 127))))
        events.append((on, 1, int(n["midi"]), vel))
        events.append((off, 0, int(n["midi"]), 0))  # offs sort before ons
    events.sort()
    mid = mido.MidiFile(ticks_per_beat=ppq)
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))
    last = 0
    for tick, _, note, vel in events:
        kind = "note_on" if vel else "note_off"
        tr.append(mido.Message(kind, note=note, velocity=vel, time=tick - last))
        last = tick
    _MIDI_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", name) or "import"
    path = _MIDI_DIR / f"{safe}.mid"
    mid.save(str(path))
    return path


# ---------------------------------------------------------------- screen I/O

def _screen_scale() -> float:
    try:
        out = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e",
             'ObjC.import("AppKit"); $.NSScreen.mainScreen.backingScaleFactor'],
            capture_output=True, text=True, timeout=5).stdout.strip()
        return float(out) or 1.0
    except Exception:  # noqa: BLE001
        return 1.0


def ocr_boxes() -> list[dict]:
    """Every text line on the main screen with its box in SCREEN POINTS."""
    ocr = rs._ocr_bin()
    if ocr is None:
        return []
    scale = _screen_scale()
    with tempfile.TemporaryDirectory() as d:
        shot = Path(d) / "screen.png"
        subprocess.run(["screencapture", "-x", "-m", str(shot)],
                       capture_output=True, timeout=10)
        if not shot.exists():
            return []
        out = subprocess.run([str(ocr), str(shot), "--boxes"], capture_output=True,
                             text=True, timeout=30).stdout
    boxes = []
    for line in out.splitlines():
        if line.startswith("#"):
            continue
        parts = line.split("\t", 4)
        if len(parts) != 5:
            continue
        x, y, w, h = (int(v) / scale for v in parts[:4])
        boxes.append({"x": x, "y": y, "w": w, "h": h, "text": parts[4],
                      "cx": x + w / 2, "cy": y + h / 2})
    return boxes


def find(boxes: list[dict], pattern: str, near: tuple[float, float] | None = None,
         below_y: float | None = None) -> dict | None:
    """First box whose text matches `pattern` (case-insensitive); nearest to
    `near` when several match; optionally only boxes below `below_y`."""
    rx = re.compile(pattern, re.I)
    hits = [b for b in boxes if rx.search(b["text"])
            and (below_y is None or b["cy"] > below_y)]
    if not hits:
        return None
    if near:
        hits.sort(key=lambda b: (b["cx"] - near[0]) ** 2 + (b["cy"] - near[1]) ** 2)
    return hits[0]


def _click(x: float, y: float) -> None:
    from fl_studio_mcp.tools.select_script import _click as ss_click
    ss_click(int(round(x)), int(round(y)))


def _dclick(x: float, y: float) -> None:
    from fl_studio_mcp.tools.select_script import CLICLICK, _run
    _run([CLICLICK, f"dc:{int(round(x))},{int(round(y))}"], timeout=5)


def _move(x: float, y: float) -> None:
    from fl_studio_mcp.tools.select_script import _move as ss_move
    ss_move(int(round(x)), int(round(y)))


def _menu_open() -> bool | None:
    from fl_studio_mcp.tools.select_script import _menu_open as ss_menu_open
    return ss_menu_open()


def _escape_menu() -> None:
    from fl_studio_mcp.tools.select_script import _send_keyseq
    _send_keyseq(["escape"])


def _osa(script: str, timeout: float = 15.0) -> tuple[int, str]:
    p = subprocess.run(["osascript", "-e", script], capture_output=True,
                       text=True, timeout=timeout)
    return p.returncode, (p.stdout.strip() or p.stderr.strip())


def _open_panel_exists() -> bool:
    rc, out = _osa(f'tell application "System Events" to tell process "{FL_PROC}" '
                   'to get name of every window')
    return rc == 0 and "Open" in [w.strip() for w in out.split(",")]


def _wait(pred, timeout: float, step: float = 0.3) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(step)
    return pred()


# --------------------------------------------------------------- the flow

def open_roll_menu(title_box: dict) -> dict[str, Any]:
    """Click the roll's ▸ menu arrow and prove the ROLL menu opened."""
    candidates = [(title_box["x"] - TITLE_TO_ARROW_DX, title_box["cy"])]
    for x, y in candidates:
        rs._activate_fl()
        _click(x, y)
        time.sleep(1.0)
        if _menu_open() is True:
            boxes = ocr_boxes()
            if find(boxes, r"^target channel"):
                return {"ok": True, "arrow": [round(x), round(y)], "boxes": boxes}
            _escape_menu()  # some other menu opened (e.g. the wrench's)
            time.sleep(0.4)
    return {"ok": False, "error": ("could not open the piano roll's ▸ menu (no popup "
                                   "with 'Target channel' after clicking left of the "
                                   "roll title)")}


def import_midi_file(channel_index: int, mid_path: Path) -> dict[str, Any]:
    """Run steps 1-5 for an existing .mid. Never sends keys without proof."""
    steps: list[str] = []
    roll = rs.open_roll_for_channel(int(channel_index))
    if not roll.get("ok"):
        return {"ok": False, "error": roll.get("error"), "steps": steps}
    steps.append(f"roll on '{roll.get('roll')}' (screen title)")

    title = find(ocr_boxes(), r"piano\s*roll\s*-")
    if not title:
        return {"ok": False, "error": "roll title not found on screen", "steps": steps}

    menu = open_roll_menu(title)
    if not menu.get("ok"):
        return {"ok": False, "error": menu["error"], "steps": steps}
    steps.append(f"roll menu open (arrow at {menu['arrow']})")

    file_row = find(menu["boxes"], r"^file$", near=tuple(menu["arrow"]))
    if not file_row:
        _escape_menu()
        return {"ok": False, "error": "'File' row not found in the roll menu", "steps": steps}
    _move(file_row["cx"], file_row["cy"])
    time.sleep(0.9)
    imp = find(ocr_boxes(), r"import midi file")
    if not imp:
        _escape_menu()
        return {"ok": False, "error": "'Import MIDI file' not shown under File", "steps": steps}
    _move(imp["cx"], file_row["cy"])          # slide right along the File row first
    time.sleep(0.3)
    _move(imp["cx"], imp["cy"])
    time.sleep(0.3)
    _click(imp["cx"], imp["cy"])
    if not _wait(_open_panel_exists, 6.0):
        return {"ok": False, "error": "the native Open panel did not appear", "steps": steps}
    steps.append("native Open panel up")

    from fl_studio_mcp.utils.open_panel import drive_open_panel
    r = drive_open_panel(str(mid_path))
    if not r["ok"]:
        return {"ok": False, "error": r["error"], "steps": steps}
    steps.append(f"imported {mid_path.name}")
    time.sleep(1.0)
    return {"ok": True, "steps": steps, "file": str(mid_path)}


def _cancel_open_panel() -> None:
    _osa(f'tell application "System Events" to tell process "{FL_PROC}" to '
         'key code 53')  # Esc closes the native panel / sheet
    time.sleep(0.5)
    if _open_panel_exists():
        _osa(f'tell application "System Events" to tell process "{FL_PROC}" to '
             'key code 53')

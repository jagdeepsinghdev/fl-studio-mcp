"""Drive FL's native macOS Open panel to a file (proven in C3 Import MIDI,
2026-10-01): Cmd+Shift+G -> set the go-to field by ACCESSIBILITY (typed
digits drop) -> double-click the resolved suggestion row -> Open -> the
panel must close. Shared by import_midi and sampler_load. The caller opens
the panel; this never types into anything but the panel's own sheet.
"""

from __future__ import annotations

import re
import time
from typing import Any

from fl_studio_mcp.utils.import_midi import (
    FL_PROC,
    _cancel_open_panel,
    _click,
    _dclick,
    _osa,
    _wait,
    find,
    ocr_boxes,
)


def open_panel_name() -> str | None:
    """Name of FL's native Open panel: 'Open' (Import MIDI) or 'Open sound
    file(s)' (Sampler 'Load sample file') — any window starting 'Open'."""
    rc, out = _osa(f'tell application "System Events" to tell process "{FL_PROC}" '
                   'to get name of every window')
    if rc != 0:
        return None
    return next((w.strip() for w in out.split(",") if w.strip().startswith("Open")), None)


def drive_open_panel(path: str) -> dict[str, Any]:
    """The panel must already be open. Returns {"ok", "error"?, "file"}."""
    win = open_panel_name()
    if win is None:
        return {"ok": False, "error": "no native Open panel is open"}
    path = str(path)
    _osa(f'tell application "System Events" to tell process "{FL_PROC}"\n'
         '  set frontmost to true\n  delay 0.3\n'
         '  keystroke "g" using {command down, shift down}\nend tell')
    sheet = (f'sheet 1 of window "{win}" of process "{FL_PROC}"')
    ok_sheet = _wait(lambda: _osa(f'tell application "System Events" to get exists {sheet}')[1]
                     == "true", 4.0)
    if not ok_sheet:
        _cancel_open_panel()
        return {"ok": False, "error": "Go-to-folder sheet did not open"}
    esc = path.replace("\\", "\\\\").replace('"', '\\"')
    _osa(f'tell application "System Events" to set value of text field 1 of {sheet} to "{esc}"')
    rc, val = _osa(f'tell application "System Events" to get value of text field 1 of {sheet}')
    if val != path:
        _cancel_open_panel()
        return {"ok": False, "error": f"go-to path not set (got {val!r})"}
    # Rows: [0] is the "Go to:" header, the LAST row is the resolved file.
    # Live 2026-10-01: a single click on it did nothing; a DOUBLE-click closes
    # the sheet and selects the file in the panel; then the Open button.
    # 2026-10-02: a fixed 1.0 s wait was sometimes too short — the row was
    # double-clicked before it resolved. Wait (≤ 4 s) until the last row
    # names the file, and retry the double-click once.
    from pathlib import Path as _P
    fname = _P(path).name

    def last_row():
        rc, txt = _osa('tell application "System Events" to get value of static text 1 of '
                       f'UI element 1 of last row of table 1 of scroll area 1 of {sheet}')
        rc2, pos = _osa('tell application "System Events" to get {position, size} of last row of '
                        f'table 1 of scroll area 1 of {sheet}')
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", pos)] if rc2 == 0 else []
        return (txt if rc == 0 else ""), nums

    def sheet_gone():
        return _osa(f'tell application "System Events" to get exists {sheet}')[1] == "false"

    nums: list[float] = []
    end = time.time() + 4.0
    while time.time() < end:
        txt, nums = last_row()
        if len(nums) == 4 and (fname in txt or not txt):
            break
        time.sleep(0.25)
    if len(nums) != 4:
        _cancel_open_panel()
        return {"ok": False, "error": "no suggestion row for the path"}
    for _ in range(2):
        _dclick(nums[0] + nums[2] / 2, nums[1] + nums[3] / 2)
        if _wait(sheet_gone, 3.0):
            break
    else:
        _cancel_open_panel()
        return {"ok": False, "error": "the go-to sheet did not resolve the file"}
    if open_panel_name() is None:        # the double-click loaded it directly
        return {"ok": True, "file": path}
    time.sleep(0.6)
    boxes = ocr_boxes()
    cancel = find(boxes, r"^cancel$")
    open_btn = find(boxes, r"^open$", near=(cancel["cx"], cancel["cy"]) if cancel else None,
                    below_y=(cancel["cy"] - 20) if cancel else None)
    if not open_btn:
        _cancel_open_panel()
        return {"ok": False, "error": "Open button not found in the panel"}
    _click(open_btn["cx"], open_btn["cy"])
    if not _wait(lambda: not (open_panel_name() is not None), 8.0):
        _cancel_open_panel()
        return {"ok": False, "error": "Open panel did not close after pressing Open",
                }
    return {"ok": True, "file": path}

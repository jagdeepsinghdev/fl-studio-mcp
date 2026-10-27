"""Drive FL's native macOS SAVE panel to an exact path (companion of open_panel.py).

Used by mixer track state saving (fl_vocal save_state). Same rules as the Open
panel (C3, 2026-10-01): set fields by ACCESSIBILITY (typed digits drop), never
type into anything but the panel; the ORACLE is the file appearing on disk.

  1. the caller opened the panel (a window whose name starts with "Save");
  2. Cmd+Shift+G -> go-to sheet -> folder path set by AX -> double-click the
     resolved row (Return did not confirm in the Open panel) -> sheet closes;
  3. the "Save As" name field set by AX;
  4. click the panel's Save button by AX; a "Replace?" sheet -> Replace;
  5. wait until the file exists (and is newer than before) -> ok.
Built 2026-10-05; NOT live-verified yet.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from fl_studio_mcp.utils.import_midi import FL_PROC, _dclick, _osa, _wait


def save_panel_name() -> str | None:
    rc, out = _osa(f'tell application "System Events" to tell process "{FL_PROC}" '
                   'to get name of every window')
    if rc != 0:
        return None
    return next((w.strip() for w in out.split(",") if w.strip().lower().startswith("save")), None)


def _cancel(win: str) -> None:
    _osa(f'tell application "System Events" to tell process "{FL_PROC}" to key code 53')
    time.sleep(0.5)
    if save_panel_name():
        _osa(f'tell application "System Events" to tell process "{FL_PROC}" to key code 53')


def drive_save_panel(path: str, overwrite: bool = True) -> dict[str, Any]:
    win = save_panel_name()
    if win is None:
        return {"ok": False, "error": "no native Save panel is open"}
    target = Path(path).expanduser()
    folder, fname = str(target.parent), target.name
    mtime0 = target.stat().st_mtime if target.exists() else 0.0
    W = f'window "{win}" of process "{FL_PROC}"'
    sheet = f"sheet 1 of {W}"

    # 2. go to the folder
    _osa(f'tell application "System Events" to tell process "{FL_PROC}"\n'
         '  set frontmost to true\n  delay 0.3\n'
         '  keystroke "g" using {command down, shift down}\nend tell')
    if not _wait(lambda: _osa(f'tell application "System Events" to get exists {sheet}')[1]
                 == "true", 4.0):
        _cancel(win)
        return {"ok": False, "error": "Go-to-folder sheet did not open"}
    esc = folder.replace("\\", "\\\\").replace('"', '\\"')
    _osa(f'tell application "System Events" to set value of text field 1 of {sheet} to "{esc}"')
    rc, val = _osa(f'tell application "System Events" to get value of text field 1 of {sheet}')
    if val.rstrip("/") != folder.rstrip("/"):
        _cancel(win)
        return {"ok": False, "error": f"go-to folder not set (got {val!r})"}

    def last_row():
        rc2, pos = _osa('tell application "System Events" to get {position, size} of last row of '
                        f'table 1 of scroll area 1 of {sheet}')
        return [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", pos)] if rc2 == 0 else []

    nums: list[float] = []
    end = time.time() + 4.0
    while time.time() < end and len(nums) != 4:
        nums = last_row()
        time.sleep(0.25)
    if len(nums) != 4:
        _cancel(win)
        return {"ok": False, "error": "no suggestion row for the folder"}
    for _ in range(2):
        _dclick(nums[0] + nums[2] / 2, nums[1] + nums[3] / 2)
        if _wait(lambda: _osa(f'tell application "System Events" to get exists {sheet}')[1]
                 == "false", 3.0):
            break
    else:
        _cancel(win)
        return {"ok": False, "error": "the go-to sheet did not resolve the folder"}

    # 3. the file name
    nm = fname.replace("\\", "\\\\").replace('"', '\\"')
    _osa(f'tell application "System Events" to set value of text field 1 of {W} to "{nm}"')
    rc, got = _osa(f'tell application "System Events" to get value of text field 1 of {W}')
    if got != fname:
        _cancel(win)
        return {"ok": False, "error": f"file name not set (got {got!r})"}

    # 4. Save (+ Replace when the file exists)
    _osa(f'tell application "System Events" to click button "Save" of {W}')
    time.sleep(0.8)
    if _osa(f'tell application "System Events" to get exists {sheet}')[1] == "true":
        if not overwrite:
            _cancel(win)
            return {"ok": False, "error": f"{fname} exists (overwrite=false)"}
        _osa(f'tell application "System Events" to click button "Replace" of {sheet}')

    # 5. the oracle: the file on disk
    if not _wait(lambda: target.exists() and target.stat().st_mtime > mtime0, 8.0):
        if save_panel_name():
            _cancel(win)
        return {"ok": False, "error": f"{target} did not appear on disk"}
    return {"ok": True, "file": str(target), "bytes": target.stat().st_size}

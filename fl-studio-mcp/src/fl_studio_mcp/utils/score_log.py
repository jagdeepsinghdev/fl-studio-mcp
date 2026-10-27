"""Score log -> pattern ("Tools > Dump score log to selected pattern"), guarded.

Tip 8 of "10 things in FL Studio": FL keeps a log of the notes PLAYED IN (MIDI
keyboard / pads) even when not recording; dumping the last N seconds into the
selected pattern rescues a take you didn't record.

API: general.dumpScoreLog(time_seconds, silent). Live 2026-10-06: with an EMPTY
log FL opens a modal "Warning" dialog even with silent=1, and the controller
stops answering until it is dismissed. So: dump with a short timeout, then look
for FL's dialog window; if it is there, dismiss it (Enter, FL frontmost only)
and report "score log empty" instead of hanging.
"""
from __future__ import annotations

import time
from typing import Any


def capture(conn, seconds: int = 60, target_pattern: int | None = None) -> dict[str, Any]:
    from fl_studio_mcp.utils import ui_guard as g
    out: dict[str, Any] = {"action": "capture", "seconds": int(seconds)}
    if target_pattern:
        st, info = g._try_exec(conn, f"import patterns\npatterns.jumpToPattern({int(target_pattern)})\nprint(1)")
        if st != "ok":
            return {**out, "success": False, "error": f"select pattern: {info}"}
    _, u0 = g._try_exec(conn, "import general\nprint(general.getUndoHistoryCount())")
    st, info = g._try_exec(conn, f"import general, patterns\ngeneral.dumpScoreLog({int(seconds)}, 1)\n"
                                 "print(patterns.patternNumber())", timeout=4.0)
    time.sleep(0.6)
    dialogs = [t for t in g.fl_window_titles() if t.startswith(("Warning", "Information"))]
    # live 2026-10-06 (2nd run): the Warning was NOT listed as an OS window, yet it
    # blocked the controller -> a timeout IS the signal; dismiss either way.
    if st == "timeout" and not dialogs:
        dialogs = ["Warning"]
    if dialogs:
        # the PROVEN dismissal for this exact dialog (lifecycle dismiss_modal: activate
        # FL, verify frontmost, Enter, poll the controller). A plain Return keypress
        # did not close it (live 2026-10-06).
        from fl_studio_mcp.tools.lifecycle_v2 import _action_dismiss_modal
        g.wait_for_front(timeout=20)
        dm = _action_dismiss_modal(dialogs[0].split()[0], "enter", 3)
        closed = bool(dm.get("success"))
        return {**out, "success": False, "empty": True, "dialog_dismissed": bool(closed),
                "error": "the score log is empty (nothing was played in) - FL's warning was "
                         + ("dismissed" if closed else "NOT dismissed: bring FL to the front and press Enter")}
    if st != "ok":
        return {**out, "success": False, "error": info}
    # proof: a real dump adds ONE undo step (live 2026-10-06: 3 played notes -> +1);
    # no dialog AND no undo step = nothing was dumped (never report that as success)
    _, u1 = g._try_exec(conn, "import general\nprint(general.getUndoHistoryCount())")
    try:
        delta = int(u1.strip().splitlines()[-1]) - int(u0.strip().splitlines()[-1])
    except Exception:
        delta = None
    out["undo_delta"] = delta
    if delta is not None and delta < 1:
        return {**out, "success": False, "empty": True,
                "error": "nothing was dumped (no undo step): the score log is probably empty"}
    out.update(success=True, pattern=info.strip().splitlines()[-1] if info else None,
               note="score log dumped into the selected pattern (each played channel)")
    return out

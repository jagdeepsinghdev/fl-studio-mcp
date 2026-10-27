"""UI guard — the safety + recovery layer every screen-driving action runs through.

Built 2026-10-05 from one live session's failures (each one is a rule here):
  * the plugin picker left open      -> FL refuses every probe.exec ("Operation unsafe")
  * an FL "Error" dialog left open    -> same refusal, everything after it fails
  * a preset MENU left open           -> Escape does NOT close it; the next OCR read
                                         a menu item as a header label and clicked it
  * the owner switched to iTerm       -> clicks/keys would land in THEIR app
  * ~350 queued Patcher preset loads  -> main thread busy for minutes, every call times out

API (all take the shared MIDI connection; nothing here clicks unless FL is frontmost):
  diagnose(conn)            -> what blocks FL right now (+ advice). Read-only.
  recover(conn, ...)        -> clear the blockers it can (picker, dialog, popup, busy wait)
  wait_for_front(...)       -> FL frontmost? waits for the owner; brings FL forward ONLY
                               after the user has been idle `idle_s` seconds (no focus
                               stealing while someone types)
  ensure_ready(conn, ...)   -> recover + (optionally) wait_for_front; one dict verdict
  is_blocked_error(err)     -> True for "Operation unsafe" / controller timeouts
"""
from __future__ import annotations

import re
import subprocess
import time
from typing import Any, Callable

from fl_studio_mcp.utils import custom_menu as cm

PICKER = "Select effect plugin"
#: FL-drawn dialog window titles that block the controller until dismissed.
DIALOG_TITLES = ("Error", "Warning", "Confirm", "Information", "Question")
BLOCK_PATTERNS = ("operation unsafe", "timeout waiting for fl studio")


def is_blocked_error(err: Any) -> bool:
    e = str(err or "").lower()
    return any(p in e for p in BLOCK_PATTERNS)


# ------------------------------------------------------------------ OS-level reads

def user_idle_seconds() -> float:
    """Seconds since the last keyboard/mouse input (IOHIDSystem HIDIdleTime)."""
    try:
        out = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True,
                             text=True, timeout=5).stdout
        m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
        return int(m.group(1)) / 1e9 if m else 0.0
    except Exception:
        return 0.0


def fl_window_titles() -> list[str]:
    """Titles of FL's OS-level windows (dialogs and the picker are separate windows)."""
    rc, out, _ = cm.osa('tell application "System Events" to tell process "OsxFL" '
                        'to get name of every window')
    if rc != 0 or not out.strip():
        return []
    return [t.strip() for t in out.split(",") if t.strip()]


def fl_cpu() -> float | None:
    try:
        pid = subprocess.run(["pgrep", "-x", "OsxFL"], capture_output=True, text=True,
                             timeout=5).stdout.split()
        if not pid:
            return None
        out = subprocess.run(["ps", "-o", "%cpu=", "-p", pid[0]], capture_output=True,
                             text=True, timeout=5).stdout.strip()
        return float(out) if out else None
    except Exception:
        return None


# ------------------------------------------------------------------ controller reads

def _try_exec(conn, code: str, timeout: float = 3.0) -> tuple[str, str]:
    """('ok', stdout) | ('unsafe', err) | ('timeout', err) | ('error', err)."""
    try:
        r = conn.send_command("probe.exec", {"code": code}, timeout=timeout)
    except Exception as e:
        return ("timeout" if "timeout" in str(e).lower() else "error"), str(e)
    if isinstance(r, dict) and r.get("success"):
        return "ok", (r.get("stdout") or "").strip()
    err = str((r or {}).get("error") or "probe.exec failed")
    if "unsafe" in err.lower():
        return "unsafe", err
    if "timeout" in err.lower():
        return "timeout", err
    return "error", err


def diagnose(conn) -> dict[str, Any]:
    front = cm.frontmost_app()
    titles = fl_window_titles()
    picker = any(PICKER in t for t in titles)
    dialogs = [t for t in titles if any(t == d or t.startswith(d + " ") for d in DIALOG_TITLES)]
    state, info = _try_exec(conn, "import json, ui\n"
                                  "print(json.dumps([int(ui.isInPopupMenu()), "
                                  "ui.getFocusedFormCaption()]))")
    popup, focused = None, None
    if state == "ok":
        try:
            import json
            popup, focused = json.loads(info.splitlines()[-1])
            popup = bool(popup)
        except Exception:
            pass
    cpu = fl_cpu()
    blockers, advice = [], []
    filtered = None
    if state == "ok":
        fs, fi = _try_exec(conn, "import json, channels\nprint(json.dumps([channels.channelCount(), "
                                 "channels.channelCount(1)]))")
        try:
            import json as _j
            a, b = _j.loads(fi.splitlines()[-1]) if fs == "ok" else (0, 0)
            if a != b:
                filtered = f"{a} of {b} channels shown"
        except Exception:
            pass
    if filtered:
        # a filter-group view re-indexes the channel API: channel numbers would be wrong
        blockers.append(f"Channel rack filtered ({filtered})")
        advice.append("recover sets the filter back to All (PgUp)")
    if picker:
        blockers.append("plugin picker open")
        advice.append("recover closes it (needs FL frontmost)")
    if dialogs:
        blockers.append(f"FL dialog open: {dialogs}")
        advice.append("recover dismisses it with Enter (needs FL frontmost)")
    if popup:
        blockers.append("popup menu open")
        advice.append("recover closes it in-engine (ui.closeActivePopupMenu)")
    if state == "unsafe" and not (picker or dialogs):
        blockers.append("controller says 'Operation unsafe' (a modal FL window is up)")
        advice.append("look at the screen: an FL-drawn modal without an OS window")
    if state == "timeout":
        busy = cpu is not None and cpu > 60
        blockers.append("controller not answering" + (f" (FL busy, {cpu:.0f}% CPU)" if busy else ""))
        advice.append("wait for FL to finish (e.g. queued preset loads)" if busy
                      else "check MIDI settings / restart the controller")
    if front != "OsxFL":
        advice.append(f"FL is not frontmost ({front!r}): screen actions will wait for it")
    return {"action": "doctor", "ready": not blockers, "frontmost": front,
            "fl_front": front == "OsxFL", "user_idle_s": round(user_idle_seconds(), 1),
            "controller": state, "popup_open": popup, "focused_form": focused,
            "picker_open": picker, "dialogs": dialogs, "fl_windows": titles[:12],
            "rack_filtered": filtered,
            "fl_cpu": cpu, "blockers": blockers, "advice": advice}


# ------------------------------------------------------------------ actions

def wait_for_front(timeout: float = 30.0, idle_s: float = 3.0, allow_focus: bool = True,
                   sleep: Callable = time.sleep, clock: Callable = time.monotonic) -> dict:
    """Wait until FL is frontmost. Brings FL forward itself only when the user has
    been idle >= idle_s (never mid-typing). Returns {front, waited_s, focused_by_us}."""
    t0, ours = clock(), False
    while True:
        if cm.frontmost_app() == "OsxFL":
            return {"front": True, "waited_s": round(clock() - t0, 1), "focused_by_us": ours}
        if clock() - t0 >= timeout:
            return {"front": False, "waited_s": round(clock() - t0, 1), "focused_by_us": ours,
                    "frontmost": cm.frontmost_app()}
        if allow_focus and user_idle_seconds() >= idle_s:
            cm.focus_fl()
            ours = True
            sleep(0.6)
            continue
        sleep(0.5)


def _dismiss_dialog(title: str) -> bool:
    """Enter closes FL's Error/Warning dialogs (score-log Warning verified; Error's
    default button is OK). Only while FL is frontmost."""
    if cm.frontmost_app() != "OsxFL":
        return False
    cm.keypress("return")
    time.sleep(0.6)
    return not any(t.startswith(title) for t in fl_window_titles())


def recover(conn, allow_focus: bool = True, busy_wait: float = 60.0,
            sleep: Callable = time.sleep) -> dict[str, Any]:
    """Clear what blocks FL. Order: picker -> dialogs -> popup -> wait while busy."""
    from fl_studio_mcp.utils.add_effect import close_picker
    from fl_studio_mcp.utils.plugin_preset_ui import close_popups
    steps: list[str] = []
    d = diagnose(conn)
    need_front = d["picker_open"] or bool(d["dialogs"])
    if need_front and not d["fl_front"]:
        w = wait_for_front(timeout=20, allow_focus=allow_focus, sleep=sleep)
        steps.append(f"waited for FL front: {w}")
    if d["picker_open"]:
        steps.append(f"close picker: {close_picker()}")
    for t in d["dialogs"]:
        steps.append(f"dismiss dialog {t!r}: {_dismiss_dialog(t)}")
    if d["controller"] == "ok" and d["popup_open"]:
        steps.append(f"close popup menu: {close_popups(conn, sleep=sleep)}")
    if d.get("rack_filtered"):
        from fl_studio_mcp.utils.channel_group import show_all_channels
        steps.append(f"channel rack filter -> All: {show_all_channels(conn).get('success')}")
    if d["controller"] == "timeout":
        t_end = time.monotonic() + busy_wait
        while time.monotonic() < t_end:
            st, _ = _try_exec(conn, "print(1)", timeout=2.0)
            if st == "ok":
                break
            sleep(2.0)
        steps.append(f"waited for busy FL: controller {st}")
    after = diagnose(conn)
    return {"action": "recover", "success": after["ready"], "steps": steps,
            "before": d["blockers"], "after": after["blockers"], "doctor": after}


def ensure_ready(conn, need_front: bool = False, timeout: float = 30.0,
                 allow_focus: bool = True) -> dict[str, Any]:
    """One verdict before any action: blockers cleared (+ FL frontmost if asked)."""
    d = diagnose(conn)
    rec = None
    if not d["ready"]:
        rec = recover(conn, allow_focus=allow_focus)
        d = rec["doctor"]
    front = None
    if need_front:
        front = wait_for_front(timeout=timeout, allow_focus=allow_focus)
    ok = d["ready"] and (front is None or front["front"])
    return {"ready": ok, "blockers": d["blockers"], "front": front,
            "recovered": rec["steps"] if rec else []}


def tidy(conn) -> dict[str, Any]:
    """Close EVERY plugin editor window (mixer effects): focusEditor + ui.escape per
    loaded slot, one trip per track. A closed editor opens and closes again (net:
    closed). Live 2026-10-05: leftover editors covered the mixer and confused OCR."""
    import json
    rows = json.loads(_try_exec(conn, (
        "import json, mixer, plugins\n"
        "print(json.dumps([[t, [s for s in range(10) if plugins.isValid(t, s)]] "
        "for t in range(0, mixer.trackCount())]))"), timeout=5.0)[1].splitlines()[-1])
    closed = 0
    for t, slots in rows:
        if not slots:
            continue
        code = "import mixer, ui\n" + "".join(
            f"mixer.focusEditor({t}, {s})\nui.escape()\n" for s in slots) + "print(1)"
        st, _ = _try_exec(conn, code, timeout=8.0)
        closed += len(slots) if st == "ok" else 0
    return {"action": "tidy", "success": True, "editors_closed_or_kept_closed": closed}

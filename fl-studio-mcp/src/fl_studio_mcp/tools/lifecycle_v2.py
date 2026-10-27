"""Process lifecycle for FL Studio (open / close / save / status / force).

This module is the BACKEND for `fl_connect` (server.py). It is not a separate
MCP tool — open/close/force live on `fl_connect(action=...)` so we do not grow
the tool surface. Saving is `fl_file("save")`; state reads are `fl_state`.

Why it's server-side (not a controller action):
  - open/close are OS-level (launch a process, dismiss a native AppKit dialog).
  - The native macOS "Confirm: Save changes to X.flp?" modal is NOT reachable by
    FL's in-process ui/screen modules (those drive FL's internal widgets only).
    It blocks the controller thread, so it must be handled OUT-of-band.

Design goals (from the 2026-09-30 session):
  * Non-blocking: a `close` never leaves FL wedged behind a modal dialog.
  * Crash-safe: detect the native dialog (via the OS, not the wedged controller)
    and dismiss it; never fire a controller call while a modal is up.
  * Idempotent: `open` on an already-running FL is a no-op; `close` on a
    not-running FL is a no-op.

Actions:
  status           — is FL running? which build? which project? is the
                     controller responsive (not wedged)?
  open             — launch FL if not running; dismiss the trial Welcome dialog;
                     wait until the controller returns a non-timeout snapshot.
  close            — quit FL. Dismisses the native "Save changes?" dialog
                     (default: Do Not Save). Optional `confirm="yes|no|cancel"`
                     controls which button the save dialog gets.
  save             — save the current project. Uses FL's in-process save path if
                     available, else File > Save via the OS. `path` optional.
  force            — last-resort hard kill (pkill) if FL is wedged. Requires
                     `confirm="yes"`.
  dismiss_modal    — un-wedge the controller when a web-rendered modal blocks it
                     (e.g. the "Warning: The score log is empty" dialog that
                     dumpScoreLog pops). Activates FL, verifies FL is actually
                     frontmost (focus-war safe: retries while another app holds
                     the foreground), sends a key (enter/esc), then polls the
                     controller until it answers. `title` is a window-title
                     substring for reporting; `key` defaults to "enter".

The native-dialog dismissal uses macOS `osascript`/`screencapture`-free AX
where possible; it degrades gracefully (returns what it could do) so a
partial success is reported rather than raising.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

# The app name as macOS sees it. Overridable via env for other installs.
FL_APP = os.environ.get("FL_STUDIO_APP", "FL Studio 2026")
# The on-disk executable name (pgrep pattern).
FL_PROC = os.environ.get("FL_STUDIO_PROC", "OsxFL")
# How long to wait (s) for the controller to come back after open.
OPEN_READY_TIMEOUT = float(os.environ.get("FL_OPEN_READY_TIMEOUT", "60"))
POLL_INTERVAL = 1.0


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], timeout: float = 15.0) -> tuple[int, str, str]:
    """Run a shell command; return (returncode, stdout, stderr). Never raises."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:  # noqa: BLE001 - report, don't raise
        return 1, "", str(e)


def _fl_running() -> bool:
    rc, out, _ = _run(["pgrep", "-f", FL_PROC])
    return rc == 0 and bool(out.strip())


def _fl_pid() -> int | None:
    rc, out, _ = _run(["pgrep", "-f", FL_PROC])
    if rc != 0 or not out.strip():
        return None
    try:
        return int(out.strip().split()[0])
    except ValueError:
        return None


def _controller_responsive(timeout: float = 3.0) -> tuple[bool, str]:
    """Lightest possible controller read. True only if a non-timeout reply comes back."""
    from fl_studio_mcp.utils.connection import get_connection

    conn = get_connection()
    r = conn.send_command("transport.getBPM", {}, timeout=timeout)
    if r.get("success"):
        return True, f"bpm={r.get('bpm')}"
    err = r.get("error") or ""
    # "Timeout" == wedged or not-yet-ready; anything else is a real error.
    if "Timeout" in err:
        return False, "controller timeout (wedged or dialog blocking)"
    return False, err


def _find_osxfl_window(*substrings: str) -> tuple[str, int, int, int, int] | None:
    """Return (name, x, y, w, h) of the first OsxFL window whose title contains
    ANY of the given substrings, or None.

    Single AppleScript round-trip: iterate the process's windows, and for the
    first one whose name `contains` any substring, return its geometry + name.
    The window name is only ever used inside AppleScript's `contains` — it is
    never re-embedded into a follow-up query, which is critical because FL's
    trial dialog titles contain private-use unicode (\ue409...) that would be
    mangled if passed through Python `repr()` into a second AppleScript.
    Substrings must be plain ASCII ("Welcome", "Confirm", ...).
    """
    # AppleScript string literals use DOUBLE quotes (Python repr()'s single
    # quotes are a syntax error). Substrings are plain ASCII.
    conds = " or ".join(f'wn contains "{s}"' for s in substrings)
    script = (
        'tell application "System Events"\n'
        '  tell (first process whose name is "OsxFL")\n'
        '    set theFound to "none"\n'
        '    repeat with w in windows\n'
        '      set wn to name of w as text\n'
        f'      if theFound is "none" and ({conds}) then\n'
        '        set p to position of w\n'
        '        set s to size of w\n'
        '        set theFound to ((item 1 of p) as text) & "," & ((item 2 of p) as text) & "," & ((item 1 of s) as text) & "," & ((item 2 of s) as text) & "," & wn\n'
        '      end if\n'
        '    end repeat\n'
        '  end tell\n'
        '  return theFound\n'
        'end tell'
    )
    rc, out, err = _run(["osascript", "-e", script], timeout=10)
    out = (out or "").strip()
    if rc != 0 or not out or out == "none":
        return None
    try:
        x, y, w, h, name = out.split(",", 4)
        return (name, int(float(x)), int(float(y)), int(float(w)), int(float(h)))
    except Exception:  # noqa: BLE001
        return None


def _cliclick() -> str | None:
    """Path to the cliclick CLI (absolute screen-coordinate clicker), if present."""
    import shutil
    return shutil.which("cliclick")


# ---------------------------------------------------------------------------
# Crash detection (v10.1 hardening, 2026-10-02: v10's OnInit crash loop)
# ---------------------------------------------------------------------------

def _crash_log_dir() -> "Path | None":
    import os
    d = Path(os.path.expanduser(
        "~/Documents/Image-Line/FL Studio/Support/Logs/Crash"))
    return d if d.is_dir() else None


def _crash_since(ts: float):
    """Newest FL crash log written after `ts` (epoch seconds).

    Returns (path, mtime) or None. FL's own clock is unreliable (the file
    NAMES carry FL-local time; mtimes are real), so match on mtime only.
    """
    d = _crash_log_dir()
    if not d:
        return None
    best = None
    try:
        for f in d.glob("*.log"):
            m = f.stat().st_mtime
            if m >= ts and (best is None or m > best[1]):
                best = (f, m)
    except Exception:
        return None
    return best


def _process_start_epoch(pid: int) -> float:
    """Process start as epoch seconds (via `ps -o etimes=`), or now on failure."""
    import time as _t
    now = _t.time()
    try:
        rc, o, _e = _run(["ps", "-o", "etimes=", "-p", str(pid)], timeout=5)
        if rc == 0 and o.strip():
            return now - float(o.strip().split()[0])
    except Exception:  # noqa: BLE001
        pass
    return now


def _crashed_since_start(pid: int):
    """(crash_log_path, mtime) if FL `pid` crashed after it started, else None."""
    if not pid:
        return None
    return _crash_since(_process_start_epoch(pid))


def _installed_controller() -> "Path | None":
    import os
    p = Path(os.path.expanduser(
        "~/Documents/Image-Line/FL Studio/Settings/Hardware/"
        "FLStudioMCP/device_FLStudioMCP.py"))
    return p if p.exists() else None


def _refresh_lastgood() -> bool:
    """After a verified-READY launch: remember the installed controller as the
    last-known-good. Called only when the controller answers, so lastgood is
    always a controller version that at least reached `ready`.

    2026-10-02 guard (taint incident): a controller version that EVER crashed
    FL must not become lastgood, even if a later launch of it reaches ready
    (crashes are non-deterministic — v10.1 poisoned lastgood this way: the
    user's manual restart loaded v10.1, one command crashed FL, and a later
    transient-ready refresh overwrote the v9 backup the crash guard relies
    on). So: refuse to refresh if any crash log exists since the previous
    lastgood was written.
    """
    import shutil
    src = _installed_controller()
    if not src:
        return False
    dst = src.with_name("device_FLStudioMCP.lastgood.py")
    try:
        if dst.exists():
            since = dst.stat().st_mtime
            crash = _crash_since(since)
            if crash:
                # lastgood was written, then FL crashed on some controller —
                # never let a possibly-bad version overwrite it.
                return False
        if not dst.exists() or dst.read_bytes() != src.read_bytes():
            shutil.copyfile(src, dst)
        return True
    except Exception:  # noqa: BLE001
        return False


def _revert_to_lastgood() -> dict[str, Any]:
    """Restore the last-known-good controller over the installed one (crash-
    loop recovery). Returns a report dict."""
    import shutil
    src = _installed_controller()
    dst = src.with_name("device_FLStudioMCP.lastgood.py") if src else None
    if not src or not dst or not dst.exists():
        return {"reverted": False, "err": "no lastgood copy"}
    try:
        if dst.read_bytes() != src.read_bytes():
            shutil.copyfile(dst, src)
            return {"reverted": True,
                    "to": dst.name,
                    "note": "installed controller differs from last-known-good "
                            "and was restored"}
        return {"reverted": False, "note": "installed == lastgood"}
    except Exception as e:  # noqa: BLE001
        return {"reverted": False, "err": str(e)[:150]}


def _click_at(x: int, y: int) -> dict[str, Any]:
    """Click at an absolute screen coordinate via cliclick (left button)."""
    cc = _cliclick()
    if not cc:
        return {"ok": False, "method": "cliclick", "err": "cliclick not on PATH"}
    rc, out, err = _run([cc, f"c:{x},{y}"], timeout=10)
    return {"ok": rc == 0, "method": "cliclick", "x": x, "y": y,
            "err": err[:150] if err else None}


def _press_escape() -> dict[str, Any]:
    """Send Escape (key code 53) to the frontmost app (FL)."""
    rc, out, err = _run(["osascript", "-e",
                         'tell application "System Events" to key code 53'],
                        timeout=10)
    return {"ok": rc == 0, "method": "escape", "err": err[:150] if err else None}


def _dismiss_welcome() -> dict[str, Any]:
    """Dismiss the trial-mode 'Welcome to FL Studio' dialog.

    It is a web-rendered panel with no AX buttons and no AX `close`; the one
    key that reliably closes it is **Escape** (verified 2026-09-30: window count
    dropped 2->1). No-op-ish if it isn't present (Escape just cancels focus).
    """
    hit = _find_osxfl_window("Welcome")
    if not hit:
        return {"present": False}
    # The dialog is only dismissed by Escape when it is the KEY window of the
    # frontmost app — so activate FL first, then Escape (a bare AXRaise does
    # NOT make a web-rendered dialog key; verified 2026-10-01).
    _run(["osascript", "-e", f'tell application "{FL_APP}" to activate'],
         timeout=10)
    time.sleep(0.4)
    r = _press_escape()
    r["present"] = True
    return r


def _dismiss_native_dialog(dialog_title: str, button: str,
                           via: str = "click") -> dict[str, Any]:
    """Dismiss a native FL dialog (e.g. 'Confirm: Save changes to X.flp?').

    These are web-rendered AppKit windows: the buttons have NO AX tree, so we
    (1) find the window via AX (title substring + exact process name "OsxFL"),
    (2) read its position/size via AX, (3) click the requested button by
    ABSOLUTE COORDINATE with cliclick. The button's horizontal fraction is
    fixed by the dialog layout: Yes left, No middle, Cancel right.
    """
    # Escape is a valid fallback: on a Save/No/Cancel dialog it maps to
    # Cancel (stay). We only use it if the caller asked for cancel.
    if button.lower() == "cancel":
        r = _press_escape()
        r["method"] = "escape-as-cancel"
        return r

    frac = {"yes": 0.24, "no": 0.45, "cancel": 0.69, "ok": 0.5,
            "reopen": 0.5}.get(button.lower(), 0.45)
    hit = _find_osxfl_window(dialog_title, "Save changes")
    if not hit:
        return {"ok": False, "method": "cliclick", "err": "dialog not found",
                "title": dialog_title}
    _, x, y, w, h = hit
    # The button row sits near the bottom of the dialog (~83% down).
    cx = int(x + frac * w)
    cy = int(y + 0.83 * h)
    r = _click_at(cx, cy)
    r["dialog"] = {"title": hit[0], "x": x, "y": y, "w": w, "h": h,
                  "button": button}
    return r


# ---------------------------------------------------------------------------
# action implementations
# ---------------------------------------------------------------------------


def _action_status() -> dict[str, Any]:
    from fl_studio_mcp.tools.state import take_state_snapshot

    out: dict[str, Any] = {
        "running": _fl_running(),
        "pid": _fl_pid(),
    }
    if not out["running"]:
        out["state"] = "not_running"
        return out

    resp, detail = _controller_responsive()
    out["controller_responsive"] = resp
    out["controller_detail"] = detail
    if not resp:
        crash = _crashed_since_start(out["pid"])
        if crash:
            out["state"] = "crashed_dialog_blocking"
            out["crash_log"] = str(crash[0])
            out["note"] = ("FL crashed after launch (crash log: %s). A "
                           "web-rendered crash-report dialog is up, which no "
                           "AX/cliclick path can dismiss — use "
                           "fl_connect('close') (auto-kills a crashed zombie) "
                           "or fl_connect('force', confirm='yes')." % crash[0].name)
        else:
            out["state"] = "wedged_or_dialog_blocking"
        return out

    snap = take_state_snapshot(0)  # fresh_seconds=0: don't care about roll staleness
    out["state"] = "ready" if snap.get("success") else "degraded"
    out["bpm"] = snap.get("bpm")
    out["project"] = snap.get("project")
    out["fl_version"] = snap.get("fl_version")
    out["selected_pattern"] = snap.get("selected_pattern")
    out["channel_count"] = snap.get("channel_count")
    return out


def _action_open(wait_ready: bool, timeout: float) -> dict[str, Any]:
    out: dict[str, Any] = {}

    if _fl_running():
        resp, detail = _controller_responsive()
        out.update({"action": "open", "already_running": True,
                    "controller_responsive": resp, "detail": detail})
        if resp:
            out["state"] = "ready"
            return out
        out["state"] = "wedged_or_dialog_blocking"
        out["note"] = ("FL is running but the controller is not responding — "
                       "a modal dialog may be open. Try fl_connect('close') "
                       "then open again.")
        return out

    rc, o, e = _run(["open", "-a", FL_APP])
    out["launch_rc"] = rc
    if rc != 0:
        out.update({"state": "launch_failed", "error": e[:300]})
        return out

    if not wait_ready:
        out.update({"state": "launching",
                    "note": "launch sent; not waiting for readiness"})
        return out

    launch_ts = time.time()
    relaunches = 0

    # Wait for the controller to become responsive (FL loads the controller
    # on a fresh launch; a resumed session may not). A trial-mode 'Welcome'
    # dialog blocks the controller thread, so clear it with Escape during the
    # wait (verified 2026-09-30: it drops the window count 2->1).
    deadline = time.time() + timeout
    last = "starting"
    last_escape = 0.0
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        if not _fl_running():
            crash = _crash_since(launch_ts)
            if crash and relaunches < 1:
                # Crash loop guard (v10.1): the installed controller crashed FL
                # at startup. Revert to last-known-good (if different) and
                # relaunch once; report what happened either way.
                relaunches += 1
                revert = _revert_to_lastgood()
                out["crash_loop"] = True
                out["crash_log"] = str(crash[0])
                out["revert"] = revert
                rc2, o2, e2 = _run(["open", "-a", FL_APP])
                if rc2 != 0:
                    out.update({"state": "crash_loop_relaunch_failed",
                                "error": e2[:300]})
                    return out
                launch_ts = time.time()
                last = "relaunched after crash"
                continue
            out.update({"state": "died_during_startup",
                        "crash" : bool(crash),
                        "crash_log": str(crash[0]) if crash else None,
                        "note": "FL process exited before becoming ready" +
                                (" (CRASH — see crash_log)" if crash else "")})
            return out
        # Nudge away the Welcome dialog at most once per ~3s while waiting.
        if time.time() - last_escape > 3:
            w = _dismiss_welcome()
            if w.get("present"):
                out["welcome_dismissed"] = True
            last_escape = time.time()
        resp, detail = _controller_responsive(2.0)
        last = detail
        if resp:
            _refresh_lastgood()  # this controller version reached `ready`
            out.update({"state": "ready", "detail": detail,
                        "crash_loop": relaunches > 0,
                        **({"crash_log": str(out.get("crash_log"))}
                           if out.get("crash_log") else {})})
            return out
    out.update({"state": "not_ready_in_time", "last": last,
                "note": ("controller did not respond within "
                         f"{timeout:.0f}s — a modal dialog (trial Welcome) is "
                         "likely blocking it. Try fl_connect('close') or "
                         "dismiss the dialog, then open again.")})
    return out


def _action_close(button: str, attempts: int = 3) -> dict[str, Any]:
    """Quit FL. `button` = the choice for the native 'Save changes?' dialog.

    The trial build is flaky here: a modal 'Welcome' dialog reappears and eats
    the ⌘Q, and a 'Save changes?' Confirm can also appear. So we retry the
    (dismiss-Welcome → quit → dismiss-Confirm) sequence up to `attempts` times
    instead of giving up after one pass.
    """
    if not _fl_running():
        return {"action": "close", "running": False,
                "note": "FL is not running; nothing to close"}

    out: dict[str, Any] = {"action": "close", "running": True,
                           "quit_sent": False, "tries": 0}

    for i in range(1, attempts + 1):
        out["tries"] = i
        # 0) A trial-mode 'Welcome' dialog is modal and eats the quit keystroke
        #    — dismiss it first (Escape). No-op if not present.
        out["welcome"] = _dismiss_welcome()
        time.sleep(0.3)

        # Send quit via the app / Cmd-Q (osascript to the app is the most
        # reliable trigger; the process name for the menu can be fiddly).
        _run(["osascript", "-e",
              f'tell application "{FL_APP}" to activate'])
        time.sleep(0.4)
        _run(["osascript", "-e",
              'tell application "System Events" to '
              'keystroke "q" using {command down}'])
        out["quit_sent"] = True

        # Give FL a moment to either exit or raise the native Confirm dialog.
        time.sleep(2.0)
        if not _fl_running():
            out["state"] = "closed_cleanly"
            return out

        # Still up — likely the native "Save changes to X.flp?" modal (or the
        # Welcome reappeared). Dismiss the Confirm with the requested button
        # (default: no / don't save) and loop for another quit if needed.
        out["dialog"] = _dismiss_native_dialog("Confirm", button)
        time.sleep(1.5)
        if not _fl_running():
            out["state"] = "closed_after_dialog"
            return out

    # Still up after all attempts. Crash detection (v10.1): if FL CRASHED
    # since it started, the thing on screen is a web-rendered crash-report
    # dialog that no AX/cliclick path can dismiss — the only clean exit is a
    # hard kill (the session is autosave-safe). Auto-escalate.
    pid = _fl_pid()
    crash = _crashed_since_start(pid)
    if crash:
        _run(["pkill", "-f", "OsxFL"], timeout=10)
        time.sleep(1.0)
        out["state"] = "crashed_cleaned"
        out["crash_log"] = str(crash[0])
        out["note"] = ("FL had crashed (log: %s); its crash-report dialog is "
                       "web-rendered and not dismissible by automation, so the "
                       "zombie was killed. The session is autosave-safe — "
                       "re-open with fl_connect('open')." % crash[0].name)
        return out

    out["state"] = "still_up"
    out["note"] = ("FL did not fully exit after "
                   f"{attempts} attempt(s). A native dialog may still be open. "
                   "Use fl_connect('force', confirm='yes') for a hard kill, "
                   "or dismiss the dialog manually.")
    return out


def _action_save(path: str | None) -> dict[str, Any]:
    if not _fl_running():
        return {"action": "save", "running": False, "error": "FL not running"}

    # Preferred: FL's own File > Save (Cmd-S). This goes through FL's normal
    # save path (respects the current project / trial save limits). We use the
    # OS-level keystroke because the in-process flp.save API is not exposed in
    # the v45 controller runtime (confirmed: no importable flp module).
    _run(["osascript", "-e", f'tell application "{FL_APP}" to activate'])
    time.sleep(0.4)

    if path:
        # Save As with a specific path: open the Save-As sheet (Cmd-Shift-S),
        # type the path in the "Where" field (Shift-Cmd-G), and confirm.
        rc, o, e = _run(["osascript", "-e",
                         'tell application "System Events" to '
                         'keystroke "s" using {command down, shift down}'])
        time.sleep(1.5)
        # "Go to folder" sheet
        rc, o, e = _run(["osascript", "-e",
                         'tell application "System Events" to '
                         'keystroke "g" using {command down, shift down}'])
        time.sleep(1.0)
        _run(["osascript", "-e",
              f'tell application "System Events" to keystroke "{path}"'])
        time.sleep(0.5)
        _run(["osascript", "-e",
              'tell application "System Events" to key code 36'])  # Return
        time.sleep(1.0)
        out: dict[str, Any] = {"action": "save", "path": path,
                               "method": "os-saveas"}
    else:
        rc, o, e = _run(["osascript", "-e",
                         'tell application "System Events" to '
                         'keystroke "s" using {command down}'])
        time.sleep(1.5)
        out = {"action": "save", "path": None, "method": "os-save"}

    out["ok"] = rc == 0 and _fl_running()
    if not out["ok"]:
        out["note"] = ("save key sent but FL did not stay up — on the trial "
                       "build, saving a NEW project is blocked; saving an "
                       "autosaved/opened project works.")
    # Trial note: even a successful Cmd-S on a brand-new untitled project is
    # refused by the trial. The reliable 'save' on trial is to the autosave
    # location; report that so the caller knows.
    return out


def _action_force(confirm: str) -> dict[str, Any]:
    if confirm != "yes":
        return {"action": "force", "error":
                "refused: pass confirm='yes' to hard-kill FL"}
    if not _fl_running():
        return {"action": "force", "running": False,
                "note": "FL not running"}
    rc, o, e = _run(["pkill", "-f", FL_PROC])
    time.sleep(1.0)
    still = _fl_running()
    if still:
        # escalate to -9
        rc2, o2, e2 = _run(["pkill", "-9", "-f", FL_PROC])
        time.sleep(1.0)
        still = _fl_running()
    return {"action": "force", "killed": not still, "rc": rc,
            "note": None if not still else "could not kill; check manually"}


def _fl_frontmost() -> bool:
    """True when FL's process owns the macOS foreground."""
    rc, out, _ = _run(
        ["osascript", "-e",
         'tell application "System Events" to get name of '
         'first process whose frontmost is true'])
    return rc == 0 and out == FL_PROC


def _press_key(key: str) -> dict[str, Any]:
    """Send a single key (esc=53, enter=36) to the frontmost app via AX."""
    key_code = 53 if key == "esc" else 36
    rc, out, err = _run(["osascript", "-e",
                         f'tell application "System Events" to key code {key_code}'],
                        timeout=10)
    return {"ok": rc == 0, "err": err[:150] if err else None}


def _action_dismiss_modal(title: str, key: str,
                          attempts: int) -> dict[str, Any]:
    """Un-wedge the controller when a web-rendered modal dialog blocks it.

    Web-rendered FL dialogs (the trial 'Welcome' panel, the 'Warning: The
    score log is empty' dialog from dumpScoreLog, …) have NO AX buttons and
    block the controller thread, so no controller call can get through while
    one is up. The only reliable dismissal is a KEY sent while FL is
    frontmost (verified: Escape closes Welcome; Enter closes the score-log
    Warning). This action makes that a one-call, focus-war-safe operation:

      for each attempt:
        1. activate FL; poll until the OsxFL process is actually frontmost
           (another app grabbing the foreground between activate and key is
           what made ad-hoc attempts fail);
        2. send the key (enter by default — the score-log Warning's OK;
           esc also cancels it; use esc for the Welcome panel);
        3. poll the controller (lightweight transport.getBPM) until it
           answers — success means the modal is gone.

    `title` is a window-title substring (e.g. "Warning") reported for
    diagnostics; it does not gate the key send (the modal is the key window
    whenever FL is frontmost). `attempts` caps the focus-war retries.
    """
    key = (key or "enter").lower()
    if key not in ("esc", "enter"):
        return {"action": "dismiss_modal", "success": False,
                "error": "key must be 'enter' or 'esc'"}
    if not _fl_running():
        return {"action": "dismiss_modal", "success": False,
                "error": "FL not running"}
    attempts = max(1, min(int(attempts or 5), 10))

    last: dict[str, Any] = {"action": "dismiss_modal", "key": key,
                            "title": title or None,
                            "dialog_found": None}
    for i in range(1, attempts + 1):
        if title:
            last["dialog_found"] = _find_osxfl_window(title) is not None
        # activate + verify frontmost (focus-war safe)
        _run(["osascript", "-e", f'tell application "{FL_APP}" to activate'],
             timeout=10)
        front = _fl_frontmost()
        for _ in range(8):
            if front:
                break
            time.sleep(0.25)
            front = _fl_frontmost()
        last["frontmost"] = front
        if not front:
            last["attempt"] = i
            last["note"] = ("another app kept the foreground; "
                            "minimise your other windows and retry")
            continue
        last.update(_press_key(key))
        last["attempt"] = i
        time.sleep(0.5)
        ok, info = _controller_responsive(3.0)
        last["controller"] = info
        last["success"] = bool(ok)
        if ok:
            last["attempts_used"] = i
            last["note"] = ("controller responsive again — the modal was "
                            "dismissed" if last.get("dialog_found")
                            else "controller responsive again")
            return last
    last["attempts_used"] = attempts
    last["hint"] = ("still blocked — the modal may need its OK button "
                    "clicked (a coordinate click via the close/save helpers) "
                    "or the user's attention.")
    return last


# ---------------------------------------------------------------------------
# public entrypoint + registration
# ---------------------------------------------------------------------------

ACTIONS = ("status", "open", "close", "save", "force", "dismiss_modal",
           "doctor", "recover", "tidy")   # utils/ui_guard.py (2026-10-05)


def fl_lifecycle(action: str, conn=None, **params: Any) -> dict:
    """Dispatch an open/close/save/status/force action (used by fl_connect).

    Actions:
      status  — running? build? project? controller responsive?
      open    — launch if not running; wait until the controller responds.
                [wait_ready=True] [timeout=60]
      close   — quit FL, dismissing the native 'Save changes?' dialog.
                [confirm="no"]  (no=don't save, yes=save, cancel=stay)
      save    — save the current project (Cmd-S, or Save-As with path).
                [path="..."]
      force   — hard kill (pkill) if FL is wedged. [confirm="yes"]
    """
    a = (action or "").lower()
    if a not in ACTIONS:
        return {"success": False,
                "error": f"unknown action {action!r}",
                "valid_actions": list(ACTIONS)}

    if a == "status":
        return _action_status()
    if a == "open":
        wr = params.get("wait_ready")
        to = params.get("timeout")
        return _action_open(True if wr is None else bool(wr),
                            float(to) if to is not None else OPEN_READY_TIMEOUT)
    if a == "close":
        return _action_close(str(params.get("confirm", "no")))
    if a == "save":
        return _action_save(params.get("path"))
    if a == "force":
        return _action_force(str(params.get("confirm", "")))
    if a in ("doctor", "recover", "tidy"):
        from fl_studio_mcp.utils import ui_guard
        if conn is None:
            from fl_studio_mcp.utils.connection import get_connection
            conn = get_connection()
        if a == "doctor":
            return ui_guard.diagnose(conn)
        if a == "tidy":
            return ui_guard.tidy(conn)
        return ui_guard.recover(conn, allow_focus=params.get("allow_focus") is not False)
    if a == "dismiss_modal":
        return _action_dismiss_modal(
            str(params.get("title", "")),
            str(params.get("key", "enter")),
            int(params.get("attempts", 5) or 5))
    return {"success": False, "error": "unhandled"}


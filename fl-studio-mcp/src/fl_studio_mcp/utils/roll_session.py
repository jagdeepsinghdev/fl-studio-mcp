"""Automatic §0 script selection + piano-roll targeting for every note write.

Two facts drive this module (both live-verified 2026-10-01 on PE v26.1.6):

1. **The ComposeWithLLM selection is per FL PROCESS, not per channel.** After
   one selection, a trigger on a *different* channel's roll ran the script
   (808 Kick's 4 hits read back with no re-selection). FL forgets it on every
   restart. So: remember the FL pid we selected for; a new pid = select again.

2. **Selecting a channel via the API does NOT retarget an already-open roll.**
   `channels.selectOne(0)` left the roll on 'Acoustic Piano' — a write would
   have landed there. Closing and re-opening the roll (native View > Piano roll
   toggle) re-opens it on the selected channel; the toggle also *focuses* an
   unfocused roll first, so we loop. The proof is the roll title **as drawn on
   screen**, read by Vision OCR (`screen_roll_title`): the engine caption has
   no channel name in the docked layout, and a focus-based proof was fooled
   by a plugin window (2026-10-01 incident). See docs/UI-AUTOMATION.md §3.2.

`ensure_script_selected()` is called from `FLStudioTrigger.trigger()`, the one
function every queue writer goes through, so no writer needs to remember §0.
Selection runs the script once (that is how FL commits it), so the request
queue is stashed to `[]` around it — otherwise the queued notes would apply
twice (selection run + the real trigger).

Disable with `FL_AUTO_SELECT_SCRIPT=0`. Off under pytest unless the env var is
explicitly `1` (the suite must never click a running FL).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

FL_PROC = os.environ.get("FL_STUDIO_PROC", "OsxFL")
SESSION_NAME = ".mcp_script_session.json"

_busy = False


def auto_enabled() -> bool:
    val = os.environ.get("FL_AUTO_SELECT_SCRIPT")
    if val is not None:
        return val != "0"
    return "PYTEST_CURRENT_TEST" not in os.environ


def busy() -> bool:
    return _busy


def _scripts_dir() -> Path:
    from fl_studio_mcp.tools.piano_roll import _get_fl_scripts_dir
    return _get_fl_scripts_dir()


def _session_file() -> Path:
    return _scripts_dir() / SESSION_NAME


def fl_pid() -> int | None:
    """PID of the running FL process, or None."""
    try:
        out = subprocess.run(["pgrep", "-x", FL_PROC], capture_output=True,
                             text=True, timeout=3).stdout.split()
        return int(out[0]) if out else None
    except Exception:  # noqa: BLE001
        return None


def fl_started_at() -> float | None:
    """Epoch time the running FL process started (ps etime), or None."""
    pid = fl_pid()
    if pid is None:
        return None
    try:
        et = subprocess.run(["ps", "-o", "etime=", "-p", str(pid)], capture_output=True,
                            text=True, timeout=3).stdout.strip()
    except Exception:  # noqa: BLE001
        return None
    secs = parse_etime(et)
    return None if secs is None else time.time() - secs


def parse_etime(et: str) -> int | None:
    """ps etime '[[dd-]hh:]mm:ss' -> seconds."""
    et = (et or "").strip()
    if not et:
        return None
    try:
        days, _, hms = et.rpartition("-")
        parts = [int(x) for x in hms.split(":")]
    except ValueError:
        return None
    while len(parts) < 3:
        parts.insert(0, 0)
    return (int(days) if days else 0) * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]


def state_mtime() -> float | None:
    """mtime of piano_roll_state.json — the script's ran-oracle."""
    try:
        return (_scripts_dir() / "piano_roll_state.json").stat().st_mtime
    except OSError:
        return None


def ran_since(before: float | None) -> bool:
    after = state_mtime()
    return after is not None and (before is None or after > before)


def recorded_pid() -> int | None:
    try:
        return int(json.loads(_session_file().read_text()).get("fl_pid"))
    except Exception:  # noqa: BLE001
        return None


def mark_selected(pid: int) -> None:
    _session_file().write_text(json.dumps(
        {"fl_pid": pid, "selected_at": time.time()}))


def invalidate() -> None:
    try:
        _session_file().unlink()
    except OSError:
        pass


def ensure_script_selected(force: bool = False) -> dict[str, Any]:
    """Make sure 0ComposeWithLLM is the selected roll script in THIS FL process.

    No-op (no clicks) when it was already selected for the running FL pid.
    Otherwise runs fl_select_script on the currently open roll with the
    request queue stashed, confirms the run via the state-file mtime, and
    records the pid.
    """
    global _busy
    if not auto_enabled():
        return {"ok": True, "skipped": "auto-select disabled"}
    if _busy:
        return {"ok": True, "skipped": "reentrant"}
    pid = fl_pid()
    if pid is None:
        return {"ok": False, "error": "FL Studio is not running"}
    if not force and recorded_pid() == pid:
        return {"ok": True, "already_selected": True, "fl_pid": pid}

    from fl_studio_mcp.tools.piano_roll import _get_request_file
    req = _get_request_file()
    stash = req.read_text() if req.exists() else None
    _busy = True
    try:
        req.write_text("[]")
        before = state_mtime()
        from fl_studio_mcp.tools.select_script import fl_select_script
        r = fl_select_script()
        time.sleep(1.0)
        ran = ran_since(before)
        ok = bool(r.get("success")) and ran
        if ok:
            mark_selected(pid)
        else:
            invalidate()
        return {"ok": ok, "selected_now": ok, "fl_pid": pid, "script_ran": ran,
                "detail": r.get("note") or r.get("error")}
    finally:
        if stash is None:
            req.write_text("[]")
        else:
            req.write_text(stash)
        _busy = False


def _activate_fl() -> None:
    subprocess.run(["osascript", "-e",
                    f'tell application "System Events" to set frontmost of '
                    f'process "{FL_PROC}" to true'],
                   capture_output=True, timeout=5)
    time.sleep(0.4)


def _toggle_roll() -> None:
    subprocess.run(["osascript", "-e",
                    f'tell application "System Events" to tell process "{FL_PROC}" '
                    'to click menu item "Piano roll" of menu "View" of menu bar 1'],
                   capture_output=True, timeout=5)
    time.sleep(1.0)


_REPO = Path(__file__).resolve().parents[3]
_OCR_SRC = _REPO / "scripts" / "ocr_text.swift"
_OCR_BIN = _REPO / ".generated" / "bin" / "ocr_text"
_TITLE_RE = re.compile(r"piano\s*roll\s*[-–]\s*(.+?)\s*[›>»]*\s*$", re.I)


def _ocr_bin() -> Path | None:
    """The Vision OCR helper (scripts/ocr_text.swift), compiled once into
    .generated/bin. None if it cannot be built — callers must then refuse."""
    if _OCR_BIN.exists() and _OCR_BIN.stat().st_mtime >= _OCR_SRC.stat().st_mtime:
        return _OCR_BIN
    _OCR_BIN.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["swiftc", "-O", str(_OCR_SRC), "-o", str(_OCR_BIN)],
                       capture_output=True, timeout=180, check=True)
    except Exception:  # noqa: BLE001
        return None
    return _OCR_BIN if _OCR_BIN.exists() else None


def _norm(name: str) -> str:
    """Compare names, ignoring the '›' arrow FL draws after the title
    (OCR reads it as '›', '>', '•' or '·') and surrounding symbols."""
    core = re.sub(r"^[^\w(]+|[^\w)]+$", "", name.strip())
    return " ".join(core.split()).lower()


_TRUNC_RE = re.compile(r"^(?P<name>.*?)\s*(?:\u2026|\.{1,3})\s*[\u203a>\u00bb]")
_TAIL_GLYPHS_RE = re.compile(r"[\s\u203a>\u00bb\u2022\u00b7\-\u2013]+$")
_TAIL_X_RE = re.compile(r"\s[x\u00d7]$", re.I)
_INSERT_ROW_RE = re.compile(r"^insert\s*\d+$", re.I)


def parse_ocr_boxes(out: str) -> list[dict[str, Any]]:
    """Parse `ocr_text --boxes` output (`#image W H`, then x y w h text)."""
    boxes = []
    for line in out.splitlines():
        if not line or line.startswith("#"):
            continue
        f = line.split("\t", 4)
        if len(f) < 5:
            continue
        try:
            x, y, w, h = (int(v) for v in f[:4])
        except ValueError:
            continue
        boxes.append({"x": x, "y": y, "w": w, "h": h, "text": f[4]})
    return boxes


def _floating_name(text: str) -> tuple[str, bool]:
    """(core, truncated) of a floating-roll title like 'Bells •' or
    '808 Astro.\u203a - • x'. A truncation marker (ellipsis / '.') only counts
    when FL's arrow glyph follows it, so '808 Astro../ : - • x' (a window
    that merely peeks out) is not a truncation."""
    t = text.strip()
    m = _TRUNC_RE.match(t)
    if m:
        return m.group("name").strip(), True
    for _ in range(6):
        t2 = _TAIL_X_RE.sub("", _TAIL_GLYPHS_RE.sub("", t)).strip()
        if t2 == t:
            break
        t = t2
    return t, False


def _rack_band(boxes: list[dict], names_norm: set[str]) -> tuple[float, float] | None:
    """Centre-x of the channel-rack column: >=3 name-matching boxes at
    different heights whose centres agree within +-15 px."""
    cands = []
    for b in boxes:
        core, trunc = _floating_name(b["text"])
        if _norm(core) in names_norm or _norm(b["text"]) in names_norm:
            cands.append((b["x"] + b["w"] / 2.0, b["y"]))
    best: list[tuple[float, float]] = []
    for cx, _ in cands:
        grp = [c for c in cands if abs(c[0] - cx) <= 15]
        if len({y for _, y in grp}) >= 3 and len(grp) > len(best):
            best = grp
    if not best:
        return None
    xs = sorted(c[0] for c in best)
    return xs[len(xs) // 2], 15.0


def roll_title_from_boxes(boxes: list[dict], channel_names: list[str]) -> str | None:
    """Channel NAME the piano-roll title shows, from OCR boxes (pure).

    Thin wrapper over `roll_title_match` (which also returns the box).
    """
    m = roll_title_match(boxes, channel_names)
    return None if m is None else m[0]


def _tail_name(k: str, by_norm: dict[str, str]) -> str | None:
    """Channel name for a title whose OCR carries 1-2 stray chars from the title-bar icon
    ('Bass r', 'Keysr', 'Keys y'; live 2026-10-11): the unique LONGEST channel name that `k`
    starts with and exceeds by <= 2 chars. 'Keys 2x' still resolves to 'Keys 2', not 'Keys'."""
    tail = [kn for kn in by_norm if len(kn) >= 3 and k.startswith(kn) and 0 < len(k) - len(kn) <= 2]
    if not tail:
        return None
    best = max(len(kn) for kn in tail)
    top = [kn for kn in tail if len(kn) == best]
    return by_norm[top[0]] if len(top) == 1 else None


def roll_title_match(boxes: list[dict],
                     channel_names: list[str]) -> tuple[str, dict, bool] | None:
    """(channel name, OCR box, docked) of the piano-roll title, or None (pure).

    1. docked: 'Piano roll - <name>'.
    2. floating: the title bar draws only the channel name ('Bells •', or a
       truncated '808 Astro.\u203a - • x'); exact (norm) match, or a truncated
       prefix (>=4 chars) that matches exactly one channel.
    Channel-rack buttons, plugin windows ('Bells (Insert 6)') and mixer
    'Insert N' labels are excluded. Ambiguous or nothing -> None.
    """
    names = [n for n in dict.fromkeys(channel_names) if n]
    by_norm: dict[str, str] = {}
    for n in names:
        by_norm.setdefault(_norm(n), n)
    names_norm = set(by_norm)

    # 1. docked form
    for b in boxes:
        m = _TITLE_RE.search(b["text"])
        if m and m.group(1).strip(" -"):
            raw = m.group(1).strip()
            return by_norm.get(_norm(raw)) or _tail_name(_norm(raw), by_norm) or raw, b, True

    # 2. floating form
    band = _rack_band(boxes, names_norm)
    found: dict[str, dict] = {}
    for b in boxes:
        t = b["text"]
        if "(insert" in t.lower() or _INSERT_ROW_RE.match(t.strip()):
            continue
        if band and abs((b["x"] + b["w"] / 2.0) - band[0]) <= band[1]:
            continue
        core, trunc = _floating_name(t)
        k = _norm(core)
        if len(k) < 1:
            continue
        if not trunc:
            if k in by_norm:
                found.setdefault(by_norm[k], b)
            else:
                # OCR reads the title-bar icons as 1-2 letters ('Keys •' -> 'Keysr')
                nm = _tail_name(k, by_norm)
                if nm:
                    found.setdefault(nm, b)
        elif len(k) >= 4:
            hits = [n for kn, n in by_norm.items() if kn.startswith(k)]
            if len(hits) == 1:
                found.setdefault(hits[0], b)
    if len(found) != 1:
        return None
    name, box = next(iter(found.items()))
    return name, box, False


def screen_roll_title(channel_names: list[str] | None = None) -> str | None:
    """The channel name in the piano roll's title AS FL DRAWS IT on screen.

    The engine's caption is useless here: the docked roll's
    ui.getFocusedFormCaption is just 'Piano roll -', and a focus-based
    close/reopen proof is fooled by any other window (a plugin editor opened
    by Add > 3x Osc made a retarget to channel 5 'pass' while the roll stayed
    on '808' — 2026-10-01, the keys were written into the 808). The drawn
    title is the ground truth. None = no roll title visible / OCR unavailable.

    With `channel_names` the floating roll (title bar = just the channel
    name) is recognised too (S1, 2026-10-03); without it only the docked
    'Piano roll - <name>' form is (old behaviour).
    """
    ocr = _ocr_bin()
    if ocr is None:
        return None
    with tempfile.TemporaryDirectory() as d:
        shot = Path(d) / "screen.png"
        subprocess.run(["screencapture", "-x", str(shot)], capture_output=True, timeout=10)
        if not shot.exists():
            return None
        out = subprocess.run([str(ocr), str(shot), "--boxes"], capture_output=True,
                             text=True, timeout=30).stdout
    return roll_title_from_boxes(parse_ocr_boxes(out), channel_names or [])


def open_roll_for_channel(channel_index: int, max_toggles: int = 5,
                          settle: float = 1.5) -> dict[str, Any]:
    """Select `channel_index` and make the piano roll show THAT channel.

    Proof = the roll title FL draws on screen ('Piano roll - <name>', read by
    macOS Vision OCR) equals the channel's name, after FL's redraw delay
    (`settle`). Toggles View > Piano roll (close/reopen re-opens it on the
    selected channel) until it matches; otherwise returns {"ok": False} and
    the caller must refuse to write (CLAUDE.md rule 6b).
    """
    from fl_studio_mcp.utils.connection import get_connection
    conn = get_connection()
    chans = conn.send_command("channels.getAll").get("channels", [])
    match = [c for c in chans if c.get("index") == channel_index]
    if not match:
        return {"ok": False, "error": f"no channel {channel_index}"}
    name = match[0].get("name") or ""
    r = conn.send_command("channels.selectOne", {"index": int(channel_index)},
                          timeout=6.0)
    if not r.get("success", False):
        return {"ok": False, "error": f"select channel {channel_index}: {r.get('error')}"}
    if _ocr_bin() is None:
        return {"ok": False, "error": ("cannot verify the open roll: the OCR helper "
                                       "(scripts/ocr_text.swift) failed to build; "
                                       "refusing to write")}

    _activate_fl()
    seen: list[str] = []
    for attempt in range(max_toggles + 1):
        time.sleep(settle)  # FL redraws the roll title late
        title = screen_roll_title([c.get("name") or "" for c in chans])
        seen.append(title or "")
        if title and _norm(title) == _norm(name):
            return {"ok": True, "channel": channel_index, "roll": title,
                    "toggles": attempt, "proof": "screen title"}
        if attempt < max_toggles:
            _toggle_roll()
    return {"ok": False, "channel": channel_index, "titles_seen": seen,
            "error": (f"could not confirm the roll shows '{name}' (screen titles "
                      f"seen: {seen}); refusing to write")}

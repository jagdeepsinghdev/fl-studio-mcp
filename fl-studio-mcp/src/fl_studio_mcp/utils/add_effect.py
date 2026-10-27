"""L16 / D2: insert an effect plugin by name on a mixer track (native menus).

There is no importable add-plugin API in v45, so this drives FL's own path:
select the mixer track (mixer.setActiveTrack via probe.exec) -> Add ▸ Effect ▸
More plugins… -> the "Select effect plugin" picker -> double-click the row
(OCR-located; typed into the picker's Find field when not visible) -> verify
that a slot on that track now holds the plugin (plugins.getPluginName).
Live-proven picker steps: the Edison opener (utils/edison_flow.py).
FL must be the frontmost app; nobody should use the mouse meanwhile.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from fl_studio_mcp.utils import custom_menu as cm

PICKER = "Select effect plugin"
SLOTS = 10


def _exec(conn, code: str) -> dict:
    r = conn.send_command("probe.exec", {"code": code})
    if not (isinstance(r, dict) and r.get("success")):
        raise RuntimeError((r or {}).get("error") or "probe.exec failed")
    return json.loads(r.get("stdout", "").strip().splitlines()[-1])


def track_slots(conn, track: int) -> list[str]:
    """Plugin names in the track's 10 effect slots ('' = empty)."""
    return _exec(conn, f"""
import json, plugins
t = {int(track)}
print(json.dumps([plugins.getPluginName(t, s) if plugins.isValid(t, s) else ""
                  for s in range({SLOTS})]))
""")


def select_track(conn, track: int) -> bool:
    # setActiveTrack alone moves the ENGINE selection but not the mixer's
    # insert panel — and Add ▸ Effect inserts into the PANEL's track
    # (2026-10-03: asked for Insert 8, Reeverb 2 landed on Insert 7, whose
    # panel was showing). setTrackNumber moves the panel (live: focused form
    # became "Mixer - Insert 7"), so call both.
    # 2026-10-05 (live, three failures): with a PLUGIN editor focused the panel did
    # not follow (Reeverb 2 landed on 12, not 16). ui.hideWindow(widMixer) really
    # hides the mixer, but ui.showWindow does NOT bring it back on screen, and
    # ui.getVisible said 1 while nothing was drawn. So: NEVER hide the mixer;
    # the oracle is the SCREEN — the insert panel's title "Mixer - <track name>";
    # the only reliable show is the native View > Mixer menu (a toggle: used only
    # when no "Mixer -" title is on screen at all).
    if not cm.require_fl_front():
        # live 2026-10-05: with iTerm in front the screen check read the TERMINAL
        # and toggled View > Mixer blindly. No screen decisions unless FL is front.
        return False
    want = _exec(conn, f"""
import json, mixer, ui, midi
ui.setFocused(midi.widMixer)
mixer.setTrackNumber({int(track)})
mixer.setActiveTrack({int(track)})
print(json.dumps(mixer.getTrackName({int(track)})))
""")
    if not ensure_mixer_panel():
        return False
    _exec(conn, f"import mixer\nmixer.setTrackNumber({int(track)})\nprint(1)")
    time.sleep(0.5)
    title = panel_title()
    return title is not None and names_match(title, want)


#: words FL's hint bar shows for the mixer window's maximise/restore button
_MAX_HINTS = ("maximi", "restore", "maximum")


def ensure_mixer_panel(log=lambda m: None) -> bool:
    """Make the mixer's insert panel ("Mixer - <track>") visible ON SCREEN.
    Live 2026-10-05: after an FL restart the mixer opened COLLAPSED (only its
    toolbar strip, "Wide"), so no panel title existed and every insert refused.
      panel title on screen -> ok
      toolbar only (collapsed) -> hover along the toolbar row until FL's hint bar
        names the maximise/restore button, click it, re-check
      no mixer at all -> View > Mixer once, then the same checks
    Requires FL frontmost; never clicks a guessed position."""
    if not cm.require_fl_front(retry_focus=False):
        return False
    for attempt in range(2):
        if panel_title() is not None:
            return True
        boxes = cm.ocr_boxes(cm.shot())
        bar = next((b for b in boxes if b.text.strip().lower() == "wide"), None)
        if bar is None:
            if attempt == 0:
                log("no mixer on screen: View > Mixer")
                cm.menu_bar_click("View", "Mixer")
                time.sleep(1.2)
                continue
            return False
        # collapsed: find the maximise button on the toolbar row by its HINT
        right = max((b.x + b.w for b in boxes if abs(b.cy - bar.cy) <= 8), default=bar.x + 400)
        for x in range(min(1915, right + 320), bar.x + bar.w, -6):
            hint = cm.hint_at(x, bar.cy, settle=0.25).lower()
            if any(h in hint for h in _MAX_HINTS):
                if not cm.require_fl_front(retry_focus=False):
                    return False
                log(f"maximise mixer at ({x},{bar.cy}): hint {hint!r}")
                cm._click(x, bar.cy)
                time.sleep(1.0)
                break
        else:
            log("mixer collapsed but no maximise hint found on its toolbar")
            return False
    return panel_title() is not None


def _norm_name(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def names_match(seen: str, want: str, ratio: float = 0.9) -> bool:
    """OCR-tolerant name equality: exact after normalising, else >= 90 % similar
    (live 2026-10-05: 'Hall Reverb' read as 'Hall Reverh')."""
    import difflib
    a, b = _norm_name(seen), _norm_name(want)
    if not a or not b:
        return False
    if re.findall(r"\d+", a) != re.findall(r"\d+", b):    # "Insert 1" != "Insert 10"
        return False
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= ratio


def panel_title() -> str | None:
    """The track name in the mixer insert panel's title ("Mixer - Vocal" -> "Vocal"),
    read from the SCREEN (FL must be frontmost). None = no mixer panel drawn."""
    for b in cm.ocr_boxes(cm.shot()):
        t = b.text.strip()
        if t.lower().startswith("mixer -") or t.lower().startswith("mixer-"):
            return t.split("-", 1)[1].strip()
    return None


def _stray(conn, tracks: list[int], before: dict[int, list[str]]) -> dict | None:
    """A plugin that landed on another track than asked (panel/selection drift)."""
    for t in tracks:
        now = track_slots(conn, t)
        for s in range(SLOTS):
            if now[s] and now[s] != before[t][s]:
                return {"track": t, "slot": s, "plugin": now[s]}
    return None


def _key(text: str) -> str:
    """OCR-tolerant row key: OCR drops spaces ("Fruity Parametric EQ2", live
    2026-10-05), so compare lowercase alphanumerics only."""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def close_picker(log=lambda m: None) -> bool:
    """Never leave the picker open: while it is up FL refuses every probe.exec
    ("Operation unsafe at current time", live 2026-10-05). Click its own close
    box (top-right of the window), Escape as fallback. True = closed."""
    for _ in range(2):
        b = cm.window_by_name(PICKER)
        if b is None:
            return True
        if not cm.require_fl_front():
            # live 2026-10-05: the owner switched to iTerm mid-run; a blind
            # click/Escape here would land in THEIR app. Refuse, report.
            log(f"picker left open: FL is not frontmost ({cm.frontmost_app()!r}); "
                "bring FL to the front and close it (or re-run)")
            return False
        x, y, w, _h = b
        cm._click(x + w - 16, y + 16)
        time.sleep(0.8)
        if cm.window_by_name(PICKER) is None:
            log("closed the leftover plugin picker")
            return True
        cm.keypress("esc")
        time.sleep(0.6)
    return cm.window_by_name(PICKER) is None


def _open_picker(log) -> bool:
    if not cm.menu_bar_click("Add", "Effect", "More plugins..."):
        log("menu path Add ▸ Effect ▸ More plugins… failed")
        return False
    time.sleep(1.2)
    if not cm.move_window(PICKER, 620, 60, 520, 900):
        log("plugin picker window did not appear")
        return False
    return True


def pick_from_picker(name: str, log, conn=None) -> bool:
    """Open Add ▸ Effect ▸ More plugins… and choose `name`.
    Route 1 (2026-10-05): BY INDEX with in-engine keys (utils/picker_index.py) —
    works when the row is off-screen / the Find field is under the Dock; the
    highlighted row is verified before ui.enter. Route 2: the visible row (OCR)."""
    if not _open_picker(log):
        return False
    if conn is not None:
        from fl_studio_mcp.utils import picker_index as pi
        order = pi.load_cache()
        if not any(pi._match(o, name) for o in order):
            log("building the picker order cache")
            order = pi.build_order(conn, cm.window_by_name(PICKER), log=log)
            pi.save_cache(order)
            close_picker(log)
            if not _open_picker(log):
                return False
        r = pi.select_by_index(conn, name, order, log=log)
        if r.get("ok"):
            log(f"picked '{name}' by index {r['index']}")
            return True
        log(f"index route: {r.get('error')}; trying the visible row")
    want = _key(name)

    def row():
        # the list reflows after the move/resize: a row is trusted only when
        # two looks 0.5 s apart agree (2026-10-02: a one-look double-click hit
        # 'Emphasizer' two rows below 'Edison')
        for _ in range(4):
            time.sleep(0.5)
            a = next((b for b in cm.ocr_boxes(cm.shot())
                      if _key(b.text) == want), None)
            time.sleep(0.5)
            b2 = next((b for b in cm.ocr_boxes(cm.shot())
                       if _key(b.text) == want), None)
            if a and b2 and abs(a.cy - b2.cy) <= 2:
                return b2
        return None

    hit = row()
    if hit is None:
        # live 2026-10-05: after an FL restart the picker opened 975 px tall, FL
        # ignored the resize, and its bottom (Find field) sat under the macOS Dock.
        # The list is alphabetical: scroll it until the row shows (or it stops moving).
        b = cm.window_by_name(PICKER)
        if b is not None and cm.require_fl_front(retry_focus=False):
            lx, ly = b[0] + b[2] // 3, b[1] + b[3] // 2
            prev = None
            for _ in range(14):
                cm.scroll(lx, ly, 6)
                time.sleep(0.35)
                seen = tuple(x.text for x in cm.ocr_boxes(cm.shot()))[:40]
                if seen == prev:          # bottom of the list reached
                    break
                prev = seen
                hit = row()
                if hit is not None:
                    log(f"found '{name}' after scrolling the picker list")
                    break
    if hit is None:   # filter via the picker's Find field (if it is on screen)
        find = next((b for b in cm.ocr_boxes(cm.shot())
                     if b.text.strip().lower().startswith("find")), None)
        if find is not None:
            cm._click(find.x + 150, find.cy)
            time.sleep(0.4)
            cm.type_text(name.strip().lower())
            time.sleep(1.2)
            hit = row()
    if hit is None:
        log(f"no '{name}' row in the plugin picker")
        cm.keypress("esc")
        return False
    cm._click(hit.cx, hit.cy, double=True)   # a real double-click confirms
    time.sleep(2.5)
    if cm.window_by_name(PICKER) is not None:
        # the first click only focused the picker: the row is SELECTED but
        # not confirmed (2026-10-02, Werq). Return confirms the selection —
        # sent only while the picker is the frontmost window, re-verified.
        r = cm.osa('tell application "System Events" to tell process "OsxFL"\n'
                   f'  perform action "AXRaise" of window "{PICKER}"\n'
                   'end tell')
        time.sleep(0.4)
        sel = next((b for b in cm.ocr_boxes(cm.shot())
                    if _key(b.text) == want), None)
        if sel is None or abs(sel.cy - hit.cy) > 3:
            log("picker still open and the row moved; nothing confirmed")
            return False
        # live 2026-10-05 (PE 26.1.6): Return did NOT confirm — the picker stayed
        # open with the row highlighted (and FL then refused every exec with
        # "Operation unsafe at current time"). A second double-click on the
        # re-verified row did. Return stays as the last resort.
        if not cm.require_fl_front():
            log(f"FL is not frontmost ({cm.frontmost_app()!r}); stopped before clicking")
            return False
        cm._click(sel.cx, sel.cy, double=True)
        time.sleep(2.0)
        if cm.window_by_name(PICKER) is not None and cm.require_fl_front():
            cm.keypress("return")
            time.sleep(2.0)
        if cm.window_by_name(PICKER) is not None:
            log("picker still open after a second double-click and Return")
            return False
        log("confirmed the selected row with a second double-click")
    return True


def selected_track(conn) -> int:
    return _exec(conn, "import json, mixer\nprint(json.dumps(mixer.trackNumber()))")


def add_effect(track: int, plugin: str, conn=None, log=print) -> dict[str, Any]:
    """Insert `plugin` on mixer `track`; verified by the slot read-back."""
    if conn is None:
        from fl_studio_mcp.utils.connection import get_connection
        conn = get_connection()
    lines: list[str] = []

    def _log(m):
        lines.append(m)
        log(m)

    from fl_studio_mcp.utils.ui_guard import ensure_ready
    ready = ensure_ready(conn, need_front=True)          # picker/dialog/popup cleared
    if not ready["ready"]:
        return {"ok": False, "error": f"FL not ready: {ready['blockers'] or ready['front']}",
                "log": lines}
    before = track_slots(conn, track)
    if all(before):
        return {"ok": False, "error": f"track {track} has no free effect slot",
                "slots": before, "log": lines}
    # the track selected BEFORE we move is where a drifted insert lands
    prev = selected_track(conn)
    watch = [t for t in {prev} if isinstance(t, int) and t != track]
    before_other = {t: track_slots(conn, t) for t in watch}
    if not select_track(conn, track):
        return {"ok": False, "error": f"could not select mixer track {track}",
                "log": lines}
    _log(f"track {track} selected; slots before: {before}")
    try:
        picked = pick_from_picker(plugin, _log, conn=conn)
        reason = lines[-1] if lines else "picker failed"
    finally:
        close_picker(_log)          # success closes it too; a no-op then
    if not picked:
        # report the REAL failure, not the clean-up line (live 2026-10-05: every
        # miss read "closed the leftover plugin picker")
        return {"ok": False, "error": reason, "log": lines}
    after = before
    for _ in range(10):
        after = track_slots(conn, track)
        if after != before:
            break
        time.sleep(0.5)
    new = [s for s in range(SLOTS) if after[s] and after[s] != before[s]]
    if not new:
        stray = _stray(conn, watch, before_other)
        if stray:
            _log(f"WRONG TRACK: {stray['plugin']!r} landed on track "
                 f"{stray['track']} slot {stray['slot']}, not track {track}")
            return {"ok": False, "error": lines[-1], "stray": stray,
                    "slots": after, "log": lines}
        _log(f"no new plugin appeared on track {track}: {after}")
        return {"ok": False, "error": lines[-1], "slots": after, "log": lines}
    slot = new[0]
    ok = plugin.strip().lower() in after[slot].lower()
    _log(f"slot {slot}: {after[slot]!r}")
    if not ok:
        # the wrong plugin landed: take it out again, never leave a stray
        from fl_studio_mcp.utils.remove_effect import remove_effect
        undo = remove_effect(track, slot, expect=after[slot], conn=conn, log=_log)
        _log(f"wrong plugin {after[slot]!r} removed again: {undo.get('ok')}")
        after = undo.get("slots") or after
    if ok:
        # FL opens the plugin's window on insert; close it again (live 2026-10-06: a
        # Fruity Delay 3 editor stayed open after setup and covered the mixer)
        from fl_studio_mcp.utils.plugin_preset_ui import close_editor
        close_editor(conn, track, slot)
    return {"ok": ok, "track": track, "slot": slot, "plugin": after[slot],
            "slots": after, "log": lines,
            **({} if ok else {"error": f"slot {slot} holds {after[slot]!r}, not {plugin!r}"})}

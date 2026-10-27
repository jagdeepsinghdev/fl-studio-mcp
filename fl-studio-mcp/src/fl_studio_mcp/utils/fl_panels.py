"""Panel-aware screen preparation: put exactly the window a step needs on top.

Owner idea 2026-10-02 ("panel aware selector or loaders"). Every screen-driven
step (roll wrench, Sampler 'Load sample file', Edison buttons, mixer slots)
failed the same way at least once: ANOTHER window covered the target — a new
channel's FLEX editor over the roll, the roll over the Sampler editor, a
maximized mixer over Edison. All failed safely (hint checks), but the run
stopped. FL's own View menu (native, System Events — no pixels) has the two
moves needed:

  clear_plugins()          View > Close all plugin windows
                           (before piano-roll work: editors cover the roll)
  visible() / set_visible() the 5 main panels through ui.getVisible /
                           hideWindow / showWindow (API, no pixels)
  show_channel_editor(i)   channel i's editor with nothing over it (roll +
                           mixer hidden); restore() puts the panels back
  (focus_only — View > Close all unfocused windows — is too blunt: it kept
  the roll and closed the editor that had just been opened)

Steps that read the screen call these first, so they never depend on what
the previous step (or the user) left open.
"""

from __future__ import annotations

import json
import time

from fl_studio_mcp.utils import custom_menu as cm

# FL's main panels (midi.wid*): ui.getVisible / hideWindow / showWindow work
# on PE (probed 2026-10-02) — panel awareness through the API, no pixels.
MIXER, CHANNEL_RACK, PLAYLIST, PIANO_ROLL, BROWSER = 0, 1, 2, 3, 4


def _exec(conn, code: str) -> str:
    return (conn.send_command("probe.exec", {"code": code}) or {}).get("stdout", "")


def visible(conn) -> dict[int, bool]:
    """{wid: visible} for the 5 main panels."""
    out = _exec(conn, "import ui, json\nprint(json.dumps({w: ui.getVisible(w) for w in range(5)}))")
    return {int(k): bool(v) for k, v in json.loads(out.strip().splitlines()[-1]).items()}


def set_visible(conn, states: dict[int, bool]) -> None:
    lines = ["import ui"] + [f"ui.{'showWindow' if v else 'hideWindow'}({int(w)})"
                             for w, v in states.items()]
    _exec(conn, "\n".join(lines))
    time.sleep(0.4)


def clear_plugins() -> bool:
    cm.focus_fl()
    ok = cm.menu_bar_click("View", "Close all plugin windows")
    time.sleep(0.6)
    return ok


def focus_only() -> bool:
    cm.focus_fl()
    ok = cm.menu_bar_click("View", "Close all unfocused windows")
    time.sleep(0.6)
    return ok


def show_channel_editor(conn, index: int) -> dict[int, bool]:
    """Channel `index`'s editor with nothing over it: plugin windows closed,
    the piano roll and the mixer hidden (they covered the Sampler editor /
    Edison on 2026-10-02). Returns the panels' previous visibility — pass it
    to restore() when done."""
    before = visible(conn)
    clear_plugins()
    set_visible(conn, {PIANO_ROLL: False, MIXER: False, CHANNEL_RACK: True})
    name = _channel_name(conn, index)
    conn.send_command("probe.exec", {"code": (
        f"import channels\nchannels.selectOne({int(index)})")})
    # channels.showEditor() does not open a Sampler's window (probed
    # 2026-10-02: no effect with 1 or 3 args); the channel rack's name
    # button does — the click FL users make. Click only while the editor's
    # title is NOT on screen (the button toggles), then require the title.
    if not editor_open(name):
        btn = rack_name_button(name)
        if btn is not None:
            cm._click(btn.cx, btn.cy)
            time.sleep(1.0)
    return before


def _norm(t: str) -> str:
    return "".join(ch for ch in t.lower() if ch.isalnum())


def rack_name_button(name: str):
    """The channel rack's name button for `name`. Full-screen OCR garbles the small rack labels
    (live 2026-10-11: 'Kick AFRO' -> 'KCKATRU', 'Hat AFRO' missed, so two kit loads failed 3/3);
    fall back to a 3x-zoomed OCR of the name column and a fuzzy, unique best match."""
    import difflib
    want = _norm(name)
    for boxes in (lambda: cm.ocr_boxes(cm.shot()), lambda: cm.ocr_region(0, 100, 500, 900, scale=3)):
        bs = [b for b in boxes() if b.x < 500]
        exact = [b for b in bs if _norm(b.text) == want]
        if len(exact) == 1:
            return exact[0]
        scored = sorted(((difflib.SequenceMatcher(None, _norm(b.text), want).ratio(), b) for b in bs),
                        key=lambda t: -t[0])
        if scored and scored[0][0] >= 0.85 and (len(scored) == 1 or scored[1][0] < scored[0][0] - 0.1):
            return scored[0][1]
    return None


def _channel_name(conn, index: int) -> str:
    chans = conn.send_command("channels.getAll").get("channels", [])
    return next((c.get("name") or "" for c in chans if c.get("index") == index), "")


def editor_open(name: str) -> bool:
    """True when a window titled '<name> (Insert N)' is on screen."""
    want = f"{name.lower()} (insert"
    return any(want in b.text.lower() for b in cm.ocr_boxes(cm.shot()))


def restore(conn, before: dict[int, bool]) -> None:
    """Put the main panels back the way show_channel_editor() found them."""
    set_visible(conn, before)

"""The Edison flow (S4.2 / L16) as library steps, shared by the fl_edison MCP
tool and scripts/edison_run.py. Live-proven 2026-10-01 (PE 26.1.6):

  open             Add ▸ Effect ▸ More plugins… → picker → double-click Edison
  load_regions     bake clip path + regions into 0MCP-Workbench.pyscript →
                   right-click ▸ Tools ▸ Run script ▸ Workbench ▸ 0MCP-Workbench
                   → OCR the "MCP-EDISON …" reply dialog → OK
  send_to_channel  right-click Edison's "Send to playlist as audio clip / to
                   channel" button: the clip + regions replace the SELECTED
                   channel's sample; FL writes Audio/Sliced audio/<name>_N.wav
                   (cue/labl regions), which is parsed to verify

Every step drives FL's custom-drawn UI (no accessibility tree), so each
click target is located by OCR first and toolbar buttons are confirmed by
their hover hint before clicking. Steps return {"ok": bool, ..., "log": [...]}.
FL must be the frontmost app; nobody should use the mouse meanwhile.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any, Callable

from fl_studio_mcp.utils import custom_menu as cm
from fl_studio_mcp.utils import edison_bridge as eb

# an empty spot to park the pointer between hint polls (re-hover = fresh hint)
SAFE_PARK = (1650, 60)


class _Run:
    """Collects log lines (and echoes them to an optional sink)."""

    def __init__(self, sink: Callable[[str], None] | None = None):
        self.lines: list[str] = []
        self.sink = sink

    def __call__(self, msg: str) -> None:
        self.lines.append(msg)
        if self.sink:
            self.sink(msg)

    def result(self, ok: bool, **kw: Any) -> dict[str, Any]:
        if not ok and "error" not in kw:
            kw["error"] = self.lines[-1] if self.lines else "failed"
        return {"ok": ok, **kw, "log": self.lines}


def _front(log: _Run) -> bool:
    if cm.require_fl_front():
        return True
    log(f"FL Studio is not the frontmost app ({cm.frontmost_app()!r})")
    return False


# ------------------------------------------------------------------ locate --

def _scan():
    """One 3x OCR pass over the window band. 3x, not 2x: at 2x the dim title
    "Edison (Insert 6)" was missed, so open() added a second Edison
    (2026-10-01); the faint logo also needs 3x."""
    return cm.ocr_region(0, 100, 1920, 900, scale=3)


def locate(boxes=None, _retry: bool = True) -> dict[str, Any] | None:
    """Where Edison is on screen: its right-click point and the top of the
    area its menus open in. Anchors, in order: the title "Edison (<slot>)"
    (never a bare "Edison": a channel named "Edison Regions" matched that),
    an empty Edison's "Click to load a sample", the "edison" logo."""
    boxes = _scan() if boxes is None else boxes
    title = next((b for b in boxes if "edison (" in b.text.lower()), None)
    if title is not None:
        # window origin ~ (title.x-12, title.y-14); clip center ~ +260, +330
        return {"anchor": title.text, "rc": (title.x + 260, title.y + 330),
                "top": title.y + 20}
    empty = next((b for b in boxes
                  if "click to load a sample" in b.text.lower()), None)
    if empty is not None:
        return {"anchor": empty.text, "rc": (empty.cx, empty.cy - 120),
                "top": empty.cy - 330}
    logo = _logo(boxes)
    if logo is not None and cm.window_by_name("Select effect plugin") is None:
        # title = logo + (-599, -25), measured on two window positions
        return {"anchor": logo.text, "rc": (logo.x - 339, logo.y + 305),
                "top": logo.y - 5}
    if _retry and boxes is not None and uncover():
        return locate(None, _retry=False)
    return None


def uncover(log=lambda m: None) -> bool:
    """Close a covering FL mixer panel (a maximized 'Mixer - …' hid Edison
    during load_song, 2026-10-02) by its ✕, confirmed by the hint 'Close'.
    True when something was closed."""
    boxes = cm.ocr_boxes(cm.shot())
    title = next((b for b in boxes if b.text.strip().lower().startswith("mixer -")), None)
    if title is None:
        return False
    for x in range(1915, title.x + 120, -8):
        if cm.hint_at(x, title.cy).strip().lower().startswith("close"):
            cm._click(x, title.cy)
            time.sleep(0.8)
            log(f"closed the covering '{title.text}' panel")
            return True
    return False


def _logo(boxes=None):
    """Edison's faint 'edison' logo (top right): the toolbar anchor. The logo
    is drawn large (≈19 px tall at 1x); the plugin picker's 'Edison' LIST ROW
    (≈10 px) must never count — it made open() report success while the
    picker was still open (2026-10-02)."""
    boxes = _scan() if boxes is None else boxes
    return next((b for b in boxes if b.text.strip().lower() == "edison"
                 and b.h >= 15), None)


def _is_playing() -> bool | None:
    """FL's main transport state (None if the controller can't say)."""
    try:
        from fl_studio_mcp.utils.connection import get_connection
        r = get_connection().send_command("state.snapshot", {})
        return bool(r.get("state", {}).get("transport", {}).get("is_playing"))
    except Exception:  # noqa: BLE001
        return None


# -------------------------------------------------------------------- open --

def open_edison(sink=None) -> dict[str, Any]:
    """Open Edison (on the selected mixer insert) unless one is visible."""
    log = _Run(sink)
    if not _front(log):
        return log.result(False)
    if locate() is not None:
        log("Edison already open")
        return log.result(True, already_open=True)
    # the picker path with the slot read-back (utils/add_effect): the slot
    # must really hold Edison, a wrong row is removed again automatically
    from fl_studio_mcp.utils.add_effect import add_effect, selected_track
    from fl_studio_mcp.utils.connection import get_connection
    conn = get_connection()
    track = selected_track(conn)
    r = add_effect(track, "Edison", conn=conn, log=log)
    if not r.get("ok"):
        return log.result(False, error=r.get("error"))
    time.sleep(1.5)
    found = locate() is not None
    log(f"Edison opened on mixer track {track} slot {r['slot']}" if found
        else "Edison inserted but its window is not visible")
    return log.result(found, already_open=False, track=track, slot=r["slot"])


# ------------------------------------------------------------ load_regions --

def _read_reply(rid: str, log: _Run, timeout: float) -> dict | None:
    deadline = time.monotonic() + timeout
    head = boxes = None
    while True:
        boxes = cm.ocr_region(0, 0, 1920, 1080, scale=2)
        head = next((b for b in boxes if "MCP-EDISON" in b.text.upper()
                     or "MCP-ED1SON" in b.text.upper()), None)
        if head is not None or time.monotonic() >= deadline:
            break
        time.sleep(1.0)
    if head is None:
        log("no MCP-EDISON reply dialog: the script did not run")
        return None
    body = [b for b in boxes if head.y - 4 <= b.y <= head.y + 120
            and head.x - 10 <= b.x <= head.x + 520]   # the reply can wrap
    body.sort(key=lambda b: (b.y // 6, b.x))
    reply = eb.parse_reply(" ".join(b.text for b in body)) or {}
    log(f"reply: {reply}")
    # "OK" is too small for the 2x pass: re-OCR the dialog at 3x
    near = cm.ocr_region(max(0, head.x - 23), max(0, head.y - 36), 520, 170)
    ok_btn = next((b for b in near if b.text.strip().upper() == "OK"), None)
    if ok_btn is not None:
        cm._click(ok_btn.cx, ok_btn.cy)
    else:
        log("reply dialog's OK not found: dialog left open")
    return reply


def load_regions(clip: str | None, regions: list[dict],
                 clear_regions: bool = True, timeout: float = 60.0,
                 sink=None) -> dict[str, Any]:
    """Load `clip` into the open Edison (optional) and stamp `regions`
    ([{name, start_s, end_s}]) via the generic script; verified by its reply."""
    log = _Run(sink)
    if not _front(log):
        return log.result(False)
    rid, src = eb.build_script(load=clip, regions=regions,
                               clear_regions=clear_regions)
    eb.install(src)
    log(f"request {rid}: load={clip} regions={len(regions)}")
    where = locate()
    if where is None:
        log("Edison is not open (call action=open first)")
        return log.result(False, request_id=rid)
    rc_x, rc_y = where["rc"]
    rx, ry = max(0, rc_x - 20), max(0, where["top"])
    # OCR only right of / below the click: FL's menu bar has a "Tools" too
    chain = [["Tools"], ["Run script"], ["Workbench"], [eb.SCRIPT_NAME]]
    if cm.menu_cascade(rc_x, rc_y, chain, region=(rx, ry, 1920 - rx, 1080 - ry),
                       settle=1.3, log=log) is None:
        return log.result(False, request_id=rid)
    reply = _read_reply(rid, log, timeout)
    if reply is None:
        return log.result(False, request_id=rid)
    ok = (str(reply.get("id")) == rid and reply.get("ok") == 1
          and reply.get("added") == len(regions))
    if not ok:
        log(f"reply mismatch: wanted id={rid} ok=1 added={len(regions)}")
    return log.result(ok, request_id=rid, reply=reply)


# --------------------------------------------------------- send_to_channel --

def send_to_channel(channel: int | None = None, out: str | None = None,
                    expected: int | None = None, sink=None) -> dict[str, Any]:
    """Right-click Edison's send button: the clip + regions replace the
    selected (or `channel`) Sampler's sample. Verified by parsing the WAV FL
    writes to Audio/Sliced audio; optionally copied to `out`."""
    log = _Run(sink)
    if not _front(log):
        return log.result(False)
    if channel is not None:
        from fl_studio_mcp.utils.connection import get_connection
        get_connection().send_command("channels.selectOne",
                                      {"index": int(channel), "use_global": True})
        time.sleep(0.5)
        log(f"selected channel {channel}")
    logo = _logo()
    if logo is None and uncover(log):
        logo = _logo()
    if logo is None:
        log("Edison logo not found (Edison closed or covered?)")
        return log.result(False)
    # send = logo + (62, 69); stop = logo + (-506, 17) — measured on two
    # window positions. Hover first: click only if the hint names it.
    sx, sy = logo.x + 62, logo.y + 69
    # FL's hint bar also shows status text ("Loading: drums.wav") for a few
    # seconds after a load: wait for the button's own hint, bounded.
    hint = ""
    for _ in range(8):
        hint = cm.hint_at(sx, sy)
        if "send to playlist" in hint.lower():
            break
        cm.move(SAFE_PARK[0], SAFE_PARK[1])
        time.sleep(1.0)
    else:
        log(f"send button not at ({sx},{sy}): hint={hint!r}")
        return log.result(False)
    playing_before = _is_playing()
    t0 = time.time() - 1
    cm._click(sx, sy, button="right")
    time.sleep(2.0)
    px, py = logo.x - 506, logo.y + 17   # the send starts preview playback
    if "stop" in cm.hint_at(px, py).lower():
        cm._click(px, py)
        log("stopped Edison preview playback")
    if playing_before is False and _is_playing():
        # FL's main transport started during the send (seen 2026-10-01,
        # cause unknown): put it back the way the user had it
        from fl_studio_mcp.utils.connection import get_connection
        get_connection().send_command("transport.stop", {})
        log("FL transport had started during the send: stopped it")
    wav = None
    for _ in range(20):
        wav = eb.newest_sliced_audio(t0)
        if wav is not None:
            break
        time.sleep(0.5)
    if wav is None:
        log("no new WAV in Sliced audio: the send did not happen")
        return log.result(False)
    regions = eb.wav_regions(wav)
    log(f"{wav.name}: {len(regions)} regions")
    copied = None
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(wav, out)
        copied = str(out)
    ok = expected is None or len(regions) == expected
    if not ok:
        log(f"region count {len(regions)} != expected {expected}")
    return log.result(ok, wav=str(wav), copied_to=copied,
                      region_count=len(regions),
                      first_regions=[r["name"] for r in regions[:5]])

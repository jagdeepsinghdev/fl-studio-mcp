"""Mixer track housekeeping for fl_mixer — server-side, via probe.exec (no controller change).

Actions (all read back in a SEPARATE trip — FL applies mixer writes after the
script trip, see CLAUDE.md §5 "Meters + faders"):
  name(track, name) · color(track, color "#RRGGBB") · mute(track, on) ·
  solo(track, on) · stereo_sep(track, value -1..1) · route_only(track, to) ·
  unroute(track, to) · list_fx(track)

route_only = FL's "Route to this track only": every other active route out of
`track` (the master included) is switched OFF, then `track -> to` ON. This is the
gap the bus layout needed (setSendLevel can only lower a route to 0, never remove
it). Built 2026-10-05; NOT live-verified yet.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from fl_studio_mcp.tools.mixer_v2 import _exec

TRACK_ACTIONS = ("name", "color", "mute", "solo", "stereo_sep",
                 "route_only", "unroute", "list_fx", "add_tracks")
_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")
SETTLE = 0.3


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate_track(action: str, p: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    if action == "add_tracks":
        n = p.get("count", 1)
        return [] if _int(n) and 1 <= n <= 32 else ["add_tracks.count: 1..32"]
    t = p.get("track")
    if not _int(t) or t < 0:
        errs.append(f"{action}.track: a mixer track index >= 0 ({t!r})")
    if action == "name" and not (isinstance(p.get("name"), str) and p["name"].strip()):
        errs.append("name.name: non-empty string required")
    if action == "color" and not (isinstance(p.get("color"), str) and _HEX.match(p["color"])):
        errs.append(f"color.color: '#RRGGBB' required ({p.get('color')!r})")
    if action in ("mute", "solo") and not isinstance(p.get("on"), bool):
        errs.append(f"{action}.on: true/false required")
    if action == "stereo_sep":
        try:
            if not -1.0 <= float(p.get("value")) <= 1.0:
                errs.append("stereo_sep.value: -1 (mono) .. 0 .. 1 (wide)")
        except (TypeError, ValueError):
            errs.append("stereo_sep.value: a number -1..1 required")
    if action in ("route_only", "unroute"):
        to = p.get("to")
        if not _int(to) or to < 0:
            errs.append(f"{action}.to: a mixer track index >= 0 ({to!r})")
        elif to == t:
            errs.append(f"{action}: track and to must differ")
    return errs


def _routes(conn, track: int) -> list[dict]:
    return json.loads(_exec(conn, (
        "import json, mixer\n"
        f"t = {track}\n"
        "print(json.dumps([[d, round(mixer.getRouteToLevel(t, d), 3)] "
        "for d in range(mixer.trackCount()) if d != t and mixer.getRouteSendActive(t, d)]))")))


def _info(conn, track: int) -> dict:
    return json.loads(_exec(conn, (
        "import json, mixer\n"
        f"t = {track}\n"
        "print(json.dumps({'name': mixer.getTrackName(t), "
        "'color': '#%06X' % (mixer.getTrackColor(t) & 0xFFFFFF), "
        "'muted': bool(mixer.isTrackMuted(t)), 'solo': bool(mixer.isTrackSolo(t)), "
        "'stereo_sep': round(mixer.getTrackStereoSep(t), 3)}))")))


def list_fx(conn, track: int) -> list[dict]:
    """Every loaded slot: plugin name, on/bypassed. (No slot name: plugins.getName
    with default args returns a PARAM label — live 2026-10-05: '^b^aInput gain'.)"""
    rows = json.loads(_exec(conn, (
        "import json, mixer, plugins\n"
        f"t = {track}\n"
        "out = []\n"
        "for s in range(10):\n"
        "    if plugins.isValid(t, s):\n"
        "        out.append([s, plugins.getPluginName(t, s), mixer.getPluginMuteState(t, s)])\n"
        "print(json.dumps(out))")))
    return [{"slot": s, "plugin": p, "on": bool(m)} for s, p, m in rows]


#: FL's hint for the mixer toolbar "+" (add an insert). Live-confirmed words only
#: are trusted; anything else refuses (never a blind click).
_ADD_HINTS = ("add", "insert", "new track", "track")


def _track_count(conn) -> int:
    """Real inserts (trackCount includes Master and FL's internal 'current' slot)."""
    return int(json.loads(_exec(conn, "import json, mixer\nprint(json.dumps(mixer.trackCount()))")))


def add_tracks(conn, count: int, log=lambda m: None) -> dict:
    """Add `count` mixer inserts with the mixer toolbar's "+" (no API creates tracks:
    the 75 mixer.* calls in v45 have none; no catalog shortcut either). The "+" is
    located next to the OCR'd "Wide" label and accepted ONLY when FL's hint bar names
    it; every click is proven by trackCount + 1. Built 2026-10-06."""
    from fl_studio_mcp.utils import custom_menu as cm
    from fl_studio_mcp.utils.add_effect import ensure_mixer_panel
    before = _track_count(conn)
    if not cm.require_fl_front():
        return {"action": "add_tracks", "success": False,
                "error": f"FL not frontmost ({cm.frontmost_app()!r})"}
    ensure_mixer_panel(log)
    bar = next((b for b in cm.ocr_boxes(cm.shot()) if b.text.strip().lower() == "wide"), None)
    if bar is None:
        return {"action": "add_tracks", "success": False, "error": "mixer toolbar not on screen"}
    plus = None
    for dx in range(-12, -48, -3):                     # the "+" sits just left of "Wide"
        hint = cm.hint_at(bar.x + dx, bar.cy, settle=0.3).lower()
        if any(h in hint for h in _ADD_HINTS):
            plus = (bar.x + dx, bar.cy, hint)
            break
    if plus is None:
        return {"action": "add_tracks", "success": False,
                "error": "no add-track button confirmed by FL's hint next to 'Wide'"}
    added = 0
    for _ in range(int(count)):
        if not cm.require_fl_front(retry_focus=False):
            break
        n0 = _track_count(conn)
        cm._click(plus[0], plus[1])
        time.sleep(0.6)
        if _track_count(conn) == n0 + 1:
            added += 1
        else:
            break
    after = _track_count(conn)
    return {"action": "add_tracks", "success": added == int(count), "added": added,
            "track_count_before": before, "track_count_after": after, "hint": plus[2],
            **({} if added == int(count) else {"error": f"only {added}/{count} added"})}


def run_track_action(action: str, conn, p: dict[str, Any], sleep=time.sleep) -> dict:
    if action == "add_tracks":
        return add_tracks(conn, int(p.get("count", 1)))
    t = int(p["track"])
    if action == "list_fx":
        return {"action": action, "success": True, "track": t, "slots": list_fx(conn, t)}

    if action in ("route_only", "unroute"):
        to = int(p["to"])
        before = _routes(conn, t)
        if action == "route_only":
            code = ("import mixer\n"
                    f"t, to = {t}, {to}\n"
                    "for d in range(mixer.trackCount()):\n"
                    "    if d not in (t, to) and mixer.getRouteSendActive(t, d):\n"
                    "        mixer.setRouteTo(t, d, 0)\n"
                    "mixer.setRouteTo(t, to, 1)\n"
                    "mixer.afterRoutingChanged()\nprint('ok')")
        else:
            code = (f"import mixer\nmixer.setRouteTo({t}, {to}, 0)\n"
                    "mixer.afterRoutingChanged()\nprint('ok')")
        _exec(conn, code)
        sleep(SETTLE)
        after = _routes(conn, t)
        dests = [d for d, _ in after]
        ok = dests == [to] if action == "route_only" else to not in dests
        return {"action": action, "success": ok, "track": t, "to": to,
                "routes_before": before, "routes_after": after,
                **({} if ok else {"error": "read-back routes disagree (see routes_after)"})}

    before = _info(conn, t)
    if action == "name":
        code = f"import mixer\nmixer.setTrackName({t}, {json.dumps(p['name'])})\nprint('ok')"
        key, want = "name", p["name"]
    elif action == "color":
        rgb = int(_HEX.match(p["color"]).group(1), 16)
        code = f"import mixer\nmixer.setTrackColor({t}, {rgb})\nprint('ok')"
        key, want = "color", "#%06X" % rgb
    elif action == "mute":
        code = f"import mixer\nmixer.muteTrack({t}, {1 if p['on'] else 0})\nprint('ok')"
        key, want = "muted", bool(p["on"])
    elif action == "solo":
        code = f"import mixer\nmixer.soloTrack({t}, {1 if p['on'] else 0})\nprint('ok')"
        key, want = "solo", bool(p["on"])
    else:  # stereo_sep
        v = float(p["value"])
        code = f"import mixer\nmixer.setTrackStereoSep({t}, {v})\nprint('ok')"
        key, want = "stereo_sep", round(v, 3)
    _exec(conn, code)
    sleep(SETTLE)
    after = _info(conn, t)
    got = after.get(key)
    ok = (abs(got - want) < 0.02) if isinstance(want, float) else got == want
    return {"action": action, "success": ok, "track": t, "before": before, "after": after,
            **({} if ok else {"error": f"read-back {key}={got!r}, wanted {want!r}"})}

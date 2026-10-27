"""Drift guard: every domain-tool action must send ONLY keys its controller
handler reads, to a handler that exists.

2026-10-01 audit found four silent mis-targets this way: fl_plugin set_param
(index/param vs plugin_index/param_index -> channel 0 param 0), fl_channel
route (index/to vs channel_index/mixer_track -> channel 0 to master),
fl_pattern set_len (pattern vs 0-based index -> always Pattern 1),
fl_transport position (value/unit vs position/mode -> always 0). An unread
key does not raise — the handler just uses its default — so only a source
cross-check catches it.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

SRC = (Path(__file__).resolve().parents[1] / "fl_controller"
       / "device_FLStudioMCP.py").read_text()
DISPATCH = dict(re.findall(r'action == "([\w.]+)":\s*\n\s*return (\w+)\(params\)', SRC))

# handled server-side or honestly refused before routing (never reach _route's
# controller action), or controller actions not yet implemented on purpose
NOT_CONTROLLER = {
    ("channel_v2", "add"),          # utils/add_channel (native Add menu)
    ("channel_v2", "clone"),        # server-side: the channel menu (utils/clone_channel)
    ("mixer_v2", "add_fx"),         # server-side: native plugin picker (utils/add_effect)
    ("mixer_v2", "fix_clipping"),   # server-side: get_peaks + probe.exec fader search
    ("mixer_v2", "fx_on"),          # server-side: probe.exec REC_Plug_Mute + read-back
    ("channel_v2", "load_sample"),
    ("channel_v2", "group"),        # server-side: utils/channel_group (Alt+G + paste)  # server-side: the Sampler's Open panel
    ("pattern_v2", "chain"),        # server-side orchestration (S5): multi-action, not one controller call
    ("plugin_v2", "load_preset"),   # not_verified_yet
    ("plugin_v2", "echo"),          # server-side: named knobs via list_params + set_param
    ("plugin_v2", "reverb"),
    ("plugin_v2", "chorus"),
    ("plugin_v2", "get_fx"),
    ("mixer_v2", "eq_preset"),      # server-side: solves via mixer.getEq/setEq
    # mixer_tracks.py / plugin_dial.py (2026-10-05): server-side probe.exec + read-back
    ("mixer_v2", "name"), ("mixer_v2", "color"), ("mixer_v2", "mute"),
    ("mixer_v2", "solo"), ("mixer_v2", "stereo_sep"), ("mixer_v2", "route_only"),
    ("mixer_v2", "unroute"), ("mixer_v2", "list_fx"), ("mixer_v2", "add_tracks"),
    ("plugin_v2", "dial"), ("plugin_v2", "find_preset"), ("plugin_v2", "preset_ui"), ("plugin_v2", "snapshot"), ("plugin_v2", "restore"),
    # set_timesig wired in v10.4e (2026-10-01) — no longer in this set
}
# handlers dispatched without params (no keys to check)
NO_PARAMS = {"transport.start", "transport.stop", "transport.record",
             "channels.getAll"}

DUMMY = {"index": 1, "param": 1, "value": 0.5, "volume": 0.5, "pan": 0.0,
         "name": "x", "to": 2, "muted": True, "solo": True, "plugin": "FLEX",
         "steps": [True] * 16, "step": 0, "pattern": 2, "track": 1, "src": 1,
         "dst": 2, "level": 0.5, "beats": 8, "length_beats": 8, "color": 1,
         "slot_index": -1, "bpm": 120, "numerator": 4, "denominator": 4,
         "speed": 1.0, "swing": 0.1, "mode": "pattern", "unit": "seconds",
         "armed": False, "preset": 1, "_bpm": 120.0,
         "band": 1, "gain": 0.5, "freq": 0.5, "bw": 0.5}


def _reads(handler: str) -> set[str]:
    body = SRC.split(f"def {handler}(", 1)[1].split("\ndef ", 1)[0]
    return (set(re.findall(r'params\.get\("(\w+)"', body))
            | set(re.findall(r'params\["(\w+)"\]', body)))


CASES = []
for _mod in ("transport_v2", "mixer_v2", "channel_v2", "pattern_v2", "plugin_v2"):
    _m = importlib.import_module(f"fl_studio_mcp.tools.{_mod}")
    CASES += [(_mod, a) for a in _m.ACTIONS if (_mod, a) not in NOT_CONTROLLER]


@pytest.mark.parametrize("mod,action", CASES)
def test_sent_keys_are_read_by_the_controller(mod, action):
    m = importlib.import_module(f"fl_studio_mcp.tools.{mod}")
    params = dict(DUMMY)
    if action == "get_steps":
        params["steps"] = 16
    ca, cp = m._route(action, params)
    if ca in NO_PARAMS:
        return
    handler = DISPATCH.get(ca)
    assert handler, f"{mod}.{action} -> {ca}: no controller handler"
    extra = set(cp) - _reads(handler)
    assert not extra, (f"{mod}.{action} -> {ca} sends {sorted(extra)}; "
                       f"{handler} reads {sorted(_reads(handler))}")


@pytest.mark.parametrize("mod,action", [c for c in CASES
                                         if c[1].startswith(("get_", "list_"))])
def test_read_actions_are_tiered_read(mod, action):
    """L5: get_step_param was tiered WRITE (unknown -> WRITE default), so a
    read was treated as a write ("_undo_missing")."""
    from fl_studio_mcp.safety import TIER_TABLE, Tier
    m = importlib.import_module(f"fl_studio_mcp.tools.{mod}")
    params = dict(DUMMY, steps=16)
    ca, _ = m._route(action, params)
    assert TIER_TABLE.get(ca) == Tier.READ, f"{mod}.{action} -> {ca} is not READ"

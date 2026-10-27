"""B4: fl_channel — validation + routing + same-trip write contract.

Verified offline:
  - set_vol/set_pan/rename/route/mute/solo route to the right controller action
  - add → channels.add (the ONLY channel-creation path; native Add menu)
  - clone → channels.clone (no importable API in v45; native-menu method)
  - range/type validation rejected pre-FL
  - a write returns state_after + undo_saved; the safety layer injects _undo_name
"""


from fl_studio_mcp.tools.channel_v2 import ACTIONS, _route, fl_channel, validate

# ---------------------------------------------------------------------------
# Validation (rejected before FL)
# ---------------------------------------------------------------------------


def test_all_eight_actions_route():
    cases = {
        "set_vol": ({"index": 2, "volume": 0.5},
                   ("channels.setVolume", {"index": 2, "volume": 0.5})),
        "set_pan": ({"index": 1, "pan": 0.3},
                   ("channels.setPan", {"index": 1, "pan": 0.3})),
        "rename": ({"index": 0, "name": "Dhol"},
                   ("channels.setName", {"index": 0, "name": "Dhol"})),
        "route": ({"index": 3, "to": 1},
                  ("channels.routeToMixer", {"channel_index": 3, "mixer_track": 1})),
        "mute": ({"index": 4, "muted": True},
                 ("channels.mute", {"index": 4, "muted": True})),
        "solo": ({"index": 5, "solo": False},
                 ("channels.solo", {"index": 5, "solo": False})),
        "clone": ({"index": 2, "name": "Copy"},
                  ("channels.clone", {"index": 2, "name": "Copy"})),
        "add": ({"plugin": "FLEX", "name": "Piano"},
                ("channels.add", {"plugin": "FLEX", "name": "Piano"})),
    }
    for action, (give, want) in cases.items():
        got = _route(action, give)
        assert got == want, f"{action}: {got} != {want}"


def test_add_defaults_name_to_plugin():
    ca, cp = _route("add", {"plugin": "FLEX"})
    assert cp["name"] == "FLEX"


def test_volume_out_of_range_rejected():
    assert validate("set_vol", {"index": 1, "volume": 1.5})
    assert validate("set_vol", {"index": 1, "volume": -0.2})
    assert validate("set_vol", {"index": 1, "volume": 0.5}) == []


def test_pan_out_of_range_rejected():
    assert validate("set_pan", {"index": 1, "pan": 2.0})
    assert validate("set_pan", {"index": 1, "pan": -1.5})
    assert validate("set_pan", {"index": 1, "pan": -1.0}) == []


def test_rename_requires_nonempty_name():
    assert validate("rename", {"index": 1, "name": ""})
    assert validate("rename", {"index": 1, "name": "Dhol"}) == []


def test_add_requires_plugin():
    assert validate("add", {})  # missing plugin
    assert validate("add", {"plugin": "FLEX"}) == []  # name optional


def test_mute_solo_bool_type_enforced():
    assert validate("mute", {"index": 1, "muted": "yes"})
    assert validate("mute", {"index": 1, "muted": True}) == []
    assert validate("solo", {"index": 1, "solo": False}) == []


def test_negative_index_rejected():
    assert validate("set_vol", {"index": -1, "volume": 0.5})
    assert validate("mute", {"index": -1})


def test_unknown_action_rejected_with_list():
    r = validate("explode", {})
    assert "unknown action" in r[0]
    assert "add" in r[0]


# ---------------------------------------------------------------------------
# Same-trip write contract (mocked connection)
# ---------------------------------------------------------------------------


class _FakeConn:
    def __init__(self):
        self.calls = []

    def send_command(self, action, params=None, timeout=2.0):
        self.calls.append((action, dict(params or {})))
        if action == "channels.setVolume":
            return {"success": True, "protocol_v2": True,
                    "state_after": {"index": params["index"],
                                   "volume": params["volume"],
                                   "channel_name": "Kick"},
                    "undo_saved": "fl_set_vol"}
        if action == "channels.setName":
            return {"success": True, "protocol_v2": True,
                    "state_after": {"index": params["index"],
                                   "channel_name": params["name"]},
                    "undo_saved": "fl_rename"}
        if action == "channels.add":
            return {"success": True, "protocol_v2": True,
                    "result": params["name"],
                    "state_after": {"name": params["name"]},
                    "undo_saved": "fl_add"}
        return {"success": True, "protocol_v2": True, "state_after": {}}


def test_set_vol_returns_state_after_and_undo():
    conn = _FakeConn()
    r = fl_channel("set_vol", conn=conn, index=2, volume=0.5)
    assert r["success"] is True
    assert r["state_after"]["index"] == 2
    assert r["state_after"]["volume"] == 0.5  # v10.4e L14: linear 0-1 read-back
    assert r["undo_saved"]
    ca, cp = conn.calls[0]
    assert ca == "channels.setVolume"
    assert cp.get("_undo_name")  # safety layer injected the undo


def test_add_uses_the_native_add_menu_not_a_controller_action(monkeypatch):
    # v45 has no channel-creation API: "channels.add" never existed on the
    # controller (it returned Unknown action). add = utils/add_channel.
    calls = []
    monkeypatch.setattr(
        "fl_studio_mcp.utils.add_channel.setup_instrument",
        lambda plugin, label: calls.append((plugin, label)) or {
            "ok": True, "index": 6, "name": label, "instrument": plugin,
            "mixer_track": 7, "channel_count": 7})
    conn = _FakeConn()
    r = fl_channel("add", conn=conn, plugin="3x Osc", name="808")
    assert r["success"] is True
    assert r["result"]["index"] == 6 and r["result"]["mixer_track"] == 7
    assert calls == [("3x Osc", "808")]
    assert conn.calls == []  # never sent to the controller


def test_add_reports_menu_failure(monkeypatch):
    monkeypatch.setattr("fl_studio_mcp.utils.add_channel.setup_instrument",
                        lambda plugin, label: {"ok": False, "error": "no channel appeared"})
    r = fl_channel("add", conn=_FakeConn(), plugin="Nope")
    assert r["success"] is False and "no channel appeared" in r["error"]


def test_rename_returns_state_after():
    conn = _FakeConn()
    r = fl_channel("rename", conn=conn, index=0, name="Dhol")
    assert r["success"] is True
    assert r["state_after"]["channel_name"] == "Dhol"


def test_invalid_call_never_reaches_fl():
    conn = _FakeConn()
    r = fl_channel("set_vol", conn=conn, index=1, volume=9.0)
    assert r["success"] is False
    assert "valid_actions" in r
    assert conn.calls == []


# ---------------------------------------------------------------------------
# Step sequencer (set_steps / get_steps) — the coverage gap now closed
# ---------------------------------------------------------------------------


def test_set_steps_routes_to_set_step_sequence():
    ca, cp = _route("set_steps", {"index": 0, "steps": [1, 0, 1, 0, 1, 0, 0, 0,
                                                       0, 0, 0, 0, 0, 0, 0, 0]})
    assert ca == "channels.setStepSequence"
    # the controller reads 'channel' + 'pattern' (the step list)
    assert cp["channel"] == 0
    assert cp["pattern"] == [True, False, True, False, True, False, False, False,
                             False, False, False, False, False, False, False, False]


def test_set_steps_with_target_pattern():
    ca, cp = _route("set_steps", {"index": 1, "steps": [1, 0], "pattern": 2})
    assert cp["channel"] == 1
    assert cp["pattern"] == [True, False]
    assert cp["target_pattern"] == 2


def test_get_steps_defaults_to_16():
    ca, cp = _route("get_steps", {"index": 3})
    assert ca == "channels.getStepSequence"
    assert cp["channel"] == 3
    assert cp["steps"] == 16


def test_set_steps_requires_steps_list():
    assert validate("set_steps", {"index": 0})  # missing steps
    assert validate("set_steps", {"index": 0, "steps": "not a list"})
    assert validate("set_steps", {"index": 0, "steps": [1, 0, 1]}) == []


# ---------------------------------------------------------------------------
# v10: per-step parameters (P4)
# ---------------------------------------------------------------------------

def test_get_step_param_routes():
    ca, cp = _route("get_step_param", {"index": 2, "step": 5})
    assert ca == "channels.getStepParameter"
    assert cp == {"channel": 2, "step": 5, "param": "pVelocity"}


def test_set_step_param_routes_with_pattern():
    ca, cp = _route("set_step_param",
                    {"index": 2, "step": 5, "value": 90,
                     "param": "pVelocity", "pattern": 2})
    assert ca == "channels.setStepParameter"
    assert cp == {"channel": 2, "step": 5, "param": "pVelocity",
                  "value": 90, "target_pattern": 2}


def test_set_step_param_value_range_enforced():
    errs = validate("set_step_param", {"index": 0, "step": 0, "value": 128})
    assert errs, "value 128 must be rejected (0..127)"
    errs = validate("set_step_param", {"index": 0, "step": 0, "value": 127})
    assert not errs


def test_step_param_actions_in_action_list():
    assert "get_step_param" in ACTIONS
    assert "set_step_param" in ACTIONS


def test_set_vol_readback_is_linear_0_1():
    """v10.4e (L14): the controller's read-back is linear 0-1 now (the old
    getChannelVolume(index, True) passed True as the dB MODE arg, so 0.5
    came back as -12.7). 0.5 in → 0.5 out; the L4 dB relabel is retired."""
    class C:
        def send_command(self, action, params=None, timeout=None):
            return {"success": True, "volume": 0.5, "channel_name": "808",
                    "state_after": {"index": 6, "volume": 0.5}, "undo_saved": "u"}
    r = fl_channel("set_vol", conn=C(), index=6, volume=0.5)
    assert r["result"]["volume"] == 0.5 and "volume_db" not in r["result"]
    assert r["state_after"]["volume"] == 0.5

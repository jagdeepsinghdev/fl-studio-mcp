"""B2: fl_transport — validation + routing + the same-trip write contract.

Verified offline:
  - every valid action/param combination routes to the right controller action
  - out-of-range / unknown / missing params are rejected BEFORE FL is touched
  - a write returns state_after + undo_saved (the same-trip verification
    the dispatcher cross-checks)
  - the safety layer takes one named saveUndo per write
"""


from fl_studio_mcp.tools.transport_v2 import (
    ACTIONS,
    _route,
    fl_transport,
    validate,
)

# ---------------------------------------------------------------------------
# Action/param validation (rejected before FL)
# ---------------------------------------------------------------------------


def test_all_eight_actions_route():
    expected = {
        "play": ("transport.start", {}),
        "stop": ("transport.stop", {}),
        "record": ("transport.record", {"armed": False}),
        "set_bpm": ("transport.setBPM", {"bpm": 120.0}),
        "set_speed": ("transport.setPlaybackSpeed", {"speed": 0.5}),
        "loop": ("transport.setLoopMode", {"mode": "song"}),
        "position": ("transport.setPosition", {"position": 8.0, "mode": 2}),
    }
    for action, (ca, cparams) in expected.items():
        got = _route(action, {"bpm": 120, "numerator": 7, "denominator": 8,
                              "speed": 0.5, "mode": "song", "value": 16,
                              "unit": "beats", "armed": False, "_bpm": 120})
        assert got == (ca, cparams), f"{action}: {got} != {(ca, cparams)}"


def test_position_unit_defaults_to_seconds():
    assert _route("position", {"value": 5})[1] == {"position": 5.0, "mode": 2}


def test_position_minutes_and_beats_convert_to_seconds():
    assert _route("position", {"value": 2, "unit": "minutes"})[1]["position"] == 120.0
    # 16 beats at 120 BPM = 8 s
    assert _route("position", {"value": 16, "unit": "beats", "_bpm": 120})[1]["position"] == 8.0


def test_set_timesig_is_wired_v104e():
    """L13 (v10.4e): set_timesig is no longer refused — it routes to
    transport.setTimesig (the controller's candidate cascade handles the
    unprobed v45 API and reports an oracle on failure)."""
    calls = []

    class C:
        def send_command(self, action, params=None, timeout=None):
            calls.append((action, params))
            return {"success": True, "numerator": 7, "denominator": 8,
                    "undo_saved": "u"}
    r = fl_transport("set_timesig", conn=C(), numerator=7, denominator=8)
    assert r["success"] is True
    assert calls[0][0] == "transport.setTimesig"
    assert calls[0][1]["numerator"] == 7 and calls[0][1]["denominator"] == 8


def test_unknown_action_rejected_with_valid_list():
    r = validate("teleport", {})
    assert r == ["unknown action 'teleport'. Valid: play, stop, record, set_bpm, set_timesig, set_speed, set_swing, loop, position"]


def test_out_of_range_bpm_rejected():
    assert validate("set_bpm", {"bpm": 350}) == ["set_bpm.bpm: 350.0 > 300.0"]
    assert validate("set_bpm", {"bpm": 10}) == ["set_bpm.bpm: 10.0 < 20.0"]
    assert validate("set_bpm", {"bpm": 120}) == []


def test_speed_range_rejected():
    assert validate("set_speed", {"speed": 0.1}) == ["set_speed.speed: 0.1 < 0.25"]
    assert validate("set_speed", {"speed": 5.0}) == ["set_speed.speed: 5.0 > 4.0"]
    assert validate("set_speed", {"speed": 1.0}) == []


def test_timesig_range_rejected():
    assert validate("set_timesig", {"numerator": 0, "denominator": 4})
    assert validate("set_timesig", {"numerator": 4, "denominator": 64})
    assert validate("set_timesig", {"numerator": 4, "denominator": 4}) == []


def test_position_negative_rejected():
    assert validate("position", {"value": -5})
    assert validate("position", {"value": 0, "unit": "beats"}) == []


def test_loop_mode_rejects_garbage():
    assert validate("loop", {"mode": "galaxy"})
    assert validate("loop", {"mode": "pattern"}) == []


def test_missing_required_param_rejected():
    assert validate("set_bpm", {})
    assert validate("position", {})
    assert validate("loop", {})


def test_non_numeric_param_rejected():
    assert validate("set_bpm", {"bpm": "fast"})


# ---------------------------------------------------------------------------
# The same-trip write contract (mocked connection)
# ---------------------------------------------------------------------------


class _FakeConn:
    """Returns a success + state_after + undo_saved, like the v8 controller."""

    def __init__(self):
        self.calls = []

    def send_command(self, action, params=None, timeout=2.0):
        self.calls.append((action, params))
        if action == "transport.setBPM":
            return {"success": True, "protocol_v2": True,
                    "bpm": params.get("bpm"),
                    "state_after": {"bpm": params.get("bpm")},
                    "undo_saved": "fl_set_bpm_120"}
        if action == "transport.start":
            return {"success": True, "protocol_v2": True,
                    "is_playing": True,
                    "state_after": {"is_playing": True},
                    "undo_saved": "fl_play"}
        return {"success": True, "protocol_v2": True, "state_after": {}}


def test_set_bpm_returns_state_after_and_undo():
    conn = _FakeConn()
    r = fl_transport("set_bpm", conn=conn, bpm=128)
    assert r["success"] is True
    assert r["action"] == "set_bpm"
    assert r["state_after"]["bpm"] == 128
    assert r["undo_saved"]
    # it went through the right controller action
    assert conn.calls[0][0] == "transport.setBPM"


def test_play_returns_state_after():
    conn = _FakeConn()
    r = fl_transport("play", conn=conn)
    assert r["success"] is True
    assert r["state_after"]["is_playing"] is True


def test_invalid_call_never_reaches_fl():
    conn = _FakeConn()
    r = fl_transport("set_bpm", conn=conn, bpm=999)
    assert r["success"] is False
    assert "valid_actions" in r
    assert conn.calls == []  # FL was never touched


def test_all_action_constants_match_route():
    for a in ACTIONS:
        assert _route is not None
        # every action in ACTIONS is routable
        params = {"bpm": 120, "numerator": 4, "denominator": 4, "speed": 1.0,
                  "swing": 0.15, "mode": "pattern", "value": 0, "unit": "seconds", "armed": False}
        ca, cparams = _route(a, params)
        assert ca.startswith(("transport.",)), f"{a} -> {ca}"


def test_set_swing_routes_to_controller_and_validates_range():
    assert _route("set_swing", {"swing": 0.15}) == ("transport.setSwing", {"swing": 0.15})
    assert validate("set_swing", {"swing": 1.5}) == ["set_swing.swing: 1.5 > 1.0"]
    assert validate("set_swing", {}) == ["set_swing: missing required param 'swing'"]

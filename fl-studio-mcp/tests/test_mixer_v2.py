"""B3: fl_mixer — validation + routing + same-trip write contract.

Verified offline:
  - set_vol/set_pan/route/sends route to the right controller action
  - src == dst is rejected pre-FL (the controller enforces it too)
  - out-of-range volume/pan/level rejected pre-FL
  - remove_fx is NOT a mixer action (it is destructive → fl_delete)
  - a write returns state_after + undo_saved
"""


from fl_studio_mcp.tools.mixer_v2 import ACTIONS, _route, fl_mixer, validate

# ---------------------------------------------------------------------------
# Validation (rejected before FL)
# ---------------------------------------------------------------------------


def test_all_five_actions_route():
    # each action gets its own correct params (shared dict would bleed values)
    base = {"track": 0, "volume": 0.0, "pan": 0.0, "to": 0, "level": 0.0,
            "plugin": "Fruity Reverb 2"}
    cases = {
        "set_vol": ("mixer.setTrackVolume", {"track": 3, "volume": 0.7},
                    {**base, "track": 3, "volume": 0.7}),
        "set_pan": ("mixer.setTrackPan", {"track": 1, "pan": -1.0},
                    {**base, "track": 1, "pan": -1.0}),
        "route": ("mixer.setSendLevel", {"track": 2, "to": 0, "level": 1.0},
                  {**base, "track": 2, "to": 0}),
        "sends": ("mixer.setSendLevel", {"track": 5, "to": 1, "level": 0.4},
                  {**base, "track": 5, "to": 1, "level": 0.4}),
        "add_fx": ("mixer.addFx", {"track": 4, "plugin": "Fruity Reverb 2"},
                   {**base, "track": 4}),
    }
    for action, (want_ca, want_cp, give) in cases.items():
        got = _route(action, give)
        assert got == (want_ca, want_cp), f"{action}: {got} != {(want_ca, want_cp)}"


def test_remove_fx_is_not_a_mixer_action():
    """remove_fx is destructive → it lives in fl_delete, not here (plan §4 rule 3)."""
    assert "remove_fx" not in ACTIONS
    r = validate("remove_fx", {"track": 2, "slot": 0})
    assert r[0].startswith("unknown action")


def test_volume_out_of_range_rejected():
    assert validate("set_vol", {"track": 3, "volume": 1.5})
    assert validate("set_vol", {"track": 3, "volume": -0.1})
    assert validate("set_vol", {"track": 3, "volume": 0.7}) == []


def test_pan_out_of_range_rejected():
    assert validate("set_pan", {"track": 1, "pan": 2.0})
    assert validate("set_pan", {"track": 1, "pan": -1.5})
    assert validate("set_pan", {"track": 1, "pan": -1.0}) == []


def test_src_equals_dst_rejected():
    assert validate("sends", {"track": 2, "to": 2, "level": 0.5})
    assert validate("route", {"track": 3, "to": 3})


def test_sends_level_range_rejected():
    assert validate("sends", {"track": 1, "to": 2, "level": 2.0})
    assert validate("sends", {"track": 1, "to": 2, "level": 0.5}) == []


def test_add_fx_requires_nonempty_plugin():
    assert validate("add_fx", {"track": 1, "plugin": ""})
    assert validate("add_fx", {"track": 1, "plugin": "FLEX"}) == []


def test_missing_param_rejected():
    assert validate("set_vol", {})
    assert validate("sends", {"track": 1})  # missing to + level


# ---------------------------------------------------------------------------
# Same-trip write contract (mocked connection)
# ---------------------------------------------------------------------------


class _FakeConn:
    def __init__(self):
        self.calls = []

    def send_command(self, action, params=None, timeout=2.0):
        self.calls.append((action, params))
        if action == "mixer.setTrackVolume":
            return {"success": True, "protocol_v2": True,
                    "state_after": {"track": params["track"],
                                   "volume": params["volume"]},
                    "undo_saved": "fl_set_vol"}
        if action == "mixer.setTrackPan":
            return {"success": True, "protocol_v2": True,
                    "state_after": {"track": params["track"], "pan": params["pan"]},
                    "undo_saved": "fl_set_pan"}
        if action == "mixer.setSendLevel":
            return {"success": True, "protocol_v2": True,
                    "state_after": {"track": params["track"], "to": params["to"],
                                   "level": params["level"]},
                    "undo_saved": "fl_send"}
        if action == "mixer.addFx":
            return {"success": True, "protocol_v2": True,
                    "result": params["plugin"],
                    "state_after": {"track": params["track"]},
                    "undo_saved": "fl_add_fx"}
        return {"success": True, "protocol_v2": True, "state_after": {}}


def test_set_vol_returns_state_after_and_undo():
    conn = _FakeConn()
    r = fl_mixer("set_vol", conn=conn, track=3, volume=0.7)
    assert r["success"] is True
    assert r["state_after"] == {"track": 3, "volume": 0.7}
    assert r["undo_saved"]
    assert conn.calls[0][0] == "mixer.setTrackVolume"


def test_invalid_call_never_reaches_fl():
    conn = _FakeConn()
    r = fl_mixer("set_vol", conn=conn, track=3, volume=5.0)
    assert r["success"] is False
    assert "valid_actions" in r
    assert conn.calls == []


def test_route_uses_full_level_when_no_send_exists():
    conn = _FakeConn()
    fl_mixer("route", conn=conn, track=2, to=0)
    sent = [p for a, p in conn.calls if a == "mixer.setSendLevel"][0]
    assert sent["level"] == 1.0


class _SendsConn:
    def __init__(self, sends):
        self.sends, self.calls = sends, []

    def send_command(self, action, params=None, timeout=None):
        self.calls.append((action, dict(params or {})))
        if action == "mixer.getSends":
            return {"success": True, "track": 7, "sends": self.sends}
        return {"success": True, "state_after": {}, "undo_saved": "u"}


def test_route_keeps_an_existing_send_level():
    """L1 (live 2026-10-01): route reset the 808's master send 0.8 -> 1.0."""
    conn = _SendsConn([{"to": 0, "level": 0.8}])
    fl_mixer("route", conn=conn, track=7, to=0)
    sent = [p for a, p in conn.calls if a == "mixer.setSendLevel"][0]
    assert sent["level"] == 0.8


def test_route_new_send_defaults_to_full_level():
    conn = _SendsConn([])
    fl_mixer("route", conn=conn, track=7, to=3)
    sent = [p for a, p in conn.calls if a == "mixer.setSendLevel"][0]
    assert sent["level"] == 1.0


def test_add_fx_uses_the_native_picker_and_reports_the_slot(monkeypatch):
    """L16: add_fx = Add > Effect > More plugins… (utils/add_effect), verified
    by the slot read-back; it never sends the old 'mixer.addFx' (L2: that hit
    'Unknown action' and saved a spurious undo point)."""
    import sys

    from fl_studio_mcp.utils import add_effect as ae
    monkeypatch.setattr(sys, "platform", "darwin")
    seen = {}

    def fake(track, plugin, conn=None, log=None):
        seen.update(track=track, plugin=plugin)
        return {"ok": True, "track": track, "slot": 0, "plugin": "Fruity Limiter",
                "slots": ["Fruity Limiter"] + [""] * 9, "log": []}

    monkeypatch.setattr(ae, "add_effect", fake)
    conn = _SendsConn([])
    r = fl_mixer("add_fx", conn=conn, track=7, plugin="Fruity Limiter")
    assert r["success"] is True and r["slot"] == 0 and r["plugin"] == "Fruity Limiter"
    assert seen == {"track": 7, "plugin": "Fruity Limiter"}
    assert all(a != "mixer.addFx" for a, _ in conn.calls)


class _FxConn:
    """probe.exec fake: slots 0/1 loaded; records the REC writes."""
    def __init__(self):
        self.on = {0: 0, 1: 0}
        self.codes = []

    def send_command(self, action, params, timeout=None):
        code = params["code"]
        self.codes.append(code)
        if "getPluginName" in code:
            return {"success": True, "stdout": '[[0, "Fruity Compressor"], [1, "Fruity Reeverb 2"]]'}
        if "processRECEvent" in code:
            v = 1 if ", 1, midi" in code else 0
            for s in self.on:
                self.on[s] = v
            return {"success": True, "stdout": "ok"}
        if "getPluginMuteState" in code:
            return {"success": True, "stdout": str([self.on[0], self.on[1]])}
        raise AssertionError(code)


def test_fx_on_uses_rec_plug_mute_and_reads_back():
    from fl_studio_mcp.tools import mixer_v2 as m
    c = _FxConn()
    r = m.fl_mixer("fx_on", conn=c, track=7, on=True)
    assert r["success"] is True
    assert [s["on"] for s in r["slots"]] == [True, True]
    assert any("REC_Plug_Mute" in x for x in c.codes)
    assert not any("setPluginMuteState" in x for x in c.codes)  # one-way in v45


def test_fx_on_validation():
    from fl_studio_mcp.tools import mixer_v2 as m
    assert m.fl_mixer("fx_on", conn=object(), track=7)["success"] is False  # no on
    assert m.fl_mixer("fx_on", conn=object(), track=7, on=True, slot=12)["success"] is False

"""EQ: controller handlers (fake mixer module) + fl_mixer get_eq/set_eq/eq_preset."""

from __future__ import annotations

import sys

import pytest

# -- controller handlers ------------------------------------------------------
from test_controller_proto2 import controller  # noqa: F401  (fixture)

from fl_studio_mcp.tools.mixer_v2 import fl_mixer


def _eq_mixer(sig="v45"):
    """A fake mixer EQ: 3 bands, norm gain->dB = (g-0.5)*36, freq Hz = 20*1000**f."""
    st = {"gain": [0.5, 0.5, 0.5], "freq": [0.2, 0.5, 0.8], "bw": [0.5] * 3, "log": []}
    m = sys.modules["mixer"]

    def getEqGain(t, b, mode=0):
        return (st["gain"][b] - 0.5) * 36 if mode == 1 else st["gain"][b]

    def getEqFrequency(t, b, mode=0):
        return 20 * 1000 ** st["freq"][b] if mode == 1 else st["freq"][b]

    def setter(key):
        def f(t, b, v, *rest):
            st["log"].append((key, t, b, v, rest))
            st[key][b] = v
        return f

    m.getEqBandCount = lambda t=None: 3
    m.getEqGain, m.getEqFrequency = getEqGain, getEqFrequency
    m.getEqBandwidth = lambda t, b: st["bw"][b]
    m.setEqGain, m.setEqFrequency, m.setEqBandwidth = setter("gain"), setter("freq"), setter("bw")
    return st


def test_controller_get_eq_returns_normalized_and_real_units(controller):
    _eq_mixer()
    r = controller.handle_mixer_get_eq({"track": 2})
    assert r["success"] and r["band_count"] == 3 and "errors" not in r
    b0 = r["bands"][0]
    assert b0["gain"] == 0.5 and b0["gain_db"] == 0.0 and b0["bw"] == 0.5
    assert b0["freq"] == 0.2 and round(b0["freq_hz"], 1) == round(20 * 1000 ** 0.2, 1)


def test_controller_get_eq_reports_signature_errors_not_crash(controller):
    _eq_mixer()
    sys.modules["mixer"].getEqBandwidth = lambda t: (_ for _ in ()).throw(TypeError("takes 1 arg"))
    r = controller.handle_mixer_get_eq({"track": 0})
    assert r["success"] and r["bands"][0]["bw"] is None
    assert any("TypeError" in e and "getEqBandwidth" in e for e in r["errors"])


def test_controller_get_eq_fails_when_count_unavailable(controller):
    _eq_mixer()
    del sys.modules["mixer"].getEqBandCount
    r = controller.handle_mixer_get_eq({"track": 0})
    assert "error" in r and "getEqBandCount" in r["error"]


def test_controller_set_eq_only_given_fields_and_clamps(controller):
    st = _eq_mixer()
    r = controller.handle_mixer_set_eq({"track": 1, "band": 2, "gain": 1.7, "bw": 0.25})
    assert r["applied"] == {"gain": 1.0, "bw": 0.25}
    assert [(k, t, b) for k, t, b, _, _ in st["log"]] == [("gain", 1, 2), ("bw", 1, 2)]
    assert st["freq"][2] == 0.8


def test_controller_set_eq_validates_band_and_fields(controller):
    _eq_mixer()
    assert "out of range" in controller.handle_mixer_set_eq({"track": 0, "band": 3, "gain": 0.5})["error"]
    assert "at least one" in controller.handle_mixer_set_eq({"track": 0, "band": 0})["error"]


def test_controller_set_eq_falls_back_to_pickup_arg_on_typeerror(controller):
    st = _eq_mixer()
    m = sys.modules["mixer"]
    def strict(t, b, v, pim):
        st["log"].append(("gain", t, b, v, (pim,)))
        st["gain"][b] = v
    m.setEqGain = strict
    r = controller.handle_mixer_set_eq({"track": 0, "band": 0, "gain": 0.3})
    assert r["applied"] == {"gain": 0.3} and st["log"][0][4] == (0,)
    assert any("TypeError" in e for e in r["errors"])


def test_controller_eq_actions_are_tiered(controller):
    assert "mixer.getEq" in controller._READ_ONLY_ACTIONS
    assert "mixer.setEq" in controller._WRITE_ONLY_ACTIONS
    assert controller.SCRIPT_VERSION >= "v10.4h"  # EQ shipped in v10.4h


def test_controller_dispatch_reaches_eq_handlers(controller):
    _eq_mixer()
    r = controller.dispatch_command("mixer.getEq", {"track": 0})
    assert r["band_count"] == 3


# -- MCP actions --------------------------------------------------------------


class EqConn:
    """Simulates the controller's EQ; a set lands after the trip (applied on
    the next command), like FL."""

    def __init__(self, deployed=True):
        self.deployed = deployed
        self.gain = [0.5, 0.5, 0.5]
        self.freq = [0.2, 0.5, 0.8]
        self.pending = []
        self.calls = []

    def _apply(self):
        for key, b, v in self.pending:
            getattr(self, key)[b] = v
        self.pending = []

    def send_command(self, action, params=None, timeout=2.0):
        self.calls.append((action, dict(params or {})))
        if not self.deployed:
            return {"success": False, "error": f"Unknown action: {action}"}
        self._apply()
        if action == "mixer.getEq":
            return {"success": True, "track": params["track"], "band_count": 3,
                    "bands": [{"band": b, "gain": self.gain[b],
                               "gain_db": (self.gain[b] - 0.5) * 36, "freq": self.freq[b],
                               "freq_hz": 20 * 1000 ** self.freq[b], "bw": 0.5}
                              for b in range(3)]}
        if action == "mixer.setEq":
            for key in ("gain", "freq"):
                if key in params:
                    self.pending.append((key, params["band"], params[key]))
            return {"success": True, "undo_saved": "u"}
        raise AssertionError(action)


def test_get_eq_action():
    r = fl_mixer("get_eq", conn=EqConn(), track=4)
    assert r["success"] and r["band_count"] == 3 and r["bands"][1]["gain_db"] == 0.0


def test_set_eq_reads_back_in_a_separate_trip():
    c = EqConn()
    r = fl_mixer("set_eq", conn=c, track=1, band=0, gain=0.25)
    assert r["success"] and r["before"]["gain"] == 0.5 and r["after"]["gain"] == 0.25
    assert r["after"]["gain_db"] == pytest.approx(-9.0)
    assert [a for a, _ in c.calls] == ["mixer.getEq", "mixer.setEq", "mixer.getEq"]


def test_set_eq_validation_before_fl():
    c = EqConn()
    assert not fl_mixer("set_eq", conn=c, track=1, band=0)["success"]
    assert not fl_mixer("set_eq", conn=c, track=1, band=0, gain=2.0)["success"]
    assert c.calls == []


@pytest.mark.parametrize("call", [
    lambda c: fl_mixer("get_eq", conn=c, track=1),
    lambda c: fl_mixer("set_eq", conn=c, track=1, band=0, gain=0.4),
    lambda c: fl_mixer("eq_preset", conn=c, track=1, preset="air"),
])
def test_unknown_action_says_controller_not_deployed(call):
    r = call(EqConn(deployed=False))
    assert r["success"] is False
    assert "controller v10.4h not deployed: restart FL after syncing the controller" in r["error"]


def test_eq_preset_reset_finds_neutral_through_the_getter():
    c = EqConn()
    c.gain = [0.9, 0.1, 0.7]
    r = fl_mixer("eq_preset", conn=c, track=0, preset="reset")
    assert r["success"] and r["exact"]
    assert all(abs(b["gain_db"]) <= 0.1 for b in r["after"])
    assert "not auditioned" in r["convention"]


def test_eq_preset_air_moves_only_the_top_band_in_real_units():
    c = EqConn()
    r = fl_mixer("eq_preset", conn=c, track=0, preset="air")
    assert r["success"]
    top = r["after"][2]
    assert top["gain_db"] == pytest.approx(3.0, abs=0.1)
    assert top["freq_hz"] == pytest.approx(10000, rel=0.02)
    assert r["after"][0]["gain_db"] == 0.0 and r["after"][1]["gain_db"] == 0.0


def test_eq_preset_cut_mud_targets_mid_and_high_pass_ish_targets_low():
    c = EqConn()
    assert fl_mixer("eq_preset", conn=c, track=0, preset="cut_mud")["success"]
    assert c.gain[1] < 0.5 and c.gain[0] == 0.5 and c.gain[2] == 0.5
    c = EqConn()
    r = fl_mixer("eq_preset", conn=c, track=0, preset="high_pass_ish")
    assert r["success"] and c.gain[0] < 0.5 and c.gain[1] == 0.5


def test_eq_preset_unknown_name_refused():
    r = fl_mixer("eq_preset", conn=EqConn(), track=0, preset="boom")
    assert r["success"] is False and "cut_mud" in r["error"]

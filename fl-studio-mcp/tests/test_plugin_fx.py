"""fl_plugin: set_param by NAME, echo/reverb/chorus, get_fx (mocked conn)."""

from __future__ import annotations

import pytest

from fl_studio_mcp.tools.plugin_v2 import fl_plugin, resolve_param

# Two FLEX presets: same names, different knob numbers; a "Not Used" knob and
# an empty name; one duplicated name.
PRESET_A = ["Cutoff", "Not Used", "", "Delay", "Delay mix", "Delay feedback",
            "Delay time", "Reverb", "Reverb mix", "Reverb decay", "Reverb size",
            "Chorus"]
PRESET_B = ["Chorus", "Reverb size", "Reverb decay", "Reverb mix", "Reverb",
            "Delay time", "Not Used", "Delay feedback", "Delay mix", "", "Delay",
            "Dup", "Dup"]


class FakeConn:
    """Params live in a dict; sets apply AFTER the trip (stale-read model):
    a getParams in the same command as a set would see the old value, so a
    set is queued and applied on the NEXT command."""

    def __init__(self, names):
        self.params = [{"index": i, "name": n, "value": 0.0, "value_string": "0%"}
                       for i, n in enumerate(names)]
        self.pending = []
        self.calls = []

    def send_command(self, action, params=None, timeout=2.0):
        self.calls.append((action, dict(params or {})))
        for i, v in self.pending:
            self.params[i]["value"] = v
            self.params[i]["value_string"] = f"{round(v * 100)}%"
        self.pending = []
        if action == "plugins.getParams":
            return {"success": True, "params": [dict(p) for p in self.params]}
        if action == "plugins.setParamValue":
            self.pending.append((params["param_index"], params["value"]))
            return {"success": True, "undo_saved": "x", "state_after": {"v": 1}}
        raise AssertionError(action)

    def sets(self):
        return [(c[1]["param_index"], c[1]["value"]) for c in self.calls
                if c[0] == "plugins.setParamValue"]


def _plist(names):
    return FakeConn(names).params


def test_resolve_is_case_and_space_insensitive():
    p = resolve_param(_plist(PRESET_A), "  delay   MIX ")
    assert p["index"] == 4


def test_same_name_different_index_per_preset():
    assert resolve_param(_plist(PRESET_A), "Delay mix")["index"] == 4
    assert resolve_param(_plist(PRESET_B), "Delay mix")["index"] == 8


@pytest.mark.parametrize("bad", ["Not Used", "not  used", "", "   "])
def test_not_used_and_empty_refuse(bad):
    with pytest.raises(ValueError) as e:
        resolve_param(_plist(PRESET_A), bad)
    assert "Candidates" in str(e.value)


def test_zero_matches_lists_candidates():
    with pytest.raises(ValueError) as e:
        resolve_param(_plist(PRESET_A), "Delay level")
    assert "Delay mix" in str(e.value)


def test_ambiguous_refuses():
    with pytest.raises(ValueError) as e:
        resolve_param(_plist(PRESET_B), "dup")
    assert "ambiguous" in str(e.value)


def test_set_param_by_name_resolves_and_reads_back_separately():
    c = FakeConn(PRESET_B)
    r = fl_plugin("set_param", conn=c, index=3, param="Delay mix", value=0.4)
    assert r["success"] and r["resolved_index"] == 8
    assert c.sets() == [(8, 0.4)]
    assert r["value_string"] == "40%" and r["before"] == "0%"
    # the read-back is a command AFTER the set
    acts = [a for a, _ in c.calls]
    assert acts[-1] == "plugins.getParams" and acts.index("plugins.setParamValue") < len(acts) - 1


def test_set_param_by_name_refusal_writes_nothing():
    c = FakeConn(PRESET_A)
    r = fl_plugin("set_param", conn=c, index=3, param="Not Used", value=0.4)
    assert r["success"] is False and "Candidates" in r["error"]
    assert c.sets() == []


def test_set_param_int_still_works():
    c = FakeConn(PRESET_A)
    r = fl_plugin("set_param", conn=c, index=3, param=4, value=0.5)
    assert r["success"] and c.sets() == [(4, 0.5)]


def test_echo_sets_only_given_fields_with_before_after():
    c = FakeConn(PRESET_A)
    r = fl_plugin("echo", conn=c, index=2, on=True, mix=0.3)
    assert r["success"]
    assert sorted(c.sets()) == [(3, 1.0), (4, 0.3)]     # feedback/time untouched
    assert r["fields"]["mix"]["before"] == "0%" and r["fields"]["mix"]["after"] == "30%"
    assert r["fields"]["on"]["after"] == "100%"
    assert set(r["fields"]) == {"on", "mix"}


def test_echo_off_sends_zero_and_uses_other_preset_indexes():
    c = FakeConn(PRESET_B)
    r = fl_plugin("echo", conn=c, index=2, on=False, time=0.7, feedback=0.2)
    assert r["success"]
    assert sorted(c.sets()) == [(5, 0.7), (7, 0.2), (10, 0.0)]


def test_reverb_and_chorus():
    c = FakeConn(PRESET_A)
    assert fl_plugin("reverb", conn=c, index=0, decay=0.6, size=0.5)["success"]
    assert sorted(c.sets()) == [(9, 0.6), (10, 0.5)]
    c2 = FakeConn(PRESET_B)
    assert fl_plugin("chorus", conn=c2, index=0, amount=0.25)["success"]
    assert c2.sets() == [(0, 0.25)]


def test_fx_validation_rejects_before_fl():
    c = FakeConn(PRESET_A)
    assert not fl_plugin("echo", conn=c, index=0)["success"]            # no field
    assert not fl_plugin("echo", conn=c, index=0, mix=1.5)["success"]   # range
    assert not fl_plugin("echo", conn=c, index=0, decay=0.5)["success"]  # wrong fx
    assert not fl_plugin("chorus", conn=c, index=0, on=True)["success"]
    assert c.calls == []


def test_echo_refuses_all_or_nothing_when_a_knob_is_missing():
    c = FakeConn(["Delay", "Delay mix"])        # no feedback knob, no keyword hit
    r = fl_plugin("echo", conn=c, index=0, mix=0.5, feedback=0.3)
    assert r["success"] is False and "echo.feedback" in r["error"]
    assert c.sets() == []                       # mix was NOT written either


def test_mixer_slot_effect_keyword_match_and_ambiguity():
    fd3 = ["Wet", "Feedback", "Time", "Not Used"]
    c = FakeConn(fd3)
    r = fl_plugin("echo", conn=c, index=1, slot_index=2, mix=0.5, feedback=0.4, time=0.1)
    assert r["success"]
    assert sorted(c.sets()) == [(0, 0.5), (1, 0.4), (2, 0.1)]
    assert all(call[1]["slot_index"] == 2 for call in c.calls)
    amb = FakeConn(["Dry/Wet mix", "Wet level", "Feedback", "Time"])
    r = fl_plugin("echo", conn=amb, index=1, slot_index=0, mix=0.5)
    assert r["success"] is False and "ambiguous" in r["error"]
    assert amb.sets() == []


def test_get_fx_only_existing_knobs():
    c = FakeConn(["Cutoff", "Reverb", "Reverb mix", "Chorus"])
    c.params[2]["value_string"] = "35%"
    r = fl_plugin("get_fx", conn=c, index=0)
    assert r["success"]
    assert r["result"] == {"reverb": {"on": "0%", "mix": "35%"}, "chorus": {"amount": "0%"}}

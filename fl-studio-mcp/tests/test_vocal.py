"""fl_vocal + the server-side mixer/plugin actions it needs (2026-10-05).

A fake FL executes the exact probe.exec code the tools send, against fake
`mixer` / `plugins` / `midi` modules — so routing, read-back and the dial
search are exercised end to end, offline. Live behaviour is still UNVERIFIED.
"""
import contextlib
import io
import json
import sys
import types

import pytest

from fl_studio_mcp.tools import plugin_dial as pd
from fl_studio_mcp.tools import vocal_v2 as vv
from fl_studio_mcp.tools.mixer_v2 import fl_mixer
from fl_studio_mcp.tools.plugin_v2 import fl_plugin


class FakeFL:
    """Mixer routes/names + one compressor-like plugin on track 3 slot 0."""

    def __init__(self, stale_strings=False):
        self.routes = {(t, 0): 0.8 for t in range(1, 8)}
        self.names = {t: f"Insert {t}" for t in range(8)}
        self.color = {t: 0 for t in range(8)}
        self.muted, self.solo, self.sep = {}, {}, {}
        # (track, slot) -> [plugin name, {param_index: [name, value]}]
        self.fx = {(3, 0): ["Fruity Limiter", {0: ["Comp ratio", 0.0], 1: ["Comp attack", 0.0],
                                                2: ["Not Used", 0.0]}],
                   (3, 1): ["Fruity Parametric EQ 2", {0: ["Band 1 freq", 0.5]}]}
        self.stale = stale_strings
        self.cmds = []

    # display maps (monotonic, non-linear — like real plugins)
    @staticmethod
    def show(name, v):
        if name == "Comp ratio":
            return f"{1 + 19 * v * v:.1f}:1"
        if name == "Comp attack":
            return f"{0.1 + 500 * v ** 3:.1f} ms"
        if name == "Band 1 freq":
            return f"{20 * (1000 ** v):.0f} Hz" if v < 0.66 else f"{20 * (1000 ** v) / 1000:.2f} kHz"
        return "-"

    def modules(self):
        fl = self
        mixer = types.SimpleNamespace(
            trackCount=lambda: 8,
            getRouteSendActive=lambda s, d: (s, d) in fl.routes,
            getRouteToLevel=lambda s, d: fl.routes.get((s, d), 0.0),
            setRouteTo=lambda s, d, v, *a: (fl.routes.__setitem__((s, d), fl.routes.get((s, d), 1.0))
                                            if v else fl.routes.pop((s, d), None)),
            afterRoutingChanged=lambda: None,
            getTrackName=lambda t: fl.names[t], setTrackName=lambda t, n: fl.names.__setitem__(t, n),
            getTrackColor=lambda t: fl.color[t], setTrackColor=lambda t, c: fl.color.__setitem__(t, c),
            isTrackMuted=lambda t: fl.muted.get(t, 0), muteTrack=lambda t, v: fl.muted.__setitem__(t, v),
            isTrackSolo=lambda t: fl.solo.get(t, 0), soloTrack=lambda t, v, *a: fl.solo.__setitem__(t, v),
            getTrackStereoSep=lambda t: fl.sep.get(t, 0.0),
            setTrackStereoSep=lambda t, v: fl.sep.__setitem__(t, v),
            getPluginMuteState=lambda t, s: 1,
        )
        self._shown = {}

        def gv(p, i, s, g=True):
            return fl.fx[(i, s)][1][p][1]

        def sv(v, p, i, s, pim=0, g=True):
            fl.fx[(i, s)][1][p][1] = float(v)

        def gs(p, i, s, g=True):
            nm, v = fl.fx[(i, s)][1][p]
            return fl.show(nm, v) if not fl.stale else fl._shown.setdefault((i, s, p), fl.show(nm, v))

        plugins = types.SimpleNamespace(
            isValid=lambda t, s, *a: (t, s) in fl.fx,
            getPluginName=lambda t, s, *a: fl.fx[(t, s)][0],
            getName=lambda t, s, *a: fl.fx[(t, s)][0],
            getParamValue=gv, setParamValue=sv, getParamValueString=gs,
            getParamName=lambda p, i, s, g=True: fl.fx[(i, s)][1][p][0],
            getParamCount=lambda i, s, *a: len(fl.fx[(i, s)][1]),
        )
        midi = types.SimpleNamespace(PIM_None=0, FPN_Preset=6)
        return {"mixer": mixer, "plugins": plugins, "midi": midi}

    def send_command(self, action, params, timeout=None):
        self.cmds.append(action)
        if action == "probe.exec":
            saved = {k: sys.modules.get(k) for k in ("mixer", "plugins", "midi")}
            sys.modules.update(self.modules())
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    exec(params["code"], {})
            finally:
                for k, v in saved.items():
                    if v is None:
                        sys.modules.pop(k, None)
                    else:
                        sys.modules[k] = v
            self._shown = {}                 # a new trip refreshes display strings
            return {"success": True, "stdout": buf.getvalue()}
        if action == "plugins.getParams":
            i, s = params["index"], params["slot_index"]
            return {"success": True, "params": [
                {"index": p, "name": nm, "value": v, "value_string": self.show(nm, v)}
                for p, (nm, v) in self.fx[(i, s)][1].items()]}
        if action == "plugins.setParamValue":
            i, s, p = params["plugin_index"], params["slot_index"], params["param_index"]
            self.fx[(i, s)][1][p][1] = params["value"]
            return {"success": True}
        if action == "mixer.setSendLevel":
            self.routes[(params["track"], params["to"])] = params["level"]
            return {"success": True, "track": params["track"], "to": params["to"],
                    "level": params["level"]}
        raise AssertionError(f"unexpected action {action}")


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    import fl_studio_mcp.tools.mixer_tracks as mt
    monkeypatch.setattr(mt, "SETTLE", 0)
    monkeypatch.setattr(pd.time, "sleep", lambda s: None)


# ------------------------------------------------------------- parsing

@pytest.mark.parametrize("s,want", [("4.0:1", 4.0), ("-20.0 dB", -20.0), ("1.2 kHz", 1200.0),
                                    ("12 ms", 12.0), ("−18 dB", -18.0), ("Off", None),
                                    (3, 3.0)])
def test_parse_display(s, want):
    assert pd.parse_display(s) == want


def test_parse_inf():
    assert pd.parse_display("-inf dB") == float("-inf")


# ------------------------------------------------------------- fl_mixer track actions

def test_route_only_drops_master_and_reads_back():
    fl = FakeFL()
    r = fl_mixer("route_only", conn=fl, track=5, to=2)
    assert r["success"], r
    assert [d for d, _ in r["routes_after"]] == [2]
    assert (5, 0) not in fl.routes


def test_unroute():
    fl = FakeFL()
    r = fl_mixer("unroute", conn=fl, track=4, to=0)
    assert r["success"] and (4, 0) not in fl.routes


def test_name_color_mute_solo_sep_read_back():
    fl = FakeFL()
    assert fl_mixer("name", conn=fl, track=2, name="Vocal Bus")["after"]["name"] == "Vocal Bus"
    assert fl_mixer("color", conn=fl, track=2, color="#1f3a93")["after"]["color"] == "#1F3A93"
    assert fl_mixer("mute", conn=fl, track=2, on=True)["success"]
    assert fl_mixer("solo", conn=fl, track=2, on=True)["success"]
    assert fl_mixer("stereo_sep", conn=fl, track=2, value=-0.5)["after"]["stereo_sep"] == -0.5


def test_track_action_validation():
    fl = FakeFL()
    assert not fl_mixer("route_only", conn=fl, track=3, to=3)["success"]
    assert not fl_mixer("color", conn=fl, track=3, color="blue")["success"]
    assert not fl_mixer("stereo_sep", conn=fl, track=3, value=2)["success"]
    assert fl.cmds == []                       # rejected before FL


def test_list_fx():
    r = fl_mixer("list_fx", conn=FakeFL(), track=3)
    assert [s["plugin"] for s in r["slots"]] == ["Fruity Limiter", "Fruity Parametric EQ 2"]


# ------------------------------------------------------------- dial

@pytest.mark.parametrize("param,target,lo,hi", [("Comp ratio", "4:1", 3.9, 4.1),
                                                 ("Comp attack", "10 ms", 9.7, 10.3),
                                                 ("Comp attack", "0.02 s", 19.4, 20.6)])
def test_dial_hits_real_units(param, target, lo, hi):
    fl = FakeFL()
    r = fl_plugin("dial", conn=fl, index=3, slot_index=0, param=param, target=target)
    assert r["success"], r
    assert r["mode"] == "in_trip"
    assert lo <= pd.parse_display(r["after"]) <= hi


def test_dial_khz_display():
    r = fl_plugin("dial", conn=FakeFL(), index=3, slot_index=1, param="Band 1 freq", target="2 kHz")
    assert r["success"], r


def test_dial_out_of_range_refuses_and_restores():
    fl = FakeFL()
    r = fl_plugin("dial", conn=fl, index=3, slot_index=0, param="Comp ratio", target="50:1")
    assert not r["success"] and "outside" in r["error"]
    assert fl.fx[(3, 0)][1][0][1] == 0.0       # scan restored the start value


def test_dial_falls_back_when_strings_stale_in_trip():
    r = fl_plugin("dial", conn=FakeFL(stale_strings=True), index=3, slot_index=0,
                  param="Comp ratio", target="4:1")
    assert r["mode"] == "per_trip" and r["success"], r


def test_dial_validation():
    assert not fl_plugin("dial", conn=FakeFL(), index=3, slot_index=0, param="Comp ratio")["success"]


# ------------------------------------------------------------- fl_vocal

def test_recipes_load_and_have_chains():
    names = vv.list_recipes()
    assert {"vocal-clean-stock", "vocal-natural-light", "vocal-buses", "master-stock"} <= set(names)
    for n in names:
        r = vv.load_recipe(n)
        assert "convention" in r["status"]
        for step in r["chain"]:
            assert step["step"] and step["plugin"]
            for k in step.get("params", []):
                assert ("target" in k) != ("value" in k), (n, step["step"], k)


def test_assign_slots_nth_occurrence():
    chain = [{"step": "a", "plugin": "Fruity Parametric EQ 2"}, {"step": "b", "plugin": "Fruity Limiter"},
             {"step": "c", "plugin": "Fruity Parametric EQ 2"}]
    slots = [{"slot": 0, "plugin": "Fruity parametric EQ 2"}, {"slot": 2, "plugin": "Fruity Limiter"},
             {"slot": 4, "plugin": "Fruity Parametric EQ 2"}]
    assert vv.assign_slots(chain, slots) == [0, 2, 4]
    assert vv.assign_slots(chain, slots[:2]) == [0, 2, None]


def test_apply_sets_knobs_and_reports_misses():
    fl = FakeFL()
    recipe = {"name": "t", "chain": [
        {"step": "comp", "plugin": "Fruity Limiter",
         "params": [{"param": ["Ratio", "Comp ratio"], "target": "4:1"},
                    {"param": ["Nope"], "value": 0.3}]},
        {"step": "missing", "plugin": "Pitcher"}]}
    r = vv.apply(fl, recipe, 3)
    comp = r["steps"][0]
    assert comp["slot"] == 0 and comp["knobs"][0]["ok"]
    whats = sorted(m["what"] for m in r["misses"])
    assert whats == ["knob", "plugin"]
    knob_miss = next(m for m in r["misses"] if m["what"] == "knob")
    assert "Comp attack" in knob_miss["candidates"] and "Not Used" not in knob_miss["candidates"]
    assert not r["success"]


def test_apply_dry_run_touches_nothing():
    fl = FakeFL()
    r = vv.apply(fl, vv.load_recipe("vocal-clean-stock"), 3, dry_run=True)
    assert r["dry_run"] and len(r["plan"]) == len(vv.load_recipe("vocal-clean-stock")["chain"])
    assert fl.fx[(3, 0)][1][0][1] == 0.0
    assert "plugins.setParamValue" not in fl.cmds


def test_buses_wire_layout():
    fl = FakeFL()
    r = vv.fl_vocal("buses", conn=fl, recipe="vocal-buses", vocal=1, vocal_bus=2,
                    reverb_bus=3, delay_bus=4, fx_tracks={"Hall Reverb": 5, "Delay 1/4": 6})
    assert r["success"], r["failed"]
    assert {d for (s, d) in fl.routes if s == 1} == {2, 5, 6}   # vocal: bus only + sends
    assert {d for (s, d) in fl.routes if s == 5} == {3}         # reverb fx -> reverb bus only
    assert {d for (s, d) in fl.routes if s == 6} == {4}
    assert fl.names[3] == "Reverb Bus" and fl.names[5] == "Hall Reverb"
    assert fl.routes[(1, 5)] == 0.55


def test_buses_refuse_overlap():
    r = vv.fl_vocal("buses", conn=FakeFL(), recipe="vocal-buses", vocal=1, vocal_bus=1,
                    reverb_bus=3, delay_bus=4)
    assert not r["success"]


def test_parse_ebur128_summary():
    txt = ("[Parsed_ebur128_0 @ 0x1] t: 1 M: -20\n  Summary:\n\n  Integrated loudness:\n"
           "    I:          -8.4 LUFS\n    Threshold: -18.6 LUFS\n\n  Loudness range:\n"
           "    LRA:         5.1 LU\n\n  True peak:\n    Peak:       -0.6 dBFS\n")
    assert vv.parse_ebur128(txt) == {"I": -8.4, "LRA": 5.1, "peak": -0.6}


def test_loudness_real_file(tmp_path):
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        pytest.skip("no ffmpeg")
    f = tmp_path / "tone.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=frequency=1000:duration=3", "-af", "volume=-12dB", str(f)], check=True)
    r = vv.loudness(str(f), reference=str(f), target_lufs=-8)
    assert r["success"] and r["delta_vs_reference_lu"] == 0.0
    assert -36 < r["mix"]["integrated_lufs"] < -30   # lavfi sine is ~-18 dBFS, then -12 dB
    assert any("too quiet" in a for a in r["advice"])


# ------------------------------------------------------------- run (batch)

def test_run_many_ops_one_call():
    fl = FakeFL()
    r = vv.fl_vocal("run", conn=fl, ops=[
        {"tool": "mixer", "action": "name", "track": 2, "name": "Vocal"},
        {"tool": "mixer", "action": "route_only", "track": 2, "to": 3},
        {"tool": "plugin", "action": "dial", "index": 3, "slot_index": 0,
         "param": "Comp ratio", "target": "4:1"},
        {"tool": "vocal", "action": "status", "track": 3}])
    assert r["success"] and r["done"] == 4, r
    assert fl.names[2] == "Vocal" and {d for (s, d) in fl.routes if s == 2} == {3}
    assert r["results"][2]["after"].startswith("4.0")


def test_run_stops_on_error_and_reports():
    fl = FakeFL()
    r = vv.fl_vocal("run", conn=fl, ops=[
        {"tool": "mixer", "action": "route_only", "track": 2, "to": 2},   # invalid
        {"tool": "mixer", "action": "name", "track": 2, "name": "never"}])
    assert not r["success"] and r["done"] == 1 and r["failed"] == 1
    assert fl.names[2] == "Insert 2"
    r2 = vv.fl_vocal("run", conn=fl, stop_on_error=False, ops=[
        {"tool": "mixer", "action": "route_only", "track": 2, "to": 2},
        {"tool": "mixer", "action": "name", "track": 2, "name": "yes"}])
    assert r2["done"] == 2 and fl.names[2] == "yes"


def test_run_rejects_bad_ops():
    for ops in ([], [{"tool": "x", "action": "y"}], [{"tool": "vocal", "action": "run"}]):
        assert not vv.fl_vocal("run", conn=FakeFL(), ops=ops)["success"]


# ------------------------------------------------------------- find_preset (paced)

class PresetFL(FakeFL):
    """Slot (3, 0) with named presets; `lag` = steps FL has not applied yet."""

    def __init__(self, plugin="Maximus", names=("Default", "A", "De-esser", "Loud"), apply=True):
        super().__init__()
        self.fx[(3, 0)][0] = plugin
        self.pnames, self.cur, self.apply, self.loads = list(names), 0, apply, 0

    def modules(self):
        m = super().modules()
        fl = self

        def step(d):
            fl.loads += 1
            if fl.apply:
                fl.cur = (fl.cur + d) % len(fl.pnames)
        m["plugins"].getPresetCount = lambda i, s, *a: len(fl.pnames)
        m["plugins"].getName = lambda i, s, flag=0, p=0, *a: fl.pnames[fl.cur]
        m["plugins"].nextPreset = lambda i, s, *a: step(1)
        m["plugins"].prevPreset = lambda i, s, *a: step(-1)
        return m


def test_find_preset_finds_and_keeps():
    fl = PresetFL()
    r = pd.find_preset(fl, 3, 0, "de-ess", sleep=lambda s: None)
    assert r["success"] and r["match"] == "De-esser" and fl.cur == 2
    assert fl.loads == 2                                   # paced: one load per step, no walk-back


def test_find_preset_refuses_patcher():
    fl = PresetFL(plugin="Patcher")
    r = pd.find_preset(fl, 3, 0, "Intelligent De-Esser", sleep=lambda s: None)
    assert not r["success"] and "whole patches" in r["error"] and fl.loads == 0


def test_find_preset_stops_when_fl_does_not_apply():
    fl = PresetFL(apply=False)                             # FL busy / no preset names
    r = pd.find_preset(fl, 3, 0, "loud", sleep=lambda s: None)
    assert not r["success"] and "did not change" in r["error"]
    assert fl.loads == 1                                   # ONE step sent, then it stopped


def test_find_preset_miss_restores_start():
    fl = PresetFL()
    r = pd.find_preset(fl, 3, 0, "nope", sleep=lambda s: None)
    assert not r["success"] and r["restored_start_preset"] and fl.cur == 0


def test_preset_match_rules():
    assert not pd.preset_matches("Default", "A")
    assert pd.preset_matches("A", "a")
    assert pd.preset_matches("De-esser", "de-ess")
    assert pd.preset_matches("Intelligent De-Esser", "Intelligent De-Esser")


def test_dial_choice_picks_text_setting(monkeypatch):
    fl = FakeFL()
    fl.fx[(3, 0)][1][3] = ["Delay type", 0.0]
    orig = FakeFL.show
    # monkeypatch restores the STATICMETHOD (a manual restore of the plain function
    # turned it into a method and broke every later FakeFL test)
    monkeypatch.setattr(FakeFL, "show", staticmethod(
        lambda n, v: (["Normal", "Ping pong", "Ping pong 2"][min(2, int(v * 3))]
                      if n == "Delay type" else orig(n, v))))
    r = fl_plugin("dial", conn=fl, index=3, slot_index=0, param="Delay type", target="Ping pong")
    assert r["success"] and r["mode"] == "choice" and r["after"] == "Ping pong", r
    bad = fl_plugin("dial", conn=fl, index=3, slot_index=0, param="Delay type", target="Tape")
    assert not bad["success"] and "Normal" in bad["choices"]


# ------------------------------------------------------------- setup / free_block

def test_free_block_skips_named_used_and_routed(monkeypatch):
    import fl_studio_mcp.tools.mixer_v2 as mv
    rows = [[1, "Insert 1", False, True],            # a channel routes here
            [2, "Insert 2", False, False], [3, "Insert 3", False, False],
            [4, "Kick Bus", False, False],           # renamed -> not free
            [5, "Insert 5", False, False], [6, "Insert 6", False, False],
            [7, "Insert 7", False, False], [8, "Insert 8", False, False],
            [9, "Insert 9", False, False], [10, "Insert 10", True, False]]   # has a plugin
    monkeypatch.setattr(mv, "_exec", lambda conn, code: json.dumps(rows))
    assert vv.free_block(None, 5) == 5
    assert vv.free_block(None, 6) is None


def test_setup_dry_run_plans_five_tracks(monkeypatch):
    monkeypatch.setattr(vv, "free_block", lambda conn, n=5: 6)
    monkeypatch.setattr(vv, "unique_names", lambda conn, rec, mine: rec)
    r = vv.setup(None, dry_run=True)
    assert r["success"] and r["tracks"] == {"vocal": 6, "vocal_bus": 7, "reverb_bus": 8,
                                            "delay_bus": 9, "reverb_fx": 10}
    assert r["steps"][:4] == ["buses", "vocal chain", "reverb + duck", "delay"]


def test_setup_refuses_when_tracks_cannot_be_added(monkeypatch):
    import fl_studio_mcp.tools.mixer_tracks as mt
    monkeypatch.setattr(vv, "free_block", lambda conn, n=5: None)
    monkeypatch.setattr(mt, "add_tracks", lambda conn, n: {"success": False})
    r = vv.setup(None)
    assert not r["success"] and "vocal=N" in r["error"]


def test_setup_adds_tracks_when_none_free(monkeypatch):
    """Live 2026-10-06: the owner deleted all inserts -> setup must create them."""
    import fl_studio_mcp.tools.mixer_tracks as mt
    calls = []
    free = iter([None, 2])                       # none free, then 2..6 after adding
    monkeypatch.setattr(vv, "free_block", lambda conn, n=5: next(free))
    monkeypatch.setattr(mt, "add_tracks", lambda conn, n: calls.append(n) or {"success": True})
    monkeypatch.setattr(vv, "unique_names", lambda conn, rec, mine: rec)
    r = vv.setup(None, dry_run=True)
    assert calls == [5] and r["tracks"]["vocal"] == 2


def test_unique_names_suffixes_when_taken(monkeypatch):
    import fl_studio_mcp.tools.mixer_v2 as mv
    monkeypatch.setattr(mv, "_exec", lambda conn, code: json.dumps(
        ["Insert 1", "Vocal", "Vocal Bus", "Reverb Bus", "Delay Bus", "Hall Reverb"]))
    rec = vv.unique_names(None, vv.load_recipe("vocal-buses"), {6, 7, 8, 9, 10})
    assert rec["routing"]["names"]["vocal"] == "Vocal 2" and rec["_fx_label"] == "Hall Reverb 2"
    assert vv.load_recipe("vocal-buses")["routing"]["names"]["vocal"] == "Vocal"   # file untouched


def test_unique_names_keeps_plain_names_when_free(monkeypatch):
    import fl_studio_mcp.tools.mixer_v2 as mv
    monkeypatch.setattr(mv, "_exec", lambda conn, code: json.dumps(["Insert 1", "Insert 2"]))
    rec = vv.unique_names(None, vv.load_recipe("vocal-buses"), {6, 7, 8, 9, 10})
    assert rec["routing"]["names"]["vocal"] == "Vocal" and "_fx_label" not in rec


def test_retry_reuses_a_late_landing_insert_no_duplicate(monkeypatch):
    """First add_effect reports failure but the plugin DID land (late read-back):
    apply must pick it up, not insert a second copy."""
    import fl_studio_mcp.utils.add_effect as ae
    fl = FakeFL()
    calls = []

    def fake_add(track, plugin, conn=None, log=None):
        calls.append(plugin)
        fl.fx[(track, 2)] = ["Pitcher", {0: ["Correction Speed", 0.5]}]   # landed late
        return {"ok": False, "error": "no new plugin appeared on track 3"}
    monkeypatch.setattr(ae, "add_effect", fake_add)
    recipe = {"name": "t", "chain": [{"step": "autotune", "plugin": "Pitcher"}]}
    r = vv.apply(fl, recipe, 3, add_missing=True)
    assert calls == ["Pitcher"], calls                       # exactly ONE insert attempt
    assert r["steps"][0]["slot"] == 2 and r["steps"][0].get("late_insert")


def test_restore_snapshot_sets_all_knobs_and_proves(tmp_path, monkeypatch):
    from fl_studio_mcp.utils import plugin_preset_ui as pu
    monkeypatch.setattr(pu, "FINGERPRINTS", tmp_path / "fp.json")
    monkeypatch.setattr(pu.time, "sleep", lambda s: None)
    fl = FakeFL()
    fl.fx[(3, 0)][1][0][1] = 0.3                        # 'Comp ratio' at the wanted state
    fl.fx[(3, 0)][1][1][1] = 0.6
    pu.record_fingerprint(fl, 3, 0, "Fruity Limiter", "MCP Vocal Comp")
    fl.fx[(3, 0)][1][0][1], fl.fx[(3, 0)][1][1][1] = 0.0, 0.0      # knobs moved away
    assert pu.matches_fingerprint(fl, 3, 0, "Fruity Limiter", "MCP Vocal Comp") is False
    r = pu.restore_fingerprint(fl, 3, 0, "Fruity Limiter", "MCP Vocal Comp")
    assert r["success"] and fl.fx[(3, 0)][1][0][1] == 0.3 and fl.fx[(3, 0)][1][1][1] == 0.6


def _order_recipe():
    return {"name": "t", "chain": [{"step": "autotune", "plugin": "Pitcher"},
                                   {"step": "comp", "plugin": "Fruity Limiter"}]}


def test_apply_reports_wrong_plugin_order_when_reorder_fails(monkeypatch):
    """Pitcher (recipe step 1) sitting AFTER the Limiter, reorder fails -> order miss."""
    import fl_studio_mcp.utils.plugin_options as po
    monkeypatch.setattr(po, "reorder", lambda conn, track, wanted, **k:
                        {"success": False, "moves": 0, "error": "slot arrow not confirmed"})
    fl = FakeFL()                                    # track 3: slot0 Limiter, slot1 EQ2
    fl.fx[(3, 2)] = ["Pitcher", {0: ["Correction Speed", 0.5]}]
    r = vv.apply(fl, _order_recipe(), 3, add_missing=True)
    assert not r["success"] and any(m["what"] == "order" for m in r["misses"])


def test_apply_fixes_wrong_order_with_reorder(monkeypatch):
    """Live 2026-10-06: FL inserted Pitcher into the selected slot (last). apply must
    move it up (slot menu 'Move up') and then pass the order proof."""
    import fl_studio_mcp.utils.plugin_options as po
    fl = FakeFL()
    fl.fx[(3, 2)] = ["Pitcher", {0: ["Correction Speed", 0.5]}]
    calls = []

    def fake_reorder(conn, track, wanted, **k):       # simulate the verified moves
        calls.append(wanted)
        lim, eq, pit = fl.fx[(3, 0)], fl.fx[(3, 1)], fl.fx[(3, 2)]
        fl.fx[(3, 0)], fl.fx[(3, 1)], fl.fx[(3, 2)] = pit, lim, eq
        return {"success": True, "moves": 2}
    monkeypatch.setattr(po, "reorder", fake_reorder)
    r = vv.apply(fl, _order_recipe(), 3, add_missing=True)
    assert calls == [["Pitcher", "Fruity Limiter"]]
    assert not any(m["what"] == "order" for m in r["misses"]), r["misses"]


def test_apply_order_ok_when_in_sequence():
    fl = FakeFL()
    recipe = {"name": "t", "chain": [{"step": "comp", "plugin": "Fruity Limiter"},
                                     {"step": "eq", "plugin": "Fruity Parametric EQ 2"}]}
    r = vv.apply(fl, recipe, 3, add_missing=True)
    assert not any(m["what"] == "order" for m in r["misses"])

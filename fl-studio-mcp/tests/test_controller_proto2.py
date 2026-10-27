"""A2: protocol v2 CONTROLLER half — tested with stubbed FL API modules.

The controller (fl_controller/device_FLStudioMCP.py) runs inside FL's Python,
so it is exercised here by injecting stub modules into sys.modules (the same
imports it performs at load time) and then unit-testing run_command directly:

- the response echoes request_id + protocol_version
- write actions carry `state_after` (same-trip read-back)
- read-only actions do not carry state_after
- a pre-v2 command (no id) still gets a working response (no id echoed)
- the MCP server consumes such a response without a legacy flag
"""

import importlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

CONTROLLER = Path(__file__).resolve().parent.parent / "fl_controller" / "device_FLStudioMCP.py"

# Stub names the controller imports at module load.
_STUB_NAMES = [
    "channels", "arrangement", "patterns", "midi", "mixer", "transport",
    "general",
]

# Values the stubs report BEFORE / AFTER a write, to prove read-back.
_STATE = {
    "bpm": 120.0,
    "swing": 0.1,
    "speed": 1.0,
    "mixer_vol": 0.8,
    "mixer_pan": 0.0,
    "ch_vol": 0.9,
    "ch_pan": -0.2,
    "ch_name": "808 Kick",
    "selected": 0,
    "pat_len": 16,
    "pat_active": 1,
    "plugin_val": 0.5,
    "timesig": (4, 4),
    "file_saved": False,
}

# v10.4e recording stubs (step-param flags, volume call args, clears).
_sp = {"store": {}, "set": [], "get": []}
_vol_calls = []
_cleared = []
_grid = {}


def _reset_recs():
    _sp["store"].clear(); _sp["set"].clear(); _sp["get"].clear()
    _vol_calls.clear(); _cleared.clear(); _grid.clear()


def _make_stubs() -> dict[str, types.ModuleType]:
    m = {}

    def mod(name, **fns):
        mm = types.ModuleType(name)
        for k, v in fns.items():
            setattr(mm, k, v)
        m[name] = mm
        sys.modules[name] = mm
        return mm

    mod("arrangement")
    mod("midi", PIM_None=0)

    mod("channels",
        getSwing=lambda: _STATE["swing"],
        # v10.4e (L14): v45 getChannelVolume(index, mode, useGlobalIndex) —
        # the 2nd arg is the dB MODE flag; both calls are recorded.
        getChannelVolume=lambda i, m, g: _vol_calls.append(("get", i, m, g)) or _STATE["ch_vol"],
        getChannelPan=lambda i, g: _STATE["ch_pan"],
        getChannelName=lambda i, g: _STATE["ch_name"],
        selectedChannel=lambda **k: _STATE["selected"],
        # v10.4e (L14): v45 setChannelVolume(index, volume, pickupMode,
        # useGlobalIndex) — the 3rd arg is pickupMode (PIM_None=0), not bool.
        setChannelVolume=lambda i, v, p, g: _vol_calls.append(("set", i, v, p, g)) or _STATE.update(ch_vol=v),
        setChannelPan=lambda i, v, g: _STATE.update(ch_pan=v),
        setChannelName=lambda i, n, g: _STATE.update(ch_name=n),
        selectOneChannel=lambda i, g: _STATE.update(selected=i),
        channelCount=lambda g=True: 1,
        # v10.4f: stateful grid (the delete handler clears via setGridBit
        # and reads it back via getGridBit — both hit this dict).
        getGridBit=lambda i, pos, g=True: _grid.get((i, pos), False),
        setGridBit=lambda i, pos, v, g=True: _grid.update({(i, pos): bool(v)}),
        # v10.4e (S2.3): step parameters with flag recording (the store is
        # keyed by (channel, step, param, useGlobalIndex)).
        getCurrentStepParam=lambda i, step, param, g: _sp["get"].append((i, step, param, g)) or _sp["store"].get((i, step, param, g), -1),
        setStepParameterByIndex=lambda i, pat, step, param, v, g: _sp["set"].append((i, step, param, v, g)) or _sp["store"].update({(i, step, param, g): v}),
    )

    mod("patterns",
        getPatternLength=lambda i: _STATE["pat_len"],
        setPatternLength=lambda i, b: _STATE.update(pat_len=b),
        patternNumber=lambda: _STATE["pat_active"],
        jumpToPattern=lambda n: _STATE.update(pat_active=n),
        patternCount=lambda: 2,
        patternMax=lambda: 2,
        clearPattern=lambda i: _cleared.append(i),
    )

    mod("mixer",
        getCurrentTempo=lambda: int(round(_STATE["bpm"] * 1000)),
        setCurrentTempo=lambda v: _STATE.update(bpm=v / 1000.0),
        getTrackVolume=lambda t, d=0: _STATE["mixer_vol"],
        setTrackVolume=lambda t, v: _STATE.update(mixer_vol=v),
        getTrackPan=lambda t: _STATE["mixer_pan"],
        setTrackPan=lambda t, v: _STATE.update(mixer_pan=v),
    )

    mod("transport",
        getPlaybackSpeed=lambda: _STATE["speed"],
        setPlaybackSpeed=lambda v: _STATE.update(speed=v),
        start=lambda: None, stop=lambda: None,
    )

    mod("general",
        save=lambda: _STATE.update(file_saved=True),
        saveUndo=lambda name, flags=0: _STATE.update(undo=name),
        # v10.4f (L13): the real v45 timesig API (setters only, no getter).
        setNumerator=lambda n: _STATE.update(timesig=(n, _STATE["timesig"][1])),
        setDenominator=lambda d: _STATE.update(timesig=(_STATE["timesig"][0], d)),
    )

    plugins_state = {"val": _STATE["plugin_val"]}
    mod("plugins",
        getParamValue=lambda *a, **k: plugins_state["val"],
        setParamValue=lambda v, *a, **k: plugins_state.update(val=v) or _STATE.update(plugin_val=v),
    )
    return m


@pytest.fixture()
def controller(monkeypatch, tmp_path):
    stubs = _make_stubs()
    for name in _STUB_NAMES:
        monkeypatch.setitem(sys.modules, name, stubs[name])
    spec = importlib.util.spec_from_file_location("device_FLStudioMCP", CONTROLLER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # Point its file paths at the test sandbox.
    mod.SCRIPT_DIR = tmp_path
    mod.COMMAND_FILE = tmp_path / "mcp_command.json"
    mod.RESPONSE_FILE = tmp_path / "mcp_response.json"
    return mod


# --- echo --------------------------------------------------------------------


def test_response_echoes_request_id_and_version(controller):
    cmd = {"action": "transport.getBPM", "params": {},
           "request_id": "abc123", "protocol_version": 2}
    controller.run_command(cmd)
    resp = json.loads(controller.RESPONSE_FILE.read_text())
    assert resp["success"] is True
    assert resp["request_id"] == "abc123"
    assert resp["protocol_version"] == 2
    assert "state_after" not in resp  # read-only action


def test_pre_v2_command_still_works_without_echo(controller):
    cmd = {"action": "transport.getBPM", "params": {}}
    controller.run_command(cmd)
    resp = json.loads(controller.RESPONSE_FILE.read_text())
    assert resp["success"] is True
    assert "request_id" not in resp  # nothing to echo for a pre-v2 command


def test_error_response_still_echoes(controller):
    cmd = {"action": "unknown.thing", "params": {},
           "request_id": "xyz", "protocol_version": 2}
    controller.run_command(cmd)
    resp = json.loads(controller.RESPONSE_FILE.read_text())
    assert resp["success"] is False
    assert resp["request_id"] == "xyz"
    assert resp["protocol_version"] == 2


# --- same-trip read-back ------------------------------------------------------


def test_set_bpm_reads_back_state_after(controller):
    _STATE["bpm"] = 120.0
    cmd = {"action": "transport.setBPM", "params": {"bpm": 128},
           "request_id": "r1", "protocol_version": 2}
    controller.run_command(cmd)
    resp = json.loads(controller.RESPONSE_FILE.read_text())
    assert resp["success"] is True
    assert resp["state_after"]["bpm"] == 128.0
    assert _STATE["bpm"] == 128.0


def test_mixer_set_volume_reads_back(controller):
    _STATE["mixer_vol"] = 0.8
    cmd = {"action": "mixer.setTrackVolume", "params": {"track": 2, "volume": 0.35},
           "request_id": "r2", "protocol_version": 2}
    controller.run_command(cmd)
    resp = json.loads(controller.RESPONSE_FILE.read_text())
    assert resp["state_after"] == {"track": 2, "volume": 0.35}
    assert resp["state_after"]["volume"] == _STATE["mixer_vol"]


def test_channel_set_name_reads_back_name(controller):
    _STATE["ch_name"] = "808 Kick"
    cmd = {"action": "channels.setName", "params": {"index": 1, "name": "Dhol"},
           "request_id": "r3", "protocol_version": 2}
    controller.run_command(cmd)
    resp = json.loads(controller.RESPONSE_FILE.read_text())
    assert resp["state_after"]["name"] == "Dhol"
    assert _STATE["ch_name"] == "Dhol"


def test_channel_select_one_reads_back_actual_selection(controller):
    """The P5 scenario: the handler claimed success; state_after reports which
    channel is ACTUALLY selected (the dispatcher trusts this, not the claim)."""
    _STATE["selected"] = 0
    cmd = {"action": "channels.selectOne", "params": {"index": 2},
           "request_id": "r4", "protocol_version": 2}
    controller.run_command(cmd)
    resp = json.loads(controller.RESPONSE_FILE.read_text())
    assert resp["state_after"]["selected_index"] == _STATE["selected"]


# --- server consumes controller responses ------------------------------------


def test_server_waits_for_matching_echo(tmp_path):
    """End-to-end through the server's _wait_for_response: the fake controller
    echoes the id, the server accepts it (no _legacy_response flag)."""
    from fl_studio_mcp.utils.midi_connection import MIDIConnection

    conn = MIDIConnection()
    conn._command_file = tmp_path / "c.json"
    conn._response_file = tmp_path / "r.json"
    conn._hardware_dir = tmp_path

    import uuid

    rid = uuid.uuid4().hex
    _STATE["bpm"] = 128.0
    cmd = {"action": "transport.getBPM", "params": {},
           "request_id": rid, "protocol_version": 2}
    (tmp_path / "c.json").write_text(json.dumps(cmd))

    # Simulate the controller: read command, echo, state_after.
    loaded = json.loads((tmp_path / "c.json").read_text())
    resp = controller_echo(loaded, tmp_path)
    assert resp["request_id"] == rid

    out = conn._wait_for_response(timeout=2.0, request_id=rid)
    assert out["success"] is True
    assert "_legacy_response" not in out
    assert out["state_after"]["bpm"] == 128.0


def controller_echo(cmd, tmp_path):
    """Minimal stand-in for the controller's protocol-v2 response writer."""
    resp = {"success": True, "bpm": _STATE["bpm"],
            "state_after": {"bpm": _STATE["bpm"]}}
    resp["request_id"] = cmd["request_id"]
    resp["protocol_version"] = cmd["protocol_version"]
    (tmp_path / "r.json").write_text(json.dumps(resp))
    return resp


# --- v10.4f: grid-first pattern clear, general.* timesig, honest file
# --- refusal (live matrix 2026-10-01 pinned all three) + the v10.4e
# --- step-param/volume/batch items stay as-is below -------------------


def _run(controller, action, params, rid):
    cmd = {"action": action, "params": params, "request_id": rid,
           "protocol_version": 2}
    controller.run_command(cmd)
    return json.loads(controller.RESPONSE_FILE.read_text())


def test_v104e_set_step_param_symmetric_readback(controller):
    """S2.3: SET and the same-trip GET use the SAME useGlobalIndex flag
    (default True), and the response reports read_back + persisted —
    a silent drop can no longer masquerade as success (P5)."""
    _reset_recs()
    resp = _run(controller, "channels.setStepParameter",
                {"channel": 0, "step": 4, "param": "pVelocity", "value": 100},
                "s1")
    assert resp["success"] is True
    assert resp["read_back"] == 100
    assert resp["persisted"] is True
    # both the write and the read-back used the same (default True) flag
    assert _sp["set"] == [(0, 4, 1, 100, True)]
    assert all(g is True for (_, _, _, g) in _sp["get"])
    assert resp["state_after"]["value"] == 100


def test_v104e_set_step_param_drop_is_reported(controller):
    """If the read-back after the write returns -1 (FL dropped it — the S2.3
    ch1-3 shift/pan symptom), persisted=False is reported, not success."""
    _reset_recs()
    # the store gets the value; force the same-flag read to report -1
    orig_get = controller.channels.getCurrentStepParam
    controller.channels.getCurrentStepParam = lambda i, step, param, g: -1
    resp = _run(controller, "channels.setStepParameter",
                {"channel": 1, "step": 2, "param": "pShift", "value": 3},
                "s2")
    controller.channels.getCurrentStepParam = orig_get
    assert resp["success"] is True          # the SET call did not raise
    assert resp["read_back"] == -1
    assert resp["persisted"] is False       # ...but it did not stick


def test_v104e_get_step_param_default_flag_true(controller):
    _reset_recs()
    _sp["store"][(0, 0, 1, True)] = 77
    resp = _run(controller, "channels.getStepParameter",
                {"channel": 0, "step": 0, "param": "pVelocity"}, "s3")
    assert resp["success"] is True
    assert resp["value"] == 77
    assert _sp["get"] == [(0, 0, 1, True)]  # default flag is True


def test_v104f_delete_pattern_data_grid_first_then_clearpattern(controller):
    """R2 (v10.4f): the scoped setGridBit loop is the PRIMARY rack-clearer
    (clearPattern does NOT clear the rack grid in v45), clearPattern runs
    second as the roll-content clear, and the read-back reports remaining
    grid bits."""
    _reset_recs()
    _grid.update({(0, 0): True, (0, 4): True, (0, 9): True})
    resp = _run(controller, "delete.pattern_data", {"index": 1}, "d1")
    assert resp["cleared"] is True
    assert resp["method"] == "grid-loop+clearPattern"
    assert _cleared == [1]                      # clearPattern still ran
    assert resp["remaining_grid_bits"] == 0     # the loop cleared the rack
    assert not any(_grid.values())              # every bit actually cleared
    assert _STATE["pat_active"] == 1            # scoped switch restored


def test_v104e_batch_read_items_return_payload(controller):
    """L3: batch read items carried only {ok, ms}; now they carry the
    controller's payload (value here)."""
    _reset_recs()
    _sp["store"][(0, 0, 1, True)] = 77
    resp = _run(controller, "batch.run",
                {"items": [{"action": "channels.getStepParameter",
                            "params": {"channel": 0, "step": 0,
                                       "param": "pVelocity"}}]}, "b1")
    item = resp["results"][0]
    assert item["ok"] is True
    assert item["value"] == 77


def test_v104f_delete_pattern_data_clearpattern_failure_not_fatal(controller):
    """clearPattern can open a modal / raise on some builds — the call is
    still a success (the grid loop did its job) with the error reported."""
    _reset_recs()
    _grid.update({(0, 0): True, (0, 8): True})

    def _modal(i):
        raise Exception("EAccessViolation (modal)")
    orig = controller.patterns.clearPattern
    controller.patterns.clearPattern = _modal
    try:
        resp = _run(controller, "delete.pattern_data", {"index": 0}, "d2")
    finally:
        controller.patterns.clearPattern = orig
    assert resp["cleared"] is True
    assert resp["remaining_grid_bits"] == 0
    assert "modal" in resp["clearPattern_error"]


def test_v104f_set_timesig_general_api(controller):
    """L13 (v10.4f): v45 has no transport.setTimesig — the real API is
    general.setNumerator/setDenominator; no getter exists, so read_back is
    honestly 'set, no getter'."""
    resp = _run(controller, "transport.setTimesig",
                {"numerator": 3, "denominator": 4}, "t1")
    assert resp["success"] is True
    assert _STATE["timesig"] == (3, 4)
    assert resp["read_back"] is None
    assert "no timesig getter" in resp["read_back_note"]


def test_v104f_set_timesig_general_missing_reports_oracle(controller):
    for attr in ("setNumerator", "setDenominator"):
        delattr(sys.modules["general"], attr)
    resp = _run(controller, "transport.setTimesig",
                {"numerator": 3, "denominator": 4}, "t2")
    assert resp["success"] is False
    assert "setNumerator" in resp["error"]


def test_v104f_file_save_refused_honestly(controller):
    """L15 (v10.4f): v45 has NO importable file API (pinned by the live
    matrix) — the handler refuses with a pointer to the OS-level path
    instead of trying candidate cascades."""
    resp = _run(controller, "file.save", {}, "f1")
    assert resp["success"] is False
    assert resp["status"] == "no_api_in_v45"
    assert "fl_connect" in resp["error"]
    assert _STATE["file_saved"] is False


def test_v104e_channel_volume_mode_and_pickup_args(controller):
    """L14: the setter passes PIM_None=0 (not True) as pickupMode, and the
    read-back uses mode=False (linear 0-1, not dB)."""
    _reset_recs()
    resp = _run(controller, "channels.setVolume",
                {"index": 1, "volume": 0.5}, "v1")
    assert resp["success"] is True
    assert ("set", 1, 0.5, 0, True) in _vol_calls
    assert ("get", 1, False, True) in _vol_calls
    assert resp["state_after"]["volume"] == 0.5

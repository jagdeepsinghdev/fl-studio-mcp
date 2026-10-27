"""A3 controller side: _safe_exec — one saveUndo per trip + in-FL identity
check, both in the same MIDI trip. Uses stubbed FL modules (incl. `general`).
"""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

CONTROLLER = Path(__file__).resolve().parent.parent / "fl_controller" / "device_FLStudioMCP.py"

_STUB_NAMES = ["channels", "arrangement", "patterns", "midi", "mixer", "transport", "plugins",
               "general"]

_STATE = {
    "bpm": 130.0,
    "ch_name": "808 Kick",
    "pat_name": "Verse",
    "selected": 0,
    "undo_log": [],
    "undo_history_length": 0,
}


def _make_stubs() -> dict:
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
    mod("mixer",
        getCurrentTempo=lambda: int(round(_STATE["bpm"] * 1000)),
        setCurrentTempo=lambda v: _STATE.update(bpm=v / 1000.0),
        getTrackVolume=lambda t, d=0: 0.8,
        setTrackVolume=lambda t, v: None,
        getTrackPan=lambda t: 0.0,
        setTrackPan=lambda t, v: None,
    )
    mod("transport",
        getPlaybackSpeed=lambda: 1.0, setPlaybackSpeed=lambda v: None,
        start=lambda: None, stop=lambda: None,
    )
    ch_state = {"name": _STATE}

    def set_channel_volume(i, v, g):
        pass

    def set_channel_pan(i, v, g):
        pass

    def set_channel_name(i, n, g):
        _STATE["ch_name"] = n

    def select_one(i, g):
        _STATE["selected"] = i

    mod("channels",
        getSwing=lambda: 0.0, setSwing=lambda v: None,
        getChannelVolume=lambda i, g: 0.8,
        getChannelPan=lambda i, g: 0.0,
        getChannelName=lambda i, g: _STATE["ch_name"],
        selectedChannel=lambda **k: _STATE["selected"],
        setChannelVolume=set_channel_volume,
        setChannelPan=set_channel_pan,
        setChannelName=set_channel_name,
        selectOneChannel=select_one,
        getGridBit=lambda c, p, g: 0, setGridBit=lambda c, p, v, g: None,
    )

    def pattern_number():
        return 1

    def pattern_max():
        return 8

    def get_pattern_name(n):
        return _STATE["pat_name"]

    def set_pattern_name(n, name, flags=None):
        _STATE["pat_name"] = name

    def set_pattern_length(i, b):
        pass

    def jump_to(n):
        pass

    def get_pattern_length(i):
        return 16

    mod("patterns",
        getPatternLength=get_pattern_length, setPatternLength=set_pattern_length,
        patternNumber=pattern_number, patternMax=pattern_max,
        getPatternName=get_pattern_name, setPatternName=set_pattern_name,
        jumpToPattern=jump_to,
        clonePattern=lambda: None,
        isPatternDefault=lambda n: False,
        setPatternColor=lambda n, c: None,
    )

    def set_param_value(v, pi, pidx, slot, *rest):
        pass

    mod("plugins",
        getParamValue=lambda *a, **k: 0.5,
        getParamValueString=lambda *a, **k: "0.5",
        getParamName=lambda *a, **k: "Param",
        getParamCount=lambda *a, **k: 1,
        isValid=lambda *a, **k: 1,
        getPluginName=lambda *a, **k: "FLEX",
        setParamValue=set_param_value,
        nextPreset=lambda *a, **k: None,
        prevPreset=lambda *a, **k: None,
        getColor=lambda *a, **k: 0,
        getPresetCount=lambda *a, **k: 1,
    )
    del ch_state
    mod("general",
        saveUndo=lambda name=None, flags=0: _STATE["undo_log"].append(name)
        or _STATE.update(undo_history_length=_STATE["undo_history_length"] + 1),
        getUndoHistoryLength=lambda: _STATE["undo_history_length"],
        getUndoHistoryCount=lambda: _STATE["undo_history_length"],
        getUndoHistoryLast=lambda: (_STATE["undo_log"][-1] if _STATE["undo_log"] else None),
        restoreUndoLevel=lambda *a, **k: None,
        restoreUndo=lambda *a, **k: None,
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
    mod.SCRIPT_DIR = tmp_path
    mod.COMMAND_FILE = tmp_path / "mcp_command.json"
    mod.RESPONSE_FILE = tmp_path / "mcp_response.json"
    _STATE["undo_log"] = []
    _STATE["undo_history_length"] = 0
    return mod


def _run(controller, action, params):
    controller.run_command({"action": action, "params": params,
                            "request_id": "t1", "protocol_version": 2})
    return json.loads(controller.RESPONSE_FILE.read_text())


def test_write_saves_exactly_one_named_undo(controller):
    r = _run(controller, "mixer.setTrackVolume",
             {"track": 1, "volume": 0.5, "_undo_name": "mcp.setTrackVolume"})
    assert r["success"] is True
    assert r["undo_saved"] == "mcp.setTrackVolume"
    assert _STATE["undo_log"] == ["mcp.setTrackVolume"]  # exactly one saveUndo
    assert _STATE["undo_history_length"] == 1


def test_read_saves_no_undo(controller):
    _run(controller, "transport.getBPM", {})
    assert _STATE["undo_log"] == []


def test_identity_mismatch_aborts_before_action(controller):
    """The undo-incident scenario, controller side: caller names a channel that
    doesn't match the live name. The action must NOT execute."""
    _STATE["ch_name"] = "808 Astronomic"
    did_run = []
    # monkeypatch the delete action in the controller's dispatch table
    orig = controller.dispatch_command

    def fake_dispatch(action, params):
        if action == "delete.channel":
            did_run.append(action)
            return {"deleted": True}
        return orig(action, params)

    controller.dispatch_command = fake_dispatch

    r = _run(controller, "delete.channel",
             {"index": 0, "name": "808 Kick",
              "_identity": {"target": "channel", "name": "808 Kick", "index": 0}})
    assert r["success"] is False
    assert r["identity_ok"] is False
    assert did_run == []  # the destructive action NEVER ran


def test_identity_match_proceeds(controller):
    _STATE["ch_name"] = "808 Kick"
    did_run = []
    orig = controller.dispatch_command

    def fake_dispatch(action, params):
        if action == "delete.channel":
            did_run.append(action)
            return {"deleted": True}
        return orig(action, params)

    controller.dispatch_command = fake_dispatch

    r = _run(controller, "delete.channel",
             {"index": 0, "name": "808 Kick", "_undo_name": "mcp.delete",
              "_identity": {"target": "channel", "name": "808 Kick", "index": 0}})
    assert r["success"] is True
    assert r["identity_ok"] is True
    assert did_run == ["delete.channel"]
    assert r["undo_saved"] == "mcp.delete"


def test_identity_out_of_range_refused(controller):
    r = _run(controller, "delete.pattern",
             {"index": 99, "name": "Verse",
              "_identity": {"target": "pattern", "name": "Verse", "index": 99}})
    assert r["success"] is False
    assert r["identity_ok"] is False


def test_saveundo_failure_does_not_block_write(controller, monkeypatch):
    """If general.saveUndo itself fails (history full?), the write still runs —
    but the response says so so the dispatcher can flag it."""
    def boom(name=None, flags=0):
        raise RuntimeError("undo history full")

    monkeypatch.setitem(sys.modules, "general",
                        types.ModuleType("general"))
    sys.modules["general"].saveUndo = boom
    r = _run(controller, "mixer.setTrackVolume",
             {"track": 1, "volume": 0.5, "_undo_name": "mcp.x"})
    assert r["success"] is True
    assert r.get("undo_error") == "undo history full"
    assert "undo_saved" not in r

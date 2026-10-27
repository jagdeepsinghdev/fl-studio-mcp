"""v10.4d controller side: `ui.keySeq` — one trip, a bounded sequence of
ui KEY events. Stubs the `ui` module (like test_controller_safety.py stubs
general/patterns/...) so no FL is needed: records what was called, in what
order, and lets specific keys raise to prove the stop-on-failure rule.

Also asserts the MCP-side sequence builder (select_script._keyseq_keys)
matches the controller's bounds, and that the canonical §0 sequence
(6 ups + enter) is exactly what fl_select_script(method="keys") would send.
"""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

import fl_studio_mcp.tools.select_script as ss

CONTROLLER = Path(__file__).resolve().parent.parent / "fl_controller" / "device_FLStudioMCP.py"

# The same FL module stubs test_controller_safety.py installs (the controller
# imports them at module load). Kept minimal here — keySeq only touches `ui`.
_STUB_NAMES = ["channels", "arrangement", "patterns", "midi", "mixer",
               "transport", "plugins", "general"]


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
        getCurrentTempo=lambda: 130000, setCurrentTempo=lambda v: None,
        getTrackCount=lambda: 1, getTrackInfo=lambda t: {},
        getAllTracks=lambda: {}, getSends=lambda: {})
    mod("transport",
        getPlaybackSpeed=lambda: 1.0, setPlaybackSpeed=lambda v: None,
        start=lambda: None, stop=lambda: None, getStatus=lambda: 0,
        getBPM=lambda: 130.0, getSwing=lambda: 0.0,
        getLength=lambda: 16)
    mod("channels",
        getSwing=lambda: 0.0, setSwing=lambda v: None,
        getChannelVolume=lambda i, g: 0.8,
        getChannelPan=lambda i, g: 0.0,
        getChannelName=lambda i, g: "808 Kick",
        selectedChannel=lambda **k: 0,
        setChannelVolume=lambda *a, **k: None,
        setChannelPan=lambda *a, **k: None,
        setChannelName=lambda *a, **k: None,
        selectOneChannel=lambda *a, **k: True,
        getCount=lambda: 1,
        getInfo=lambda i: {},
        getAll=lambda: {},
        getSelected=lambda: 0,
        getGridBit=lambda c, p, g: 0,
        getStepSequence=lambda c, p, g: [0] * 16,
        setGridBit=lambda *a, **k: None,
        setStepSequence=lambda *a, **k: None,
        triggerNote=lambda *a, **k: None,
        setVolume=lambda *a, **k: None,
        setPan=lambda *a, **k: None,
        mute=lambda *a, **k: None,
        solo=lambda *a, **k: None,
        setName=lambda *a, **k: None,
        setColor=lambda *a, **k: None,
        routeToMixer=lambda *a, **k: None,
        getStepParameter=lambda *a, **k: -1,
        setStepParameter=lambda *a, **k: None)
    mod("patterns",
        getPatternLength=lambda i: 16, setPatternLength=lambda *a, **k: None,
        patternNumber=lambda: 1, patternMax=lambda: 8,
        getPatternName=lambda n: "Pattern 1",
        setPatternName=lambda *a, **k: None,
        jumpToPattern=lambda *a, **k: None,
        clonePattern=lambda *a, **k: None,
        isPatternDefault=lambda n: False,
        setPatternColor=lambda *a, **k: None,
        list=lambda: [{"name": "Pattern 1", "index": 0}])
    mod("plugins",
        getParamValue=lambda *a, **k: 0.5,
        getParamValueString=lambda *a, **k: "0.5",
        getParamName=lambda *a, **k: "Param",
        getParamCount=lambda *a, **k: 1,
        isValid=lambda *a, **k: 1,
        getPluginName=lambda *a, **k: "FLEX",
        setParamValue=lambda *a, **k: None,
        nextPreset=lambda *a, **k: None,
        prevPreset=lambda *a, **k: None,
        getColor=lambda *a, **k: 0,
        getPresetCount=lambda *a, **k: 1)
    mod("general",
        saveUndo=lambda name=None, flags=0: True,
        getUndoHistoryLength=lambda: 0,
        getUndoHistoryCount=lambda: 0,
        getUndoHistoryLast=lambda: None,
        restoreUndoLevel=lambda *a, **k: None,
        restoreUndo=lambda *a, **k: None,
        getVersion=lambda: "test")
    return m


@pytest.fixture()
def keyseq_env(monkeypatch, tmp_path):
    """Controller module with a recording `ui` stub.

    The stub records every key call in order. `up`/`down`/`enter` return an
    int (FL-style status); any key named in UI_FAIL_AT raises on call.
    """
    stubs = _make_stubs()
    calls: list[str] = []
    fail_at: set[str] = set()

    def make_key(name):
        def fn(*args, **kwargs):
            if name in fail_at:
                raise RuntimeError(f"stub-fault:{name}")
            calls.append(name)
            return 12345
        return fn

    ui_stub = types.ModuleType("ui")
    for k in ("enter", "escape", "yes", "no", "up", "down", "left", "right",
              "jog", "jog2", "previous", "next"):
        setattr(ui_stub, k, make_key(k))
    stubs["ui"] = ui_stub
    for name in (*_STUB_NAMES, "ui"):
        monkeypatch.setitem(sys.modules, name, stubs[name])

    spec = importlib.util.spec_from_file_location("device_FLStudioMCP", CONTROLLER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.SCRIPT_DIR = tmp_path
    mod.COMMAND_FILE = tmp_path / "mcp_command.json"
    mod.RESPONSE_FILE = tmp_path / "mcp_response.json"
    return {"mod": mod, "calls": calls, "fail_at": fail_at}


def _run(controller, action, params):
    controller.run_command({"action": action, "params": params,
                            "request_id": "t1", "protocol_version": 2})
    return json.loads(controller.RESPONSE_FILE.read_text())


def test_keyseq_is_in_the_action_allowlist(keyseq_env):
    assert "ui.keySeq" in keyseq_env["mod"]._READ_ONLY_ACTIONS


def test_valid_sequence_executes_in_order(keyseq_env):
    out = _run(keyseq_env["mod"], "ui.keySeq",
               {"keys": ["up", "up", "enter"]})
    assert out["success"] is True
    assert out["executed"] == ["up", "up", "enter"]
    assert keyseq_env["calls"] == ["up", "up", "enter"]


def test_bad_key_rejected_before_any_dispatch(keyseq_env):
    out = _run(keyseq_env["mod"], "ui.keySeq",
               {"keys": ["up", "warpDrive", "enter"]})
    assert out["success"] is False
    assert "warpDrive" in out["error"]
    assert keyseq_env["calls"] == []  # nothing dispatched


def test_empty_and_oversized_sequences_refused(keyseq_env):
    assert _run(keyseq_env["mod"], "ui.keySeq", {"keys": []})["success"] is False
    assert _run(keyseq_env["mod"], "ui.keySeq",
                {"keys": ["up"] * 13})["success"] is False
    assert _run(keyseq_env["mod"], "ui.keySeq",
                {"keys": ["up"] * 11 + ["enter"]})["success"] is True
    assert keyseq_env["calls"] == ["up"] * 11 + ["enter"]


def test_failure_stops_the_sequence(keyseq_env):
    keyseq_env["fail_at"].add("enter")
    out = _run(keyseq_env["mod"], "ui.keySeq",
               {"keys": ["up", "up", "enter", "escape"]})
    assert out["success"] is False
    assert out["executed"] == ["up", "up"]
    assert keyseq_env["calls"] == ["up", "up"]  # escape never sent


def test_missing_keys_param_refused(keyseq_env):
    out = _run(keyseq_env["mod"], "ui.keySeq", {})
    assert out["success"] is False


# --- MCP-side sequence builder (pure) --------------------------------------


class TestKeyseqKeys:
    def test_canonical_s0_sequence(self):
        # 6 ups + enter = 0ComposeWithLLM in the default 27-item wrench menu
        assert ss._keyseq_keys(6) == ["up"] * 6 + ["enter"]

    def test_clamps_to_controller_bounds(self):
        assert ss._keyseq_keys(0) == ["enter"]
        assert ss._keyseq_keys(99) == ["up"] * 11 + ["enter"]  # 12 total max
        assert ss._keyseq_keys(-3) == ["enter"]

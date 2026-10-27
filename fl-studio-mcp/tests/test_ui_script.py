"""v10.4i: controller `ui.steps` + MCP-side `fl_ui_script` (routine runner).

Controller half: stubs FL modules like test_ui_keyseq.py, records calls.
MCP half: a fake connection answers `ui.steps` with scripted results; no FL.
"""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

import fl_studio_mcp.tools.ui_script_v2 as us

_KS_PATH = Path(__file__).resolve().parent / "test_ui_keyseq.py"
_ks_spec = importlib.util.spec_from_file_location("_ks_helpers", _KS_PATH)
_ks = importlib.util.module_from_spec(_ks_spec)
_ks_spec.loader.exec_module(_ks)


@pytest.fixture()
def ctl(monkeypatch, tmp_path):
    stubs = _ks._make_stubs()
    calls: list[tuple] = []
    fail_at: set[str] = set()

    def rec(name):
        def fn(*args):
            if name in fail_at:
                raise TypeError(f"stub-fault:{name}")
            calls.append((name, args))
            return 7
        return fn

    ui = types.ModuleType("ui")
    for k in ("showPicker", "escape", "enter", "isInPopupMenu",
              "getFocusedFormCaption"):
        setattr(ui, k, rec(f"ui.{k}"))
    stubs["ui"] = ui
    stubs["mixer"].setTrackNumber = rec("mixer.setTrackNumber")
    for name in (*_ks._STUB_NAMES, "ui"):
        monkeypatch.setitem(sys.modules, name, stubs[name])
    spec = importlib.util.spec_from_file_location("device_FLStudioMCP",
                                                  _ks.CONTROLLER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.SCRIPT_DIR = tmp_path
    mod.COMMAND_FILE = tmp_path / "mcp_command.json"
    mod.RESPONSE_FILE = tmp_path / "mcp_response.json"
    return {"mod": mod, "calls": calls, "fail_at": fail_at}


def _run(mod, params):
    mod.run_command({"action": "ui.steps", "params": params,
                     "request_id": "t", "protocol_version": 2})
    return json.loads(mod.RESPONSE_FILE.read_text())


# --- controller ------------------------------------------------------------

def test_steps_registered_read_tier(ctl):
    assert "ui.steps" in ctl["mod"]._READ_ONLY_ACTIONS


def test_steps_run_in_order_with_args(ctl):
    out = _run(ctl["mod"], {"steps": [
        {"fn": "mixer.setTrackNumber", "args": [7]},
        {"fn": "ui.showPicker", "args": [1, 0]}]})
    assert out["success"] is True
    assert ctl["calls"] == [("mixer.setTrackNumber", (7,)),
                            ("ui.showPicker", (1, 0))]
    assert [e["fn"] for e in out["executed"]] == ["mixer.setTrackNumber",
                                                  "ui.showPicker"]


def test_unlisted_fn_refused_before_dispatch(ctl):
    out = _run(ctl["mod"], {"steps": [
        {"fn": "ui.escape"}, {"fn": "ui.selectBrowserMenuItem"},
        {"fn": "general.saveUndo", "args": ["x", 0]}]})
    assert out["success"] is False
    assert ctl["calls"] == []


def test_fault_stops_and_reports_signature(ctl):
    ctl["fail_at"].add("ui.showPicker")
    out = _run(ctl["mod"], {"steps": [
        {"fn": "ui.showPicker", "args": []}, {"fn": "ui.escape"}]})
    assert out["success"] is False
    assert "stub-fault" in out["error"] and out["failed"] == "ui.showPicker"
    assert ctl["calls"] == []  # escape never sent


def test_bounds(ctl):
    assert _run(ctl["mod"], {"steps": []})["success"] is False
    assert _run(ctl["mod"], {"steps": [{"fn": "ui.escape"}] * 17})["success"] is False


def test_mcp_allowlist_mirrors_controller(ctl):
    c = ctl["mod"]._STEP_FNS
    assert {k: set(v) for k, v in c.items()} == \
           {k: set(v) for k, v in us.STEP_FNS.items()}


# --- MCP side: validation ---------------------------------------------------

def test_key_needs_prior_expect():
    errs = us.validate([{"call": "ui.enter"}])
    assert errs and "before any expect" in errs[0]
    assert us.validate([{"expect": "ui.isInPopupMenu", "equals": True},
                        {"call": "ui.enter"}]) == []
    assert us.validate([{"call": "ui.escape"}]) == []


def test_unknown_fn_and_bad_shapes():
    assert us.validate([{"call": "screen.menuShowing"}])
    assert us.validate([{"wait": 9}])
    assert us.validate([{"expect": "ui.isInPopupMenu"}])  # no equals/contains
    assert us.validate([{"call": "ui.escape", "wait": 1}])


def test_routine_files_are_valid():
    for name in us._names():
        r = us._load(name)
        vars_ = {k: (v or {}).get("default", 1)
                 for k, v in (r.get("vars") or {}).items()}
        steps = us._subst(r["steps"], vars_)
        assert us.validate(steps) == [], name


def test_subst_keeps_types():
    assert us._subst({"args": ["{t}"], "x": "tr {t}"}, {"t": 7}) == \
        {"args": [7], "x": "tr 7"}
    assert us._subst("{a}", {"a": [1, 0]}) == [1, 0]


# --- MCP side: runner -------------------------------------------------------

class FakeConn:
    def __init__(self, answers):
        self.answers = answers  # fn -> list of repr results (popped) or fixed
        self.sent: list[list[str]] = []

    def send_command(self, action, params, timeout=None):
        assert action == "ui.steps"
        fns = [c["fn"] for c in params["steps"]]
        self.sent.append(fns)
        out = []
        for c in params["steps"]:
            a = self.answers.get(c["fn"], "None")
            out.append({"fn": c["fn"], "result":
                        a.pop(0) if isinstance(a, list) else a})
        return {"success": True, "executed": out}


def test_expect_retries_then_passes():
    conn = FakeConn({"ui.isInPopupMenu": ["False", "False", "True"]})
    r = us.execute([{"expect": "ui.isInPopupMenu", "equals": True,
                     "retries": 3, "interval": 0}, {"call": "ui.enter"}],
                   conn, sleep=lambda s: None)
    assert r["success"] is True
    assert conn.sent[-1] == ["ui.enter"]


def test_expect_miss_runs_cleanup_and_no_key():
    conn = FakeConn({"ui.isInPopupMenu": "False"})
    r = us.execute([{"expect": "ui.isInPopupMenu", "equals": True,
                     "retries": 2, "interval": 0}, {"call": "ui.enter"}],
                   conn, sleep=lambda s: None)
    assert r["success"] is False and r["failed_step"] == 0
    assert ["ui.enter"] not in conn.sent
    assert conn.sent[-1] == ["ui.escape"]  # default on_fail


def test_reads_recorded_and_contains():
    conn = FakeConn({"ui.getFocusedFormCaption": "'Mixer - Insert 7'"})
    r = us.execute([{"read": "ui.getFocusedFormCaption", "as": "cap"},
                    {"expect": "ui.getFocusedFormCaption",
                     "contains": "insert 7"}], conn, sleep=lambda s: None)
    assert r["success"] and r["reads"]["cap"] == "Mixer - Insert 7"


def test_not_deployed_message():
    class Old:
        def send_command(self, *a, **k):
            return {"success": False, "error": "Unknown action: ui.steps"}
    r = us.execute([{"call": "ui.escape"}], Old(), on_fail=[])
    assert "v10.4i" in r["error"]


def test_tool_dry_run_and_list():
    assert us.fl_ui_script("list")["success"]
    r = us.fl_ui_script("run", routine="probe-show-picker",
                        vars={"track": 7}, dry_run=True)
    assert r["success"] and r["steps"][0]["args"] == [7]
    assert us.fl_ui_script("run", routine="probe-show-picker",
                           dry_run=True)["success"] is False  # track missing

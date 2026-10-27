"""B7: fl_plugin — validation + routing + the unverified load_preset.

Verified offline:
  - list_params/set_param route to the right controller action
  - load_preset returns "not yet verified" (no importable preset-load in v45)
  - index/param int validation rejected pre-FL
  - set_param is a write (state_after + undo via the safety layer)
"""


from fl_studio_mcp.tools.plugin_v2 import _route, _validate, fl_plugin

# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_list_params_routes_to_get_params():
    ca, cp = _route("list_params", {"index": 2, "slot_index": 0})
    assert ca == "plugins.getParams"
    assert cp == {"index": 2, "slot_index": 0}


def test_set_param_routes_to_set_param_value():
    ca, cp = _route("set_param", {"index": 3, "param": 1, "value": 0.5})
    assert ca == "plugins.setParamValue"
    assert cp == {"plugin_index": 3, "param_index": 1, "value": 0.5, "slot_index": -1}


def test_set_param_keys_match_what_the_controller_reads():
    """Drift guard (2026-10-01 live bug): the tool sent index/param, the
    controller read plugin_index/param_index, so every set silently hit
    channel 0 param 0. Every key we send must be one the handler reads."""
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "fl_controller"
           / "device_FLStudioMCP.py").read_text()
    body = src.split("def handle_plugins_set_param_value", 1)[1].split("\ndef ", 1)[0]
    read_keys = set(re.findall(r'params\.get\("(\w+)"', body))
    _, cp = _route("set_param", {"index": 3, "param": 1, "value": 0.5})
    assert set(cp) <= read_keys, f"sent {set(cp) - read_keys} that the controller ignores"


def test_slot_index_defaults_to_minus_one():
    ca, cp = _route("set_param", {"index": 1, "param": 0, "value": 1.0})
    assert cp["slot_index"] == -1


# ---------------------------------------------------------------------------
# Validation (rejected before FL)
# ---------------------------------------------------------------------------


def test_index_must_be_non_negative_int():
    assert _validate("list_params", {"index": -1})
    assert _validate("list_params", {"index": 2}) == []
    assert _validate("list_params", {"index": "2"})  # not an int


def test_param_must_be_non_negative_int():
    assert _validate("set_param", {"index": 1, "param": -3, "value": 0.5})
    assert _validate("set_param", {"index": 1, "param": 1, "value": 0.5}) == []


def test_value_must_be_numeric():
    assert _validate("set_param", {"index": 1, "param": 1, "value": "loud"})
    assert _validate("set_param", {"index": 1, "param": 1, "value": 1.5}) == []


def test_missing_value_rejected():
    assert _validate("set_param", {"index": 1, "param": 1})


def test_unknown_action_rejected_with_list():
    r = _validate("explode", {})
    assert "list_params" in r[0]


# ---------------------------------------------------------------------------
# load_preset is unverified (not faked)
# ---------------------------------------------------------------------------


def test_load_preset_reports_not_verified():
    r = fl_plugin("load_preset", index=1, preset=3)
    assert r["success"] is False
    assert r.get("status") == "not_verified_yet"
    assert "preset" in r["error"].lower()


def test_load_preset_validates_params_first():
    # even unverified, a bad index is rejected at the validation layer
    r = fl_plugin("load_preset", index=-1, preset=3)
    assert r["success"] is False
    assert "index" in r["error"]


# ---------------------------------------------------------------------------
# set_param is a write (mocked connection)
# ---------------------------------------------------------------------------


class _FakeConn:
    def __init__(self):
        self.calls = []

    def send_command(self, action, params=None, timeout=2.0):
        self.calls.append((action, dict(params or {})))
        if action == "plugins.setParamValue":
            return {"success": True, "protocol_v2": True,
                    "state_after": {"value": params.get("value")},
                    "undo_saved": "fl_set_param"}
        if action == "plugins.getParams":
            return {"success": True, "protocol_v2": True,
                    "params": [{"name": "cutoff", "value": 0.5}]}
        return {"success": True, "protocol_v2": True, "state_after": {}}


def test_set_param_returns_state_after_and_undo():
    conn = _FakeConn()
    r = fl_plugin("set_param", conn=conn, index=3, param=1, value=0.5)
    assert r["success"] is True
    assert r["state_after"]["value"] == 0.5
    assert r["undo_saved"]
    ca, cp = conn.calls[0]
    assert ca == "plugins.setParamValue"
    assert cp.get("_undo_name")  # safety injected the undo


def test_list_params_returns_read_result():
    conn = _FakeConn()
    r = fl_plugin("list_params", conn=conn, index=2)
    assert r["success"] is True


def test_invalid_set_param_never_reaches_fl():
    conn = _FakeConn()
    r = fl_plugin("set_param", conn=conn, index=-1, param=1, value=0.5)
    assert r["success"] is False
    assert "valid_actions" in r
    assert conn.calls == []


def test_list_params_returns_the_controller_payload():
    """Regression (2026-10-01 live): reads returned a bare {"success": true} —
    the controller puts read payloads at the top level, not under "result"."""
    from fl_studio_mcp.tools.plugin_v2 import fl_plugin as _fp

    class C:
        def send_command(self, action, params=None, timeout=None):
            return {"success": True, "request_id": "x",
                    "params": [{"index": 0, "name": "Osc 1 shape", "value": 0.0}]}
    r = _fp("list_params", conn=C(), index=6)
    assert r["success"] is True
    assert r["result"]["params"][0]["name"] == "Osc 1 shape"
    assert "request_id" not in r["result"]

"""Tests for fl_probe (read-only introspection route for the v9/v10.3
controller probe.* actions)."""
from fl_studio_mcp.tools.probe_v2 import ACTIONS, fl_probe


def test_actions():
    assert ACTIONS == ("ilmcp", "api", "patterns", "tempo", "playlist")


def test_unknown_action():
    out = fl_probe("warp")
    assert out["success"] is False
    assert set(out["valid_actions"]) == set(ACTIONS)


def test_probe_call_shape_no_crash():
    # without FL the dispatcher no-ops; the tool must still return a well-
    # shaped dict (live behaviour is verified against a running controller)
    out = fl_probe("ilmcp")
    assert isinstance(out, dict)
    assert out["action"] == "ilmcp"

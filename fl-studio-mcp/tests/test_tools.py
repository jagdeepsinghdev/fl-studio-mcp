"""Offline tests: new tools register and validate input without FL Studio running."""

from fl_studio_mcp.tools import (
    register_marker_tools,
    register_mixer_tools,
    register_pattern_tools,
    register_transport_tools,
)


class _FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def _registered():
    mcp = _FakeMCP()
    for register in (register_marker_tools, register_pattern_tools, register_transport_tools, register_mixer_tools):
        register(mcp)
    return mcp.tools


def test_new_tools_registered():
    names = set(_registered())
    assert {
        "fl_list_patterns", "fl_create_pattern", "fl_select_pattern", "fl_clone_pattern",
        "fl_get_swing", "fl_set_swing", "fl_add_marker", "fl_list_markers", "fl_get_sends", "fl_set_send_level",
    } <= names


def test_swing_and_send_validation_rejects_out_of_range():
    tools = _registered()
    assert "error" in tools["fl_set_swing"](1.5)
    assert "error" in tools["fl_set_send_level"](1, 0, 2.0)


def test_marker_validation_rejects_bad_input():
    tools = _registered()
    assert "error" in tools["fl_add_marker"]("", 4)
    assert "error" in tools["fl_add_marker"]("Verse", -1)

"""A2: fl_exec_python is gated behind FL_ALLOW_EXEC=1 (off by default).

The gate lives in tools/exec_python._exec_enabled(); the tool itself returns a
descriptive refusal instead of dispatching to FL when the env var is unset.
No connection stubbing: the gate is proven by the refusal path never reaching
get_connection, and the open path by monkeypatching the module-level function.
"""

from __future__ import annotations


class _FakeFastMCP:
    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco

    def __init__(self):
        self.tools = {}


def test_gate_closed_by_default(monkeypatch):
    """With FL_ALLOW_EXEC unset, the tool refuses before touching the connection."""
    monkeypatch.delenv("FL_ALLOW_EXEC", raising=False)
    from fl_studio_mcp.tools import exec_python as mod

    # Make any accidental connection use blow up loudly.
    def no_connection():
        raise AssertionError("get_connection must NOT be called while the gate is closed")

    monkeypatch.setattr(mod, "get_connection", no_connection)
    mcp = _FakeFastMCP()
    mod.register_exec_tools(mcp)
    out = mcp.tools["fl_exec_python"]('print("pwned")')
    assert out["ok"] is False
    assert "FL_ALLOW_EXEC=1" in out["error"]


def test_gate_opens_with_env(monkeypatch):
    """With FL_ALLOW_EXEC=1 the tool passes the gate and dispatches to FL."""
    monkeypatch.setenv("FL_ALLOW_EXEC", "1")
    from fl_studio_mcp.tools import exec_python as mod

    captured = {}

    class _FakeConn:
        def send_command(self, action, params, timeout):
            captured.update({"action": action, "params": params, "timeout": timeout})
            return {"success": True, "stdout": "42", "stderr": ""}

    monkeypatch.setattr(mod, "get_connection", lambda: _FakeConn())
    mcp = _FakeFastMCP()
    mod.register_exec_tools(mcp)
    out = mcp.tools["fl_exec_python"]("import channels; print(channels.channelCount())")
    assert out["ok"] is True
    assert out["stdout"] == "42"
    assert captured["action"] == "probe.exec"  # dispatched (audit-logged in midi_connection)

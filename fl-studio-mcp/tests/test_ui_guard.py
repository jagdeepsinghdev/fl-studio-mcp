"""ui_guard: diagnose / recover / wait_for_front / retry-on-blocked (offline)."""
import pytest

from fl_studio_mcp.utils import ui_guard as g


class Conn:
    def __init__(self, replies):
        self.replies = list(replies)      # successive probe.exec results
        self.sent = []

    def send_command(self, action, params, timeout=None):
        code = params.get("code", "")
        self.sent.append(code)
        if "channelCount" in code:                     # rack filter check (2026-10-06)
            return {"success": True, "stdout": "[7, 7]\n"}
        r = self.replies.pop(0) if self.replies else {"success": True, "stdout": "[0, \"Mixer - Vocal\"]\n"}
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture
def screen(monkeypatch):
    st = {"front": "OsxFL", "titles": ["FL Studio 2026"], "idle": 0.0, "focused": 0}
    monkeypatch.setattr(g.cm, "frontmost_app", lambda: st["front"])
    monkeypatch.setattr(g, "fl_window_titles", lambda: list(st["titles"]))
    monkeypatch.setattr(g, "user_idle_seconds", lambda: st["idle"])
    monkeypatch.setattr(g, "fl_cpu", lambda: 20.0)

    def focus():
        st["focused"] += 1
        st["front"] = "OsxFL"
    monkeypatch.setattr(g.cm, "focus_fl", focus)
    return st


def test_blocked_error_patterns():
    assert g.is_blocked_error("Operation unsafe at current time")
    assert g.is_blocked_error("Timeout waiting for FL Studio response after 2.0s")
    assert not g.is_blocked_error("no knob named x")


def test_diagnose_ready(screen):
    d = g.diagnose(Conn([]))
    assert d["ready"] and d["controller"] == "ok" and d["focused_form"] == "Mixer - Vocal"


def test_diagnose_flags_picker_dialog_and_unsafe(screen):
    screen["titles"] = ["FL Studio 2026", "Select effect plugin", "Error"]
    d = g.diagnose(Conn([{"success": False, "error": "Operation unsafe at current time"}]))
    assert not d["ready"] and d["picker_open"] and d["dialogs"] == ["Error"]
    assert d["controller"] == "unsafe"


def test_diagnose_popup(screen):
    d = g.diagnose(Conn([{"success": True, "stdout": "[1, \"Maximus\"]\n"}]))
    assert d["popup_open"] and not d["ready"]


def test_wait_for_front_never_steals_while_typing(screen):
    screen["front"], screen["idle"] = "iTerm2", 0.2          # user typing
    t = iter(range(0, 1000))
    r = g.wait_for_front(timeout=5, sleep=lambda s: None, clock=lambda: next(t))
    assert not r["front"] and screen["focused"] == 0


def test_wait_for_front_focuses_when_idle(screen):
    screen["front"], screen["idle"] = "iTerm2", 10.0
    r = g.wait_for_front(timeout=5, sleep=lambda s: None)
    assert r["front"] and r["focused_by_us"] and screen["focused"] == 1


def test_run_retries_once_after_recover(monkeypatch):
    from fl_studio_mcp.tools import vocal_v2 as vv
    calls = []

    def flaky(action, conn=None, **kw):
        calls.append(action)
        return ({"success": False, "error": "Operation unsafe at current time"}
                if len(calls) == 1 else {"success": True})
    monkeypatch.setattr(g, "recover", lambda conn, **k: {"success": True, "steps": ["closed picker"]})
    r = vv._call_guarded(flaky, "x", None, {})
    assert r["success"] and len(calls) == 2


def test_run_does_not_retry_real_errors(monkeypatch):
    from fl_studio_mcp.tools import vocal_v2 as vv
    calls = []
    monkeypatch.setattr(g, "recover", lambda conn, **k: pytest.fail("must not recover"))
    r = vv._call_guarded(lambda a, conn=None, **k: calls.append(1) or
                         {"success": False, "error": "no knob named x"}, "x", None, {})
    assert not r["success"] and len(calls) == 1


def test_diagnose_flags_a_filtered_channel_rack(screen):
    class C(Conn):
        def send_command(self, action, params, timeout=None):
            if "channelCount" in params.get("code", ""):
                return {"success": True, "stdout": "[2, 7]\n"}
            return super().send_command(action, params, timeout)
    d = g.diagnose(C([]))
    assert not d["ready"] and d["rack_filtered"] == "2 of 7 channels shown"

"""fl_ui_screen: allowlisted ui.*/screen.* call routing (PE era).

Controller-side: v10.4's _ui_screen_call (allowlist + getattr + args
pass-through; FL's exception text is the signature oracle). Server-side:
one tool, two controller actions.
"""
import sys

sys.path.insert(0, "fl_controller")
import device_FLStudioMCP as dev

sys.path.insert(0, "src")
from fl_studio_mcp.tools.ui_screen_v2 import fl_ui_screen


# ---------------------------------------------------------------- controller
def test_ui_call_allowlisted_name_rejects_unknown():
    out = dev.handle_ui_call({"name": "fork_bomb", "args": []})
    assert out["success"] is False
    assert "not in allowlist" in out["error"]
    assert "enter" in out["allowed"]


def test_ui_call_unknown_module_rejected():
    out = dev._ui_screen_call("rmrf", "enter", [])
    assert out["success"] is False
    assert "unknown module" in out["error"]


def test_screen_calls_quarantined_at_controller():
    # 2026-10-02: screen.menuShowing() crashed FL (EAccessViolation, side
    # thread) — ALL screen calls are refused before any import/call.
    out = dev.handle_screen_call({"name": "menuShowing", "args": []})
    assert out["success"] is False
    assert "quarantined" in out["error"]
    assert out["asked_for"] == "menuShowing"


def test_allowlists_are_reviewed_sets():
    assert "yes" in dev._UI_ALLOWLIST
    assert "no" in dev._UI_ALLOWLIST
    assert "enter" in dev._UI_ALLOWLIST
    assert "navigateBrowser" in dev._UI_ALLOWLIST
    assert "selectBrowserMenuItem" in dev._UI_ALLOWLIST
    assert "setFocused" in dev._UI_ALLOWLIST
    assert "menuItemClick" in dev._SCREEN_ALLOWLIST
    assert "menuShowing" in dev._SCREEN_ALLOWLIST
    # and nothing dangerous sneaks in
    assert "exec" not in dev._UI_ALLOWLIST
    assert "eval" not in dev._UI_ALLOWLIST
    assert "os" not in dev._UI_ALLOWLIST


def test_ui_browser_set_still_gated_in_v10_4c(monkeypatch):
    # v10.4c: key events unlocked; browser/window fns stay gated
    out = dev.handle_ui_call({"name": "navigateBrowser", "args": []})
    assert out["success"] is False
    assert "not callable in v10.4c" in out["error"]
    assert "enter" in out["error"]  # key events ARE in the allowed list


def test_ui_key_event_passes_gate(monkeypatch):
    calls = []
    monkeypatch.setattr(dev, "_ui_screen_call",
                        lambda m, n, a: calls.append((m, n, a))
                        or {"success": True, "module": m, "fn": n,
                            "args": a, "result": "1"})
    out = dev.handle_ui_call({"name": "escape", "args": []})
    assert out["success"] is True
    assert calls == [("ui", "escape", [])]


def test_ui_safe_read_passes_gate(monkeypatch):
    # getProgTitle is in the gate; the call then fails at import in the
    # test env (no FL ui module) — but it must NOT be a gate rejection
    out = dev.handle_ui_call({"name": "getProgTitle", "args": []})
    if not out["success"]:
        assert "safe-read subset" not in out["error"]
        assert "not in allowlist" not in out["error"]


def test_handlers_forward_name_and_args(monkeypatch):
    calls = []

    def fake(module, name, args):
        calls.append((module, name, list(args)))
        return {"success": True, "module": module, "fn": name,
                "args": args, "result": "42"}

    monkeypatch.setattr(dev, "_ui_screen_call", fake)
    out = dev.handle_ui_call({"name": "getProgTitle", "args": []})
    assert out["success"] is True
    assert calls == [("ui", "getProgTitle", [])]


# --------------------------------------------------------------- MCP wrapper
def _mock_send(monkeypatch, responder):
    import fl_studio_mcp.tools.channel_v2 as cv2

    calls = []

    def fake(action, params, conn=None):
        calls.append((action, dict(params)))
        return responder(action, params)

    monkeypatch.setattr(cv2, "_safe_send", fake)
    return calls


def test_wrapper_routes_to_ui_call(monkeypatch):
    calls = _mock_send(monkeypatch,
                       lambda a, p: {"success": True, "fn": p["name"],
                                     "status": "ok"})
    out = fl_ui_screen("ui", "getFocusedFormID", [1])
    assert out["success"] is True
    assert calls == [("ui.call", {"name": "getFocusedFormID", "args": [1]})]
    assert out["result"] == {"fn": "getFocusedFormID", "status": "ok"}


def test_wrapper_quarantines_screen(monkeypatch):
    calls = _mock_send(monkeypatch,
                       lambda a, p: {"success": True, "fn": p["name"]})
    out = fl_ui_screen("screen", "menuItemClick")
    assert out["success"] is False
    assert "quarantined" in out["error"]
    assert calls == []  # never reaches the controller


def test_wrapper_rejects_unknown_module(monkeypatch):
    _mock_send(monkeypatch, lambda a, p: {"success": True})
    out = fl_ui_screen("rmrf", "enter")
    assert out["success"] is False
    assert "unknown module" in out["error"]


def test_wrapper_rejects_ui_browser_set(monkeypatch):
    calls = _mock_send(monkeypatch,
                       lambda a, p: {"success": True, "fn": p["name"]})
    out = fl_ui_screen("ui", "navigateBrowser")
    assert out["success"] is False
    assert "v10.4c" in out["error"]
    assert calls == []


def test_wrapper_allows_ui_key_event(monkeypatch):
    calls = _mock_send(monkeypatch,
                       lambda a, p: {"success": True, "fn": p["name"]})
    out = fl_ui_screen("ui", "escape")
    assert out["success"] is True
    assert calls == [("ui.call", {"name": "escape", "args": []})]


def test_wrapper_surfaces_fl_error_with_oracle_note(monkeypatch):
    _mock_send(monkeypatch,
               lambda a, p: {"success": False,
                             "error": "TypeError: getFocusedFormID() takes "
                                      "1 positional argument (2 given)"})
    out = fl_ui_screen("ui", "getFocusedFormID", [1])
    assert out["success"] is False
    assert "takes 1 positional" in out["error"]
    assert "signature" in out["note"]

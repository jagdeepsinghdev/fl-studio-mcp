"""B8: fl_file — the tier table (open=destructive) + honest API status.

Verified offline:
  - the tier table: open=destructive, save/save_as/export=write
  - open is flagged destructive (confirm-flow territory) and not faked
  - save/save_as/export route to the controller (v10.4e, L15); the v45
    file API is unprobed, so the controller answers with success (a
    candidate ran) or an oracle payload (attempt texts + probe dump)
  - format validation for export (wav|mp3|stems)
  - missing path rejected pre-FL
"""

import pytest

from fl_studio_mcp.tools.file_v2 import ACTIONS, TIERS, _validate, fl_file

# ---------------------------------------------------------------------------
# The tier table (B8's core deliverable)
# ---------------------------------------------------------------------------


def test_tier_table_open_is_destructive():
    assert TIERS["open"] == "destructive"


def test_tier_table_writes():
    assert TIERS["save"] == "write"
    assert TIERS["save_as"] == "write"
    assert TIERS["export"] == "write"


def test_all_actions_have_a_tier():
    for a in ACTIONS:
        assert a in TIERS, f"{a} has no tier"


# ---------------------------------------------------------------------------
# open is destructive (not a plain write)
# ---------------------------------------------------------------------------


def test_open_is_destructive_and_not_faked():
    r = fl_file("open", path="/tmp/other.flp")
    assert r["success"] is False
    assert r["tier"] == "destructive"
    assert r.get("status") == "not_verified_yet"
    assert "DESTRUCTIVE" in r["error"] or "destructive" in r["error"]
    assert "confirm" in r["error"].lower()


def test_open_requires_path():
    assert _validate("open", {})
    assert _validate("open", {"path": "/tmp/x.flp"}) == []


# ---------------------------------------------------------------------------
# save / save_as / export
# ---------------------------------------------------------------------------


def test_save_omits_optional_path():
    assert _validate("save", {}) == []  # path optional (save to current)
    assert _validate("save", {"path": "/tmp/a.flp"}) == []


def test_save_as_requires_path():
    assert _validate("save_as", {})
    assert _validate("save_as", {"path": "/tmp/a.flp"}) == []


def test_export_requires_path_and_valid_format():
    assert _validate("export", {})
    assert _validate("export", {"path": "/tmp/a.wav", "format": "flac"})  # bad format
    assert _validate("export", {"path": "/tmp/a.wav", "format": "wav"}) == []
    assert _validate("export", {"path": "/tmp/a.wav", "format": "mp3"}) == []
    assert _validate("export", {"path": "/tmp/a.wav", "format": "stems"}) == []


@pytest.mark.parametrize("action,extra", [
    ("save", {"path": "/tmp/a.flp"}),
    ("save_as", {"path": "/tmp/a.flp"}),
    ("export", {"path": "/tmp/a.wav", "format": "wav"}),
])
def test_write_actions_route_to_controller(action, extra):
    """v10.4e (L15): save/save_as/export are wired — they reach the
    controller's candidate-cascade handlers (file.save / file.saveAs /
    file.export). Success here means a candidate ran without raising; the
    v45 API itself is still confirmed by the post-restart matrix."""
    calls = []

    class C:
        def send_command(self, action, params=None, timeout=None):
            calls.append((action, params))
            return {"success": True, "saved": True, "via": "general.save()",
                    "undo_saved": "u"}
    r = fl_file(action, conn=C(), **extra)
    assert r["success"] is True
    want = {"save": "file.save", "save_as": "file.saveAs",
            "export": "file.export"}[action]
    assert calls[0][0] == want


def test_unknown_action_rejected_with_list():
    r = _validate("explode", {})
    assert "open" in r[0]

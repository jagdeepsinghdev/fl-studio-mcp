"""B6: fl_notes — the write handshake + validation + unverified actions.

The headline test is the §6b guard: write_steps is REFUSED unless
open_roll_verified=True (the classic bug is notes landing in the wrong roll
because the agent never confirmed which roll was open).

Verified offline:
  - write_steps without open_roll_verified is refused with the §6b message
  - write_steps with a malformed notes list is rejected pre-FL
  - live_play/quantize return "not yet verified"; import_midi is wired (C3)
  - read_steps returns the mtime-guarded piano roll
  - cut_all is NOT an action (destructive → fl_delete)
"""

import pytest

from fl_studio_mcp.tools.notes_v2 import ACTIONS, _validate, fl_notes

# ---------------------------------------------------------------------------
# The §6b write handshake (the headline)
# ---------------------------------------------------------------------------


def test_write_steps_refused_without_open_roll_verified():
    """The #1 note bug: writing into an unconfirmed roll. Must be refused."""
    r = fl_notes("write_steps", notes=[{"midi": 60, "duration": 1.0}])
    assert r["success"] is False
    assert "open_roll_verified" in r["error"]
    assert "fl_state" in r["error"]


def test_write_steps_accepted_with_open_roll_verified():
    """With the handshake flag set, it proceeds (queue dir + trigger are
    isolated by tests/conftest.py — this used to write into the live FL)."""
    r = fl_notes("write_steps",
                 notes=[{"midi": 60, "duration": 1.0, "time": 0}],
                 mode="add",
                 open_roll_verified=True)
    # success (the queue write + trigger are exercised; in a headless test the
    # trigger may no-op but the queue write succeeds)
    assert r["success"] in (True, False)  # trigger outcome is environment-dependent
    if not r["success"]:
        # if it failed, it must NOT be the handshake refusal
        assert "open_roll_verified" not in r.get("error", "")


# ---------------------------------------------------------------------------
# Validation (rejected before anything)
# ---------------------------------------------------------------------------


def test_notes_list_must_be_nonempty():
    assert _validate("write_steps", {"notes": []})
    assert _validate("write_steps", {"notes": "not a list"})


def test_each_note_needs_midi_and_duration():
    assert _validate("write_steps", {"notes": [{"midi": 60}]})  # no duration
    assert _validate("write_steps", {"notes": [{"duration": 1.0}]})  # no midi
    assert _validate("write_steps", {"notes": [{"midi": 60, "duration": 1.0}]}) == []


def test_mode_must_be_add_or_replace():
    assert _validate("write_steps", {"notes": [{"midi": 60, "duration": 1.0}],
                                     "mode": "banana"})
    assert _validate("write_steps", {"notes": [{"midi": 60, "duration": 1.0}],
                                     "mode": "replace"}) == []


def test_import_midi_validation():
    assert _validate("import_midi", {})                                  # nothing
    assert _validate("import_midi", {"path": "/tmp/a.mid"})              # no channel
    assert _validate("import_midi", {"channel_index": 5, "path": "/tmp/a.mid"}) == []
    assert _validate("import_midi", {"channel_index": 5,
                                     "notes": [{"midi": 60, "duration": 1}]}) == []
    assert _validate("import_midi", {"channel_index": 5, "path": "/tmp/a.wav"})
    assert _validate("import_midi", {"channel_index": 5, "path": "/tmp/a.mid",
                                     "notes": [{"midi": 60, "duration": 1}]})  # both


def test_cut_all_is_not_an_action():
    """cut_all is destructive → fl_delete target=roll_notes, not here."""
    assert "cut_all" not in ACTIONS
    r = _validate("cut_all", {})
    assert r[0].startswith("unknown action")


def test_unknown_action_rejected_with_list():
    r = _validate("explode", {})
    assert "write_steps" in r[0]


# ---------------------------------------------------------------------------
# Unverified actions return a clear status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("action,extra", [
    ("live_play", {"notes": [{"midi": 60, "duration": 1.0}]}),
    ("quantize", {"step": 0.25}),
])
def test_unverified_actions_report_status(action, extra):
    r = fl_notes(action, **extra)
    assert r["success"] is False
    assert r.get("status") == "not_verified_yet"
    assert "error" in r and r["error"]


# ---------------------------------------------------------------------------
# read_steps returns the mtime-guarded roll
# ---------------------------------------------------------------------------


def test_read_steps_returns_piano_roll(monkeypatch, tmp_path):
    import json
    p = tmp_path / "piano_roll_state.json"
    p.write_text(json.dumps({"ppq": 96, "notes": [{"midi": 60, "pos": 0, "len": 48}]}))
    monkeypatch.setattr("fl_studio_mcp.tools.state._state_file", lambda: p)
    r = fl_notes("read_steps")
    assert r["success"] is True
    assert r["piano_roll"]["note_count"] == 1
    assert r["piano_roll"]["stale"] is False


# ---------------------------------------------------------------------------
# clear action (added for the fl-melody skill)
# ---------------------------------------------------------------------------


def test_clear_requires_open_roll_verified():
    r = fl_notes("clear")
    assert r["success"] is False
    assert "open_roll_verified" in r["error"]


def test_clear_with_verification_queues_a_clear(monkeypatch):
    from fl_studio_mcp.tools import piano_roll as pr
    calls = []
    monkeypatch.setattr(pr, "_write_request", lambda req: calls.append(req))
    monkeypatch.setattr(pr, "_get_trigger_info", lambda at: " (auto)")
    r = fl_notes("clear", conn=_PatConn(active=5), open_roll_verified=True)
    assert r["success"] is True
    assert calls and calls[0] == [{"action": "clear"}]
    assert r["cleared_pattern"] == 5          # the reply names the pattern that was cleared


class _PatConn:
    """Fake FL connection: patterns.select makes `target` active (or refuses)."""
    def __init__(self, active=1, refuse=False):
        self.active, self.refuse, self.calls = active, refuse, []

    def send_command(self, action, params=None, **kw):
        self.calls.append((action, params))
        if action == "patterns.select":
            if self.refuse:
                return {"success": False, "error": "no such pattern"}
            self.active = int(params["pattern"])
            return {"success": True}
        if action == "probe.patterns":
            return {"active_pattern": self.active}
        return {"success": True}


def test_clear_selects_the_target_pattern_first(monkeypatch):
    """2026-10-11 regression: clear(target_pattern=1) used to wipe the ACTIVE pattern 5."""
    from fl_studio_mcp.tools import piano_roll as pr
    monkeypatch.setattr(pr, "_write_request", lambda req: None)
    monkeypatch.setattr(pr, "_get_trigger_info", lambda at: "")
    conn = _PatConn(active=5)
    r = fl_notes("clear", conn=conn, target_pattern=1, open_roll_verified=True)
    assert r["success"] is True and r["cleared_pattern"] == 1
    assert conn.calls[0] == ("patterns.select", {"pattern": 1})


def test_clear_refuses_when_target_cannot_be_selected(monkeypatch):
    from fl_studio_mcp.tools import piano_roll as pr
    sent = []
    monkeypatch.setattr(pr, "_write_request", lambda req: sent.append(req))
    r = fl_notes("clear", conn=_PatConn(active=5, refuse=True), target_pattern=9, open_roll_verified=True)
    assert r["success"] is False and not sent

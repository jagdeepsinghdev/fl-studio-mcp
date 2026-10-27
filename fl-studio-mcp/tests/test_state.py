"""B1: fl_state — session snapshot with the piano-roll mtime guard.

The 11.8-hour stale-file incident (P4): the agent read piano_roll_state.json,
assumed the notes were current, and built on a snapshot from hours ago.
fl_state fixes this by reporting the state file's mtime + age + a `stale`
flag, so a stale note list is never silently treated as live.

Verified offline: a backdated state file fixture reproduces the incident and
the guard flags it.
"""

import json
import os
import time
from pathlib import Path

import pytest

from fl_studio_mcp.tools.state import _state_file, take_state_snapshot

# ---------------------------------------------------------------------------
# The 11.8-hour incident as a fixture
# ---------------------------------------------------------------------------

INCIDENT_AGE_SECONDS = 11.8 * 3600  # 42480s


@pytest.fixture(autouse=True)
def _fake_controller(monkeypatch):
    """Stands in for the controller (these tests used to hit the live FL).
    Tests needing a specific snapshot patch send_command again."""
    from fl_studio_mcp.utils import connection as connmod
    monkeypatch.setattr(
        connmod.FLConnection, "send_command",
        lambda self, cmd, *a, **k: {"success": True, "bpm": 120,
                                    "patterns": [], "channel_count": 0})


@pytest.fixture
def backdated_state_file(tmp_path: Path, monkeypatch):
    """Create a piano-roll state file and backdate it 11.8 hours."""
    p = tmp_path / "piano_roll_state.json"
    p.write_text(json.dumps({
        "ppq": 96,
        "notes": [
            {"midi": 45, "pos": 0, "len": 48},
            {"midi": 48, "pos": 96, "len": 48},
        ],
    }))
    old = time.time() - INCIDENT_AGE_SECONDS
    os.utime(p, (old, old))
    # point the state-file resolver at our fixture
    monkeypatch.setattr("fl_studio_mcp.tools.state._state_file", lambda: p)
    return p


def test_backdated_state_file_is_flagged_stale(tmp_path, monkeypatch, backdated_state_file):
    """The 11.8h-old state file must be flagged stale by fl_state."""
    result = take_state_snapshot(fresh_seconds=600)
    pr = result["piano_roll"]
    assert pr["stale"] is True
    assert pr["note_count"] == 2
    assert pr["age_seconds"] > INCIDENT_AGE_SECONDS - 60  # ≈11.8h
    assert "warning" in pr
    assert "ComposeWithLLM" in pr["warning"]


def test_fresh_state_file_not_stale(tmp_path, monkeypatch):
    """A just-written state file is fresh."""
    p = tmp_path / "piano_roll_state.json"
    p.write_text(json.dumps({"ppq": 96, "notes": []}))
    monkeypatch.setattr("fl_studio_mcp.tools.state._state_file", lambda: p)
    result = take_state_snapshot(fresh_seconds=600)
    pr = result["piano_roll"]
    assert pr["stale"] is False
    assert pr["note_count"] == 0
    assert "warning" not in pr


def test_zero_fresh_seconds_always_stale(tmp_path, monkeypatch):
    """fresh_seconds=0 → always stale (conservative)."""
    p = tmp_path / "piano_roll_state.json"
    p.write_text(json.dumps({"ppq": 96, "notes": []}))
    monkeypatch.setattr("fl_studio_mcp.tools.state._state_file", lambda: p)
    result = take_state_snapshot(fresh_seconds=0)
    assert result["piano_roll"]["stale"] is True


def test_missing_state_file_is_stale_with_zero_notes(tmp_path, monkeypatch):
    p = tmp_path / "does_not_exist.json"
    monkeypatch.setattr("fl_studio_mcp.tools.state._state_file", lambda: p)
    result = take_state_snapshot(fresh_seconds=600)
    pr = result["piano_roll"]
    assert pr["stale"] is True
    assert pr["note_count"] == 0
    assert "warning" in pr


def test_corrupt_state_file_is_stale(tmp_path, monkeypatch):
    p = tmp_path / "piano_roll_state.json"
    p.write_text("not json at all {{{")
    monkeypatch.setattr("fl_studio_mcp.tools.state._state_file", lambda: p)
    result = take_state_snapshot(fresh_seconds=600)
    pr = result["piano_roll"]
    assert pr["stale"] is True
    assert pr["note_count"] == 0


# ---------------------------------------------------------------------------
# The snapshot fields the agent needs to orient
# ---------------------------------------------------------------------------

def test_snapshot_contains_core_session_fields(monkeypatch):
    """take_state_snapshot returns the fields fl_state promises (FL mocked)."""
    from fl_studio_mcp.utils import connection as connmod
    fake = {"success": True, "protocol_v2": True, "state": {
        "bpm": 130, "transport": {"is_playing": False},
        "patterns": [{"n": 1, "name": "Pattern 1", "length": 16}],
        "selected_pattern": 1, "channel_count": 5,
        "selected_channel": {"index": 0, "name": "808 Kick"},
        "fl_version": 26,
        "active_pattern": 1, "active_is_default": False,
    }}
    monkeypatch.setattr(connmod.FLConnection, "send_command",
                        lambda self, cmd, *a, **k: fake)
    monkeypatch.setattr("fl_studio_mcp.tools.state._state_file",
                        lambda: Path("/nonexistent/state.json"))
    result = take_state_snapshot()
    for field in ("bpm", "transport", "patterns", "selected_pattern",
                  "channel_count", "selected_channel", "project",
                  "fl_version", "piano_roll", "active_pattern",
                  "active_is_default"):
        assert field in result, f"missing {field}"
    assert result["bpm"] == 130
    assert result["piano_roll"]["stale"] is True  # missing file -> stale
    assert result["active_pattern"] == 1
    assert result["active_is_default"] is False


def test_snapshot_flags_default_active_pattern(monkeypatch):
    """When the active pattern is a FL default (empty), fl_state flags it.

    This is the case the fl-patterns skill warns about: a select can drift
    the active pattern to an empty default, making all step reads come
    back empty.  active_is_default=True tells the agent to re-select the
    intended pattern instead of trusting empty reads.
    """
    from fl_studio_mcp.utils import connection as connmod
    fake = {"success": True, "protocol_v2": True, "state": {
        "bpm": 130, "transport": {"is_playing": False},
        "patterns": [{"n": 2, "name": "Verse", "length": 16}],
        "selected_pattern": 2, "channel_count": 5,
        "selected_channel": None, "fl_version": 26,
        "active_pattern": 1, "active_is_default": True,
    }}
    monkeypatch.setattr(connmod.FLConnection, "send_command",
                        lambda self, cmd, *a, **k: fake)
    monkeypatch.setattr("fl_studio_mcp.tools.state._state_file",
                        lambda: Path("/nonexistent/state.json"))
    result = take_state_snapshot()
    assert result["selected_pattern"] == 2
    assert result["active_pattern"] == 1
    assert result["active_is_default"] is True
    # The active pattern (1) is not in the patterns list (skipped by _named_patterns)
    assert [p["n"] for p in result["patterns"]] == [2]


def test_snapshot_backwards_compat_no_active_fields(monkeypatch):
    """Pre-v10.4h controllers don't send active_pattern/active_is_default.
    fl_state falls back to selected_pattern and False."""
    from fl_studio_mcp.utils import connection as connmod
    fake = {"success": True, "protocol_v2": True, "state": {
        "bpm": 130, "transport": {"is_playing": False},
        "patterns": [{"n": 1, "name": "Pattern 1", "length": 16}],
        "selected_pattern": 1, "channel_count": 5,
        "selected_channel": None, "fl_version": 26,
    }}
    monkeypatch.setattr(connmod.FLConnection, "send_command",
                        lambda self, cmd, *a, **k: fake)
    monkeypatch.setattr("fl_studio_mcp.tools.state._state_file",
                        lambda: Path("/nonexistent/state.json"))
    result = take_state_snapshot()
    assert result["active_pattern"] == 1  # falls back to selected_pattern
    assert result["active_is_default"] is False


def test_state_file_resolver_finds_real_location():
    """_state_file() returns a path under the FL settings tree."""
    p = _state_file()
    assert "Image-Line" in str(p)
    assert p.name == "piano_roll_state.json"


def test_state_note_list_is_compact_capped_and_summarised(tmp_path, monkeypatch):
    """L6: a 42-note roll was ~15 KB per fl_state call (10 constant fields per note)."""
    from fl_studio_mcp.tools.state import _read_piano_roll
    notes = [{"number": 60 + (i % 12), "midi": 60 + (i % 12), "time": i * 0.25,
              "duration": 0.25, "velocity": 0.7, "pan": 0.5, "fcut": 0.5, "fres": 0.5,
              "color": 0, "time_ticks": i * 24, "length_ticks": 24, "slide": i == 3,
              "porta": False, "pitchofs": 0, "selected": False, "muted": False}
             for i in range(42)]
    p = tmp_path / "piano_roll_state.json"
    p.write_text(json.dumps({"ppq": 96, "notes": notes}))
    monkeypatch.setattr("fl_studio_mcp.tools.state._state_file", lambda: p)
    capped = _read_piano_roll(600, max_notes=16)
    assert capped["note_count"] == 42 and len(capped["notes"]) == 16
    assert capped["notes_truncated"] is True
    assert set(capped["notes"][0]) == {"midi", "time", "duration", "velocity"}
    assert capped["notes"][3]["slide"] is True
    assert capped["summary"] == {"pitch_range": [60, 71], "end_beat": 10.5, "slides": 1}
    full = _read_piano_roll(600)
    assert len(full["notes"]) == 42 and "notes_truncated" not in full


def test_fl_version_falls_back_to_ui_getversion(monkeypatch):
    """L7: state.snapshot returned fl_version null."""
    from fl_studio_mcp.tools import state as st
    st._VERSION_CACHE.clear()

    class C:
        def send_command(self, action, params=None, timeout=None):
            if action == "ui.call":
                return {"success": True, "result": "'Producer Edition v26.1.6 [build 5406]'"}
            return {"success": True, "state": {"bpm": 140}}
    monkeypatch.setattr(st, "get_connection", lambda: C())
    assert st.take_state_snapshot()["fl_version"] == "Producer Edition v26.1.6 [build 5406]"


def test_state_from_a_previous_fl_session_is_stale(tmp_path, monkeypatch):
    """L18 (live): after an FL restart a 4-minute-old state file passed the age
    check (stale: false) but described the PREVIOUS session's roll."""
    from fl_studio_mcp.tools.state import _read_piano_roll
    from fl_studio_mcp.utils import roll_session
    p = tmp_path / "piano_roll_state.json"
    p.write_text(json.dumps({"ppq": 96, "notes": [{"midi": 48, "time": 0, "duration": 0}]}))
    written = time.time() - 270
    os.utime(p, (written, written))
    monkeypatch.setattr("fl_studio_mcp.tools.state._state_file", lambda: p)
    monkeypatch.setattr(roll_session, "fl_started_at", lambda: written + 200)  # FL restarted after
    pr = _read_piano_roll(600)
    assert pr["stale"] is True and pr["from_previous_fl_session"] is True
    assert "PREVIOUS FL session" in pr["warning"]
    monkeypatch.setattr(roll_session, "fl_started_at", lambda: written - 3600)  # same session
    assert _read_piano_roll(600)["stale"] is False


def test_parse_ps_etime():
    from fl_studio_mcp.utils.roll_session import parse_etime
    assert parse_etime("01:07") == 67
    assert parse_etime("02:00:05") == 7205
    assert parse_etime("1-00:00:10") == 86410
    assert parse_etime("") is None and parse_etime("x:y") is None

"""Automatic §0 selection + roll targeting (utils/roll_session.py).

Live facts these pin (2026-10-01, PE v26.1.6): the script selection survives
channel switches within one FL process; `channels.selectOne` does NOT retarget
an open roll (a View-menu close/reopen does). All FL access is mocked — no
osascript, no MIDI trips, no clicks.
"""

from __future__ import annotations

import json
import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fl_studio_mcp.utils import fl_trigger  # noqa: E402
from fl_studio_mcp.utils import roll_session as rs


@pytest.fixture
def scripts(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "_scripts_dir", lambda: tmp_path)
    from fl_studio_mcp.tools import piano_roll
    monkeypatch.setattr(piano_roll, "_get_request_file",
                        lambda: tmp_path / "mcp_request.json")
    monkeypatch.setenv("FL_AUTO_SELECT_SCRIPT", "1")
    (tmp_path / "piano_roll_state.json").write_text("{}")
    return tmp_path


def _touch_state(d):
    p = d / "piano_roll_state.json"
    st = p.stat().st_mtime
    os.utime(p, (st + 5, st + 5))


def test_disabled_under_pytest_by_default(monkeypatch):
    monkeypatch.delenv("FL_AUTO_SELECT_SCRIPT", raising=False)
    assert rs.auto_enabled() is False
    assert rs.ensure_script_selected()["skipped"] == "auto-select disabled"


def test_already_selected_for_this_pid_makes_no_clicks(scripts, monkeypatch):
    monkeypatch.setattr(rs, "fl_pid", lambda: 4242)
    rs.mark_selected(4242)
    with mock.patch("fl_studio_mcp.tools.select_script.fl_select_script") as sel:
        r = rs.ensure_script_selected()
    assert r["already_selected"] is True
    sel.assert_not_called()


def test_new_fl_process_selects_with_queue_stashed_then_restored(scripts, monkeypatch):
    monkeypatch.setattr(rs, "fl_pid", lambda: 999)
    monkeypatch.setattr(rs.time, "sleep", lambda s: None)
    rs.mark_selected(111)  # old FL process
    queued = json.dumps([{"action": "add_notes", "notes": [{"midi": 60}]}])
    (scripts / "mcp_request.json").write_text(queued)
    seen_queue = []

    def fake_select():
        # the selection run must see an EMPTY queue (else notes apply twice)
        seen_queue.append((scripts / "mcp_request.json").read_text())
        _touch_state(scripts)
        return {"success": True}

    with mock.patch("fl_studio_mcp.tools.select_script.fl_select_script", fake_select):
        r = rs.ensure_script_selected()
    assert r["ok"] and r["selected_now"]
    assert seen_queue == ["[]"]
    assert (scripts / "mcp_request.json").read_text() == queued
    assert rs.recorded_pid() == 999


def test_selection_without_a_script_run_is_not_recorded(scripts, monkeypatch):
    monkeypatch.setattr(rs, "fl_pid", lambda: 999)
    monkeypatch.setattr(rs.time, "sleep", lambda s: None)
    with mock.patch("fl_studio_mcp.tools.select_script.fl_select_script",
                    return_value={"success": True}):
        r = rs.ensure_script_selected()
    assert r["ok"] is False and r["script_ran"] is False
    assert rs.recorded_pid() is None


def test_fl_not_running(scripts, monkeypatch):
    monkeypatch.setattr(rs, "fl_pid", lambda: None)
    assert rs.ensure_script_selected()["ok"] is False


class _Conn:
    def __init__(self):
        self.calls = []

    def send_command(self, action, params=None, timeout=None):
        self.calls.append(action)
        if action == "channels.getAll":
            return {"channels": [{"index": 0, "name": "808 Kick"},
                                 {"index": 5, "name": "Acoustic Piano"}]}
        return {"success": True}


def _roll_env(monkeypatch, titles, ocr=True):
    conn = _Conn()
    monkeypatch.setattr("fl_studio_mcp.utils.connection.get_connection", lambda: conn)
    monkeypatch.setattr(rs, "_activate_fl", lambda: None)
    monkeypatch.setattr(rs, "_ocr_bin", lambda: "ocr" if ocr else None)
    monkeypatch.setattr(rs.time, "sleep", lambda s: None)
    toggles = []
    monkeypatch.setattr(rs, "_toggle_roll", lambda: toggles.append(1))
    it = iter(titles)
    monkeypatch.setattr(rs, "screen_roll_title", lambda names=None: next(it, None))
    return conn, toggles


def test_open_roll_toggles_until_screen_title_matches(monkeypatch):
    # FL redraws late / focus games: keep toggling until the DRAWN title names it
    conn, toggles = _roll_env(monkeypatch, ["Acoustic Piano", None, "808 Kick ›"])
    r = rs.open_roll_for_channel(0)
    assert r["ok"] and r["proof"] == "screen title" and r["toggles"] == 2
    assert len(toggles) == 2
    assert "channels.selectOne" in conn.calls


def test_open_roll_already_on_target_makes_no_toggles(monkeypatch):
    _, toggles = _roll_env(monkeypatch, ["808 Kick •"])
    assert rs.open_roll_for_channel(0)["ok"]
    assert toggles == []


def test_open_roll_refuses_when_title_never_matches(monkeypatch):
    # the 2026-10-01 incident shape: roll stuck on another channel
    _, toggles = _roll_env(monkeypatch, ["Acoustic Piano"] * 10)
    r = rs.open_roll_for_channel(0, max_toggles=3)
    assert r["ok"] is False and "refusing to write" in r["error"]
    assert len(toggles) == 3


def test_open_roll_refuses_without_ocr(monkeypatch):
    _, toggles = _roll_env(monkeypatch, ["808 Kick"], ocr=False)
    r = rs.open_roll_for_channel(0)
    assert r["ok"] is False and "OCR" in r["error"] and toggles == []


def test_open_roll_unknown_channel(monkeypatch):
    _roll_env(monkeypatch, [])
    assert rs.open_roll_for_channel(9)["ok"] is False


def test_title_regex_and_name_normalisation():
    assert rs._TITLE_RE.search("4› Piano roll - Acoustic Piano ›").group(1).strip() == "Acoustic Piano"
    assert rs._TITLE_RE.search("Piano roll") is None
    assert rs._norm("Acoustic Piano •") == rs._norm("acoustic piano")
    assert rs._norm("808") != rs._norm("808 Kick")


def test_load_melody_refuses_when_roll_not_confirmed(scripts, monkeypatch):
    from fl_studio_mcp.tools import preset_v2
    monkeypatch.setattr(preset_v2, "get_connection", lambda: _Conn())
    monkeypatch.setattr(rs, "open_roll_for_channel",
                        lambda idx: {"ok": False, "error": "nope"})
    r = preset_v2.load_melody("a-minor-pop", channel_index=0, auto_trigger=False)
    assert r == {"ok": False, "error": "nope"}
    assert not (scripts / "mcp_request.json").exists()


def test_trigger_self_heals_when_script_did_not_run(scripts, monkeypatch):
    calls = []
    monkeypatch.setattr(rs, "ensure_script_selected",
                        lambda force=False: calls.append(force) or {"ok": True})
    t = fl_trigger.FLStudioTrigger()
    keys = []
    t._trigger_func = lambda: keys.append(1) or True
    assert t.trigger(delay=0) is True
    assert calls == [False, True]   # normal ensure, then forced heal
    assert len(keys) == 2           # re-triggered once


def test_trigger_no_heal_when_script_ran(scripts, monkeypatch):
    calls = []
    monkeypatch.setattr(rs, "ensure_script_selected",
                        lambda force=False: calls.append(force) or {"ok": True})
    t = fl_trigger.FLStudioTrigger()
    t._trigger_func = lambda: _touch_state(scripts) or True
    assert t.trigger(delay=0) is True
    assert calls == [False]


def test_fl_notes_channel_index_retargets_then_writes(scripts, monkeypatch):
    from fl_studio_mcp.tools.notes_v2 import fl_notes
    seen = []
    monkeypatch.setattr(rs, "open_roll_for_channel",
                        lambda idx: seen.append(idx) or {"ok": True})
    r = fl_notes("write_steps", conn=_Conn(), channel_index=6, auto_trigger=False,
                 notes=[{"midi": 36, "duration": 1, "time": 0},
                        {"midi": 39, "duration": 0.25, "time": 0.75, "slide": True}])
    assert r["success"] is True and seen == [6]
    queued = json.loads((scripts / "mcp_request.json").read_text())
    assert queued[-1]["notes"][1]["slide"] is True  # slide passes through


def test_fl_notes_channel_index_refuses_when_roll_unproven(scripts, monkeypatch):
    from fl_studio_mcp.tools.notes_v2 import fl_notes
    monkeypatch.setattr(rs, "open_roll_for_channel",
                        lambda idx: {"ok": False, "error": "could not confirm"})
    r = fl_notes("write_steps", conn=_Conn(), channel_index=6, auto_trigger=False,
                 notes=[{"midi": 36, "duration": 1}])
    assert r["success"] is False and "could not confirm" in r["error"]
    assert not (scripts / "mcp_request.json").exists()


def test_preset_slide_notes_reach_the_queue(scripts, monkeypatch):
    from fl_studio_mcp.tools import preset_v2
    monkeypatch.setattr(preset_v2, "get_connection", lambda: _Conn())
    monkeypatch.setattr(rs, "open_roll_for_channel", lambda idx: {"ok": True})
    r = preset_v2.load_melody("drill-808-c-minor", channel_index=6, auto_trigger=False)
    assert r["ok"] and r["notes_queued"] == 11
    notes = json.loads((scripts / "mcp_request.json").read_text())[-1]["notes"]
    assert sum(1 for n in notes if n.get("slide")) == 3
    assert max(n["time"] + n["duration"] for n in notes) <= 8  # inside the 8-beat loop

"""fl_edison (tools/edison_v2.py) + utils/edison_flow.py, with every UI call
mocked (OCR, clicks, hints, the controller): nothing touches FL or the mouse."""

from __future__ import annotations

import json
from unittest import mock

import pytest

from fl_studio_mcp.tools import edison_v2 as tool
from fl_studio_mcp.utils import edison_flow as flow
from fl_studio_mcp.utils.custom_menu import Box


@pytest.fixture(autouse=True)
def _mac(monkeypatch):
    monkeypatch.setattr(tool.sys, "platform", "darwin")


@pytest.fixture
def hits(tmp_path):
    p = tmp_path / "drums.json"
    p.write_text(json.dumps({"hits": [{"t": 1.0, "type": "kick"},
                                      {"t": 2.0, "type": "hat"}]}))
    return str(p)


@pytest.fixture
def clip(tmp_path):
    p = tmp_path / "drums.wav"
    p.write_bytes(b"RIFF")
    return str(p)


def _ok(**kw):
    return {"ok": True, **kw, "log": []}


# ------------------------------------------------------------- validation --

@pytest.mark.parametrize("kw, msg", [
    ({"action": "nope"}, "unknown action"),
    ({"action": "load_regions"}, "hits_json"),
    ({"action": "send_to_channel"}, "needs channel"),
    ({"action": "load_regions", "clip": "/no/such.wav", "hits_json": "x"}, "existing audio"),
    ({"action": "send_to_channel", "channel": 5, "out": "/tmp/x.wav"}, "inside the repo"),
    ({"action": "send_to_channel", "channel": 5, "out": "data/x.mp3"}, ".wav"),
])
def test_rejects_bad_input_before_touching_the_ui(monkeypatch, kw, msg):
    ui = mock.Mock(side_effect=AssertionError("UI touched"))
    for f in ("open_edison", "load_regions", "send_to_channel", "locate"):
        monkeypatch.setattr(flow, f, ui)
    r = tool.fl_edison(**kw)
    assert r["ok"] is False and msg in r["error"]


def test_non_mac_refuses(monkeypatch):
    monkeypatch.setattr(tool.sys, "platform", "linux")
    assert "darwin" in tool.fl_edison("status")["error"]


# --------------------------------------------------------------- sequence --

def test_run_does_all_steps_with_expected_count(monkeypatch, hits, clip):
    calls = []
    monkeypatch.setattr(flow, "open_edison", lambda: calls.append("open") or _ok())
    monkeypatch.setattr(flow, "load_regions", lambda c, regs, clear_regions: (
        calls.append(("load", c, len(regs))) or _ok(reply={"added": len(regs)})))
    monkeypatch.setattr(flow, "send_to_channel", lambda channel, out, expected: (
        calls.append(("send", channel, expected)) or _ok(region_count=expected)))
    r = tool.fl_edison("run", clip=clip, hits_json=hits, channel=5)
    assert r["ok"] and set(r["steps"]) == {"open", "load_regions", "send_to_channel"}
    assert calls == ["open", ("load", clip, 2), ("send", 5, 2)]


def test_run_stops_at_the_first_failure(monkeypatch, hits):
    monkeypatch.setattr(flow, "open_edison", lambda: _ok())
    monkeypatch.setattr(flow, "load_regions", lambda *a, **k: {
        "ok": False, "error": "no MCP-EDISON reply dialog", "log": []})
    sent = mock.Mock()
    monkeypatch.setattr(flow, "send_to_channel", sent)
    r = tool.fl_edison("run", hits_json=hits, channel=5)
    assert r["ok"] is False and r["error"].startswith("load_regions:")
    sent.assert_not_called()


def test_status_is_read_only(monkeypatch):
    monkeypatch.setattr(flow, "locate", lambda: {"anchor": "Edison (Insert 6)"})
    r = tool.fl_edison("status")
    assert r == {"ok": True, "action": "status", "edison_open": True,
                 "anchor": "Edison (Insert 6)"}


# ------------------------------------------------------------ flow safety --

def _no_front(monkeypatch, front=True):
    monkeypatch.setattr(flow.cm, "require_fl_front", lambda: front)
    monkeypatch.setattr(flow.cm, "frontmost_app", lambda: "Google Chrome")
    monkeypatch.setattr(flow.time, "sleep", lambda s: None)
    monkeypatch.setattr(flow.cm, "move", mock.Mock())      # never the real pointer


def test_flow_refuses_when_fl_is_not_front(monkeypatch):
    _no_front(monkeypatch, front=False)
    clicked = mock.Mock()
    monkeypatch.setattr(flow.cm, "_click", clicked)
    r = flow.send_to_channel()
    assert r["ok"] is False and "Chrome" in r["error"]
    clicked.assert_not_called()


def test_send_refuses_when_the_hint_is_not_the_send_button(monkeypatch):
    _no_front(monkeypatch)
    monkeypatch.setattr(flow, "_logo", lambda: Box(1021, 339, 62, 19, "edison"))
    monkeypatch.setattr(flow.cm, "hint_at", lambda x, y: "Save as... / save as WavPack...")
    clicked = mock.Mock()
    monkeypatch.setattr(flow.cm, "_click", clicked)
    r = flow.send_to_channel()
    assert r["ok"] is False and "send button not at (1083,408)" in r["error"]
    clicked.assert_not_called()


def test_locate_never_matches_a_channel_named_edison(monkeypatch):
    monkeypatch.setattr(flow, "uncover", lambda *a: False)
    monkeypatch.setattr(flow.cm, "ocr_region", lambda *a, **k: [
        Box(329, 320, 70, 10, "Edison Regions")])
    assert flow.locate() is None
    monkeypatch.setattr(flow.cm, "ocr_region", lambda *a, **k: [
        Box(329, 320, 70, 10, "Edison Regions"),
        Box(400, 320, 90, 10, "Edison (Insert 6)")])
    assert flow.locate()["rc"] == (660, 650)


def test_load_regions_fails_on_a_reply_for_another_request(monkeypatch, tmp_path):
    _no_front(monkeypatch)
    monkeypatch.setattr(flow.eb, "install", lambda src: tmp_path / "s.pyscript")
    monkeypatch.setattr(flow, "locate", lambda: {"anchor": "x", "rc": (500, 500), "top": 300})
    monkeypatch.setattr(flow.cm, "menu_cascade", lambda *a, **k: [Box(0, 0, 1, 1, "x")])
    monkeypatch.setattr(flow, "_read_reply", lambda rid, log, t: {
        "id": "stale", "ok": 1, "added": 1})
    r = flow.load_regions(None, [{"name": "k", "start_s": 1.0}])
    assert r["ok"] is False and "reply mismatch" in r["error"]


def test_locate_falls_back_to_the_logo(monkeypatch):
    # the title is covered by another window; only the faint logo is read
    monkeypatch.setattr(flow.cm, "window_by_name", lambda n: None)
    got = flow.locate([Box(1046, 370, 60, 19, "edison")])
    assert got == {"anchor": "edison", "rc": (707, 675), "top": 365}


def test_send_waits_out_a_loading_hint_then_stops_a_started_transport(monkeypatch, tmp_path):
    _no_front(monkeypatch)
    monkeypatch.setattr(flow, "_logo", lambda: Box(1021, 339, 62, 19, "edison"))
    hints = iter(["Loading: drums.wav", "Send to playlist as audio clip / to channel",
                  "Stop Space"])
    monkeypatch.setattr(flow.cm, "hint_at", lambda x, y: next(hints))
    clicks = []
    monkeypatch.setattr(flow.cm, "_click", lambda x, y, **k: clicks.append((x, y, k)))
    playing = iter([False, True])
    monkeypatch.setattr(flow, "_is_playing", lambda: next(playing))
    conn = mock.Mock()
    monkeypatch.setattr("fl_studio_mcp.utils.connection.get_connection", lambda: conn)
    wav = tmp_path / "drums_4.wav"
    monkeypatch.setattr(flow.eb, "newest_sliced_audio", lambda t0: wav)
    monkeypatch.setattr(flow.eb, "wav_regions", lambda p: [{"name": "hat 1", "start": 1}])
    r = flow.send_to_channel(expected=1)
    assert r["ok"] and r["region_count"] == 1
    assert clicks[0] == (1083, 408, {"button": "right"})   # only after the real hint
    assert clicks[1][:2] == (515, 356)                      # Edison's stop
    conn.send_command.assert_called_once_with("transport.stop", {})


def test_a_picker_list_row_is_not_the_edison_logo(monkeypatch):
    """2026-10-02: 'Edison' in the plugin picker's list (≈10 px text) made
    open() report success while the picker was still open."""
    monkeypatch.setattr(flow.cm, "window_by_name", lambda n: None)
    monkeypatch.setattr(flow, "uncover", lambda *a: False)
    assert flow.locate([Box(659, 155, 32, 10, "Edison")]) is None
    assert flow.locate([Box(1046, 370, 60, 19, "edison")]) is not None
    monkeypatch.setattr(flow.cm, "window_by_name", lambda n: (620, 60, 520, 900))
    assert flow.locate([Box(1046, 370, 60, 19, "edison")]) is None    # picker open


def test_a_covered_edison_is_uncovered_once_and_found(monkeypatch):
    """2026-10-02: a maximized mixer hid Edison during load_song."""
    monkeypatch.setattr(flow.cm, "window_by_name", lambda n: None)
    calls = []
    monkeypatch.setattr(flow, "uncover", lambda *a: calls.append(1) or True)
    monkeypatch.setattr(flow, "_scan", lambda: [Box(400, 340, 90, 10, "Edison (Insert 9)")])
    got = flow.locate([Box(10, 10, 50, 10, "Mixer - Insert 9")])
    assert calls == [1] and got["anchor"] == "Edison (Insert 9)"

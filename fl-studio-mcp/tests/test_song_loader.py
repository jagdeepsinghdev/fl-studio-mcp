"""fl_preset(action="load_song") — every FL/UI/subprocess step mocked."""

from __future__ import annotations

import json
from unittest import mock

from fl_studio_mcp.tools import mixer_v2
from fl_studio_mcp.tools import preset_v2 as pv
from fl_studio_mcp.utils import song_loader as sl

FILES = {"beat": "b.json", "melody": "m.json", "bass": "bs.json",
         "bass_sample": "bss.json", "bass_sample_wav": "x-bass-25.wav"}


def _song(tmp_path, keys=tuple(FILES), **extra):
    for k in keys:
        (tmp_path / FILES[k]).write_text("{}")
    (tmp_path / "song.json").write_text(json.dumps({"bpm": 93.75, **{k: FILES[k] for k in keys}, **extra}))
    return tmp_path


def _wire(monkeypatch, sample_ok=True):
    calls = []
    conn = mock.Mock()
    monkeypatch.setattr(sl, "_ensure_channel", lambda c, name, plugin, log: (
        calls.append(("channel", name, plugin)) or {"ok": True, "index": 9 if "Bass" in name else 8,
                                                     "name": name, "mixer_track": 7}))
    from fl_studio_mcp.utils import sampler_load
    monkeypatch.setattr(sampler_load, "load_sample", lambda c, idx, wav, label="", log=None: (
        calls.append(("sample", idx, wav)) or {"ok": sample_ok, "error": None if sample_ok else "send failed"}))
    monkeypatch.setattr(pv, "load_beat", lambda **k: (calls.append(("beat", k["path"])) or {"ok": True}))
    monkeypatch.setattr(pv, "load_melody", lambda **k: (
        calls.append(("notes", k["channel_index"], k["path"])) or {"ok": True, "notes_queued": 3, "script_ran": True}))
    monkeypatch.setattr(mixer_v2, "fix_clipping", lambda c, t, db: (calls.append(("level", t, db)) or {"changed": False}))
    monkeypatch.setattr(sl.time, "sleep", lambda s: None)
    monkeypatch.setattr(sl, "_clear_editors", lambda: calls.append(("clear",)))
    return conn, calls


def test_whole_song_in_order_with_the_original_bass_sample(tmp_path, monkeypatch):
    d = _song(tmp_path)
    conn, calls = _wire(monkeypatch)
    r = sl.load_song(str(d), label="Demo", conn=conn, log=lambda m: None)
    assert r["ok"] and r["steps"]["bass"]["source"] == "original sample"
    conn.send_command.assert_any_call("transport.setBPM", {"bpm": 93.75})
    f = lambda k: str(d / FILES[k])  # noqa: E731
    assert calls == [("beat", f("beat")),
                     ("channel", "Demo Melody", "FLEX"), ("clear",), ("notes", 8, f("melody")),
                     ("channel", "Demo Bass", "Sampler"), ("sample", 9, f("bass_sample_wav")),
                     ("clear",), ("notes", 9, f("bass_sample")), ("level", 0, -1.0)]


def test_label_from_the_manifest_then_the_folder(tmp_path, monkeypatch):
    conn, calls = _wire(monkeypatch)
    r = sl.load_song(str(_song(tmp_path, ("melody",), label="Hook")), conn=conn, log=lambda m: None)
    assert r["label"] == "Hook" and ("channel", "Hook Melody", "FLEX") in calls


def test_no_sample_falls_back_to_a_flex_bass(tmp_path, monkeypatch):
    d = _song(tmp_path, ("beat", "melody", "bass"))
    conn, calls = _wire(monkeypatch)
    r = sl.load_song(str(d), label="S", conn=conn, log=lambda m: None)
    assert r["ok"] and r["steps"]["bass"]["source"] == "FLEX (no sample)"
    assert ("channel", "S Bass", "FLEX") in calls and ("notes", 9, str(d / "bs.json")) in calls


def test_a_failed_sample_send_fails_the_song_and_writes_no_bass_notes(tmp_path, monkeypatch):
    d = _song(tmp_path)
    conn, calls = _wire(monkeypatch, sample_ok=False)
    r = sl.load_song(str(d), label="S", conn=conn, log=lambda m: None)
    assert r["ok"] is False and r["steps"]["bass"]["error"] == "send failed"
    assert ("notes", 9, str(d / "bss.json")) not in calls


def test_missing_manifest(tmp_path):
    r = sl.load_song(str(tmp_path), conn=mock.Mock(), log=lambda m: None)
    assert r["ok"] is False and "song.json" in r["error"]


def test_manifest_with_a_missing_file_is_refused_before_touching_fl(tmp_path):
    (tmp_path / "song.json").write_text(json.dumps({"melody": "gone.json"}))
    conn = mock.Mock()
    r = sl.load_song(str(tmp_path), conn=conn, log=lambda m: None)
    assert r["ok"] is False and "gone.json" in r["error"] and not conn.send_command.called


def test_manifest_with_no_parts_is_refused(tmp_path):
    (tmp_path / "song.json").write_text(json.dumps({"bpm": 120}))
    assert "none of beat" in sl.load_song(str(tmp_path), conn=mock.Mock(), log=lambda m: None)["error"]


def test_dispatch_requires_song_dir():
    assert "song_dir" in pv._preset_dispatch("load_song")["error"]


def test_notes_retry_once_after_reselecting_the_script(monkeypatch):
    from fl_studio_mcp.tools import select_script
    results = iter([{"ok": False, "script_ran": False, "error": "did not run"},
                    {"ok": True, "script_ran": True, "notes_queued": 3}])
    calls = []
    monkeypatch.setattr(pv, "load_melody", lambda **k: (calls.append("load") or next(results)))
    monkeypatch.setattr(select_script, "fl_select_script", lambda channel_index: calls.append(("select", channel_index)))
    monkeypatch.setattr(sl, "_clear_editors", lambda: calls.append("clear"))
    r = sl._notes_with_retry(pv, "/p/m.json", 2, 7, log=lambda m: None)
    assert r["ok"] and calls == ["load", "clear", ("select", 7), "load"]

"""fx delete via FL's slot menu (utils/remove_effect.py); every UI call mocked."""

from __future__ import annotations

from unittest import mock

import pytest

from fl_studio_mcp.utils import remove_effect as re_
from fl_studio_mcp.utils.custom_menu import Box


@pytest.fixture
def ui(monkeypatch):
    clicks = []
    monkeypatch.setattr(re_.cm, "require_fl_front", lambda: True)
    monkeypatch.setattr(re_.cm, "_click", lambda x, y, **k: clicks.append((x, y)))
    monkeypatch.setattr(re_, "select_track", lambda conn, t: True)
    monkeypatch.setattr(re_.time, "sleep", lambda s: None)
    # 2026-10-05 contract: ui_guard readiness first, then the track's real name
    monkeypatch.setattr("fl_studio_mcp.utils.ui_guard.ensure_ready",
                        lambda conn, **k: {"ready": True, "blockers": [], "front": None})
    monkeypatch.setattr(re_, "_exec", lambda conn, code: "Insert 6")
    return clicks


def _slots(seq):
    it = iter(seq)
    return lambda conn, t: next(it)


def test_wrong_plugin_in_the_slot_clicks_nothing(ui, monkeypatch):
    monkeypatch.setattr(re_, "track_slots", _slots([["Fruity Reeverb 2"] + [""] * 9]))
    r = re_.remove_effect(6, 0, expect="Fruity Limiter", conn=object(), log=lambda m: None)
    assert r["ok"] is False and "nothing was deleted" in r["error"]
    assert ui == []


def test_unconfirmed_slot_arrow_clicks_nothing(ui, monkeypatch):
    monkeypatch.setattr(re_, "track_slots", _slots([["Fruity Limiter"] + [""] * 9]))
    monkeypatch.setattr(re_, "_slot_row", lambda name, t, *a: (
        Box(1697, 120, 82, 10, "Mixer - Insert 6"), Box(1718, 177, 99, 17, "Fruity Limiter")))
    monkeypatch.setattr(re_.cm, "hint_at", lambda x, y: "Mix level: 100%")
    r = re_.remove_effect(6, 0, conn=object(), log=lambda m: None)
    assert r["ok"] is False and "nothing was clicked" in r["error"] and ui == []


def test_full_path_is_verified_by_the_read_back(ui, monkeypatch):
    monkeypatch.setattr(re_, "track_slots", _slots([["Fruity Limiter"] + [""] * 9, [""] * 10]))
    monkeypatch.setattr(re_, "_slot_row", lambda name, t, *a: (
        Box(1697, 120, 82, 10, "Mixer - Insert 6"), Box(1701, 177, 99, 17, "- Fruity Limiter")))
    # 2026-10-05 contract: ui_guard readiness first, then the track's real name
    monkeypatch.setattr("fl_studio_mcp.utils.ui_guard.ensure_ready",
                        lambda conn, **k: {"ready": True, "blockers": [], "front": None})
    monkeypatch.setattr(re_, "_exec", lambda conn, code: "Insert 6")
    # only the real arrow (x 1705-1712, live 1709) answers with the slot hint
    monkeypatch.setattr(re_.cm, "hint_at", lambda x, y:
                        "FX slot 1 options" if 1705 <= x <= 1712 else "Mix level: 100%")
    monkeypatch.setattr(re_.cm, "ocr_region", lambda *a, **k: [Box(1715, 224, 39, 11, "Delete...")])
    monkeypatch.setattr(re_.cm, "shot", lambda *a: "/x.png")
    monkeypatch.setattr(re_.cm, "ocr_boxes", lambda p: [
        Box(885, 455, 220, 12, "The selected plugin is about to be deleted."),
        Box(1007, 582, 16, 11, "Ok")])
    r = re_.remove_effect(6, 0, expect="Fruity Limiter", conn=object(), log=lambda m: None)
    assert r["ok"] and r["removed"] == "Fruity Limiter"
    (ax, ay), *rest = ui
    assert 1705 <= ax <= 1712 and ay == 185                 # the arrow
    assert rest == [(1734, 229), (1015, 587)]               # Delete..., Ok


def test_roll_notes_clear_is_withdrawn_when_the_script_did_not_run(monkeypatch):
    from fl_studio_mcp.tools import delete
    from fl_studio_mcp.utils import roll_session
    writes = []
    monkeypatch.setattr("fl_studio_mcp.tools.piano_roll._write_request", writes.append)
    monkeypatch.setattr("fl_studio_mcp.tools.piano_roll.trigger_fl_studio", lambda: True)
    monkeypatch.setattr(roll_session, "ran_since", lambda before: False)
    monkeypatch.setattr(delete, "get_connection", lambda: mock.Mock())
    mcp = mock.Mock()
    tools = {}
    mcp.tool = lambda *a, **k: (lambda f: tools.setdefault(f.__name__, f))
    delete.register_delete_tools(mcp)
    r = tools["fl_delete"](target="roll_notes")
    assert r["ok"] is False and "withdrawn" in r["error"]
    assert writes == [{"action": "clear"}, []]


def test_master_panel_title(monkeypatch):
    monkeypatch.setattr(re_.cm, "shot", lambda *a: "/x.png")
    monkeypatch.setattr(re_.cm, "ocr_boxes", lambda p: [
        Box(1698, 120, 70, 10, "Mixer - Master"),
        Box(1701, 460, 99, 17, "- Emphasizer"),
        Box(1698, 600, 70, 10, "Mixer - Insert 10")])
    title, row = re_._slot_row("Emphasizer", 0)
    assert title.text == "Mixer - Master" and row.text == "- Emphasizer"
    title, _ = re_._slot_row("x", 1)             # "Insert 1" must not match "Insert 10"
    assert title is None


def test_add_effect_reports_plugin_that_landed_on_wrong_track(monkeypatch):
    """2026-10-03 live: asked Insert 8, Reeverb 2 landed on Insert 7 (the
    panel's track). add_effect must name the stray, not just 'nothing'."""
    from fl_studio_mcp.utils import add_effect as ae
    slots = {7: ["Fruity Compressor"] + [""] * 9, 8: [""] * 10}
    monkeypatch.setattr(ae.cm, "require_fl_front", lambda: True)
    monkeypatch.setattr(ae, "track_slots", lambda conn, t: list(slots[t]))
    monkeypatch.setattr(ae, "selected_track", lambda conn: 7)
    monkeypatch.setattr(ae, "select_track", lambda conn, t: True)
    monkeypatch.setattr(ae.time, "sleep", lambda s: None)

    def pick(name, log, **kw):          # conn= since the index route (2026-10-05)
        slots[7][1] = "Fruity Reeverb 2"   # drifted onto the panel's track
        return True
    monkeypatch.setattr(ae, "pick_from_picker", pick)
    r = ae.add_effect(8, "Fruity Reeverb 2", conn=object(), log=lambda m: None)
    assert r["ok"] is False
    assert r["stray"] == {"track": 7, "slot": 1, "plugin": "Fruity Reeverb 2"}
    assert "WRONG TRACK" in r["error"]


def test_slot_row_matches_a_renamed_track(monkeypatch):
    """Live 2026-10-05: track 12 renamed 'Vocal' -> panel title 'Mixer - Vocal';
    the old 'Insert N' match missed it and nothing could be deleted."""
    monkeypatch.setattr(re_.cm, "shot", lambda *a: "/x.png")
    monkeypatch.setattr(re_.cm, "ocr_boxes", lambda p: [
        Box(1469, 180, 60, 10, "Mixer - Vocal"), Box(1487, 405, 80, 10, "Fruity Reeverb 2")])
    title, row = re_._slot_row("Fruity Reeverb 2", 12, "Vocal")
    assert title is not None and row is not None and row.text == "Fruity Reeverb 2"
    assert re_._slot_row("Fruity Reeverb 2", 12, "Hall Reverb") == (None, None)


def test_names_match_tolerates_ocr_slips():
    from fl_studio_mcp.utils.add_effect import names_match
    assert names_match("Hall Reverh", "Hall Reverb")          # live OCR slip
    assert names_match("Mixer-Vocal".split("-")[1], "Vocal")
    assert not names_match("Vocal", "Hall Reverb")
    assert not names_match("Insert 1", "Insert 7")             # digits must not blur


def test_names_match_never_blurs_numbers():
    from fl_studio_mcp.utils.add_effect import names_match
    assert not names_match("Insert 1", "Insert 10")
    assert not names_match("Delay 1/4", "Delay 1/8")


def test_slot_row_picks_the_nth_same_named_plugin(monkeypatch):
    """Two 'Fruity Limiter' slots: deleting the 2nd must target the 2nd row."""
    monkeypatch.setattr(re_.cm, "shot", lambda *a: "/x.png")
    monkeypatch.setattr(re_.cm, "ocr_boxes", lambda p: [
        Box(1700, 90, 80, 10, "Mixer - Vocal 2"),
        Box(1718, 280, 90, 12, "Fruity Limiter"),
        Box(1718, 343, 60, 12, "Maximus"),
        Box(1718, 375, 90, 12, "Fruity Limiter")])
    _, first = re_._slot_row("Fruity Limiter", 6, "Vocal 2", 0)
    _, second = re_._slot_row("Fruity Limiter", 6, "Vocal 2", 1)
    assert first.y == 280 and second.y == 375
    assert re_._slot_row("Fruity Limiter", 6, "Vocal 2", 2) == (re_._slot_row("x", 6, "Vocal 2")[0], None)

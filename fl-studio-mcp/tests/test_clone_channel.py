"""fl_channel clone via FL's channel menu — every UI call mocked."""

from __future__ import annotations

import sys
from unittest import mock

import pytest

from fl_studio_mcp.tools import channel_v2
from fl_studio_mcp.utils import clone_channel as cc
from fl_studio_mcp.utils.custom_menu import Box


def test_rack_labels_are_shortened_with_dots():
    assert cc.rack_label_matches("Sapphi..Melody", "Sapphire Melody")
    assert cc.rack_label_matches("808 Kick", "808 kick")
    assert not cc.rack_label_matches("Sapphi..Melody", "Sapphire Bass")
    assert not cc.rack_label_matches("808 Clap", "808 Kick")


class _Conn:
    def __init__(self, chans):
        self.chans = chans
        self.calls = []

    def send_command(self, action, params=None, **kw):
        self.calls.append((action, params))
        if action == "channels.getAll":
            return {"channels": list(self.chans)}
        if action == "channels.setName":
            for c in self.chans:
                if c["index"] == params["index"]:
                    c["name"] = params["name"]
        return {"success": True}


@pytest.fixture
def ui(monkeypatch):
    monkeypatch.setattr(cc.cm, "require_fl_front", lambda: True)
    monkeypatch.setattr(cc.fp, "clear_plugins", lambda: True)
    monkeypatch.setattr(cc.fp, "set_visible", lambda c, s: None)
    monkeypatch.setattr(cc.cm, "shot", lambda *a: "/x.png")
    monkeypatch.setattr(cc.time, "sleep", lambda s: None)


def test_clone_is_found_where_fl_inserts_it_and_nothing_else_is_renamed(ui, monkeypatch):
    """FL inserts the clone right after its source and shifts the rest
    (2026-10-02: the old index-diff renamed the shifted last channel)."""
    conn = _Conn([{"index": 0, "name": "808 Kick"}, {"index": 1, "name": "Sapphire Melody"},
                  {"index": 2, "name": "Werq Bass"}])
    monkeypatch.setattr(cc.cm, "ocr_boxes", lambda p: [Box(327, 318, 74, 14, "Sapphi..Melody")])
    seen = {}

    def cascade(x, y, chain, region=None, log=None, **k):
        seen.update(x=x, y=y, chain=chain)
        conn.chans[:] = [{"index": 0, "name": "808 Kick"}, {"index": 1, "name": "Sapphire Melody"},
                         {"index": 2, "name": "Sapphire Melody #2"}, {"index": 3, "name": "Werq Bass"}]
        return [Box(422, 521, 28, 10, "Clone")]

    monkeypatch.setattr(cc.cm, "menu_cascade", cascade)
    r = cc.clone_channel(conn, 1, "Melody B", log=lambda m: None)
    assert r["ok"] and r["index"] == 2 and r["name"] == "Melody B"
    assert [c["name"] for c in conn.chans] == ["808 Kick", "Sapphire Melody", "Melody B", "Werq Bass"]
    assert seen["chain"] == [["Clone"]] and (seen["x"], seen["y"]) == (364, 325)


def test_no_new_channel_is_a_failure(ui, monkeypatch):
    conn = _Conn([{"index": 0, "name": "808 Kick"}])
    monkeypatch.setattr(cc.cm, "ocr_boxes", lambda p: [Box(344, 169, 43, 11, "808 Kick")])
    monkeypatch.setattr(cc.cm, "menu_cascade", lambda *a, **k: [Box(0, 0, 1, 1, "Clone")])
    r = cc.clone_channel(conn, 0, log=lambda m: None)
    assert r["ok"] is False and "did not appear" in r["error"]


def test_duplicate_names_refuse_before_clicking(ui, monkeypatch):
    conn = _Conn([{"index": 0, "name": "Kick"}, {"index": 1, "name": "Kick"}])
    clicked = mock.Mock()
    monkeypatch.setattr(cc.cm, "menu_cascade", clicked)
    r = cc.clone_channel(conn, 0, log=lambda m: None)
    assert r["ok"] is False and "rename one first" in r["error"]
    clicked.assert_not_called()


def test_tool_routes_clone_server_side(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(cc, "clone_channel", lambda c, i, n, log=None: {"ok": True, "index": 9, "name": n})
    r = channel_v2.fl_channel("clone", conn=object(), index=1, name="Copy")
    assert r["success"] and r["index"] == 9 and r["name"] == "Copy"


def _rack_then_dialog(conn, after):
    """First OCR = the rack, later OCRs = FL's Confirm dialog."""
    shots = iter([[Box(334, 349, 62, 12, "Astro Copy 2")]])

    def ocr(p):
        return next(shots, [Box(880, 456, 228, 12, "The selected channel is about to be deleted."),
                            Box(1013, 582, 12, 10, "Ok"), Box(1074, 582, 30, 10, "Cancel")])
    return ocr


def test_delete_clicks_ok_under_the_confirm_text_and_verifies(ui, monkeypatch):
    conn = _Conn([{"index": 5, "name": "Astro Copy"}, {"index": 6, "name": "Astro Copy 2"}])
    monkeypatch.setattr(cc.cm, "ocr_boxes", _rack_then_dialog(conn, None))
    monkeypatch.setattr(cc.cm, "menu_cascade", lambda *a, **k: [Box(440, 605, 40, 10, "Delete..")])
    clicks = []

    def click(x, y, **k):
        clicks.append((x, y))
        conn.chans[:] = [{"index": 5, "name": "Astro Copy"}]
    monkeypatch.setattr(cc.cm, "_click", click)
    r = cc.delete_channel(conn, 6, "Astro Copy 2", log=lambda m: None)
    assert r["ok"] and r["channel_count"] == 1
    assert clicks == [(1019, 587)]


def test_delete_refuses_a_wrong_name_before_clicking(ui, monkeypatch):
    conn = _Conn([{"index": 5, "name": "Astro Copy"}])
    clicked = mock.Mock()
    monkeypatch.setattr(cc.cm, "menu_cascade", clicked)
    r = cc.delete_channel(conn, 5, "Werq Bass", log=lambda m: None)
    assert r["ok"] is False and "nothing was deleted" in r["error"]
    clicked.assert_not_called()


def test_delete_without_the_confirm_text_never_clicks_ok(ui, monkeypatch):
    conn = _Conn([{"index": 6, "name": "Astro Copy 2"}])
    shots = iter([[Box(334, 349, 62, 12, "Astro Copy 2")]])
    monkeypatch.setattr(cc.cm, "ocr_boxes", lambda p: next(shots, [Box(500, 500, 12, 10, "Ok")]))
    monkeypatch.setattr(cc.cm, "menu_cascade", lambda *a, **k: [Box(0, 0, 1, 1, "Delete..")])
    monkeypatch.setattr(cc.cm, "dismiss_menu", lambda: None)
    click = mock.Mock()
    monkeypatch.setattr(cc.cm, "_click", click)
    r = cc.delete_channel(conn, 6, "Astro Copy 2", log=lambda m: None)
    assert r["ok"] is False and "did not appear" in r["error"]
    click.assert_not_called()

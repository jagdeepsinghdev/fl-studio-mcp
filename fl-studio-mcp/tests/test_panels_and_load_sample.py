"""fl_ui_screen panels/set_panels + fl_channel load_sample — all FL/UI mocked."""

from __future__ import annotations

import sys

from fl_studio_mcp.tools import channel_v2, ui_screen_v2
from fl_studio_mcp.utils import fl_panels as fp
from fl_studio_mcp.utils import sampler_load


def test_panels_reads_the_five_panels(monkeypatch):
    monkeypatch.setattr(fp, "visible", lambda c: {0: False, 1: True, 2: False, 3: True, 4: True})
    r = ui_screen_v2.fl_ui_screen("ui", "panels", conn=object())
    assert r["success"] and r["result"] == {"mixer": False, "channel_rack": True,
                                            "playlist": False, "piano_roll": True, "browser": True}


def test_set_panels_sets_then_reads_back(monkeypatch):
    seen = {}
    monkeypatch.setattr(fp, "set_visible", lambda c, st: seen.update(st))
    monkeypatch.setattr(fp, "visible", lambda c: {0: False, 1: True, 2: False, 3: False, 4: True})
    r = ui_screen_v2.fl_ui_screen("ui", "set_panels", [{"piano_roll": False, "mixer": False}], conn=object())
    assert seen == {fp.PIANO_ROLL: False, fp.MIXER: False}
    assert r["result"]["piano_roll"] is False


def test_set_panels_rejects_unknown_panels():
    r = ui_screen_v2.fl_ui_screen("ui", "set_panels", [{"drums": True}], conn=object())
    assert r["success"] is False and "unknown" in r["error"]


def test_load_sample_routes_to_the_sampler_loader(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    seen = {}
    monkeypatch.setattr(sampler_load, "load_sample", lambda c, idx, path, label="", log=None: (
        seen.update(idx=idx, path=path, label=label) or {"ok": True, "channel": idx, "file": path}))
    r = channel_v2.fl_channel("load_sample", conn=object(), index=8, path="/a/b.wav", name="Werq Bass")
    assert r["success"] and seen == {"idx": 8, "path": "/a/b.wav", "label": "Werq Bass"}


def test_load_sample_validates_before_touching_fl():
    r = channel_v2.fl_channel("load_sample", conn=object(), index=8)
    assert r["success"] is False and "path" in r["error"]

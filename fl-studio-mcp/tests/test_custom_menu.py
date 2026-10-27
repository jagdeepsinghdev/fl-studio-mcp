"""Tests for the screen/mouse primitives (utils/custom_menu.py) and the
scripts/screen.py CLI. Every OS call (cliclick, screencapture, sips,
osascript, OCR) is mocked: nothing touches the real screen or mouse."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from fl_studio_mcp.utils import custom_menu as cm
from fl_studio_mcp.utils.custom_menu import Box


def _b(text, x=10, y=10):
    return Box(x, y, 40, 12, text)


# ---------------------------------------------------------------- matching -

def test_exact_match_beats_substring():
    boxes = [_b("Edit last script: OMCP-Workbench"), _b("Workbench >")]
    assert cm.match_box(boxes, "Workbench").text == "Workbench >"


def test_substring_never_hits_edit_rows():
    boxes = [_b("Edit last script: OMCP-Workbench")]
    assert cm.match_box(boxes, "Workbench") is None


def test_ocr_o_and_zero_are_equal():
    assert cm.match_box([_b("OMCP-Workbench")], "0MCP-Workbench") is not None


def test_short_names_need_an_exact_match():
    assert cm.match_box([_b("Snapshot")], "Snap") is None      # len <= 4: exact only
    assert cm.match_box([_b("Run script ›")], ["Run script"]) is not None


# ---------------------------------------------------------- region mapping -

def test_ocr_region_maps_boxes_back_to_screen(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        out = "pixelWidth: 100\n" if cmd[:2] == ["sips", "-g"] else ""
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    monkeypatch.setattr(cm.subprocess, "run", fake_run)
    # OCR of the 3x image: a box at (30, 60) px, 60x30 -> screen /3 + origin
    monkeypatch.setattr(cm, "ocr_boxes", lambda p: [Box(30, 60, 60, 30, "OK")])
    [b] = cm.ocr_region(700, 470, 100, 50, scale=3)
    assert (b.x, b.y, b.w, b.h) == (710, 490, 20, 10)
    assert calls[0][:4] == ["screencapture", "-x", "-R", "700,470,100,50"]
    assert calls[2][:4] == ["sips", "-z", "150", "300"]


# ----------------------------------------------------------------- cascade -

def test_menu_cascade_clicks_each_level(monkeypatch):
    levels = iter([[_b("Tools", 100, 200)], [_b("Run script", 300, 220)]])
    clicks = []
    monkeypatch.setattr(cm, "ocr_region", lambda *a, **k: next(levels))
    monkeypatch.setattr(cm, "_click", lambda x, y, **k: clicks.append((x, y, k)))
    monkeypatch.setattr(cm.time, "sleep", lambda s: None)
    got = cm.menu_cascade(50, 60, [["Tools"], ["Run script"]], log=lambda m: None)
    assert [b.text for b in got] == ["Tools", "Run script"]
    assert clicks[0] == (50, 60, {"button": "right"})       # opens the menu
    assert clicks[1][:2] == (120, 206) and clicks[2][:2] == (320, 226)


def test_menu_cascade_failure_dismisses_safely(monkeypatch):
    clicks = []
    monkeypatch.setattr(cm, "ocr_region", lambda *a, **k: [_b("Format")])
    monkeypatch.setattr(cm, "_click", lambda x, y, **k: clicks.append((x, y)))
    monkeypatch.setattr(cm, "shot", lambda p="": p)
    monkeypatch.setattr(cm.time, "sleep", lambda s: None)
    assert cm.menu_cascade(50, 60, [["Tools"]], log=lambda m: None) is None
    assert clicks[-1] == cm.SAFE_DISMISS                     # never a title bar


# --------------------------------------------------------------------- CLI -

def _load_cli():
    path = Path(__file__).resolve().parent.parent / "scripts" / "screen.py"
    spec = importlib.util.spec_from_file_location("screen_cli", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_refuses_to_click_when_fl_is_not_front(monkeypatch):
    cli = _load_cli()
    monkeypatch.setattr(cli.cm, "require_fl_front", lambda: False)
    monkeypatch.setattr(cli.cm, "frontmost_app", lambda: "Google Chrome")
    clicked = mock.Mock()
    monkeypatch.setattr(cli.cm, "_click", clicked)
    with pytest.raises(SystemExit, match="Chrome"):
        cli.main(["click", "10", "20"])
    clicked.assert_not_called()


def test_cli_click_text_dry_run_does_not_click(monkeypatch, capsys):
    cli = _load_cli()
    monkeypatch.setattr(cli.cm, "ocr_region", lambda *a, **k: [_b("OK", 1163, 608)])
    clicked = mock.Mock()
    monkeypatch.setattr(cli.cm, "_click", clicked)
    cli.main(["click-text", "OK", "--region", "700,470,520,170", "--dry-run"])
    clicked.assert_not_called()
    assert "(1183,614)" in capsys.readouterr().out

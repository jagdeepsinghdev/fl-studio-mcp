"""Tests for fl_select_script (automates the ComposeWithLLM selection, §0).

These mock the OS-level helpers (cliclick, osascript, screencapture, pgrep)
so the tests are deterministic and never touch a real FL process or display.
They cover:
  * the window-frame -> coordinate scaling math (machine-independence),
  * the "never blindly toggle the roll" guard (_ensure_roll_open),
  * the fraction parser and script-row indexing,
  * parameter validation (unknown script, out-of-range channel).
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from fl_studio_mcp.tools import select_script as ss


class _Base(unittest.TestCase):
    """Common: make the tool pretend macOS and stub the OS shims."""

    def setUp(self):
        # macOS gate + a known 1920x993 window at origin (0,30)
        self.patches = [
            mock.patch.object(ss, "platform"),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        ss.platform.system = lambda: "Darwin"
        self.frame = (0, 30, 1920, 993)
        # stub the low-level OS shims so no real subprocess runs
        self.mocks = []
        for name in ("_run", "_osascript", "_click", "_move",
                     "_capture_to", "_crop_to_ppm", "_read_ppm",
                     "_window_frame", "_fl_running", "_activate_fl",
                     "_roll_open", "_roll_focused", "_menu_open",
                     "_locate_wrench", "_verify_selection", "_send_keyseq",
                     "_wrench_from_title", "_open_roll_via_menu"):
            m = mock.patch.object(ss, name)
            self.mocks.append(m)
        for m in self.mocks:
            m.start()
            self.addCleanup(m.stop)   # (was leaking into every later test)
        ss._run.return_value = (0, "", "")
        ss._osascript.return_value = (0, "", "")
        ss._click.return_value = None
        ss._move.return_value = None
        ss._capture_to.return_value = True
        ss._window_frame.return_value = self.frame
        ss._fl_running.return_value = True
        ss._roll_open.return_value = True
        ss._roll_focused.return_value = True
        ss._menu_open.return_value = True
        ss._locate_wrench.return_value = None
        # OCR + hover never run in tests: default = wrench confirmed at the
        # docked-layout spot the old fraction pointed at
        ss._wrench_from_title.return_value = (1041, 214)
        ss._open_roll_via_menu.return_value = (True, "mocked")
        ss._verify_selection.return_value = (False, "mocked (off by default)")
        ss._send_keyseq.return_value = {"success": True,
                                       "executed": ["up"] * 6 + ["enter"]}


class TestFracAndRow(_Base):
    def test_frac(self):
        self.assertEqual(ss._frac("1041/1920"), 1041 / 1920)
        self.assertEqual(ss._frac("0.5"), 0.5)
        self.assertEqual(ss._frac(0.5), 0.5)
        self.assertEqual(ss._frac("bad/0"), 0.0)  # zero division guarded
        self.assertEqual(ss._frac("garbage"), 0.0)

    def test_row_index(self):
        # 2026-10-02: renamed 0ComposeWithLLM (sorts first in the merged list)
        self.assertEqual(ss._script_row_index("0ComposeWithLLM"), 0)
        self.assertEqual(ss._script_row_index("ComposeWithLLM"), 0)  # legacy alias
        self.assertEqual(ss._script_row_index("Arpeggiator"), 1)
        self.assertEqual(ss._script_row_index("UnknownScript"), 0)  # -> our script slot


class TestCoordinateScaling(_Base):
    def test_window_relative_coordinates(self):
        # 1920x993 window at origin: wrench fx=1041/1920 -> x=1041;
        # toolbar fy=184/963 of 963 height from top=30 -> 30+184=214.
        r = ss.fl_select_script(channel_index=0, method="click")
        self.assertTrue(r["success"])
        self.assertEqual(r["wrench_x"], 1041)
        self.assertEqual(r["toolbar_y"], 214)
        # 0ComposeWithLLM (index 0 = first script row): anchor row (2nd script
        # item) is 315; first script row = 315-30 = 285; col fx=1302/1920 -> 1302
        self.assertEqual(r["script_click"]["x"], 1302)
        self.assertEqual(r["script_click"]["y"], 285)

    def test_explicit_coordinates_win_over_scaling(self):
        r = ss.fl_select_script(channel_index=0, method="click", wrench_x=500,
                                script_x=600, script_y=700)
        self.assertEqual(r["wrench_x"], 500)
        self.assertEqual(r["script_click"]["x"], 600)
        self.assertEqual(r["script_click"]["y"], 700)

    def test_scaled_window_is_proportional(self):
        # A half-size window should yield proportional (smaller) coordinates.
        self.frame = (0, 30, 960, 481)
        ss._window_frame.return_value = self.frame
        # the wrench now comes from the screen (title + hint), not a fraction
        ss._wrench_from_title.return_value = (520, 122)
        r = ss.fl_select_script(channel_index=0, method="click")
        self.assertEqual((r["wrench_x"], r["wrench_y"]), (520, 122))
        self.assertTrue(r["script_click"]["y"] < 315)  # smaller window -> smaller y


class TestWrenchProbe(_Base):
    """v10.4d: the wrench click is its own roll detector (isInPopupMenu)."""

    def test_menu_opens_first_try_no_toggle(self):
        ss._menu_open.return_value = True
        with mock.patch.object(ss, "_open_roll_via_menu") as om:
            r = ss.fl_select_script(channel_index=0, method="keys")
            om.assert_not_called()
        self.assertTrue(r["success"])
        self.assertIs(r["menu_open"], True)

    def test_menu_miss_opens_roll_then_retries(self):
        # first wrench click opens nothing (roll closed); after the View
        # toggle the retry opens the menu
        ss._menu_open.side_effect = [False, True]
        with mock.patch.object(ss, "_open_roll_via_menu") as om:
            om.return_value = (True, "toggled View > Piano roll")
            r = ss.fl_select_script(channel_index=0, method="keys")
            om.assert_called_once()
        self.assertTrue(r["success"])
        ss._send_keyseq.assert_called_once_with(["up"] * 6 + ["enter"])

    def test_double_miss_fails_loudly_and_sends_no_keys(self):
        ss._menu_open.side_effect = [False, False]
        ss._send_keyseq.reset_mock()
        with mock.patch.object(ss, "_open_roll_via_menu") as om:
            om.return_value = (True, "toggled View > Piano roll")
            r = ss.fl_select_script(channel_index=0, method="keys")
        self.assertFalse(r["success"])
        self.assertIn("NOT sent", r["error"])
        ss._send_keyseq.assert_not_called()

    def test_out_of_range_channel_is_soft(self):
        # selectOne returns False for a bad index; the tool should continue,
        # not raise (it proceeds to whatever roll is current).
        with mock.patch("fl_studio_mcp.utils.connection.get_connection") as gc:
            gc.return_value = mock.Mock(send_command=lambda *a, **k: {"success": False, "error": "Index out of range"})
            r = ss.fl_select_script(channel_index=99)
            self.assertTrue(r["success"])
            self.assertTrue(any("out of range" in s for s in r["setup"]["steps"]))


class TestGating(_Base):
    def test_not_darwin_is_refused(self):
        ss.platform.system = lambda: "Linux"
        r = ss.fl_select_script(channel_index=0)
        self.assertFalse(r["success"])
        self.assertIn("macOS-only", r["error"])

    def test_fl_not_running(self):
        ss._fl_running.return_value = False
        r = ss.fl_select_script(channel_index=0)
        self.assertFalse(r["success"])
        self.assertIn("not running", r["error"])

    def test_verify_is_opt_in(self):
        # verify defaults to False -> _verify_selection must not be called
        ss._verify_selection.return_value = (True, "ok")
        ss.fl_select_script(channel_index=0, method="click")
        ss._verify_selection.assert_not_called()
        # verify=True -> called
        ss._verify_selection.reset_mock()
        ss.fl_select_script(channel_index=0, method="click", verify=True)
        ss._verify_selection.assert_called_once()


class TestKeySeqPath(_Base):
    """v10.4d: the default keys-mode flow — one controller trip, no row click."""

    def test_keys_commits_and_skips_row_click(self):
        ss._send_keyseq.return_value = {"success": True,
                                        "executed": ["up"] * 6 + ["enter"]}
        r = ss.fl_select_script(channel_index=0)  # method defaults to 'keys'
        self.assertTrue(r["success"])
        self.assertEqual(r["script_click"].get("mode"), "keys")
        ss._send_keyseq.assert_called_once_with(["up"] * 6 + ["enter"])
        # the row click must NOT have happened (no click at the row's y)
        row_clicks = [c for c in ss._click.call_args_list
                      if len(c.args) == 2 and c.args[1] == 285]
        self.assertEqual(row_clicks, [])

    def test_keyseq_failure_falls_back_to_click(self):
        ss._send_keyseq.return_value = {"success": False,
                                        "error": "Unknown action"}
        r = ss.fl_select_script(channel_index=0)
        self.assertTrue(r["success"])
        self.assertIn("keyseq_note", r)
        # fell back to the row click at the computed coords
        self.assertEqual(r["script_click"]["x"], 1302)
        self.assertEqual(r["script_click"]["y"], 285)


if __name__ == "__main__":
    unittest.main()


class TestWrenchFromTitle(unittest.TestCase):
    """2026-10-02: the fixed fraction hit the roll's colour-group selector."""

    def _run(self, boxes, hint):
        from fl_studio_mcp.utils import custom_menu as cm
        with mock.patch.object(cm, "shot", return_value="/x.png"), \
             mock.patch.object(cm, "ocr_boxes", return_value=boxes), \
             mock.patch.object(cm, "ocr_region", return_value=[]), \
             mock.patch.object(cm, "hint_at", side_effect=hint):
            return ss._wrench_from_title()

    def test_title_anchor_confirmed_by_hint(self):
        from fl_studio_mcp.utils.custom_menu import Box
        title = Box(1363, 208, 180, 12, "Piano roll - Sapphire Melody")
        got = self._run([title], lambda x, y: "Tools" if x == 1031 else "Color group / MIDI channel 15")
        self.assertEqual(got, (1031, 214))

    def test_icon_glyph_before_the_title(self):
        # live OCR: '4 Piano roll-Sapphire Melody', box starting at the icon
        from fl_studio_mcp.utils.custom_menu import Box
        title = Box(1336, 206, 214, 16, "4 Piano roll-Sapphire Melody")
        got = self._run([title], lambda x, y: "Tools" if 1020 <= x <= 1035 else "x")
        self.assertIsNotNone(got)
        self.assertTrue(1020 <= got[0] <= 1035)

    def test_unconfirmed_hint_returns_none(self):
        from fl_studio_mcp.utils.custom_menu import Box
        title = Box(1363, 208, 180, 12, "Piano roll - X")
        self.assertIsNone(self._run([title], lambda x, y: "Color group / MIDI channel 15"))


class TestUnconfirmedWrenchRefuses(_Base):
    def test_no_click_no_keys_when_the_wrench_is_not_confirmed(self):
        ss._wrench_from_title.return_value = None
        r = ss.fl_select_script(channel_index=5)
        self.assertFalse(r["success"])
        self.assertIn("nothing was clicked", r["error"])
        ss._click.assert_not_called()
        ss._send_keyseq.assert_not_called()
        ss._open_roll_via_menu.assert_called_once()     # one look after opening

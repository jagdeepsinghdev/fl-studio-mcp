"""Tests for the B11 fl_lifecycle tool (open/close/save/status/force).

These mock the OS-level helpers (_fl_running, _run, _controller_responsive) so
the tests are deterministic and never touch a real FL process.
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from fl_studio_mcp.tools import lifecycle_v2 as lc


class TestLifecycle(unittest.TestCase):

    def test_unknown_action(self):
        r = lc.fl_lifecycle("bogus")
        self.assertFalse(r["success"])
        self.assertIn("valid_actions", r)
        self.assertEqual(lc.ACTIONS[0], "status")

    # -- status ----------------------------------------------------------

    def test_status_not_running(self):
        with mock.patch.object(lc, "_fl_running", return_value=False):
            r = lc.fl_lifecycle("status")
        self.assertFalse(r["running"])
        self.assertEqual(r["state"], "not_running")

    def test_status_ready(self):
        import fl_studio_mcp.tools.state as state_mod
        with mock.patch.object(lc, "_fl_running", return_value=True), \
             mock.patch.object(lc, "_fl_pid", return_value=1234), \
             mock.patch.object(lc, "_controller_responsive",
                               return_value=(True, "bpm=120")), \
             mock.patch.object(state_mod, "take_state_snapshot",
                               return_value={"success": True, "bpm": 120,
                                             "project": "x", "fl_version": "26.1",
                                             "selected_pattern": 1,
                                             "channel_count": 5}):
            r = lc.fl_lifecycle("status")
        self.assertTrue(r["running"])
        self.assertTrue(r["controller_responsive"])
        self.assertEqual(r["state"], "ready")
        self.assertEqual(r["bpm"], 120)

    def test_status_wedged(self):
        with mock.patch.object(lc, "_fl_running", return_value=True), \
             mock.patch.object(lc, "_fl_pid", return_value=999), \
             mock.patch.object(lc, "_controller_responsive",
                               return_value=(False, "controller timeout (wedged)")):
            # patch the snapshot import used inside _action_status
            import fl_studio_mcp.tools.state as state_mod
            with mock.patch.object(state_mod, "take_state_snapshot"):
                r = lc.fl_lifecycle("status")
        self.assertTrue(r["running"])
        self.assertFalse(r["controller_responsive"])
        self.assertEqual(r["state"], "wedged_or_dialog_blocking")

    # -- open ------------------------------------------------------------

    def test_open_already_running_ready(self):
        with mock.patch.object(lc, "_fl_running", return_value=True), \
             mock.patch.object(lc, "_controller_responsive",
                               return_value=(True, "bpm=130")):
            r = lc.fl_lifecycle("open")
        self.assertTrue(r["already_running"])
        self.assertEqual(r["state"], "ready")

    def test_open_launches(self):
        with mock.patch.object(lc, "_fl_running",
                               side_effect=[False, True, True]), \
             mock.patch.object(lc, "_run", return_value=(0, "", "")), \
             mock.patch.object(lc, "_controller_responsive",
                               return_value=(True, "bpm=120")), \
             mock.patch("time.sleep"):
            r = lc.fl_lifecycle("open")
        self.assertEqual(r["state"], "ready")
        self.assertEqual(r.get("launch_rc"), 0)

    def test_open_no_wait(self):
        with mock.patch.object(lc, "_fl_running", return_value=False), \
             mock.patch.object(lc, "_run", return_value=(0, "", "")):
            r = lc.fl_lifecycle("open", wait_ready=False)
        self.assertEqual(r["state"], "launching")

    # -- close -----------------------------------------------------------

    def test_close_not_running(self):
        with mock.patch.object(lc, "_fl_running", return_value=False):
            r = lc.fl_lifecycle("close")
        self.assertFalse(r["running"])
        self.assertIn("note", r)

    def test_close_clean(self):
        # running at first, gone after quit
        with mock.patch.object(lc, "_fl_running",
                               side_effect=[True, False]), \
             mock.patch.object(lc, "_run", return_value=(0, "", "")), \
             mock.patch("time.sleep"):
            r = lc.fl_lifecycle("close")
        self.assertTrue(r["quit_sent"])
        self.assertEqual(r["state"], "closed_cleanly")

    def test_close_after_dialog(self):
        # running, then still running after quit (dialog), then gone after dismiss
        with mock.patch.object(lc, "_fl_running",
                               side_effect=[True, True, False]), \
             mock.patch.object(lc, "_run", return_value=(0, "", "")), \
             mock.patch.object(lc, "_dismiss_native_dialog",
                               return_value={"ok": True, "method": "ax-button"}), \
             mock.patch("time.sleep"):
            r = lc.fl_lifecycle("close")
        self.assertEqual(r["state"], "closed_after_dialog")

    # -- save ------------------------------------------------------------

    def test_save_not_running(self):
        with mock.patch.object(lc, "_fl_running", return_value=False):
            r = lc.fl_lifecycle("save")
        self.assertFalse(r["running"])
        self.assertIn("error", r)

    def test_save_plain(self):
        with mock.patch.object(lc, "_fl_running", return_value=True), \
             mock.patch.object(lc, "_run", return_value=(0, "", "")), \
             mock.patch("time.sleep"):
            r = lc.fl_lifecycle("save")
        self.assertTrue(r["ok"])
        self.assertEqual(r["method"], "os-save")
        self.assertIsNone(r["path"])

    # -- force -----------------------------------------------------------

    def test_force_requires_confirm(self):
        r = lc.fl_lifecycle("force")
        self.assertIn("error", r)
        self.assertIn("confirm='yes'", r["error"])
        self.assertNotIn("killed", r)

    def test_force_nothing_running(self):
        with mock.patch.object(lc, "_fl_running", return_value=False):
            r = lc.fl_lifecycle("force", confirm="yes")
        self.assertFalse(r["running"])

    def test_force_kills(self):
        with mock.patch.object(lc, "_fl_running",
                               side_effect=[True, False]), \
             mock.patch.object(lc, "_run", return_value=(0, "", "")), \
             mock.patch("time.sleep"):
            r = lc.fl_lifecycle("force", confirm="yes")
        self.assertTrue(r["killed"])

    # -- dismiss_modal ---------------------------------------------------

    def test_dismiss_modal_bad_key(self):
        r = lc.fl_lifecycle("dismiss_modal", key="tab")
        self.assertFalse(r["success"])
        self.assertIn("key must be", r["error"])

    def test_dismiss_modal_not_running(self):
        with mock.patch.object(lc, "_fl_running", return_value=False):
            r = lc.fl_lifecycle("dismiss_modal")
        self.assertFalse(r["success"])
        self.assertIn("not running", r["error"])

    def test_dismiss_modal_success_first_attempt(self):
        with mock.patch.object(lc, "_fl_running", return_value=True), \
             mock.patch.object(lc, "_fl_frontmost", return_value=True), \
             mock.patch.object(lc, "_run", return_value=(0, "", "")), \
             mock.patch.object(lc, "_find_osxfl_window",
                               return_value=("Warning", 100, 100, 400, 200)), \
             mock.patch.object(lc, "_controller_responsive",
                               return_value=(True, "bpm=130")), \
             mock.patch("time.sleep"):
            r = lc.fl_lifecycle("dismiss_modal", title="Warning", key="enter")
        self.assertTrue(r["success"])
        self.assertEqual(r["attempts_used"], 1)
        self.assertTrue(r["dialog_found"])
        self.assertTrue(r["frontmost"])
        self.assertEqual(r["controller"], "bpm=130")

    def test_dismiss_modal_focus_war_then_success(self):
        # first attempt: another app keeps the foreground; second wins
        with mock.patch.object(lc, "_fl_running", return_value=True), \
             mock.patch.object(lc, "_fl_frontmost",
                               side_effect=[False, False, True, True]), \
             mock.patch.object(lc, "_run", return_value=(0, "", "")), \
             mock.patch.object(lc, "_find_osxfl_window", return_value=None), \
             mock.patch.object(lc, "_controller_responsive",
                               side_effect=[
                                   (False, "controller timeout (wedged or dialog blocking)"),
                                   (True, "bpm=130")]), \
             mock.patch("time.sleep"):
            r = lc.fl_lifecycle("dismiss_modal", attempts=3)
        self.assertTrue(r["success"])
        self.assertEqual(r["attempts_used"], 2)

    def test_dismiss_modal_stays_blocked(self):
        with mock.patch.object(lc, "_fl_running", return_value=True), \
             mock.patch.object(lc, "_fl_frontmost", return_value=True), \
             mock.patch.object(lc, "_run", return_value=(0, "", "")), \
             mock.patch.object(lc, "_find_osxfl_window", return_value=None), \
             mock.patch.object(lc, "_controller_responsive",
                               return_value=(False, "still wedged")), \
             mock.patch("time.sleep"):
            r = lc.fl_lifecycle("dismiss_modal", attempts=2)
        self.assertFalse(r["success"])
        self.assertIn("hint", r)
        self.assertEqual(r["attempts_used"], 2)


class TestRegistration(unittest.TestCase):
    def test_connect_is_action_based_and_lifecycle_not_a_separate_tool(self):
        import fl_studio_mcp.server as srv
        tools = asyncio.run(srv.mcp.list_tools())
        names = [t.name for t in tools]
        # fl_connect is present and now exposes an `action` param (open/close/force/reconnect)
        self.assertIn("fl_connect", names)
        # the separate fl_lifecycle tool is gone (folded into fl_connect)
        self.assertNotIn("fl_lifecycle", names)
        connect = next(t for t in tools if t.name == "fl_connect")
        props = connect.parameters.get("properties", {})
        self.assertIn("action", props)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestVirtualInputPort(unittest.TestCase):
    """The P2 input leg: the server process opens a persistent 'FL Notes Out'
    virtual destination at startup (rTMIDI 1.5.8 new API: MidiIn() creates
    the destination)."""

    def test_disabled_via_env(self, monkeypatch=None):
        import fl_studio_mcp.server as srv
        called = []
        class FakeMidiIn:
            def open_virtual_port(self, name):
                called.append(name)
        import rtmidi
        with mock.patch.object(rtmidi, "MidiIn", FakeMidiIn):
            os.environ["FL_MCP_VIRTUAL_INPUT"] = "0"
            try:
                srv._open_virtual_input_port()
            finally:
                os.environ.pop("FL_MCP_VIRTUAL_INPUT", None)
        self.assertEqual(called, [])

    def test_creates_fl_notes_out(self):
        import fl_studio_mcp.server as srv
        names = []
        class FakeMidiIn:
            def open_virtual_port(self, name):
                names.append(name)
        import rtmidi
        with mock.patch.object(rtmidi, "MidiIn", FakeMidiIn):
            srv._open_virtual_input_port()
        self.assertEqual(names, ["FL Notes Out"])

    def test_failure_is_non_fatal(self):
        import fl_studio_mcp.server as srv
        class FakeMidiIn:
            def open_virtual_port(self, name):
                raise RuntimeError("port name in use")
        import rtmidi
        with mock.patch.object(rtmidi, "MidiIn", FakeMidiIn):
            srv._open_virtual_input_port()  # must not raise

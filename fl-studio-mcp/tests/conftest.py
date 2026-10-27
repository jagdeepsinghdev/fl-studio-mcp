"""Suite-wide isolation from the user's running FL Studio.

2026-10-01 incident: test_notes_v2 wrote a real C5 note into the live
ComposeWithLLM queue and pressed the real Cmd+Opt+Y trigger, stacking one
note per suite run into whichever piano roll the user had open. Every test
now gets a temp piano-roll-scripts dir and a trigger keystroke that does
nothing; tests that exercise the trigger set `_trigger_func` themselves.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture(autouse=True)
def _isolate_from_live_fl(tmp_path, monkeypatch):
    from fl_studio_mcp.tools import piano_roll
    from fl_studio_mcp.utils import connection, fl_trigger, midi_connection

    scripts = tmp_path / "Piano roll scripts"
    scripts.mkdir()
    monkeypatch.setattr(piano_roll, "_get_fl_scripts_dir", lambda: scripts)

    # The controller channel: temp command/response/audit files and NO real
    # MIDI port (the same incident sent live state.snapshot / channels.selectOne
    # to the user's FL). Tests that need a connection inject a fake `_port`.
    hw = tmp_path / "FLStudioMCP"
    hw.mkdir()
    monkeypatch.setattr(midi_connection, "_get_fl_hardware_dir", lambda: hw)

    def _no_live_fl(self):
        self._error = "tests never connect to a live FL (tests/conftest.py)"
        return False

    monkeypatch.setattr(midi_connection.MIDIConnection, "connect", _no_live_fl)

    # No test may depend on whether FL happens to be running on this machine.
    from fl_studio_mcp.utils import roll_session
    monkeypatch.setattr(roll_session, "fl_started_at", lambda: None)
    monkeypatch.setattr(roll_session, "fl_pid", lambda: None)
    monkeypatch.setattr(midi_connection, "_connection", None)
    monkeypatch.setattr(connection, "_connection", None)
    monkeypatch.setattr(fl_trigger.FLStudioTrigger, "_trigger_macos",
                        lambda self: True)
    monkeypatch.setattr(fl_trigger.FLStudioTrigger, "_trigger_windows",
                        lambda self: True)
    monkeypatch.setattr(fl_trigger, "_trigger", None)

    # 2026-10-26: a test called the real ui_guard.ensure_ready, which focused the
    # user's FL window on every run and failed in CI (no FL there). Readiness and
    # focus must be mocked by the test that needs them; the real ones refuse.
    from fl_studio_mcp.utils import custom_menu, ui_guard

    def _refuse(name):
        def _f(*a, **k):
            raise AssertionError(f"test called the real {name}: mock it (tests/conftest.py)")
        return _f

    monkeypatch.setattr(ui_guard, "ensure_ready", _refuse("ui_guard.ensure_ready"))
    monkeypatch.setattr(custom_menu, "focus_fl", _refuse("custom_menu.focus_fl"))
    monkeypatch.setattr(custom_menu, "require_fl_front", _refuse("custom_menu.require_fl_front"))

    # Nor may a test drive the real screen: AppleScript (System Events clicks/queries),
    # screenshots or OCR reach the user's live FL locally and fail in CI. ffmpeg, git
    # and other tools still run.
    import subprocess
    _ui_tools = {"osascript", "screencapture", "ocr_text", "cliclick"}
    for fn_name in ("run", "Popen", "check_output", "call"):
        real = getattr(subprocess, fn_name)

        def _guard(*a, _real=real, _name=fn_name, **k):
            cmd = a[0] if a else k.get("args")
            exe = (cmd if isinstance(cmd, str) else (cmd or [""])[0])
            if os.path.basename(str(exe).split()[0] if isinstance(cmd, str) else str(exe)) in _ui_tools:
                raise AssertionError(f"test ran the real {exe!r} via subprocess.{_name}: "
                                     "mock the UI call (tests/conftest.py)")
            return _real(*a, **k)
        monkeypatch.setattr(subprocess, fn_name, _guard)
    yield

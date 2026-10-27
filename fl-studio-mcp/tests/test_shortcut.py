"""fl_shortcut: catalog integrity, key encoding, and the guard order (no FL)."""

import pytest

import fl_studio_mcp.tools.shortcut_v2 as sc


class FakeIO:
    def __init__(self, caption="Playlist - Arrangement", front=True,
                 values=None, focus_to=None):
        self.caption = caption
        self.front = front
        self.values = list(values or [])
        self.focus_to = focus_to
        self.sent: list[str] = []
        self.steps: list[list] = []

    def fl_front(self):
        return self.front, ("" if self.front else "Google Chrome")

    def ui_steps(self, calls):
        self.steps.append(calls)
        if self.focus_to:
            self.caption = self.focus_to
        return {"success": True, "executed": []}

    def read(self, fn, args=None):
        if fn == "ui.getFocusedFormCaption":
            return self.caption
        return self.values.pop(0)

    def send_keys(self, keys):
        self.sent.append(keys)
        return True, ""

    def sleep(self, s):
        pass

    def roll_snapshot(self):
        self.snaps = getattr(self, "snaps", 0) + 1
        return {"note_count": 1,
                "notes": [{"midi": 60, "time": 0,
                           "duration": 1.0 if self.sent else 0.25}]}


def _e(**kw):
    base = {"id": "x", "keys": "F9", "context": "global", "action": "a",
            "risk": "view"}
    base.update(kw)
    return base


def test_catalog_is_valid():
    entries = sc.load_catalog()
    assert len(entries) > 200
    assert sc.validate_catalog(entries) == []


def test_every_verify_reads_an_allowlisted_getter():
    from fl_studio_mcp.tools.ui_script_v2 import STEP_FNS
    for e in sc.load_catalog():
        v = e.get("verify")
        if v:
            mod, _, name = v["changes"].partition(".")
            assert name in STEP_FNS[mod], e["id"]


def test_dialog_openers_need_confirm():
    by = {e["id"]: e for e in sc.load_catalog()}
    for i in ("open_file", "save_as", "channel_rack.delete",
              "piano_roll.quantize", "browser.replace_channel", "panic"):
        assert by[i]["risk"] == "confirm", i


@pytest.mark.parametrize("keys,want", [
    ("cmd+shift+s", 'keystroke "s" using {command down, shift down}'),
    ("F7", "key code 98"),
    ("opt+fwddel", "key code 117 using {option down}"),
    ("num_plus", "key code 69"),
    ("space", "key code 49"),
])
def test_applescript(keys, want):
    assert sc.applescript(keys).endswith(want)


@pytest.mark.parametrize("bad", ["", "hyper+s", "cmd+cmd+s", "cmd+F13", "cmd+"])
def test_parse_rejects(bad):
    with pytest.raises(ValueError):
        sc.parse_keys(bad)


def test_confirm_tier_refused_without_confirm():
    io = FakeIO()
    r = sc.run_entry(_e(risk="confirm"), io)
    assert r["refused"] == "confirm" and io.sent == []
    assert sc.run_entry(_e(risk="confirm"), io, confirm=True)["success"]


def test_not_front_refused():
    io = FakeIO(front=False)
    r = sc.run_entry(_e(), io)
    assert r["refused"] == "front" and io.sent == []


def test_wrong_context_refused_then_focus_fixes_it():
    e = _e(context="mixer", keys="s", risk="toggle")
    io = FakeIO(caption="Piano roll - 808")
    assert sc.run_entry(e, io)["refused"] == "focus" and io.sent == []
    io = FakeIO(caption="Piano roll - 808", focus_to="Mixer - Master")
    r = sc.run_entry(e, io, focus=True)
    assert r["success"] and io.sent == ["s"]
    assert io.steps[0] == [{"fn": "ui.hideWindow", "args": [0]},
                           {"fn": "ui.showWindow", "args": [0]}]


def test_focus_that_does_not_take_is_refused():
    io = FakeIO(caption="Browser", focus_to="Browser")
    r = sc.run_entry(_e(context="piano_roll", keys="cmd+g"), io, focus=True)
    assert r["refused"] == "focus" and io.sent == []


def test_global_collision_refused():
    io = FakeIO(caption="Piano roll - Lead")
    r = sc.run_entry(_e(keys="cmd+m", not_in=["piano_roll"]), io)
    assert r["refused"] == "collision" and io.sent == []


def test_verify_oracle():
    e = _e(verify={"changes": "ui.getVisible", "args": [0]})
    ok = sc.run_entry(e, FakeIO(values=[0, 1]))
    assert ok["success"] and ok["verify"]["changed"]
    miss = sc.run_entry(e, FakeIO(values=[1, 1]))
    assert not miss["success"] and "did not land" in miss["error"]


def test_tool_list_show_dry_run_and_adhoc():
    r = sc.fl_shortcut("list", context="mixer", limit=0)
    assert r["success"] and r["shown"] == r["total"]
    assert all(s["id"].startswith("mixer.") for s in r["shortcuts"])
    assert sc.fl_shortcut("show", id="piano_roll")["applescript"].endswith("key code 98")
    assert sc.fl_shortcut("run", id="nope")["success"] is False
    assert sc.fl_shortcut("run", id="mixer", dry_run=True)["dry_run"]
    io = FakeIO()
    r = sc.fl_shortcut("run", keys="cmd+k", io=io)
    assert r["refused"] == "confirm"   # ad-hoc keys are confirm-tier
    assert sc.fl_shortcut("bogus")["success"] is False


def test_window_toggle_that_focuses_counts_as_landed():
    e = _e(verify={"changes": "ui.getVisible", "args": [0],
                   "or_focused": "mixer"})
    io = FakeIO(caption="Channel rack", values=[1, 1])
    orig = io.read

    def read(fn, args=None):
        if fn == "ui.getFocusedFormCaption" and io.sent:
            return "Mixer - Master"
        return orig(fn, args)
    io.read = read
    r = sc.run_entry(e, io)
    assert r["success"] and r["verify"]["changed"] == "focused"


def test_batch_runs_in_order_and_stops_on_fail():
    io = FakeIO(caption="Channel rack", values=[0, 1, 0, 3])
    r = sc.fl_shortcut("batch", items=["piano_roll", "snap_toggle"], io=io)
    assert r["success"] and r["ok"] == 2 and io.sent == ["F7", "backspace"]
    io = FakeIO(caption="Channel rack")
    r = sc.fl_shortcut("batch", items=["arrange_windows", "open_file",
                                       "close_window"], io=io)
    assert not r["success"] and r["stopped_at"] == 1
    assert r["not_run"] == ["close_window"] and io.sent == ["cmd+shift+h"]


def test_batch_validates_before_any_key():
    io = FakeIO()
    r = sc.fl_shortcut("batch", items=["mixer", "no_such"], io=io)
    assert not r["success"] and io.sent == []
    assert sc.fl_shortcut("batch", items=[])["success"] is False
    assert sc.fl_shortcut("batch", items=["mixer"] * 31)["success"] is False
    assert sc.fl_shortcut("batch", items=["mixer"], dry_run=True)["dry_run"]


def test_list_is_production_first_and_token_small():
    r = sc.fl_shortcut("list")
    assert r["shown"] == 10 and r["total"] > 100 and "more" in r
    assert all(s["priority"] == 1 for s in r["shortcuts"])
    assert sc.fl_shortcut("list", query="quick legato")["shortcuts"][0]["id"] == "piano_roll.quick_legato"
    p2 = sc.fl_shortcut("list", offset=10)["shortcuts"]
    assert p2 and p2[0]["id"] != r["shortcuts"][0]["id"]


def test_unreachable_keys_hidden_and_refused():
    ids = {s["id"] for s in sc.fl_shortcut("list", limit=0)["shortcuts"]}
    assert "piano_roll.delete_tool" not in ids
    io = FakeIO(caption="Piano roll - x")
    by = {e["id"]: e for e in sc.load_catalog()}
    r = sc.run_entry(by["piano_roll.delete_tool"], io)
    assert r["refused"] == "reach" and io.sent == []
    # modifier combos are reachable
    assert by["piano_roll.quick_legato"].get("reach") != "no"
    assert by["play_stop"].get("reach") != "no"


def test_focus_hides_a_sticky_browser_first():
    io = FakeIO(caption="Browser", focus_to="Playlist - Arrangement")
    r = sc.run_entry(_e(context="playlist", keys="pgup"), io, focus=True)
    assert r["success"]
    fns = [(c["fn"], c["args"][0]) for c in io.steps[0]]
    assert fns == [("ui.hideWindow", 4), ("ui.hideWindow", 1),
                   ("ui.showWindow", 1), ("ui.hideWindow", 2),
                   ("ui.showWindow", 2)]


def test_roll_edit_reads_back_notes():
    e = _e(context="piano_roll", keys="cmd+l", risk="edit")
    io = FakeIO(caption="Piano roll - SC Test")
    r = sc.run_entry(e, io)
    assert r["success"] and r["roll"]["changed"] and io.snaps == 2


def test_roll_edit_without_change_fails():
    e = _e(context="piano_roll", keys="cmd+l", risk="edit")
    io = FakeIO(caption="Piano roll - SC Test")
    io.roll_snapshot = lambda: {"note_count": 0, "notes": []}
    r = sc.run_entry(e, io)
    assert not r["success"] and "unchanged" in r["error"]
    assert sc.run_entry(e, io, readback=False)["success"]


def test_roll_edit_refuses_with_queued_notes():
    e = _e(context="piano_roll", keys="cmd+l", risk="edit")
    io = FakeIO(caption="Piano roll - SC Test")
    io.roll_snapshot = lambda: {"error": "queue not empty"}
    r = sc.run_entry(e, io)
    assert r["refused"] == "readback" and io.sent == []

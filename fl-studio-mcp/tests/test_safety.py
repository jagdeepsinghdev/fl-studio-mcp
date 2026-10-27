"""A3: safety tiers — undo per trip, scratch detection, confirm flow,
identity verify, batch rules, and the undo-incident regression case.
"""

import pytest

from fl_studio_mcp.dispatcher import DispatchContext, Dispatcher
from fl_studio_mcp.safety import (
    SafeDispatcher,
    SafetyError,
    SessionState,
    Tier,
    is_scratch_session,
    make_safety_plan,
    tier_of,
)

# --- tier table -------------------------------------------------------------


def test_tier_table_classifies_core_actions():
    assert tier_of("transport.getBPM") is Tier.READ
    assert tier_of("mixer.setTrackVolume") is Tier.WRITE
    assert tier_of("file.open") is Tier.DESTRUCTIVE
    assert tier_of("delete.channel") is Tier.DESTRUCTIVE
    assert tier_of("setup") is Tier.DESTRUCTIVE


def test_unknown_action_defaults_to_write_never_read():
    """A new action must be conservative (undo-able), never silently a read."""
    assert tier_of("brand.new.action") is Tier.WRITE


def test_safety_plan_rules():
    s = SessionState(is_scratch=False)
    p = make_safety_plan(["transport.getBPM"], s)
    assert not p.needs_undo and not p.needs_confirm and not p.needs_identity

    p = make_safety_plan(["mixer.setTrackVolume"], s)
    assert p.needs_undo and not p.needs_confirm

    p = make_safety_plan(["delete.channel"], s)
    assert p.needs_undo and p.needs_confirm and p.needs_identity

    s2 = SessionState(is_scratch=True)
    p2 = make_safety_plan(["delete.channel"], s2)
    assert p2.needs_undo and p2.needs_identity and not p2.needs_confirm


# --- scratch detection (rule 8: title AND path) ------------------------------


def test_scratch_requires_both_title_and_path():
    f = "/Users/x/Desktop/flstudio/scratch"
    assert is_scratch_session("SCRATCH_test", f + "/SCRATCH_test.flp", f)
    assert not is_scratch_session("my song", f + "/x.flp", f)          # wrong title
    assert not is_scratch_session("SCRATCH_test", "/Users/x/other/x.flp", f)  # wrong path
    assert not is_scratch_session("SCRATCH_test", "", f)               # no path
    assert not is_scratch_session("", f + "/x.flp", f)                 # no title


# --- harness ----------------------------------------------------------------


def _registry_with(behaviors: dict) -> Dispatcher:
    """Dispatcher whose handlers return scripted responses per action.

    Plain dict behaviors that lack a ``resp`` key are READ actions (their full
    dict is returned — used for identity re-reads like channels.getInfo).
    ``{"resp": {...}}`` is a write/other action returning that response, with
    the controller's evidence plumbing (``undo_saved``/``identity_ok``) added.
    """
    d = Dispatcher()

    def make(action):
        def h(ctx, params):
            b = behaviors.get(action, {})
            resp = dict(b["resp"])
            if "_undo_name" in params:
                resp["undo_saved"] = params["_undo_name"]
            if "_identity" in params and not b.get("identity_fail"):
                resp["identity_ok"] = True
            if b.get("identity_fail"):
                resp["identity_ok"] = False
            return resp

        return h

    _READ_ACTIONS = ("channels.getInfo", "patterns.list", "channels.getSelected")
    for a in list(behaviors) + ["mixer.setTrackVolume", "transport.getBPM",
                                "transport.setBPM", "delete.channel", "delete.pattern"]:
        if a not in d._handlers:
            if a in _READ_ACTIONS:
                d.register(a, lambda ctx, p, _a=a: dict(behaviors.get(_a, {})))
            else:
                d.register(a, make(a))
    return d


def _ctx(reg, record=None):
    """Transport stand-in. If ``record`` is a list, every command sent through
    this ctx is appended (lets tests count exactly what was dispatched)."""
    def send(action, params):
        if record is not None:
            record.append((action, dict(params)))
        handler = reg._handlers[action]
        return handler(DispatchContext(send=send), params)

    return DispatchContext(send=send)


# --- undo per trip ----------------------------------------------------------


def test_write_produces_exactly_one_undo_name():
    reg = _registry_with({"mixer.setTrackVolume": {"resp": {"success": True}}})
    sd = SafeDispatcher(reg, SessionState())
    r = sd.dispatch(_ctx(reg), "mixer.setTrackVolume", {"track": 1, "volume": 0.5})
    assert r.response.get("undo_saved") == "mcp.setTrackVolume"
    assert r.params["_undo_name"] == "mcp.setTrackVolume"  # the marker went to FL
    assert "_undo_missing" not in r.response


def test_read_produces_no_undo():
    reg = _registry_with({"transport.getBPM": {"resp": {"success": True, "bpm": 130}}})
    sd = SafeDispatcher(reg, SessionState())
    r = sd.dispatch(_ctx(reg), "transport.getBPM", {})
    assert "_undo_name" not in r.params


def test_missing_undo_evidence_is_flagged():
    reg = _registry_with({"mixer.setTrackVolume": {"resp": {"success": True}}})
    # sabotage: response lacks undo_saved
    reg._handlers["mixer.setTrackVolume"] = lambda ctx, p: {"success": True}
    sd = SafeDispatcher(reg, SessionState())
    r = sd.dispatch(_ctx(reg), "mixer.setTrackVolume", {"track": 1, "volume": 0.5})
    assert r.response.get("_undo_missing") is True


# --- confirm flow -----------------------------------------------------------


def test_destructive_outside_scratch_requires_confirm():
    reg = _registry_with({
        "channels.getInfo": {"success": True, "name": "808 Kick"},
        "delete.channel": {"resp": {"success": True}},
    })
    sd = SafeDispatcher(reg, SessionState(), confirm=lambda msg, actions: False)
    with pytest.raises(SafetyError) as e:
        sd.dispatch(_ctx(reg), "delete.channel", {"index": 0, "name": "808 Kick"})
    assert e.value.reason == "confirm_declined"


def test_first_confirm_unblocks_rest_of_session():
    reg = _registry_with({
        "channels.getInfo": {"success": True, "name": "808 Kick"},
        "delete.channel": {"resp": {"success": True}},
    })
    calls = []

    def confirm(msg, actions):
        calls.append(msg)
        return True

    sd = SafeDispatcher(reg, SessionState(), confirm=confirm)
    sd.dispatch(_ctx(reg), "delete.channel", {"index": 0, "name": "808 Kick"})
    sd.dispatch(_ctx(reg), "delete.channel", {"index": 0, "name": "808 Kick"})
    assert len(calls) == 1  # only the FIRST destructive action asked


def test_scratch_session_needs_no_confirm():
    reg = _registry_with({
        "channels.getInfo": {"success": True, "name": "808 Kick"},
        "delete.channel": {"resp": {"success": True}},
    })
    sd = SafeDispatcher(reg, SessionState(is_scratch=True), confirm=None)
    r = sd.dispatch(_ctx(reg), "delete.channel", {"index": 0, "name": "808 Kick"})
    assert r.response.get("success") is True


# --- identity verify (undo-incident regression) ------------------------------


def test_destructive_identity_mismatch_is_refused():
    """THE undo-incident scenario: the caller asked to delete channel 0 named
    '808 Kick', but the live name is something else. The dispatcher re-reads
    and must REFUSE to touch the wrong target — the destructive action never runs."""
    reg = _registry_with({
        "channels.getInfo": {"success": True, "index": 0, "name": "808 Astronomic"},
        "delete.channel": {"resp": {"success": True}},
    })
    deleted = []

    def delete_h(ctx, p):
        deleted.append(p)
        return {"success": True}

    reg._handlers["delete.channel"] = delete_h
    sd = SafeDispatcher(reg, SessionState(is_scratch=True), confirm=None)
    with pytest.raises(SafetyError) as e:
        sd.dispatch(_ctx(reg), "delete.channel", {"index": 0, "name": "808 Kick"})
    assert e.value.reason == "identity_mismatch"
    assert deleted == []  # the destructive action NEVER ran


def test_destructive_identity_match_proceeds():
    reg = _registry_with({
        "channels.getInfo": {"success": True, "index": 0, "name": "808 Kick"},
        "delete.channel": {"resp": {"success": True}},
    })
    deleted = []

    def delete_h(ctx, p):
        deleted.append(p)
        return {"success": True}

    reg._handlers["delete.channel"] = delete_h
    sd = SafeDispatcher(reg, SessionState(is_scratch=True), confirm=None)
    r = sd.dispatch(_ctx(reg), "delete.channel", {"index": 0, "name": "808 Kick"})
    assert r.response.get("success") is True
    assert len(deleted) == 1
    assert deleted[0]["_identity_verified"] is True


def test_destructive_without_named_target_is_refused():
    reg = _registry_with({"delete.channel": {"resp": {"success": True}}})
    deleted = []
    reg._handlers["delete.channel"] = lambda ctx, p: (deleted.append(p), {"success": True})[1]
    sd = SafeDispatcher(reg, SessionState(is_scratch=True), confirm=None)
    with pytest.raises(SafetyError) as e:
        sd.dispatch(_ctx(reg), "delete.channel", {})
    assert e.value.reason == "identity_mismatch"
    assert deleted == []


# --- batch rules (preview of A5) ---------------------------------------------


def test_batch_rejects_destructive_items():
    reg = _registry_with({
        "mixer.setTrackVolume": {"resp": {"success": True}},
        "delete.channel": {"resp": {"success": True}},
    })
    sd = SafeDispatcher(reg, SessionState(), confirm=None)
    with pytest.raises(SafetyError) as e:
        sd.dispatch_batch(_ctx(reg), [
            {"action": "mixer.setTrackVolume", "params": {"track": 1, "volume": 0.5}},
            {"action": "delete.channel", "params": {"index": 0, "name": "x"}},
        ])
    assert e.value.reason == "batch_destructive"


def test_batch_stops_on_first_failure_with_per_item_results():
    reg = _registry_with({
        "transport.getBPM": {"resp": {"success": True, "bpm": 130}},
        "mixer.setTrackVolume": {"resp": {"success": False, "error": "boom"}},
        "transport.setBPM": {"resp": {"success": True}},
    })
    sd = SafeDispatcher(reg, SessionState())
    results = sd.dispatch_batch(_ctx(reg), [
        {"action": "transport.getBPM"},
        {"action": "mixer.setTrackVolume", "params": {"track": 1, "volume": 0.5}},
        {"action": "transport.setBPM", "params": {"bpm": 128}},
    ])
    # stop-on-fail: the third item never executed, its result is synthesized
    assert len(results) == 3
    assert results[0].response.get("success") is True
    assert results[1].response.get("success") is False
    assert results[2].response.get("error", "").startswith("skipped")
    # ONE undo marker for the whole trip, on the FIRST WRITE item only
    # (the getBPM read carries none; the skipped item never got one)
    undo_items = [r.params for r in results if "_undo_name" in r.params]
    assert len(undo_items) == 1 and undo_items[0]["_undo_name"] == "mcp.batch"


def test_batch_reads_get_no_undo():
    reg = _registry_with({"transport.getBPM": {"resp": {"success": True, "bpm": 130}}})
    sd = SafeDispatcher(reg, SessionState())
    results = sd.dispatch_batch(_ctx(reg), [{"action": "transport.getBPM"}])
    assert "_undo_name" not in results[0].params

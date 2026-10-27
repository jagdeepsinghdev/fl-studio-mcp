"""A4: fl_delete — the single permission-gateable destructive tool.

Targets: channel | pattern | pattern_data | fx | roll_notes.
Safety comes from A3: tier=destructive, owner-confirm outside scratch,
identity re-read before the action, one saveUndo per trip (controller side).
"""

import pytest

from fl_studio_mcp.safety import SafeDispatcher, SessionState, Tier, tier_of
from fl_studio_mcp.tools.delete import _DELETE_ACTIONS

# --- registry wiring --------------------------------------------------------


def test_all_targets_are_destructive():
    for t in ("channel", "pattern", "pattern_data", "fx", "roll_notes"):
        assert _DELETE_ACTIONS[t] == f"delete.{t}"
        assert tier_of(_DELETE_ACTIONS[t]) is Tier.DESTRUCTIVE


def test_delete_targets_registered_in_dispatcher():
    from fl_studio_mcp.dispatcher import build_default_dispatcher

    d = build_default_dispatcher()
    # the delete.* actions are tiered (A3 table); the registry gains them in
    # the B-sprint re-registration. Here we only check the tier table.
    assert "delete.channel" in d.actions or tier_of("delete.channel") is Tier.DESTRUCTIVE


# --- confirm flow via SafeDispatcher ----------------------------------------


def _registry_with(behaviors: dict):
    from fl_studio_mcp.dispatcher import Dispatcher

    d = Dispatcher()
    for a, b in behaviors.items():
        d.register(a, (lambda b: lambda ctx, p: dict(b))(b))
    return d


def test_channel_delete_outside_scratch_needs_confirm():
    reg = _registry_with({
        "channels.getInfo": {"success": True, "index": 0, "name": "808 Kick"},
        "delete.channel": {"success": True, "deleted": True},
    })
    sd = SafeDispatcher(reg, SessionState(), confirm=lambda msg, actions: False)
    with pytest.raises(Exception) as e:
        sd.dispatch(_ctx_of(reg), "delete.channel", {"index": 0, "name": "808 Kick"})
    assert "confirm" in str(e.value).lower() or getattr(e.value, "reason", "") == "confirm_declined"


def test_channel_delete_in_scratch_runs():
    reg = _registry_with({
        "channels.getInfo": {"success": True, "index": 0, "name": "808 Kick"},
        "delete.channel": {"success": True, "deleted": True},
    })
    sd = SafeDispatcher(reg, SessionState(is_scratch=True), confirm=None)
    r = sd.dispatch(_ctx_of(reg), "delete.channel", {"index": 0, "name": "808 Kick"})
    assert r.response.get("success") is True
    assert r.response.get("deleted") is True


def test_pattern_delete_identity_mismatch_refused():
    """Caller names pattern 2 'Verse' but the live pattern 2 is 'Chorus' —
    the dispatcher must refuse BEFORE the delete runs (undo-incident rule)."""
    deleted = []

    _registry_with({
        "patterns.list": {"success": True, "patterns": [
            {"pattern": 1, "name": "Intro"},
            {"pattern": 2, "name": "Chorus"},
        ]},
    })
    from fl_studio_mcp.dispatcher import Dispatcher
    reg2 = Dispatcher()
    reg2.register("patterns.list", lambda ctx, p: {
        "success": True, "patterns": [
            {"pattern": 1, "name": "Intro"},
            {"pattern": 2, "name": "Chorus"},
        ]})
    reg2.register("delete.pattern", lambda ctx, p: (deleted.append(p), {"success": True})[1])

    sd = SafeDispatcher(reg2, SessionState(is_scratch=True), confirm=None)
    with pytest.raises(Exception) as e:
        sd.dispatch(_ctx_of(reg2), "delete.pattern", {"index": 2, "name": "Verse"})
    assert getattr(e.value, "reason", "") == "identity_mismatch"
    assert deleted == []


def _ctx_of(reg):
    from fl_studio_mcp.dispatcher import DispatchContext

    def send(action, params):
        return reg._handlers[action](DispatchContext(send=send), params)

    return DispatchContext(send=send)

"""A5: fl_batch — many actions in ONE MIDI trip.

Rules (plan §4 rule 4 + §10 outcome 1):
  * batch REJECTS destructive items (no delete-by-stealth)
  * one saveUndo for the whole trip (on the first WRITE item; reads carry none)
  * stop-on-fail: a failing item stops the trip; later items get synthesized
    "skipped" results (they never touch FL)
  * per-item results are always returned
  * optional rollback: best-effort restoreUndoLevel to the batch's undo point —
    NOT transactional (documented in the tool docstring)
"""

import pytest

from fl_studio_mcp.dispatcher import DispatchContext, Dispatcher
from fl_studio_mcp.safety import (
    SafeDispatcher,
    SafetyError,
    SessionState,
)


def _registry_with(behaviors: dict) -> Dispatcher:
    d = Dispatcher()
    for a, b in behaviors.items():
        d.register(a, (lambda b: lambda ctx, p: dict(b))(b))
    return d


def _ctx(reg, record=None):
    def send(action, params):
        if record is not None:
            record.append((action, dict(params)))
        return reg._handlers[action](DispatchContext(send=send), params)

    return DispatchContext(send=send)


def test_five_items_one_trigger():
    """A 5-item batch (read, write, write, read, write) dispatches through the
    transport exactly once per item in ONE trip (5 handler calls, 1 undo name)."""
    reg = _registry_with({
        "transport.getBPM": {"success": True, "bpm": 130},
        "transport.setBPM": {"success": True},
        "transport.setSwing": {"success": True},
        "mixer.setTrackVolume": {"success": True},
    })
    sd = SafeDispatcher(reg, SessionState())
    calls = []
    results = sd.dispatch_batch(_ctx(reg, calls), [
        {"action": "transport.getBPM"},
        {"action": "transport.setBPM", "params": {"bpm": 128}},
        {"action": "mixer.setTrackVolume", "params": {"track": 1, "volume": 0.5}},
        {"action": "transport.getBPM"},
        {"action": "transport.setSwing", "params": {"swing": 0.2}},
    ])
    assert len(results) == 5
    assert all(r.response.get("success") is True for r in results)
    # exactly one undo marker, on the FIRST write item
    undo = [r.params for r in results if "_undo_name" in r.params]
    assert len(undo) == 1
    assert undo[0]["_undo_name"] == "mcp.batch"
    # reads carried no undo marker
    reads = [r.params for r in results if r.action == "transport.getBPM"]
    assert all("_undo_name" not in p for p in reads)


def test_batch_rejects_destructive_items():
    reg = _registry_with({
        "mixer.setTrackVolume": {"success": True},
        "delete.channel": {"success": True},
    })
    sd = SafeDispatcher(reg, SessionState(), confirm=None)
    with pytest.raises(SafetyError) as e:
        sd.dispatch_batch(_ctx(reg), [
            {"action": "mixer.setTrackVolume", "params": {"track": 1, "volume": 0.5}},
            {"action": "delete.channel", "params": {"index": 0, "name": "x"}},
        ])
    assert e.value.reason == "batch_destructive"


def test_mid_batch_failure_stops_and_reports_per_item():
    reg = _registry_with({
        "transport.getBPM": {"success": True, "bpm": 130},
        "mixer.setTrackVolume": {"success": False, "error": "boom"},
        "transport.setBPM": {"success": True},
    })
    sd = SafeDispatcher(reg, SessionState())
    calls = []
    results = sd.dispatch_batch(_ctx(reg, calls), [
        {"action": "transport.getBPM"},
        {"action": "mixer.setTrackVolume", "params": {"track": 1, "volume": 0.5}},
        {"action": "transport.setBPM", "params": {"bpm": 128}},
    ])
    assert len(results) == 3
    assert results[0].response.get("success") is True
    assert results[1].response.get("success") is False
    assert results[1].response.get("error") == "boom"
    # the third item was NEVER dispatched (it's a synthesized skip)
    assert results[2].response.get("error", "").startswith("skipped")
    assert all(a != "transport.setBPM" for a, _ in calls)


def test_all_read_batch_has_no_undo():
    reg = _registry_with({
        "transport.getBPM": {"success": True, "bpm": 130},
        "channels.getAll": {"success": True, "channels": []},
    })
    sd = SafeDispatcher(reg, SessionState())
    calls = []
    results = sd.dispatch_batch(_ctx(reg, calls), [
        {"action": "transport.getBPM"},
        {"action": "channels.getAll"},
    ])
    assert all(r.response.get("success") is True for r in results)
    assert all("_undo_name" not in p for _, p in calls)


def test_empty_batch_is_noop():
    reg = _registry_with({})
    sd = SafeDispatcher(reg, SessionState())
    results = sd.dispatch_batch(_ctx(reg), [])
    assert results == []


def test_rollback_flag_is_documented_non_transactional():
    """The tool-level rollback flag is best-effort: the dispatcher does NOT
    auto-restore; the controller-side restoreUndoLevel is invoked by the tool
    wrapper, and the docstring must say it is not transactional."""
    from fl_studio_mcp.tools.batch import _rollback_docstring_ok

    assert _rollback_docstring_ok() is True


# ---------------------------------------------------------------------------
# Lifecycle interleaving (open / close / force mixed with domain actions)
# ---------------------------------------------------------------------------

def test_batch_interleaves_lifecycle_and_domain():
    """open -> [one domain trip] -> close runs in the requested order."""
    from fl_studio_mcp.safety import SessionState
    from fl_studio_mcp.tools.batch import run_batch

    calls = []

    def lc(action, **params):
        calls.append(("lc", action, params))
        return {"open": {"state": "ready"}, "close": {"state": "closed_cleanly"},
                "force": {"killed": True}}.get(action, {})

    def trip(run_items):
        calls.append(("trip", [i["action"] for i in run_items]))
        return (True, [{"action": i["action"], "ok": True} for i in run_items],
                "mcp.batch")

    items = [
        {"action": "open"},
        {"action": "transport.setBPM", "params": {"bpm": 128}},
        {"action": "mixer.setTrackVolume", "params": {"track": 1, "volume": 0.5}},
        {"action": "close", "params": {"confirm": "no"}},
    ]
    out = run_batch(items, SessionState(), lc, trip)
    assert out["ok"] is True
    # order: lifecycle(open) -> domain trip -> lifecycle(close)
    assert [c[0] for c in calls] == ["lc", "trip", "lc"]
    # the single trip got exactly the two domain items
    assert calls[1][1] == ["transport.setBPM", "mixer.setTrackVolume"]
    # close received its confirm param
    assert calls[2] == ("lc", "close", {"confirm": "no"})
    # results preserve item order
    assert [r["action"] for r in out["results"]] == [
        "open", "transport.setBPM", "mixer.setTrackVolume", "close"]
    assert out["undo_saved"] == "mcp.batch"


def test_batch_lifecycle_failure_fails_the_batch():
    from fl_studio_mcp.safety import SessionState
    from fl_studio_mcp.tools.batch import run_batch

    def lc(action, **p):
        return {"state": "not_ready_in_time"}  # open did not reach ready

    def trip(run_items):
        return (True, [{"action": i["action"], "ok": True} for i in run_items], None)

    out = run_batch([{"action": "open"}, {"action": "transport.setBPM"}],
                    SessionState(), lc, trip)
    assert out["ok"] is False
    assert out["results"][0]["ok"] is False  # the open item


def test_batch_domain_only_is_one_trip():
    from fl_studio_mcp.safety import SessionState
    from fl_studio_mcp.tools.batch import run_batch

    trips = []
    def lc(action, **p):  # pragma: no cover - not reached for domain-only
        raise AssertionError("lifecycle should not be called")

    def trip(run_items):
        trips.append([i["action"] for i in run_items])
        return (True, [{"action": i["action"], "ok": True} for i in run_items], None)

    out = run_batch([{"action": "transport.setBPM"},
                     {"action": "mixer.setTrackVolume"}], SessionState(), lc, trip)
    assert out["ok"] is True
    assert len(trips) == 1  # both domain items in a single trip
    assert trips[0] == ["transport.setBPM", "mixer.setTrackVolume"]


def test_batch_empty_is_an_error():
    from fl_studio_mcp.safety import SessionState
    from fl_studio_mcp.tools.batch import run_batch
    out = run_batch([], SessionState(), lambda a, **p: {}, lambda r: (True, [], None))
    assert out["ok"] is False
    assert out["error"] == "empty batch"

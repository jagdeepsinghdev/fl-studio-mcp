"""A5: fl_batch — many read/write actions in ONE MIDI trip.

One trip = one command file + one MIDI trigger: the controller executes the
item list in order, saves ONE undo before the first write, and returns
per-item results. Destructive items are rejected by the safety layer
(no delete-by-stealth). `rollback: true` is best-effort restoreUndoLevel —
explicitly NOT transactional.
"""

from __future__ import annotations

import os
from typing import Any

from fastmcp import FastMCP

from fl_studio_mcp.safety import SessionState
from fl_studio_mcp.utils.connection import get_connection

_MAX_ITEMS = 50
_MAX_CODE_LEN = 32768

# Lifecycle actions are OS-level (launch/kill FL, dismiss native dialogs) — they
# do NOT go through the MIDI controller, so in a batch they are executed
# server-side in item order, flushing any pending domain items into a MIDI trip
# at each lifecycle boundary. This lets a single call do: open -> configure ->
# close. Names map to the fl_lifecycle dispatcher action.
_LIFECYCLE = {
    "open": "open",
    "close": "close",
    "force": "force",
    "connect.open": "open",
    "connect.close": "close",
    "connect.force": "force",
}


def _lc_ok(r: dict, action: str) -> bool:
    """Whether a lifecycle action result counts as a success."""
    if action == "open":
        return r.get("state") in ("ready", "already_running")
    if action == "close":
        return r.get("state") in ("closed_cleanly", "closed_after_dialog")
    if action == "force":
        return bool(r.get("killed"))
    return bool(r.get("state") in ("ready",))


def _run_domain_trip(run_items: list[dict], session: SessionState):
    """Execute a group of domain (controller) items in ONE MIDI trip.

    Returns (ok, results, undo_saved). Destructive items are rejected by the
    safety layer.
    """
    from fl_studio_mcp.safety import make_safety_plan

    actions = [i.get("action", "") for i in run_items]
    plan = make_safety_plan(actions, session)
    if plan.needs_confirm:
        return (False, [{
            "action": a, "ok": False,
            "error": "destructive action rejected in batch; use fl_delete",
        } for a in actions], None)

    conn = get_connection()
    params = {"items": [
        {"action": a, "params": dict(i.get("params") or {})}
        for a, i in zip(actions, run_items)
    ]}
    if plan.has_write:
        params["_undo_name"] = "mcp.batch"
    result = conn.send_command("batch.run", params, timeout=30.0)

    ok = bool(result.get("success", False))
    results = result.get("results") or []
    if not ok and not results:
        results = [{"action": a, "ok": False,
                   "error": result.get("error", "batch failed")} for a in actions]
    return (ok, results, result.get("undo_saved"))


def _scratch_folder() -> str:
    return os.environ.get("FL_SCRATCH_FOLDER", "")


def _session() -> SessionState:
    return SessionState(
        is_scratch=False,
        project_title=os.environ.get("FL_PROJECT_TITLE", ""),
        project_path=os.environ.get("FL_PROJECT_PATH", ""),
    )


def _rollback_docstring_ok() -> bool:
    """A5 verify helper: the batch tool must document that rollback is
    best-effort and not transactional."""
    from fl_studio_mcp.tools import batch as m

    src = m.__doc__ or ""
    return "not transactional" in src.lower() or "non-transactional" in src.lower()


def run_batch(items: list[dict], session: SessionState, lc, trip) -> dict:
    """Core batch orchestration (testable: `lc` and `trip` are injectable).

    `lc(action, **params) -> dict` handles a lifecycle action (open/close/force).
    `trip(run_items) -> (ok, results, undo_saved)` runs a group of domain items
    in one MIDI trip. Items are processed in order; domain items are buffered and
    flushed into a trip at each lifecycle boundary (and at the end), so
    `open -> [domain trip] -> close` runs in the requested order.
    """
    if not items:
        return {"ok": False, "error": "empty batch"}
    if len(items) > _MAX_ITEMS:
        return {"ok": False, "error": f"batch too large: {len(items)} > {_MAX_ITEMS}"}

    out_results: list[dict] = []
    pending: list[dict] = []
    ok_all = True
    last_undo = None

    def flush() -> None:
        nonlocal pending, ok_all, last_undo
        if not pending:
            return
        ok, results, undo_saved = trip(pending)
        ok_all = ok_all and ok
        last_undo = undo_saved or last_undo
        out_results.extend(results)
        pending = []

    for item in items:
        a = item.get("action", "")
        action = _LIFECYCLE.get(a)
        if action:
            flush()  # finish any pending domain trip before the OS-level op
            r = lc(action, **dict(item.get("params") or {}))
            good = _lc_ok(r, action)
            ok_all = ok_all and good
            out_results.append({"action": a, "ok": good, "detail": r})
        else:
            pending.append(item)
    flush()

    return {"ok": ok_all, "results": out_results, "undo_saved": last_undo,
            "rolled_back": False}


def register_batch_tools(mcp: FastMCP) -> None:
    """Register the fl_batch MCP tool."""

    @mcp.tool()
    def fl_batch(
        items: list[dict[str, Any]],
        rollback: bool = False,
    ) -> dict[str, Any]:
        """Run a list of FL actions in one call — domain actions in ONE MIDI
        round trip (one command file, one trigger, one undo), plus optional
        process-lifecycle actions (open/close/force) interleaved in order.

        Use this instead of N separate fl_* calls when the actions are
        independent. Domain items are batched into a single fast 50-300 ms
        MIDI trip; lifecycle items (which work even when FL is down) are
        executed server-side in place, so one call can do:
            [{"action":"open"}, {"action":"transport.setBPM",...}, ..., {"action":"close"}]
        = launch FL, apply the config in one trip, then quit.

        Rules:
          - items: [{action, params}, ...]. Domain actions use the same
            "domain.verb" names the other tools use (transport.setBPM,
            mixer.setTrackVolume, channels.setVolume, patterns.setLength, ...).
          - Lifecycle actions: "open" / "close" / "force" (or "connect.open" /
            "connect.close" / "connect.force"). Params pass through: open
            (wait_ready, timeout), close (confirm), force (confirm). They are
            run OUTSIDE the MIDI trip, in item order, flushing pending domain
            items into a trip at each lifecycle boundary.
          - DESTRUCTIVE domain actions (delete.*, file.open, setup,
            clear.piano_roll) are REJECTED — no delete-by-stealth. Use
            fl_delete for those. (close/force are process-level, not
            project-data deletes.)
          - Stop-on-fail within a domain trip: a failed item reports the rest
            as skipped. You get per-item results.
          - One saveUndo covers each domain trip (before its first write).
          - rollback: true → best-effort general.restoreUndoLevel() after a
            failing trip. NOT transactional.

        Args:
            items: list of {"action": "domain.verb"|"open"|"close"|"force",
                            "params": {...}}
            rollback: restore the pre-trip undo level when a trip fails
                (best-effort, non-transactional)

        Returns:
            {"ok": bool, "results": [{action, ok, error?, state_after?,
             detail?}], "undo_saved": str|None, "rolled_back": bool}
        """
        session = _session()
        # Lazy import avoids a circular import through the tools package __init__
        # (which imports this module).
        from fl_studio_mcp.tools import lifecycle_v2 as _lc

        def _trip(run_items):
            return _run_domain_trip(run_items, session)

        out = run_batch(items, session, _lc.fl_lifecycle, _trip)

        if rollback and not out.get("ok"):
            # Best-effort: restore the undo level saved by the last domain trip.
            conn = get_connection()
            rr = conn.send_command("undo.restore", {"level": -1}, timeout=10.0)
            out["rolled_back"] = bool(rr.get("success", False))
            out["rollback_note"] = "best-effort; non-transactional (partial state possible)"
        return out


def _batch_registry():
    """Registry for the dispatcher's safety checks: batch items route to the
    controller's batch runner, not to individual handlers, so the registry
    only needs the actions to be *known* (tiers come from the table)."""
    from fl_studio_mcp.dispatcher import Dispatcher

    d = Dispatcher()

    def h(action):
        def _h(ctx, params):
            # The controller runs the whole batch; this handler is only ever
            # reached for the top-level "batch.run" dispatch.
            return {"success": True, "batch": True}

        return _h

    for a in ("batch.run", "undo.restore"):
        d.register(a, h(a))
    return d

"""A3: safety tiers in the dispatcher.

Design (FL-control plan rules 3/4/8 + senior-review outcomes 2/5):

- Every action is tagged **read | write | destructive** in a table. The dispatcher
  derives a **safety plan** per command from the tiers:
    * any destructive item  → confirm required (unless in a verified scratch session)
    * any write             → exactly ONE ``general.saveUndo(name)`` per trip
    * any destructive       → identity re-verify before executing
- **Undo incident regression (P3):** a destructive action MUST re-read state and
  match the caller's named target (name+index) before running — a stale selection
  can no longer take the wrong channel.
- **Scratch (rule 8):** a session is scratch iff the project title starts with
  ``SCRATCH_`` AND the file path is under the fixed scratch folder (title alone is
  rename-fakeable). Outside scratch the owner confirms the FIRST destructive
  action of a session; later ones proceed (session-scoped flag).
- The controller performs the actual ``saveUndo``/identity re-reads in the same
  trip (it alone can touch FL); the dispatcher decides and the response carries
  the evidence (``undo_saved``, ``identity_ok``, ``state_after``).

C0 note: the undo history has a user-set maximum; A3 assumes the default and
stores only one named level per trip, so overflow risk is bounded by the batch
length (see DEV-TASKS C0 for the live limit probe).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from fl_studio_mcp.dispatcher import DispatchContext, Dispatcher, DispatchResult

# ---------------------------------------------------------------------------
# Tier table
# ---------------------------------------------------------------------------


class Tier(str, Enum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


#: Actions explicitly tiered here; anything not listed falls back to
#: ``default_tier`` (write) so a new action is never accidentally "read".
TIER_TABLE: dict[str, Tier] = {
    # --- reads ---
    "transport.getStatus": Tier.READ,
    "transport.getBPM": Tier.READ,
    "transport.getSwing": Tier.READ,
    "transport.getLength": Tier.READ,
    "mixer.getTrackCount": Tier.READ,
    "mixer.getTrackInfo": Tier.READ,
    "mixer.getAllTracks": Tier.READ,
    "mixer.getSends": Tier.READ,
    "mixer.getPeaks": Tier.READ,
    "mixer.getEq": Tier.READ,
    "channels.getCount": Tier.READ,
    "channels.getInfo": Tier.READ,
    "channels.getAll": Tier.READ,
    "channels.getSelected": Tier.READ,
    "channels.getGridBit": Tier.READ,
    "channels.getStepSequence": Tier.READ,
    "channels.getStepParameter": Tier.READ,  # L5: was defaulting to WRITE
    "patterns.getLength": Tier.READ,
    "patterns.list": Tier.READ,
    "plugins.isValid": Tier.READ,
    "plugins.getName": Tier.READ,
    "plugins.getParamCount": Tier.READ,
    "plugins.getParams": Tier.READ,
    "plugins.getParamValue": Tier.READ,
    "plugins.getPresetCount": Tier.READ,
    "plugins.getColor": Tier.READ,
    "probe.exec": Tier.READ,      # introspection; arbitrary exec is a separate tool
    "probe.api": Tier.READ,
    "probe.patterns": Tier.READ,
    "probe.tempo": Tier.READ,
    "probe.playlist": Tier.READ,
    # --- writes ---
    "transport.start": Tier.WRITE,
    "transport.stop": Tier.WRITE,
    "transport.record": Tier.WRITE,
    "transport.setPosition": Tier.WRITE,
    "transport.setLoopMode": Tier.WRITE,
    "transport.setPlaybackSpeed": Tier.WRITE,
    "transport.setBPM": Tier.WRITE,
    "transport.setSwing": Tier.WRITE,
    "transport.setTimesig": Tier.WRITE,   # L13 (v10.4e wired)
    "mixer.setTrackVolume": Tier.WRITE,
    "mixer.setTrackPan": Tier.WRITE,
    "mixer.muteTrack": Tier.WRITE,
    "mixer.soloTrack": Tier.WRITE,
    "mixer.armTrack": Tier.WRITE,
    "mixer.setTrackName": Tier.WRITE,
    "mixer.setTrackColor": Tier.WRITE,
    "mixer.setStereoSep": Tier.WRITE,
    "mixer.setSendLevel": Tier.WRITE,
    "mixer.setEq": Tier.WRITE,           # v10.4h (not deployed until FL restart)
    "channels.select": Tier.WRITE,
    "channels.selectOne": Tier.WRITE,
    "channels.triggerNote": Tier.WRITE,
    "channels.setVolume": Tier.WRITE,
    "channels.setPan": Tier.WRITE,
    "channels.mute": Tier.WRITE,
    "channels.solo": Tier.WRITE,
    "channels.setName": Tier.WRITE,
    "channels.setColor": Tier.WRITE,
    "channels.routeToMixer": Tier.WRITE,
    "channels.setGridBit": Tier.WRITE,
    "channels.setStepSequence": Tier.WRITE,
    "patterns.setLength": Tier.WRITE,
    "patterns.create": Tier.WRITE,
    "patterns.select": Tier.WRITE,
    "patterns.clone": Tier.WRITE,
    "plugins.setParamValue": Tier.WRITE,
    "plugins.nextPreset": Tier.WRITE,
    "plugins.prevPreset": Tier.WRITE,
    "file.save": Tier.WRITE,             # L15 (v10.4e wired)
    "file.saveAs": Tier.WRITE,           # L15 (v10.4e wired)
    "file.export": Tier.WRITE,           # L15 (v10.4e wired)
    # --- destructive (plan §4 rule 3 + §10 outcome 2) ---
    "file.open": Tier.DESTRUCTIVE,        # replaces/strands the live session
    "delete.channel": Tier.DESTRUCTIVE,
    "delete.pattern": Tier.DESTRUCTIVE,
    "delete.pattern_data": Tier.DESTRUCTIVE,
    "delete.fx": Tier.DESTRUCTIVE,
    "delete.roll_notes": Tier.DESTRUCTIVE,
    "setup": Tier.DESTRUCTIVE,            # the legacy consolidator deletes patterns
    "clear.piano_roll": Tier.DESTRUCTIVE,
}


def tier_of(action: str, default: Tier = Tier.WRITE) -> Tier:
    return TIER_TABLE.get(action, default)


# ---------------------------------------------------------------------------
# Session / scratch
# ---------------------------------------------------------------------------


@dataclass
class SessionState:
    """Server-side view of the FL session, refreshed from read-backs.

    ``project_title``/``project_path`` come from a state read (B1 will add
    title/path to the controller; until then the dispatcher accepts them as
    caller-supplied facts and the controller cross-checks when it can).
    """

    is_scratch: bool = False
    project_title: str = ""
    project_path: str = ""
    session_id: str = field(default_factory=lambda: os.urandom(8).hex())
    confirmed_destructive: bool = False  # owner confirmed the first one this session


def is_scratch_session(project_title: str, project_path: str, scratch_folder: str) -> bool:
    """Rule 8: BOTH the title prefix and the path must match (title alone is
    rename-fakeable). Path match is a normalized prefix comparison so it works
    across absolute/relative spellings of the same folder."""
    if not (project_title or "").startswith("SCRATCH_"):
        return False
    if not (project_path or "") or not (scratch_folder or ""):
        return False
    p = os.path.normpath(os.path.expanduser(project_path))
    f = os.path.normpath(os.path.expanduser(scratch_folder))
    return p == f or p.startswith(f + os.sep)


# ---------------------------------------------------------------------------
# Safety plan
# ---------------------------------------------------------------------------


class SafetyError(Exception):
    """Raised when a command may not proceed (unconfirmed destructive, identity
    mismatch, batch containing destructive items)."""

    def __init__(self, message: str, reason: str):
        super().__init__(message)
        self.reason = reason


@dataclass
class SafetyPlan:
    """What the dispatcher decides for one trip (batch or single)."""

    tiers: list[Tier]
    needs_undo: bool = False
    needs_confirm: bool = False
    needs_identity: bool = False

    @property
    def has_write(self) -> bool:
        return any(t in (Tier.WRITE, Tier.DESTRUCTIVE) for t in self.tiers)

    @property
    def has_destructive(self) -> bool:
        return Tier.DESTRUCTIVE in self.tiers


def make_safety_plan(actions: list[str], session: SessionState) -> SafetyPlan:
    tiers = [tier_of(a) for a in actions]
    plan = SafetyPlan(tiers=tiers)
    if plan.has_write:
        plan.needs_undo = True          # one saveUndo for the WHOLE trip
    if plan.has_destructive:
        plan.needs_identity = True      # re-read + match before executing
        if not session.is_scratch:
            plan.needs_confirm = True   # owner confirms first destructive/session
    return plan


# ---------------------------------------------------------------------------
# Dispatcher with safety
# ---------------------------------------------------------------------------


@dataclass
class IdentityCheck:
    """Result of the pre-destruction identity re-read (same trip, controller)."""

    ok: bool
    expected_name: str
    expected_index: int
    actual: dict[str, Any] = field(default_factory=dict)


class SafeDispatcher:
    """Dispatcher + safety tiers. Wraps a Dispatcher's registry.

    The controller is invoked through ``ctx.send`` as usual; the dispatcher
    annotates the command with the safety plan (``safety`` block: undo name,
    identity expectations) and validates the response evidence:
      * write      → response must carry ``undo_saved`` (the controller's
                     ``general.saveUndo``) and, for writes we track, ``state_after``
      * destructive → ``identity_ok`` must be True, else the trip is aborted
    """

    def __init__(self, registry: Dispatcher, session: SessionState,
                 scratch_folder: str | None = None,
                 confirm: Callable[[str, list[str]], bool] | None = None):
        self.registry = registry
        self.session = session
        self.scratch_folder = scratch_folder or os.environ.get("FL_SCRATCH_FOLDER", "")
        self._confirm = confirm  # None = no interactive confirm available

    # -- session refresh ------------------------------------------------------

    def refresh_session(self, project_title: str, project_path: str) -> None:
        """Call after any state read; re-derives scratch status (title+path)."""
        self.session.project_title = project_title
        self.session.project_path = project_path
        self.session.is_scratch = is_scratch_session(
            project_title, project_path, self.scratch_folder
        )

    # -- confirm flow ---------------------------------------------------------

    def _need_owner_confirm(self, actions: list[str]) -> None:
        """Owner confirms the FIRST destructive action of a session (rule 8)."""
        if self.session.confirmed_destructive:
            return
        if self._confirm is None:
            raise SafetyError(
                "Destructive action(s) outside a scratch session require owner "
                f"confirmation: {', '.join(actions)}. Re-run with confirm.",
                reason="confirm_required",
            )
        if not self._confirm("Destructive action(s) about to run: " + ", ".join(actions),
                             actions):
            raise SafetyError(
                "Owner declined the destructive action(s): " + ", ".join(actions),
                reason="confirm_declined",
            )
        self.session.confirmed_destructive = True

    # -- identity verify ------------------------------------------------------

    def verify_identity(self, ctx: DispatchContext, action: str,
                        params: dict[str, Any]) -> IdentityCheck:
        # Tell the controller-side _safe_exec the expected identity so it can
        # re-read inside FL (same trip) and abort on mismatch before acting.
        params["_identity"] = {
            "target": {"delete.channel": "channel",
                       "delete.pattern": "pattern"}.get(action, "selected"),
            "name": params.get("name"),
            "index": params.get("index"),
        }
        """Re-read the affected object and match name+index (undo-incident rule).

        ``params`` must carry the caller's named target: ``name`` (+ optional
        ``index``). The re-read goes through ``ctx.send`` (a read action) so it
        happens in the same trip the controller can see, before the destructive
        action runs.
        """
        expected_name = params.get("name")
        expected_index = params.get("index")
        if expected_name is None and expected_index is None:
            return IdentityCheck(ok=False, expected_name="", expected_index=-1,
                                 actual={"error": "no name/index given — refusing to "
                                                 "delete an unnamed target"})
        if action in ("delete.fx", "delete.roll_notes", "delete.pattern_data"):
            # controller-side target = the SELECTED channel; the caller names it
            return IdentityCheck(ok=True, expected_name=expected_name or "",
                                 expected_index=expected_index if expected_index is not None else -1,
                                 actual={"target": "selected"})

        actual: dict[str, Any] = {}
        if action == "delete.channel":
            r = self._read(ctx, "channels.getInfo", {"index": expected_index or 0})
            actual = {"index": expected_index or 0,
                      "name": r.get("name"),
                      "selected": r.get("is_selected")}
        elif action == "delete.pattern":
            r = self._read(ctx, "patterns.list", {})
            for p in r.get("patterns", []):
                if (expected_index is None or p.get("pattern") == expected_index) \
                        and (expected_name is None or p.get("name") == expected_name):
                    actual = p
                    break
            if not actual:
                actual = {"patterns": [p.get("name") for p in r.get("patterns", [])]}
        else:
            # fx / pattern_data / roll_notes: match on whatever the read gives us
            r = self._read(ctx, "channels.getSelected", {})
            actual = r.get("channel") or {"selected": None}

        ok = True
        if expected_name is not None:
            ok = ok and actual.get("name") == expected_name
        if expected_index is not None:
            ok = ok and actual.get("index") == expected_index
        return IdentityCheck(ok=ok, expected_name=expected_name or "",
                             expected_index=expected_index if expected_index is not None else -1,
                             actual=actual)

    # -- dispatch -------------------------------------------------------------

    def dispatch(self, ctx: DispatchContext, action: str,
                 params: dict[str, Any] | None = None,
                 *, _reentered: bool = False) -> DispatchResult:
        params = dict(params or {})
        if _reentered:
            # identity pre-reads (and any nested send) go straight to the
            # registry — no recursive safety plan, no double undo/confirm
            return self.registry.dispatch(ctx, action, params)
        plan = make_safety_plan([action], self.session)

        if plan.needs_confirm:
            self._need_owner_confirm([action])

        if plan.needs_identity:
            check = self.verify_identity(ctx, action, params)
            if not check.ok:
                raise SafetyError(
                    f"Identity mismatch — refusing {action}: expected "
                    f"name={check.expected_name!r} index={check.expected_index}, "
                    f"actual={check.actual}",
                    reason="identity_mismatch",
                )
            params["_identity_verified"] = True

        if plan.needs_undo:
            params.setdefault("_undo_name", f"mcp.{action.split('.')[-1]}")

        result = self.registry.dispatch(ctx, action, params)

        resp = result.response
        # Evidence checks (never trust the success message — P5).
        # A controller that ran the action but failed the in-FL identity check
        # returns success=False + identity_ok=False: refuse hard in that case.
        if plan.needs_identity and resp.get("identity_ok") is False:
            resp["success"] = False
            resp["error"] = (resp.get("error") or "identity mismatch in controller")
            resp["_identity_failed"] = True
        if not resp.get("success", False):
            return result
        if plan.needs_undo and not resp.get("undo_saved"):
            resp["_undo_missing"] = True
        return result

    def _read(self, ctx: DispatchContext, action: str, params: dict[str, Any]):
        """Identity/verification read that bypasses the safety plan (so the
        re-read never re-triggers confirm/undo/identity for itself)."""
        return self.registry.dispatch(ctx, action, params).response

    # -- batch (A5 reuses this) -----------------------------------------------

    def dispatch_batch(self, ctx: DispatchContext,
                       items: list[dict[str, Any]]) -> list[DispatchResult]:
        """One trip: the batch gets ONE undo; destructive items are rejected
        (no delete-by-stealth); stop-on-fail with per-item results."""
        actions = [i["action"] for i in items]
        tiers = [tier_of(a) for a in actions]
        if any(t is Tier.DESTRUCTIVE for t in tiers):
            bad = [a for a, t in zip(actions, tiers) if t is Tier.DESTRUCTIVE]
            raise SafetyError(
                "Batch rejects destructive items: " + ", ".join(bad)
                + " — use fl_delete (with its own confirm flow) instead.",
                reason="batch_destructive",
            )
        plan = make_safety_plan(actions, self.session)
        if plan.needs_confirm:
            self._need_owner_confirm(actions)

        results: list[DispatchResult] = []
        undo_name = "mcp.batch"
        first_write_seen = False
        for i, item in enumerate(items):
            p = dict(item.get("params") or {})
            a = item["action"]
            t = tier_of(a)
            # ONE saveUndo for the whole trip, on the FIRST write item
            if plan.needs_undo and not first_write_seen and t is not Tier.READ:
                p.setdefault("_undo_name", undo_name)
                first_write_seen = True
            try:
                r = self.registry.dispatch(ctx, a, p)
            except Exception as e:  # stop-on-fail: record and stop
                results.append(DispatchResult(a, p,
                                              {"success": False, "error": str(e)}, 0.0))
                break
            results.append(r)
            if not r.response.get("success", False):
                for rest in items[i + 1:]:
                    results.append(DispatchResult(
                        rest["action"], dict(rest.get("params") or {}),
                        {"success": False,
                         "error": f"skipped (previous item failed): {rest['action']}"},
                        0.0))
                break
        return results


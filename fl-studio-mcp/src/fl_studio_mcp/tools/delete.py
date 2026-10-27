"""A4: fl_delete — the single destructive tool (permission-gateable).

Targets:
  channel      – delete a channel by name+index (identity-verified, confirm-gated)
  pattern      – delete a pattern slot by name+index
  pattern_data – clear all content (notes/steps) in a pattern (notes stay in other patterns)
  fx           – remove an effect from a mixer track slot (FL's slot menu)
  roll_notes   – clear all notes in the currently-open piano roll (the ComposeWithLLM path)

Safety (A3): every target is tier=destructive in TIER_TABLE; the SafeDispatcher
handles confirm flow (non-scratch: owner confirms first destructive per session)
and identity verify (re-read name+index before the action; mismatch → abort
before the controller executes anything).

Controller actions used (all go through _safe_exec, so they get undo + identity):
  delete.channel      -> channels.deleteChannel(index) or probe.exec
  delete.pattern      -> patterns.deletePattern(index)
  delete.pattern_data -> patterns.clearPattern(index) or probe.exec
  delete.fx           -> plugins.removeInsert(channel, slot) or probe.exec
  delete.roll_notes   -> ComposeWithLLM script queue (action="clear")
"""

from __future__ import annotations

import os
from typing import Any, Literal

from fastmcp import FastMCP

from fl_studio_mcp.safety import SessionState
from fl_studio_mcp.utils.connection import get_connection

# ---------------------------------------------------------------------------
# Action -> controller dispatch mapping
# ---------------------------------------------------------------------------

# Controller actions for each fl_delete target. These are registered in the
# controller's dispatch_command() as new elif branches (A4 controller work).
# Until the controller is updated, the MCP tool falls back to probe.exec.

_DELETE_ACTIONS: dict[str, str] = {
    "channel": "delete.channel",
    "pattern": "delete.pattern",
    "pattern_data": "delete.pattern_data",
    "fx": "delete.fx",
    "roll_notes": "delete.roll_notes",
}


def _scratch_folder() -> str:
    return os.environ.get("FL_SCRATCH_FOLDER", "")


def _session() -> SessionState:
    return SessionState(
        is_scratch=False,  # refreshed by refresh_session when a state read happens
        project_title=os.environ.get("FL_PROJECT_TITLE", ""),
        project_path=os.environ.get("FL_PROJECT_PATH", ""),
    )


def register_delete_tools(mcp: FastMCP) -> None:
    """Register the fl_delete MCP tool."""

    @mcp.tool()
    def fl_delete(
        target: Literal["channel", "pattern", "pattern_data", "fx", "roll_notes"],
        name: str = "",
        index: int | None = None,
        slot_index: int | None = None,
    ) -> dict[str, Any]:
        """Delete something from the FL Studio project.

        THIS IS THE ONLY DESTRUCTIVE TOOL. All other tools are read or write
        (undo-able). Use this when you need to permanently remove something.

        Safety:
          - In a SCRATCH session (title starts with SCRATCH_ AND file is under
            the scratch folder): no confirmation needed.
          - In any other session: the owner must confirm the FIRST destructive
            action of the session; subsequent ones proceed without re-asking.
          - Identity is re-verified (name+index) before the action executes;
            if the live state doesn't match, the action is REFUSED.

        Args:
            target: What to delete:
              - "channel": remove a channel from the Channel Rack
              - "pattern": remove a pattern from the playlist
              - "pattern_data": clear all notes/steps in a pattern (pattern slot remains)
              - "fx": remove an effect from a MIXER TRACK slot: index = mixer
                track, slot_index = 0-based slot, name = expected plugin
                (FL's slot menu Delete..., verified by the slot read-back)
              - "roll_notes": clear all notes in the currently-open piano roll
            name: Name of the target (channel name, pattern name, or FX name).
                  Required for channel/pattern; optional for others.
            index: 0-based channel index or 1-based pattern number.
                  Required for channel/pattern; for fx use slot_index instead.
            slot_index: FX slot number to remove (0-based) — only for target="fx".

        Returns:
            dict with success/error and the evidence (identity_ok, undo_saved,
            state_after where applicable).
        """
        conn = get_connection()

        # Build the controller action and params
        action = _DELETE_ACTIONS[target]
        params: dict[str, Any] = {}

        if target == "channel":
            if index is None:
                return {"ok": False, "error": "index required for channel delete"}
            # v45 has no channels.deleteChannel (live AttributeError,
            # 2026-10-02): FL's channel menu "Delete..." + its Confirm, gated
            # on the name at `index` and verified by the channel list.
            if not name:
                return {"ok": False, "error": "name required for channel delete "
                                              "(identity check before any click)"}
            import sys
            if sys.platform != "darwin":
                return {"ok": False, "error": "channel delete drives FL's menu (macOS only)"}
            from fl_studio_mcp.utils.clone_channel import delete_channel
            r = delete_channel(conn, int(index), name, log=lambda m: None)
            return {"target": "channel", "action": "channel menu > Delete...", **r}
        elif target == "pattern":
            if index is None:
                return {"ok": False, "error": "index required for pattern delete"}
            params["index"] = index  # 1-based pattern number
            if name:
                params["name"] = name
        elif target == "pattern_data":
            if index is None:
                return {"ok": False, "error": "index required for pattern_data clear"}
            params["index"] = index - 1  # controller uses 0-based
        elif target == "fx":
            # index = MIXER TRACK, slot_index = 0-based slot. v45 has no
            # remove-plugin API (the controller's plugins.removeInsert does
            # not exist): FL's slot menu "Delete..." + its Confirm, verified
            # by the slot read-back; `name` (if given) must match the slot.
            if index is None:
                return {"ok": False, "error": "index (mixer track) required for fx delete"}
            if slot_index is None:
                return {"ok": False, "error": "slot_index required for fx delete"}
            import sys
            if sys.platform != "darwin":
                return {"ok": False, "error": "fx delete drives FL's mixer menu (macOS only)"}
            from fl_studio_mcp.utils.remove_effect import remove_effect
            r = remove_effect(int(index), int(slot_index), expect=name or "",
                              conn=conn, log=lambda m: None)
            return {"target": "fx", "action": "mixer slot menu > Delete...", **r}
        elif target == "roll_notes":
            # roll_notes goes through the ComposeWithLLM script queue
            # (same path as fl_clear_piano_roll)
            from fl_studio_mcp.tools.piano_roll import _write_request, trigger_fl_studio
            from fl_studio_mcp.utils import roll_session
            before = roll_session.state_mtime()
            _write_request({"action": "clear"})
            try:
                trigger_fl_studio()
            except Exception:
                pass
            if not roll_session.ran_since(before):
                # never leave a 'clear' queued: the next trigger in ANY roll
                # would run it (2026-10-02 load_melody incident, rule 6b)
                _write_request([])
                return {"ok": False, "target": "roll_notes",
                        "error": "the ComposeWithLLM script did not run; the queued "
                                 "clear was withdrawn (nothing was cleared)"}
            return {"ok": True, "target": "roll_notes", "script_ran": True}

        # Dispatch via the controller (which applies _safe_exec: undo + identity)
        result = conn.send_command(action, params, timeout=10.0)

        ok = result.get("success", False)
        resp: dict[str, Any] = {
            "ok": ok,
            "target": target,
            "action": action,
        }
        if not ok:
            resp["error"] = result.get("error", "unknown error")
        # Copy safety evidence
        for k in ("identity_ok", "identity_detail", "undo_saved", "undo_error",
                  "state_after", "_identity_failed", "_undo_missing"):
            if k in result:
                resp[k] = result[k]
        # v10.4f: lift the clear-pattern report — remaining_grid_bits is the
        # P5 proof that the "cleared" claim is true (the old wrapper dropped
        # it, so R2's first clearPattern run looked clean and wasn't).
        for k in ("cleared", "method", "remaining_grid_bits",
                  "clearPattern_error"):
            if k in result:
                resp[k] = result[k]
        return resp

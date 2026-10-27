"""fl_probe — read-only introspection of FL's built-in Python API.

The v9-era controller has `probe.*` actions (api/patterns/tempo/playlist +
v10.3's `probe.ilmcp`) that the 10-tool v2 surface never routed. This tool
is that route. STRICTLY read-only by design:

  ilmcp     — the Gopher set: `ilmcp` (the compiled module FL's built-in MCP
              calls: run_piano_roll_script, add_channel, ...), plus
              `ui`/`screen`/`pianoroll` (PE unlockables). Returns names +
              docstrings + signatures. NO function is ever called.
  api       — callable names of any module (default "notes").
  patterns / tempo / playlist — the v9 one-shot module probes.

(`probe.exec` — arbitrary code — is deliberately NOT exposed here.)
"""
from __future__ import annotations

from typing import Any

ACTIONS = ("ilmcp", "api", "patterns", "tempo", "playlist")


def fl_probe(action: str, conn=None, **params: Any) -> dict:
    """Introspect FL's built-in Python modules (read-only; nothing is called).

    Actions:
      ilmcp    — names + docstrings of `ilmcp` (Gopher's backend), `ui`,
                 `screen`, `pianoroll`. Requires the v10.3 controller.
      api      — callable method names of one module (`module`, default
                 "notes").
      patterns / tempo / playlist — module snapshot probes.
    """
    if action not in ACTIONS:
        return {"success": False,
                "error": f"unknown action {action!r}",
                "valid_actions": list(ACTIONS)}
    if conn is None:
        from fl_studio_mcp.utils.connection import get_connection
        conn = get_connection()

    from fl_studio_mcp.tools.channel_v2 import _safe_send
    ca = f"probe.{action}"
    cparams = {"section": params.get("module", "notes")} \
        if action == "api" else {}
    try:
        res = _safe_send(ca, cparams, conn)
    except Exception as e:  # noqa: BLE001
        return {"action": action, "success": False, "error": str(e)}
    out = {"action": action, "success": bool(res.get("success"))
           and not res.get("error")}
    if res.get("error"):
        out["error"] = res["error"]
    if res.get("result"):
        out["result"] = res["result"]
    elif res.get("success") and not res.get("error"):
        # read actions: the controller's payload dict arrives at the top
        # level of the dispatcher response — lift it through
        _ENVELOPE = ("success", "error", "state_after", "undo_saved",
                     "request_id", "protocol_version")
        payload = {k: v for k, v in res.items() if k not in _ENVELOPE}
        if payload:
            out["result"] = payload
    return out


def register_probe_tools(mcp) -> None:
    """Register the fl_probe tool (read-only API introspection)."""
    from fl_studio_mcp.tools.probe_v2 import fl_probe as _impl

    @mcp.tool()
    def fl_probe(action: str, module: str | None = None) -> dict:
        """Introspect FL's built-in Python modules (read-only; nothing is called).

        Actions: ilmcp (the Gopher set: ilmcp + ui + screen + pianoroll,
        names/docstrings/signatures — v10.3 controller) | api (callable
        names of one module) | patterns | tempo | playlist.
        """
        return _impl(action, module=module)

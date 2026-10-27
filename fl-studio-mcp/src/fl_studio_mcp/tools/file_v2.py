"""B8: fl_file — project file + export control.

Actions: save | save_as | export | open.

**Tier table (the point of B8):**
  - open        = **destructive** — on a trial it strands the live project;
                  even licensed it replaces the session. Routed through
                  fl_delete's confirm flow (owner must confirm outside scratch).
  - save        = write (one named undo)
  - save_as     = write (one named undo)
  - export      = write (wav|mp3|stems)

**API status (v10.4f, 2026-10-01 post-deploy matrix, LIVE):** v45 has
NO importable file API — general has no save/saveAs/export methods and
no flp/file/project modules exist (probe.api + import attempts, all
negative). The controller's file handlers therefore refuse honestly
(status "no_api_in_v45") and point to the OS-level paths:
`fl_connect(action='save')` for File>Save (native save-dialog dismissal
included), and the native File > Export dialog for renders (L16). `open`
stays refused (destructive; native-menu path, L16). Nothing is faked.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from fl_studio_mcp.tools.transport_v2 import _safe_send, shape_response
from fl_studio_mcp.utils.connection import get_connection

ACTIONS = ("save", "save_as", "export", "open")

# tier table (B8's core deliverable)
TIERS = {
    "open": "destructive",   # strands/replaces the session; confirm flow
    "save": "write",
    "save_as": "write",
    "export": "write",
}

_PARAM_SPEC = {
    "save": [("path", "str", None, None)],
    "save_as": [("path", "str", None, None)],
    "export": [("path", "str", None, None),
               ("format", "str", ("wav", "mp3", "stems"), None)],
    "open": [("path", "str", None, None)],
}

_OPTIONAL = {("save", "path")}  # save to the current path if omitted


def _validate(action: str, params: dict[str, Any]) -> list[str]:
    if action not in ACTIONS:
        return [f"unknown action {action!r}. Valid: {', '.join(ACTIONS)}"]
    errs = []
    for name, kind, lo, hi in _PARAM_SPEC[action]:
        if (action, name) in _OPTIONAL and name not in params:
            continue
        if name not in params:
            errs.append(f"{action}: missing required param '{name}'")
            continue
        v = params[name]
        if kind == "str":
            if not isinstance(v, str) or not v.strip():
                if name == "format" and v in ("wav", "mp3", "stems"):
                    continue
                errs.append(f"{action}.{name}: non-empty string required")
            elif name == "format" and v not in ("wav", "mp3", "stems"):
                errs.append(f"{action}.format: {v!r} not in wav|mp3|stems")
    return errs


def fl_file(action: str, conn=None, **params: Any) -> dict:
    """Control FL Studio project file / export (one tool, 4 actions).

    Actions:
      save ([path]) — save the project (write; one undo)
      save_as (path) — save to a new path (write; one undo)
      export (path, format=wav|mp3|stems) — render an audio export (write)
      open (path) — **DESTRUCTIVE**: opens that file, replacing the session
          (on a trial it strands the live project). Still refused (native
          menu path, L16); its destructive tier is defined.

    v10.4f: v45 has NO importable file API (pinned by the live post-deploy
    matrix: no save/saveAs/export on general, no flp/file/project modules),
    so these actions refuse with status "no_api_in_v45" and point to the
    OS-level paths: fl_connect(action='save') for File>Save, native menus
    for export (L16). The refusal is honest, not faked — saving a real
    project is done through fl_connect.
    """
    errs = _validate(action, params)
    if errs:
        return {"success": False, "error": "; ".join(errs),
                "valid_actions": list(ACTIONS)}

    # open is destructive: it goes through the confirm flow, not a plain write.
    # (Wired via fl_delete's confirm path when the controller handler lands.)
    if action == "open":
        return {
            "success": False,
            "status": "not_verified_yet",
            "tier": "destructive",
            "error": ("open is a DESTRUCTIVE action (it replaces the live session; "
                      "on a trial it strands the project). Its destructive tier is "
                      "defined and it will route through the owner-confirm flow "
                      "(fl_delete), but the File→Open handler is not yet wired "
                      "(the `flp` file API is unprobed in v45 / File menu is the "
                      "native path). Do not rely on it yet."),
        }

    # save / save_as / export (L15, v10.4f): no importable file API in v45
    # — the controller refuses; the status field is the payload here.
    if conn is None:
        conn = get_connection()
    route = {"save": "file.save", "save_as": "file.saveAs",
             "export": "file.export"}[action]
    cparams = {k: v for k, v in params.items() if v is not None}
    try:
        res = _safe_send(route, cparams, conn)
    except Exception as e:
        return {"action": action, "success": False, "error": str(e)}
    out = shape_response(action, res)
    # shape_response drops non-envelope keys on error paths; lift the
    # refusal status back so the caller sees the no-API finding.
    for k in ("status",):
        if k in res:
            out[k] = res[k]
    return out


def register_file_tools_v2(mcp: FastMCP) -> None:
    """Register the B8 fl_file tool."""
    from fl_studio_mcp.tools.file_v2 import fl_file as _impl

    @mcp.tool()
    def fl_file(
        action: str,
        path: str | None = None,
        format: str | None = None,
    ) -> dict:
        """Control FL Studio project file / export (one tool, 4 actions).

        Actions: save | save_as | export(wav|mp3|stems) | open.
        open is DESTRUCTIVE (replaces the session; confirm flow) and still
        refused. save/save_as/export: v45 has no importable file API
        (v10.4f, L15) — they refuse with status 'no_api_in_v45' and point
        to fl_connect(action='save') / the native File menus.
        """
        p = {k: v for k, v in {"path": path, "format": format}.items()
             if v is not None}
        return _impl(action, **p)

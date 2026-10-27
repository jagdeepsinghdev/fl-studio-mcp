"""Arrangement marker tools for FL Studio (add / list).

Built on the controller's generic ``probe.exec`` action, so no controller reload is
needed. Verified live on FL 2026.1.6: ``arrangement.addAutoTimeMarker(ticks, name)``
adds a timeline marker, and ``getMarkerName(i)`` indexes markers in *time* order.
FL's API has no way to read a marker's position or to delete/rename a marker.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

_LIST_CODE = """\
import arrangement, json
names = []
for i in range(0, 256):
    try:
        n = arrangement.getMarkerName(i)
    except Exception:
        break
    if not n:
        break
    names.append(n)
print(json.dumps(names))
"""


def _exec(code: str) -> dict:
    from fl_studio_mcp.utils.connection import get_connection

    result = get_connection().send_command("probe.exec", {"code": code})
    if result.get("error"):
        return {"error": result["error"]}
    if result.get("stderr"):
        return {"error": result["stderr"].strip()}
    return {"stdout": result.get("stdout", "")}


def _list_names() -> list[str] | dict:
    out = _exec(_LIST_CODE)
    if "error" in out:
        return out
    return json.loads(out["stdout"].strip().splitlines()[-1])


def register_marker_tools(mcp: FastMCP) -> None:
    """Register arrangement marker tools with the MCP server."""

    @mcp.tool()
    def fl_list_markers() -> dict:
        """List the arrangement (timeline) markers, in time order.

        FL's API exposes only marker names, not their positions. Markers cannot be
        deleted or renamed through the API - remove them in FL's playlist if needed.
        """
        names = _list_names()
        if isinstance(names, dict):
            return names
        return {"markers": [{"index": i, "name": n} for i, n in enumerate(names)]}

    @mcp.tool()
    def fl_add_marker(name: str, beat: float = 0.0) -> dict:
        """Add a named marker on the playlist timeline (e.g. "Verse" at beat 16).

        Use it to label song sections alongside fl_create_pattern. There is no API to
        delete or rename a marker afterwards, so add each one once.

        Args:
            name: Marker name (required, non-empty).
            beat: Position in quarter-note beats from the song start (bar N starts at
                  beat (N-1)*4 in 4/4). Fractions are allowed.
        """
        if not name or not name.strip():
            return {"error": "name is required"}
        if beat < 0:
            return {"error": "beat must be >= 0"}
        code = (
            "import arrangement, general\n"
            f"arrangement.addAutoTimeMarker(int(round({float(beat)!r} * general.getRecPPQ())), {name!r})\n"
        )
        out = _exec(code)
        if "error" in out:
            return out
        names = _list_names()
        if isinstance(names, dict):
            return names
        return {"added": name, "beat": beat, "markers": names}

"""Pattern management tools for FL Studio (create / list / select / clone)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def _call(action: str, params: dict) -> dict:
    """Send a command and normalise errors to {"error": ...}."""
    from fl_studio_mcp.utils.connection import get_connection

    result = get_connection().send_command(action, params)
    if result.get("error"):
        return {"error": result["error"]}
    return {k: v for k, v in result.items() if k != "success"}


def select_pattern(pattern: int) -> dict:
    """Make an existing pattern active. Shared with the piano-roll tools."""
    return _call("patterns.select", {"pattern": pattern})


def register_pattern_tools(mcp: FastMCP) -> None:
    """Register pattern tools with the MCP server."""

    @mcp.tool()
    def fl_list_patterns() -> dict:
        """List the project's patterns (name, number, length in beats) and the active one.

        Only patterns that have been created/named are listed; FL treats untouched
        slots as default and they do not exist yet.
        """
        return _call("patterns.list", {})

    @mcp.tool()
    def fl_create_pattern(name: str, length_beats: int = 0, color: int | None = None) -> dict:
        """Create a new named pattern (e.g. "Verse", "Chorus") in the first free slot.

        Safe: it never jumps to the new pattern, because selecting an empty pattern
        makes FL open a modal rename dialog that blocks the whole MCP bridge. The new
        pattern is NOT made active - call fl_select_pattern to write into it.

        Args:
            name: Pattern name (required).
            length_beats: Pattern length in beats (0 = leave FL's default of 16).
            color: Optional 0xRRGGBB colour as an integer.
        """
        params: dict = {"name": name}
        if length_beats:
            params["length_beats"] = length_beats
        if color is not None:
            params["color"] = color
        return _call("patterns.create", params)

    @mcp.tool()
    def fl_select_pattern(pattern: int) -> dict:
        """Make an existing pattern the active one (step sequencer and piano roll write here).

        Args:
            pattern: Pattern number, 1-based. Must already exist (see fl_list_patterns).
        """
        return _call("patterns.select", {"pattern": pattern})

    @mcp.tool()
    def fl_clone_pattern(pattern: int = 0, name: str = "") -> dict:
        """Clone a pattern (with its notes and steps) into the slot right after it.

        The clone becomes the active pattern. Patterns after the source shift up by
        one number, so re-run fl_list_patterns before addressing them.

        Args:
            pattern: Pattern to clone, 1-based (0 = the currently active pattern).
            name: Optional name for the clone.
        """
        params: dict = {}
        if pattern:
            params["pattern"] = pattern
        if name:
            params["name"] = name
        return _call("patterns.clone", params)

"""Advanced / diagnostic tools that execute FL Python directly.

The FL Studio Python API (v45+) intentionally does NOT expose a channel-creation
call (channels/patterns/plugins have no add/create/new for channels). These tools
give us the full power of the embedded interpreter so we can:

  * introspect any FL API module (fl_probe_api)
  * run arbitrary Python inside FL's process (fl_exec_python)

This is the escape hatch for anything the curated MCP tools can't express
(e.g. adding a new instrument channel, cloning patterns, saving a template).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from fl_studio_mcp.utils.connection import get_connection

if TYPE_CHECKING:
    from fastmcp import FastMCP


def _exec_enabled() -> bool:
    """`fl_exec_python` is OFF by default (plan §4 rule 6: it bypasses the whole
    dispatcher, so it can't be always-on). Enable per-session with FL_ALLOW_EXEC=1.
    `fl_probe_api` stays on — it is read-only introspection."""
    return os.environ.get("FL_ALLOW_EXEC", "0") == "1"

def register_exec_tools(mcp: FastMCP) -> None:
    """Register the exec/probe tools with the MCP server."""
    @mcp.tool()
    def fl_probe_api(section: str = "channels") -> dict[str, Any]:
        """List the callable methods available in a FL Studio Python API module.

        Use this to discover what an FL API module can do before scripting it.

        Args:
            section: FL Python module name (e.g. "channels", "patterns",
                "plugins", "mixer", "transport", "arrangement", "playlist").
        """
        conn = get_connection()
        result = conn.send_command("probe.api", {"section": section}, timeout=3.0)
        if not result.get("success", False):
            return {"error": result.get("error", "probe failed"), "methods": []}
        return {
            "section": result.get("section", section),
            "methods": result.get("methods", []),
        }

    @mcp.tool()
    def fl_exec_python(code: str) -> dict[str, Any]:
        """Execute a Python snippet INSIDE FL Studio's interpreter and return output.

        GATED: off by default. Set the environment variable FL_ALLOW_EXEC=1 on
        the MCP server process to enable it. Every call is written to the JSONL
        audit log (mcp_audit.jsonl) regardless.

        This runs with FL Studio's Python environment, so you can import any FL
        API module (channels, patterns, plugins, mixer, transport, notes, etc.)
        and act on the live project. Use `print(...)` to return a value.

        This is the escape hatch for operations the curated tools don't cover,
        e.g. adding a new instrument channel, cloning patterns, or saving a
        template .flp. Be careful: code runs with full access to the project.

        Example:
            fl_exec_python(code="import channels; print(channels.channelCount())")

        Args:
            code: Python source to execute. Multiple statements allowed.
        """
        if not _exec_enabled():
            return {
                "ok": False,
                "stdout": "",
                "stderr": "",
                "error": (
                    "fl_exec_python is disabled by default (arbitrary code in FL's process). "
                    "Enable it by setting FL_ALLOW_EXEC=1 on the MCP server. "
                    "Prefer the curated fl_* tools; every call here is audit-logged."
                ),
            }
        conn = get_connection()
        result = conn.send_command("probe.exec", {"code": code}, timeout=10.0)
        # The audit log is written in midi_connection._audit for every dispatched
        # command, including this one (action="probe.exec").
        if not result.get("success", False):
            return {
                "ok": False,
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "error": result.get("error", "execution failed"),
            }
        return {
            "ok": True,
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
        }

    def _add_instrument_core(name: str = "FL Keys") -> dict[str, Any]:
        """Shared with fl_channel(action="add"): utils/add_channel.py."""
        from fl_studio_mcp.utils.add_channel import add_instrument
        return add_instrument(name)

    @mcp.tool()
    def fl_add_instrument(name: str = "FL Keys") -> dict[str, Any]:
        """Add a new instrument channel by clicking FL Studio's macOS "Add" menu.

        The FL Python API cannot create channels, so this drives the native
        menu bar through System Events (requires Accessibility permission for
        the process running this server). Returns the new channel's index.

        Args:
            name: Exact Add-menu instrument, e.g. "FLEX", "FL Keys", "3x Osc",
                "Sytrus", "MiniSynth", "Harmor". Run `scripts/fl-add.sh --list`
                to see all available names.

        Requires Accessibility permission for the process running this server.
        """
        return _add_instrument_core(name)

    @mcp.tool()
    def fl_setup_instrument(
        name: str = "FLEX",
        label: str = "Piano",
        instrument: str | None = None,
    ) -> dict[str, Any]:
        """One-call instrument setup: add the channel, route it, name it, select it.

        Does in a single call what used to take 4-5 separate MCP calls:
          1. Add the instrument (via the native Add menu).
          2. Route it to the next free mixer track.
          3. Rename it to `label`.
          4. Select it exclusively (so its piano roll is ready for notes).

        Returns the new channel's index, mixer track, and name — so an agent can
        immediately write notes to it (see the fl-melody skill).

        Args:
            name: Exact Add-menu instrument, e.g. "FLEX", "FL Keys", "Sytrus".
            label: Name to give the new channel (e.g. "Piano", "Keys", "Bass").
                Defaults to the instrument name.
            instrument: Optional; overrides `name` if you prefer that keyword.
        """
        from fl_studio_mcp.utils.add_channel import setup_instrument

        r = setup_instrument(instrument or name, label or (instrument or name))
        if r.get("ok"):
            r["next"] = "write notes with fl_notes write_steps (channel_index=...)"
        return r


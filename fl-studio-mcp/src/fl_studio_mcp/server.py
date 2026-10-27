"""FL Studio MCP Server - Control FL Studio via Model Context Protocol.

This MCP server provides tools to control FL Studio through two mechanisms:
1. MIDI + JSON - Real-time control of mixer, transport, channels, and plugins
2. Piano Roll Scripts - Persistent note placement via JSON + keystroke triggering

Requirements:
- FL Studio 20.7+ running
- FLStudioMCP controller script installed (run: ./scripts/setup_mac.sh)
- On Mac: IAC Driver enabled in Audio MIDI Setup
- On Windows: loopMIDI virtual MIDI ports configured
- For piano roll: ComposeWithLLM.pyscript installed in FL Studio

Limitations:
- Cannot load new plugins (only control existing ones)
- Cannot create new patterns programmatically
"""

from __future__ import annotations

import os

from fastmcp import FastMCP

from fl_studio_mcp.tools import lifecycle_v2 as _lifecycle
from fl_studio_mcp.tools import (
    register_batch_tools,
    register_channel_tools,
    register_delete_tools,
    register_exec_tools,
    register_marker_tools,
    register_mixer_tools,
    register_pattern_tools,
    register_piano_roll_tools,
    register_plugin_tools,
    register_song_builder_tools,
    register_transport_tools,
)
from fl_studio_mcp.tools.audio_v2 import register_audio_tools
from fl_studio_mcp.tools.channel_v2 import register_channel_tools_v2
from fl_studio_mcp.tools.edison_v2 import register_edison_tools
from fl_studio_mcp.tools.file_v2 import register_file_tools_v2
from fl_studio_mcp.tools.genre_v2 import register_genre_tools
from fl_studio_mcp.tools.help_v2 import register_help_tools_v2
from fl_studio_mcp.tools.launchpad import register_launchpad_tools
from fl_studio_mcp.tools.mixer_v2 import register_mixer_tools_v2
from fl_studio_mcp.tools.notes_v2 import register_notes_tools_v2
from fl_studio_mcp.tools.pattern_v2 import register_pattern_tools_v2
from fl_studio_mcp.tools.plugin_v2 import register_plugin_tools_v2
from fl_studio_mcp.tools.preset_v2 import register_preset_tools
from fl_studio_mcp.tools.probe_v2 import register_probe_tools
from fl_studio_mcp.tools.recipe_v2 import register_recipe_tools_v2
from fl_studio_mcp.tools.screen_v2 import register_screen_tools
from fl_studio_mcp.tools.select_script import register_select_script_tool
from fl_studio_mcp.tools.shortcut_v2 import register_shortcut_tools
from fl_studio_mcp.tools.slice_v2 import register_slice_tools

# B10: the 10-tool domain surface (replaces the 86-tool legacy surface).
from fl_studio_mcp.tools.state import register_state_tools
from fl_studio_mcp.tools.transport_v2 import register_transport_tools_v2
from fl_studio_mcp.tools.ui_screen_v2 import register_ui_screen_tools
from fl_studio_mcp.tools.ui_script_v2 import register_ui_script_tools
from fl_studio_mcp.tools.variations_v2 import register_variations_tools
from fl_studio_mcp.tools.vocal_v2 import register_vocal_tools
from fl_studio_mcp.utils.connection import get_connection, reset_connection

# B10: the 86 legacy tools are OFF by default (86 schemas in context is exactly
# P1). Set LEGACY_TOOLS=1 on the MCP server to register them for ONE cycle
# (a migration safety net); the 10 domain tools + fl_delete/fl_batch are always
# on. There are NO aliases — a legacy name either exists (LEGACY_TOOLS=1) or
# the agent uses the domain tool.
_LEGACY_TOOLS = os.environ.get("LEGACY_TOOLS", "0") == "1"

# Create the MCP server
mcp = FastMCP(
    name="fl-studio-mcp",
    instructions="""
FL Studio MCP Server - Control FL Studio from AI assistants.

This server provides tools to control FL Studio through its Python scripting API.
FL Studio must be running with the FLStudioMCP MIDI controller enabled.

Available tool categories:
- Transport: Play, stop, record, tempo, position control
- Mixer: Volume, pan, mute, solo, track management
- Channels: Channel info, note triggering, step sequencer
- Plugins: Parameter control, preset navigation (cannot load new plugins)

Important limitations:
1. Cannot load new VST/AU plugins - only control existing ones
2. Cannot create new patterns programmatically
3. Note triggering (fl_trigger_note) is real-time only - notes won't persist
   unless FL Studio is recording. Use step sequencer (fl_set_grid_bit) for
   persistent drum patterns.
""",
)


# Register connection status resource
@mcp.resource("fl://status")
def get_fl_status() -> str:
    """Get FL Studio connection status."""
    conn = get_connection()
    if conn.is_connected:
        return "Connected to FL Studio via MIDI"
    else:
        return f"Not connected: {conn.connection_error}"


@mcp.resource("fl://project")
def get_project_info() -> dict:
    """Get current FL Studio project information."""
    conn = get_connection()

    if not conn.is_connected:
        return {"error": conn.connection_error}

    try:
        result = conn.send_command("transport.getStatus")
        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}

        return {
            "is_playing": result.get("is_playing", False),
            "is_recording": result.get("is_recording", False),
            "position": result.get("position", ""),
            "loop_mode": result.get("loop_mode", "pattern"),
        }
    except Exception as e:
        return {"error": str(e)}


# Connection management tools
@mcp.tool()
def fl_connect(
    action: str | None = None,
    confirm: str | None = None,
    wait_ready: bool | None = None,
    timeout: float | None = None,
    title: str | None = None,
    key: str | None = None,
    attempts: int | None = None,
) -> dict:
    """Manage the FL connection AND process: open / close / force / reconnect.

    This is the one tool for bringing FL up and taking it down (no other tool
    can run when FL is not up, so these live here, not in the 10 domain tools).

    Actions:
      (none) / "reconnect" — reconnect the MIDI link (original behavior).
      "open"   — launch FL if down, dismiss the trial Welcome dialog, wait until
                 the controller is responsive. [wait_ready=True] [timeout=60]
      "close"  — quit FL, auto-dismissing the native 'Save changes?' dialog.
                 [confirm=no|yes|cancel]  (no=don't save; default no)
      "force"  — last-resort hard kill (pkill) if FL is wedged. [confirm=yes]
      "dismiss_modal" — un-wedge the controller when a web-rendered modal
                 (Welcome, "Warning: The score log is empty", …) is blocking
                 it: activates FL, verifies it is frontmost (focus-war safe),
                 sends a key, then polls the controller until it answers.
                 [title="Warning"] [key=enter|esc] [attempts=5]
      "doctor" — one read-only check before any job: FL frontmost? controller
                 ok / 'Operation unsafe' / timeout? picker, FL dialogs, popup menu
                 open? focused form, CPU, user idle time; blockers + advice.
      "recover" — clear what blocks FL: close the picker, dismiss FL dialogs
                 (Enter), close popup menus in-engine, wait while FL is busy.
                 Brings FL forward only after ~3 s of user idle (never mid-typing).
      "tidy"   — close every plugin editor window (in-engine focus + Escape).

    Saving a project is `fl_file(action="save")`; reading session state is
    `fl_state` — not here.
    """
    a = (action or "reconnect").lower()
    if a == "reconnect":
        reset_connection()
        conn = get_connection()
        try:
            conn.ensure_connected()
            return {"action": "reconnect", "ok": True,
                    "message": "Successfully connected to FL Studio via MIDI!"}
        except RuntimeError as e:
            return {"action": "reconnect", "ok": False, "error": str(e)}
    # open / close / force / dismiss_modal — process/lifecycle (OS-level),
    # delegated.
    return _lifecycle.fl_lifecycle(a, confirm=confirm,
                                   wait_ready=wait_ready, timeout=timeout,
                                   title=title, key=key, attempts=attempts)


@mcp.tool()
def fl_connection_status() -> dict:
    """Get the current FL Studio connection status.

    Returns information about whether FL Studio is connected
    and any error messages if not.
    """
    conn = get_connection()
    # Eagerly attempt a connection so the reported status reflects actual
    # reachability rather than the lazily-initialized flag.
    try:
        conn.ensure_connected()
    except RuntimeError:
        pass
    status = conn.get_status()
    return {
        "connected": status.get("connected", False),
        "port_name": status.get("port_name"),
        "available_ports": status.get("available_ports", []),
        "error": status.get("error"),
    }


# Register all tools — B10: 10 domain tools always on; legacy tools off
# unless LEGACY_TOOLS=1 (no aliases; R5 2026-10-01 retired the last preset
# loaders fl_list_presets/fl_load_beat/fl_load_melody).
register_state_tools(mcp)
register_transport_tools_v2(mcp)
register_mixer_tools_v2(mcp)
register_channel_tools_v2(mcp)
register_pattern_tools_v2(mcp)
register_launchpad_tools(mcp)
register_probe_tools(mcp)
register_ui_screen_tools(mcp)
register_ui_script_tools(mcp)
register_shortcut_tools(mcp)
register_notes_tools_v2(mcp)
register_select_script_tool(mcp)
register_plugin_tools_v2(mcp)
register_file_tools_v2(mcp)
register_help_tools_v2(mcp)
register_recipe_tools_v2(mcp)
register_variations_tools(mcp)
register_preset_tools(mcp)
register_slice_tools(mcp)
register_edison_tools(mcp)
# Sprint A tools (always on, part of the 10-tool surface + safety):
register_delete_tools(mcp)
register_batch_tools(mcp)
register_vocal_tools(mcp)
register_screen_tools(mcp)
register_genre_tools(mcp)
register_audio_tools(mcp)

if _LEGACY_TOOLS:
    # One-cycle migration safety net: the remaining legacy tools + the exec gate.
    register_transport_tools(mcp)
    register_mixer_tools(mcp)
    register_channel_tools(mcp)
    register_plugin_tools(mcp)
    register_piano_roll_tools(mcp)
    register_exec_tools(mcp)
    register_pattern_tools(mcp)
    register_marker_tools(mcp)
    register_song_builder_tools(mcp)


def _open_virtual_input_port() -> None:
    """Open a persistent virtual MIDI destination 'FL Notes Out' (P2 input leg).

    FL Studio can select this port as an input device (Options → MIDI
    settings); notes sent to it from any app (or our own MIDI loop) are then
    visible to FL — e.g. via general.dumpScoreLog. rtmidi 1.5.8 new-API:
    ``MidiIn().open_virtual_port(name)`` creates a DESTINATION (inverted vs
    the classic API) — verified 2026-10-02. Non-fatal on failure (e.g. the
    name is already registered by a previous server instance).
    Disable with FL_MCP_VIRTUAL_INPUT=0.
    """
    if os.environ.get("FL_MCP_VIRTUAL_INPUT", "1") == "0":
        return
    try:
        from rtmidi import MidiIn
        global _VIRTUAL_INPUT_PORT
        _VIRTUAL_INPUT_PORT = MidiIn()
        _VIRTUAL_INPUT_PORT.open_virtual_port("FL Notes Out")
    except Exception:  # noqa: BLE001 - a missing virtual port is not fatal
        pass


def main():
    """Run the FL Studio MCP server."""
    _open_virtual_input_port()
    mcp.run()


if __name__ == "__main__":
    main()

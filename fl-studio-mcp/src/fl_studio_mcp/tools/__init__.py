"""FL Studio MCP tools."""

from fl_studio_mcp.tools.batch import register_batch_tools
from fl_studio_mcp.tools.channels import register_channel_tools
from fl_studio_mcp.tools.delete import register_delete_tools
from fl_studio_mcp.tools.exec_python import register_exec_tools
from fl_studio_mcp.tools.markers import register_marker_tools
from fl_studio_mcp.tools.mixer import register_mixer_tools
from fl_studio_mcp.tools.patterns import register_pattern_tools
from fl_studio_mcp.tools.piano_roll import register_piano_roll_tools
from fl_studio_mcp.tools.plugins import register_plugin_tools
from fl_studio_mcp.tools.song_builder import register_song_builder_tools
from fl_studio_mcp.tools.state import register_state_tools
from fl_studio_mcp.tools.transport import register_transport_tools

__all__ = [
    "register_transport_tools",
    "register_mixer_tools",
    "register_channel_tools",
    "register_plugin_tools",
    "register_piano_roll_tools",
    "register_exec_tools",
    "register_pattern_tools",
    "register_marker_tools",
    "register_song_builder_tools",
    "register_delete_tools",
    "register_batch_tools",
    "register_state_tools",
]

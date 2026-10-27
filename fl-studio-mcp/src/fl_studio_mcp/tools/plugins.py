"""Plugin control tools for FL Studio.

NOTE: These tools can only control EXISTING plugins. FL Studio's scripting API
does not support loading new plugins programmatically.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


_STEP_PAUSE = 0.5  # seconds FL needs to refresh the channel name after a preset step


def register_plugin_tools(mcp: FastMCP) -> None:
    """Register plugin control tools with the MCP server."""
    from fl_studio_mcp.utils.connection import get_connection

    @mcp.tool()
    def fl_is_plugin_valid(
        index: int,
        slot_index: int = -1,
        use_global_index: bool = True
    ) -> bool:
        """Check if a plugin exists at the given location.

        For channel rack plugins, use just index.
        For mixer effect plugins, use index as mixer track and slot_index as effect slot.

        Args:
            index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        result = conn.send_command("plugins.isValid", {
            "index": index,
            "slot_index": slot_index,
            "use_global": use_global_index,
        })

        if not result.get("success", False) and "error" in result:
            return False

        return result.get("valid", False)

    @mcp.tool()
    def fl_get_plugin_name(
        index: int,
        slot_index: int = -1,
        use_global_index: bool = True
    ) -> str:
        """Get the name of a plugin.

        Args:
            index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        result = conn.send_command("plugins.getName", {
            "index": index,
            "slot_index": slot_index,
            "use_global": use_global_index,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        return result.get("name", "")

    @mcp.tool()
    def fl_get_plugin_param_count(
        index: int,
        slot_index: int = -1,
        use_global_index: bool = True
    ) -> int:
        """Get the number of parameters a plugin has.

        Args:
            index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        result = conn.send_command("plugins.getParamCount", {
            "index": index,
            "slot_index": slot_index,
            "use_global": use_global_index,
        })

        if not result.get("success", False) and "error" in result:
            return -1

        return result.get("count", 0)

    @mcp.tool()
    def fl_get_plugin_params(
        index: int,
        slot_index: int = -1,
        use_global_index: bool = True,
        max_params: int = 50
    ) -> list[dict]:
        """Get all parameters of a plugin with their current values.

        Args:
            index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
            max_params: Maximum number of parameters to return (default 50)
        """
        conn = get_connection()
        result = conn.send_command("plugins.getParams", {
            "index": index,
            "slot_index": slot_index,
            "use_global": use_global_index,
            "max_params": max_params,
        })

        if not result.get("success", False) and "error" in result:
            return [{"error": result["error"]}]

        return result.get("params", [])

    @mcp.tool()
    def fl_get_plugin_param_value(
        param_index: int,
        plugin_index: int,
        slot_index: int = -1,
        use_global_index: bool = True
    ) -> dict:
        """Get the value of a specific plugin parameter.

        Args:
            param_index: Parameter index
            plugin_index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        result = conn.send_command("plugins.getParamValue", {
            "param_index": param_index,
            "plugin_index": plugin_index,
            "slot_index": slot_index,
            "use_global": use_global_index,
        })

        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}

        return {
            "index": result.get("index", param_index),
            "name": result.get("name", ""),
            "value": result.get("value", 0),
            "value_string": result.get("value_string", ""),
        }

    @mcp.tool()
    def fl_set_plugin_param_value(
        param_index: int,
        value: float,
        plugin_index: int,
        slot_index: int = -1,
        use_global_index: bool = True
    ) -> str:
        """Set the value of a plugin parameter.

        Args:
            param_index: Parameter index
            value: New value (typically 0.0 to 1.0, but depends on parameter)
            plugin_index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        result = conn.send_command("plugins.setParamValue", {
            "param_index": param_index,
            "value": value,
            "plugin_index": plugin_index,
            "slot_index": slot_index,
            "use_global": use_global_index,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        name = result.get("name", f"Parameter {param_index}")
        new_value = result.get("value", value)
        value_str = result.get("value_string", "")
        return f"Parameter '{name}' set to {new_value:.4f} ({value_str})"

    @mcp.tool()
    def fl_get_preset_count(
        index: int,
        slot_index: int = -1,
        use_global_index: bool = True
    ) -> int:
        """Get the number of presets available for a plugin.

        Args:
            index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        result = conn.send_command("plugins.getPresetCount", {
            "index": index,
            "slot_index": slot_index,
            "use_global": use_global_index,
        })

        if not result.get("success", False) and "error" in result:
            return -1

        return result.get("count", 0)

    @mcp.tool()
    def fl_next_preset(
        index: int,
        slot_index: int = -1,
        use_global_index: bool = True
    ) -> str:
        """Switch to the next preset for a plugin.

        Args:
            index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        result = conn.send_command("plugins.nextPreset", {
            "index": index,
            "slot_index": slot_index,
            "use_global": use_global_index,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        plugin_name = result.get("plugin_name", "Plugin")
        return f"Switched '{plugin_name}' to next preset"

    @mcp.tool()
    def fl_prev_preset(
        index: int,
        slot_index: int = -1,
        use_global_index: bool = True
    ) -> str:
        """Switch to the previous preset for a plugin.

        Args:
            index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        result = conn.send_command("plugins.prevPreset", {
            "index": index,
            "slot_index": slot_index,
            "use_global": use_global_index,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        plugin_name = result.get("plugin_name", "Plugin")
        return f"Switched '{plugin_name}' to previous preset"

    @mcp.tool()
    def fl_get_plugin_color(
        index: int,
        slot_index: int = -1,
        use_global_index: bool = True
    ) -> str:
        """Get the color of a plugin.

        Args:
            index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        result = conn.send_command("plugins.getColor", {
            "index": index,
            "slot_index": slot_index,
            "use_global": use_global_index,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        return result.get("color", "0x0")

    # --- preset-by-name (FL exposes no name lookup: step + read the name) ---------

    def _cmd(action: str, index: int, slot_index: int, use_global: bool) -> dict:
        return get_connection().send_command(
            action, {"index": index, "slot_index": slot_index, "use_global": use_global}
        )

    def _preset_name(index: int) -> str:
        """Current preset name = the channel's name.

        FLEX (and similar) auto-rename the channel after the selected preset, and the
        name refreshes immediately after a paced step. (plugins.getName with
        midi.FPN_Preset is stuck on one value, and getPluginName returns "FLEX".)
        """
        r = get_connection().send_command(
            "probe.exec",
            {"code": f"import channels; print(channels.getChannelName({int(index)}))"},
        )
        return (r.get("stdout") or "").strip()

    def _scan_presets(index: int, slot_index: int, use_global: bool, query: str,
                      max_steps: int, keep_match: bool) -> dict:
        """Step forward with nextPreset, reading the real preset name after each step.

        Each step is a separate command: FL only refreshes the preset name between
        calls (stepping in one script call reads the same name every time).
        Stops at the first case-insensitive substring match of `query` (if given).
        Anything that isn't a kept match is walked back to the starting preset.
        Channel-rack presets only (slot_index -1).
        """
        cnt = _cmd("plugins.getPresetCount", index, slot_index, use_global)
        if cnt.get("error"):
            return {"ok": False, "error": cnt["error"]}
        count = int(cnt.get("count", 0))
        limit = min(max_steps, count) if max_steps > 0 else count
        names = [_preset_name(index)]
        q = query.strip().lower()
        found = 0 if q and q in names[0].lower() else None
        steps = 0
        while found is None and steps < limit - 1:
            r = _cmd("plugins.nextPreset", index, slot_index, use_global)
            time.sleep(_STEP_PAUSE)
            if r.get("error"):
                return {"ok": False, "error": r["error"], "steps_taken": steps,
                        "note": "channel list may have changed; check fl_get_all_channels"}
            steps += 1
            nm = _preset_name(index)
            names.append(nm)
            if q and q in nm.lower():
                found = steps
        keep = found is not None and keep_match
        for _ in range(0 if keep else steps):
            _cmd("plugins.prevPreset", index, slot_index, use_global)
            time.sleep(_STEP_PAUSE / 2)
        out: dict = {"ok": True, "preset_count": count, "steps_scanned": steps,
                     "names": names, "distinct_names": len(set(names))}
        if len(names) > 2 and len(set(names)) == 1:
            out["warning"] = "name did not change while stepping: this plugin does not report preset names"
        if q:
            out["query"] = query
            out["found"] = found is not None
            if found is not None:
                out["match"] = names[found]
                out["steps_from_start"] = found
                out["selected"] = keep
        out["returned_to_start"] = not keep
        return out

    @mcp.tool()
    def fl_find_preset(
        index: int,
        query: str,
        max_steps: int = 0,
        keep_match: bool = True,
        slot_index: int = -1,
        use_global_index: bool = True,
    ) -> dict:
        """Find (and select) a plugin preset BY NAME, e.g. query="guitar" on a FLEX channel.

        FL's API has no preset-name lookup, so this steps with next-preset and reads
        the channel's name (FLEX auto-names the channel after the preset) after each paced step until a case-insensitive substring matches. NOTE: this also replaces any custom channel label with the preset name.
        On a match the preset stays selected (keep_match=True). If nothing matches
        it walks back to the preset it started on. It CHANGES the plugin's preset
        while scanning: don't run it while the user is editing that channel.

        Args:
            index: channel index (0-based; re-check with fl_get_all_channels first).
            query: text to look for in the preset name ("guitar", "acoustic", ...).
            max_steps: stop after this many steps (0 = the plugin's preset count).
            keep_match: leave the matched preset selected.
        """
        return _scan_presets(index, slot_index, use_global_index, query, max_steps, keep_match)

    @mcp.tool()
    def fl_list_preset_names(
        index: int,
        max_steps: int = 0,
        slot_index: int = -1,
        use_global_index: bool = True,
    ) -> dict:
        """List the preset names of a plugin (steps through all, then returns to the start).

        Use to see what a FLEX/plugin bank contains (e.g. is there any guitar?). Same
        caveat as fl_find_preset: it changes the preset temporarily.

        Args:
            index: channel index (0-based).
            max_steps: cap on presets to scan (0 = the plugin's preset count).
        """
        return _scan_presets(index, slot_index, use_global_index, "", max_steps, False)

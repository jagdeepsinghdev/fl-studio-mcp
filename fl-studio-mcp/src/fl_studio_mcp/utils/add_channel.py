"""Add an instrument channel via FL's native Add menu (the ONLY creation path).

The FL Python API (v45) has no channel-creation call, so this clicks
`Add > <instrument>` in the macOS menu bar through System Events (needs
Accessibility permission for the process running the server), waits for the
channel count to grow, then routes / renames / selects the new channel.

Shared by the always-on `fl_channel(action="add")` and the legacy
`fl_add_instrument` / `fl_setup_instrument` (behind LEGACY_TOOLS=1).
Counts and mixer routing come from `channels.getAll` — no probe.exec.
"""

from __future__ import annotations

import subprocess
import time
from typing import Any

from fl_studio_mcp.utils.connection import get_connection

FL_PROC = "OsxFL"


def _channels() -> list[dict] | None:
    r = get_connection().send_command("channels.getAll", timeout=8.0)
    chans = r.get("channels") if isinstance(r, dict) else None
    return chans if isinstance(chans, list) else None


def _click_add_menu_item(name: str) -> tuple[bool, str]:
    esc = name.replace("\\", "\\\\").replace('"', '\\"')
    # FL's Add menu has a Simple (flat) and a Tree mode (Add ▸ Sampler ▸
    # Sampler). Click a top-level leaf if there is one; otherwise find the
    # plugin inside the category submenus. (2026-10-01: in Tree mode the old
    # flat click hit the "Sampler" category and no channel appeared.)
    script = f'''
tell application "System Events" to tell process "{FL_PROC}"
  set addMenu to menu 1 of menu bar item "Add" of menu bar 1
  if exists menu item "{esc}" of addMenu then
    if (count of menus of menu item "{esc}" of addMenu) is 0 then
      click menu item "{esc}" of addMenu
      return "top"
    end if
  end if
  repeat with mi in menu items of addMenu
    if (count of menus of mi) > 0 then
      if exists menu item "{esc}" of menu 1 of mi then
        click menu item "{esc}" of menu 1 of mi
        return name of mi
      end if
    end if
  end repeat
  error "no Add menu item named {esc}"
end tell'''
    try:
        proc = subprocess.run(["osascript", "-e", script],
                              capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return False, "osascript timed out (is a dialog open?)"
    if proc.returncode != 0:
        return False, proc.stderr.strip() or "menu click failed"
    time.sleep(0.5)
    return True, "ok"


def add_instrument(name: str = "FL Keys") -> dict[str, Any]:
    """Click Add > `name`; return the new channel's index once it appears."""
    before = _channels()
    if before is None:
        return {"ok": False, "error": "FL Studio not reachable"}
    ok, err = _click_add_menu_item(name)
    if not ok:
        return {"ok": False, "error": f"Add > {name}: {err}"}
    for _ in range(20):
        time.sleep(0.25)
        after = _channels()
        if after is not None and len(after) > len(before):
            return {"ok": True, "name": name, "index": len(after) - 1,
                    "channel_count": len(after)}
    return {"ok": False,
            "error": f"clicked 'Add > {name}' but no channel appeared (dialog open?)"}


def setup_instrument(plugin: str = "FLEX", label: str | None = None) -> dict[str, Any]:
    """Add `plugin`, route it to the next free mixer track, rename it, select it."""
    label = label or plugin
    added = add_instrument(plugin)
    if not added.get("ok"):
        return added
    idx = added["index"]
    conn = get_connection()

    used = {int(c.get("target_fx_track") or 0) for c in (_channels() or [])
            if c.get("index") != idx}
    track = 1
    while track in used and track < 125:
        track += 1
    conn.send_command("channels.routeToMixer",
                      {"channel_index": idx, "mixer_track": track})
    conn.send_command("channels.setName",
                      {"index": idx, "name": label, "use_global": True})
    conn.send_command("channels.selectOne", {"index": idx, "use_global": True})
    time.sleep(0.3)
    return {"ok": True, "index": idx, "name": label, "instrument": plugin,
            "mixer_track": track, "channel_count": added.get("channel_count")}

"""Load a WAV into a Sampler channel through the Sampler's own Open panel.

Replaces the Edison route for plain samples (2026-10-02): the plugin picker
is a reflowing list and a double-click into it twice confirmed the WRONG row
(Emphasizer, Fruity delay 2). This path never touches the picker:

  channels.showEditor(channel) -> the editor's "Load sample file" button
  (found next to the 'File' label, confirmed by its hover hint) -> FL's native
  Open panel, driven by accessibility (utils/open_panel, proven in C3) ->
  verified: FL renames the channel after the file it loaded -> the caller's
  label is put back.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fl_studio_mcp.utils import custom_menu as cm


def _name(conn, idx: int) -> str:
    chans = conn.send_command("channels.getAll").get("channels", [])
    return next((c.get("name") or "" for c in chans if c.get("index") == idx), "")


def _load_button(name: str):
    """(x, y) of the editor's 'Load sample file' button, hint-confirmed."""
    boxes = cm.ocr_boxes(cm.shot())
    title = next((b for b in boxes if b.text.lower().startswith(name.lower())
                  and "(insert" in b.text.lower()), None)
    files = [b for b in boxes if b.text.strip().lower().startswith("file")
             and (title is None or (0 < b.y - title.y < 140 and abs(b.x - title.x) < 120))]
    for f in files:
        for dx in range(150, 270, 6):
            x, y = f.x + dx, f.cy
            if cm.hint_at(x, y, settle=0.4).lower().startswith("load sample file"):
                return x, y
    return None


def load_sample(conn, channel_index: int, wav: str, label: str = "",
                log=print) -> dict[str, Any]:
    wav_p = Path(wav).expanduser().resolve()
    if not wav_p.is_file():
        return {"ok": False, "error": f"no such file: {wav_p}"}
    if not cm.require_fl_front():
        return {"ok": False, "error": f"FL Studio is not frontmost ({cm.frontmost_app()!r})"}
    name = _name(conn, channel_index)
    label = label or name
    # panel-aware: the editor alone on screen (the roll covered it, 2026-10-02)
    from fl_studio_mcp.utils.fl_panels import restore, show_channel_editor
    panels = show_channel_editor(conn, channel_index)
    try:
        return _load(conn, channel_index, wav_p, name, label, log)
    finally:
        restore(conn, panels)


def _load(conn, channel_index, wav_p, name, label, log) -> dict[str, Any]:
    from fl_studio_mcp.utils.import_midi import _wait
    from fl_studio_mcp.utils.open_panel import drive_open_panel, open_panel_name
    btn = _load_button(name)
    if btn is None:
        # a maximized mixer panel hides the editor (2026-10-02): close it once
        from fl_studio_mcp.utils.edison_flow import uncover
        if uncover(log):
            from fl_studio_mcp.utils.fl_panels import show_channel_editor
            show_channel_editor(conn, channel_index)
            btn = _load_button(name)
    if btn is None:
        return {"ok": False, "error": f"'Load sample file' button not found in the "
                                      f"'{name}' editor; nothing was clicked"}
    cm._click(*btn)
    if not _wait(lambda: open_panel_name() is not None, 6.0):
        return {"ok": False, "error": "the native Open panel did not appear"}
    r = drive_open_panel(str(wav_p))
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error")}
    # proof: FL renames a Sampler after the file it loaded
    stem = wav_p.stem.lower()
    renamed = _wait(lambda: _name(conn, channel_index).lower().startswith(stem), 4.0)
    got = _name(conn, channel_index)
    # Reloading the SAME file does not rename the channel (2026-10-02), so
    # the editor's File field showing the file is the other accepted proof.
    shown = renamed or any(stem in b.text.lower().replace(" ", "")
                           for b in cm.ocr_region(0, 100, 1920, 900, scale=2))
    loaded = renamed or shown
    conn.send_command("channels.setName", {"index": int(channel_index),
                                           "name": label, "use_global": True})
    from fl_studio_mcp.utils.fl_panels import clear_plugins
    clear_plugins()                       # showEditor(_, 0) left it open
    if not loaded:
        return {"ok": False, "error": f"channel did not take the sample (name {got!r})"}
    log(f"loaded {wav_p.name} into channel {channel_index} ('{label}')")
    return {"ok": True, "channel": channel_index, "file": str(wav_p)}


def _close_stuck_panel() -> bool:
    """Escape a native Open panel left open by a failed attempt (loading-samples.md §3)."""
    import subprocess

    from fl_studio_mcp.utils.open_panel import open_panel_name
    if open_panel_name() is None:
        return False
    subprocess.run(["osascript", "-e", 'tell application "System Events" to tell process "OsxFL" '
                    'to set frontmost to true', "-e", "delay 0.3", "-e",
                    'tell application "System Events" to key code 53'], capture_output=True)
    time.sleep(1.0)
    return True


def load_sample_retry(conn, channel_index: int, wav: str, label: str = "",
                      attempts: int = 3, log=print) -> dict[str, Any]:
    """load_sample with the documented fixes automated between tries: close a stuck Open panel,
    close plugin windows, wait. Owner rule: fix + automate every FL miss."""
    from fl_studio_mcp.utils.fl_panels import clear_plugins
    errors = []
    for n in range(1, attempts + 1):
        r = load_sample(conn, channel_index, wav, label, log)
        if r.get("ok"):
            return {**r, "attempts": n, **({"earlier_errors": errors} if errors else {})}
        errors.append(r.get("error"))
        if "no such file" in str(r.get("error")) or "not frontmost" in str(r.get("error")):
            break
        _close_stuck_panel()
        clear_plugins()
        time.sleep(1.0)
    return {"ok": False, "error": errors[-1], "attempts": len(errors), "errors": errors}

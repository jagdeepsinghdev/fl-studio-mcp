---
name: fl-setup
description: Connect to FL Studio and fix setup problems - MIDI bridge, timeouts, Accessibility permission, and the ComposeWithLLM selection (now automated via fl_select_script). Use when FL tools fail/time out, before first use, or when asked to connect/check FL Studio.
---

# FL Studio setup & connection

> Per-session step is **automatic** (first note write per FL process; manual: `fl_select_script(channel_index=…)`)
> and selects the ComposeWithLLM piano-roll script (see `fl-melody` → `references/piano-roll-setup.md`).

The MCP server talks to FL Studio over a virtual MIDI port. On macOS 26 the IAC Driver can be Offline, so a
small helper, `fl-studio-mcp/fl_controller/fl_midi_loop.py`, creates the ports instead (LaunchAgent
`com.flstudiomcp.fl-midi-loop`, starts at login; install it with `fl-studio-mcp/scripts/install-midi-loop.sh`).
No IAC needed. Below, `<label>` = that label (or your `FL_MIDI_LOOP_LABEL`).

## Check connection

1. Call `fl_connection_status`. Healthy = `connected: true`, `port_name: "FL Studio MCP"`.
2. Call `fl_state`. A real answer (transport position like `1:01:00`, channels, patterns) proves the whole chain works.
3. If not connected, call `fl_connect`, then repeat step 2.

## Open / close FL — use `fl_connect(action=...)`

`fl_connect` is the one tool for bringing FL up and taking it down (no domain tool can run
when FL isn't up). It is idempotent and non-blocking — it dismisses the native dialogs that
would otherwise wedge the controller thread:
- `fl_connect()` (no action) → reconnect the MIDI link (original behavior).
- `fl_connect("open")` → launches if down, dismisses the trial **Welcome** dialog (Escape),
  polls until the controller is responsive. A fresh launch may need the MIDI loopback
  (`launchctl kickstart -k gui/$(id -u)/<label>`) before it reports `ready`.
- `fl_connect("close", confirm="no")` → quits and auto-dismisses the native "Save changes?"
  dialog (confirm = `no`|`yes`|`cancel`; it clicks the button by coordinate — these dialogs have no AX tree).
- `fl_connect("force", confirm="yes")` → last-resort hard kill if FL is wedged.

Save is `fl_file("save")`; session state reads are `fl_state`. The in-process `ui`/`screen`
modules do NOT reach these native macOS dialogs (only FL's internal widgets), so `fl_connect`
handles them out-of-band via AX (find window by exact process name `OsxFL`) + cliclick / Escape.

## If it fails, work down this list (cheapest first)

| Symptom | Cause | Fix |
|---|---|---|
| `available_ports: []`, "No MIDI output ports" | Loopback not running | `launchctl kickstart -k gui/$(id -u)/<label>` (or run `.venv/bin/python fl_controller/fl_midi_loop.py &` from `fl-studio-mcp/`) |
| Connected but "Timeout waiting for FL Studio response" | FL's port connection is stale (loopback restarted, or FL started before it) | In FL: Options → MIDI settings → **Refresh device list**. If still failing, restart FL |
| `port_name` is `FL Studio MCP Out` | MCP server running old code | Reconnect the `flstudio` MCP server (`/mcp`) |
| Timeout and MIDI settings show no `FL Studio MCP Bus` | FL launched before loopback | Start loopback, then Refresh device list |
| Input row exists but nothing happens | Controller not set | MIDI settings → Input `FL Studio MCP Bus` → Controller type "FL Studio MCP Controller", Enable on. View → Script output should print "FL Studio MCP Controller initialized" |

Do not conclude "MIDI is broken" because a port is missing from a list: virtual ports only exist while the process that
created them runs. Check that process first (`launchctl print gui/$(id -u)/<label>`).

### Two gotchas confirmed this session
- **Never fire two `flstudio` tool calls in parallel.** The server uses ONE shared `mcp_command.json`
  / `mcp_response.json` file pair, so concurrent calls clobber each other (symptom: `Invalid JSON in
  command file: Extra data`). Always send one call, await its result, then send the next.
- **A single call can time out once and succeed on an identical retry.** The FL→MIDI path has jitter;
  on a lone "Timeout waiting for FL Studio response" retry the SAME call once before assuming the
  connection is dead. (If it times out twice in a row, treat it as the stale-port case above.)

Launch FL if needed: `open -a "FL Studio 2026"`. It shows an audio-input "Warning" dialog on start; click Ok (harmless).
The trial cannot reopen saved projects.

## One-time setup (only if never done before)

1. Make sure the loopback is running (see above) **before** starting FL.
2. FL: Options → MIDI settings → Input → `FL Studio MCP Bus` → Controller type "FL Studio MCP Controller" → Enable.
3. `fl_connect`.

Mechanics: the `fl_midi_loop.py` module docstring (port lifecycle, stale-port recovery).

## Piano roll auto-trigger

Piano roll tools auto-send `Cmd+Opt+Y` to FL Studio. This requires **Accessibility permission**:
System Settings → Privacy & Security → Accessibility → enable for the terminal/agent process running this.

If auto-trigger fails, run **`fl_select_script(channel_index=<target>)`** to (re)select
**ComposeWithLLM** and open the roll (FL 2026 has no Tools → Scripting menu — the tool clicks the
wrench dropdown by coordinate), then trigger again (a write via `fl_notes` auto-sends the trigger,
or the `apply-melody.sh` helper). If the selection reports a miss, pass explicit
`wrench_x`/`script_x`/`script_y`. Alternatively grant the accessibility permission.

## Permissions for the MCP server process (usually your terminal)

- **Accessibility** - System Events menu clicks, `cliclick`, the Cmd+Opt+Y trigger.
- **Screen Recording** - `screencapture` feeds the Vision OCR that proves which channel the
  piano roll shows. Without it the capture is blank and note writes with `channel_index`
  are REFUSED (they cannot prove the target).
- **OCR helper** - `scripts/ocr_text.swift` is compiled on first use to
  `fl-studio-mcp/.generated/bin/ocr_text`; needs `swiftc` (Xcode command line tools).
  `cliclick` must be installed (`brew install cliclick`).
Details: `fl-studio-mcp/docs/UI-AUTOMATION.md`.

## Troubleshooting

- Check FL Studio: View → Script output for controller logs.
- The MCP server logs to its own stdout (visible in the MCP server status).
- If FL Studio was updated/restarted, re-run `fl_connect`.

## Adding a channel (Accessibility permission)

`fl_channel("add", plugin=…, name=…)` adds a channel by clicking FL's native
**Add** menu bar item via System Events (the legacy `fl_setup_instrument` /
`fl_add_instrument` do the same behind `LEGACY_TOOLS=1`). This requires
**Accessibility permission** for the process running the MCP server (the terminal,
in practice). If the call returns an AppleScript/permission error (e.g. "Not
authorized to send Apple events" or the click is a no-op with no new channel),
grant Accessibility in **System Settings → Privacy & Security → Accessibility** for
that terminal/app, then retry. To list available instruments from any terminal:
`cd fl-studio-mcp && ./scripts/fl-add.sh --list`.

Note: the in-window Channel-Rack **"+"** button and the web-rendered **Browser** do
NOT respond to synthetic clicks — only the **menu bar** is scriptable. Use the
`fl_channel("add")` / `fl-add.sh` path, not pynput clicks on those.

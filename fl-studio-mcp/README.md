<!-- mcp-name: io.github.jagdeepsinghdev/fl-studio-mcp -->
# FL Studio MCP Server (Extended Fork)

An MCP (Model Context Protocol) server that enables AI assistants to control FL Studio through MIDI communication and Piano Roll scripts.

> **Fork of [karl-andres/fl-studio-mcp](https://github.com/karl-andres/fl-studio-mcp), with thanks.** The original provided the transport/mixer/channel/plugin/piano-roll foundation (MIT license, retained). This fork extends it: session-safe note writing (roll handshake + title OCR), full pattern/channel/file management, in-engine UI automation, one-call track/song building, and a request-id protocol with audit + controller rollback.

### Quick Demo (from the original project)
dont mind the scuffed audio, i had to clip with my mic bc apple wouldnt let me record desktop audio lol

https://github.com/user-attachments/assets/d4fc668f-9fe5-4ab4-9f18-76cd661029c6

### Original Audio
If you wanted to hear the better audio

https://github.com/user-attachments/assets/c2b1a5e7-1640-41fa-82bc-18ca7cbae9e8

## Features

### Transport Control

- Play, pause, stop playback
- Toggle recording
- Set playback position
- Get song length and position
- Control loop mode (pattern/song)
- Adjust playback speed

### Mixer Control

- Get/set track volume and pan
- Mute/solo tracks
- Arm tracks for recording
- Set track names and colors
- Stereo separation control

### Channel Rack Control

- List all channels
- Get/set channel properties (volume, pan, name, color)
- Mute/solo channels
- Route channels to mixer tracks
- Trigger MIDI notes in real-time
- Step sequencer control (get/set grid bits)

### Plugin Control

- List plugin parameters
- Get/set parameter values
- Navigate presets (next/previous)
- Query plugin info

### Piano Roll Control

- **Add notes** to the piano roll with precise timing
- **Add chords** with a single command
- **Delete specific notes** by MIDI number and time
- **Clear all notes** from the piano roll
- **Read piano roll state** to see all existing notes
- Auto-triggering via keystroke (Cmd+Opt+Y on macOS, Ctrl+Alt+Y on Windows)

## Important Limitations

### Cannot Load Plugins

The FL Studio scripting API does **not** support loading new VST/AU plugins. You can only control parameters of plugins that are already loaded in your project.

### Patterns

Patterns **can** be created and managed: `fl_create_pattern`, `fl_list_patterns`, `fl_select_pattern`, `fl_clone_pattern`. Never jump onto an *empty* pattern by other means: FL opens a modal "Pattern N name" dialog that blocks the controller until a human closes it. Not possible: placing patterns on the playlist (no playlist-clip API); use `fl_add_marker` to label sections on the timeline instead.

## Requirements

- **FL Studio 20.7+** (MIDI Controller Scripting API)
- **Python 3.10+**
- **macOS** or **Windows**
  - macOS: IAC Driver (built-in, needs to be enabled)
  - Windows: [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html)
  - **The fork's UI automation is macOS-only** (roll-title OCR via Vision, System
    Events clicks/keys, automatic piano-roll script selection, `fl_screen`,
    `fl_shortcut`, `fl_channel add`). On Windows only the original
    transport/mixer/channel/plugin tools are expected to work (untested).
- **Screen Recording + Accessibility permission** for the process running the server (macOS)

## Which AI Clients Work With This?

This is a standard [MCP](https://modelcontextprotocol.io) server that talks to clients over stdio — it isn't hardcoded to any one AI vendor. In principle, **any MCP-compatible client can connect**: Claude Desktop, Claude Code, Cursor, Windsurf, Gemini CLI/Gemini's MCP support, OpenAI's Codex CLI/Agents SDK MCP support, etc.

**What's actually tested and auto-configured:** only **Claude Desktop** and **Claude Code**, via `scripts/install_mcp_for_claude.sh` (macOS/Linux) and `scripts/install_mcp_for_claude.ps1` (Windows). Other clients (Gemini, OpenAI-based tools, etc.) are not tested against this server and have no installer support — you'd need to manually add an equivalent MCP server entry to that client's own config, pointing at:

```json
{
  "command": "uv",
  "args": ["run", "--directory", "/path/to/fl-studio-mcp", "fl-studio-mcp"]
}
```

(adjust `/path/to/fl-studio-mcp` to your local clone). If you try this with a non-Claude client, please open an issue with what worked/didn't — the protocol should support it, but it hasn't been verified here.

## Quick Installation

The easiest way to install is using the provided setup script for your platform.

### macOS / Linux

```bash
# Clone the repository
git clone https://github.com/jagdeepsinghdev/fl-studio-mcp.git
cd fl-studio-mcp/fl-studio-mcp      # the server lives in this subfolder

# Run the one-command installer
./install.sh
```

### Windows

```powershell
# Clone the repository
git clone https://github.com/jagdeepsinghdev/fl-studio-mcp.git
cd fl-studio-mcp/fl-studio-mcp      # the server lives in this subfolder

# Allow running local scripts for this user (one-time)
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force

# Run the one-command installer
.\install.ps1
```

`install.ps1` is the Windows counterpart to `install.sh` — same steps, PowerShell instead of bash, and it installs Python 3.12 specifically (required for prebuilt `python-rtmidi` wheels on Windows).

Both installers will:

1. Install [uv](https://github.com/astral-sh/uv) if not present
2. Install Python dependencies
3. Guide you through enabling virtual MIDI ports (IAC Driver on Mac, loopMIDI on Windows)
4. Install the FL Studio MIDI controller script
5. Install the Piano Roll script (ComposeWithLLM)
6. Configure Claude Desktop or Claude Code automatically (`scripts/install_mcp_for_claude.sh` / `scripts/install_mcp_for_claude.ps1`)

> **Windows piano-roll auto-trigger note:** the Piano Roll script is launched by sending FL Studio a keystroke (`Ctrl+Alt+Y`). On Windows this requires briefly foregrounding the FL Studio window, so **FL Studio will pop to the front for a moment** each time a tool like `fl_send_notes` runs. This is expected. See [Piano Roll script not triggering](#piano-roll-script-not-triggering) if it doesn't fire at all.

## Manual Installation

### 1. Install Python Dependencies

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -e .
```

### 2. Enable Virtual MIDI Ports

#### macOS (IAC Driver)

1. Open **Audio MIDI Setup** (search in Spotlight)
2. Press **Cmd+2** or go to **Window > Show MIDI Studio**
3. Double-click on **IAC Driver**
4. Check **"Device is online"**
5. Click **Apply**

#### macOS without a working IAC Driver (macOS 26 "Tahoe")

On macOS 26 the IAC Driver can stay **Offline** in the new *MIDI Studio* view, and the server then fails with
"No MIDI output ports found". You don't need IAC: any process can create virtual CoreMIDI ports (macOS starts
its MIDI server on demand), and FL Studio lists them like any other device.

1. Start the loopback helper (creates `FL Studio MCP`, `FL Studio MCP Bus`, `FL Studio MCP Out`):
   ```bash
   .venv/bin/python fl_controller/fl_midi_loop.py &
   ```
   Virtual ports exist **only while this process runs**. Start it **before** launching FL Studio, and keep it running.
2. In FL Studio: **Options > MIDI settings > Input** > select `FL Studio MCP Bus` > Controller type
   **FL Studio MCP Controller** > turn **Enable** on. (Saved by FL; you do this once.)
3. The server picks the port named exactly `FL Studio MCP` automatically.
4. If the helper restarts while FL is open, FL's port connection goes stale (commands time out). Click
   **Refresh device list** in the MIDI settings.

To start the helper at login, use a LaunchAgent (`RunAtLoad` + `KeepAlive`) that runs the command above with
`WorkingDirectory` set to this repo. Keep the plist minimal: no `EnvironmentVariables` block needed.

#### Windows (loopMIDI)

1. Download and install [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html)
2. Create a virtual port (any name works)
3. Keep loopMIDI running while using FL Studio

### 3. Install FL Studio Scripts

Copy the controller script to FL Studio's Hardware folder:

```bash
# macOS
mkdir -p ~/Documents/Image-Line/FL\ Studio/Settings/Hardware/FLStudioMCP
cp fl_controller/device_FLStudioMCP.py ~/Documents/Image-Line/FL\ Studio/Settings/Hardware/FLStudioMCP/

# Windows
mkdir "%USERPROFILE%\Documents\Image-Line\FL Studio\Settings\Hardware\FLStudioMCP"
copy fl_controller\device_FLStudioMCP.py "%USERPROFILE%\Documents\Image-Line\FL Studio\Settings\Hardware\FLStudioMCP\"
```

Copy the Piano Roll script:

```bash
# macOS
cp scripts/ComposeWithLLM.pyscript ~/Documents/Image-Line/FL\ Studio/Settings/Piano\ roll\ scripts/

# Windows
copy scripts\ComposeWithLLM.pyscript "%USERPROFILE%\Documents\Image-Line\FL Studio\Settings\Piano roll scripts\"
```

### 4. Configure FL Studio

1. **Restart FL Studio** (if it's running)
2. Go to **Options > MIDI Settings**
3. Under **Input**, find your virtual MIDI port (e.g., "IAC Driver Bus 1")
4. Set the **Controller type** to **FLStudioMCP**
5. Enable the port (click to highlight it)

### 5. Configure Claude (or another MCP client)

Add to your Claude Desktop config:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "fl-studio": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/fl-studio-mcp", "fl-studio-mcp"]
    }
  }
}
```

Or for Claude Code, add to your MCP settings (`~/.claude.json`, or run `claude mcp add`).

Using a different MCP-compatible client (Gemini, an OpenAI-based tool, Cursor, etc.)? The same `command`/`args` pair above is all any MCP host needs — add it to that client's own MCP config in whatever format it expects. See [Which AI Clients Work With This?](#which-ai-clients-work-with-this) for what's actually been tested.

### Skills (optional)

The server is complete without them. The repo also ships an **optional** skill pack for Claude
in [`../skills/`](../skills/README.md): FL workflows and gotchas (setup, patterns, piano roll,
mixing, plugins, genres, whole-song building) and a standalone **music-theory** skill (harmony,
rhythm, 808 writing, form, ragas, ear training). None are installed by default. Pick them by name:

```bash
../skills/install.sh                          # list them with descriptions
../skills/install.sh fl-studio fl-melody music-theory   # -> ~/.claude/skills (symlinks)
```

The table in [`skills/README.md`](../skills/README.md) says what each one adds and when to install it.

## Usage

### Running the Server Manually

```bash
# Using uv
uv run fl-studio-mcp

# Or after installation
fl-studio-mcp
```

### Piano Roll Workflow

1. Open FL Studio and select a channel
2. Open the Piano Roll (F7 or double-click the channel)
3. The first time, manually run the script: **Tools > Scripting > ComposeWithLLM**
4. After that, the MCP tools will auto-trigger the script

## Available Tools

### Connection

| Tool | Description |
|------|-------------|
| `fl_connect` | Connect/reconnect to FL Studio |
| `fl_connection_status` | Get connection status |

### Transport

| Tool | Description |
|------|-------------|
| `fl_play` | Start/pause playback |
| `fl_stop` | Stop playback |
| `fl_record` | Toggle recording |
| `fl_get_transport_status` | Get playback/recording state |
| `fl_set_song_position` | Set playback position |
| `fl_get_song_length` | Get song duration |
| `fl_set_loop_mode` | Switch between pattern/song mode |
| `fl_set_playback_speed` | Adjust playback speed (0.25x-4x) |
| `fl_get_swing` / `fl_set_swing` | Global swing, 0.0-1.0 (one project-wide setting) |

### Mixer

| Tool | Description |
|------|-------------|
| `fl_get_mixer_track_count` | Get number of mixer tracks |
| `fl_get_mixer_track_info` | Get track details |
| `fl_get_all_mixer_tracks` | List all tracks |
| `fl_set_track_volume` | Set track volume |
| `fl_set_track_pan` | Set track pan |
| `fl_mute_track` | Mute/unmute track |
| `fl_solo_track` | Solo/unsolo track |
| `fl_arm_track` | Arm track for recording |
| `fl_set_track_name` | Rename track |
| `fl_set_track_color` | Set track color |
| `fl_set_stereo_separation` | Adjust stereo width |
| `fl_get_sends` | List a track's active routes and levels |
| `fl_set_send_level` | Set (and enable) the send level to another track |

### Channels

| Tool | Description |
|------|-------------|
| `fl_get_channel_count` | Get number of channels |
| `fl_get_channel_info` | Get channel details |
| `fl_get_all_channels` | List all channels |
| `fl_get_selected_channel` | Get selected channel |
| `fl_select_channel` | Select/deselect channel |
| `fl_select_one_channel` | Select channel exclusively |
| `fl_trigger_note` | Trigger MIDI note (real-time) |
| `fl_set_channel_volume` | Set channel volume |
| `fl_set_channel_pan` | Set channel pan |
| `fl_mute_channel` | Mute/unmute channel |
| `fl_solo_channel` | Solo/unsolo channel |
| `fl_set_channel_name` | Rename channel |
| `fl_set_channel_color` | Set channel color |
| `fl_route_channel_to_mixer` | Route to mixer track |
| `fl_get_grid_bit` | Get step sequencer step |
| `fl_set_grid_bit` | Set step sequencer step |
| `fl_get_step_sequence` | Get full pattern |
| `fl_set_step_sequence` | Set full pattern |

### Patterns

| Tool | Description |
|------|-------------|
| `fl_list_patterns` | List created patterns (number, name, length) and the active one |
| `fl_create_pattern` | Create a named pattern in the first free slot (does not select it) |
| `fl_select_pattern` | Make an existing pattern active |
| `fl_clone_pattern` | Clone a pattern into the next slot; later patterns shift up |

### Markers

| Tool | Description |
|------|-------------|
| `fl_add_marker` | Add a named timeline marker at a beat position (add-only) |
| `fl_list_markers` | List marker names in time order |

### Plugins

| Tool | Description |
|------|-------------|
| `fl_is_plugin_valid` | Check if plugin exists |
| `fl_get_plugin_name` | Get plugin name |
| `fl_get_plugin_param_count` | Get parameter count |
| `fl_get_plugin_params` | List all parameters |
| `fl_get_plugin_param_value` | Get parameter value |
| `fl_set_plugin_param_value` | Set parameter value |
| `fl_get_preset_count` | Get preset count |
| `fl_next_preset` | Next preset |
| `fl_prev_preset` | Previous preset |
| `fl_get_plugin_color` | Get plugin color |

### Piano Roll

| Tool | Description |
|------|-------------|
| `fl_send_notes` | Add notes to the piano roll (`target_pattern` selects the pattern first) |
| `fl_send_chord` | Add a chord (multiple notes at same time; supports `target_pattern`) |
| `fl_delete_notes` | Delete specific notes |
| `fl_clear_piano_roll` | Clear all notes |
| `fl_get_piano_roll_state` | Read current piano roll notes |
| `fl_trigger_script` | Manually trigger the FL Studio script |
| `fl_get_piano_roll_info` | Get piano roll system info |
| `fl_clear_request_queue` | Cancel pending queued changes |

### Song builder (only the numbers change)

Agent guide: [`AGENT-SONG-BUILDER.md`](AGENT-SONG-BUILDER.md) · skill: `skills/fl-song-builder` · a whole analysed song in one call: [`docs/SONG-TO-FL.md`](docs/SONG-TO-FL.md).

| Tool | Description |
|------|-------------|
| `fl_build_track` | Tempo + pattern length + drums + melody in one call (`melody_channel_index` addresses by index) |
| `fl_write_drums` | Multi-bar drum rows from step numbers; a shorter per-bar list is a cycle repeated to fill `bars` |
| `fl_clean_drums` | Clear kick/snare/hat/clap for `bars` in a pattern |
| `fl_write_melody` | Notes by name per bar (chords as lists, `"-"` rest, `"~"` hold); `bars=N` cycles, `channel_index` addresses by index |
| `fl_write_notes_file` | Queue a large `{midi,time,duration,velocity}` JSON list into one channel (no pasting) |
| `fl_find_preset` / `fl_list_preset_names` | Find/list a plugin preset by name (steps presets, reads the channel name; changes the preset while scanning) |
| `fl_write_808_slides` | 808 line with FL slide notes |

The Piano Roll script applies queued notes to the roll that is OPEN, not the selected channel: do the roll handshake (`CLAUDE.md` rule 6b, `skills/fl-melody`) before writing.

## Example Workflows

### Adjusting a Mix

```text
"Set the volume of mixer track 1 to 80% and pan it slightly left"
```

### Creating a Drum Pattern

```text
"Create a basic kick pattern on channel 0 with kicks on steps 0, 4, 8, and 12"
```

### Adding a Melody to Piano Roll

```text
"Add a C major arpeggio starting at beat 0: C4, E4, G4, C5 - each note quarter duration"
```

### Adding Chords

```text
"Add a C major chord at beat 0, then F major at beat 2, then G major at beat 4"
```

### Automating Plugin Parameters

```text
"List the parameters of the plugin on channel 0 and set the filter cutoff to 50%"
```

## Troubleshooting

### "Not connected to FL Studio"

1. Ensure FL Studio is running
2. Check that the FLStudioMCP controller is enabled in MIDI Settings
3. On Mac, verify IAC Driver is enabled in Audio MIDI Setup, or (macOS 26) that `fl_controller/fl_midi_loop.py` is running (see above)
4. On Windows, verify loopMIDI is running
5. Restart FL Studio after enabling the controller

### "Timeout waiting for FL Studio response"

0. If you use the virtual-port loopback: it restarted after FL started, or FL was launched before it. Click **Refresh device list** in FL's MIDI settings (or restart FL). Also check the server opened `FL Studio MCP`, not `FL Studio MCP Out` (`fl_connection_status`).
1. Make sure FL Studio is in focus
2. Check the Script output window in FL Studio (View > Script output)
3. Verify the controller is receiving MIDI (look for activity in MIDI Settings)

### Piano Roll script not triggering

1. First time: manually run **Tools > Scripting > ComposeWithLLM** in FL Studio
2. On macOS: grant Accessibility permissions when prompted
3. On Windows: the MCP server foregrounds the FL Studio window automatically before sending the hotkey — if FL Studio isn't running or is minimized to the system tray, the trigger can't find it and will fall back to a warning telling you to press the hotkey manually
4. Try pressing Cmd+Opt+Y (macOS) or Ctrl+Alt+Y (Windows) manually to confirm the hotkey itself is bound to the script in FL Studio
5. If you just updated the server code (e.g. pulled a fix to the trigger logic), **fully restart** your MCP client (Claude Desktop/Code) — reconnecting the MCP server alone does not respawn the underlying process, so it can keep running stale code

### No MIDI ports available

- **macOS**: Enable IAC Driver in Audio MIDI Setup
- **Windows**: Install and run loopMIDI

## Architecture

This MCP server uses a hybrid approach:

```text
┌─────────────────┐     ┌─────────────────────────────────────────┐
│   MCP Client    │────▶│           FastMCP Server                │
│  (Claude, etc)  │     │                                         │
└─────────────────┘     │  ┌─────────────────┐  ┌──────────────┐  │
                        │  │ MIDI + JSON     │  │ Piano Roll   │  │
                        │  │ Tools           │  │ Tools (JSON) │  │
                        │  └────────┬────────┘  └──────┬───────┘  │
                        └───────────┼──────────────────┼──────────┘
                                    │                  │
                               MIDI + JSON        JSON Files +
                                    │              Keystroke
                                    ▼                  ▼
                        ┌─────────────────────────────────────────┐
                        │              FL Studio                   │
                        │  ┌──────────────┐  ┌──────────────────┐ │
                        │  │FLStudioMCP   │  │ Piano Roll Script│ │
                        │  │(MIDI Ctrl)   │  │ (ComposeWithLLM) │ │
                        │  └──────────────┘  └──────────────────┘ │
                        └─────────────────────────────────────────┘
```

### How It Works

1. **Transport/Mixer/Channels/Plugins**:
   - MCP server writes command to JSON file
   - Sends MIDI trigger note to FL Studio
   - FL Studio controller script reads JSON, executes API, writes response
   - MCP server reads response

2. **Piano Roll**:
   - MCP server writes note requests to JSON file
   - Sends keystroke (Cmd+Opt+Y on macOS, Ctrl+Alt+Y on Windows) to trigger FL Studio script — on Windows, the FL Studio window is foregrounded first so the keystroke actually reaches it
   - Piano Roll script reads JSON and modifies notes

## Development

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (recommended)

### Setup

```bash
# Install all dependencies including dev extras
uv sync --dev

# Or with pip
pip install -e ".[dev]"
```

### Available Commands

| Command | Description |
|---------|-------------|
| `uv run fl-studio-mcp` | Run the MCP server |
| `uv run ruff check .` | Lint the codebase |
| `uv run ruff check --fix .` | Lint and auto-fix |
| `uv run pytest` | Run tests |

### Project Structure

```
fl-studio-mcp/
├── fl_controller/
│   └── device_FLStudioMCP.py    # FL Studio MIDI controller script (runs inside FL Studio)
├── scripts/
│   ├── setup.sh                  # FL Studio script installer
│   ├── install_mcp_for_claude.sh # Claude config installer (macOS/Linux)
│   ├── install_mcp_for_claude.ps1 # Claude config installer (Windows)
│   └── ComposeWithLLM.pyscript   # Piano Roll script (runs inside FL Studio)
├── src/fl_studio_mcp/
│   ├── server.py                # FastMCP server entry point
│   ├── tools/                   # MCP tool implementations
│   │   ├── channels.py
│   │   ├── mixer.py
│   │   ├── piano_roll.py
│   │   ├── plugins.py
│   │   ├── song_builder.py      # fl_build_track / fl_write_drums / fl_write_melody / fl_clean_drums / fl_write_notes_file
│   │   └── transport.py
│   └── utils/
│       ├── connection.py        # FL Studio connection wrapper
│       ├── fl_trigger.py        # Piano roll keystroke trigger
│       └── midi_connection.py   # MIDI + JSON communication layer
├── install.sh                   # One-command installer (macOS/Linux)
└── install.ps1                  # One-command installer (Windows)
```

## Credits

This project is a fork of, and builds directly on:

- **[karl-andres/fl-studio-mcp](https://github.com/karl-andres/fl-studio-mcp)** (MIT) by Karl Andres — the original FL Studio MCP server: transport, mixer, channel, plugin and piano-roll tools, the MIDI controller script, and the ComposeWithLLM piano-roll integration. Thanks for the foundation!
- [calvinw/fl-studio-mcp](https://github.com/calvinw/fl-studio-mcp) — upstream reference the original is based on (Piano Roll integration approach)

Other dependencies:

- [FL Studio API Stubs](https://github.com/IL-Group/FL-Studio-API-Stubs) - API documentation
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP server framework
- [mido](https://github.com/mido/mido) - MIDI library for Python
- [Image-Line](https://www.image-line.com/) - FL Studio

## License

MIT

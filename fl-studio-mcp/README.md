<!-- mcp-name: io.github.jagdeepsinghdev/fl-studio-mcp -->
# FL Studio MCP Server

An [MCP](https://modelcontextprotocol.io) server that lets an AI assistant control **FL Studio**: transport,
mixer, channels, patterns, the piano roll, plugins, presets, genre packs, vocal chains and audio files.
It runs locally next to FL Studio (stdio) and talks to it through FL's own Python scripting API over
virtual MIDI ports, plus, on macOS, the screen and keyboard for the things the API cannot do.

> **Fork of [karl-andres/fl-studio-mcp](https://github.com/karl-andres/fl-studio-mcp), with thanks.** The original provided the transport/mixer/channel/plugin/piano-roll foundation (MIT license, retained). This fork extends it: session-safe note writing (roll handshake + title OCR), full pattern/channel/file management, in-engine UI automation, one-call track/song building, and a request-id protocol with audit + controller rollback.

> **Status: alpha.** Built and tested on **macOS** with **FL Studio 2026 Producer Edition**. Windows is
> untested beyond the original tools. See the [project page](https://github.com/jagdeepsinghdev/fl-studio-mcp) for releases and the changelog.

## Features

29 tools, each with several actions (`fl_help(domain)` prints the parameters of one). Highlights:

- **Transport and mixer**: play/stop/record, tempo, time signature, swing, loop; volume, pan, sends,
  routing, effects, peak meters, automatic clipping fix.
- **Channels and patterns**: list, add instruments, clone, group, rename, route; create, clone,
  select and resize patterns; step-sequencer rows with per-step velocity/pitch/pan.
- **Piano roll, safely**: notes and chords from text (`"Am F C G"`), melodies as note tokens, MIDI import,
  capture of what you played. Every write first proves which roll is open by reading its on-screen title.
- **Plugins and presets**: list and set parameters, load presets by name, built-in echo/reverb/chorus;
  JSON beat and melody presets (drop in a file, no code).
- **One-call setups**: 16 genre packs with drum kits (`fl_genre`), a vocal chain with buses and sends
  (`fl_vocal`), a whole song folder (`fl_preset load_song`), multi-step recipes with undo (`fl_recipe`).
- **Audio files** (`fl_audio`): tempo, key, chords and 808 root note; cut a section, isolate left/right,
  load into a new Sampler.
- **Seeing and recovering**: `fl_screen` (OCR), FL's own keyboard shortcuts (`fl_shortcut`),
  `fl_connect` `doctor` / `recover` / `tidy` when FL gets stuck.
- **Optional Claude skills** with FL workflows and a music-theory knowledge base (see [Skills](#skills-optional)).

## Important Limitations

- **macOS-only UI automation.** Adding instruments and effects, loading samples, exporting audio and
  selecting the piano-roll script are done by driving FL's menus (OCR, System Events), because FL's
  scripting API cannot do them. FL must be in front and the mouse left alone while they run.
  Needs Accessibility and Screen Recording permission.
- **No playlist clips.** The API cannot place patterns on the playlist, so songs are built one pattern per
  section. Markers can be added and listed, not deleted or renamed.
- **Never jump onto an *empty* pattern by other means** than `fl_pattern(action="select")`: FL opens a
  modal "Pattern N name" dialog that blocks the controller until a human closes it. `fl_pattern create`
  names the next free slot without jumping.
- **The piano-roll script selection resets on every FL launch.** The server redoes it automatically on
  the first note write (`fl_select_script` is the manual call).
- **One call at a time.** The server and FL share one command/response file pair; never run two FL tool
  calls in parallel.
- FL Studio itself is not included, and other editions may lack features the automation relies on.

## Requirements

- **FL Studio 20.7+** (MIDI Controller Scripting API)
- **Python 3.10+**
- **ffmpeg** on your PATH (`brew install ffmpeg`), used by `fl_audio` and the sample tools
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

> **Windows piano-roll auto-trigger note:** the Piano Roll script is launched by sending FL Studio a keystroke (`Ctrl+Alt+Y`). On Windows this requires briefly foregrounding the FL Studio window, so **FL Studio will pop to the front for a moment** each time a note-writing tool runs. This is expected. See [Piano Roll script not triggering](#piano-roll-script-not-triggering) if it doesn't fire at all.

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
in [`skills/`](https://github.com/jagdeepsinghdev/fl-studio-mcp/blob/main/skills/README.md): FL workflows and gotchas (setup, patterns, piano roll,
mixing, plugins, genres, whole-song building) and a standalone **music-theory** skill (harmony,
rhythm, 808 writing, form, ragas, ear training). None are installed by default. Pick them by name:

```bash
../skills/install.sh                          # list them with descriptions
../skills/install.sh fl-studio fl-melody music-theory   # -> ~/.claude/skills (symlinks)
```

The table in [`skills/README.md`](https://github.com/jagdeepsinghdev/fl-studio-mcp/blob/main/skills/README.md) says what each one adds and when to install it.

## Usage

### Running the server manually

```bash
uv run fl-studio-mcp        # from this folder; MCP clients normally start it for you
```

### Writing notes

Ask for notes in plain words ("a minor 4-bar hook on the piano channel"). The server selects the right
piano-roll script once per FL launch, opens the target channel's roll, checks the roll title on screen,
writes the notes, and reads them back. If notes do not land, see
[Troubleshooting](#piano-roll-script-not-triggering).

## Available Tools

Every domain tool takes an `action`; `fl_help(domain)` shows its parameters. The full generated list of
tools, skills and presets is in [`INVENTORY.md`]({R}/blob/main/INVENTORY.md).

| Tool | What it does |
|---|---|
| `fl_state` | read-only snapshot: tempo, transport, patterns, channels, selected channel, piano-roll notes |
| `fl_transport` | `play`, `stop`, `record`, `set_bpm`, `set_timesig`, `set_speed`, `set_swing`, `loop`, `position` |
| `fl_mixer` | `set_vol`, `set_pan`, `route`, `sends`, `add_fx`, `get_info`, `get_sends`, `get_peaks`, `fix_clipping`, `get_eq`, `set_eq` |
| `fl_channel` | `list`, `add`, `clone`, `group`, `rename`, `route`, `mute`, `solo`, `set_vol`, `set_pan`, `set_steps`, `get_steps`, `get_step_param`, `set_step_param`, `load_sample` |
| `fl_pattern` | `create`, `select`, `rename`, `set_len`, `clone`, `chain` |
| `fl_notes` | `write_steps`, `write_chords`, `read_steps`, `clear`, `clear_queue`, `import_midi`, `capture` |
| `fl_select_script` | select the piano-roll script (automatic on the first note write) |
| `fl_plugin` | `list_params`, `set_param`, `load_preset`, `echo`, `reverb`, `chorus`, `get_fx` |
| `fl_preset` | `list`, `load_beat`, `load_melody`, `load_song` |
| `fl_genre` | `list`, `show`, `load`, `load_kit`: one call per genre |
| `fl_vocal` | `setup`, `apply`, `buses`, `loudness`, `recipes`, `show`, `status`, `learn`, `run`, `onboard` |
| `fl_audio` | `analyze`, `extract`, `split`, `load`, `recorder` (needs `ffmpeg`) |
| `fl_recipe` | `validate`, `plan`, `apply`, `status`, `undo`, `export` |
| `fl_file` | `save`, `save_as`, `export`, `open` |
| `fl_delete` | destructive: `channel`, `pattern`, `pattern_data`, `fx`, `roll_notes` |
| `fl_batch` | many controller actions in one MIDI round trip |
| `fl_connect` | FL lifecycle: `status`, `open`, `close`, `save`, `force`, `dismiss_modal`, `doctor`, `recover`, `tidy` |
| `fl_screen` / `fl_shortcut` | see the screen (`look`, `ocr`, `find`, `hint`, `click_text`) / press FL's own shortcuts, guarded |
| `fl_launchpad` | 8x8 grid controller to step sequencer |
| `fl_edison` / `fl_slice_audio` | Edison audio-region flow / slice a file into onset or grid samples |
| `fl_variations` / `fl_list_generated` | rule-based beat variations / list generated presets |
| `fl_probe` / `fl_ui_screen` / `fl_ui_script` / `fl_connection_status` / `fl_help` | discovery, allowlisted `ui.*` calls, UI routines, connection check, docs |

The older single-purpose tools (`fl_play`, `fl_set_bpm`, `fl_send_notes`, ...) are **legacy**: they are
registered only with `LEGACY_TOOLS=1`.

## Example Workflows

Say these to your assistant; the tool calls are what it runs.

**A beat and a hook in one go**
```
fl_genre(action="load", genre="trap")                      # tempo, kit, beat, Keys + Bass, chords, levels
fl_notes(action="write_chords", text="Am F C G", channel_index=5)
```

**Drums by hand**
```
fl_pattern(action="set_len", pattern=1, beats=4)
fl_channel(action="set_steps", index=0, steps=[1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0])
```

**A melody on a new instrument**
```
fl_channel(action="add", plugin="FLEX", name="Piano")
fl_notes(action="write_steps", channel_index=<piano idx>, melody=[["C4","E4","G4","E4"]])
```

**Mix check**
```
fl_mixer(action="get_peaks", track=0)
fl_mixer(action="fix_clipping")      # lowers the master fader just enough
```

**Know a sample before you use it**
```
fl_audio(action="analyze", path="loop.wav")    # tempo (+ whether the estimators agree), key, chords, root
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

1. The server selects the script itself on the first note write after each FL launch. If notes still do not land, run `fl_select_script(channel_index=N)` and check `fl_state` shows the channel's notes
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
├── src/fl_studio_mcp/
│   ├── server.py          # FastMCP entry point, registers the tools
│   ├── tools/             # one module per domain tool (transport_v2.py, mixer_v2.py, notes_v2.py, ...)
│   ├── audio/             # numpy tempo/key/chord analysis, slicer
│   └── utils/             # connection, UI automation, roll session, loaders
├── fl_controller/         # runs INSIDE FL: device_FLStudioMCP.py, fl_midi_loop.py (macOS MIDI ports)
├── scripts/               # setup.sh, install-midi-loop.sh, install_mcp_for_claude.*, ComposeWithLLM.pyscript
├── presets/               # beats, melodies, genres, kits, vocal (JSON; drop in a file, no code)
├── recipes/ shortcuts/ ui_routines/ docs/ tests/
└── install.sh / install.ps1
```

The repository root also has the optional `skills/`, `CHANGELOG.md`, `INVENTORY.md` and the CI/release
workflows: see the [project page](https://github.com/jagdeepsinghdev/fl-studio-mcp).

## Credits

This project is a fork of, and builds directly on:

- **[karl-andres/fl-studio-mcp](https://github.com/karl-andres/fl-studio-mcp)** (MIT) by Karl Andres — the original FL Studio MCP server: transport, mixer, channel, plugin and piano-roll tools, the MIDI controller script, and the ComposeWithLLM piano-roll integration. Thanks for the foundation!
- The original project's demo video: see [its README](https://github.com/karl-andres/fl-studio-mcp#readme).
- [calvinw/fl-studio-mcp](https://github.com/calvinw/fl-studio-mcp) — upstream reference the original is based on (Piano Roll integration approach)

Other dependencies:

- [FL Studio API Stubs](https://github.com/IL-Group/FL-Studio-API-Stubs) - API documentation
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP server framework
- [mido](https://github.com/mido/mido) - MIDI library for Python
- [Image-Line](https://www.image-line.com/) - FL Studio

## License

MIT

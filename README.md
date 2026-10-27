# FL Studio MCP

[![CI](https://github.com/jagdeepsinghdev/fl-studio-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/jagdeepsinghdev/fl-studio-mcp/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/jagdeepsinghdev/fl-studio-mcp?include_prereleases&sort=semver)](https://github.com/jagdeepsinghdev/fl-studio-mcp/releases)
[![License: MIT](https://img.shields.io/github/license/jagdeepsinghdev/fl-studio-mcp)](LICENSE)
[![Stars](https://img.shields.io/github/stars/jagdeepsinghdev/fl-studio-mcp?style=flat)](https://github.com/jagdeepsinghdev/fl-studio-mcp/stargazers)
[![Issues](https://img.shields.io/github/issues/jagdeepsinghdev/fl-studio-mcp)](https://github.com/jagdeepsinghdev/fl-studio-mcp/issues)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![Status](https://img.shields.io/badge/status-alpha-orange)
<!-- after the first PyPI publish, add:
[![PyPI](https://img.shields.io/pypi/v/fl-studio-mcp)](https://pypi.org/project/fl-studio-mcp/) -->

**Control FL Studio from an AI assistant over [MCP](https://modelcontextprotocol.io).** Build beats,
write melodies into the piano roll, mix, and load samples by talking to Claude (or any MCP client);
the server drives FL Studio's own scripting API plus, on macOS, its UI.

- **Transport, mixer, channels, patterns, plugins, presets**: one tool per domain, several actions each.
- **Safe piano-roll writes**: the roll handshake (title proven by OCR) before any note lands.
- **One-call setups**: 16 genre packs (`fl_genre`), vocal chains (`fl_vocal`), a whole song folder (`fl_preset load_song`).
- **Audio files**: tempo, key, chords and 808 root note (`fl_audio analyze`), cut, split, load into a Sampler.
- **Optional skills**: FL workflows and a standalone music-theory skill for Claude. None installed by default.

> **Status: alpha (0.1.x).** Built and tested on **macOS** with **FL Studio 2026 Producer Edition**.
> The UI automation (OCR, System Events) is macOS-only; Windows supports only the original
> transport/mixer/channel/plugin tools and is untested. FL Studio is not included.

## Quick start

```bash
git clone https://github.com/jagdeepsinghdev/fl-studio-mcp.git
cd fl-studio-mcp/fl-studio-mcp
./install.sh                    # uv, dependencies, FL controller + piano-roll script, Claude config
./scripts/install-midi-loop.sh  # macOS: the virtual MIDI ports (LaunchAgent)
```

Then in FL Studio: **Options → MIDI settings** → enable the *FLStudioMCP* controller (input
`FL Studio MCP Bus`), and grant your terminal **Accessibility** and **Screen Recording**
permission. Ask Claude: *"check the FL Studio connection"* (`fl_connect`). Full guide, troubleshooting
and every tool: [`fl-studio-mcp/README.md`](fl-studio-mcp/README.md).

Optional skills for Claude: `skills/install.sh` lists them, `skills/install.sh fl-studio fl-melody music-theory` installs the ones you pick ([what each adds](skills/README.md)).

## Project

| | |
|---|---|
| Releases and version history | [Releases](https://github.com/jagdeepsinghdev/fl-studio-mcp/releases) · [`CHANGELOG.md`](CHANGELOG.md) |
| Everything the server offers (generated) | [`INVENTORY.md`](INVENTORY.md) |
| Report a bug / ask | [Issues](https://github.com/jagdeepsinghdev/fl-studio-mcp/issues) · security: [`SECURITY.md`](SECURITY.md) |
| Contribute | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| For AI agents working on this repo | [`CLAUDE.md`](CLAUDE.md) |

Fork of [karl-andres/fl-studio-mcp](https://github.com/karl-andres/fl-studio-mcp) (MIT), with thanks. See [Credits](fl-studio-mcp/README.md#credits).

> **Pure MCP.** The server does not import or run any other app. `fl_preset load_song` reads a plain
> song folder (`song.json` + presets) that any tool can write
> ([format](fl-studio-mcp/docs/SONG-TO-FL.md)).

## Repository map

The rest of this file is the detailed map of the repo, for contributors and agents.

---

## 1. System at a glance

```
                 ┌─────────────────────────────────────────────┐
   AI / pi ───► │  fl-studio-mcp/  (MCP server, Python)        │
   agent        │   29 MCP tools: transport, mixer, channels,  │
   (skills)     │   piano-roll, plugins, presets, exec-python  │
                 └───────────────┬─────────────────────────────┘
                                  │ MIDI (virtual CoreMIDI ports)
                                  │ "FL Studio MCP" ↔ "FL Studio MCP Bus"
                 ┌───────────────▼─────────────────────────────┐
                 │  FL Studio 2026                             │
                 │   FLStudioMCP device controller (Python)     │
                 │   ComposeWithLLM.pyscript (piano-roll bridge)│
                 └─────────────────────────────────────────────┘
```

Two moving parts:
- **MCP server** (`fl-studio-mcp/`) — what the agent talks to. Runs via `.mcp.json` (`uv run fl-studio-mcp`).
- **FL controller** (`fl-studio-mcp/fl_controller/`) — a Python script *inside* FL that receives commands over a **virtual MIDI port pair** and calls FL's own Python API.

The bridge: a **LaunchAgent** (`com.flstudiomcp.fl-midi-loop`, installed by `fl-studio-mcp/scripts/install-midi-loop.sh`) keeps two virtual CoreMIDI
ports wired together, so commands/requests flow MCP → MIDI → FL.

---

## 2. Directory map

```
<repo>/
├── README.md                     ← THIS FILE (the map)
├── CLAUDE.md                     ← operational rules, script selection (§0), gotchas
├── INVENTORY.md                  ← AUTO-GENERATED list of all tools/skills/presets (gen-inventory.py)
├── fl-studio-mcp/docs/UI-AUTOMATION.md ← how the server drives FL's UI (layers, oracles, flows, debugging)
├── .mcp.json                     ← MCP server registration (uv run fl-studio-mcp)
├── skills/install.sh             ← installs the optional skills you pick (none by default)
│
├── skills/                       ← SKILLS (what the agent reads) — main index + 8 domains; rules in skills/README.md
│   ├── fl-studio/                ← MAIN: start here (domain index, golden rules, transport/channel tools)
│   ├── fl-setup/                 ← connection, MIDI loop, Accessibility, script selection (automatic)
│   ├── fl-presets/               ← ready-made beat/melody JSON presets
│   ├── fl-patterns/              ← drums, step sequencer, pattern length, song sections (+ drum templates)
│   ├── fl-melody/                ← piano-roll notes (+ scales, genre recipes, apply-queue, gotchas)
│   ├── fl-mixing/                ← levels, pan, sends/buses, swing
│   ├── fl-plugins/               ← add instruments, plugin params, preset-by-name
│   ├── fl-genres/                ← one reference per genre (trap/drill, house, lofi, ...)
│   └── fl-song-builder/          ← whole track, ANY instrument: domain-tool recipe + examples
│
└── fl-studio-mcp/                ← THE REPO (MCP server + controller + presets)
    ├── .mcp.json / pyproject.toml / uv.lock
    ├── README.md                 ← repo-level docs (install, MCP tools)
    ├── src/fl_studio_mcp/        ← MCP server source
    │   ├── server.py             ← FastMCP entrypoint
    │   ├── tools/                ← tool groups:
    │   │   ├── transport.py      ← play/stop, BPM, pattern length, loop, speed
    │   │   ├── channels.py       ← channels, routing, step-sequencer, pattern length
    │   │   ├── mixer.py          ← mixer tracks, volume/pan/solo/mute
    │   │   ├── plugins.py        ← plugin params, presets, colors
    │   │   ├── piano_roll.py     ← send/chord/delete/clear notes, trigger, state
    │   │   └── exec_python.py    ← probe_api, exec_python, add/setup instrument,
    │   │                           list/load beat + melody (the preset loaders)
    │   └── utils/                ← connection, fl_trigger, midi_connection
    ├── fl_controller/            ← runs INSIDE FL (copied to FL's Hardware/ dir)
    │   ├── device_FLStudioMCP.py ← the controller (receives MIDI, calls FL API)
    │   └── setup_template.py
    ├── scripts/                  ← setup/install scripts
    │   ├── setup.sh              ← install controller + MIDI loop + pyscript
    │   ├── fl-add.sh             ← add an instrument via the native Add menu
    │   ├── ComposeWithLLM.pyscript
    │   └── install_mcp_for_claude.{sh,ps1}
    ├── apply-melody.sh           ← one command: drain queued melody + play
    ├── build-track.sh            ← ONE COMMAND track builder (see §4)
    └── presets/                  ← THE PRESET SYSTEM (drop-in, no code)
        ├── README.md
        ├── beats/                ← drum-pattern + tempo presets
        │   └── {reggaeton, trap, boom-bap, house, lofi,
        │        nursery-beat, punjabi-banger, drill, ...}.json
        └── melodies/             ← melody + chord presets
            └── {raga-yaman, a-minor-pop, synthwave-hook,
                 nursery-baby, punjabi-hook, drill-c-minor, ...}.json
```

---

## 3. The MCP tools (what the agent can call)

Registered under the `flstudio` server. The default surface is the **domain tools** (one tool, many
`action`s; `fl_help(domain)` prints the full params of each):

| Tool | Actions / use |
|---|---|
| `fl_state` | read-only snapshot: bpm, transport, patterns, channels, selected channel, piano-roll note state (mtime-guarded), session parts |
| `fl_transport` | `play`, `stop`, `record`, `set_bpm`, `set_timesig`, `set_speed`, `set_swing`, `loop`, `position` |
| `fl_mixer` | `set_vol`, `set_pan`, `route`, `sends`, `add_fx`, `get_info`, `get_sends`, `get_peaks`, `fix_clipping` |
| `fl_channel` | `list`, `set_vol`, `set_pan`, `rename`, `route`, `mute`, `solo`, `clone`, `add`, `set_steps` (bool row or `bars=[[1,7],...]`), `get_steps`, `get_step_param`, `set_step_param`, `load_sample` |
| `fl_pattern` | `create`, `select`, `rename`, `set_len`, `clone`, `chain` (build a "Full" pattern from sections) |
| `fl_notes` | `write_steps` (`notes` or `melody=[["C#4","G#4",...]]`), `read_steps`, `clear`, `clear_queue`, `import_midi`; `live_play` / `quantize` not yet wired |
| `fl_select_script` | select the ComposeWithLLM piano-roll script (automatic on first note write; manual call available) |
| `fl_plugin` | `list_params`, `set_param`, `load_preset`, `echo`, `reverb`, `chorus`, `get_fx` |
| `fl_file` | `save`, `save_as`, `export`, `open` |
| `fl_delete` | destructive: `target` = `channel`, `pattern`, `pattern_data`, `fx`, `roll_notes` |
| `fl_batch` | many controller actions in ONE MIDI trip (controller action names, e.g. `channels.setStepSequence`) |
| `fl_preset` | `list`, `load_beat`, `load_melody`, `load_song` (beat ids: reggaeton, trap, boom-bap, house, lofi, nursery-beat, punjabi-banger, drill, … · melody ids: raga-yaman, a-minor-pop, synthwave-hook, nursery-baby, punjabi-hook, drill-c-minor, lofi-a-minor) |
| `fl_variations` / `fl_list_generated` | generate rule-based beat variations / list the generated presets |
| `fl_connect` | FL lifecycle: `status`, `open`, `close`, `save`, `force`, `dismiss_modal` (+ connection / key helpers) |
| `fl_connection_status` | is the controller bridge connected |
| `fl_help` | full docs for one domain tool |
| `fl_probe` / `fl_ui_screen` | discovery: introspect FL's Python modules (`ilmcp`, `api`, `patterns`, `tempo`, `playlist`) / allowlisted `ui.*` calls |
| `fl_launchpad` | `status`, `map`, `calibrate`, `apply`, `light` — 8x8 grid to step sequencer |
| `fl_ui_script` | mouse-free UI routines: allowlisted in-engine `ui.*`/`mixer.*` calls with `expect` oracles (JSON routines in `fl-studio-mcp/ui_routines/`) |
| `fl_shortcut` | FL's own keyboard shortcuts (226 from the manual): `list` (top 10, production-first), `show`, `run`, `batch`; guarded by focus proof, collisions, confirm tier; roll edits read the notes back. Skill: `skills/fl-studio/references/shortcuts.md` |
| `fl_edison` / `fl_slice_audio` | Edison audio-region flow (`status`, `open`, `load_regions`, `send_to_channel`, `run`) / slice an audio file into onset or grid samples |

The ~60 older single-purpose tools (`fl_play`, `fl_set_bpm`, `fl_send_notes`, `fl_build_track`, `fl_add_marker`, ...)
are **legacy**: they are only registered when the server runs with `LEGACY_TOOLS=1` (markers, the swing getter and
the song-builder helpers have no domain equivalent yet). The map legacy -> domain is `LEGACY_TO_DOMAIN` in
`fl-studio-mcp/tests/test_skill_refs.py`. Agent guide for building a track:
[`fl-studio-mcp/AGENT-SONG-BUILDER.md`](fl-studio-mcp/AGENT-SONG-BUILDER.md).

> Full per-tool docs: the domain skills under `skills/` (start at `skills/fl-studio/SKILL.md`) and `fl-studio-mcp/README.md`.

---

## 4. Building a track — the reusable path

A song = **base channels** + **a beat preset** + **a melody preset** + **timing fixes**.

### Fastest via MCP (one call):
```
fl_genre(action="load", genre="trap")   # 16 genres: tempo + beat + Keys/Bass + chords + bass + levels
fl_vocal(action="setup")                 # vocal buses + 9-plugin chain + reverb/delay, 0-miss proof
fl_audio(action="analyze", path="x.wav") # tempo / key / chords / root note of any sample
fl_notes(action="write_chords", text="Am F C G", channel_index=5)
fl_notes(action="capture", seconds=120)  # what you played in -> the pattern
```
Packs: `fl-studio-mcp/presets/genres/`, vocal recipes: `fl-studio-mcp/presets/vocal/`
(edit the JSON, call again). Vision/recovery: `fl_screen`, `fl_connect("doctor"|"recover"|"tidy")`.

### Fastest (one shell command):
```bash
cd fl-studio-mcp
./build-track.sh list                      # see all presets
./build-track.sh punjabi-banger            # beat only
./build-track.sh drill drill-c-minor --piano          # beat + chords + ensure a piano
```
It: ensures channels, loads the beat (**cleared + matched by name** — no crossed channels),
sets **real BPM + pattern length**, queues the melody, **prints a VERIFY table**, and plays.

### Via MCP tools (what the agent does):
```
fl_channel(action="add", plugin="FLEX", name="Piano")   # add+route+rename+select a piano
fl_preset(action="load_beat", preset="punjabi-banger")  # drums
fl_transport(action="set_bpm", bpm=96)                  # REAL tempo
fl_transport(action="set_speed", speed=1.0)
fl_pattern(action="set_len", pattern=1, beats=8)        # match the phrase
fl_preset(action="load_melody", preset="punjabi-hook", channel_index=<piano idx>)
# (selects ComposeWithLLM once per FL process, retargets the roll, queues + triggers)
fl_transport(action="loop", mode="pattern")
fl_transport(action="play")
```

**Add a new preset = drop a JSON file** in `presets/beats/` or `presets/melodies/`
(schema in [`presets/README.md`](fl-studio-mcp/presets/README.md)). No code, no restart.

---

## 5. The per-launch script selection (automatic; read CLAUDE.md §0)

**FL resets the piano-roll script to the default on every launch.** Melody/chord notes
only land when **ComposeWithLLM** is the *selected* piano-roll script. The server now
selects it itself on the first note write in each FL process (writers with `channel_index`
also retarget the roll and prove it by its on-screen title); `fl_select_script` stays
available as a manual call. Details: [`fl-studio-mcp/docs/UI-AUTOMATION.md`](fl-studio-mcp/docs/UI-AUTOMATION.md).
The **beat** (step sequencer) never needed it.

**Also two timing gotchas:** use `fl_transport(action="set_bpm")` for real tempo (not the speed multiplier),
and `fl_pattern(action="set_len")` to match your content (new patterns default to 16 beats →
"plays a bit then silence").

---

## 6. Setup (first time only)

```bash
cd fl-studio-mcp
./scripts/setup.sh              # installs the controller into FL's Hardware/ dir + the ComposeWithLLM pyscript
./scripts/install-midi-loop.sh  # macOS: the MIDI-loop LaunchAgent (virtual ports, no IAC needed)
```
Then in FL: **Hardware → FLStudioMCP → enable**. Bridge troubleshooting: `skills/fl-setup/SKILL.md`.

---

## 7. Current state / known limits
- **FL is Producer Edition** (v26.1.6, licensed 2026-10; was a Trial before) — saved projects reopen; the `ui` key-event tier works (CLAUDE.md §5).
- **Swing** is a single global setting: `fl_transport(action="set_swing")` (0.0-1.0; the getter is legacy `fl_get_swing`, `LEGACY_TOOLS=1`).
- **Not possible via the API** (verified against FL 2026.1.6): placing pattern clips on the playlist, loading plugins/samples, rendering audio, and deleting/renaming/positioning-readback of markers (markers can be *added* and listed).
- **Melody landing** requires the one ComposeWithLLM click (§5).

---

## 8. Repository & hosting

- **MCP registration:** `.mcp.json` at the repo root points pi/agents at the server
  (`uv run fl-studio-mcp`). The server reads presets from `fl-studio-mcp/presets/`.
- **Not committed** (via `.gitignore`): the Python venv, `uv.lock`, the 34 MB upstream demo
  video, secrets, and FL's live runtime JSON files (`mcp_*.json`, `piano_roll_state.json`).

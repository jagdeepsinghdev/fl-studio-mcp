# INVENTORY — single source of truth for the FL Studio MCP workspace

> **AUTO-GENERATED** by `fl-studio-mcp/scripts/gen-inventory.py` on 2026-10-26. 
> Do not hand-edit — change the code, then re-run the script. This exists so the tool/skill/preset lists can never drift from reality.

- **MCP tools:** 110 across 36 groups
- **Skills:** 10
- **Beat presets:** 19 · **Melody presets:** 10

---
## MCP tools

### audio (1)

| Tool | What it does |
|------|--------------|
| `fl_audio` | Audio FILES: analyze | extract | split | load | recorder. |

### batch (1)

| Tool | What it does |
|------|--------------|
| `fl_batch` | Run a list of FL actions in one call — domain actions in ONE MIDI |

### channel (20)

| Tool | What it does |
|------|--------------|
| `fl_get_all_channels` | Get information about all channels in the channel rack. |
| `fl_get_channel_count` | Get the number of channels in the channel rack. |
| `fl_get_channel_info` | Get detailed information about a channel. |
| `fl_get_grid_bit` | Get whether a step is active in the step sequencer. |
| `fl_get_pattern_length` | Get the length of a pattern, in beats. |
| `fl_get_selected_channel` | Get information about the currently selected channel. |
| `fl_get_step_sequence` | Get the step sequence pattern for a channel. |
| `fl_mute_channel` | Mute or unmute a channel. |
| `fl_route_channel_to_mixer` | Route a channel to a specific mixer track. |
| `fl_select_channel` | Select or deselect a channel. |
| `fl_select_one_channel` | Select only one channel, deselecting all others. |
| `fl_set_channel_color` | Set the color of a channel. |
| `fl_set_channel_name` | Set the name of a channel. |
| `fl_set_channel_pan` | Set the pan position of a channel. |
| `fl_set_channel_volume` | Set the volume of a channel. |
| `fl_set_grid_bit` | Set a step in the step sequencer on or off. |
| `fl_set_pattern_length` | Set the length of a pattern, in beats. |
| `fl_set_step_sequence` | Set a complete step sequence pattern for a channel. |
| `fl_solo_channel` | Solo or unsolo a channel. |
| `fl_trigger_note` | Trigger a MIDI note on a channel (real-time, does NOT persist to pattern). |

### channel v2 (1)

| Tool | What it does |
|------|--------------|
| `fl_channel` | Control a FL Studio channel (one tool, 15 actions). |

### connection (2)

| Tool | What it does |
|------|--------------|
| `fl_connect` | Manage the FL connection AND process: open / close / force / reconnect. |
| `fl_connection_status` | Get the current FL Studio connection status. |

### delete (1)

| Tool | What it does |
|------|--------------|
| `fl_delete` | Delete something from the FL Studio project. |

### edison (1)

| Tool | What it does |
|------|--------------|
| `fl_edison` | Edison: load a clip, stamp onset regions, send clip+regions to a Sampler. |

### exec (4)

| Tool | What it does |
|------|--------------|
| `fl_add_instrument` | Add a new instrument channel by clicking FL Studio's macOS "Add" menu. |
| `fl_exec_python` | Execute a Python snippet INSIDE FL Studio's interpreter and return output. |
| `fl_probe_api` | List the callable methods available in a FL Studio Python API module. |
| `fl_setup_instrument` | One-call instrument setup: add the channel, route it, name it, select it. |

### file v2 (1)

| Tool | What it does |
|------|--------------|
| `fl_file` | Control FL Studio project file / export (one tool, 4 actions). |

### genre (1)

| Tool | What it does |
|------|--------------|
| `fl_genre` | ONE CALL per genre: list | show(genre) | load(genre, [dry_run], [level], [kit]) | |

### help v2 (1)

| Tool | What it does |
|------|--------------|
| `fl_help` | Get the full param/action docs for one FL domain tool. |

### launchpad (1)

| Tool | What it does |
|------|--------------|
| `fl_launchpad` | Control a Launchpad-style 8x8 grid against FL's step sequencer. |

### marker (2)

| Tool | What it does |
|------|--------------|
| `fl_add_marker` | Add a named marker on the playlist timeline (e.g. "Verse" at beat 16). |
| `fl_list_markers` | List the arrangement (timeline) markers, in time order. |

### mixer (13)

| Tool | What it does |
|------|--------------|
| `fl_arm_track` | Toggle the recording arm state of a mixer track. |
| `fl_get_all_mixer_tracks` | Get information about all mixer tracks. |
| `fl_get_mixer_track_count` | Get the total number of mixer tracks available. |
| `fl_get_mixer_track_info` | Get detailed information about a specific mixer track. |
| `fl_get_sends` | List the active routes (sends) out of a mixer track and their levels. |
| `fl_mute_track` | Mute or unmute a mixer track. |
| `fl_set_send_level` | Set the send level from one mixer track to another (enabling the route if needed). |
| `fl_set_stereo_separation` | Set the stereo separation of a mixer track. |
| `fl_set_track_color` | Set the color of a mixer track. |
| `fl_set_track_name` | Set the name of a mixer track. |
| `fl_set_track_pan` | Set the pan position of a mixer track. |
| `fl_set_track_volume` | Set the volume of a mixer track. |
| `fl_solo_track` | Solo or unsolo a mixer track. |

### mixer v2 (1)

| Tool | What it does |
|------|--------------|
| `fl_mixer` | Control a FL Studio mixer track (one tool, 21 actions). |

### notes v2 (1)

| Tool | What it does |
|------|--------------|
| `fl_notes` | Control FL Studio piano-roll notes (one tool, 9 actions). |

### pattern (4)

| Tool | What it does |
|------|--------------|
| `fl_clone_pattern` | Clone a pattern (with its notes and steps) into the slot right after it. |
| `fl_create_pattern` | Create a new named pattern (e.g. "Verse", "Chorus") in the first free slot. |
| `fl_list_patterns` | List the project's patterns (name, number, length in beats) and the active one. |
| `fl_select_pattern` | Make an existing pattern the active one (step sequencer and piano roll write here). |

### pattern v2 (1)

| Tool | What it does |
|------|--------------|
| `fl_pattern` | Control FL Studio patterns (one tool, 6 actions). |

### piano roll (9)

| Tool | What it does |
|------|--------------|
| `fl_clear_piano_roll` | Clear all notes from the FL Studio piano roll. |
| `fl_clear_request_queue` | Clear any pending note requests without executing them. |
| `fl_delete_notes` | Delete specific notes from the FL Studio piano roll. |
| `fl_get_piano_roll_info` | Get information about the Piano Roll integration status. |
| `fl_get_piano_roll_state` | Get the current state of notes in the FL Studio piano roll. |
| `fl_send_chord` | Add a chord (multiple simultaneous notes) to the FL Studio piano roll. |
| `fl_send_notes` | Add or replace notes in the FL Studio piano roll. |
| `fl_trigger_script` | Manually trigger FL Studio to process pending note requests. |
| `fl_write_808_slides` | Write an 808 bass line with FL's native slide (portamento) notes. |

### plugin (12)

| Tool | What it does |
|------|--------------|
| `fl_find_preset` | Find (and select) a plugin preset BY NAME, e.g. query="guitar" on a FLEX channel. |
| `fl_get_plugin_color` | Get the color of a plugin. |
| `fl_get_plugin_name` | Get the name of a plugin. |
| `fl_get_plugin_param_count` | Get the number of parameters a plugin has. |
| `fl_get_plugin_param_value` | Get the value of a specific plugin parameter. |
| `fl_get_plugin_params` | Get all parameters of a plugin with their current values. |
| `fl_get_preset_count` | Get the number of presets available for a plugin. |
| `fl_is_plugin_valid` | Check if a plugin exists at the given location. |
| `fl_list_preset_names` | List the preset names of a plugin (steps through all, then returns to the start). |
| `fl_next_preset` | Switch to the next preset for a plugin. |
| `fl_prev_preset` | Switch to the previous preset for a plugin. |
| `fl_set_plugin_param_value` | Set the value of a plugin parameter. |

### plugin v2 (1)

| Tool | What it does |
|------|--------------|
| `fl_plugin` | Control a FL Studio plugin (one tool, 9 actions). |

### preset (1)

| Tool | What it does |
|------|--------------|
| `fl_preset` | Load a beat or melody PRESET, or a whole analysed song (the legacy fl_load_beat / |

### probe (1)

| Tool | What it does |
|------|--------------|
| `fl_probe` | Introspect FL's built-in Python modules (read-only; nothing is called). |

### recipe v2 (1)

| Tool | What it does |
|------|--------------|
| `fl_recipe` | A beat as numbered steps you can apply, edit, re-apply and undo one at a time. |

### screen (1)

| Tool | What it does |
|------|--------------|
| `fl_screen` | Vision on FL's screen (macOS OCR): look | ocr | find | hint | click_text. |

### select script tool (1)

| Tool | What it does |
|------|--------------|
| `fl_select_script` | Select the active piano-roll script (default: 0ComposeWithLLM) for ANY channel. |

### shortcut (1)

| Tool | What it does |
|------|--------------|
| `fl_shortcut` | Press one of FL Studio's own keyboard shortcuts (226 from the manual). |

### slice (1)

| Tool | What it does |
|------|--------------|
| `fl_slice_audio` | Slice an audio file into per-onset or per-grid-step sample |

### song builder (5)

| Tool | What it does |
|------|--------------|
| `fl_build_track` | Whole track in ONE call: tempo, length, drums and melody. Only the numbers vary. |
| `fl_clean_drums` | Clear every drum row (kick/snare/hat/clap) in a pattern: the 'start over' button. |
| `fl_write_drums` | Write a multi-bar drum pattern; you only supply WHICH STEPS hit. |
| `fl_write_melody` | Write a multi-bar melody into a named channel; you only supply the NOTES. |
| `fl_write_notes_file` | Queue a LARGE note list from a JSON file (no pasting hundreds of notes). |

### state (1)

| Tool | What it does |
|------|--------------|
| `fl_state` | One-trip snapshot of the FL Studio session (read-only). |

### transport (12)

| Tool | What it does |
|------|--------------|
| `fl_get_bpm` | Read the project's current tempo in BPM. |
| `fl_get_song_length` | Get the total length of the current song/pattern. |
| `fl_get_swing` | Read the project's global swing amount (0.0 - 1.0). |
| `fl_get_transport_status` | Get current transport status including playback and recording state. |
| `fl_play` | Start or pause FL Studio playback. |
| `fl_record` | Toggle recording mode in FL Studio. |
| `fl_set_bpm` | Set the project's ACTUAL tempo in BPM (not a speed multiplier). |
| `fl_set_loop_mode` | Set the loop mode between pattern and song. |
| `fl_set_playback_speed` | Set the playback speed multiplier. |
| `fl_set_song_position` | Set the playback position in FL Studio. |
| `fl_set_swing` | Set the project's global swing (0.0 = straight, 1.0 = maximum). |
| `fl_stop` | Stop FL Studio playback completely. |

### transport v2 (1)

| Tool | What it does |
|------|--------------|
| `fl_transport` | Control FL Studio playback and tempo (one tool, 9 actions). |

### ui screen (1)

| Tool | What it does |
|------|--------------|
| `fl_ui_screen` | Call one allowlisted FL ui.* getter (PE-era unlock; v10.4b safe set). |

### ui script (1)

| Tool | What it does |
|------|--------------|
| `fl_ui_script` | Run mouse-free FL UI routines (in-engine ui/mixer calls; no clicks). |

### variations (2)

| Tool | What it does |
|------|--------------|
| `fl_list_generated` | List generated variation presets (.generated/{beats,melodies}/). |
| `fl_variations` | Generate N rule-based variations of a beat preset (deterministic; |

### vocal (1)

| Tool | What it does |
|------|--------------|
| `fl_vocal` | Vocal mixing from JSON recipes (presets/vocal/): chains, buses, loudness. |

---
## Skills

Structure: one main index (`fl-studio`) -> domains -> `references/` inside each domain. Rules: `skills/README.md`.

| Skill (domain) | Description | References |
|----------------|-------------|------------|
| `fl-genres` | Genre recipes + one-call packs (trap, drill, hip-hop, boom-bap, lofi, r&b, pop, afrobeats, phonk, punjabi, house, techno, future bass, dnb, dubstep, reggaeton) - tempo, grid, key, chords. Use when the user names a genre or style. | `afrobeats`, `boom-bap`, `drum-and-bass`, `dubstep`, `future-bass`, `hip-hop`, `house`, `lofi`, `phonk`, `pop`, `punjabi`, `reggaeton`, `rnb`, `techno`, `trap` |
| `fl-melody` | Write melodies, basslines, chords and any notes into FL Studio's piano roll (ComposeWithLLM queue, via fl_notes). Includes scales/keys, per-genre note recipes, and fixing "notes didn't land". Use when the user wants notes, a tune, chords or a bass line on any instrument. | `apply-queue`, `chord-practice`, `genre-recipes`, `gotchas`, `melody-practice`, `piano-roll-setup`, `scales` |
| `fl-mixing` | Mix and master in FL Studio - levels, pan, send buses (reverb/delay), EQ/FX, vocal chains (autotune, EQ, compression, de-ess, vocal/reverb/delay buses) and stock-plugin mastering to a LUFS target. Use when balancing levels, adding space, mixing or de-essing vocals, or mastering a track. | `background-vocals`, `eq-and-fx`, `glue-buses`, `mastering-stock`, `vocal-bus-routing`, `vocal-chain`, `vocals` |
| `fl-patterns` | Drums and patterns in FL Studio - step sequencer, multi-bar drum rows, pattern length and phrase sync, song sections (multiple patterns), markers. Use for programming or fixing drums, "loop plays then goes silent", or building Intro/Verse/Chorus. | `drum-templates`, `sections` |
| `fl-plugins` | Instruments and sounds in FL Studio - add an instrument channel (FLEX, FL Keys, Sytrus...), set plugin parameters, and find/select a preset BY NAME (piano, bass, pad, guitar). Use when a channel needs a specific sound or a new instrument. | `instruments`, `loading-samples`, `sound-craft` |
| `fl-presets` | Build FL Studio tracks from reusable presets — genre beats (reggaeton, trap, boom-bap, house, lofi) and melodies (raga, pop, synthwave). Use when the user wants a quick full track, a specific genre beat, a raga/raga-flavored tune, or to add a piano/FLEX channel. The one-call setup + preset loading path. | - |
| `fl-setup` | Connect to FL Studio and fix setup problems - MIDI bridge, timeouts, Accessibility permission, and the ComposeWithLLM selection (now automated via fl_select_script). Use when FL tools fail/time out, before first use, or when asked to connect/check FL Studio. | - |
| `fl-song-builder` | Build a whole multi-bar track in FL Studio with ANY instrument (drums + 808 + lead/keys/pad) using the default domain tools (fl_state, fl_transport, fl_pattern, fl_channel, fl_notes, fl_batch). Use for "make a beat + <instrument> melody", adding a second instrument, or rebuilding drums. | `build-around-a-sample`, `checkpoint-workflow`, `future-style-hook`, `layers-by-style` |
| `fl-studio` | START HERE for any FL Studio task. Main index of the FL skill domains (setup, presets, patterns, melody, mixing, plugins, genres, song-builder), the hard rules, and which skill to open next. Use when the user asks to make, edit, play or mix anything in FL Studio. | `shortcuts`, `transport-channels` |
| `music-theory` | The music-theory brain - fundamentals, scales/modes, chords, harmony, voice leading, jazz reharm, rhythm/meter, melody and 808 writing, form, timbre/orchestration, ragas (Bhairavi, Yaman...), world and genre theory, ear training, reading song analysis. Use for any why/what-notes question, writing original parts in a style, or interpreting an analysis. | `chord-emotion`, `chords`, `ear-training`, `form-and-arrangement`, `fundamentals`, `glossary`, `harmony`, `hit-song-patterns`, `idea-to-record`, `indian-classical-ragas`, `jazz-and-reharmonization`, `learning-from-references`, `melody-and-808`, `melody-layering`, `reading-analysis`, `rhythm`, `scales-and-modes`, `timbre-and-orchestration`, `voice-leading-and-counterpoint`, `world-and-genre-theory` |

> Registered project-wide by `.pi/settings.json` (`"skills": ["skills"]`).

---
## Beat presets (`fl-studio-mcp/presets/beats/`)

| id | name | bpm | swing |
|----|------|-----|-------|
| `afrobeats` | Afrobeats | 104 | 12% |
| `boom-bap` | Boom Bap | 90 | 57% |
| `drill-displaced` | UK Drill — displaced snare (2-bar, 140 BPM) | 140 | 15% |
| `drill` | UK Drill (off-beat kick, 140 BPM) | 140 | 15% |
| `drum-and-bass` | Drum and bass (two-step) | 174 |  |
| `dubstep` | Dubstep (half-time) | 140 |  |
| `future-bass` | Future bass | 150 |  |
| `hip-hop` | Hip-hop (modern) | 95 | 10% |
| `house` | House (four-on-the-floor) | 124 |  |
| `lofi` | Lo-fi (chill, sparse) | 80 | 60% |
| `nursery-beat` | Nursery beat (soft kick + claps, bouncy) | 108 | 10% |
| `phonk` | Phonk | 140 |  |
| `pop` | Pop | 118 |  |
| `punjabi-banger` | Punjabi banger (dhol-flavored, driving pop/rap beat) | 96 | 12% |
| `reggaeton` | Reggaeton (dembow) | 95 |  |
| `rnb` | R&B | 80 | 15% |
| `romantic-minimal` | Romantic / minimal (soft kick, clap on 3, airy hats, 117 BPM) | 117 |  |
| `techno` | Techno (minimal four-on-the-floor) | 132 |  |
| `trap` | Trap (half-time) | 140 |  |

## Melody presets (`fl-studio-mcp/presets/melodies/`)

| id | name | key | bpm | notes |
|----|------|-----|-----|-------|
| `a-minor-pop` | A-minor pop melody (Am F C G) | A minor | 95 | 4 beats |
| `dm-soothing-piano` | D minor soothing piano chords (Dm9 Bbmaj7 Fmaj7 Cmaj9) | D minor | 117 | 64 beats |
| `drill-808-c-minor` | Drill 808 — C minor (roots + slides, Cm-Ab-Fm-G) | C minor | 140 | 8 beats |
| `drill` | Drill — C minor (guitar lead + 808 line + Cm/Am chords) | C minor | 140 | 8 beats |
| `drill-keys-c-minor` | Drill keys — C minor (Cm-Ab-Fm-G stabs + bell top line) | C minor | 140 | 8 beats |
| `lofi-a-minor` | Lofi A-minor (Am7 Fmaj7 C E7) | A minor | 80 | 8 beats |
| `nursery-baby` | Nursery rhyme (original, Cocomelon-style) — bright & bouncy | C major | 108 | 4 beats |
| `punjabi-hook` | Punjabi toori hook (bright, catchy, F minor pentatonic) | F minor pentatonic | 96 | 8 beats |
| `raga-yaman` | Raga Yaman (E Phrygian dominant) — Hijaz line | D | 90 | 4 beats |
| `synthwave-hook` | Synthwave / retrowave hook (E Phrygian) | E Phrygian (D F# A B E) | 110 |  |

---
## Scripts (`fl-studio-mcp/`)

| Script | Where |
|--------|-------|
| `apply-melody.sh` | `fl-studio-mcp` |
| `build-track.sh` | `fl-studio-mcp` |
| `install.sh` | `fl-studio-mcp` |
| `0MCP-Workbench.pyscript` | `scripts/` |
| `ComposeWithLLM.pyscript` | `scripts/` |
| `build_drumkits.py` | `scripts/` |
| `edison_run.py` | `scripts/` |
| `fl-add.sh` | `scripts/` |
| `gen-inventory.py` | `scripts/` |
| `install-midi-loop.sh` | `scripts/` |
| `install_mcp_for_claude.ps1` | `scripts/` |
| `install_mcp_for_claude.sh` | `scripts/` |
| `render_track.py` | `scripts/` |
| `s0_probe.py` | `scripts/` |
| `screen.py` | `scripts/` |
| `setup.sh` | `scripts/` |
| `skill_tool_refs.py` | `scripts/` |


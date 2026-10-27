---
name: fl-presets
description: Build FL Studio tracks from reusable presets — genre beats (reggaeton, trap, boom-bap, house, lofi) and melodies (raga, pop, synthwave). Use when the user wants a quick full track, a specific genre beat, a raga/raga-flavored tune, or to add a piano/FLEX channel. The one-call setup + preset loading path.
---

# FL Studio Presets — beats, melodies, and one-call instrument setup

> **⚠️ First:** read `CLAUDE.md` (repo root) — it has the timing gotchas
> (real BPM via `fl_transport("set_bpm")`, pattern length via `fl_pattern("set_len")`) and the
> ComposeWithLLM selection (automatic on the first note write per FL process; manual
> fallback `fl_select_script`).

The song is built in **three layers**:

1. **Base setup** (deterministic): the 5 drum channels (808 Kick/Clap/HiHat/Snare/Astronomic)
   on mixer tracks 1–5. Already in the project.
2. **Beat preset** (genre): the drum pattern + tempo. Loaded with `fl_channel("set_steps")`.
3. **Melody preset** (raga / pop / hook): piano/FLEX notes + chords. Loaded with
   `fl_notes("write_steps")` into a selected instrument channel.

All tools are on the `flstudio` MCP server. Call `fl_connect` first if not connected.
The **add-instrument** tools need **Accessibility permission** for the process running
the server (the native "Add" menu is driven via System Events).

## The 3-call full track

```
# 1. Get a piano channel (adds FLEX, routes to a free mixer track, names it, selects it)
fl_channel("add")(name="FLEX", label="Piano")

# 2. Genre beat + tempo in one call
fl_channel("set_steps")(preset="reggaeton")        # or trap / boom-bap / house / lofi / lofi-a-minor / ...

# 3. Melody into the selected piano channel
fl_notes("write_steps")(preset="a-minor-pop")    # or raga-yaman / synthwave-hook

# 4. Fix the two timing gotchas, then play
fl_transport("set_bpm")(95)                          # REAL tempo (fl_channel("set_steps") only sets a speed multiplier)
fl_transport("set_speed")(1.0)              # reset speed now that the real BPM is set
fl_pattern("set_len")(1, 4)             # new patterns default to 16 beats; make the loop tight
fl_transport("play")
```

Then tune by ear: `fl_channel("set_vol")`, `fl_mixer("set_pan")`, `fl_transport("set_speed")`.

### The two timing gotchas (read this before calling a track "done")

1. **Real BPM vs speed multiplier.** `fl_channel("set_steps")` scales the *playback speed* to hit the
   preset BPM (FL's old API had no BPM setter). It now exists: **`fl_transport("set_bpm")(bpm)`** sets the
   real tempo (the toolbar box updates). After calling it, reset `fl_transport("set_speed")(1.0)`
   so the two don't stack.
2. **Pattern length.** A brand-new FL pattern is **16 beats**, not 4. A 4-beat (16-step) drum
   pattern in it plays 4 beats then loops 12 beats of silence — it sounds like the beat
   "plays for a bit then goes empty." Fix with `fl_pattern("set_len")(1, 4)`. Verify with
   `fl_pattern("set_len")(1)`.

## Discover what's available

```
fl_plugin  # list_presets (gap)("beats")     # reggaeton, trap, boom-bap, house, lofi
fl_plugin  # list_presets (gap)("melodies")  # raga-yaman, a-minor-pop, synthwave-hook
```

## Instruments
Adding instruments and choosing sounds: **`fl-plugins`** (`references/instruments.md`).

## How the presets are defined

Each preset is a small JSON file in `fl-studio-mcp/presets/`:

- **`beats/<id>.json`** — `bpm`, `swing`, and per-part 16-step boolean `pattern`s keyed
  to the drum channel names. `fl_channel("set_steps")` matches channel names to the channel rack,
  writes each via `fl_channel("set_steps")`, and scales playback speed to the preset BPM.

- **`melodies/<id>.json`** — `key`, `scale`, a `melody` (list of `{note, step, dur, vel}`,
  step in 16ths), and `chords` (list of `{notes[], step, dur}`). `fl_notes("write_steps")` converts
  to the ComposeWithLLM note format and writes to the **selected** channel's piano roll.

**To add a new preset:** create `fl-studio-mcp/presets/beats/<name>.json` (or
`melodies/`), then it's immediately available to `fl_plugin  # list_presets (gap)` / `fl_load_*` —
no code change, no restart.

### Beat preset template
```json
{
  "id": "my-beat",
  "name": "My Genre",
  "bpm": 100,
  "swing": 0.0,
  "channels": {
    "kick":  {"name": "808 Kick",  "pattern": [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0]},
    "snare": {"name": "808 Snare", "pattern": [0,0,0,0, 1,0,0,0, 0,0,0,0, 1,0,0,0]},
    "hat":   {"name": "808 HiHat", "pattern": [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0]}
  }
}
```

### Melody preset template
```json
{
  "id": "my-tune",
  "name": "My Tune",
  "key": "C",
  "bpm": 100,
  "channel": "Piano",
  "melody": [
    {"note": 60, "step": 0,  "dur": 2, "vel": 85},
    {"note": 64, "step": 2,  "dur": 2, "vel": 75}
  ],
  "chords": [
    {"notes": [48, 52, 55, 60], "step": 0, "dur": 4},
    {"notes": [53, 57, 60, 64], "step": 4, "dur": 4}
  ]
}
```

## Notes & gotchas
- Writing a NEW preset: pick the notes with the `music-theory` skill (`skills/music-theory/references/harmony.md`, `skills/music-theory/references/melody-and-808.md`, `skills/music-theory/references/rhythm.md`).

- **Add-instrument needs Accessibility permission** (the app running the MCP server /
  the terminal). If `fl_channel("add")` errors with an AppleScript/permission message,
  grant Accessibility and retry.
- **`fl_notes("write_steps")` writes to the SELECTED channel** — run `fl_channel("add")` (which
  selects it) or `fl_state  # + a channel select` first. The piano roll must have **ComposeWithLLM**
  selected (FL forgets this on quit — see `fl-melody`). If notes don't appear,
  `fl_notes  # auto-triggers ComposeWithLLM` and re-check `fl_notes("read_steps")`.
- **Tempo:** use `fl_transport("set_bpm")(bpm)` for the real tempo (sets FL's actual BPM; the toolbar
  box updates and tempo-synced plugins/exports read it). `fl_channel("set_steps")` also applies a
  playback-speed multiplier as a fallback, so if you then call `fl_transport("set_bpm")`, reset
  `fl_transport("set_speed")(1.0)`. FL's default base is 130 BPM.
- **Swing** — `fl_channel("set_steps")` does **not** set swing automatically; it only reports the
  preset's `swing` value in `swing_note`. Set it yourself with **`fl_transport  # swing (gap)(x)`**
  (0.0–1.0, global) if the genre needs it (boom-bap ~0.57, lofi ~0.60).
- One pattern only: everything plays from the active pattern (Pattern 1). Keep drums and
  melody in the same pattern so they play together.

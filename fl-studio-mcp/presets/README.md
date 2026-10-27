# Presets — beats & melodies

Reusable song-building blocks for the FL Studio MCP server. A track is built in
three layers: a **base setup** (the drum channels, already in the project) + a
**beat preset** (genre / song) + a **melody preset** (raga / pop / hook / song chords).

> **Top-level map:** `README.md` (repo root) · **operational rules:** `CLAUDE.md` (repo root)

## Beat presets (`beats/*.json`)

Loaded with **`fl_preset(action="load_beat", preset="<id>")`** or **`./build-track.sh <id>`**. Each writes its
drum parts to the **matching channel by name** (kick/snare/clap/hat/dhol/…), **clears** all
drums first (no stale residue), and sets the **real BPM** (`fl_set_bpm`).

| id | genre / song | bpm | swing |
|---|---|---|---|
| `reggaeton` | dembow | 95 | – |
| `trap` | half-time | 140 | – |
| `boom-bap` | hip-hop | 90 | 57% |
| `house` | four-on-the-floor | 124 | – |
| `lofi` | chill / sparse | 80 | 60% |
| `nursery-beat` | soft kick+claps (baby) | 108 | 10% |
| `punjabi-banger` | dhol-flavored pop/rap | 96 | 12% |
| `drill` | UK drill (off-beat kick, 8th-note feel) | 140 | 15% |
| `romantic-minimal` | soft/minimal: kick 1 & 11, clap on 3, airy hats (leaves room for a lead) | 117 | – |
| `drill-displaced` | UK drill, **displaced snare** (beat 3 → beat 4), 2-bar | 140 | 15% |

> **Per percussion:** the `channels` object can include any part (kick, snare, clap, hat,
> dhol, …). Each part's `name` must match a real channel in the rack. A `dhol` part writes
> to a channel named "Dhol" (add it with `fl_setup_instrument("SAMPLER", "Dhol")`).
> **Pattern length:** a beat preset may set `"length_beats": N` (default 4) so the loop is
> tight — new FL patterns default to 16 beats, which otherwise trails silence.

## Melody presets (`melodies/*.json`)

Loaded with **`fl_preset(action="load_melody", preset="<id>")`** into the target channel's
piano roll (the open roll is auto-retargeted — see the `fl-melody` skill
(`references/apply-queue.md`)).

| id | key / scale | character |
|---|---|---|
| `raga-yaman` | D — E Phrygian dominant (Hijaz) | cinematic, Eastern / raga |
| `a-minor-pop` | A minor (Am-F-C-G) | singable pop hook |
| `synthwave-hook` | E Phrygian | retrowave drive |
| `nursery-baby` | C major, 108 BPM | original Cocomelon-style, bouncy |
| `punjabi-hook` | F minor pentatonic, 96 BPM | original desi toori hook |
| `dm-soothing-piano` | D minor, 64 beats, 117 BPM | soothing piano chords: Dm9 Bbmaj7 Fmaj7 Cmaj9 x2 |
| `drill-c-minor` | C minor, 8 beats, 140 BPM | dark drill hook: 808 line + Cm/Am(add9) + arpeggio lead |

> A melody preset may set `"length_beats": N` — `fl_preset` sets the pattern to that
> length automatically so a multi-bar phrase loops without trailing silence.

## The one golden rule — phrase length must match

**The pattern length, the drum loop, and every melody/bass/chord phrase must share
the same total phrase length, or the loop drifts out of phase with the drums**
(verified painful: an 8-beat melody over a 4-beat pattern looks fine on paper —
8 is a multiple of 4 — but a 6-beat melody over a 4-beat pattern drifts every
loop, and notes written *past* the pattern length just don't play).

Rules:
1. **Set the pattern length BEFORE writing notes**
   — and make it **long enough for the phrase**: a 2-bar (8-beat) drill phrase
   needs an **8-beat pattern**, because the Channel Rack step grid is only ever
   **16 steps (one 4-beat bar)** — the drums *repeat* across an 8-beat pattern,
   they cannot span it. To write a true 2-bar drum pattern (e.g. the displaced
   snare in `drill-displaced`: beat 3 bar 1, beat 4 bar 2), use two 16-step bars:
   `fl_create_pattern("Bar 1", 4)`, `fl_create_pattern("Bar 2", 4)`, write each
   bar's 16 steps into the matching pattern (via `target_pattern` or
   `fl_select_pattern`), then put both in the Playlist in order.
   (beat presets stay 16 steps on purpose — `fl_preset` load_beat assumes that.) —
   `fl_set_pattern_length` first, then `fl_notes` / `fl_preset` load_melody. If you already wrote notes,
   `fl_clear_piano_roll` and rewrite (notes are written to the open piano roll;
   the pattern length only gates what plays).
2. **Phrase length L beats:** the pattern is L beats; drums (16-step grid) repeat
   `L/4` times across it — L must be a multiple of 4. Every piano-roll phrase
   (bass, chords, lead) must start at beat 0 and end exactly at beat L (last
   note's `time + duration ≤ L`; nothing may spill past the loop point — it
   clips and glitches).
3. **Preset fields:** put `"length_beats": L` in BOTH the beat preset and the
   melody preset when they are meant to be used together. `fl_preset` applies it on both
   loads, so the loop is tight and in sync in two calls.
4. **Always read back** after writing: `fl_get_piano_roll_state` (note times +
   durations) and `fl_get_pattern_length` — confirm the last note ends at L.
5. **MCP 2-second timeouts are common on this bridge** — a timeout is not a
   failure; re-issue the same call, then verify with the readback. Never assume
   a call that timed out did (or did not) land.

## Adding a preset (no code, no restart)

Drop a JSON file in the right folder — `fl_preset(action="list")` and the loaders
pick it up immediately.

**Beat** (`beats/my-beat.json`):
```json
{
  "id": "my-beat", "name": "My Genre", "bpm": 100, "swing": 0.0, "length_beats": 4,
  "channels": {
    "kick":  {"name": "808 Kick",  "pattern": [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0]},
    "snare": {"name": "808 Snare", "pattern": [0,0,0,0, 1,0,0,0, 0,0,0,0, 1,0,0,0]},
    "clap":  {"name": "808 Clap",  "pattern": [0,0,0,0, 1,0,0,0, 0,0,0,0, 1,0,0,0]},
    "hat":   {"name": "808 HiHat", "pattern": [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0]},
    "dhol":  {"name": "Dhol",      "pattern": [1,0,0,1, 0,0,1,0, 1,0,0,1, 0,0,1,0]}
  }
}
```
`pattern` is a 16-element list, 1 = step on. `name` must match a channel in the rack.

**Melody** (`melodies/my-tune.json`):
```json
{
  "id": "my-tune", "name": "My Tune", "key": "C", "bpm": 100, "channel": "Piano",
  "length_beats": 8,
  "melody": [
    {"note": 60, "step": 0, "dur": 2, "vel": 85},
    {"note": 64, "step": 2, "dur": 2, "vel": 75}
  ],
  "chords": [
    {"notes": [48,52,55,60], "step": 0, "dur": 4},
    {"notes": [53,57,60,64], "step": 4, "dur": 4}
  ]
}
```
`note` = MIDI number (60 = C4). `step`/`dur` are in 16th-note steps (4 per beat).
`vel` is 0–127. Chord `notes` are simultaneous; `dur` is the chord length in steps.

## Instruments

`fl_setup_instrument("<name>", "<label>")` adds an instrument (FLEX, FL Keys,
Sytrus, SAMPLER, …), routes it to a free mixer track, names it, and selects it. List
every available instrument name from a terminal:

```
./scripts/fl-add.sh --list
```
(needs Accessibility permission for the calling app)

> **Sampler-based sounds** (dhol, tabla, custom samples): the preset triggers the
> channel's pattern, but the actual *sound* depends on the sample loaded into that
> Sampler channel. Load a dhal/tabla sample into the "Dhol" channel for the real tone.

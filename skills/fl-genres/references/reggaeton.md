# Reggaeton in FL Studio

**Fastest path:** `fl_channel("set_steps")("reggaeton")` writes the exact grid below to the
808 channels and applies a **playback-speed multiplier** (not the real BPM) to reach ~95 BPM.
Right after it, call **`fl_transport("set_bpm")(95)`** + **`fl_transport("set_speed")(1.0)`** so the two don't
stack. Read `fl-presets` for how to pair it with a melody (e.g. `fl_notes("write_steps")("a-minor-pop")`)
and a piano channel (`fl_channel("add")`).

<details><summary>Manual (per-step) version — if you want to tweak individual parts</summary>

Read `fl-studio` for the tool map and `fl-setup` if a call times out. Verify the connection first (`fl_state` must return a position).

**Tempo:** 90-98 BPM. Use `fl_transport("set_bpm")(<target BPM>)` to set the real tempo (the toolbar box updates). It's the only reliable tempo lever; `fl_transport("set_speed")` only plays faster/slower without changing the BPM.

## Drum grid (16 steps, 1 = first step)

| Part | Active steps | `pattern` argument for `fl_channel("set_steps")` |
|---|---|---|
| Kick | 1, 5, 9, 13 | `[true, false, false, false, true, false, false, false, true, false, false, false, true, false, false, false]` |
| Snare | 4, 7, 12, 15 | `[false, false, false, true, false, false, true, false, false, false, false, true, false, false, true, false]` |
| Clap | (none) | `[false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false]` |
| Closed/open hat | 1, 3, 5, 7, 9, 11, 13, 15 | `[true, false, true, false, true, false, true, false, true, false, true, false, true, false, true, false]` |

**Feel:** The dembow rhythm: kick on every beat, snare in a 3+3+2 pattern on steps 4, 7, 12, 15 ('boom-ch-boom-chick'). Bright, crisp snare; 8th hats.

**Swing:** `fl_transport  # swing (gap)(x)` sets FL's *global* swing (0.0–1.0). Usually straight (`0.0`); try 0.1 for a looser dembow. Its scale vs. the MPC-style percentages above is not calibrated: start there, listen, adjust; `fl_state  # swing (gap)` reads it back.

## Steps

1. `fl_state` and map channels by **name** (Kick, Snare/Clap, HiHat). Indexes are 0-based. Don't assume the order.
2. For each part with steps: `fl_channel("set_steps")(channel, pattern)` using the row above. Skip parts marked (none) or clear them by sending 16 `false`.
3. Read each channel back with `fl_channel("get_steps")` and confirm it matches before playing.
4. `fl_transport("loop")("pattern")`, then `fl_transport("play")`. Tell the user what you set, then adjust by ear together.
5. Mix: `fl_channel("set_vol")` (0-1) / `fl_channel("set_pan")`. Loud punchy kick, bright snare with short reverb, hats crisp. Vocals dominate; keep the beat simple and steady.

</details>

## Variations
**Key/scale:** typically A or C minor; natural minor / minor pentatonic. For exact MIDI notes, chord formulas and progressions read `fl-melody` → `references/scales.md`.


Bass stabs on the kicks, a rimshot or clap doubling the snare. Switch to half the hats for the pre-chorus.

## Caveats

- Patterns are the standard conventions for the genre, written from music knowledge. They were **not** auditioned in FL by the assistant; expect to tune by ear.
- Persistent notes need the step sequencer (`fl_channel("set_steps")` / `fl_channel("set_steps")  # one bit`). `fl_channel  # real-time trigger (gap)` is real-time only.
- Melody/bass: use the `fl-melody` skill (piano roll + ComposeWithLLM). It works; the script must be re-selected in the piano roll toolbar each FL session.
- Ask before overwriting a pattern the user may have made: read it with `fl_channel("get_steps")` first.

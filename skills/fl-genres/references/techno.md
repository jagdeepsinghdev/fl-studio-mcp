# Techno in FL Studio

Read `fl-studio` for the tool map and `fl-setup` if a call times out. Verify the connection first (`fl_state` must return a position).

**Tempo:** 128-140 BPM. Use `fl_transport("set_bpm")(<target BPM>)` to set the real tempo (the toolbar box updates). It's the only reliable tempo lever; `fl_transport("set_speed")` only plays faster/slower without changing the BPM.

## Drum grid (16 steps, 1 = first step)

| Part | Active steps | `pattern` argument for `fl_channel("set_steps")` |
|---|---|---|
| Kick | 1, 5, 9, 13 | `[true, false, false, false, true, false, false, false, true, false, false, false, true, false, false, false]` |
| Snare | (none) | `[false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false]` |
| Clap | 13 | `[false, false, false, false, false, false, false, false, false, false, false, false, true, false, false, false]` |
| Closed/open hat | 3, 7, 11, 15 | `[false, false, true, false, false, false, true, false, false, false, true, false, false, false, true, false]` |

**Feel:** Relentless four-on-the-floor. Sparse percussion: clap only on the 4 (step 13) or on 2 and 4 for a less bare version. Off-beat hat drives it; the groove comes from percussion variation, not melody.

**Swing:** `fl_transport  # swing (gap)(x)` sets FL's *global* swing (0.0–1.0). Keep it straight (`0.0`) or very light (≤0.1). Its scale vs. the MPC-style percentages above is not calibrated: start there, listen, adjust; `fl_state  # swing (gap)` reads it back.

## Steps

1. `fl_state` and map channels by **name** (Kick, Snare/Clap, HiHat). Indexes are 0-based. Don't assume the order.
2. For each part with steps: `fl_channel("set_steps")(channel, pattern)` using the row above. Skip parts marked (none) or clear them by sending 16 `false`.
3. Read each channel back with `fl_channel("get_steps")` and confirm it matches before playing.
4. `fl_transport("loop")("pattern")`, then `fl_transport("play")`. Tell the user what you set, then adjust by ear together.
5. Mix: `fl_channel("set_vol")` (0-1) / `fl_channel("set_pan")`. Heavy compressed kick, distorted 'rumble' bassline, lots of reverb/delay on percussion. Long, evolving filter and automation over 16-32 bars.

## Variations
**Key/scale:** typically A or D minor (or any); minimal, repetitive minor. For exact MIDI notes, chord formulas and progressions read `fl-melody` → `references/scales.md`.


Rotate hat/perc patterns every 4 bars. Add a ride or shaker on all 16ths at low volume.

## Caveats

- Patterns are the standard conventions for the genre, written from music knowledge. They were **not** auditioned in FL by the assistant; expect to tune by ear.
- Persistent notes need the step sequencer (`fl_channel("set_steps")` / `fl_channel("set_steps")  # one bit`). `fl_channel  # real-time trigger (gap)` is real-time only.
- Melody/bass: use the `fl-melody` skill (piano roll + ComposeWithLLM). It works; the script must be re-selected in the piano roll toolbar each FL session.
- Ask before overwriting a pattern the user may have made: read it with `fl_channel("get_steps")` first.

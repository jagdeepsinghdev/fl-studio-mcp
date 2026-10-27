# R&B in FL Studio

**One call:** `fl_genre("load", genre="rnb")` (pack `fl-studio-mcp/presets/genres/rnb.json`).
**Tempo:** about 80 BPM (`fl_transport("set_bpm")`; keep speed at 1.0). Swing 0.15.

## Drum grid (16 steps, 1 = first step)

| Part | Active steps | `pattern` for `fl_channel("set_steps")` |
|---|---|---|
| Kick | 1, 4, 11 | `[true, false, false, true, false, false, false, false, false, false, true, false, false, false, false, false]` |
| Snare | 9 | `[false, false, false, false, false, false, false, false, true, false, false, false, false, false, false, false]` |
| Clap | 9 | `[false, false, false, false, false, false, false, false, true, false, false, false, false, false, false, false]` |
| Closed/open hat | 1, 3, 5, 7, 9, 10, 11, 13, 15 | `[true, false, true, false, true, false, true, false, true, true, true, false, true, false, true, false]` |

**Feel:** Laid-back half-time groove, soft kick pattern, snare/clap on step 9, hats with a 16th skip; lush descending 7th chords.

**Key/scale:** major or minor with extended chords (7ths, 9ths). Pack default: Eb major, progression IV7 - iii7 - ii7 - I7 (7, half rhythm); bass plays the roots (sustain).
Theory of the style: `music-theory` -> `references/world-and-genre-theory.md`.

Convention, not auditioned - tune by ear.

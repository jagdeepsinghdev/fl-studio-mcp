# Future bass in FL Studio

**One call:** `fl_genre("load", genre="future-bass")` (pack `fl-studio-mcp/presets/genres/future-bass.json`).
**Tempo:** about 150 BPM (`fl_transport("set_bpm")`; keep speed at 1.0). Swing 0.0.

## Drum grid (16 steps, 1 = first step)

| Part | Active steps | `pattern` for `fl_channel("set_steps")` |
|---|---|---|
| Kick | 1, 11 | `[true, false, false, false, false, false, false, false, false, false, true, false, false, false, false, false]` |
| Snare | 9 | `[false, false, false, false, false, false, false, false, true, false, false, false, false, false, false, false]` |
| Clap | 9 | `[false, false, false, false, false, false, false, false, true, false, false, false, false, false, false, false]` |
| Closed/open hat | 3, 7, 11, 15 | `[false, false, true, false, false, false, true, false, false, false, true, false, false, false, true, false]` |

**Feel:** Half-time drums (snare on step 9) under big chopped 7th chords; the chords carry the drop, sidechain them to the kick.

**Key/scale:** major keys (F, C, G) with 7ths and 9ths. Pack default: F major, progression vi - IV - I - V (7, stab rhythm); bass plays the roots (sustain).
Theory of the style: `music-theory` -> `references/world-and-genre-theory.md`.

Convention, not auditioned - tune by ear.

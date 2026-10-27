# Hip-hop (modern) in FL Studio

**One call:** `fl_genre("load", genre="hip-hop")` (pack `fl-studio-mcp/presets/genres/hip-hop.json`).
**Tempo:** about 95 BPM (`fl_transport("set_bpm")`; keep speed at 1.0). Swing 0.1.

## Drum grid (16 steps, 1 = first step)

| Part | Active steps | `pattern` for `fl_channel("set_steps")` |
|---|---|---|
| Kick | 1, 8, 11 | `[true, false, false, false, false, false, false, true, false, false, true, false, false, false, false, false]` |
| Snare | 5, 13 | `[false, false, false, false, true, false, false, false, false, false, false, false, true, false, false, false]` |
| Clap | 5, 13 | `[false, false, false, false, true, false, false, false, false, false, false, false, true, false, false, false]` |
| Closed/open hat | 1, 3, 5, 7, 9, 11, 13, 15 | `[true, false, true, false, true, false, true, false, true, false, true, false, true, false, true, false]` |

**Feel:** Modern hip-hop: punchy kick on 1 with pushes on 8 and 11, backbeat on 2 and 4, steady 8th hats; leave room for the vocal.

**Key/scale:** A, E or D minor; minor pentatonic / natural minor. Pack default: A minor, progression i - VI - III - VII (triad, whole rhythm); bass plays the roots (sustain).
Theory of the style: `music-theory` -> `references/world-and-genre-theory.md`.

Convention, not auditioned - tune by ear.

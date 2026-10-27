# Scales, Keys & Chords (music theory reference)

> Quick MIDI tables for FL. The full theory (all modes, why they sound the way they do, ragas) is the `music-theory` skill: `skills/music-theory/references/scales-and-modes.md`, `skills/music-theory/references/harmony.md`.

Use this when the `fl-melody` or `fl-genres` skills tell you to write a melody/chord
but don't give exact notes. Everything here is in **MIDI numbers** (what
`fl_notes("write_steps")` / `fl_notes("write_steps")  # several notes at the same time = a chord` expect). `60 = C4 (middle C)`.

## First: pick a key

Unless the user names a key, pick one that suits the genre (table below).
State the key you chose when you tell the user what you wrote.

All scales below are given in **C major / C minor** (root = C, MIDI 60). To move to
another key, transpose every MIDI number by the interval from C to that key's **root**.
(For a *minor* key, use the minor root — e.g. A **minor** = A3 = 57, so transpose by
+9, not +21. +21 is the **A major** / A4 root.)

| Key root (major or minor) | Transpose from C (60) by |
|---|---|
| C | +0 |
| Db | +1 |
| D | +2 |
| Eb | +3 |
| E | +4 |
| F | +5 |
| F# | +6 |
| G | +7 |
| Ab | +8 |
| A | +9 |
| Bb | +10 |
| B | +11 |
| (add 12 per octave up) | |

**Easiest method:** write the melody in the scale table below (rooted on C), then add the
transpose value to every `midi` before calling `fl_notes("write_steps")`.

## Scales (rooted on C, MIDI numbers)

### C major (Ionian) — happy, bright
`C D E F G A B` = `60 62 64 65 67 69 71`
Octave 2: `72 74 76 77 79 81 83`

### C minor (Aeolian) — sad, dark (the workhorse for trap/dark pop)
`C D♭ E♭ F G A♭ B♭` = `60 61 63 65 67 68 70`
Octave 2: `72 73 75 77 79 80 82`

### C major pentatonic — folk, lo-fi, safe (no clashing notes)
`C D E G A` = `60 62 64 67 69`

### C minor pentatonic — blues, rock, rap (very safe)
`C D♭ E♭ G A♭` = `60 61 63 67 68`

### C Dorian — moody, jazzy (lo-fi, DnB liquid)
`C D E♭ F G A B♭` = `60 62 63 65 67 69 70`

### C Lydian — dreamy, floating (ambient, future bass)
`C D E F♯ G A B` = `60 62 64 66 67 69 71`

### Harmonic minor — dramatic, classical (C, D♭, E♭, F, G, A♭, B♮)
`60 61 63 65 67 68 71`

### Natural minor = Aeolian (same as C minor above).

## Chord formulas (intervals from root, in semitones)

Build any chord by adding these to the root MIDI note:

| Chord | Formula (semitones) | Example on C (60) | Example on A (57) |
|---|---|---|---|
| Major (M) | 0, 4, 7 | 60, 64, 67 | 57, 61, 64 |
| Minor (m) | 0, 3, 7 | 60, 63, 67 | 57, 60, 64 |
| Major 7 (M7) | 0, 4, 7, 11 | 60, 64, 67, 71 | 57, 61, 64, 68 |
| Minor 7 (m7) | 0, 3, 7, 10 | 60, 63, 67, 70 | 57, 60, 64, 67 |
| Dominant 7 (7) | 0, 4, 7, 10 | 60, 64, 67, 70 | 57, 61, 64, 67 |
| Minor 9 (m9) | 0, 3, 7, 10, 14 | 60, 63, 67, 70, 74 | 57, 60, 64, 67, 71 |
| Major 9 (M9) | 0, 4, 7, 11, 14 | 60, 64, 67, 71, 74 | 57, 61, 64, 68, 71 |
| Sus 4 | 0, 5, 7 | 60, 65, 67 | 57, 62, 64 |
| Sus 2 | 0, 2, 7 | 60, 62, 67 | 57, 59, 64 |
| Power chord (5) | 0, 7 | 60, 67 | 57, 64 |

For `fl_notes("write_steps")  # several notes at the same time = a chord`, pass the resulting MIDI list as `midi_notes`.

## Common chord progressions (as scale degrees)

Roman numerals → how to build each from the key's root:

| Progression | Feel | Use |
|---|---|---|
| I – V – vi – IV | upbeat, pop | House, pop |
| i – VI – III – VII | epic, emotional | Trap, cinematic |
| i – VII – VI – VII | dark, looping | Trap, DnB |
| I – iv – V – I | simple, folk | Lo-fi, country |
| i – iv – VI – v | sad, wistful | Lo-fi, ballad |
| I – III – IV – III | bright, dance | Disco, reggaeton |
| i – bVII – bVI – v | dramatic minor | Metal, dark |

**To realize a progression:** pick your key's root MIDI (e.g. A minor → root 57 = A3,
or 45 = A2 for bass). For each degree, transpose the root and build the chord with the
formulas above. Example, **A minor, i–VII–VI–VII**:
- i (Am) = 57, 60, 64
- VII (G) = 55, 59, 62
- VI (F) = 53, 57, 60
- VII (G) = 55, 59, 62

## Basslines

- **Bass root** = the chord root, **one or two octaves below** the melody.
  Melody on C4 (60) → bass on C2 (36) or C3 (48).
- Keep bass in the **36–55** range (C2–G3) for 808s; **48–67** for synth bass.
- Follow the chord roots, one note per beat or per chord change.

## Per-genre key & scale suggestions

| Genre | Common keys | Scale / feel |
|---|---|---|
| Reggaeton | A minor, C minor, E minor | natural minor, minor pentatonic |
| Trap | F#, G, A minor (dark) | harmonic/minor pentatonic, sparse |
| Lo-fi | D, F, A minor | Dorian, minor 9ths, jazzy |
| House | A minor, C, F major | minor pentatonic, stabs |
| Techno | any (often Am, Dm) | minimal, repetitive, minor |
| Drum & bass | A, C, F# minor | liquid = Dorian; raw = minor |
| Dubstep | F, G, A minor | minor, half-time; wobble on root |
| Boom bap | A, E minor | natural minor, soul 7ths |

## Quick reference: note names → MIDI (octave 3 & 4)

```
C=48/60  C#=49/61  D=50/62  D#=51/63  E=52/64  F=53/65
F#=54/66 G=55/67  G#=56/68  A=57/69  A#=58/70  B=59/71
(octave 3 = 48-59, octave 4 = 60-71)
```

## How to apply in a melody (worked example)

User: "write a sad A minor melody".
1. Key = A minor → transpose-from-C = **+9** (A3 = 57 is the root; see the key table above).
2. Pick C-minor-pentatonic shape: `60 63 61 67 68` (a simple 5-note phrase).
3. Transpose +9 → `69 72 70 76 77` = `A4 C5 B4 E5 F5`. Keep it lower instead: use
   the shape rooted directly on A3 → `57 60 58 64 65` = `A3 C4 B3 E4 F4`.
4. `fl_notes("write_steps")(notes=[{midi:57,time:0,duration:1}, {midi:60,time:1,duration:1}, ...])`.
5. Read back with `fl_notes("read_steps")`, then `fl_transport("play")`.

Prefer to keep melodies in the **60–79** range (C4–G5) and bass in **36–55**.

# Fundamentals — pitch, notation, intervals, the harmonic series, tuning

This is the shared vocabulary of conservatory theory (rudiments level; ABRSM grade 5 / first-year
undergraduate). Everything else in this domain builds on it.

## 1. Pitch and pitch names

- **Pitch class:** a note name regardless of octave (all Cs). 12 pitch classes in Western
  equal temperament, numbered 0-11 from C (C=0, C#/Db=1 … B=11). This is "pitch-class set"
  notation, used in analysis software and post-tonal theory.
- **Enharmonic equivalents:** same pitch, different spelling (C# = Db, E# = F, B# = C,
  Fb = E, Cb = B, F## = G). **Spelling follows the key and the chord:** in C# minor the
  raised 7th is **B#**, not C; in Db major the 4th is **Gb**, not F#. Correct spelling keeps
  each letter name once per scale.
- **Scientific pitch notation (SPN):** C4 = middle C = 261.63 Hz = MIDI 60. A4 = 440 Hz = MIDI 69.
  **FL Studio's piano roll labels MIDI 60 as C5** (one octave higher than SPN). Some
  hardware/DAWs (Yamaha) also say C3. Always communicate with MIDI numbers when tools differ.
- **Frequency ↔ MIDI:** `f = 440 · 2^((m − 69)/12)`; `m = 69 + 12·log2(f/440)`.
  One semitone = 100 **cents**; an octave = 1200 cents = frequency × 2.

| MIDI | SPN | FL label | Hz |
|---|---|---|---|
| 21 | A0 | A1 | 27.5 (lowest piano key) |
| 24 | C1 | C2 | 32.70 |
| 36 | C2 | C3 | 65.41 |
| 48 | C3 | C4 | 130.81 |
| 60 | C4 | C5 | 261.63 (middle C) |
| 69 | A4 | A5 | 440.00 (tuning A) |
| 72 | C5 | C6 | 523.25 |
| 84 | C6 | C7 | 1046.50 |
| 108 | C8 | C9 | 4186.01 (highest piano key) |

## 2. Notation essentials (reading a score or a lead sheet)

- **Clefs:** treble (G clef, G4 on line 2), bass (F clef, F3 on line 4), alto (C4 on the middle
  line: viola), tenor (C4 on line 4: cello/bassoon/trombone high range).
- **Key signature order:** sharps F C G D A E B; flats B E A D G C F ("Father Charles Goes Down
  And Ends Battle" / reversed). Major key from sharps = a semitone above the last sharp; from
  flats = the second-last flat. Relative minor = 3 semitones (a minor 3rd) below the major.
- **Accidentals:** # sharp, b flat, ♮ natural, x double sharp, bb double flat; they last to the barline.
- **Durations:** whole, half, quarter, eighth, 16th, 32nd; a dot adds half the value; a tie joins.
  Tuplets: triplet = 3 in the time of 2; quintuplet = 5 in the time of 4.
- **Lead sheet / chord symbols:** `Cm7`, `G7(b9)`, `F/A` (slash = bass note), `N.C.` (no chord).
  Full grammar in `chords.md`.
- **Roman numerals:** upper case = major, lower = minor, ° = diminished, ø = half-diminished,
  + = augmented; figures (6, 6/4, 7, 6/5, 4/3, 4/2) = inversion (`chords.md` §inversions).
- **Nashville numbers** (session players): chords as scale-degree numbers (1, 4, 5, 6m) so a
  chart works in any key. Minus = minor, diamond = whole note/let ring, a dot = push.
- **Dynamics:** ppp pp p mp mf f ff fff; hairpins (cresc./dim.). **Articulation:** staccato
  (short), tenuto (full), accent (>), marcato (^), legato slur, fermata (hold).

## 3. Intervals

An interval has a **number** (count letter names, inclusive) and a **quality**.

| Semitones | Interval | Abbr. | Enharmonic | Consonance |
|---|---|---|---|---|
| 0 | perfect unison | P1 | | perfect consonance |
| 1 | minor 2nd | m2 | augmented unison A1 | sharp dissonance |
| 2 | major 2nd | M2 | diminished 3rd d3 | mild dissonance |
| 3 | minor 3rd | m3 | augmented 2nd A2 | imperfect consonance |
| 4 | major 3rd | M3 | diminished 4th d4 | imperfect consonance |
| 5 | perfect 4th | P4 | augmented 3rd A3 | consonant (dissonant above the bass in common practice) |
| 6 | tritone | A4 / d5 | | dissonance (unstable) |
| 7 | perfect 5th | P5 | diminished 6th d6 | perfect consonance |
| 8 | minor 6th | m6 | augmented 5th A5 | imperfect consonance |
| 9 | major 6th | M6 | diminished 7th d7 | imperfect consonance |
| 10 | minor 7th | m7 | augmented 6th A6 | mild dissonance |
| 11 | major 7th | M7 | diminished octave d8 | sharp dissonance |
| 12 | perfect octave | P8 | | perfect consonance |

- **Quality rules:** 2, 3, 6, 7 are major/minor; 1, 4, 5, 8 are perfect. Widen a major/perfect
  by a semitone → augmented; narrow a minor/perfect → diminished.
- **Compound intervals** (beyond the octave): 9th = 2nd + octave (m9 = 13 semitones, M9 = 14),
  11th = 4th + octave (P11 = 17, #11 = 18), 13th = 6th + octave (m13/b13 = 20, M13 = 21). These name chord extensions.
- **Inversion:** interval + its inversion = 9 (numbers) and 12 semitones; major ↔ minor,
  augmented ↔ diminished, perfect ↔ perfect. M3 inverts to m6; P5 to P4; tritone to tritone.
- **Why enharmonic spelling matters:** A2 (C–D#) and m3 (C–Eb) sound the same but function
  differently: A2 is the harmonic-minor 6→7 step; m3 is a chord third.

## 4. The harmonic series (why consonance and timbre work)

A pitched sound contains the **fundamental** plus **overtones** at integer multiples. On C2 (65.4 Hz):

| Partial | × f | Note | Interval from previous |
|---|---|---|---|
| 1 | 1 | C2 | — |
| 2 | 2 | C3 | octave |
| 3 | 3 | G3 | P5 |
| 4 | 4 | C4 | P4 |
| 5 | 5 | E4 (−14 cents) | M3 |
| 6 | 6 | G4 | m3 |
| 7 | 7 | Bb4 (−31 cents) | ~m3 (the "blue" 7th) |
| 8 | 8 | C5 | ~M2 |
| 9 | 9 | D5 | M2 |
| 10 | 10 | E5 | M2 |
| 11 | 11 | F#5 (−49 cents) | ~quarter-tone |
| 13 | 13 | A5 (+41 cents) | |

Consequences used by professionals:
- **Consonance** ≈ shared overtones: the octave (2:1) and fifth (3:2) share the most, so they
  sound most stable. The major triad = partials 4:5:6.
- **Wide intervals at the bottom, close at the top** (as in the series) is the natural voicing
  rule; close 3rds low in the register sound muddy (`voice-leading-and-counterpoint.md` §spacing).
- **Timbre** = the relative strength of the partials. A square wave has odd partials only
  (hollow, clarinet-like); a saw has all (bright, brassy/string); a sine has none (pure: an 808 sub
  is close to a sine, so its pitch is heard mostly through harmonics added by saturation).
- **Missing fundamental:** the ear hears a pitch from its upper partials even if the fundamental
  is absent; that's why a distorted 808 is audible on phone speakers.

## 5. Tuning and temperament

- **12-tone equal temperament (12-TET):** every semitone = 2^(1/12). All keys equally in
  tune and equally slightly out. The standard for all DAW instruments.
- **Just intonation:** pure ratios (5:4 M3 = 386 cents vs 400 in 12-TET). Choirs, string
  quartets and barbershop drift toward it; that's why stacked synth thirds can sound "harsh".
- **Pythagorean:** stacked pure fifths (3:2), with wide M3s (408 c).
- **Historical temperaments** (meantone, well-tempered) give each key a colour; relevant to
  baroque performance.
- **A = 440 Hz** is the standard concert pitch; 432 Hz is a modern myth with no special
  property; orchestras in Europe often tune 442-443.
- **Microtonal systems:** Arabic maqam (quarter tones, `world-and-genre-theory.md`), Indian
  shruti (22 per octave), 24-TET, 19-TET, 31-TET (theory/experimental).
- **Pitch correction targets** (our `pitchfix` step) assume 12-TET; a singer's "blue" notes
  between semitones are expressive, not errors.

## 6. Rhythm vocabulary (full treatment in `rhythm.md`)
Pulse (beat) → meter (grouping of beats) → subdivision (2 = simple, 3 = compound) → rhythm
(durations on top of the grid). Tempo is in BPM; the beat unit depends on the meter (a quarter
in 4/4, a dotted quarter in 6/8).

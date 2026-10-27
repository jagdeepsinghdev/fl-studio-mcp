---
name: music-theory
description: The music-theory brain - fundamentals, scales/modes, chords, harmony, voice leading, jazz reharm, rhythm/meter, melody and 808 writing, form, timbre/orchestration, ragas (Bhairavi, Yaman...), world and genre theory, ear training, reading song analysis. Use for any why/what-notes question, writing original parts in a style, or interpreting an analysis.
---

# Music theory — the main brain

Conservatory-level theory (Western common practice, jazz, pop/production, Hindustani ragas,
world styles), written for making music in this repo. Other skills say *how to put notes into FL*
(`fl-melody`, `fl-patterns`, `fl-genres`, `fl-song-builder`); this one says *which notes, and why*.
Open the ONE reference that matches (topic index below).

## Rule zero: say where every claim comes from
Claude cannot hear audio. The analysis code reads the audio; Claude reads its JSON. Label every
musical statement:

| Label | Means | Example |
|---|---|---|
| **measured** | a number in an analysis file | "two tempo models agree on 122 BPM" |
| **inferred** | theory applied to measured numbers | "notes at C#1 (35 Hz) are an 808, not a lead" |
| **convention** | how the style is usually made, not from this song | "trap snares sit on beat 3" |
| **heard (user)** | the user listened and told us | "the lead is a flute" |

Never present an inference or a convention as heard. For what can't be measured (lead timbre, hat
rolls, ornaments), ask the user to listen to the stem.

## Topic index (tags → file)

| Tags / keywords | Reference |
|---|---|
| pitch, notation, clefs, key signatures, intervals, cents, harmonic series, overtones, tuning, temperament, A440, MIDI ↔ Hz, octave naming | `references/fundamentals.md` |
| scales, modes, dorian, phrygian, lydian, mixolydian, locrian, harmonic/melodic minor, phrygian dominant, pentatonic, blues, whole-tone, diminished, bebop, exotic scales | `references/scales-and-modes.md` |
| chords, triads, 7ths, 9/11/13, alterations, sus, add9, slash chords, quartal, inversions, figured bass, voicings, drop 2, shell, rootless | `references/chords.md` |
| harmony, function, roman numerals, cadences, progressions, sequences, non-chord tones, suspensions, secondary dominants, borrowed chords, neapolitan, augmented 6th, chromatic mediants, modulation, modal harmony, dark progressions, drone | `references/harmony.md` |
| chord emotion, mood, sad / happy / dark / joyful / melancholic / euphoric chords, progression for a feeling, pivot a progression, revoicing for mood, pedal tone, descending bass | `references/chord-emotion.md` |
| voice leading, parallel 5ths, SATB, doubling, tendency tones, counterpoint, species, Fux, guide tones, bass vs melody | `references/voice-leading-and-counterpoint.md` |
| jazz, ii-V-I, chord-scale, tritone sub, reharmonisation, gospel, neo-soul, R&B chords, blues changes, modal jazz | `references/jazz-and-reharmonization.md` |
| melody layering, layers, foundation / core / support / toppings, build order, humanize velocity, hook vs verse energy, resampling, texture layer, call and response between instruments | `references/melody-layering.md` |
| rhythm, tempo math, BPM, half-time, grid, steps, swing, triplets, hat rolls, ghost notes, meter, 6/8, 12/8, odd meters, hemiola, polyrhythm, tresillo | `references/rhythm.md` |
| melody, motif, hook, contour, call and response, counter-melody, arpeggio, 808 lines, slides, turnarounds | `references/melody-and-808.md` |
| form, arrangement, sections, energy curve, transitions, verse/chorus, AABA, binary/ternary/rondo/sonata, period/sentence, sthayi/antara | `references/form-and-arrangement.md` |
| hit songs, what makes a hit, Billboard data, danceability, energy, valence, acousticness, speechiness, predictable vs surprise, A A B A B C, simple melody, lyric repetition and rhyme | `references/hit-song-patterns.md` |
| voice memo, hum an idea, make a sound not find one, synth + voice hybrid, sad ballad to groovy pop flip, swap the instrument, double-track and pan, verse bare, era modelling, tape / vinyl crackle / hum, disco bass, anti-drop, every chorus different, vocal stacking, buried acoustic guitar, artist breakdown (Charlie Puth "Attention") | `references/idea-to-record.md` |
| timbre, orchestration, instrument ranges, frequency spectrum, doubling, synthesis, 808 tuning, mix-as-theory, film-scoring colours | `references/timbre-and-orchestration.md` |
| raga, raag, Bhairavi, Yaman, Bhairav, Kafi, Malkauns, Darbari, thaat, swara, sargam, komal, tivra, vadi, pakad, meend, gamak, tala, teentaal, keherwa, tabla, Carnatic, guitar raga tabs | `references/indian-classical-ragas.md` |
| genre theory: trap, drill, boom-bap, lo-fi, R&B, gospel, pop, K-pop, house, techno, DnB, reggaeton, clave, Afrobeats, Bollywood, Punjabi/bhangra, ghazal, maqam, gamelan, flamenco, Celtic, Balkan, blues, metal, funk | `references/world-and-genre-theory.md` |
| ear training, intervals by ear, scale degrees, transcription, dictation, practice plan | `references/ear-training.md` |
| analysis output, analysis.json, melody.json, drumlab, tempo octave errors, key confusion, which numbers to trust, worked example | `references/reading-analysis.md` |
| reference track, type beat, style vs copying, style sheet, transformation checklist, yt-dlp + orchestrator commands | `references/learning-from-references.md` |
| definitions of any term (Western, Indian, producer) | `references/glossary.md` |

## Workflow: reference track → your own beat
1. **Analyse:** `references/learning-from-references.md` (commands; private use, CLAUDE.md rule 10).
2. **Read the outputs:** `references/reading-analysis.md` (trust table, failure modes, cross-checks).
3. **Sanity-check with theory:** the key against the chords and the bass (`harmony.md`), the tempo
   against hit spacing (`rhythm.md`), the "melody" against its register (`timbre-and-orchestration.md`).
   Fix the *reading*, not the data (rule 12b).
4. **Ask for ears** (`ear-training.md` §8) for everything the data can't give.
5. **Write a style sheet**, then **compose originally** (`learning-from-references.md`).
6. **Build in FL** with `fl-song-builder` / `fl-melody` / `fl-patterns`.

## Quick math
- One beat = `60 / BPM` s; bar (4/4) = 4 beats; 1/16 = beat / 4; 1/8 triplet = beat / 3.
- Frequency = `440 · 2^((midi − 69) / 12)` Hz; 100 cents = 1 semitone.
- **Octave names differ:** MIDI 60 = **C4** in analysis files and these references; FL's piano roll
  labels it **C5**. Always go by MIDI numbers.
- Transpose = add the key's offset from C (C 0, C# 1, D 2 … B 11).

## Who owns what (don't duplicate)
| Fact | Owner |
|---|---|
| Ready-to-type MIDI scale tables in C, key transposition table | `fl-melody` → `references/scales.md` |
| Genre build recipes (BPM, drum steps, FL tools) | `fl-genres` → `references/<genre>.md` |
| Writing notes/drums into FL | `fl-melody`, `fl-patterns`, `fl-song-builder` |
| Mix moves in FL | `fl-mixing` |
| What `fl_audio analyze` returns and how to read it | `references/reading-analysis.md` |
| All theory (why, what notes, what style) | this skill |

Genre values are conventions unless marked tested ("convention, not auditioned"; skills/README.md rule 9).
This domain's references have no line cap (owner decision, 2026-10-03); keep one topic per file.

## References
- `references/fundamentals.md`
- `references/scales-and-modes.md`
- `references/chords.md`
- `references/harmony.md`
- `references/chord-emotion.md`
- `references/voice-leading-and-counterpoint.md`
- `references/jazz-and-reharmonization.md`
- `references/rhythm.md`
- `references/melody-and-808.md`
- `references/melody-layering.md`
- `references/form-and-arrangement.md`
- `references/hit-song-patterns.md`
- `references/idea-to-record.md`
- `references/timbre-and-orchestration.md`
- `references/indian-classical-ragas.md`
- `references/world-and-genre-theory.md`
- `references/ear-training.md`
- `references/reading-analysis.md`
- `references/learning-from-references.md`
- `references/glossary.md`

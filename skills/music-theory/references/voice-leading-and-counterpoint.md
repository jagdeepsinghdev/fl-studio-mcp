# Voice leading and counterpoint

How individual lines move when chords change. This is the craft that separates "chords played
as blocks" from professional writing for keys, strings, choirs and synth pads. Sources of the
rules: Fux (*Gradus ad Parnassum*, species counterpoint), the common-practice chorale style
(Bach chorales; Aldwell/Schachter, Kostka/Payne), and jazz/pop practice.

## 1. Motion types (between any two voices)

| Motion | Description | Effect |
|---|---|---|
| **Contrary** | voices move in opposite directions | strongest independence (best for outer voices) |
| **Oblique** | one voice holds, the other moves | smooth, pedal-like |
| **Similar** | same direction, different intervals | fine, in moderation |
| **Parallel** | same direction, same interval | 3rds/6ths sweet; 5ths/octaves lose independence |

## 2. Common-practice rules (four-part SATB chorale style)

**Ranges:** soprano C4–G5, alto G3–D5 (≈ C5), tenor C3–G4, bass E2–C4 (≈ D4).
**Spacing:** adjacent upper voices (S–A, A–T) ≤ an octave apart; tenor–bass may be wider.
No voice crossing or overlap (a voice shouldn't move past where the neighbouring voice just was).

**Forbidden / avoided:**
1. **Parallel perfect 5ths and octaves** (and unisons) between any two voices: the voices fuse
   and lose independence. (Also contrary 5ths/8ves, "consecutives by contrary motion".)
2. **Direct (hidden) 5ths/8ves** in the *outer* voices: similar motion into a P5/P8 with a leap in
   the soprano.
3. **Doubling the leading tone** (scale degree 7 in V/vii°): it must resolve up, so doubling
   forces parallel octaves.
4. **Doubling chordal 7ths** and other tendency tones.
5. **Augmented-2nd melodic leaps** (in harmonic minor, 6 → #7): avoid or fill in.
6. **Leaps of a 7th or an augmented interval** in one voice.

**Tendency tones (must resolve):**
- **Leading tone (7) → 1** (up a half step), especially in the outer voices.
- **Chordal 7th → down by step** (the 7th of V7 = scale degree 4 → 3).
- **Tritone in V7** (between 3rd and 7th: degrees 7 and 4) resolves inward to 1 and 3 (from the
  diminished 5th) or outward (from the augmented 4th).
- **b6 → 5 down; #4 → 5 up** (augmented-6th chords resolve outward to an octave).

**Doubling:** in root-position triads double the root (best), then the 5th; in first inversion double
any stable tone (often the soprano or the bass note if it isn't a tendency tone); in a cadential 6/4 double
the bass (the 5th).

**Melodic principles for each voice:** mostly steps; after a leap, turn and move by step in the
opposite direction (gap-fill); the climax note occurs once; the inner voices move as little as possible
(keep common tones, move to the nearest chord tone).

## 3. Smooth voice leading (the practical method for keys/pads)

1. **Keep common tones** in the same voice.
2. **Move every other voice to the nearest available chord tone** (usually by step, ideally ≤ 2 semitones).
3. **Bass moves independently**, often by leap (roots), in contrary motion to the soprano.
4. **Top voice = melody**: pick the inversion whose top note gives the smoothest line.

Example, C – Am – F – G (right hand; the bass plays roots):
`C E G` → `C E A` (G→A) → `C F A` (E→F) → `B D G` (C→B, F→D, A→G). Every move ≤ 3 semitones.

Guide-tone lines (jazz): the 3rds and 7ths of successive chords connect by half or whole step:
Dm7 (F, C) → G7 (F, B) → Cmaj7 (E, B). The 7th falls to the next 3rd; the 3rd holds to become the 7th.
That's the most important voice-leading idea in jazz and in R&B keys.

## 4. Species counterpoint (Fux) — the training method

Write a line against a given **cantus firmus** (CF), whole notes:

| Species | Rhythm vs CF | Key rule |
|---|---|---|
| 1st | note against note | only consonances (P1, P5, P8, 3rds, 6ths); begin/end on perfect consonances; no parallel 5ths/8ves; mostly contrary motion |
| 2nd | 2 against 1 | strong beat consonant; the weak beat may be a passing dissonance (by step) |
| 3rd | 4 against 1 | first beat consonant; passing and neighbour tones; the cambiata/double neighbour figures |
| 4th | syncopated (tied) | **suspensions**: prepared consonance → dissonance on the strong beat → resolve down by step (7-6, 4-3 above; 2-3 below) |
| 5th | florid (mixed) | everything combined, with rhythmic variety |

Cadence (2 voices): the 6th expanding to an octave (or the 3rd contracting to a unison), with a
leading-tone approach (the clausula vera).

Why a producer cares: a bass line and a melody written as first/second-species counterpoint sound
"composed" rather than "looped": independent rhythms, contrary motion, consonance on strong beats.

## 5. Two-voice writing for beats (bass + melody, or 808 + lead)

- **Contrary motion** between the 808/bass and the lead at phrase ends.
- **Different rhythms:** if the lead is busy, the bass holds (oblique motion), and vice versa.
- **Strong beats consonant** (3rds, 6ths, 10ths, octaves, 5ths between bass and melody);
  dissonance on weak beats or as a suspension resolving down.
- **Avoid parallel octaves** between the 808 and the lead for long runs (they sound like one
  instrument), unless the doubling is intentional (unison hooks).
- **Register gap:** keep ≥ 1-2 octaves between the bass and the melody; fill the middle with pads only if needed.

## 6. Spacing in the frequency domain (orchestration meets mixing)
- Low register: wide intervals only (octaves, 5ths). See the low interval limits in `chords.md`.
- Mid register: 3rds and 6ths; the most "musical" zone.
- High register: seconds and clusters are acceptable (bells, string harmonics) because high
  partials are far apart in Hz.
- Doubling a line an octave up thickens it without changing the harmony; doubling at the 3rd/6th
  (parallel) sweetens it (pop backing vocals, horn sections).

## 7. Imitation and counterpoint devices
- **Imitation / canon:** a second voice repeats the first at a delay (and possibly another pitch).
  A delay effect on a melody is accidental canon; tempo-synced delays (1/4 dotted) make "ping-pong" lines.
- **Fugue** terms: subject, answer (at the 5th), countersubject, episode, stretto (overlapping entries).
- **Inversion** (upside-down intervals), **retrograde** (backwards), **augmentation/diminution**
  (longer/shorter notes): ways to develop a motif without new material (also `melody-and-808.md`).
- **Ostinato:** a repeated pattern (riff, 808 loop, arpeggio) under changing material: the basis of
  most beat-making, and of passacaglias and grounds in classical music.

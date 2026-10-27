# Melody and 808 writing

Notes are written into FL with `fl-melody` (`fl_notes`). Scales in MIDI: `fl-melody/references/scales.md`.
This page is how to *write* a line that sounds intentional. For the full stack around it (foundation,
support layers, accents, hook vs verse, resampling) see `melody-layering.md`.

## Build from a motif
A **motif** = 2-5 notes with a recognisable rhythm. The whole melody develops it:
1. **State** it (bar 1).
2. **Repeat** it (bar 2) so the ear learns it.
3. **Vary** it (bar 3): same rhythm with different notes, or same notes shifted (sequence a step up/down).
4. **Answer/resolve** it (bar 4): end on a stable note (root, 3rd or 5th) on a strong beat.

Shapes that work: **AABA'** (4 bars), **call and response** (bars 1-2 ask, ending on an unstable
note; bars 3-4 answer, ending on the root), **AAAB** (hypnotic loop with a twist at the end, the
trap favourite).

**Rhythm first.** Tap the rhythm before choosing notes; a good rhythm with 2 pitches beats a
random rhythm with 7. Repeated rhythm makes it memorable; varied pitch keeps it interesting.

## Note choice
- **Strong beats (1 and 3, and the start of a phrase) → chord tones** (root, 3rd, 5th of the
  current chord). They sound stable.
- **Weak beats → passing/neighbour tones** (scale steps between chord tones). They create
  motion and then resolve by step.
- **Tension notes** for emotion, held briefly then resolved: the 2nd (→ root), the 4th (→ 3rd),
  the **b6 → 5** (the dark trap sigh), the **b2 → root** (phrygian menace), the 7th (→ root).
- **Range:** keep a hook inside about an octave (a 6th to a 10th). A small range is singable and
  hypnotic; save the highest note for the emotional peak, once per phrase.
- **Contour:** mostly steps, a few leaps. After a leap (> 4 semitones), move back by step in
  the opposite direction. Arches (up then down) feel complete; descending lines feel sad or final.
- **Space:** rests are part of the melody. In beats, the melody has to leave room for a
  vocalist: 1-2 bar phrases with gaps, not a wall of notes.

## Register and sound choice (don't fight the 808)

| Part | Range (MIDI, 60 = C4) | Note |
|---|---|---|
| 808 / sub | 24-40 (C1-E2) | one note at a time, always |
| Bass (non-808) | 28-48 | roots and 5ths |
| Chords / pads | 48-72 | 2-4 notes, above the bass |
| Lead / bells / flute | 60-90 | the hook; bells read best ~72-90 |
| Counter-melody | an octave away from the lead | answers the lead in its gaps |

Dark-trap palettes (convention): bells, music boxes, flutes, choirs, plucked strings,
detuned pianos, eerie pads. One lead + one texture is enough; more fights the vocal.

## Counter-melody
A second line that **moves when the lead rests** and rests when the lead moves, in a
different register, usually slower (long notes) or simpler (an arpeggio). Use contrary
motion: when the lead goes up, the counter goes down.

## Arpeggios (broken chords)
Bells and plucks often play the chord as an arpeggio: root-3rd-5th-octave up/down in 1/8 or
1/16. Vary it: up-down, skipping a note, a repeated top note, or accenting every 3rd note
(a 3-over-4 feel, `rhythm.md`).

## 808 lines

### Defaults
- **Follow the chord root** on the downbeat of each chord; one note at a time; mono.
- **Rhythm = the kick pattern** (or the kick + a few extra notes). In trap the 808 *is* the kick's tail.
- **Length:** long notes that end just before the next kick/808 hit. Overlap = mud; cut-off = punch.
- **Tune the 808 sample to the key** (most 808 samples are pitched; set the root so MIDI note
  = the played pitch). An out-of-tune 808 is the #1 amateur giveaway.

### Movement that makes 808s musical
- **Octave jumps:** root → root+12 for a bounce (on an off-beat 16th), back down next hit.
- **Fifths:** root → 5th (+7) or → 4th below (−5): strong and safe.
- **Turnarounds** in the last beat or two of a phrase: walk to the next root by scale steps
  (a walk-down b7 → b6 → 5 → root, or a step from below 7 → root). The 808's turnaround is often the
  real hook of a minimal beat.
- **Slides (glides):** one note slides into the next. In FL: the piano roll's **slide** notes,
  or the 808 sampler/3xOsc **porta(mento)** setting with overlapping notes. Slide on the turnaround
  or into the hook, not on every note. Step-sequencer notes can't slide (`fl-melody`).
- **Leave the root most of the time.** Moving every hit sounds like a bass solo; 70-80% root
  with movement at phrase ends is the trap norm (convention).

### 808 over a one-chord drone (e.g. C# minor drone)
Root C# for 3 bars; bar 4: a turnaround from the scale (examples, all C# natural minor):
- B → A → G# → C# (walk down then jump to root, bright)
- E → D# → C# (simple step down)
- A → G# then slide to C# (the b6 → 5 sigh, then home)
Any of these is the *style*. Choose your own order and rhythm (`learning-from-references.md`).

## Checklist before writing notes into FL
1. Key and mode decided (and stated to the user).
2. Chord per bar decided (even if it's one drone chord).
3. Motif rhythm decided (tap it).
4. Strong beats = chord tones; tension resolved by step.
5. Lead register ≥ an octave above the chords; the 808 alone below C2/E2.
6. The phrase ends on a stable note; the turnaround is in the last beat/bar.
7. The motif is yours: not the reference's notes plus rhythm (`learning-from-references.md`).

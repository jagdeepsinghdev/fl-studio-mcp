# Reading analysis output like a musician

Analysis comes from `fl_audio(action="analyze")` (tempo, key, chords, root note; numpy, in
the MCP server) or from a fuller external pipeline (stems, beat grid, note and drum
transcription). Claude reads the numbers; it never hears the audio. This page says which
numbers to trust, how each kind of estimate fails, and how to cross-check one against another.

## The fields that matter

`fl_audio analyze`:

| Field | Holds |
|---|---|
| `tempo.bpm`, `tempo.bpm_alt` | the estimate and its half/double |
| `tempo.autocorr`, `tempo.tempogram`, `tempo.agree` | two independent estimators; `agree=false` = check by ear/tap |
| `key.key`, `key.strength` | e.g. `C# minor`, Pearson r of the key profile (< 0.5 = weak) |
| `chords[]` | `chord`, `start`, `end`, `score` (triads only: 7ths/sus show as the nearest triad) |
| `note` | root of a monophonic hit (808, bass): `note`, `midi`, `hz`, `cents_off` |
| `gaps` | everything the tool is unsure about: read it first |

A full pipeline usually adds: beats/downbeats, stems (vocals / drums / bass / other), a note
transcription of the loudest line, and drum hits per instrument. The checks below say which
of those you need for each question.

## How much to trust each estimate

Measured on public benches with ML models (a fuller pipeline than `fl_audio`); `fl_audio`'s
numpy estimators are lighter and not benched, so treat them as **first guesses** of the same
kind and run the cross-checks below:

| Step | Score | Use it for | Don't use it for |
|---|---|---|---|
| Tempo, allowing half/double | 88% (GiantSteps, 660 clips) | the pulse | — |
| Tempo, exact octave | 43% (same set) | — | the BPM you type in FL, until checked against hit spacing |
| Chords | 85.8% (GuitarSet, detected beats) | the progression | rare chords (dim/sus get weak labels) |
| Key | not benched | a first guess | final answer: check it against the chords and bass |
| Kick hits | F1 0.86 | kick placement | — |
| Snare hits | F1 0.34 | rough backbeat position | exact pattern, ghost notes |
| Hat hits | F1 0.14 | almost nothing | rolls, triplets, open hats |
| Melody | not benched | register and contour of the loudest line | assuming it is the lead (it may be the 808) |
| Sections | energy-based if `allin1` is missing (see warnings) | where the energy changes | labels like "verse/hook" |

## Failure modes and the cross-check for each

### 1. Tempo octave (half/double)
Detectors often lock onto twice or half the felt tempo. **Check:** compute the spacing of the
snare hits. In most modern genres the backbeat comes once per bar (half-time trap) or twice per
bar (pop, boom-bap). `60/BPM × 4` = bar length. If the snare spacing equals one bar at the
detected BPM, you have a half-time feel at that BPM; if it equals one bar at half the BPM,
the "true" count is the lower one. Both are valid ways to count the same groove (`rhythm.md`).
`bpm_alt` lists the ½× and 2× options.

### 2. Key off by a related key
A key finder sees the notes, not the "home". Typical confusions:
- **Relative** major/minor (same notes): C major ↔ A minor.
- **Fifth-related** (the dominant): it reports the V key, e.g. G# major for a song in C# minor,
  because the raised 7th (B#) and the V chord pull it there.
- **Parallel** (same root): C# minor ↔ C# major, when the chord quality is unclear.

**Check, in order:** (a) which chord occupies most of the time in `chords`; (b) which
pitch class the bass/808 sits on most (`fl_audio analyze what=["note"]` on a few bass hits, or a
transcription's pitches below MIDI 48); (c) the first
and last chord; (d) whether the "out-of-key" notes in the gaps log become in-key under your
candidate. The key that makes the most notes diatonic *and* has the most-held chord as its
i/I wins. Log the disagreement; don't edit the data.

### 3. "Melody" is really the bass or 808 (and the real lead is never transcribed)
A melody transcriber run on the **vocal stem only** sees bleed on an instrumental (a type
beat) — often the 808 — so "the melody" can be the 808.
**Check the register** (table below): mostly below MIDI 40 (E2, 82 Hz) = bass/808. A lead
lives around MIDI 60-84.
**The lead/arp/pads live in the "other" stem.** Run the same transcriber on it (and on the
bass stem for the 808) — the standard check for any beat (`pip install basic-pitch`):
```bash
python - <<'E'
from basic_pitch.inference import predict
for p in ["<song>/stems/other.wav", "<song>/stems/bass.wav"]:
    _, _, ev = predict(p); ev = sorted(e for e in ev if e[1] - e[0] >= 0.1)
    print(p, len(ev), "notes", min(e[2] for e in ev), "-", max(e[2] for e in ev))
E
```
Read: notes per bar (density), pitch range and median (register), pitch-class counts
(root/5th-heavy = arpeggio/drone texture; varied = melody). Polyphonic layers (arp + pad)
add up, so the count is an upper bound on any one part.

### 4. No kicks, or kicks hidden
Trap kicks are often layered with or replaced by the 808. Demucs may send that low thump to
the *bass* stem, so the drum model sees no kick. **Check:** the 808 note onsets in the transcription
usually land where the kick would be. A note-onset pattern on 8th/16th positions is a kick+808
pattern. Mark it "inferred".

### 5. Hats too regular
At F1 0.14, the hat track usually comes back as a steady grid; rolls and triplets go missing.
Steady 1/8 or 1/16 hats in the data mean "there's a hat grid". Rolls must be heard.

### 6. One chord for the whole song
A drone loop (common in dark trap) gives one long chord span. Fine. If the score is low,
the chord may be ambiguous (power chord, no third). Check the melody/bass pitch classes for
the third (minor 3rd = 3 semitones above the root).

## Pitch register table (MIDI 60 = C4 here; FL shows it as C5)

| MIDI | Note | Hz | Typical role |
|---|---|---|---|
| 24 | C1 | 32.7 | 808 sub (lowest useful) |
| 25 | C#1 | 34.6 | 808 sub |
| 28 | E1 | 41.2 | 808 / bass guitar low E |
| 36 | C2 | 65.4 | 808 upper, bass |
| 40 | E2 | 82.4 | bass ceiling for "sub" feel |
| 48 | C3 | 130.8 | low keys, chord bass |
| 60 | C4 | 261.6 | chords, pads |
| 72 | C5 | 523.3 | lead, bells, vocal top |
| 84 | C6 | 1046.5 | high bells, plucks, piccolo |
| 96 | C7 | 2093.0 | sparkle, top of a bell |

Rule of thumb: below 100 Hz = felt more than heard (808/sub); 100-300 Hz = body/mud;
300 Hz-3 kHz = where melodies and voices read; above 5 kHz = air and hats.

## Turning hits into a step grid
1. Bar length = `60/BPM × 4`. Find the downbeat (a pipeline's `downbeats`, or the first kick).
2. Step index (0-15) of a hit = `round(((t − bar_start) / bar_len) × 16) mod 16`.
3. Off-grid by a third of a step, consistently? That's a triplet or swing (`rhythm.md`).

## Worked example: "Shutdown" (Future-type beat, 2026-10-03; private learning reference)

| Field | Raw output | Reading | Label |
|---|---|---|---|
| Tempo | 122.44; check 122.0; candidates 61/122/245 | 122 BPM, half-time feel | measured + inferred |
| Hat spacing | 0.245 s steady | 1/8 notes at 122 (60/122/2 = 0.246) | measured; rolls unknown |
| Snare spacing | ~1.97 s | one per bar at 122 (bar = 1.967 s): snare on beat 3 | inferred (snare F1 is low) |
| Kick | 0 hits | low end carried by the 808 | inferred, not verified |
| Key | "G# major", strength 0.82 | **C# minor**: C#m spans 118 of 130 s, the 808 rests on C#, and E/F# are diatonic to C# minor but flagged in G# major | inferred, fifth-related confusion |
| Melody | 78 of 140 notes on C#1 (MIDI 25, 35 Hz) | that's the 808, not a lead | inferred from register |
| 808 turnaround | C#1 … F#1 → D#1 → E1 → C#1 at phrase ends | the 808's motion is the hook | measured notes |
| Form | 1 bar intro, a 4-bar loop ×7, a 3-bar end | minimal loop beat | measured (energy sections) |
| Lead sound | not in the data | unknown; ask the user (the other stem) | — |
| other stem (basic-pitch, added later) | 920 notes, 14.4/bar, C#3-G6, median C4, mostly G# and C# | a rolling 1/8 arpeggio of root + 5th across 4 octaves (+ pad), not a sung melody | measured + inferred |
| bass stem (basic-pitch) | 111 notes, C#1 84%, E1/D#1 passing, ~1.5-beat spacing | the 808 sits at **C#1 (MIDI 25)**, sparse, long notes | measured |

Second lesson (v1 of our own beat missed this): the first reading never looked at the other stem,
so v1 got a sparse, high, singable lead and an 808 an octave too high. Always run the
other/bass stem check before writing parts.

Lesson: three wrong-looking outputs (key, melody, kick) were all *readable* once the theory
checks above were applied. None needed the data changed.

# Ear training and practice (aural skills)

The aural-skills curriculum used in conservatories (sight-singing, dictation, recognition),
adapted for producers. Claude can't hear, so these are drills to run **with the user**: the
user listens, Claude checks the answers against the analysis data or theory.

## 1. Interval recognition (reference songs; learn with your own culture's songs too)

| Interval | Ascending reference | Descending reference |
|---|---|---|
| m2 | *Jaws* theme | *Für Elise* (opening) |
| M2 | *Happy Birthday* ("Hap-py") | *Yesterday* (Beatles) |
| m3 | *Greensleeves*; *Smoke on the Water* | *Hey Jude* ("Hey Jude") |
| M3 | *When the Saints Go Marching In* | *Swing Low, Sweet Chariot* |
| P4 | *Here Comes the Bride*; *Amazing Grace* | *O Come All Ye Faithful* |
| Tritone | *The Simpsons* ("The Simp-"); *Maria* (West Side Story) | *Black Sabbath* riff |
| P5 | *Star Wars* main theme; *Twinkle Twinkle* | *Flintstones* ("Flint-stones") |
| m6 | *The Entertainer* (3rd-4th notes) | *Love Story* theme |
| M6 | *My Bonnie*; NBC chime | *Nobody Knows the Trouble I've Seen* |
| m7 | *Somewhere* (West Side Story) | *An American in Paris* |
| M7 | *Take On Me* chorus (1st to 3rd note) | *I Love You* (Cole Porter) |
| Octave | *Somewhere Over the Rainbow* | *Willow Weep for Me* |

Sargam ear training (Indian method): sing Sa–Re, Sa–Ga … against a tanpura drone; every note is
heard as a relation to Sa. That's **scale-degree hearing**, the most useful skill for producers.

## 2. Scale-degree (functional) hearing
- Play a drone or a I–IV–V–I cadence to set the key, then a single note; name its degree (1-7, or the sargam).
- Learn each degree's feel: 1 = home, 5 = stable/open, 3 = sweet (major)/dark (minor), 7 = pulling up,
  4 = pulling down to 3, 6 = yearning, 2 = passing, b2 = menacing, b6 = sad sigh.
- Then do it with chords: name I, IV, V, vi from a cadence.

## 3. Chord quality and progression recognition
1. Triads: major / minor / diminished / augmented (bright / dark / tense / dreamy).
2. 7ths: maj7 (dreamy), dom7 (bluesy, unresolved), m7 (mellow), m7b5 (yearning), dim7 (horror).
3. Progressions: identify the bass line first (sing the lowest note), then each chord's quality.
   Common targets: I–V–vi–IV, vi–IV–I–V, i–VI–III–VII, ii–V–I, 12-bar blues.
4. Use the pipeline as an answer key: `chords.json` (85.8% accurate) after the user guesses.

## 4. Rhythm
- Tap the beat, then the subdivision (8ths, 16ths, triplets); count out loud ("1 e & a").
- Identify the backbeat: snare on 2 & 4 or on 3 (half-time).
- Identify swing: even or long–short?
- Clap the clave, tresillo, dembow and a Teentaal theka; then layer the hats over them.
- Dictation: listen to 1 bar of drums, write it as 16 steps; compare with `drumlab` / the pattern MIDI.

## 5. Timbre and production listening
- Name the lead instrument; is it plucked, bowed, blown, synthetic?
- Locate each part in the spectrum (low/mid/high) and stereo field (left/centre/right).
- Hear effects: reverb size, delay rhythm (1/8, dotted 1/8, 1/4), distortion, sidechain pumping.
- A/B a reference against your mix at the same loudness.

## 6. Transcription method (by ear, professional order)
1. Tempo and meter (tap; check the analysis BPM).
2. Form: mark sections and bar counts.
3. Bass line (sets the harmony).
4. Chords (bass + quality; check the upper voices).
5. Melody (sing it back first, then find the notes; start from the phrase-ending note, usually 1, 3 or 5).
6. Drums (kick, snare, hats separately).
7. Details: ornaments, fills, effects.

## 7. Daily practice plan (20-30 minutes)
| Minutes | Drill |
|---|---|
| 5 | intervals (ascending/descending, then harmonic) |
| 5 | scale degrees over a drone (sargam or numbers) |
| 5 | chord qualities and one progression (mood version: `chord-emotion.md`; FL drills: `fl-melody/references/chord-practice.md`) |
| 5 | rhythm: clap, count, dictate 1 bar |
| 5-10 | transcribe 4 bars of a reference (bass first) |

## 8. Producer drills (with the analysis pipeline)
1. **Count it:** clap the snare; count so it lands on 3 (half-time) or on 2 and 4.
2. **Find the root:** hum the lowest "home" note; compare with the 808's most common pitch in `melody.json`.
3. **Hear the hats:** play `stems/drums.wav`; count rolls per 4 bars and where they land.
4. **Name the lead:** bell, pluck, flute, piano, choir? Bright or dark? Dry or reverb?
5. **Spot the change:** what changes every 4 bars? Every 8?
6. **Rewrite drill:** keep the style sheet, write 3 different 4-bar motifs, and choose the best.
7. **Recreate-then-mutate:** build the drum grid from conventions, then change 3 things on purpose.

# Genre-specific melody / bass / chord recipes

> The theory behind these recipes, and many more styles: `skills/music-theory/references/world-and-genre-theory.md`.

### Reggaeton / Latin
- **Bass:** C1 (midi 36) on beats 1 and 3, short (0.5 quarter), hard velocity.
  Optional: E1 (40) on beat 4 for a lift.
- **Chords:** minor 7ths, one chord per bar, 2-beat duration. Am7: [45, 48, 52, 55].
- **Melody:** sparse, pentatonic minor (A C D E G), 2–4 notes per bar, syncopated
  against the dembow.

### Lo-fi / Chill
- **Bass:** sine-like, C2 (48) on beat 1, 1-beat duration, soft (0.6 velocity).
- **Chords:** jazzy 9ths/7ths, one per bar or every 2 bars. Cmaj9: [60, 64, 67, 71, 74].
- **Melody:** slow, legato, minor pentatonic, lots of space.

### House / Techno
- **Bass:** off-beat 8ths (0.5, 1.5, 2.5, 3.5…), short stabs (0.25 quarter),
  root note only, hard velocity.
- **Chords:** stabs on beats 2 and 4, short (0.25 quarter), detuned for width.
- **Melody:** optional, repetitive 4-note motif, minor or dorian.

### Trap
- **808 bass:** follows the kick (steps 1, 8, 11 in a 16-step bar), long decay
  (1–2 beats), glide between notes. Use `fl_notes("write_steps")` with long duration.
- **Melody:** dark, minor, 2–3 notes, slow. Often a single sustained pad note.

### Drum & Bass
- **Bass:** fast 16th-note runs, root + 5th, tight (0.25 quarter), aggressive.
- **Chords:** rare; if used, quick stabs on the "and" of 2.
- **Melody:** liquid = smooth legato phrases; neuro = sparse, glitchy.

### Boom Bap
- **Bass:** follows the kick (1, 8, 11), 0.5–1 beat, medium velocity.
- **Chords:** one soul-jazz chord per bar (7ths, 9ths), 2-beat, soft.
- **Melody:** Rhodes-style, 3–5 notes per bar, swung.

### Dubstep
- **Bass:** wobble bass (use a plugin with LFO, not just piano roll notes).
  In the piano roll: root note on beat 1, 1-beat duration, hard.
- **Chords:** minimal; a sustained pad chord per 2 bars.
- **Melody:** the "drop" is the bass; the "build" can have a rising pad or
  sparse synth lead.

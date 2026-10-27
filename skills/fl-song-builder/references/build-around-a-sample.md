# Build a whole song around one sample (a Splice loop, a melody, a guitar)

The flow from the 2026-10-11 session: a 4.8 s woodwind-flute melody loop (Splice, C minor, 100 BPM)
became a 20-bar arrangement (intro, verse, hook, break, hook) with a genre drum kit, bass, chords, a
melody written from the sample's own motif, and a glued mix. Everything here ran with MCP tools; picks
and numbers are **convention, not auditioned** (skills/README.md rule 9) unless marked measured.
Theory behind each step: `music-theory` (`melody-layering.md`, `hit-song-patterns.md`, `idea-to-record.md`).

## 0. Rules this flow follows
- **One melody at a time.** If the sample is a melody it is the hook; do not stack a second, different
  melody on top (the "double melody" complaint). Other parts support or double it.
- **Never the default 808 kit.** Drums come from a genre kit (`fl_genre("load_kit")`, `fl-genres` skill).
- **Melody leads; bass/chords sit under** (`melody-layering.md` §4); notes humanized, not gridded.
- **Read back every write**, and audit before blaming the sound (section 9).

## 1. Get and measure the sample
1. Get the sample from your library (a Splice/pack download with your account, or your own). The file name often carries
   the BPM and key ("..._100_..._Cmin.wav"); the page lists BPM. Convert with ffmpeg to WAV.
2. **Length check:** bars = seconds x BPM / 240. The flute: 4.78 s at 100 BPM = 8 beats = 2 bars, so it
   loops cleanly every 8 beats (retrigger the sample on every 2nd bar).
3. `fl_audio("analyze", path, what=["tempo","key","chords"])` (Mac CPU). The tempo model can read an
   octave off (96.8 vs 48.4); trust the file name/page when it agrees with the length.
4. **Notes and feel (measured, `.venvs/torch` has librosa):** `librosa.pyin` for pitch + onsets, then
   segment into notes and divide by the beat length. Convert each onset to a 16th-grid position and its
   deviation in ms. Detectors are noisy: use medians, never single hits.
5. **Feel decides swing.** Odd 16ths late = swing; odd 16ths early (the flute: median -27 ms) = a push.
   Drums must not swing against a pushed sample: set `fl_transport("set_swing", swing=0)` and keep
   the shaker/hat "e/a" shifts tiny.

## 2. Project, tempo, kit
- Tempo = the sample's BPM, speed 1.0. A mouse scroll over FL's tempo box can change it later
  (seen 98 -> 522 BPM): re-check `fl_state` before playing.
- If FL restarted, it opens a default session (130 BPM, 808 rack, 5 channels). Reuse the first Sampler
  or add channels; the empty template is File > New from template > Empty (menu click). Check the
  project was saved to disk (Desktop/Project*/...flp) before starting over.
- `fl_genre("load_kit", genre=..., beat="<4-bar groove>")`: about 50 s per sample the first time, so
  a 6-sample kit takes 4 to 8 min; it can finish partial (missing rows) - **just run it again**, it only
  redoes the misses (loaded samples are remembered per FL process). Keep your hands off FL.

## 3. Harmony and the melody (core first)
- Key from the sample (the flute's notes were Eb, D, C: C minor). Write the **hook harmony as a one-chord
  vamp** under a looping sample (Cm); write the **verse with four roots** (Cm | Ab | Fm | G) so it
  resolves. `fl_notes("write_steps", notes=[...])` with explicit velocity/time (humanize is only for
  generated notes).
- **Custom melody from the sample's motif:** state the 3-note cell in bar 1, answer it a step lower in bar 2
  (on the next chord), climb to one peak in bar 3, end bar 4 on the leading tone so it pulls back to the
  loop. Same key and tempo, so it reads as the same voice.
- **Hybrid voice:** an instrument plays the sample's exact notes (same onsets) at 0.3 to 0.5 velocity
  under it in the hooks: a pluck on every flute note (`idea-to-record.md` section 2).
- Bass: tresillo 3+3+2 (beats 0, 1.5, 3) on the chord root, octave 2; hook stays on the tonic with a
  dominant pickup into each loop; break = one long root per bar.

## 4. Sections and the song pattern
- One pattern per section (Intro, Verse, Hook, Break; 16 beats each), each loaded with
  `fl_preset("load_beat", preset=..., target_pattern=N)`; then ONE pattern for the whole song.
- **Most reliable song writer:** concatenate the section rows into one preset (multi-bar
  beats, 320 steps for 20 bars; `velocities`/`shifts` arrays the same length) and
  `load_beat(..., target_pattern=<song>, fill=false)`. `fl_pattern("chain")` also works now for
  step-only sections (and copies velocity/shift), but verify with the audit in section 9.
- Melodic parts are written straight into the song pattern, **one channel per call**, `mode="replace"`,
  absolute beats (verse at beat 16, hook at 32...). Read each back before the next.
- Sample triggers: `fl_channel("set_steps", bars=[[1],[],[1],...], n_bars=20)`.

### Split the sample: full vs half + echo (instead of the loop playing all the time)
A looping sample that never leaves is tiring. Alternate it:
1. Cut a half with ffmpeg at a gap between phrases (the flute: phrase A ends at beat 3.8, phrase B starts at 4.59, so cut
   at 4.3 beats = 2.58 s) with a short fade-out: `ffmpeg -i loop.wav -t 2.58 -af "afade=t=out:st=2.5:d=0.08" half.wav`.
2. Load the half on its own Sampler (own mixer insert), keep the full loop on another. In the song pattern trigger
   **full on the first 2-bar cycle and half on the second** (flute: full at bars 1, 9, 17; half at bars 3, 11, 19).
   The groove then has the gap to itself, and the last cycle ends on the half.
3. **Echo only on the half** (its own insert): Fruity Delay 3, time = a dotted 8th (0.375 beat = 225 ms at 100 BPM),
   feedback about 40%, output wet about 45%, feedback low-pass about 1.8 kHz so repeats are darker; route it to the
   music bus and send a little to the Room. The echo fills the gap the cut leaves.
4. Instruments that double the sample must stop where the half stops (drop the notes of the second phrase in the
   half cycles), or they will play over the gap.

## 5. Arrangement (hit-song-patterns, idea-to-record)
| Section | Layers |
|---|---|
| Intro (4 bars) | the sample alone first (hook in the first seconds), shaker fades in |
| Verse (4) | custom melody + chords + bass + light drums (room for a vocal) |
| Hook (4) | sample + guitar double + full drums + one-chord vamp |
| Break (4) | drums out (anti-drop), melody soft, long chords, rim roll into the hook |
| Hook 2 (4) | same layers, stronger velocities: change drums/bass, not a new melody |
About 48 s at 100 BPM: a short-form length.

## 6. Glue the mix (so it reads as one record)
`fl-mixing` `references/glue-buses.md`: drum bus + music bus + one shared room reverb, levels by
rule, pans on mixer tracks, then measure the master peak while playing.

## 7. Levels (starting values)
Sample/melody lead 0.8; kick 0.78; bass 0.62; rim 0.55; clap 0.5; perc 0.5; keys 0.5 (quiet); hat 0.38;
shaker 0.26 (the shaker was the first complaint: 16 full-velocity hits per bar).

## 8. Instruments
FL Keys = Grand Piano with no setup. FLEX needs a preset from its Library panel
(`fl-plugins` `references/instruments.md`): nylon/steel guitar are in the General MIDI Library pack. A new
FLEX channel opens on the first Core Synths preset ("BAS ..."), usable as a bass.

## 9. Audit before you debug by ear (what went wrong, 2026-10-11)
- **Per-section hit counts** (one exec): `channels.getGridBit(i, s)` for s in 0..N-1, sum per 64 steps.
  Expected kick [0,12,12,0,12] showed a kick in the intro: the old chain read the ACTIVE pattern for every
  section. Fixed (select the section, then read) and rebuilt with a single preset.
- `getGridBit` counts **only unshifted** steps (a step with a shift value no longer matches the grid);
  a lower count than the preset's hit count is normal for shifted hats/shakers.
- **Grid-aligned notes show up as steps.** `channels.setStepSequence` with all false on a melodic
  channel DELETES those notes (it wiped the guitar twice). Never use set_steps to clear a melodic channel.
- `fl_notes("clear")` clears the OPEN roll's pattern: pass `target_pattern` (now honored and reported).
- `read_steps` can return a stale export (compare `age_seconds`); a write re-exports, so write then read.
- Channels read as muted after UI poking: check `fl_channel("list")` `is_muted` before assuming a part is silent.
- Mixer fresh-project limit: only 16 inserts; unused default channels' inserts 1 to 5 can be reused as buses.

## 10. Checklist
1. Sample measured (bars, key, motif, feel)? Tempo and swing set to match?
2. Genre kit loaded with no misses, never the default kit?
3. One melody; hybrid double; custom melody built from the motif?
4. Section hit counts audited; every melodic channel read back?
5. Buses, shared room, levels; master peak under -3 dBFS while playing?
6. Saved? (`fl_connect("save")`; an unsaved session is lost when FL closes.)

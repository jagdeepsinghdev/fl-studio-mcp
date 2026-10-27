# Sound craft: shaping every sound by hand (FL stock tools)

Five production habits from a Charlie Puth studio deep dive (youtu.be/5N3UUO5nev0; auto
captions), mapped to FL Studio stock plugins and our MCP tools. His statements are **heard
(artist)**; the FL equivalents are **convention, not auditioned** (skills/README.md rule 9). He works in
Pro Tools with third-party plugins (Valhalla Delay, Soundtoys Little AlterBoy, AIR Lo-Fi, RC-20,
Transient Master, LFO Tool, FabFilter); the table in §6 gives the FL stock stand-in for each.
The record-level ideas (voice memos, era sound, every chorus different) are in
`music-theory` `idea-to-record.md`.

## 1. One note at a time, then make each note clean
- He plays a melody **one note per take** (F, then A flat, then E flat...), each at its own velocity,
  "so you have individual control over each note" (a tip from Benny Blanco). Quantize, then **print to
  audio** and shape every note: trim the click at the start, fade the end, cross-fade overlaps.
- Why: "if what you hear sounds like a final product", it inspires the next idea. Clean the
  basic sounds from the start; don't leave clicks for later. Doing the fades by hand "feels more
  natural... you need these fun placebos to make the music sound personal".
- **In FL:** per-note velocity and length in the piano roll (our `fl_notes write_steps` with explicit
  `notes=[{midi,time,duration,velocity}]`; humanize is on by default for generated notes).
  For audio: render the part (gap: no render action yet; File > Export or Edison on the track),
  then in **Edison** trim, fade in/out and declick; or load it into a **Sampler** (`fl_audio load`) and use
  its declick mode + short attack/release envelope. Slice a phrase into one-note pieces with **Slicex**.

## 2. Make a sound, don't find one (hybrid instrument)
- He never uses "just the soft synth": he **layers his own voice** (single notes sung into the phone)
  on top, lined up note for note, turned down, then **formant-shifted** (Little AlterBoy after the EQ) so
  it sounds ambiguous, like texture inside the synth, not like a singer.
- Why: presets are shared by producers everywhere; a blend you made in the moment is one of a kind, and
  "something of me" in the sound makes it personal. "You always want to *make* an interesting sound."
- **In FL:** synth on one channel, the voice notes on a Sampler/audio channel (`fl_audio load`), same
  notes. Voice 6-12 dB below the synth, EQ it (`fl_mixer set_eq`/`eq_preset`), then **Pitch Shifter**
  (formant) or **Pitcher**/**Newtone** formant controls. Route both to one bus (`fl_mixer route`) and balance
  the blend there. Variant: hum the notes yourself through **Vocodex** with the synth as carrier.

## 3. A delay as a widener (create space while you make the sound)
- On the channel itself (not an aux: "more instant gratification") he uses a **tape-style delay synced to a
  note value, very short and low in the mix**, so it acts as width, not echo, then rolls off a little top
  so the sound isn't stuck "in the middle". He prefers this to stereo wideners ("that's how they used to make
  things wider anyway").
- Why: the mix will get crowded; widening each part as it is made leaves the centre free for vocal,
  kick and bass later.
- **In FL:** **Fruity Delay 3** (tape-ish modulation, tempo sync, stereo offset; high-cut filter) on the insert:
  short synced time, low feedback, low mix. Our knobs: `fl_plugin("echo", index, mix=, feedback=, time=)` or
  `fl_plugin("dial", index, slot_index, param, target="1:16")`; A/B with `fl_mixer("fx_on", track, on=false/true)`.
  Delay-bus variant: `fl-mixing` `vocal-bus-routing.md`.

## 4. Movement: nothing stays static
Every part gets some internal motion, subtle or obvious:

| His move | What it does | FL stock stand-in |
|---|---|---|
| AIR Lo-Fi, sample rate down (on all his vocals) | slight grit, "dirties them up" | **Fruity Squeeze** (downsample/bit-crush) or **Distructor**, low mix |
| RC-20 | wobble, noise, "cheap" vintage colour | **Vintage Chorus** (slow, deep) for wow; a vinyl-noise sample layer |
| Transient Master, attack up | punch on a percussive part | **Transient Processor** |
| Transient Master, **sustain down on a vocal** | the voice turns into a new plucked/bowed instrument ("a string instrument with a dog howling") | **Transient Processor**, release/sustain down |
| LFO Tool / one-knob pumper, half depth | rhythmic volume pump | **Gross Beat** (volume) or a sidechained **Fruity Limiter** |
| FabFilter EQ sweep over the 4-bar intro | the filter opens, builds anticipation | **Fruity Filter** / **Parametric EQ 2** cutoff automated over 4 bars |
| Valhalla Delay again, as a real delay | bounce on the percussion | **Fruity Delay 3**, synced 1/8 or dotted 1/8 |

Rule of thumb: after a sound is made, ask what moves inside it (tone, texture, level, space) over 1-4
bars. Automation (the filter sweep) has no MCP action yet: draw it in FL (gap).

## 5. Drag hits slightly off the grid
- After quantizing, he drags individual hits **a little late or a little early, hit by hit** (some stay on
  the grid): "if a human were playing it, it wouldn't be perfect... delightfully imperfect".
- Why: it feels played, and it keeps the exact grid free so the drums can sit bang on it later and
  everything still sounds "in the pocket".
- **In FL:** piano-roll parts: explicit `notes=` with small `time` offsets (±0.01-0.03 beats; our default
  humanize already drifts off-beat notes). Step-sequencer parts: the per-step **shift** parameter
  (`fl_channel("set_step_param", index, step, param="pShift", value=)`, only on an active step; read back)
  or a generated variation (`fl_variations(base_id, style="humanize")` adds small shifts). Step shift can only
  push a hit **later**; for an early hit, move that part to the piano roll. Keep the main kick/snare on the grid.

## 6. Quick map: his plugin -> FL stock
| His plugin | FL stock |
|---|---|
| Valhalla Delay (tape mode) | Fruity Delay 3 |
| Soundtoys Little AlterBoy (formant) | Pitch Shifter, Pitcher, Newtone |
| AIR Lo-Fi | Fruity Squeeze, Distructor |
| XLN RC-20 | Vintage Chorus + a noise layer |
| Transient Master | Transient Processor |
| LFO Tool / One Knob Pumper | Gross Beat, Fruity Limiter (sidechain) |
| FabFilter Pro-Q (sweep) | Parametric EQ 2, Fruity Filter (automated) |
To insert any of them: `fl_mixer("add_fx", track, plugin="<name>")` (clicks; FL in front, hands off).

## Checklist (per sound)
1. Clean? (no clicks at note starts, ends faded)
2. Is there something of you in it (a voice/phone layer, a hand-played take)?
3. Does it have its own width, leaving the centre for vocal, kick and bass?
4. What moves inside it over 1-4 bars?
5. Is it slightly off the grid where a player would be, and on it where the drums need to be?

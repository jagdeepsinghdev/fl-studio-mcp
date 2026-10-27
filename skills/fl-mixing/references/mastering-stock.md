# Mastering with FL stock plugins (+ a loudness check)

The chain on the **master** track after the mix is done (`references/vocal-chain.md`,
`references/vocal-bus-routing.md`). Source: TF (TRIFREEZE, `dtoTIR0m0is`, from 17:50 on; transcript path in
`vocal-chain.md`). Numbers are **from convention, not auditioned**. The video's paid mastering service
is left out: use any reference track you like instead.

## 0. Before you start
- **Use a reference track** (a finished, mastered song in the same style) and switch between it and
  your mix at matched loudness. Without one you get used to your own mix and stop hearing its problems.
- **Bounce the mix with nothing on the master, peaking around −6 dBFS** (headroom for the chain).

## 1. Chain, in order
| # | Plugin | Move |
|---|---|---|
| 1 | Parametric EQ 2 | Match the reference's overall tone: smooth the highs if the vocal is harsher than the reference; lower the lows a little (less low end = more room to get loud). |
| 2 | **Patcher → mid/side** preset (press M in the list) | EQ the **sides** and the **middle** separately: unlink one, sweep for resonances (as in `vocal-chain.md` §2), cut; trim the lows on the sides so the low end isn't too wide. |
| 3 | Fruity Limiter (COMP) | Peak control like the beat bus: ratio 2:1, knee up, threshold just under the tallest peaks; **attack and release fairly long** so it doesn't distort. |
| 4 | Parametric EQ 2 | Compare with the reference again: is there more mid-range or resonance than the reference has? Cut it. |
| 5 | **Fruity Stereo Enhancer** | Widen a little, only up to how wide the reference sounds. |
| 6 | **Maximus** (the loudness stage) | Solo each band: **lows toward the centre** (club/mono playback), mids wider, highs much wider. Then lower the threshold *very slightly*, leave everything else, and raise **pre then post gain** until it starts to crackle, then back off. TF turns on the **saturation** (threshold + ceiling slightly on, both pushed up) instead of hitting the limiter's post-gain harder: less pumping and distortion. |

Vocal level vs. reference: if the reference vocal is louder, raise the vocal bus, not the master.

## 2. Loudness target
- Peak meters don't tell you how loud a track sounds: five tracks that all peak at 0 dB can sound very
  different. Use **integrated LUFS**.
- TF target for loud rap/pop: **−7 to −9 LUFS** (he aimed for about −8). Streaming services turn loud
  masters down anyway; for a quieter genre use a lower target. The genre decides.
- **Can't get loud enough? Lower the low end** in the EQs (low end uses up most of the headroom), then
  raise the Maximus gain again.

### Measure without FL (verified command, used in `references/vocals.md`)
```bash
ffmpeg -i master.wav -af ebur128=peak=true -f null - 2>&1 | tail -12   # I = integrated LUFS, Peak = true peak
```
Bounce first (`fl_connect save` / FL export — there is no importable export API in v45), then measure the
bounce **and** the reference the same way: `fl_vocal("loudness", path, reference=, target_lufs=-8)`
(the same ebur128 parse, plus advice).

### Export and low-end checks (SC, `W1tgWclKqwQ`)
- Export the mix as **WAV, 24-bit, highest resampling quality**, then master it on its own insert/project.
- Limiter **ceiling about -1 dB**; loudness target **-7 to -10 LUFS** for this style (same range as above).
- **Distorts when you push the master? Usually too much bass in the beat.** First slot, before everything
  else: a gentle high-pass (not steep) at **30-40 Hz**. Better: fix the bass in the mix.

## 2b. After the bounce: varispeed "between keys" (optional character)
- Charlie Puth (youtu.be/c6qAPklUL3E, **heard (artist)**): almost every record is tuned to A440, so he
  sometimes **speeds the finished bounce up slightly** (pitch and tempo together, like tape varispeed)
  until it sits *between* keys, "B flat and a half major", by ear, around **+30 cents**. Credits Julian
  Bunetta (early One Direction) and says Tears for Fears' "Everybody Wants to Rule the World" was sped up
  the same way. It "makes it more interesting" and stands out in a playlist of A440 songs.
- **Offline, exact (ffmpeg; +30 cents = ×2^(30/1200) ≈ 1.0175):**
  ```bash
  ffmpeg -i master.wav -af "asetrate=44100*1.0175,aresample=44100" master_vari.wav
  ```
  (replace 44100 with the file's sample rate; measure loudness again afterwards). Verified 2026-10-11 on a
  test tone: 440 Hz -> 447.7 Hz (+30 cents), 2.00 s -> 1.97 s.
- **In FL:** load the bounce into a Sampler (`fl_audio("load", path, pitch=0.3)`, semitones; resampling, so
  speed follows; fractional pitch read-back untested) or an audio clip with stretch mode *Resample*.
- Also a writing trick: speed up a sample of your own and **build a new song around it**.
- Not for: songs a band must play live in the original key, or tracks that must match other A440 material.

## 3. With MCP tools
- Whole chain: `fl_vocal("apply", recipe="master-stock", track=0, [add_missing])`.
- Insert one plugin: `fl_mixer("add_fx", 0, plugin=…)` (master = track 0; clicks: ask first).
- Knobs in real units: `fl_plugin("dial", 0, param, target, slot_index=s)`; presets (Patcher
  mid/side) = `fl_plugin("preset_ui", 0, slot_index=s, query=…)` (Patcher presets are patches:
  the menu route; `find_preset` refuses Patcher).
- A/B any stage: `fl_mixer("fx_on", 0, on=false/true, slot=s)`.
- Clipping: `fl_mixer("fix_clipping")` sets the *fader*; it's a safety step, not mastering.

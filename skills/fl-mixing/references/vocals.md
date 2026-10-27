# Making a vocal stem better (separation artefacts, level, space)

Applies to a Demucs `vocals.wav` or any raw vocal. Settings are **from convention, not auditioned** unless marked "measured".

> **Check the stem before cleaning it.** On live ensemble recordings Demucs' `vocals` can be just the chorus/harmonies (owner listened,
> 2026-09-29). Prefer a non-drum mix (vocals + other + bass, light clean, warped to the grid): rated
> "much better / excellent quality". The heavy chain below (denoise) is for a genuinely isolated studio-style vocal.

## Offline cleanup (ffmpeg, keeps the original)
```bash
ffmpeg -y -i vocals.wav -af "highpass=f=90,afftdn=nr=10:nf=-50,acompressor=threshold=-32dB:ratio=3:attack=15:release=150:makeup=6,loudnorm=I=-16:TP=-1.5:LRA=8" -ar 44100 -c:a pcm_s24le vocals_CLEAN.wav
```
Measured on the Nusrat live stem: −31.3 LUFS / peak −14.9 / LRA 13.7 → **−16.4 LUFS / peak −1.5 / LRA 7.9**. Check with
`ffmpeg -i f.wav -af ebur128=peak=true -f null -`. If it sounds dull or "watery", lower `afftdn nr` (10 → 6) or drop it: noise
reduction is what dulls separated vocals. Keep the raw stem to redo it.

## In FL (short version — full stock chain: `references/vocal-chain.md`; buses/sends: `references/vocal-bus-routing.md`)
Order on the vocal's mixer track: **EQ → compressor → (de-ess) → reverb/delay send**. Read the loaded plugin first
(`fl_plugin("list_params")`), set with `fl_plugin("set_param")(plugin_index, param_index, value 0–1)`.
- EQ: high-pass ~80–100 Hz; cut mud 200–400 Hz a few dB; gentle presence lift 3–5 kHz; air shelf 10 kHz+ only if clean.
- Compressor: 2:1–3:1, medium attack, 3–6 dB gain reduction on peaks.
- Space: send to a shared reverb bus (`fl_mixer("sends")`), short/dark reverb; live vocals already contain room, so go light.
- Level: vocal is the loudest element; drums/808 sit under it; master peak ≲ −1 dB.
- Stereo: keep the vocal centred (pan 0); widen only the backing layers.

## Checks
Peak meters via `fl_exec_python` (`mixer.getTrackPeaks`, ≤ 3 tracks per call), never above ~0.95; solo/mute A/B against the raw stem;
the user's ears decide (we cannot hear).

## Vocal inside a remix (workflow)
1. **Get the audio:** a non-drum mix (vocals + other + bass) from your stem separator usually sounds better than the
   vocal stem alone; load it with `fl_audio(action="load", path=...)`. Only fall back to a single stem after listening to it.
2. **Time-align:** project BPM = the clip's measured BPM (`fl_audio analyze`); if the first beat is at `beats[0]` s, so the trigger note starts at beat 0 and the vocal
   may need a small offset (start the channel late/early by that many seconds in beats: `offset_beats = beats[0] × BPM / 60`).
   A live vocal drifts ±70 ms against a grid: leave it, the drums should serve the vocal, not the reverse.
3. **Key:** build everything in the vocal's key (`fl_audio analyze` → `key`; Sa = tonic, drone on Pa). To move the vocal instead, trigger the
   sampler on a different note (MIDI 60 ± semitones); in Resample mode pitch and speed change together, so re-check tempo.
4. **Room for the vocal:** duck pads/piano/808 under it (lower their level 2–4 dB, or a sidechain compressor keyed by the vocal if the
   user has one loaded); keep the 808 below ~100 Hz and the vocal high-passed so they don't collide.
5. **Sections:** mark rough sections by ear or from a pipeline's structure output; loud passages (climax/tabla-fast) get the full drums, quiet passages get
   the minimal kit (`presets/beats/romantic-minimal.json`). Automating drum levels/mutes per section needs patterns or the Playlist (no API).
6. **Finish:** vocal loudest, master ≲ −1 dB peak, check in mono, then `references/mastering-stock.md`.

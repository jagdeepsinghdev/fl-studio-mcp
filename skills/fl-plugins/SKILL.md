---
name: fl-plugins
description: Instruments and sounds in FL Studio - add an instrument channel (FLEX, FL Keys, Sytrus...), set plugin parameters, and find/select a preset BY NAME (piano, bass, pad, guitar). Use when a channel needs a specific sound or a new instrument.
---

# Plugins, instruments & sounds

Owns: adding channels, plugin params, preset lookup. **Cannot load new plugins** — only
control what's in the project.

## Add an instrument (any, not only guitar)
```
fl_channel("add", plugin="FLEX", name="Piano")   # the native Add menu — the ONLY creation path
```
This is the native Add-menu path (there is no importable `channels.add()`). `plugin` = exact
Add-menu name (`references/instruments.md`); `name` = channel name. After adding, route it to
a mixer track (`fl_channel("route", index, to=…)`) and select it (`fl_state` shows the new
channel's index). The legacy `fl_setup_instrument` (which did add+route+name+select in one
call) is only behind `LEGACY_TOOLS=1`.

## Load your own sample (wav)
`fl_channel(action="add", plugin="Sampler", name=...)` then
`fl_channel(action="load_sample", index, path="/abs/file.wav")` (FL's native Open panel, driven by the
server — hands off the mouse; WAV only). Trigger it with a step (a Sampler plays the whole sample from
one step) or a MIDI 60 note. Failure table (stuck Open panel, go-to sheet), where FL's own drum
samples live, and the reference-track A/B setup: **`references/loading-samples.md`**.
Fallback: drag the file from FL's Browser onto the rack (the channel takes the file's name).

## Choose the sound by name
**Preset-by-name is a documented coverage gap** — `fl_plugin` has `list_params`/`set_param`/
`load_preset` but no `find_preset`/`list_preset_names`/`next`/`prev` yet (the v45 API only
exposes `getPresetCount`/`nextPreset`/`prevPreset`, no name lookup). Until that lands, preset
selection is only behind `LEGACY_TOOLS=1` (`fl_find_preset`, `fl_list_preset_names`,
`fl_next_preset`). **Preset changes are applied by FL asynchronously — never queue many
steps.** Any keyword works; no match = the bank lacks it → the user picks in the plugin
browser / installs a pack. Both paths change the preset while scanning: ask first, re-check
`fl_state` (the user edits live), never step on a stale index.

## Tools — `fl_plugin`
- `fl_plugin("list_params", index, [slot_index])` — every param with its index/name/value.
- `fl_plugin("set_param", index, param, value=0–1, [slot_index])` — set one param. (The
  argument is `index`, i.e. the channel/track; a `slot_index` targets a specific insert.)
- `fl_plugin("load_preset", index, preset, [slot_index])` — **not yet verified** (no
  importable preset-load in v45); it reports `not_verified_yet`.

### Tweak a sound (plugin params)
`fl_plugin("list_params", index)` lists every knob with its index; `fl_plugin("set_param",
index, param, value=0–1)` sets one. Example, FLEX "Acoustic Piano": param 30 = **Reverb mix**
(default 0.5 is too wet next to another reverb-y instrument: 0.15 sits with a guitar);
13/15/17 = Chorus/Tremolo/Vibrato (off = 0); 25 = Delay mix (switch 37); 10–12 = EQ
Low/Mid/Hi. If an instrument sounds "doubled" or smeared, read the params before touching
notes.

- **Cannot load new plugins** — only control what's already in the project.

## References
- **Choosing sounds (instrument ranges, timbre, synthesis vocabulary, 808 tuning):** `music-theory` skill → `skills/music-theory/references/timbre-and-orchestration.md`.
- `references/sound-craft.md` — shaping each sound by hand: one note per take + declick/fades, a hybrid
  synth + voice instrument, a short delay as widener, movement FX, off-grid nudges; FL stock stand-ins for
  Valhalla / AlterBoy / Lo-Fi / RC-20 / Transient Master / LFO Tool / FabFilter.
- `references/loading-samples.md` — load WAV samples step by step, failure fixes, FL's sample folders, reference-track A/B.
- `references/instruments.md` — which instrument is good for what; how to list every
  Add-menu name.

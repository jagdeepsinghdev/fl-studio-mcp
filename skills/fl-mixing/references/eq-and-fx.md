# Echo / reverb / chorus by name, and per-track EQ

## Named FX knobs (`fl_plugin`, MCP-side, live now)
FLEX knob NUMBERS differ per preset ("Delay mix" was 25 in one Bells preset; Chorus, Detune
and Tape move; unused knobs are named "Not Used"; some names are empty). So address knobs by
name; the tool resolves them against `list_params` on every call.

- `set_param(index, param="Delay mix", value=0.4, [slot_index])` — exact match, case- and
  space-insensitive. Refuses (with a candidate list) on 0 matches, >1 matches, "Not Used" or
  an empty name. Returns `resolved_index`, `before`, and the read-back `value_string`.
- `echo(index, [slot_index], on?, mix?, feedback?, time?)` — knobs "Delay", "Delay mix",
  "Delay feedback", "Delay time".
- `reverb(index, [slot_index], on?, mix?, decay?, size?)` — "Reverb", "Reverb mix/decay/size".
- `chorus(index, [slot_index], amount?)` — "Chorus".
- `get_fx(index, [slot_index])` — `{echo|reverb|chorus: {field: value_string}}`, only knobs
  that exist.

Values are the 0–1 normalized plugin values; `on` is true/false (sent as 1/0). Only the
given fields change; every name is resolved BEFORE the first write (all-or-nothing). Each
field reports `before` and `after` `value_string`; `after` is read by a separate command
because FL applies a set after the trip returns (a same-trip read is stale).

For an effect in a mixer slot (Fruity Delay 3, ...) pass `slot_index`; if the exact FLEX
names are absent the tool matches by keyword (mix = "wet"/"mix", feedback, time, decay,
size) and refuses when more than one knob matches (then use `set_param` with the number).
Keyword matching never takes a knob that carries another effect's name ("Reverb mix" is not
an echo mix).

## Per-track EQ (`fl_mixer`, needs controller v10.4h = FL restart)
Mixer tracks have a built-in parametric EQ. The controller exposes it as `mixer.getEq` /
`mixer.setEq` (added in v10.4h-eq). Until the controller is synced and FL restarted, the
actions answer: "controller v10.4h not deployed: restart FL after syncing the controller".

- `get_eq(track)` — `band_count` and per band `gain`, `gain_db`, `freq`, `freq_hz`, `bw`
  (normalized 0–1 plus the real units from the mode=1 getters). `errors` carries any
  TypeError text (the signature oracle: the v45 signatures are unverified).
- `set_eq(track, band, gain?, freq?, bw?)` — normalized 0–1. Reads the band before, sets,
  then reads again in a separate trip; returns `before` / `after`.
- `eq_preset(track, preset)` — `cut_mud` (mid band -4 dB at 250 Hz), `high_pass_ish`
  (lowest band -12 dB), `air` (top band +3 dB at 10 kHz), `reset` (all gains to 0 dB). The
  tool finds the normalized value for a dB/Hz target by bisecting through the real-unit
  getters (nothing hard-coded). CONVENTION, NOT AUDITIONED: band roles (low/mid/high) and the
  numbers are starting points; listen before trusting them. `exact: false` means the target
  was outside the band's range (the nearest value is left in place).

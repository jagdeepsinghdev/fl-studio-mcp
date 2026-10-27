---
name: fl-mixing
description: Mix and master in FL Studio - levels, pan, send buses (reverb/delay), EQ/FX, vocal chains (autotune, EQ, compression, de-ess, vocal/reverb/delay buses) and stock-plugin mastering to a LUFS target. Use when balancing levels, adding space, mixing or de-essing vocals, or mastering a track.
---

# Mixing

Owns: mixer tracks, channel levels, sends, swing. Sound selection → `fl-plugins`; notes →
`fl-melody`. Grow this domain by adding files under `references/` (e.g. gain-staging, bus
recipes) — not new skills.

## Tools
- Read: `fl_state` returns the mixer (track count, names, selection) — use it before you
  touch anything. (`fl_mixer` has no read action yet; `fl_state` is the read path.)
- `fl_mixer("set_vol", track, volume=0.0–1.0)` (0.8 ≈ 0 dB default) ·
  `fl_mixer("set_pan", track, pan=-1.0–1.0)` — **not** 0–100. **The reply text can be
  stale; read back with `fl_state` (it returns the track's volume/pan).**
- `fl_mixer("route", track, to=0)` — full-level send to the master (or a bus).
- `fl_mixer("sends", track, to, level=0–1)` — set the level to another track, **enabling
  the route if needed**. Use it for reverb/delay buses: send an instrument's insert to a
  bus insert. `track` and `to` must differ. **There is no action to *remove* a route yet**
  (a documented gap; the old `fl_remove_*` path doesn't exist — a route is only lowered to
  0, not deleted).
- `fl_mixer("add_fx", track, plugin=…)` — insert an FX (native Add-FX menu; the only
  reliable way; it CLICKS: ask the owner, FL in front, hands off). Check the result's
  `stray` (plugin landed on another track) and LOOK with `screen.py look --fl-window`.
  A/B a track's effects by ear: `fl_mixer("fx_on", track, on=false)` then `on=true`
  (never `mixer.setPluginMuteState` - one-way, it can't switch a slot back on).
  Mouse-free track selection / mixer window: `fl_ui_script`. Hints:
  `fl-studio-mcp/docs/SCREEN-CONTROL.md` §1b.
- **Echo / reverb / chorus per channel, by NAME (no knob numbers):**
  `fl_plugin("echo", index, on=, mix=, feedback=, time=)` · `("reverb", …, decay=, size=)` ·
  `("chorus", index, amount=)` · `("get_fx", index)`; values 0–1, only the given fields
  change, each returns before/after `value_string`. `fl_plugin("set_param", index,
  param="Delay mix", value=)` also takes a knob NAME. `slot_index` targets a mixer-slot FX.
- **Per-track EQ (needs controller v10.4h deployed = FL restart; unverified live):**
  `fl_mixer("get_eq", track)` · `("set_eq", track, band, gain=, freq=, bw=)` (0–1
  normalized) · `("eq_preset", track, "cut_mud"|"high_pass_ish"|"air"|"reset")`
  (convention, not auditioned).
- Details: `references/eq-and-fx.md`.
- **Track housekeeping (probe.exec, read back; live-verified 2026-10-05/06):**
  `fl_mixer("name", track, name=)` · `("color", track, color="#RRGGBB")` ·
  `("mute"|"solo", track, on=)` · `("stereo_sep", track, value=-1..1)` ·
  `("route_only", track, to)` = FL's "route to this track only" (master route OFF) ·
  `("unroute", track, to)` · `("list_fx", track)` (slot, plugin, on) ·
  `("add_tracks", count=N)` — new inserts via the mixer "+" (no API/shortcut creates
  tracks; hint-confirmed click, `trackCount` proof). Arm/swing: still gaps.
- **Knobs in real units:** `fl_plugin("dial", index, param, target="4:1"|"10 ms"|"-20 dB"|
  "1.2 kHz", slot_index=)` — searches FL's own display string, reads back.
  `fl_plugin("find_preset", index, query, slot_index=)` — API preset stepping, paced; Maximus
  has no names here and Patcher is refused (heavy patch loads) -> use snapshot / preset_ui.
- **Presets, fastest first:** `fl_plugin("restore", index, slot_index, query=name)` applies
  a stored full-knob SNAPSHOT in one API call (< 1 s, read-back proof; record once with
  `("snapshot", …)`). Not for Patcher (its patch is not knobs) -> `("preset_ui", …)`, the
  editor's menu read by column/tile OCR.
- **Vocals / mastering in one tool:** `fl_vocal` — `apply(recipe, track)` configures a
  chain from `fl-studio-mcp/presets/vocal/*.json`, `buses(...)` wires vocal/reverb/delay
  buses, `loudness(path, reference)` = LUFS, `learn(track, slot)` saves real knob names.
  Loop: `references/vocal-chain.md` §5.
- **Fewest calls:** `fl_vocal("run", ops=[{"tool": "mixer"|"plugin"|"vocal", "action": …,
  …params}, …])` — up to 60 steps in ONE MCP call, compact per-step results, stops at the
  first failure (`stop_on_error=false` to continue). Whole chain = one `apply`; whole bus
  layout = one `buses`. Prefer these over one call per knob.
- **Vision:** `fl_screen` — `look`, `ocr(region, zoom, tile)`, `find(text)`, `hint(x, y)`,
  `click_text(text)` (refuses unless FL is in front). Zoom tiles ~150 px for dense/small text.
- **FL facts that bite (live 2026-10-06):** Add > Effect inserts into the SELECTED slot (not the
  first free one) -> `apply` proves the plugin ORDER and fixes it (slot menu "Move up",
  verified per move); Escape (in-engine or key) closes the
  mixer window; never import AppKit in our Python (it becomes a focus-stealing app).
- **Before a long job:** `fl_connect(action="doctor")`; if blocked, `("recover")`. All
  screen tools wait for FL to be frontmost (never steal focus mid-typing). Rules:
  `fl-studio-mcp/docs/UI-AUTOMATION.md` §3.7. Plugin inserts pick by INDEX in the picker
  (works when rows are off-screen); short preset names are verified by knob fingerprints
  (`plugin_preset_ui.record_fingerprint` once, after confirming on screen).
- **How plugins are controlled:** knobs = FL Python API (`dial`/`set_param`, no mouse, FL need
  not be in front); inserting a plugin = the native picker (clicks, FL in front, hands off);
  presets = `find_preset` (API stepping) or `fl_plugin("preset_ui", track, slot_index, query)`
  (the editor's preset MENU, exact item, e.g. "Soundgoodizer presets/a"; Maximus/Patcher). Settings with no knob in the API (Pitcher's key
  notes, Limiter sidechain number, Patcher internals) = UI clicks or a saved preset — gaps.

## Quick commands (one request -> one call; run `fl_connect("doctor")` first)
| Owner says | Call |
|---|---|
| "set up vocals" / "vocal chain" | `fl_vocal("setup")` (5 free inserts) or `("setup", vocal=N)` -> `success` only at 0 misses |
| "same chain on track N" | `fl_vocal("apply", recipe="vocal-clean-stock", track=N, add_missing=true)` |
| "reverb/delay buses" | `fl_vocal("buses", recipe="vocal-buses", vocal, vocal_bus, reverb_bus, delay_bus, fx_tracks)` |
| "master it" | `fl_vocal("apply", recipe="master-stock", track=0, add_missing=true)` then `("loudness", path, reference)` |
| "add plugin X" (new to us) | `fl_vocal("onboard", plugin="X")` -> knobs + presets + recipe stub in `presets/vocal/plugins/` |
| "set <knob> to <value>" | `fl_plugin("dial", index=track, slot_index=s, param, target="4:1"/"10 ms"/"Ping Pong")` |
| "load preset P" | `fl_plugin("preset_ui", index=track, slot_index=s, query="P")` |
| "A/B it" | `fl_mixer("fx_on", track, on=false)` then `on=true` |
| "FL is stuck" | `fl_connect("recover")` |
| "close the plugin windows" | `fl_connect("tidy")` |
Misses come back with the real knob names / menu items: fix the recipe JSON, re-run the same call.

## Workflow
1. `fl_state` (or `fl_mixer("get_info")` per track) to see current mixer state.
2. `fl_mixer("set_vol")` / `("set_pan")`; for space, `fl_mixer("sends", track, bus, level)`
   to a reverb/delay bus.
3. For plugin params, `fl_plugin("list_params", index)` to discover names, then
   `fl_plugin("set_param", index, param, value)`.

## Balance rules of thumb
- Kick/808 loud and centred; snare + clap layered (clap a little lower); hats ~30% below
  snare, panned slightly off-centre.
- Keep the low end mono. If a melody is buried, raise the lead / duck drums
  (`fl_mixer("set_vol")`) before touching notes.
- Swing is **global** — it's a documented coverage gap (not a domain action yet), so it's
  only reachable behind `LEGACY_TOOLS=1`. Use for boom-bap/lofi/house *after* drums are in;
  reset to `0.0` for straight genres (trap, techno).
- Mixer tracks are 1-based; channel indexes 0-based (`fl_state`).
- `fl_channel("set_vol")` reported success but sometimes changed nothing (2026-09-29); if a
  channel level won't move, set it inside FL via the gated `fl_exec_python`
  (`channels.setChannelVolume(i, v)`, raw 0–1, default 0.78) and read back.
- Keep exec peak-meter checks short (`mixer.getTrackPeaks(t, 2|3)`, ≤ 3 tracks per call): a
  call over ~10 s times out.

## Guitar + piano together (worked example)
Two harmonic instruments in the same register fight. Make the guitar the lead: guitar
`fl_mixer("set_vol", track, 0.8)`, piano `0.6` (−6 dB), piano pan `fl_mixer("set_pan", …, -0.25)`, guitar `+0.12`, soft drums (kick 0.45, clap 0.3, hats 0.25). Verify with `fl_mixer("get_info")` / `fl_state` and meters (nothing above ~0.95).

## References
- **Per-sound craft (short synced delay as a widener, movement FX, hand fades, FL stand-ins for
  paid plugins):** `fl-plugins` skill → `skills/fl-plugins/references/sound-craft.md`.
- **Why a mix is muddy (orchestration, frequency spectrum, 808 vs kick):** `music-theory` skill → `skills/music-theory/references/timbre-and-orchestration.md`.
- `references/eq-and-fx.md` — echo/reverb/chorus by name, `set_param` by name, per-track EQ
  and its presets, deploy status, refusals.
- `references/background-vocals.md` — BGV stack (front take + two high-passed whispers on one bus), thinner
  harmonies, grit, diction (over-smile), tiny clip fades, the unexpected cut-off ending.
- `references/glue-buses.md` — glue a whole beat: drums bus + music bus + one shared room reverb, sends, peak check, pans on mixer tracks, the 16-insert limit of a fresh project.
- `references/vocals.md` — cleaning and mixing a (separated) vocal: ffmpeg chain, FL chain
  order, measured before/after.
- `references/vocal-chain.md` — full stock-plugin vocal insert chain (Pitcher → Maximus →
  EQs → comp → dynamic de-harsh → glue comp → de-esser), compressor attack/release rules,
  ad-libs variant, tool mapping + gaps.
- `references/vocal-bus-routing.md` — vocal / reverb / delay buses, Fruity Send pre-fader
  sends, dry 0 / wet 100, sidechain-ducked reverb/delay, carving the beat for the vocal.
- `references/mastering-stock.md` — (also §2b: varispeed the bounce +~30 cents "between keys") master chain (EQ → mid/side → limiter → stereo →
  Maximus), reference-track matching, LUFS target + ffmpeg measurement.
- **Mixer hotkeys** (link selected channels to a track, Alt-solo, move track ←/→, wave view): `fl_shortcut` → `skills/fl-studio/references/shortcuts.md`.

# Transport & channel rack — domain-tool reference

## Transport — `fl_transport` (one tool, `action` + params)
- `fl_transport("play")` / `("stop")` / `("record", armed=True)`
- `fl_state` — is_playing, is_recording, position, loop_mode (the read path)
- `fl_transport("set_position", value=…, unit="seconds"|"beats"|"minutes")`
- `fl_transport("loop", mode="pattern"|"song")` · `fl_transport("set_speed", speed=0.25–4.0)`
  (**speed multiplier — does NOT change the BPM; reset to 1.0 after setting real tempo**)
- `fl_transport("set_bpm", bpm=20–300)` — **the real BPM** (sets FL's actual tempo; the
  toolbar box updates). Use this, not the speed multiplier, to change tempo.
- **Swing:** `fl_transport(action="set_swing", swing=0.0-1.0)` — global groove, one setting for
  the whole project (FL quantises slightly: 0.3 reads back ~0.297). No getter action yet.

## Channel rack — `fl_channel` (+ `fl_state` for reads)
- Read: `fl_state` returns every channel (index, name, muted, selected, target FX track) and
  the selected channel — use it instead of the old `fl_get_all_channels`/`fl_get_selected_channel`.
- `fl_channel("set_vol", index, volume=0–1)` · `("set_pan", index, pan=-1..1)`
- `fl_channel("mute", index, muted=True)` · `("solo", index, solo=True)`
- `fl_channel("rename", index, name=…)`
- `fl_channel("route", index, to=mixer_track)` — set the channel's target mixer track
- `fl_channel("add", plugin="FLEX", name="Piano")` — the native Add menu (the ONLY
  channel-creation path)
- `fl_channel("clone", index, name="Copy")` — FL's channel menu "Clone" (v45 has no clone
  API). FL inserts the copy RIGHT AFTER the source and shifts later channels: re-read
  `fl_state` before using any index. Refuses if two channels share the source's name.
- `fl_channel("load_sample", index, path=…)` — a wav into a Sampler via its own Open panel.
- `fl_delete("channel", index=…, name=…)` — channel menu "Delete…" + FL's confirm (v45 has no
  `deleteChannel`). `name` is REQUIRED: nothing is clicked unless the channel at `index`
  has that name; Ok is clicked only under FL's "about to be deleted" text; proof = the
  channel list. FL must be frontmost (macOS).
- **Real-time note trigger** (`fl_trigger_note`) and **channel color** are not in the domain
  surface yet — documented coverage gaps (only behind `LEGACY_TOOLS=1`).

## General tips
- Always `fl_state` before overwriting (`mode="add"` is safer than `"replace"`).
- Mixer tracks and channel indices are 1-based in FL Studio.
- If a tool returns a MIDI/connection error, use the `fl-setup` skill.

## Quick recipes (verified on this setup)
- **Look around first:** `fl_state` (gives channels, patterns, transport, mixer in one trip).
- **Drum pattern:** `fl_channel("set_steps", index, steps=[True,False,…])` writes a channel's
  step grid (the step-sequencer was promoted into the domain surface; reads with
  `fl_channel("get_steps")`). It now covers multi-bar loops too (a 64-step list = 4 bars),
  which the old single-call path didn't. Use it, then confirm by re-reading `fl_state`.
- **Stop cleanly:** `fl_transport("stop")` (resets position).
- Prefer the step sequencer for anything that must persist; real-time triggering does not persist.
- Piano-roll notes use the separate ComposeWithLLM queue path — `fl_notes` (see the `fl-melody`
  skill); confirm the open roll first (`open_roll_verified=True`).
- After any timeout, follow `fl-setup` before retrying; don't loop on the same failing call.

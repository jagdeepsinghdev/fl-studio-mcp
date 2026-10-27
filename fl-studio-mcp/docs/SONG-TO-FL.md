# Song → FL Studio: `load_song`

`fl_preset(action="load_song", song_dir=...)` loads a **song folder** into FL in
one call: tempo, drum groove, melody, the song's own bass sound and a safe
level. The folder can come from any tool (an analysis app, a DAW export
script, or written by hand). This server only consumes it.

Companion guides: [`SCREEN-CONTROL.md`](SCREEN-CONTROL.md) (how the screen and
mouse are driven safely) · [`UI-AUTOMATION.md`](UI-AUTOMATION.md) (all control
layers).

> **Songs:** use your own or CC-licensed material, or songs for **private
> learning only**. Never share stems, renders or exports of songs you do not own.

---

## 0. The song folder

```
my-song/
  song.json            the manifest (below)
  beat.json            a beat preset      (presets/README.md format)
  melody.json          a melody preset
  bass.json            a melody preset for a FLEX bass        (optional)
  bass-sample.json     the bass line mapped to the sample     (optional)
  bass-hit.wav         one bass hit to load into a Sampler    (optional)
```

```json
{"label": "MySong", "bpm": 93.75,
 "beat": "beat.json", "melody": "melody.json", "bass": "bass.json",
 "bass_sample": "bass-sample.json", "bass_sample_wav": "bass-hit.wav"}
```

Every key is optional except at least one of `beat` / `melody` / `bass`. Paths
are relative to the folder (absolute paths work too); a missing file is refused
**before** FL is touched. `label` names the channels (`<label> Melody`,
`<label> Bass`); the `label=` argument overrides it, the folder name is the
fallback.

```
fl_pattern(action="create", name="MySong")          # if the target is not pattern 1
fl_preset(action="load_song", song_dir="~/songs/my-song", target_pattern=2)
```

**Before you start:** FL Studio running with the FLStudioMCP controller, FL in
front, **hands off the mouse and keyboard** while it runs (≈2 min). Screen
Recording + Accessibility permission for the terminal (see `SCREEN-CONTROL.md` §0).

What you get in FL:

| Part | Where | How |
|---|---|---|
| Tempo | project BPM | `bpm` |
| Drums | 808 Kick / Snare / HiHat steps, target pattern | `beat`, repeated over the pattern |
| Melody | channel `<label> Melody` (FLEX) | `melody` |
| Bass | channel `<label> Bass` (Sampler) | `bass_sample_wav` playing `bass_sample`; else a FLEX playing `bass` |
| Level | master fader | lowered just enough that the output peak stays ≤ -1 dBFS |

Everything is normal FL notes/steps: edit freely. FL's API cannot build the
playlist, so this is one pattern, not an arrangement.

Need tempo/key/chords of an audio file first? `fl_audio(action="analyze", path=...)`
(numpy, in-process) gives tempo, key, a chord timeline and an 808 root note to
write the presets from.

## 1. What `load_song` does

Each step reuses a verified tool; each reports `ok` + evidence:

| Step | Tool underneath | Proof it worked |
|---|---|---|
| tempo | `transport.setBPM` | state read-back |
| beat | `fl_preset load_beat` (fill) | steps read back per channel, tiled to the pattern |
| melody | `fl_preset load_melody` | **script_ran**: the roll script rewrote its state file |
| bass sample | `fl_channel load_sample` | FL renamed the channel after the file, or the editor shows it |
| bass notes | `fl_preset load_melody` | script_ran |
| level | `fl_mixer fix_clipping` | pre-fader peak + fader dB ≤ target |


---

## 2. The safety rules every screen step follows

1. **Panel-aware first** (`utils/fl_panels.py`): before a step reads the
   screen, put the window it needs on top — `clear_plugins()` (View ▸ Close
   all plugin windows) before piano-roll work; `show_channel_editor(i)` hides
   the roll and mixer (`ui.hideWindow`) and opens the channel's window via its
   channel-rack button; `restore()` puts the panels back. Tool access:
   `fl_ui_screen(module="ui", action="panels" | "set_panels")`.
2. **Locate, then confirm by hint, then click.** Buttons are found by OCR and
   must show the expected hover hint ("Tools", "Load sample file", "FX slot 1
   options") — otherwise nothing is clicked.
3. **Verify by read-back, never by "the click happened".** Slots are read back
   after add/remove, the roll script must have *run*, the sample load must show.
4. **A failed step leaves nothing behind:** a queued note write that did not
   run is withdrawn; a wrong plugin is taken back out; the transport is left
   as found.

---

## 3. Troubleshooting (real incidents, 2026-10-02)

| Symptom | Cause | Fix (now built in) |
|---|---|---|
| Beat plays 1 bar then silence | 16 steps in a 4-bar pattern | `load_beat` fills the pattern |
| `script did not run` | roll covered by a plugin editor / roll closed | `clear_plugins()` before roll steps; script-selection wrench is title-anchored + hint-confirmed |
| `script did not run` although the roll is visible | FL's **keyboard focus** was on the Browser / Channel rack — the trigger shortcut goes to the focused form | the trigger focuses the roll first (`ui.showWindow(3)` + `ui.setFocused(3)`); `load_song` re-selects + retries once |
| Open panel left open / `go-to sheet did not resolve` | the resolved row was double-clicked before it filled in | `open_panel` waits for the file's row, retries the double-click, accepts "panel closed = loaded" |
| Colour group changed in the roll | old fixed-position wrench click hit the colour selector | wrench found from the roll title, confirmed by hint |
| Wrong plugin inserted (Emphasizer, Fruity delay 2) | double-click into the plugin picker while its list reflowed | samples go through the Sampler's own Open panel instead; `add_effect` double-checks the row and takes a wrong plugin back out |
| `'Load sample file' button not found` | the roll / a maximized mixer covered the editor | `show_channel_editor()` (panel-aware) |
| Master clipping | loud loop | `fix_clipping` after every load (FL meters are **pre-fader**; fader writes are only readable in the *next* call) |
| Transport left playing | a step started playback | `load_song` stops it if it was stopped at the start |
| FL ignores all clicks, MCP still answers | a mouse drag never released | `scripts/screen.py mouse-up` |

Still open: whole-song arrangement (playlist), drum kit sounds (the 808 rack is
used).

---

## 4. Extending it

- New screen-driven step: follow `SCREEN-CONTROL.md` §5 and the rules in §2
  above (panel-aware → hint-confirmed → read-back). Put the logic in
  `src/fl_studio_mcp/utils/`, expose it as an **action of an existing tool**
  (the default surface is capped at 22 tools), test it with every OS call
  mocked (see `tests/test_song_loader.py`, `tests/test_panels_and_load_sample.py`).
- After adding or renaming a tool: `uv run python scripts/gen-inventory.py`.

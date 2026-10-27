# Instruments you can add

`fl_channel("add")` / `fl_channel("add")` take the exact name from FL's **Add** menu.
The useful ones:

| Instrument | Good for |
|---|---|
| `FLEX` | piano, synth, bass — the versatile one (default for melodies) |
| `FL Keys` | sampled piano/keys |
| `Sytrus` | modern lead/bass |
| `3x Osc` | classic saw/sine synth |
| `GMS` / `Harmor` / `Sawer` | synths, resynthesis |
| `MiniSynth` / `BooBass` / `Transistor Bass` | bass |

See **every** available name from any terminal:
```
cd fl-studio-mcp && ./scripts/fl-add.sh --list
```

## FLEX: pick a preset (verified 2026-10-11)
A new FLEX channel opens on the first Core Synths preset (a "BAS ..." bass: usable as a bass as-is).
The preset API cannot step FLEX (`find_preset` reads a stale name). Pick from the editor's **Library** tab:
open the editor (`show_channel_editor` through `fl_channel("load_sample")` style panels, or click the channel
name), click **Library**, the list groups presets by pack (General MIDI Library has Nylon Guitar, Steel Guitar,
12-String, Jazz, Electric ...), then click the preset name. **Verify by reading the editor title**
("<Preset> (Insert N)") and check the neighbour rows: the list can shift one row and select the wrong
preset (Jazz Guitar instead of Nylon Guitar). Screenshot coordinates from the screen tool's look action with the FL-window option
are 30 px above screen click coordinates.
- FL Keys = Grand Piano, no setup. Plucked/guitar alternatives: FL's DirectWave guitar multisamples
  (`Packs/Instruments/Guitar/*.fst`: Classical Acoustic, Jazz, Piezo, Strat...) exist but are not loaded by any tool yet.

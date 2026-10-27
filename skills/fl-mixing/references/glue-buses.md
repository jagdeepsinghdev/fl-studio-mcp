# Glue a whole beat: drum bus, music bus, shared room (so separate sounds read as one record)

For a full track (drums + instruments + a sample). Vocal buses are in `vocal-bus-routing.md`; this is
the instrumental version used for the 2026-10-11 Afrobeats build. Numbers are **convention, not
auditioned**. Why it works: sounds that share one acoustic space and one dynamics stage are hard to tell
apart as separate sources (`music-theory` `idea-to-record.md`).

## 1. Layout
```
kick, rim, clap, shaker, perc, hat (each its own insert) -- route only --> [Drums bus] -> Master
guitar, keys, bass, flute (each its own insert)          -- route only --> [Music bus] -> Master
guitar, keys, flute, perc, clap, rim (+ a little shaker, hat)  -- sends --> [Room] -> Master
```
Kick and bass stay out of the Room (dry low end). Fruity Reeverb 2 on the Room insert: **Dry 0%,
Wet 100%**, decay about 1.5 s, pre-delay 25 ms, **low cut 250 Hz**, a little modulation (20%).

## 2. Mixer tracks in a fresh project
A new default project has only **16 inserts** (Master + Insert 1-16); Insert 20+ does not exist
("Index out of range"). `fl_mixer("add_tracks")` needs the mixer's own toolbar on screen. Easier: reuse the
inserts of unused default channels (1-5) as the buses, e.g. 1 = Drums bus, 2 = Music bus, 3 = Room.

## 3. One call for the routing (`fl_vocal("run", ops=[...])`, stop_on_error=false)
```
{"tool":"mixer","action":"route_only","track":7,"to":1}      # each drum insert -> Drums bus (read back)
{"tool":"mixer","action":"route_only","track":6,"to":2}      # each instrument insert -> Music bus
{"tool":"mixer","action":"sends","track":6,"to":3,"level":0.28}   # sends into the Room
{"tool":"mixer","action":"name","track":1,"name":"Drums bus"}     # names read back one trip late: re-run once
```
Send levels used: guitar 0.28, keys 0.3, flute 0.3, perc 0.2, clap 0.25, rim 0.25, shaker 0.15, hat 0.1.

## 4. Effects (`fl_mixer("add_fx")` clicks: FL in front, hands off; ~20 s each)
| Insert | Plugin | Settings (`fl_plugin("dial"/"set_param")`) |
|---|---|---|
| Room | Fruity Reeverb 2 | Dry level 0, Wet level 0.8 (100%), Low cut 250 Hz, Predelay 25 ms, Mod Depth 0.2 |
| Drums bus | Fruity Compressor | ratio 3:1, threshold -14 dB, attack 20 ms, release 160 ms, gain +2 dB |
| Master | Fruity Soft Clipper | defaults (gentle saturation); the default template also has an Emphasizer here |
`fl_plugin("list_params", index=<track>, slot_index=<slot>)` first: knob names come from the plugin.

## 5. Levels and pans
- Channel volume rule of thumb (`fl_channel("set_vol")`): lead 0.8, kick 0.78, bass 0.62, rim 0.55, clap/perc 0.5,
  hat 0.38, shaker 0.26. Keys under the lead (0.5).
- **Pans: use the mixer track** (`fl_mixer("set_pan")`). `channels.setChannelPan` via the channel tool did not
  stick (read back 0.0 on every channel, 2026-10-11).
- Peak check while playing: `fl_mixer("get_peaks")`; aim for the master under -3 dBFS in the loudest section.

## 6. Checklist
1. Every instrument and drum on a bus; kick and bass dry; the Room is 100% wet?
2. Room low-cut so the low end stays clean; drums compressed together, not each?
3. Shaker/hat well below the snare/rim; melody loudest?
4. Peaks measured while playing, not guessed?

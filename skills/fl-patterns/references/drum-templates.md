# Drum templates (copy, then edit the step numbers)

Steps are 1–16 per bar (16th-note grid; 1, 5, 9, 13 are the beats). Translate a template
into a boolean list and write it per drum channel with `fl_channel("set_steps", index,
steps=[…])` (one channel per drum part; `fl_batch` to do several in one trip). A template
like `[1,5,9,13]` becomes `[1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0]`. For multi-bar, repeat/
extend the list (e.g. 64 steps = 4 bars). Genre patterns are from convention, not
auditioned — tune by ear.

| Style | kick (beats/steps) | snare | hat |
|---|---|---|---|
| Trap (half-time, 140) | `1,8,11` | `9` | all 16 |
| Drill (140) | `1,5,12` | `9` | all 16 |
| Drill, moving (4 bars) | `1,7,12` / `1,8,11` / `1,7,15` / `1,6,11` | `9`/`13`/`9`/`13` | odd steps; bar 4 also 14,16 |
| House (124) | `1,5,9,13` | `5,13` | `3,7,11,15` |
| Boom-bap (90) | `1,4,11` | `5,13` | `1,3,5,7,9,11,13,15` |

Example (trap, 1 bar, 3 channels — channel indexes from `fl_state`):
```
fl_channel("set_steps", index=<kick>,  steps=[1,0,0,0, 0,0,0,0, 1,0,0,1, 0,0,0,0])
fl_channel("set_steps", index=<snare>, steps=[0,0,0,0, 0,0,0,0, 0,1,0,0, 0,0,0,0])
fl_channel("set_steps", index=<hat>,   steps=[1,1,1,1, 1,1,1,1, 1,1,1,1, 1,1,1,1])
fl_pattern("set_len", pattern=1, beats=4)     # tight loop
```
**Clear the drums** (start over, melody untouched): send all-`0` steps to each drum
channel — `fl_channel("set_steps", index, steps=[0]*16)`. (The legacy `fl_clean_drums`
does this in one call behind `LEGACY_TOOLS=1`.)

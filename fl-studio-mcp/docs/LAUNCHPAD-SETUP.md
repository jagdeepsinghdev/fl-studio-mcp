# Launchpad (LP) setup for FL Studio — via the MCP layer

_Last updated: 2026-10-02. Controller v10.1 (input monitor) + `fl_launchpad`
MCP tool (5 actions, server-side)._

Goal: use a Novation-style **Launchpad** as a human-in-the-loop grid for
FL's **step sequencer** — tap a pad to toggle a drum step, tap the pattern
row to switch patterns, and have the pads **light up** to match FL's current
state. Everything runs through the `flstudio` MCP server; there is exactly
**one manual step** (below), which is a limitation of the FL trial build
(its MIDI-input picker has no scripting API — verified by full API sweep).

## How the data flows

```
 LP pad  ──USB──▶  FL Studio MIDI input (ONE-TIME PICK, step 2)
                     │  (FL routes the notes to its controller layer)
                     ▼
              controller "FL Studio MCP" virtual port  (v10.1)
                     │  input monitor (armed after the 1st command)
                     ▼
              input_notes.jsonl   (one JSON line per note on/off)
                     │
        fl_launchpad(action="apply")   ← you / the AI
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
 channels.setGridBit      patterns.jumpToPattern
 (step toggle, read-modify- (pattern-row tap)
  write via get/set_steps)
        ▲
        │  fl_launchpad(action="light")
 "FL Studio MCP Out" ──(IAC / direct)──▶ LP pads light up
```

Files (all in `~/Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP/`):
`input_notes.jsonl` (raw taps), `lp_mapping.json` (grid config),
`lp_state.json` (last consumed log offset).

## 1. Hardware

- Launchpad MK1/MK2/X/Pro (or any 8×8-note grid controller) connected by
  **USB** (use the supplied cable; no extender).
- The FL Studio **MIDI loop agent** must be running (it is: LaunchAgent
  `com.flstudiomcp.fl-midi-loop`). The loop only *forwards* virtual ports —
  it never sends notes on its own.
- **No physical LP?** Use an IAC bus as the "LP": Audio MIDI Setup → create
  an IAC device → select that IAC bus as FL's MIDI input → any MIDI source
  (MIDI Monitor, another app, the test harness) can then inject pad notes.

## 2. The ONE manual step (per FL install, not per session)

1. Open **Options → MIDI Settings** (or `F10` → *MIDI* tab).
2. In the **MIDI Input** list, find the Launchpad (or your IAC bus), select
   it and press **Enable**.
3. If the list looks stale after a loop restart: click **Refresh device
   list** (the input *binding* persists; only the device list can go stale).

That's it. There is **no API** for this pick (full v45 API sweep incl. the
`device` module — see CLAUDE.md §5), so it stays manual, **once per
install**, on any build.

## 3. Activate the controller (needs the v10.1 controller loaded)

The v10.1 controller (`SCRIPT_VERSION = "v10.1-lp"`) carries the input
monitor. It is already synced to the install dir; it takes effect on the
**next FL restart** (hard rule 4 — controller changes need one restart;
MCP-server changes do not).

After a restart, run **one** of these to arm the monitor (it arms on the
*first* command the controller processes — by design, the monitor is never
active on a cold FL with no traffic):

```
fl_connect(action="status")     # quick; or
fl_state                        # full snapshot
```

## 4. Configure the grid (MCP only)

Defaults (already sensible for a standard 8×8):

| key | default | meaning |
|---|---|---|
| `rows` / `cols` | 8 / 8 | grid geometry |
| `first_note` | 0 | note number of pad (0,0) — **set by calibrate** |
| `pattern_row` | 0 | the top row = pattern launch (col+1 = pattern #) |
| `channels` | `[0..7]` | channel **index** per step row (top→bottom, skipping the pattern row) |

```
fl_launchpad(action="map", rows=8, cols=8, pattern_row=0,
             channels=[0,1,2,3])      # rows 1-4 → channels 0-3
```

**Calibrate** (do this once per controller model — models differ in their
base note range): press **any one pad**, then:

```
fl_launchpad(action="calibrate")      # anchors first_note to the note it saw
```

Then verify the tap was seen:

```
fl_launchpad(action="status")         # pending_note_ons = 1 expected
```

## 5. Use it

```
fl_launchpad(action="apply")          # consume pending taps:
                                      #   pattern-row tap  → select pattern
                                      #   grid tap         → TOGGLE that
                                      #   channel/step in the step grid
fl_launchpad(action="light")          # re-light the grid from FL's state
                                       # (note-on 96 = on, note-off = off)
```

`apply` is idempotent per tap: each pad tap **toggles** (read the current
sequence via `fl_channel get_steps`, flip the bit, write back via
`set_steps`). A second tap on the same pad clears the step.

Loop it for live use: call `apply` + `light` after each batch of taps
(e.g. every 0.5–1 s while the human is playing) — or wire it into
`fl_batch` if you want one call.

## 6. Pad → action reference (defaults)

| Pad (row, col) | Note (first_note=F) | Action |
|---|---|---|
| (0, c) | F + c | select pattern **c+1** |
| (1, c) | F + 8 + c | toggle channel `channels[0]`, step c |
| (2, c) | F + 16 + c | toggle channel `channels[1]`, step c |
| … | … | … |
| (7, c) | F + 56 + c | toggle channel `channels[6]`, step c |

(With 8 step rows and only N channels listed, extra rows are ignored.)

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `input_notes.jsonl` never grows | FL's MIDI input not set to the LP (step 2); or v10.1 not loaded (`fl_connect status` → check after restart); or no command processed yet (run `fl_state` once). |
| Pads seen but `apply` says `consumed: 0` | mapping `first_note` wrong → `calibrate` again (press the **top-left** pad). |
| `light` error: no `FL Studio MCP Out` port | the `fl-midi-loop` LaunchAgent died — `launchctl kickstart -k gui/$(id -u)/com.flstudiomcp.fl-midi-loop`, then re-pick the input (Refresh device list). |
| A tap selects a pattern instead of toggling | you hit the `pattern_row`; change it with `map(pattern_row=…)`. |
| Different note range per bank/zone | Launchpad banks shift note ranges; this tool handles the first bank's geometry — `map(first_note=…)` per zone if needed. |
| FL shows a crash dialog after a controller change | v10.1's `fl_connect open` crash guard auto-reverts to the last-known-good controller and reports it in the `open` result; v10.1's `OnInit` is bare (prints only) by design — the v10 OnInit crash (2026-10-02) is the reason. |

## 8. Trial-build notes

The LP path is **plain MIDI in/out** — no `ui.*`/`screen.*` calls — so it
works on the trial build exactly as it will on a licensed one. The only
trial-specific wart is the manual input pick (step 2), which is also a
licensed-build manual step (FL simply has no API for it).

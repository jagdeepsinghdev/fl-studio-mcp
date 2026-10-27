#!/usr/bin/env bash
# Drain the queued melody notes into the piano roll and play.
#
# Prereq (ONE manual click, per FL session):
#   In the Piano roll window, click the small script-selector button
#   (left end of the "Piano roll - Piano" toolbar) and choose "ComposeWithLLM".
#   FL resets this to the default on every launch, so do it once after each restart.
#
# Then run this. It sends the trigger keystroke and verifies the notes landed.
cd "$(dirname "$0")"
PY=.venv/bin/python

# Send the ComposeWithLLM trigger (Cmd+Opt+Y on macOS) via pynput
$PY - <<'EOF'
import subprocess, time, json, os
from pynput.keyboard import Controller, Key
subprocess.run(["osascript","-e",'tell application "FL Studio" to activate'], capture_output=True)
time.sleep(1.0)
kb = Controller()
kb.press(Key.cmd); kb.press(Key.alt)
kb.press("y")                 # letter y (use the string form, not keycode)
time.sleep(0.05)
kb.release("y"); kb.release(Key.alt); kb.release(Key.cmd)
print("sent Cmd+Opt+Y ...")
time.sleep(2.0)
S = os.path.expanduser("~/Documents/Image-Line/FL Studio/Settings/Piano roll scripts")
st = json.load(open(os.path.join(S,"piano_roll_state.json")))
n = st.get("notes",[])
ticks = sorted(x["time_ticks"] for x in n)
if ticks:
    print(f"OK — {len(n)} notes in piano roll, spanning {min(ticks)/96:.1f} to {max(ticks)/96:.1f} beats")
else:
    print("STILL 0 notes — ComposeWithLLM is not the selected piano-roll script. Select it, then re-run.")
EOF

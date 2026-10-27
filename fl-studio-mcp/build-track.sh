#!/usr/bin/env bash
# =============================================================================
# build-track.sh — one-command FL Studio track builder (auto-loads presets + verifies)
#
# Usage:
#   ./build-track.sh <beat-preset> [melody-preset]
#   ./build-track.sh drill drill-c-minor            # beat + melody/chords
#   ./build-track.sh punjabi-banger                 # beat only
#   ./build-track.sh lofi --piano                   # beat + add/ensure a piano channel
#
# What it does (all via the MCP server, robustly):
#   1. Ensures the named channels exist (adds a piano if requested)
#   2. Loads the beat preset  -> drums  (auto-cleared first, matched BY NAME)
#   3. Sets REAL BPM + resets playback speed + sets pattern length
#   4. Loads the melody preset -> the selected piano channel (queues it)
#   5. VERIFIES every drum channel by reading it back; prints a table so any
#      crossed/empty channel is obvious
#   6. Plays. For the melody to LAND, select "ComposeWithLLM" once in the
#      piano-roll toolbar, then re-run this script (or ./apply-melody.sh).
#
# Preset names = file names (without .json) in presets/beats/ and presets/melodies/.
# List them: ./build-track.sh list
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python

if [[ "${1:-}" == "list" || $# -eq 0 ]]; then
  echo "=== beat presets ===";    ls presets/beats/*.json     | xargs -n1 basename
  echo "=== melody presets ===";  ls presets/melodies/*.json  | xargs -n1 basename
  echo ""
  echo "usage: ./build-track.sh <beat> [melody] [--piano]"
  exit 0
fi

BEAT="$1"
MELODY=""
PIANO=0
for a in "$@"; do
  [[ "$a" == "--piano" ]] && PIANO=1
  [[ "$a" != "list" && "$a" != "--piano" && "$a" != "$BEAT" ]] && MELODY="$a"
done

$PY - "$BEAT" "$MELODY" "$PIANO" <<'PYEOF'
import sys, json, os, time
beat, melody, piano = sys.argv[1], sys.argv[2], int(sys.argv[3])
from fl_studio_mcp.utils.connection import get_connection
conn = get_connection()

def cmd(action, params={}):
    return conn.send_command(action, params)

print(f"\n### Building track: beat={beat}  melody={melody or '(none)'}  add_piano={bool(piano)}")

# 1. Ensure a piano channel exists if requested
if piano:
    r = cmd("probe.exec", {"code":
        "import channels; print(channels.channelCount())"})
    # find a free mixer track + add a FLEX piano if none selected has a keyboard name
    r = cmd("channels.getSelect")
    sel = r.get("index", -1)
    have_piano = False
    for c in cmd("channels.getAll", {}).get("channels", []):
        nm = (c.get("name","") or "").lower()
        if any(k in nm for k in ("piano","keys","flex","sytrus","sampler")):
            have_piano = True
    if not have_piano:
        print("  adding FLEX piano channel ...")
        r = conn.send_command("channels.add", {"instrument": "FLEX", "label": "Piano"})
        print("   add ->", r)
    # re-read all channels to find the piano index
    chans = cmd("channels.getAll", {}).get("channels", [])
    piano_idx = next((c["index"] for c in chans
                     if any(k in (c.get("name","") or "").lower()
                            for k in ("piano","keys","flex","sytrus","sampler"))), None)
    print(f"  piano channel index: {piano_idx}")

# 2. Load the beat (exec the tool's logic via the same module)
from fl_studio_mcp.tools.exec_python import register_exec_tools
# We can't easily call the closure; instead replicate with the public command path:
data = json.load(open(f"presets/beats/{beat}.json"))
allch = cmd("channels.getAll").get("channels", [])
n2i = {(c.get("name","") or "").strip().lower(): c["index"] for c in allch}

def resolve(spec, part):
    i = n2i.get((spec.get("name") or "").strip().lower(), -1)
    if i >= 0: return i
    for nm, idx in n2i.items():
        if part in nm: return idx
    return -1

# clear all drums first
for c in allch:
    nm = (c.get("name","") or "").lower()
    if any(k in nm for k in ("kick","snare","clap","hat","808","drum","perc","dhol","dholak","tabla")):
        cmd("channels.setStepSequence", {"channel": c["index"], "pattern": [False]*16, "target_pattern": 1})

print("\n### Beat parts (name -> channel index -> pattern):")
for part, spec in data.get("channels", {}).items():
    idx = resolve(spec, part)
    pat = [bool(x) for x in spec.get("pattern", [0]*16)]
    if idx < 0:
        print(f"  {spec.get('name'):16}  !! NO MATCH (skipped)")
        continue
    cmd("channels.setStepSequence", {"channel": idx, "pattern": pat, "target_pattern": 1})
    print(f"  {spec.get('name'):16}  ch{idx}  steps={[i for i,b in enumerate(pat) if b]}")

# 3. Real BPM + speed + pattern length
bpm = data.get("bpm", 120)
cmd("transport.setBPM", {"bpm": bpm})
cmd("transport.setPlaybackSpeed", {"speed": 1.0})
pat_beats = 4
if melody:
    m = json.load(open(f"presets/melodies/{melody}.json"))
    pat_beats = m.get("length_beats", 4)
cmd("patterns.setLength", {"index": 0, "beats": pat_beats})
print(f"\n### BPM={bpm}  pattern={pat_beats} beats")

# 4. Load melody (queue it)
if melody:
    m = json.load(open(f"presets/melodies/{melody}.json"))
    # select the piano channel
    if piano_idx is not None:
        cmd("channels.setSelect", {"index": piano_idx, "selected": True})
        cmd("channels.selectOnly", {"index": piano_idx}) if "channels.selectOnly" else None
    S = os.path.expanduser("~/Documents/Image-Line/FL Studio/Settings/Piano roll scripts")
    def s2t(step): return round(step/4.0, 3)
    notes = []
    for n in m.get("melody", []):
        notes.append({"midi": int(n["note"]), "duration": round(n.get("dur",1)/4.0,3),
                      "time": s2t(n.get("step",0)), "velocity": round(n.get("vel",80)/127,3)})
    for ch in m.get("chords", []):
        for midi in ch.get("notes", []):
            notes.append({"midi": int(midi), "duration": round(ch.get("dur",4)/4.0,3),
                          "time": s2t(ch.get("step",0)), "velocity": 0.7})
    req = [{"action":"clear"}, {"action":"add_notes","notes":notes}]
    with open(os.path.join(S,"mcp_request.json"),"w") as f: json.dump(req,f)
    print(f"\n### Melody queued: {len(notes)} notes (needs ComposeWithLLM selected to land)")
    # trigger once (works only if script is already selected)
    try:
        from fl_studio_mcp.utils.fl_trigger import get_trigger
        get_trigger().trigger()
    except Exception as e:
        print("   (trigger skipped:", e, ")")

# 5. VERIFY by reading back every drum channel
print("\n### VERIFY (read back):")
for c in allch:
    nm = (c.get("name","") or "")
    r = cmd("channels.getStepSequence", {"channel": c["index"], "steps": 16})
    seq = [int(b) for b in r.get("sequence", [])]
    on = [i for i,b in enumerate(seq) if b]
    print(f"  {nm:16}  ch{c['index']}  -> {on}")

# 6. Play
cmd("transport.setLoopMode", {"mode": "pattern"})
cmd("transport.stop", {})
time.sleep(0.4)
cmd("transport.start", {})
print("\n### PLAYING. Select ComposeWithLLM in the piano-roll toolbar, then re-run to land the melody.")
PYEOF

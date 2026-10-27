#!/usr/bin/env python3
"""Virtual MIDI loopback for macOS (no IAC driver required).

Creates / attaches to CoreMIDI endpoints (visible to FL Studio, mido, rtmidi):
  "FL Studio MCP"      destination  <- the MCP server writes here (mido output)
  "FL Studio MCP Bus"  source       -> FL Studio's MIDI *Input*
  "FL Studio MCP Out"  destination  -> FL Studio's MIDI *Output*
Everything received on "FL Studio MCP" is forwarded to "FL Studio MCP Bus".

Port lifecycle (verified on macOS 26.5):
  - A virtual endpoint persists until the *process* that created it exits.
    rtmidi's MidiIn.close()/MidiOut.close() and the Python GC do NOT remove
    the endpoint; after a process dies the endpoints stay in the CoreMIDI
    list but are inert (nothing forwards into them), and no other process
    can open a virtual port with the same name.
  - Consequence: this script must be the *creator* of the endpoints it
    forwards from. If stale endpoints with the same names are found at
    startup (a previous instance was SIGKILLed / crashed), this process
    exits with a clear message; the operator must run
      launchctl kickstart -k gui/$(id -u)/<label>
    so launchd terminates the stale holder and re-spawns us, which then
    takes ownership of the ports and re-establishes forwarding.

Auto-started by a LaunchAgent (label from $FL_MIDI_LOOP_LABEL, default
com.flstudiomcp.fl-midi-loop)
(RunAtLoad + KeepAlive; logs to /tmp/fl_midi_loop.{out,err}.log).
Keep this running while using the MCP server.

Gotcha for FL: if this process restarts while FL Studio is open, FL's
MIDI input binding goes stale and MCP commands time out until you click
"Refresh device list" in Options -> MIDI settings (the Input binding
itself persists). At login/reboot the agent starts before FL, so no
refresh is needed.
"""
import os
import sys
import time

import rtmidi

PORT_MCP = "FL Studio MCP"
PORT_BUS = "FL Studio MCP Bus"
PORT_OUT = "FL Studio MCP Out"
ALL_NAMES = (PORT_MCP, PORT_BUS, PORT_OUT)
AGENT_LABEL = os.environ.get("FL_MIDI_LOOP_LABEL", "com.flstudiomcp.fl-midi-loop")
RECOVERY = f"launchctl kickstart -k gui/$(id -u)/{AGENT_LABEL}"


def _die(msg: str) -> None:
    print(f"fl_midi_loop: {msg}", file=sys.stderr, flush=True)
    print(f"fl_midi_loop: recovery -> {RECOVERY}", file=sys.stderr, flush=True)
    sys.exit(1)


def _close(port) -> None:
    if port is None:
        return
    try:
        port.close()
    except Exception:
        pass


# ---- Refuse to start over stale endpoints -------------------------------
# (See module docstring: we must be the creator of the ports we forward.)
probe = rtmidi.MidiIn()
stale_out = [n for n in ALL_NAMES if n in list(probe.get_ports() or [])]
probe_out = rtmidi.MidiOut()
stale_in = [n for n in ALL_NAMES if n in list(probe_out.get_ports() or [])]
_close(probe)
_close(probe_out)
stale = sorted(set(stale_out) | set(stale_in))
if stale:
    _die(
        f"stale virtual port(s) present: {stale}. A previous fl_midi_loop "
        "instance was killed without a clean exit and still owns these "
        "endpoints; they cannot be recreated or forwarded by a new process. "
        f"Recovery: {RECOVERY}"
    )

# ---- Create the endpoints -----------------------------------------------
bus = rtmidi.MidiOut()
try:
    bus.open_virtual_port(PORT_BUS)
except Exception as e:
    _die(f"cannot create '{PORT_BUS}': {e}")

sink = rtmidi.MidiIn()
try:
    sink.open_virtual_port(PORT_OUT)
except Exception as e:
    _die(f"cannot create '{PORT_OUT}': {e}")
sink.ignore_types(sysex=False, timing=False, active_sense=False)

mcp_in = rtmidi.MidiIn()
try:
    mcp_in.set_callback(lambda ev, _data: bus.send_message(ev[0]))
    mcp_in.open_virtual_port(PORT_MCP)
except Exception as e:
    _die(f"cannot create '{PORT_MCP}': {e}")
mcp_in.ignore_types(sysex=False, timing=False, active_sense=False)

print(
    f"fl_midi_loop ready ({PORT_MCP} -> {PORT_BUS}; {PORT_OUT} as sink)",
    flush=True,
)

# ---- Run until asked to stop --------------------------------------------
_running = True


def _stop(_signum, _frame) -> None:
    global _running
    _running = False


import signal

signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)

while _running:
    time.sleep(0.5)

# Clean exit releases all virtual endpoints (close() alone would not).
for p in (bus, sink, mcp_in):
    _close(p)
print("fl_midi_loop: stopped, virtual ports released", flush=True)

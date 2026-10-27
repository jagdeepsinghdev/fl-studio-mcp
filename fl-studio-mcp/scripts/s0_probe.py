#!/usr/bin/env python3
"""S0 probe runner — runs discovery probes against the RUNNING FL Studio.

Layer: DISCOVERY ONLY (hard rule 1). Goes through the normal audited MIDI
connection (`probe.exec` / `probe.api` controller actions, already in v9),
so every call lands in `mcp_audit.jsonl`. These probes inform S0; the
delivered features (S1+) are verified through the MCP tools, not this script.

Usage (from fl-studio-mcp/):
  uv run python scripts/s0_probe.py ver            # S0.0: is the probe path alive?
  uv run python scripts/s0_probe.py flrack         # S0.1: P1 internal-module import probe
  uv run python scripts/s0_probe.py scratch        # S0.3-prep: PROBE pattern + channel
  uv run python scripts/s0_probe.py cleanup        # remove PROBE pattern (+ its channel via delete.channel)
  uv run python scripts/s0_probe.py stepparam      # S0.3: P4 set/getStepParameterByIndex
  uv run python scripts/s0_probe.py scorelog       # S0.2: P2 dumpScoreLog surface (read-only)
  uv run python scripts/s0_probe.py iac            # S0.2: IAC port discovery + test-note send
  uv run python scripts/s0_probe.py raw '<code>'   # ad-hoc probe.exec
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")

from fl_studio_mcp.utils.midi_connection import get_connection  # noqa: E402


def run(code: str, timeout: float = 20.0) -> dict:
    r = get_connection().send_command("probe.exec", {"code": code}, timeout=timeout)
    return r


def show(r: dict) -> None:
    out = r.get("stdout") or ""
    err = r.get("stderr") or ""
    if out:
        print("STDOUT:", out[:4000])
    if err:
        print("STDERR:", err[:2000])
    if not r.get("success", True) and "error" in r:
        print("ERROR:", r.get("error"))


# --------------------------------------------------------------------------- probes

PROBE_VER = """
import sys
out = {'py': sys.version.split()[0]}
for m in ('channels','patterns','mixer','transport','general','arrangement','midi','plugins','playlist'):
    try:
        mod = __import__(m)
        out[m] = len([n for n in dir(mod) if not n.startswith('_')])
    except Exception as e:
        out[m] = 'ERR:' + str(e)[:80]
print(out)
"""

PROBE_FLRACK = """
import importlib
CANDIDATES = ['flrack','flrack_proxy','flcpt','flcpt_proxy','flpianoroll','flpianoroll_proxy',
              'fl_rack','fl_chans','flr','enveditor','launchMapPages','screen','general','midi','flp']
out = {}
for m in CANDIDATES:
    try:
        mod = importlib.import_module(m)
        out[m] = [n for n in dir(mod) if not n.startswith('_')][:150]
    except Exception as e:
        out[m] = {'error': str(e)[:150]}
print(out)
"""

PROBE_STEPPARAM = """
import channels, patterns, midi
out = {}
out['midi_names'] = [n for n in dir(midi) if not n.startswith('_')]
out['set_get'] = {
    'setStepParameterByIndex': hasattr(channels, 'setStepParameterByIndex'),
    'getStepParameterByIndex': hasattr(channels, 'getStepParameterByIndex'),
}
idx = channels.getSelected()
pat = patterns.patternNumber()
out['target'] = {'channel': idx, 'pattern': pat, 'name': channels.getName(idx)}
# find a set step
found = None
for s in range(64):
    try:
        if channels.getGridBit(idx, pat, s):
            found = s
            break
    except Exception:
        break
out['first_set_step'] = found
if found is None:
    # lay a known pattern first (one hit on step 0)
    try:
        channels.setStepSequence(idx, [True] + [False] * 63)
        found = 0
        out['laid'] = 'step 0'
    except Exception as e:
        out['lay_err'] = str(e)[:200]
if found is not None:
    # try the param write: discover the enum names first
    for pname in ('VELOCITY','SHIFT','PITCH','REPEAT','RELEASE'):
        if not hasattr(midi, pname):
            out[pname] = 'enum-missing'
            continue
        try:
            val = 100 if pname == 'VELOCITY' else (50 if pname == 'SHIFT' else 0)
            try:
                channels.setStepParameterByIndex(idx, pat, found, getattr(midi, pname), val)
                args6 = ''
            except TypeError:
                args6 = '(6th-arg)'
                channels.setStepParameterByIndex(idx, pat, found, getattr(midi, pname), val, True)
            out[pname] = {'set': 'ok' + args6,
                          'read': getattr(channels, 'getStepParameterByIndex', lambda *a: 'n/a')(idx, pat, found, getattr(midi, pname))}
        except Exception as e:
            out[pname] = {'err': str(e)[:200]}
print(out)
"""

PROBE_SCORELOG = """
import general
out = {}
out['general_methods'] = sorted(n for n in dir(general) if not n.startswith('_'))
if hasattr(general, 'dumpScoreLog'):
    try:
        out['dumpScoreLog_doc'] = (general.dumpScoreLog.__doc__ or '')[:500]
    except Exception as e:
        out['dumpScoreLog_doc'] = 'err:' + str(e)[:100]
print(out)
"""

PROBE_IAC = """
import rtmidi
out = {'ports': []}
for i in range(rtmidi.getDeviceCount(rtmidi.OUTPUT_TYPE) if hasattr(rtmidi,'getDeviceCount') else 0):
    pass
try:
    n = rtmidi.getDeviceCount()
    for i in range(n):
        out['ports'].append({'i': i, 'name': rtmidi.getPortName(i),
                             'type': 'out' if rtmidi.isPortOpen(i) else '?'})
except Exception as e:
    out['err'] = str(e)[:200]
print(out)
"""


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "ver":
        show(run(PROBE_VER))
    elif cmd == "flrack":
        show(run(PROBE_FLRACK, 25.0))
    elif cmd == "stepparam":
        show(run(PROBE_STEPPARAM, 25.0))
    elif cmd == "scorelog":
        show(run(PROBE_SCORELOG))
    elif cmd == "iac":
        show(run(PROBE_IAC))
    elif cmd == "scratch":
        c = get_connection()
        print("create pattern:", c.send_command("patterns.create", {"name": "PROBE"}))
    elif cmd == "cleanup":
        c = get_connection()
        r = c.send_command("probe.exec", {"code": (
            "import patterns\n"
            "for p in range(patterns.patternCount()):\n"
            "    if patterns.getPatternName(p) == 'PROBE':\n"
            "        patterns.deletePattern(p)\n"
            "print('deleted')"
        )}, timeout=10.0)
        show(r)
    elif cmd == "raw":
        if len(sys.argv) < 3:
            print("usage: s0_probe.py raw '<code>'")
            return
        show(run(sys.argv[2], 25.0))
    else:
        print(f"unknown probe: {cmd}")
        sys.exit(2)


if __name__ == "__main__":
    main()

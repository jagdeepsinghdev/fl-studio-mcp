# name=FL Studio MCP Controller
# url=https://github.com/karl-andres/fl-studio-mcp
# supportedDevices=FL Studio MCP

"""
FL Studio MIDI Controller Script for MCP Integration.

This script runs inside FL Studio and receives MIDI trigger messages from the
MCP server. When triggered, it reads a command from a JSON file, executes the
corresponding FL Studio API function, and writes the response to another JSON file.

Communication flow:
1. MCP server writes command to mcp_command.json
2. MCP server sends MIDI note 127 (trigger)
3. This script receives the trigger via OnMidiMsg()
4. Script reads command JSON, executes FL Studio API
5. Script writes response to mcp_response.json
6. MCP server reads response
"""

import json
import os
import re
import sys
from pathlib import Path

# FL Studio API modules (available when running inside FL Studio)
import channels
import arrangement
import patterns
import midi
import mixer
import plugins
import transport


def _get_script_dir() -> Path:
    """Get the script directory path.

    FL Studio's Python environment doesn't support __file__, so we construct
    the path based on the platform's standard FL Studio settings location.
    """
    if sys.platform == "darwin":
        # macOS
        base = Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings"
    elif sys.platform == "win32":
        # Windows
        userprofile = os.environ.get("USERPROFILE", "~")
        base = Path(userprofile) / "Documents" / "Image-Line" / "FL Studio" / "Settings"
    else:
        # Linux (unlikely but handle it)
        base = Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings"

    return base / "Hardware" / "FLStudioMCP"


# File paths for JSON communication
SCRIPT_DIR = _get_script_dir()
COMMAND_FILE = SCRIPT_DIR / "mcp_command.json"
RESPONSE_FILE = SCRIPT_DIR / "mcp_response.json"

# MIDI trigger note
TRIGGER_NOTE = 127

# File-based trigger state (used when no MIDI transport is available,
# e.g. macOS builds without an IAC/virtual MIDI port)
HEARTBEAT_FILE = SCRIPT_DIR / "mcp_heartbeat.json"
_last_cmd_mtime = None
_hb_ticks = 0
_last_hb = 0.0


# v10.4i-uisteps: `ui.steps` — a bounded list of allowlisted ui/mixer/plugins
# calls in one trip (the engine half of `fl_ui_script`; routines live
# MCP-side). NOT DEPLOYED until synced + FL restarted (v10.4h-eq is deployed).
# v10.4h-eq: mixer.getEq / mixer.setEq (per-track parametric EQ).
SCRIPT_VERSION = "v10.4i-uisteps"

_READ_ONLY_ACTIONS = frozenset({
    "transport.getStatus", "transport.getBPM", "transport.getSwing",
    "transport.getLength", "mixer.getTrackCount", "mixer.getTrackInfo",
    "mixer.getAllTracks", "mixer.getSends", "mixer.getPeaks", "mixer.getEq",
    "channels.getCount",
    "channels.getInfo", "channels.getAll", "channels.getSelected",
    "channels.getGridBit", "channels.getStepSequence", "patterns.getLength",
    "patterns.list", "plugins.isValid", "plugins.getName",
    "plugins.getParamCount", "plugins.getParams", "plugins.getParamValue",
    "plugins.getPresetCount", "plugins.getColor", "probe.exec", "probe.api",
    "state.snapshot",
    "probe.patterns", "probe.tempo", "probe.playlist",
    "channels.getStepParameter",
    "probe.ilmcp",
    "ui.call", "screen.call", "ui.keySeq", "ui.steps",
})

# Actions that mutate state but are not destructive (the batch's undo rule
# applies to these; destructive actions never reach the batch).
_WRITE_ONLY_ACTIONS = frozenset({
    "transport.start", "transport.stop", "transport.record",
    "transport.setPosition", "transport.setLoopMode", "transport.setPlaybackSpeed",
    "transport.setBPM", "transport.setSwing",
    "mixer.setTrackVolume", "mixer.setTrackPan", "mixer.muteTrack",
    "mixer.soloTrack", "mixer.armTrack", "mixer.setTrackName", "mixer.setEq",
    "mixer.setTrackColor", "mixer.setStereoSep", "mixer.setSendLevel",
    "channels.select", "channels.selectOne", "channels.triggerNote",
    "channels.setVolume", "channels.setPan", "channels.mute", "channels.solo",
    "channels.setName", "channels.setColor", "channels.routeToMixer",
    "channels.setGridBit", "channels.setStepSequence", "channels.setStepParameter",
    "patterns.setLength", "patterns.create", "patterns.select", "patterns.clone",
    "patterns.setName", "transport.setTimesig", "state.snapshot",
    "file.save", "file.saveAs", "file.export",
    "plugins.setParamValue", "plugins.nextPreset", "plugins.prevPreset",
})

# Protocol v2: the command JSON carries request_id + protocol_version; the
# response MUST echo both. The MCP server refuses to consume a response whose
# request_id doesn't match its own (stale-reply protection), and flags replies
# without a request_id as _legacy_response (pre-v2 controllers tolerated).
PROTOCOL_VERSION = 2

def OnInit():
    """Called when the script is loaded."""
    print(f"FL Studio MCP Controller {SCRIPT_VERSION} initialized")
    print("FL Studio MCP Controller initialized")
    print(f"Command file: {COMMAND_FILE}")
    print(f"Response file: {RESPONSE_FILE}")


def OnDeInit():
    """Called when the script is unloaded."""
    print("FL Studio MCP Controller deinitialized")


def OnMidiMsg(event):
    """Called when a MIDI message is received."""
    # Check for trigger note (Note On, note 127)
    if event.midiId == 0x90 and event.data1 == TRIGGER_NOTE and event.data2 > 0:
        execute_pending_command()
        event.handled = True


def OnIdle():
    """Called periodically when FL Studio is idle.

    File-based trigger: polls for a new mcp_command.json and executes it.
    Also writes a throttled heartbeat so the MCP server can verify the
    script is loaded and see OnIdle cadence (including while playing).
    """
    global _last_cmd_mtime, _hb_ticks, _last_hb
    import time as _time

    _hb_ticks += 1
    now = _time.time()
    if _hb_ticks == 1 or now - _last_hb >= 0.5:
        _last_hb = now
        try:
            HEARTBEAT_FILE.write_text(json.dumps({
                "ticks": _hb_ticks,
                "time": now,
                "is_playing": bool(transport.isPlaying()),
            }))
        except Exception:
            pass

    try:
        st = COMMAND_FILE.stat()
    except OSError:
        return  # No command file yet
    if st.st_mtime == _last_cmd_mtime:
        return  # No new command
    try:
        command = json.loads(COMMAND_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return  # Partial write; retry on next tick
    _last_cmd_mtime = st.st_mtime
    run_command(command)


def _safe_exec(action: str, params: dict, dispatch) -> dict:
    """One-trip safety wrapper (A3), around any action:

    * ``_undo_name`` in params  -> ``general.saveUndo(name)`` BEFORE the action
      (ONE named undo per trip; the dispatcher never issues raw ``undo()``).
    * ``_identity`` in params   -> re-read the named target BEFORE a destructive
      action and abort with ``identity_ok: False`` when it doesn't match
      (the undo-incident rule: a stale selection must not delete the wrong thing).

    Both pieces of evidence are returned in the response (``undo_saved``,
    ``identity_ok``) so the dispatcher can check them in the same trip.
    """
    out: dict = {}
    try:
        import general
    except Exception:
        general = None

    if params.get("_undo_name") and action not in _READ_ONLY_ACTIONS:
        if general is not None:
            try:
                # v45: saveUndo(name, flags) — the flags arg is REQUIRED (pos 2).
                general.saveUndo(params["_undo_name"], 0)
                out["undo_saved"] = params["_undo_name"]
            except Exception as e:
                out["undo_error"] = str(e)
        else:
            out["undo_error"] = "general module unavailable"

    ident = params.get("_identity")
    if ident is not None:
        try:
            ok, detail = _verify_target(ident)
        except Exception as e:  # a broken re-read must refuse, not proceed
            ok, detail = False, f"identity re-read failed: {e}"
        out["identity_ok"] = ok
        out["identity_detail"] = detail
        if not ok:
            # Evidence travels with the abort: the dispatcher hard-refuses on
            # identity_ok=False even if the handler claimed success (P5).
            return {"error": f"identity mismatch, action not executed: {detail}", **out}

    result = dispatch()
    if out:
        result = {**result, **out}
    return result


def _verify_target(ident: dict) -> tuple:
    """Match the caller's named target against the live state. Returns (ok, detail)."""
    target = ident.get("target")
    name = ident.get("name")
    index = ident.get("index")
    if target == "channel":
        i = int(index if index is not None else 0)
        actual = channels.getChannelName(i, True)
        if name is not None and actual != name:
            return False, f"channel {i} is {actual!r}, expected {name!r}"
        return True, f"channel {i} = {actual!r}"
    if target == "pattern":
        n = int(index if index is not None else 1)
        if n < 1 or n > patterns.patternMax():
            return False, f"pattern {n} out of range"
        actual = patterns.getPatternName(n)
        if name is not None and actual != name:
            return False, f"pattern {n} is {actual!r}, expected {name!r}"
        return True, f"pattern {n} = {actual!r}"
    # fx / pattern_data / roll_notes: verify the selected channel identity
    sel = channels.selectedChannel(canBeNone=True, indexGlobal=True)
    if sel is None or sel < 0:
        return False, "no channel selected"
    actual = channels.getChannelName(sel, True)
    if name is not None and actual != name:
        return False, f"selected channel is {actual!r}, expected {name!r}"
    return True, f"selected channel {sel} = {actual!r}"


def _read_back(action: str, params: dict, before: dict) -> dict:
    """Same-trip read-back: after executing a WRITE action, re-read the affected
    state and return it so the server verifies in the SAME MIDI trip (plan §10
    review outcome 4: no second round trip for verification; P5: success
    messages lie — the dispatcher cross-checks state_after instead).

    Read-only actions and unknown actions return {} (nothing to verify).
    """
    if action in ("transport.setBPM",):
        try:
            return {"bpm": round(mixer.getCurrentTempo() / 1000.0, 3)}
        except Exception:
            return {}
    if action in ("transport.setSwing",):
        try:
            return {"swing": round(channels.getSwing(), 4)}
        except Exception:
            return {}
    if action in ("transport.setPlaybackSpeed",):
        try:
            return {"speed": transport.getPlaybackSpeed()}
        except Exception:
            return {}
    if action == "mixer.setTrackVolume":
        try:
            t = int(params.get("track", 0))
            return {"track": t, "volume": mixer.getTrackVolume(t)}
        except Exception:
            return {}
    if action == "mixer.setTrackPan":
        try:
            t = int(params.get("track", 0))
            return {"track": t, "pan": mixer.getTrackPan(t)}
        except Exception:
            return {}
    if action == "channels.setVolume":
        try:
            i = int(params.get("index", 0))
            # v10.4e (L14): v45 getChannelVolume(index, mode, useGlobalIndex)
            # — mode is the 2nd arg; True returned dB. Read back linear 0-1.
            return {"index": i, "volume": channels.getChannelVolume(i, False, True),
                    "channel_name": channels.getChannelName(i, True)}
        except Exception:
            return {}
    if action == "channels.setPan":
        try:
            i = int(params.get("index", 0))
            return {"index": i, "pan": channels.getChannelPan(i, True),
                    "channel_name": channels.getChannelName(i, True)}
        except Exception:
            return {}
    if action == "channels.setStepParameter":
        # v10.2: re-read the exact step/param we just wrote (same trip).
        # v10.4e (S2.3): read with the SAME useGlobalIndex flag as the write
        # (the old GET=False/SET=True asymmetry was the prime suspect for
        # per-channel shift/pan drops). 'param' default fixed to an official
        # name (SPT_VELOCITY does not exist in v45).
        return handle_channels_get_step_param({
            "channel": params.get("channel", 0),
            "step": params.get("step", 0),
            "param": params.get("param", "pVelocity"),
            "target_pattern": params.get("target_pattern"),
            "use_global": params.get("use_global", True)})
    if action == "channels.setName":
        try:
            i = int(params.get("index", 0))
            return {"index": i, "name": channels.getChannelName(i, True)}
        except Exception:
            return {}
    if action == "channels.selectOne":
        try:
            i = int(params.get("index", 0))
            return {"selected_index": channels.selectedChannel(canBeNone=True, indexGlobal=True),
                    "channel_name": channels.getChannelName(i, True)}
        except Exception:
            return {}
    if action in ("channels.setGridBit", "channels.setStepSequence"):
        try:
            c = int(params.get("channel", 0))
            return {"channel": c, "selected_index": channels.selectedChannel(canBeNone=True, indexGlobal=True)}
        except Exception:
            return {}
    if action == "patterns.setLength":
        try:
            i = int(params.get("index", 0))
            return {"index": i, "length_beats": patterns.getPatternLength(i)}
        except Exception:
            return {}
    if action == "patterns.select":
        try:
            return {"active": patterns.patternNumber()}
        except Exception:
            return {}
    if action == "plugins.setParamValue":
        try:
            pi = int(params.get("param_index", 0))
            slot = int(params.get("slot_index", -1))
            pg = int(params.get("plugin_index", 0))
            if slot >= 0:
                return {"value": plugins.getParamValue(pi, pg, slot, True)}
            return {"value": plugins.getParamValue(pi, pg, -1, params.get("use_global", True))}
        except Exception:
            return {}
    return {}  # read-only or unverified action


def run_command(command: dict) -> None:
    """Execute an already-parsed command dict and write the response file.

    Protocol v2: the response echoes the command's request_id and
    protocol_version. Write actions additionally carry `state_after` — the
    affected state re-read in the same trip (see _read_back).
    """
    action = command.get("action", "")
    params = command.get("params", {})
    response = {"success": False, "error": None}
    try:
        before = _read_back(action, params, {})
        result = _safe_exec(action, params, lambda: dispatch_command(action, params))
        if result.get("error"):
            # Keep safety evidence (identity_ok / undo_saved) on the abort path
            # so the dispatcher can act on it — never trust an error-only reply.
            response = {"success": False,
                        **{k: v for k, v in result.items() if k != "error"},
                        "error": result["error"]}
        else:
            after = _read_back(action, params, before)
            response = {"success": True, **result}
            if after:
                response["state_after"] = after

    except Exception as e:
        response["error"] = f"Error executing command: {e}"

    # Protocol v2 echo (always present, even on error paths).
    if "request_id" in command:
        response["request_id"] = command["request_id"]
    if "protocol_version" in command:
        response["protocol_version"] = command["protocol_version"]
    elif command.get("protocol_version") is None and "request_id" in command:
        response["protocol_version"] = PROTOCOL_VERSION

    write_response(response)


def execute_pending_command():
    """Read command from JSON file, execute it, and write response.

    Used by the MIDI trigger path (OnMidiMsg). The OnIdle path polls the
    file directly and calls run_command().
    """
    global _last_cmd_mtime
    response = {"success": False, "error": None}

    try:
        # Read command file
        if not COMMAND_FILE.exists():
            response["error"] = "No command file found"
            write_response(response)
            return

        command_text = COMMAND_FILE.read_text()
        command = json.loads(command_text)

    except json.JSONDecodeError as e:
        response["error"] = f"Invalid JSON in command file: {e}"
        write_response(response)
        return
    except Exception as e:
        response["error"] = f"Error executing command: {e}"
        write_response(response)
        return

    _last_cmd_mtime = COMMAND_FILE.stat().st_mtime
    run_command(command)


def write_response(response: dict):
    """Write response to JSON file."""
    try:
        RESPONSE_FILE.write_text(json.dumps(response, indent=2))
    except Exception as e:
        print(f"Error writing response: {e}")


def handle_batch_run(params: dict) -> dict:
    """A5: execute a list of {action, params} items in this ONE trip.
    One saveUndo (params['_undo_name']) before the first write; reads never
    save. Stop-on-fail: later items are reported 'skipped', never executed.
    Destructive items must never arrive here (the dispatcher rejects them)."""
    import time as _t
    items = params.get("items", [])
    if not isinstance(items, list) or not items:
        return {"error": "batch: no items"}
    if len(items) > 50:
        return {"error": f"batch: too many items ({len(items)} > 50)"}

    out: dict = {"results": []}
    try:
        import general
    except Exception:
        general = None

    first_write = True
    for it in items:
        a = it.get("action", "")
        p = dict(it.get("params") or {})
        # One undo for the whole trip, before the first write item.
        if "_undo_name" in params and a not in _READ_ONLY_ACTIONS and first_write:
            first_write = False
            if general is not None:
                try:
                    general.saveUndo(params["_undo_name"], 0)
                    out["undo_saved"] = params["_undo_name"]
                except Exception as e:
                    out["undo_error"] = str(e)
        t0 = _t.time()
        if a in _READ_ONLY_ACTIONS or a in _WRITE_ONLY_ACTIONS:
            res = _safe_exec(a, p, lambda _a=a, _p=p: dispatch_command(_a, _p))
        else:
            res = {"error": f"unknown action: {a}"}
        item = {"action": a, "ms": int((_t.time() - t0) * 1000)}
        if res.get("error"):
            item["ok"] = False
            item["error"] = res["error"]
            for k in ("identity_ok", "identity_detail", "undo_saved"):
                if k in res:
                    item[k] = res[k]
            out["results"].append(item)
            # stop-on-fail: mark the rest as skipped (never executed)
            for rest in items[items.index(it) + 1:]:
                out["results"].append({
                    "action": rest.get("action", "?"),
                    "ok": False,
                    "error": "skipped (previous item failed)",
                })
            return out
        item["ok"] = True
        for k in ("state_after", "identity_ok", "undo_saved", "undo_error"):
            if k in res:
                item[k] = res[k]
        # L3 (v10.4e): read items carry their payload — the controller puts
        # read results at the top level of res (value / channels / params /...).
        if a in _READ_ONLY_ACTIONS:
            for k, v in res.items():
                if k not in ("success", "error", "state_after"):
                    item[k] = v
        out["results"].append(item)
    return out


def handle_state_snapshot() -> dict:
    """B1: one-trip session snapshot (bpm, transport, patterns, selection,
    version). Read-only; the server adds project title/path + piano-roll mtime."""
    out = {"state": {}}
    try:
        s = out["state"]
        s["bpm"] = round(mixer.getCurrentTempo() / 1000.0, 3)
        try:
            s["transport"] = {
                "is_playing": transport.isPlaying() == 1,
                "is_recording": transport.isRecording() == 1,
                "position": transport.getSongPosHint(),
            }
        except Exception:
            s["transport"] = {}
        s["selected_pattern"] = patterns.patternNumber()
        s["patterns"] = _named_patterns()
        # active_pattern + active_is_default: the pattern that FL is
        # currently playing/reading (1-based).  _named_patterns() skips
        # default (empty) patterns, so if the active one is a default
        # it won't appear in the patterns list — flag it so the agent
        # can diagnose "all step reads came back empty" (skill fl-patterns
        # lesson: a select can drift the active pattern to an empty default).
        ap = patterns.patternNumber()
        s["active_pattern"] = ap
        s["active_is_default"] = bool(patterns.isPatternDefault(ap))
        count = channels.channelCount(True)
        s["channel_count"] = count
        sel = channels.selectedChannel(canBeNone=True, indexGlobal=True)
        s["selected_channel"] = (
            {"index": int(sel), "name": channels.getChannelName(int(sel), True)}
            if sel is not None and 0 <= int(sel) < count else None
        )
        try:
            s["fl_version"] = general.getVersion()
        except Exception:
            pass
    except Exception as e:
        out["error"] = f"state.snapshot failed: {e}"
    return out


# =============================================================================
# File Handlers (L15, v10.4e)
# =============================================================================

def _import_mod(name: str):
    """Import an FL module, or None (a build may lack modules entirely)."""
    import importlib
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _file_probe_dump() -> dict:
    """Bounded, names-only view of the file-relevant FL modules (L15):
    a failed save/export carries this so the post-restart matrix can pin
    the real v45 API without extra probe trips."""
    out = {}
    for name in ("general", "flp"):
        m = _import_mod(name)
        if m is None:
            out[name] = "import failed"
        else:
            out[name] = sorted(n for n in dir(m)
                               if re.search(r"save|export|project|wav|mp3|render", n, re.I))
    return out


def _run_candidates(cands: list) -> tuple:
    """Try (label, fn) candidates in order; return (ok-result, attempt log).
    Every attempt's exception text is recorded — the signature oracle (P4)."""
    attempts = []
    for label, fn in cands:
        try:
            r = fn()
            return ({"via": label, "result": r if r is not None else True}), attempts
        except Exception as e:
            attempts.append(f"{label}: {type(e).__name__}: {str(e)[:200]}")
    return None, attempts


def _file_no_api(notes: str = "") -> dict:
    """L15 (v10.4f): the post-deploy matrix (2026-10-01) pinned v45 — there is
    NO importable file API at all: general has no save/saveAs/export methods
    (probe.api: clearLog…setUndoHistoryPos), and flp/file/project modules do
    not exist (No module named). The v10.4e candidate cascades are retired.
    Saving is OS-level: fl_connect(action='save') (File>Save, incl. the
    native save-dialog dismissal); export = the native File > Export dialog.
    These handlers stay so fl_file can say so honestly instead of faking."""
    return {"success": False, "status": "no_api_in_v45",
            "error": ("v45 has no importable file API. " + notes +
                      "Use fl_connect(action='save') for OS-level File>Save.")}


def handle_file_save(params: dict) -> dict:
    return _file_no_api("No in-process save in this build; ")


def handle_file_save_as(params: dict) -> dict:
    """L15 (v10.4f): explicit-path save is OS-level too (File > Save As)."""
    path = params.get("path", "")
    if not path:
        return {"success": False, "error": "file.saveAs requires 'path'"}
    return _file_no_api(f"No in-process saveAs to {path!r}; ")


def handle_file_export(params: dict) -> dict:
    """L15 (v10.4f): wav/mp3/stems export all go through the native
    File > Export dialog (L16 native-menu path); no Python API in v45."""
    path = params.get("path", "")
    fmt = params.get("format", "wav")
    if not path:
        return {"success": False, "error": "file.export requires 'path'"}
    if fmt not in ("wav", "mp3", "stems"):
        return {"success": False, "error": f"unknown format {fmt!r} (wav|mp3|stems)"}
    return _file_no_api(f"No in-process {fmt} export; ")


def handle_undo_restore(params: dict) -> dict:
    """Best-effort restore to a saved undo level (A5 rollback).
    level: -1 = the level saved most recently by this controller (the batch's).
    Explicitly NOT transactional: partial batch state may remain."""
    try:
        import general
        level = int(params.get("level", -1))
        if level == -1:
            # restore to the last saved level (the batch's undo point)
            last = general.getUndoHistoryLast()
            general.restoreUndoLevel(last)
        else:
            general.restoreUndoLevel(level)
        return {"restored": True, "level": level}
    except Exception as e:
        return {"error": f"undo.restore failed: {e}"}


def handle_delete_channel(params: dict) -> dict:
    """Delete a channel by index. The caller's name is checked by _safe_exec
    before this runs (identity verify)."""
    index = int(params.get("index", 0))
    name = params.get("name")
    try:
        # v45: no direct channels.deleteChannel — use probe.exec as the mechanism
        import channels
        count = channels.channelCount(True)
        if index < 0 or index >= count:
            return {"error": f"channel index {index} out of range (0-{count-1})"}
        # Delete via the general module or probe.exec
        # channels has no delete in v45; use probe.exec as the mechanism
        code = f"import channels; channels.deleteChannel({index})"
        import io, sys, contextlib
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            exec(code, {})
        return {"deleted": True, "index": index, "name": name or "",
                "stdout": out.getvalue(), "stderr": err.getvalue()}
    except Exception as e:
        return {"error": f"delete.channel failed: {e}"}


def handle_delete_pattern(params: dict) -> dict:
    """Delete a pattern slot by 1-based number."""
    n = int(params.get("index", 1))
    name = params.get("name")
    try:
        if n < 1 or n > patterns.patternMax():
            return {"error": f"pattern {n} out of range"}
        patterns.deletePattern(n)
        return {"deleted": True, "pattern": n, "name": name or "",
                "pattern_count": patterns.patternCount()}
    except Exception as e:
        return {"error": f"delete.pattern failed: {e}"}


def handle_delete_pattern_data(params: dict) -> dict:
    """Clear all content (rack steps + roll notes) in a 0-based pattern index.
    The pattern slot remains; only its content is wiped.

    v10.4f (R2 matrix, live 2026-10-01): in v45 patterns.clearPattern does
    NOT clear the channel-rack step grid (23 bits remained after the call —
    the user's groove survived it; what it does clear is unknown, likely
    pattern-owned roll notes). So the scoped setGridBit loop is the PRIMARY
    rack-clearer (target pattern selected first via _pattern_scope, steps up
    to the pattern length), and clearPattern runs second as the roll-content
    clear — a failure there is reported, not fatal (some builds open a modal).
    Same-trip read-back (P5): remaining active grid bits. The old v10.4e
    clearPattern-first order is gone.
    """
    idx = int(params.get("index", 0))
    with _pattern_scope(idx + 1) as sc:
        if sc.error:
            return {"error": sc.error}
        try:
            steps = max(int(patterns.getPatternLength(idx)) * 4, 64)
        except Exception:
            steps = 64
        steps = min(steps, 1024)
        # 1) rack grid — the proven clearer (one setGridBit per cell).
        for c in range(channels.channelCount(True)):
            for i in range(steps):
                try:
                    channels.setGridBit(c, i, 0, True)
                except Exception:
                    pass
        # 2) roll content — clearPattern (best effort; report, don't fail).
        cp_error = None
        try:
            patterns.clearPattern(idx)
        except Exception as e:
            cp_error = f"{type(e).__name__}: {str(e)[:200]}"
        # 3) same-trip read-back: remaining active grid bits.
        remaining = 0
        for c in range(channels.channelCount(True)):
            for i in range(steps):
                try:
                    if channels.getGridBit(c, i, True):
                        remaining += 1
                except Exception:
                    pass
        out = {"cleared": True, "index": idx, "method": "grid-loop+clearPattern",
               "remaining_grid_bits": remaining, **_pattern_info()}
        if cp_error:
            out["clearPattern_error"] = cp_error
        return out


def handle_delete_fx(params: dict) -> dict:
    """Remove an FX insert from a channel's FX chain (by slot index)."""
    ch_idx = int(params.get("index", 0))
    slot = int(params.get("slot_index", 0))
    name = params.get("name")
    try:
        # v45: plugins has no removeInsert — use probe.exec
        code = f"""
import plugins
try:
    plugins.removeInsert({ch_idx}, {slot}, True)
    print("removed")
except Exception as e:
    print("ERR:" + str(e))
"""
        import io, contextlib
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            exec(code, {})
        text = out.getvalue().strip()
        if text.startswith("ERR:"):
            return {"error": text[4:]}
        return {"removed": True, "channel": ch_idx, "slot": slot, "name": name or ""}
    except Exception as e:
        return {"error": f"delete.fx failed: {e}"}


def handle_delete_roll_notes(params: dict) -> dict:
    """Clear all notes in the currently-open piano roll via ComposeWithLLM queue.
    (Same path as fl_clear_piano_roll; routed here so it's tier=destructive.)"""
    # The actual clearing happens via the ComposeWithLLM script queue.
    # The MCP tool (fl_delete roll_notes) writes the queue directly;
    # this controller handler is a fallback / direct path.
    return {"note": "roll_notes delete is handled by the MCP tool via the "
                   "ComposeWithLLM script queue; no controller action needed"}


def dispatch_command(action: str, params: dict) -> dict:
    """Route command to appropriate handler and return result."""

    # Transport commands
    if action == "transport.start":
        return handle_transport_start()
    elif action == "transport.stop":
        return handle_transport_stop()
    elif action == "transport.record":
        return handle_transport_record()
    elif action == "transport.getStatus":
        return handle_transport_get_status()
    elif action == "transport.setPosition":
        return handle_transport_set_position(params)
    elif action == "transport.getLength":
        return handle_transport_get_length()
    elif action == "transport.setLoopMode":
        return handle_transport_set_loop_mode(params)
    elif action == "transport.setPlaybackSpeed":
        return handle_transport_set_playback_speed(params)
    elif action == "transport.getBPM":
        return handle_transport_get_bpm()
    elif action == "transport.setBPM":
        return handle_transport_set_bpm(params)
    elif action == "transport.setTimesig":
        return handle_transport_set_timesig(params)

    # Mixer commands
    elif action == "mixer.getTrackCount":
        return handle_mixer_get_track_count()
    elif action == "mixer.getTrackInfo":
        return handle_mixer_get_track_info(params)
    elif action == "mixer.getAllTracks":
        return handle_mixer_get_all_tracks(params)
    elif action == "mixer.setTrackVolume":
        return handle_mixer_set_track_volume(params)
    elif action == "mixer.setTrackPan":
        return handle_mixer_set_track_pan(params)
    elif action == "mixer.muteTrack":
        return handle_mixer_mute_track(params)
    elif action == "mixer.soloTrack":
        return handle_mixer_solo_track(params)
    elif action == "mixer.armTrack":
        return handle_mixer_arm_track(params)
    elif action == "mixer.setTrackName":
        return handle_mixer_set_track_name(params)
    elif action == "mixer.setTrackColor":
        return handle_mixer_set_track_color(params)
    elif action == "mixer.setStereoSep":
        return handle_mixer_set_stereo_sep(params)

    # Channel commands
    elif action == "channels.getCount":
        return handle_channels_get_count(params)
    elif action == "channels.getInfo":
        return handle_channels_get_info(params)
    elif action == "channels.getAll":
        return handle_channels_get_all()
    elif action == "channels.getSelected":
        return handle_channels_get_selected()
    elif action == "channels.select":
        return handle_channels_select(params)
    elif action == "channels.selectOne":
        return handle_channels_select_one(params)
    elif action == "channels.triggerNote":
        return handle_channels_trigger_note(params)
    elif action == "channels.setVolume":
        return handle_channels_set_volume(params)
    elif action == "channels.setPan":
        return handle_channels_set_pan(params)
    elif action == "channels.mute":
        return handle_channels_mute(params)
    elif action == "channels.solo":
        return handle_channels_solo(params)
    elif action == "channels.setName":
        return handle_channels_set_name(params)
    elif action == "channels.setColor":
        return handle_channels_set_color(params)
    elif action == "channels.routeToMixer":
        return handle_channels_route_to_mixer(params)

    elif action == "probe.patterns":
        return handle_probe_patterns(params)
    elif action == "patterns.getLength":
        return handle_patterns_get_length(params)
    elif action == "patterns.setLength":
        return handle_patterns_set_length(params)
    elif action == "patterns.list":
        return handle_patterns_list(params)
    elif action == "patterns.create":
        return handle_patterns_create(params)
    elif action == "patterns.select":
        return handle_patterns_select(params)
    elif action == "patterns.clone":
        return handle_patterns_clone(params)
    elif action == "patterns.setName":
        return handle_patterns_set_name(params)
    elif action == "transport.getSwing":
        return handle_transport_get_swing()
    elif action == "transport.setSwing":
        return handle_transport_set_swing(params)
    elif action == "mixer.getSends":
        return handle_mixer_get_sends(params)
    elif action == "mixer.getPeaks":
        return handle_mixer_get_peaks(params)
    elif action == "mixer.getEq":
        return handle_mixer_get_eq(params)
    elif action == "mixer.setEq":
        return handle_mixer_set_eq(params)
    elif action == "mixer.setSendLevel":
        return handle_mixer_set_send_level(params)
    elif action == "probe.tempo":
        return handle_probe_tempo(params)
    elif action == "probe.playlist":
        return handle_probe_playlist(params)

    # Step sequencer commands
    elif action == "channels.getGridBit":
        return handle_channels_get_grid_bit(params)
    elif action == "channels.setGridBit":
        return handle_channels_set_grid_bit(params)
    elif action == "channels.getStepSequence":
        return handle_channels_get_step_sequence(params)
    elif action == "channels.setStepSequence":
        return handle_channels_set_step_sequence(params)
    elif action == "channels.getStepParameter":
        return handle_channels_get_step_param(params)
    elif action == "channels.setStepParameter":
        return handle_channels_set_step_param(params)

    # Plugin commands
    elif action == "plugins.isValid":
        return handle_plugins_is_valid(params)
    elif action == "plugins.getName":
        return handle_plugins_get_name(params)
    elif action == "plugins.getParamCount":
        return handle_plugins_get_param_count(params)
    elif action == "plugins.getParams":
        return handle_plugins_get_params(params)
    elif action == "plugins.getParamValue":
        return handle_plugins_get_param_value(params)
    elif action == "plugins.setParamValue":
        return handle_plugins_set_param_value(params)
    elif action == "plugins.getPresetCount":
        return handle_plugins_get_preset_count(params)
    elif action == "plugins.nextPreset":
        return handle_plugins_next_preset(params)
    elif action == "plugins.prevPreset":
        return handle_plugins_prev_preset(params)
    elif action == "plugins.getColor":
        return handle_plugins_get_color(params)
    elif action == "probe.exec": return probe_exec(params)
    elif action == "probe.api":
        return probe_api(params)
    elif action == "probe.ilmcp":
        return handle_probe_ilmcp(params)
    elif action == "ui.call":
        return handle_ui_call(params)
    elif action == "ui.keySeq":
        return handle_ui_key_seq(params)
    elif action == "ui.steps":
        return handle_ui_steps(params)
    elif action == "screen.call":
        return handle_screen_call(params)
    elif action == "setup":
        return handle_setup(params)

    # L15 (v10.4e): project file / export (candidate cascade, oracle-driven)
    elif action == "file.save":
        return handle_file_save(params)
    elif action == "file.saveAs":
        return handle_file_save_as(params)
    elif action == "file.export":
        return handle_file_export(params)

    # A4: destructive targets (all wrapped by _safe_exec: undo + identity)
    elif action == "delete.channel":
        return handle_delete_channel(params)
    elif action == "delete.pattern":
        return handle_delete_pattern(params)
    elif action == "delete.pattern_data":
        return handle_delete_pattern_data(params)
    elif action == "delete.fx":
        return handle_delete_fx(params)
    elif action == "delete.roll_notes":
        return handle_delete_roll_notes(params)

    # A5: batch runner — ONE MIDI trip for a list of items; one undo before
    # the first write; stop-on-fail with per-item results.
    elif action == "batch.run":
        return handle_batch_run(params)
    elif action == "undo.restore":
        return handle_undo_restore(params)

    # B1: session snapshot (read-only, one trip)
    elif action == "state.snapshot":
        return handle_state_snapshot()

    else:
        return {"error": f"Unknown action: {action}"}


# =============================================================================
# Transport Handlers
# =============================================================================


def handle_transport_start() -> dict:
    """Toggle play/pause."""
    transport.start()
    return {"is_playing": transport.isPlaying() == 1}


def handle_transport_stop() -> dict:
    """Stop playback."""
    transport.stop()
    return {"stopped": True}


def handle_transport_record() -> dict:
    """Toggle recording."""
    transport.record()
    return {"is_recording": transport.isRecording() == 1}


def handle_transport_get_status() -> dict:
    """Get transport status."""
    loop_mode = transport.getLoopMode()
    return {
        "is_playing": transport.isPlaying() == 1,
        "is_recording": transport.isRecording() == 1,
        "position": transport.getSongPosHint(),
        "loop_mode": "song" if loop_mode == 1 else "pattern",
    }


def handle_transport_set_position(params: dict) -> dict:
    """Set playback position."""
    position = params.get("position", 0)
    mode = params.get("mode", 2)  # Default: seconds
    transport.setSongPos(position, mode)
    return {"position": transport.getSongPosHint()}


def handle_transport_get_length() -> dict:
    """Get song length."""
    return {
        "ticks": transport.getSongLength(3),
        "seconds": transport.getSongLength(2),
        "milliseconds": transport.getSongLength(1),
    }


def handle_transport_set_loop_mode(params: dict) -> dict:
    """Set loop mode."""
    mode = params.get("mode", "pattern")
    current_mode = transport.getLoopMode()
    target_mode = 1 if mode.lower() == "song" else 0

    if current_mode != target_mode:
        transport.setLoopMode()

    return {"mode": mode}


def handle_transport_set_playback_speed(params: dict) -> dict:
    """Set playback speed."""
    speed = params.get("speed", 1.0)
    transport.setPlaybackSpeed(speed)
    return {"speed": speed}


def handle_transport_get_bpm() -> dict:
    """Read the project's real BPM. mixer.getCurrentTempo() returns BPM * 1000."""
    raw = mixer.getCurrentTempo()
    bpm = round(raw / 1000.0, 3)
    return {"bpm": bpm}


def handle_transport_set_bpm(params: dict) -> dict:
    """Set the project's real BPM. mixer.setCurrentTempo() takes BPM * 1000."""
    bpm = params.get("bpm", 120)
    mixer.setCurrentTempo(int(round(bpm * 1000)))
    return {"bpm": round(mixer.getCurrentTempo() / 1000.0, 3)}


def handle_transport_set_timesig(params: dict) -> dict:
    """L13 (v10.4f): set the project time signature.

    v45 (pinned by the 2026-10-01 post-deploy matrix): transport has NO
    setTimesig. The real API is general.setNumerator(n) +
    general.setDenominator(d) (both call clean live). SETTERS ONLY — no
    getter in general/patterns/midi/transport, so read-back is honestly
    'set, no getter'.
    """
    num = int(params.get("numerator", 4))
    den = int(params.get("denominator", 4))
    g = _import_mod("general")
    if g is None:
        return {"success": False,
                "error": "general module not importable in this build",
                "attempt": {"numerator": num, "denominator": den}}
    try:
        g.setNumerator(num)
        g.setDenominator(den)
    except Exception as e:
        cands = sorted(n for n in dir(g)
                       if re.search(r"numer|denom|timesig", n, re.I))
        return {"success": False,
                "error": (f"general.setNumerator/setDenominator failed: "
                          f"{type(e).__name__}: {str(e)[:200]}"),
                "timesig_like": cands,
                "attempt": {"numerator": num, "denominator": den}}
    return {"success": True, "numerator": num, "denominator": den,
            "read_back": None,
            "read_back_note": "set did not raise; v45 has no timesig getter"}
    return out


# =============================================================================
# Pattern Handlers (length)
# =============================================================================

def handle_patterns_get_length(params: dict) -> dict:
    """Get pattern length in beats. index is 0-based (Pattern 1 = index 0)."""
    idx = params.get("index", 0)
    length = patterns.getPatternLength(idx)
    return {"index": idx, "length_beats": length}


def handle_patterns_set_length(params: dict) -> dict:
    """Set pattern length in beats. index is 0-based (Pattern 1 = index 0)."""
    idx = params.get("index", 0)
    beats = params.get("beats", 4)
    patterns.setPatternLength(idx, beats)
    return {"index": idx, "length_beats": patterns.getPatternLength(idx)}


# =============================================================================
# Pattern management (create / list / select / clone)
# =============================================================================
# Verified live on FL 2026.1.6:
#  * setPatternName(n, name) on a *default* pattern CREATES it with no dialog.
#  * jumpToPattern() / findFirstNextEmptyPat() onto an empty default pattern opens a
#    MODAL "Pattern N name" dialog that blocks this controller until a human closes it.
#    So we never jump to a default pattern (handle_patterns_select refuses).
#  * clonePattern() clones the ACTIVE pattern into slot active+1, shifts later patterns
#    up by one, and makes the clone active. No dialog.
# Pattern numbers here are 1-based; getPatternLength/setPatternLength take index-1.

def _named_patterns() -> list:
    out = []
    total = patterns.patternCount()
    n = 1
    while len(out) < total and n <= patterns.patternMax():
        if not patterns.isPatternDefault(n):
            out.append({
                "pattern": n,
                "name": patterns.getPatternName(n),
                "length_beats": patterns.getPatternLength(n - 1),
            })
        n += 1
    return out


def handle_patterns_list(params: dict) -> dict:
    """List all non-default patterns plus the active one."""
    return {"patterns": _named_patterns(), "active": patterns.patternNumber()}


def handle_patterns_set_name(params: dict) -> dict:
    """B5 rename: rename an existing pattern.
    v45: 2-arg setPatternName(index, name). The 3-arg form with `flags`
    CRASHES FL (EAccessViolation) — verified live 2026-10-01 (C4)."""
    n = int(params.get("pattern", 1))
    name = params.get("name")
    if not name:
        return {"error": "name is required"}
    if n < 1 or n > patterns.patternMax() or patterns.isPatternDefault(n):
        return {"error": f"pattern {n} does not exist (create it first)"}
    patterns.setPatternName(n, str(name))  # 2-arg (v45; 3-arg crashes)
    return {"pattern": n, "name": patterns.getPatternName(n),
            "active": patterns.patternNumber()}


def handle_patterns_create(params: dict) -> dict:
    """Create a pattern in the first free slot without jumping to it (no dialog)."""
    name = params.get("name")
    if not name:
        return {"error": "name is required (a default-named pattern is not created)"}
    n = 1
    while n <= patterns.patternMax() and not patterns.isPatternDefault(n):
        n += 1
    if n > patterns.patternMax():
        return {"error": "no free pattern slot"}
    patterns.setPatternName(n, str(name))  # v45: 2-arg (verified live 2026-10-01)
    if params.get("color") is not None:
        patterns.setPatternColor(n, int(params["color"]))
    if params.get("length_beats"):
        patterns.setPatternLength(n - 1, int(params["length_beats"]))
    return {
        "pattern": n,
        "name": patterns.getPatternName(n),
        "length_beats": patterns.getPatternLength(n - 1),
        "active": patterns.patternNumber(),
    }


def handle_patterns_select(params: dict) -> dict:
    """Make an existing (non-default) pattern the active one."""
    n = int(params.get("pattern", 1))
    if n < 1 or n > patterns.patternMax():
        return {"error": f"pattern {n} out of range"}
    if patterns.isPatternDefault(n) and n != patterns.patternNumber():
        return {"error": f"Pattern {n} does not exist yet; create it first "
                         "(selecting an empty pattern opens a blocking rename dialog)"}
    patterns.jumpToPattern(n)
    return {"active": patterns.patternNumber(), "name": patterns.getPatternName(n)}


def handle_patterns_clone(params: dict) -> dict:
    """Clone the active pattern (or params['pattern']) into the next slot; clone becomes active."""
    if params.get("pattern") is not None:
        sel = handle_patterns_select({"pattern": params["pattern"]})
        if "error" in sel:
            return sel
    src = patterns.patternNumber()
    patterns.clonePattern()
    new = patterns.patternNumber()
    if params.get("name"):
        patterns.setPatternName(new, str(params["name"]))  # v45: 2-arg
    return {
        "source": src,
        "pattern": new,
        "name": patterns.getPatternName(new),
        "note": "later patterns shifted up by one slot",
        "patterns": _named_patterns(),
    }


# =============================================================================
# Swing (global) and mixer sends
# =============================================================================

def handle_transport_get_swing() -> dict:
    return {"swing": round(channels.getSwing(), 4)}


def handle_transport_set_swing(params: dict) -> dict:
    swing = max(0.0, min(1.0, float(params.get("swing", 0.0))))
    channels.setSwing(swing)
    return {"swing": round(channels.getSwing(), 4)}


def handle_mixer_get_sends(params: dict) -> dict:
    """List active routes from a mixer track: [{to, level}]. Track 0 = Master."""
    src = int(params.get("track", 0))
    sends = []
    for dst in range(mixer.trackCount()):
        try:
            if mixer.getRouteSendActive(src, dst):
                sends.append({"to": dst, "level": round(mixer.getRouteToLevel(src, dst), 3)})
        except Exception:
            continue  # FL raises "Index out of range" for invalid pairs (e.g. src == dst)
    return {"track": src, "sends": sends}


def handle_mixer_set_send_level(params: dict) -> dict:
    """Set (and enable if needed) the route level from one mixer track to another."""
    src = int(params.get("track", 0))
    dst = int(params.get("to", 0))
    level = max(0.0, min(1.0, float(params.get("level", 0.8))))
    if src == dst:
        return {"error": "source and destination must differ"}
    try:
        if not mixer.getRouteSendActive(src, dst):
            mixer.setRouteTo(src, dst, 1)
        mixer.setRouteToLevel(src, dst, level)
        return {"track": src, "to": dst, "level": round(mixer.getRouteToLevel(src, dst), 3)}
    except Exception as e:
        return {"error": f"send {src}->{dst} failed: {e}"}


# =============================================================================
# Mixer Handlers
# =============================================================================


def handle_mixer_get_track_count() -> dict:
    """Get number of mixer tracks."""
    return {"count": mixer.trackCount()}


def handle_mixer_get_track_info(params: dict) -> dict:
    """Get info about a mixer track."""
    track = params.get("track", 0)
    return {
        "index": track,
        "name": mixer.getTrackName(track),
        "volume": mixer.getTrackVolume(track),
        "volume_db": mixer.getTrackVolume(track, 1),
        "pan": mixer.getTrackPan(track),
        "stereo_separation": mixer.getTrackStereoSep(track),
        "is_muted": mixer.isTrackMuted(track) == 1,
        "is_solo": mixer.isTrackSolo(track) == 1,
        "is_armed": mixer.isTrackArmed(track) == 1,
        "color": hex(mixer.getTrackColor(track)),
    }


def handle_mixer_get_all_tracks(params: dict) -> dict:
    """Get info about all mixer tracks."""
    include_empty = params.get("include_empty", False)
    tracks = []
    track_count = mixer.trackCount()

    for i in range(track_count):
        name = mixer.getTrackName(i)

        # Skip empty tracks if requested
        if not include_empty and (not name or name.startswith("Insert ")):
            if i != 0:  # Always include master
                continue

        tracks.append({
            "index": i,
            "name": name if name else ("Master" if i == 0 else f"Insert {i}"),
            "volume": mixer.getTrackVolume(i),
            "pan": mixer.getTrackPan(i),
            "is_muted": mixer.isTrackMuted(i) == 1,
            "is_solo": mixer.isTrackSolo(i) == 1,
        })

    return {"tracks": tracks}


def handle_mixer_set_track_volume(params: dict) -> dict:
    """Set mixer track volume."""
    track = params.get("track", 0)
    volume = params.get("volume", 0.8)
    mixer.setTrackVolume(track, volume)
    return {
        "volume": mixer.getTrackVolume(track),
        "volume_db": mixer.getTrackVolume(track, 1),
    }


def handle_mixer_set_track_pan(params: dict) -> dict:
    """Set mixer track pan."""
    track = params.get("track", 0)
    pan = params.get("pan", 0.0)
    mixer.setTrackPan(track, pan)
    return {"pan": mixer.getTrackPan(track)}


def handle_mixer_mute_track(params: dict) -> dict:
    """Mute/unmute mixer track."""
    track = params.get("track", 0)
    muted = params.get("muted")  # None = toggle

    if muted is None:
        mixer.muteTrack(track, -1)
    else:
        mixer.muteTrack(track, 1 if muted else 0)

    return {
        "is_muted": mixer.isTrackMuted(track) == 1,
        "track_name": mixer.getTrackName(track),
    }


def handle_mixer_solo_track(params: dict) -> dict:
    """Solo/unsolo mixer track."""
    track = params.get("track", 0)
    solo = params.get("solo")  # None = toggle
    mode = params.get("mode", 3)

    if solo is None:
        mixer.soloTrack(track, -1, mode)
    else:
        mixer.soloTrack(track, 1 if solo else 0, mode)

    return {
        "is_solo": mixer.isTrackSolo(track) == 1,
        "track_name": mixer.getTrackName(track),
    }


def handle_mixer_arm_track(params: dict) -> dict:
    """Toggle arm state of mixer track."""
    track = params.get("track", 0)
    mixer.armTrack(track)
    return {
        "is_armed": mixer.isTrackArmed(track) == 1,
        "track_name": mixer.getTrackName(track),
    }


def handle_mixer_set_track_name(params: dict) -> dict:
    """Set mixer track name."""
    track = params.get("track", 0)
    name = params.get("name", "")
    mixer.setTrackName(track, name)
    return {"name": name}


def handle_mixer_set_track_color(params: dict) -> dict:
    """Set mixer track color."""
    track = params.get("track", 0)
    r = params.get("r", 0)
    g = params.get("g", 0)
    b = params.get("b", 0)
    # FL Studio's scripting API takes 0xRRGGBB
    color = (r << 16) | (g << 8) | b
    mixer.setTrackColor(track, color)
    return {"color": f"RGB({r}, {g}, {b})"}


def handle_mixer_set_stereo_sep(params: dict) -> dict:
    """Set mixer track stereo separation."""
    track = params.get("track", 0)
    separation = params.get("separation", 0.0)
    mixer.setTrackStereoSep(track, separation)
    return {"separation": separation}


# =============================================================================
# Channel Handlers
# =============================================================================


def handle_channels_get_count(params: dict) -> dict:
    """Get number of channels."""
    global_count = params.get("global_count", True)
    return {"count": channels.channelCount(global_count)}


def handle_channels_get_info(params: dict) -> dict:
    """Get info about a channel."""
    index = params.get("index", 0)
    use_global = params.get("use_global", True)

    return {
        "index": index,
        "name": channels.getChannelName(index, use_global),
        "color": hex(channels.getChannelColor(index, use_global)),
        "volume": channels.getChannelVolume(index, False, use_global),  # v10.4e L14: mode arg is 2nd
        "pan": channels.getChannelPan(index, use_global),
        "pitch": channels.getChannelPitch(index, useGlobalIndex=use_global),
        "is_muted": channels.isChannelMuted(index, use_global) == 1,
        "is_solo": channels.isChannelSolo(index, use_global) == 1,
        "is_selected": channels.isChannelSelected(index, use_global) == 1,
        "target_fx_track": channels.getTargetFxTrack(index, use_global),
    }


def handle_channels_get_all() -> dict:
    """Get info about all channels."""
    channels_list = []
    count = channels.channelCount(True)

    for i in range(count):
        channels_list.append({
            "index": i,
            "name": channels.getChannelName(i, True),
            "is_muted": channels.isChannelMuted(i, True) == 1,
            "is_selected": channels.isChannelSelected(i, True) == 1,
            "target_fx_track": channels.getTargetFxTrack(i, True),
        })

    return {"channels": channels_list}


def handle_channels_get_selected() -> dict:
    """Get currently selected channel."""
    index = channels.selectedChannel(canBeNone=True, indexGlobal=True)

    if index is None or index < 0:
        return {"channel": None}

    return {
        "channel": {
            "index": index,
            "name": channels.getChannelName(index, True),
            "volume": channels.getChannelVolume(index, False, True),  # v10.4e L14
            "pan": channels.getChannelPan(index, True),
            "is_muted": channels.isChannelMuted(index, True) == 1,
            "is_solo": channels.isChannelSolo(index, True) == 1,
        }
    }


def handle_channels_select(params: dict) -> dict:
    """Select/deselect a channel."""
    index = params.get("index", 0)
    select = params.get("select", True)
    channels.selectChannel(index, 1 if select else 0, True)
    return {
        "selected": select,
        "channel_name": channels.getChannelName(index, True),
    }


def handle_channels_select_one(params: dict) -> dict:
    """Select only one channel, deselecting others."""
    index = params.get("index", 0)
    channels.selectOneChannel(index, True)
    return {"channel_name": channels.getChannelName(index, True)}


def handle_channels_trigger_note(params: dict) -> dict:
    """Trigger a MIDI note on a channel."""
    channel = params.get("channel", 0)
    note = params.get("note", 60)
    velocity = params.get("velocity", 100)
    midi_channel = params.get("midi_channel", -1)
    channels.midiNoteOn(channel, note, velocity, midi_channel)
    return {"triggered": True, "note": note, "velocity": velocity}


def handle_channels_set_volume(params: dict) -> dict:
    """Set channel volume.

    v10.4e (L14): v45 signature is setChannelVolume(index, volume,
    pickupMode, useGlobalIndex) — the old call passed True as pickupMode;
    PIM_None = 0. Read-back is linear 0-1 (the 2nd getChannelVolume arg is
    the dB mode flag; True returned dB).
    """
    index = int(params.get("index", 0))
    volume = float(params.get("volume", 0.8))
    channels.setChannelVolume(index, volume, 0, True)
    return {
        "volume": channels.getChannelVolume(index, False, True),
        "channel_name": channels.getChannelName(index, True),
    }


def handle_channels_set_pan(params: dict) -> dict:
    """Set channel pan."""
    index = params.get("index", 0)
    pan = params.get("pan", 0.0)
    channels.setChannelPan(index, pan, True)
    return {
        "pan": channels.getChannelPan(index, True),
        "channel_name": channels.getChannelName(index, True),
    }


def handle_channels_mute(params: dict) -> dict:
    """Mute/unmute channel."""
    index = params.get("index", 0)
    muted = params.get("muted")  # None = toggle

    if muted is None:
        channels.muteChannel(index, -1, True)
    else:
        channels.muteChannel(index, 1 if muted else 0, True)

    return {
        "is_muted": channels.isChannelMuted(index, True) == 1,
        "channel_name": channels.getChannelName(index, True),
    }


def handle_channels_solo(params: dict) -> dict:
    """Solo/unsolo channel."""
    index = params.get("index", 0)
    solo = params.get("solo")  # None = toggle

    if solo is None:
        channels.soloChannel(index, -1, True)
    else:
        channels.soloChannel(index, 1 if solo else 0, True)

    return {
        "is_solo": channels.isChannelSolo(index, True) == 1,
        "channel_name": channels.getChannelName(index, True),
    }


def handle_channels_set_name(params: dict) -> dict:
    """Set channel name."""
    index = params.get("index", 0)
    name = params.get("name", "")
    channels.setChannelName(index, name, True)
    return {"name": name}


def handle_channels_set_color(params: dict) -> dict:
    """Set channel color."""
    index = params.get("index", 0)
    r = params.get("r", 0)
    g = params.get("g", 0)
    b = params.get("b", 0)
    # FL Studio's scripting API takes 0xRRGGBB
    color = (r << 16) | (g << 8) | b
    channels.setChannelColor(index, color, True)
    return {"color": f"RGB({r}, {g}, {b})"}


def handle_channels_route_to_mixer(params: dict) -> dict:
    """Route channel to mixer track."""
    channel_index = params.get("channel_index", 0)
    mixer_track = params.get("mixer_track", 0)
    channels.setTargetFxTrack(channel_index, mixer_track, True)
    return {
        "channel_name": channels.getChannelName(channel_index, True),
        "mixer_track": mixer_track,
    }


# =============================================================================
# Step Sequencer Handlers
# =============================================================================


# FL's grid-bit functions act on the *active* pattern: patterns.patternNumber()
# ("the pattern where notes and step sequencing will be modified"). There is no
# separate "current pattern" to set (patterns.setActivePattern does not exist),
# so by default we write to whatever the user has selected and report its number.
# An explicit params["target_pattern"] jumps there for the write and then jumps back.


def _pattern_info() -> dict:
    info = {}
    try:
        n = patterns.patternNumber()
        info["pattern"] = n
        info["pattern_name"] = patterns.getPatternName(n)
    except Exception:
        pass
    return info


class _pattern_scope:
    """Context manager: optionally switch to params['target_pattern'], restore on exit."""

    def __init__(self, target):
        self.target = target
        self.orig = None
        self.error = None

    def __enter__(self):
        if self.target is None:
            return self
        self.orig = patterns.patternNumber()
        if self.target == self.orig:
            self.orig = None
        elif not 1 <= self.target <= patterns.patternCount():
            # jumpToPattern would silently create a new pattern; refuse instead
            self.error = f"Pattern {self.target} does not exist (1-{patterns.patternCount()})"
        else:
            patterns.jumpToPattern(self.target)
        return self

    def __exit__(self, *exc):
        if self.orig is not None and self.error is None:
            patterns.jumpToPattern(self.orig)
        return False


def handle_probe_patterns(params: dict) -> dict:
    """Read-only diagnostics: which pattern is active and which pattern API exists."""
    out = {"api": {n: hasattr(patterns, n) for n in (
        "patternNumber", "patternCount", "jumpToPattern", "getPatternName",
        "setActivePattern", "setPatternGroup", "getActivePatternGroup")}}
    try:
        out["active_pattern"] = patterns.patternNumber()
        out["pattern_count"] = patterns.patternCount()
        out["names"] = [patterns.getPatternName(i) for i in range(1, patterns.patternCount() + 1)]
    except Exception as e:
        out["error"] = str(e)
    return out


def handle_probe_tempo(params: dict) -> dict:
    """Probe the transport module for BPM/tempo accessors."""
    import transport
    out = {}
    for attr in dir(transport):
        if not attr.startswith("_"):
            try:
                val = getattr(transport, attr)
                out[attr] = repr(val) if not callable(val) else f"<{val.__name__}>"
            except Exception as e:
                out[attr] = f"error: {e}"
    # Try common BPM methods
    for name in ("getBPM", "setBPM", "getTempo", "setTempo", "bpm", "tempo"):
        if hasattr(transport, name):
            fn = getattr(transport, name)
            try:
                if name in ("getBPM", "getTempo", "bpm", "tempo"):
                    out[f"CALL_{name}"] = repr(fn())
            except Exception as e:
                out[f"CALL_{name}"] = f"error: {e}"
    return out

def handle_channels_get_grid_bit(params: dict) -> dict:
    """Get whether a step is active (active pattern, or params['target_pattern'])."""
    channel = params.get("channel", 0)
    position = params.get("position", 0)
    with _pattern_scope(params.get("target_pattern")) as sc:
        if sc.error:
            return {"success": False, "error": sc.error}
        return {"value": channels.getGridBit(channel, position, True) == 1, **_pattern_info()}


def handle_channels_set_grid_bit(params: dict) -> dict:
    """Set a step on or off (active pattern, or params['target_pattern'])."""
    channel = params.get("channel", 0)
    position = params.get("position", 0)
    value = params.get("value", False)
    with _pattern_scope(params.get("target_pattern")) as sc:
        if sc.error:
            return {"success": False, "error": sc.error}
        channels.setGridBit(channel, position, 1 if value else 0, True)
        return {
            "value": value,
            "channel_name": channels.getChannelName(channel, True),
            **_pattern_info(),
        }


def handle_channels_get_step_sequence(params: dict) -> dict:
    """Get step sequence for a channel (active pattern, or params['target_pattern'])."""
    channel = params.get("channel", 0)
    steps = params.get("steps", 16)
    with _pattern_scope(params.get("target_pattern")) as sc:
        if sc.error:
            return {"success": False, "error": sc.error}
        sequence = [channels.getGridBit(channel, i, True) == 1 for i in range(steps)]
        return {"sequence": sequence, **_pattern_info()}


# v10.4 (PE era): allowlisted ui/screen call actions. The trial build ABORTED
# FL on any ui.*/screen.* call; Producer Edition does not. These are UI-level
# operations (menus, focus, navigation) — no project data is written, so they
# live outside the undo/identity tiers (same as probes). Unknown names or
# wrong arity surface FL's own exception text (self-teaching, P4-style).
_UI_ALLOWLIST = {
    "enter", "escape", "yes", "no", "up", "down", "left", "right",
    "insert", "delete", "copy", "cut", "paste",
    "jog", "jog2", "strip", "stripJog", "stripHold", "moveJog",
    "previous", "next",
    "selectWindow", "nextWindow", "scrollWindow", "showWindow", "hideWindow",
    "setFocused", "getFocused", "getFocusedFormID", "getFocusedFormCaption",
    "getFocusedNodeCaption", "getFocusedNodeFileType", "getFocusedPluginName",
    "getHintMsg", "getHintValue", "getProgTitle", "getVersion", "isClosing",
    "getVisible", "getSnapMode", "setSnapMode", "snapMode", "snapOnOff",
    "getTimeDispMin", "setTimeDispMin", "getStepEditMode", "setStepEditMode",
    "isLoopRecEnabled", "isMetronomeEnabled", "isPrecountEnabled",
    "isStartOnInputEnabled", "isBrowserAutoHide", "setBrowserAutoHide",
    "isInPopupMenu", "closeActivePopupMenu", "closeAllMenu",
    "navigateBrowser", "navigateBrowserMenu", "navigateBrowserTabs",
    "selectBrowserMenuItem", "previewBrowserMenuItem", "toggleBrowserNode",
    "openEventEditor", "launchAudioEditor", "showPicker", "showNotification",
    "horZoom", "verZoom", "crDisplayRect", "miDisplayRect", "miDisplayDockRect",
}
# v10.4b: the only ui.* functions callable for now — pure getters, no
# engine-state writes. Proven-by-use expansion happens one at a time.
_UI_SAFE_READS = {
    "getProgTitle", "getVersion", "getFocused", "getFocusedFormID",
    "getFocusedFormCaption", "getFocusedNodeCaption",
    "getFocusedNodeFileType", "getFocusedPluginName", "getHintMsg",
    "getHintValue", "getSnapMode", "getStepEditMode", "getTimeDispMin",
    "isBrowserAutoHide", "isClosing", "isInPopupMenu", "getVisible",
}
# v10.4c: second tier — keyboard/navigation events. All 17 getters
# survived 8 live calls with zero engine impact (2026-10-02), so the
# gate widens to the key-event set. These dispatch to the FOCUSED form
# (no focus = no-op), so the first live test is `escape` (zero state
# change even when something IS focused). Browser/window fns
# (navigateBrowser/selectBrowserMenuItem/setFocused/openEventEditor/
# launchAudioEditor/showPicker/zoom/strip*) remain gated for the next
# tier — they open or move windows.
_UI_KEY_EVENTS = {
    "enter", "escape", "up", "down", "left", "right",
    "jog", "jog2", "previous", "next",
}

_SCREEN_ALLOWLIST = {
    "menuItemClick", "menuNext", "menuPrev", "menuShowing", "hideMenu",
    "setup", "init", "deInit", "update",
    "displayText", "displayTimedText", "addTextLine", "findTextLine",
    "removeTextLine", "animateText", "displayBar",
    "drawText", "drawRect", "fillRect", "eraseRect", "addMeter",
    "blank", "unBlank", "isBlanked", "isUnBlank", "keepDisplayActive",
    "getScreenActiveCounter", "setScreenActiveCounter",
}


def _ui_screen_call(module_name: str, name: str, args: list) -> dict:
    if module_name == "ui":
        allow = _UI_ALLOWLIST
    elif module_name == "screen":
        allow = _SCREEN_ALLOWLIST
    else:
        return {"success": False,
                "error": f"unknown module {module_name!r} (ui|screen)"}
    if name not in allow:
        return {"success": False,
                "error": f"{module_name}.{name} not in allowlist",
                "allowed": sorted(allow)}
    if module_name == "ui" and name not in (_UI_SAFE_READS | _UI_KEY_EVENTS):
        # v10.4c: getters (proven) + key events (second tier) are
        # callable; browser/window fns stay gated for the next tier
        return {"success": False,
                "error": (f"ui.{name} not callable in v10.4c; allowed "
                          f"now: {sorted(_UI_SAFE_READS | _UI_KEY_EVENTS)}"),
                "allowed": sorted(_UI_SAFE_READS | _UI_KEY_EVENTS)}
    try:
        mod = __import__(module_name)
    except Exception as e:  # noqa: BLE001
        return {"success": False,
                "error": f"import {module_name}: {type(e).__name__}: {str(e)[:150]}"}
    fn = getattr(mod, name, None)
    if not callable(fn):
        return {"success": False, "error": f"{module_name}.{name} not callable"}
    try:
        result = fn(*args)
        # FL's ui fns return an int status; screen fns usually None/bool
        return {"success": True, "module": module_name, "fn": name,
                "args": args, "result": repr(result)[:200]}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "module": module_name, "fn": name,
                "args": args,
                "error": f"{type(e).__name__}: {str(e)[:300]}",
                "note": "FL's own complaint is the signature answer"}


def handle_ui_call(params: dict) -> dict:
    """v10.4: call one allowlisted ui.* function (see _ui_screen_call)."""
    return _ui_screen_call("ui", str(params.get("name", "")),
                           list(params.get("args", [])))


_UI_KEYSEQ_MAX = 12


def handle_ui_key_seq(params: dict) -> dict:
    """v10.4d: dispatch a bounded SEQUENCE of ui key events in one trip.

    Collapses what used to be N separate MCP round-trips (each a full
    command/response file exchange) into one. Canonical use: the §0
    script selection — wrench click (MCP-side) then
    {"keys": ["up"]*6, "enter"} — 7 calls become 1.

    Every key must already be in _UI_KEY_EVENTS (the proven tier); the
    whole sequence is validated BEFORE any key is dispatched, and the
    loop stops at the first failure (no key is sent after a fault).
    """
    keys = params.get("keys")
    if not isinstance(keys, list) or not keys:
        return {"success": False, "error": "keys must be a non-empty list"}
    if len(keys) > _UI_KEYSEQ_MAX:
        return {"success": False,
                "error": f"sequence too long ({len(keys)} > {_UI_KEYSEQ_MAX})"}
    bad = [k for k in keys if k not in _UI_KEY_EVENTS]
    if bad:
        return {"success": False, "error": f"keys not callable: {bad}",
                "allowed": sorted(_UI_KEY_EVENTS)}
    try:
        mod = __import__("ui")
    except Exception as e:  # noqa: BLE001
        return {"success": False,
                "error": f"import ui: {type(e).__name__}: {str(e)[:150]}"}
    executed: list[str] = []
    results: list[str] = []
    errors: list[str] = []
    for k in keys:
        fn = getattr(mod, k, None)
        if not callable(fn):
            errors.append(f"{k}: not callable")
            break
        try:
            # ui key events take no args (v10.4c live-verified).
            results.append(repr(fn())[:100])
            executed.append(k)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{k}: {type(e).__name__}: {str(e)[:150]}")
            break
    return {"success": not errors, "executed": executed,
            "results": results, "errors": errors}


# v10.4i: third tier — window/picker/browser navigation. `showPicker` is
# present in live v45 but UNDOCUMENTED (absent from il-group's API stubs,
# 2026-10-03): its signature is learned from FL's own TypeError text.
# `selectBrowserMenuItem` stays out (stubs: "appears to open the File menu");
# launchAudioEditor/openEventEditor stay out (open editors, not navigation).
_UI_NAV_TIER = {
    "showPicker", "setFocused", "showWindow", "hideWindow",
    "closeActivePopupMenu", "closeAllMenu",
    "navigateBrowser", "navigateBrowserMenu", "navigateBrowserTabs",
    "toggleBrowserNode", "previewBrowserMenuItem", "yes", "no",
}
# ui.steps may also aim the UI: mixer track selection/focus and pure
# plugin-slot getters (no project data written — selection only).
_STEP_FNS = {
    "ui": _UI_SAFE_READS | _UI_KEY_EVENTS | _UI_NAV_TIER,
    "mixer": {"trackNumber", "setTrackNumber", "selectTrack",
              "setActiveTrack", "isTrackSelected", "focusEditor",
              "getActiveEffectIndex", "getTrackPluginId",
              "isTrackPluginValid", "getTrackName"},
    "plugins": {"isValid", "getPluginName", "getName"},
}
_UI_STEPS_MAX = 16


def handle_ui_steps(params: dict) -> dict:
    """v10.4i: run a bounded list of allowlisted calls in ONE trip.

    steps = [{"fn": "ui.showPicker", "args": [...]}, ...]. The whole list is
    validated before anything is dispatched; the loop stops at the first
    exception (no later step runs). Sequencing logic (waits, oracle checks,
    retries) lives MCP-side (`fl_ui_script`), so new routines need no FL
    restart — only a new FUNCTION on this allowlist does.
    """
    steps = params.get("steps")
    if not isinstance(steps, list) or not steps:
        return {"success": False, "error": "steps must be a non-empty list"}
    if len(steps) > _UI_STEPS_MAX:
        return {"success": False,
                "error": f"too many steps ({len(steps)} > {_UI_STEPS_MAX})"}
    parsed = []
    bad = []
    for s in steps:
        fn = str((s or {}).get("fn", "")) if isinstance(s, dict) else ""
        args = (s or {}).get("args", []) if isinstance(s, dict) else None
        mod_name, _, name = fn.partition(".")
        if (name not in _STEP_FNS.get(mod_name, ())
                or not isinstance(args, list)):
            bad.append(fn or repr(s)[:60])
        else:
            parsed.append((mod_name, name, args))
    if bad:
        return {"success": False, "error": f"steps not callable: {bad}",
                "allowed": {k: sorted(v) for k, v in _STEP_FNS.items()}}
    done: list[dict] = []
    for mod_name, name, args in parsed:
        try:
            fn = getattr(__import__(mod_name), name, None)
        except Exception as e:  # noqa: BLE001
            return {"success": False, "executed": done,
                    "error": f"import {mod_name}: {type(e).__name__}: {str(e)[:150]}"}
        if not callable(fn):
            return {"success": False, "executed": done,
                    "error": f"{mod_name}.{name} not callable"}
        try:
            result = fn(*args)
        except Exception as e:  # noqa: BLE001
            return {"success": False, "executed": done,
                    "failed": f"{mod_name}.{name}", "args": args,
                    "error": f"{type(e).__name__}: {str(e)[:300]}",
                    "note": "FL's own complaint is the signature answer"}
        done.append({"fn": f"{mod_name}.{name}", "args": args,
                     "result": repr(result)[:200]})
    return {"success": True, "executed": done}


def handle_screen_call(params: dict) -> dict:
    """v10.4b: screen.* QUARANTINED. 2026-10-02: the first live call
    (screen.menuShowing(), no args) killed FL — EAccessViolation on a
    side thread in FLEngine_x64.dylib. Until each screen function is
    individually proven safe, none of them are callable. The list is
    still importable (harmless) — the call is refused here."""
    return {"success": False,
            "error": ("screen.* quarantined: menuShowing() crashed FL "
                      "(EAccessViolation, side thread, 2026-10-02). "
                      "No screen calls until per-function testing."),
            "asked_for": str(params.get("name", ""))}


def handle_probe_ilmcp(params: dict) -> dict:
    """v10.3 (Gopher/PE lead): introspect the compiled engine modules —
    `ilmcp` (the one Gopher's MCPTools.pyc calls: run_piano_roll_script,
    add_channel, …), plus `ui`/`screen`/`pianoroll` (licensed-build
    unlockables). STRICTLY introspective: import + dir + __doc__/signature
    reads only. No function of any probed module is ever called here (a bad
    call could abort FL; actual calls get dedicated reviewed actions after
    we see the surface). Command-only by design (never OnInit — v10 crash
    notes)."""
    out = {"modules": {}, "errors": []}
    for mod_name in ("ilmcp", "ui", "screen", "flpianoroll",
                    "flmcp", "gopher", "mcp"):
        # (2026-10-02: ilmcp/pianoroll do NOT exist as modules — the
        #  Gopher pyc string was misleading; flpianoroll/flmcp/gopher/
        #  mcp are the remaining candidates for the real backend)
        entry = {"found": False}
        try:
            mod = __import__(mod_name)
        except Exception as e:  # noqa: BLE001
            entry["errors"] = [f"import {mod_name}: {type(e).__name__}: {str(e)[:150]}"]
            out["modules"][mod_name] = entry
            continue
        entry["found"] = True
        names = {}
        try:
            for n in [n for n in dir(mod) if not n.startswith("_")]:
                try:
                    v = getattr(mod, n)
                except Exception as e:  # noqa: BLE001
                    names[n] = {"type": "ERR", "err": str(e)[:60]}
                    continue
                info = {"type": type(v).__name__}
                doc = getattr(v, "__doc__", None)
                if isinstance(doc, str) and doc.strip():
                    info["doc"] = doc.strip()[:200]
                if callable(v):
                    try:
                        import inspect
                        info["sig"] = str(inspect.signature(v))[:120]
                    except Exception:  # noqa: BLE001
                        pass
                names[n] = info
            entry["names"] = names
        except Exception as e:  # noqa: BLE001
            entry["errors"] = [f"dir/getattr: {str(e)[:150]}"]
        out["modules"][mod_name] = entry
    return out


def handle_channels_set_step_sequence(params: dict) -> dict:
    """Set complete step sequence for a channel (active pattern, or params['target_pattern'])."""
    channel = params.get("channel", 0)
    pattern = params.get("pattern", [])
    with _pattern_scope(params.get("target_pattern")) as sc:
        if sc.error:
            return {"success": False, "error": sc.error}
        for i, value in enumerate(pattern):
            channels.setGridBit(channel, i, 1 if value else 0, True)
        return {
            "active_steps": sum(1 for v in pattern if v),
            "total_steps": len(pattern),
            "channel_name": channels.getChannelName(channel, True),
            **_pattern_info(),
        }


# Official step-parameter constants (image-line manual, midi_scripting.htm
# #stepParams — 2026-10-02; the 'SPT_*' names from the fl-bridge snippet do
# NOT exist in v45's midi module). int values pass through unchanged.
_STEP_PARAM_NAMES = {
    "ppitch": 0, "pvelocity": 1, "prelease": 2, "pfinepitch": 3,
    "ppan": 4, "pmodx": 5, "pmodify": 6, "pshift": 7, "prepeat": 8,
}


def _resolve_step_param(param):
    """Resolve a step-parameter type: int id used directly; str = an official
    name (pVelocity, pPan, … — case-insensitive). Returns (id, error). On an
    unknown name the error lists the official constants (P4 self-teaching).
    Only touches `midi`-safe patterns — v10.3 deliberately does NOT import
    `device` anywhere (device.* calls crash the trial build, 2026-10-02)."""
    if isinstance(param, int):
        return param, None
    name = str(param).strip().lower()
    if name in _STEP_PARAM_NAMES:
        return _STEP_PARAM_NAMES[name], None
    # legacy/unknown name: check the midi module too (harmless), else error
    raw = str(param)
    if hasattr(midi, raw):
        return getattr(midi, raw), None
    return None, (f"unknown step-param {param!r}; official: "
                 + ", ".join(f"{k.capitalize()}={v}" for k, v in
                             sorted(_STEP_PARAM_NAMES.items(), key=lambda x: x[1])))


def handle_channels_get_step_param(params: dict) -> dict:
    """v10.3 (P4): read one step parameter via getCurrentStepParam (official
    signature: (int index, int step, int param[, bool useGlobalIndex]) —
    image-line manual midi_scripting.htm). params: channel, step, param,
    [target_pattern (switches the active pattern first, since the getter
    reads the current pattern)], [use_global, default True — v10.4e (S2.3):
    default flipped False->True so GET and SET share one symmetric flag].
    If the built-in rejects the call the exception text is the P4 answer.
    """
    channel = int(params.get("channel", 0))
    step = int(params.get("step", 0))
    use_global = bool(params.get("use_global", True))
    param, err = _resolve_step_param(params.get("param", "pVelocity"))
    if err:
        return {"success": False, "error": err}
    with _pattern_scope(params.get("target_pattern")) as sc:
        if sc.error:
            return {"success": False, "error": sc.error}
        try:
            val = channels.getCurrentStepParam(channel, step, param, use_global)
        except Exception as e:
            return {"success": False,
                    "error": f"getCurrentStepParam({channel}, {step}, {param}, {use_global}) -> "
                            f"{type(e).__name__}: {str(e)[:200]}",
                    "attempt": {"channel": channel, "step": step, "param": param}}
        return {"success": True, "value": val, "channel": channel,
                "step": step, "param": param, "use_global": use_global,
                **_pattern_info()}


def handle_channels_set_step_param(params: dict) -> dict:
    """v10.2 (P4): set one step parameter via setStepParameterByIndex.

    v10.4e (S2.3): the useGlobalIndex flag is now SYMMETRIC — SET and the
    same-trip read-back GET use the same flag (params: use_global, default
    True). The old GET=False/SET=True asymmetry was the prime suspect for
    shift/pan writes that stuck on some channels but not others. The
    read-back value and a `persisted` flag are returned so the server never
    reports a silent drop (P5: the success message is the read-back).
    """
    channel = int(params.get("channel", 0))
    step = int(params.get("step", 0))
    value = int(params.get("value", 0))
    use_global = bool(params.get("use_global", True))
    param, err = _resolve_step_param(params.get("param", "pVelocity"))
    if err:
        return {"success": False, "error": err}
    with _pattern_scope(params.get("target_pattern")) as sc:
        if sc.error:
            return {"success": False, "error": sc.error}
        pat = patterns.patternNumber()
        try:
            channels.setStepParameterByIndex(channel, pat, step, param, value, use_global)
        except Exception as e:
            return {"success": False,
                    "error": f"setStepParameterByIndex({channel}, {pat}, {step}, {param}, "
                            f"{value}, {use_global}) -> {type(e).__name__}: {str(e)[:200]}",
                    "attempt": {"channel": channel, "pattern": pat, "step": step,
                                "param": param, "value": value, "use_global": use_global}}
        out = {"success": True, "channel": channel, "pattern": pat,
               "step": step, "param": param, "value": value,
               "use_global": use_global, **_pattern_info()}
        # Same-trip read-back with the SAME flag (P5: report, don't assume).
        try:
            rb = channels.getCurrentStepParam(channel, step, param, use_global)
            out["read_back"] = rb
            out["persisted"] = (rb == value)
        except Exception as e:
            out["read_back"] = None
            out["persisted"] = False
            out["read_back_error"] = f"{type(e).__name__}: {str(e)[:160]}"
        return out


# =============================================================================
# Plugin Handlers
# =============================================================================


def handle_plugins_is_valid(params: dict) -> dict:
    """Check if plugin exists at location."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        valid = plugins.isValid(index, slot_index, True)
    else:
        valid = plugins.isValid(index, -1, use_global)

    return {"valid": valid == 1}


def handle_plugins_get_name(params: dict) -> dict:
    """Get plugin name."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        name = plugins.getPluginName(index, slot_index, True)
    else:
        name = plugins.getPluginName(index, -1, use_global)

    return {"name": name}


def handle_plugins_get_param_count(params: dict) -> dict:
    """Get number of plugin parameters."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        count = plugins.getParamCount(index, slot_index, True)
    else:
        count = plugins.getParamCount(index, -1, use_global)

    return {"count": count}


def handle_plugins_get_params(params: dict) -> dict:
    """Get all plugin parameters."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)
    max_params = params.get("max_params", 50)

    if slot_index >= 0:
        param_count = plugins.getParamCount(index, slot_index, True)
    else:
        param_count = plugins.getParamCount(index, -1, use_global)

    param_list = []
    for i in range(min(param_count, max_params)):
        try:
            if slot_index >= 0:
                name = plugins.getParamName(i, index, slot_index, True)
                value = plugins.getParamValue(i, index, slot_index, True)
                value_str = plugins.getParamValueString(i, index, slot_index, True)
            else:
                name = plugins.getParamName(i, index, -1, use_global)
                value = plugins.getParamValue(i, index, -1, use_global)
                value_str = plugins.getParamValueString(i, index, -1, use_global)

            param_list.append({
                "index": i,
                "name": name,
                "value": value,
                "value_string": value_str,
            })
        except Exception as e:
            print(f"Warning: could not read param {i}: {e}")
            continue

    return {"params": param_list}


def handle_plugins_get_param_value(params: dict) -> dict:
    """Get specific parameter value."""
    param_index = params.get("param_index", 0)
    plugin_index = params.get("plugin_index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        name = plugins.getParamName(param_index, plugin_index, slot_index, True)
        value = plugins.getParamValue(param_index, plugin_index, slot_index, True)
        value_str = plugins.getParamValueString(param_index, plugin_index, slot_index, True)
    else:
        name = plugins.getParamName(param_index, plugin_index, -1, use_global)
        value = plugins.getParamValue(param_index, plugin_index, -1, use_global)
        value_str = plugins.getParamValueString(param_index, plugin_index, -1, use_global)

    return {
        "index": param_index,
        "name": name,
        "value": value,
        "value_string": value_str,
    }


def handle_plugins_set_param_value(params: dict) -> dict:
    """Set plugin parameter value."""
    param_index = params.get("param_index", 0)
    value = params.get("value", 0.0)
    plugin_index = params.get("plugin_index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    # setParamValue's 5th argument is pickupMode, NOT useGlobalIndex:
    # setParamValue(value, paramIndex, index, slotIndex, pickupMode, useGlobalIndex).
    # Passing True there enables pickup mode and the value is silently ignored.
    pim_none = midi.PIM_None
    if slot_index >= 0:
        name = plugins.getParamName(param_index, plugin_index, slot_index, True)
        plugins.setParamValue(value, param_index, plugin_index, slot_index, pim_none, True)
        new_value = plugins.getParamValue(param_index, plugin_index, slot_index, True)
        value_str = plugins.getParamValueString(param_index, plugin_index, slot_index, True)
    else:
        name = plugins.getParamName(param_index, plugin_index, -1, use_global)
        plugins.setParamValue(value, param_index, plugin_index, -1, pim_none, use_global)
        new_value = plugins.getParamValue(param_index, plugin_index, -1, use_global)
        value_str = plugins.getParamValueString(param_index, plugin_index, -1, use_global)

    return {
        "name": name,
        "value": new_value,
        "value_string": value_str,
    }


def handle_plugins_get_preset_count(params: dict) -> dict:
    """Get number of plugin presets."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        count = plugins.getPresetCount(index, slot_index, True)
    else:
        count = plugins.getPresetCount(index, -1, use_global)

    return {"count": count}


def handle_plugins_next_preset(params: dict) -> dict:
    """Switch to next preset."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        plugin_name = plugins.getPluginName(index, slot_index, True)
        plugins.nextPreset(index, slot_index, True)
    else:
        plugin_name = plugins.getPluginName(index, -1, use_global)
        plugins.nextPreset(index, -1, use_global)

    return {"plugin_name": plugin_name}


def handle_plugins_prev_preset(params: dict) -> dict:
    """Switch to previous preset."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        plugin_name = plugins.getPluginName(index, slot_index, True)
        plugins.prevPreset(index, slot_index, True)
    else:
        plugin_name = plugins.getPluginName(index, -1, use_global)
        plugins.prevPreset(index, -1, use_global)

    return {"plugin_name": plugin_name}


def handle_plugins_get_color(params: dict) -> dict:
    """Get plugin color."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        color = plugins.getColor(index, slot_index, True)
    else:
        color = plugins.getColor(index, -1, use_global)

    return {"color": hex(color)}

def handle_probe_playlist(params: dict) -> dict:
    """Probe the playlist module for track/pattern management."""
    import playlist
    out = {"api": {}}
    for attr in dir(playlist):
        if not attr.startswith("_"):
            try:
                val = getattr(playlist, attr)
                out["api"][attr] = repr(val) if not callable(val) else f"<{val.__name__}>"
            except Exception as e:
                out["api"][attr] = f"err: {e}"
    # Try key methods
    for name in ("getTrackCount", "getTrackName", "clearTrack", "setStep", "getStep",
                 "addPattern", "removePattern", "getPatternNumber", "setPatternNumber"):
        if hasattr(playlist, name):
            fn = getattr(playlist, name)
            try:
                if name == "getTrackCount":
                    out["track_count"] = fn()
                elif name == "getStep":
                    out["step_track0"] = fn(0, 0)
            except Exception as e:
                out[f"err_{name}"] = str(e)
    return out

# =============================================================================
# API introspection (diagnostic)
# =============================================================================

def probe_api(params: dict) -> dict:
    """Return the available callable methods of a FL Python API module."""
    import importlib
    section = params.get("section", "notes")
    try:
        mod = importlib.import_module(section)
        fns = [x for x in dir(mod) if not x.startswith("_") and callable(getattr(mod, x))]
        return {"success": True, "section": section, "methods": fns}
    except Exception as e:
        return {"success": True, "error": str(e)}


def handle_mixer_get_peaks(params: dict) -> dict:
    """L17 (v10.4g): instantaneous mixer peak meters. Read-only.

    mixer.getTrackPeaks(track, mode): LINEAR amplitude (1.0 = 0 dBFS, >1.0 =
    clipping), a decaying meter; modes midi.PEAK_L=0 / PEAK_R=1 (PEAK_LR=2 is
    max(L,R); PEAK_LR_INV=3 is another scale, not used). getLastPeakVol(0/1)
    is a faster-decaying master L/R value. Live 2026-10-01: one 808 kick read
    0.8993 on the master, decaying 0.71 -> 0.32 -> 0.23 over ~0.2 s; all 0.0
    while silent. track < 0 or absent = every track (0 = master).
    """
    t = params.get("track")
    if t is None or int(t) < 0:
        tracks = range(mixer.trackCount())
    else:
        tracks = [int(t)]
    peaks = [[i, mixer.getTrackPeaks(i, 0), mixer.getTrackPeaks(i, 1)]
             for i in tracks]
    return {"success": True, "peaks": peaks,
            "master_last": [mixer.getLastPeakVol(0), mixer.getLastPeakVol(1)],
            "playing": bool(transport.isPlaying())}


def _eq_call(errors: list, label: str, fn_name: str, *variants):
    """Call mixer.<fn_name> with each argument tuple in turn until one does not
    raise TypeError (v45 signatures are unverified); TypeError texts are
    appended to `errors` — they are the signature oracle. Other exceptions are
    recorded and stop the attempt. Returns (ok, value)."""
    fn = getattr(mixer, fn_name, None)
    if fn is None:
        errors.append(f"{label}: mixer.{fn_name} missing")
        return False, None
    for args in variants:
        try:
            return True, fn(*args)
        except TypeError as e:
            errors.append(f"{label} {fn_name}{args}: TypeError: {e}")
        except Exception as e:
            errors.append(f"{label} {fn_name}{args}: {type(e).__name__}: {e}")
            break
    return False, None


def handle_mixer_get_eq(params: dict) -> dict:
    """v10.4h: a mixer track's built-in parametric EQ. Read-only.

    Per band: gain/freq/bw NORMALIZED (0-1) plus gain_db/freq_hz (mode=1
    getters, the real units). UNVERIFIED signatures: errors carry any
    TypeError text instead of failing the whole read.
    """
    t = int(params.get("track", 0))
    errors: list = []
    ok, n = _eq_call(errors, "count", "getEqBandCount", (t,), ())
    if not ok or n is None:
        return {"error": "mixer.getEqBandCount failed: " + "; ".join(errors)}
    bands = []
    for b in range(int(n)):
        band = {"band": b}
        for key, fn, args in (
            ("gain", "getEqGain", [(t, b, 0), (t, b)]),
            ("gain_db", "getEqGain", [(t, b, 1)]),
            ("freq", "getEqFrequency", [(t, b, 0), (t, b)]),
            ("freq_hz", "getEqFrequency", [(t, b, 1)]),
            ("bw", "getEqBandwidth", [(t, b)]),
        ):
            ok, v = _eq_call(errors, f"band{b}.{key}", fn, *args)
            band[key] = v if ok else None
        bands.append(band)
    out = {"success": True, "track": t, "band_count": int(n), "bands": bands}
    if errors:
        out["errors"] = errors
    return out


def handle_mixer_set_eq(params: dict) -> dict:
    """v10.4h: set one EQ band's gain/freq/bw (NORMALIZED 0-1; only the given
    fields). FL applies the value after the trip returns: read it in the NEXT
    command (no same-trip state_after on purpose). Signatures unverified:
    setEqX(track, band, value) first, then with a trailing pickup arg."""
    t = int(params.get("track", 0))
    b = int(params.get("band", 0))
    errors: list = []
    ok, n = _eq_call(errors, "count", "getEqBandCount", (t,), ())
    if ok and n is not None and not 0 <= b < int(n):
        return {"error": f"band {b} out of range (track {t} has {int(n)} bands)"}
    applied = {}
    for key, fn, raw in (("gain", "setEqGain", params.get("gain")),
                         ("freq", "setEqFrequency", params.get("freq")),
                         ("bw", "setEqBandwidth", params.get("bw"))):
        if raw is None:
            continue
        v = max(0.0, min(1.0, float(raw)))
        variants = [(t, b, v)]
        pim = getattr(midi, "PIM_None", None)
        if pim is not None:
            variants.append((t, b, v, pim))
        ok, _ = _eq_call(errors, f"band{b}.{key}", fn, *variants)
        if not ok:
            return {"error": f"mixer.{fn} failed: " + "; ".join(errors)}
        applied[key] = v
    if not applied:
        return {"error": "mixer.setEq: give at least one of gain/freq/bw"}
    out = {"track": t, "band": b, "applied": applied,
           "note": "applied after the trip; read back in the next command"}
    if errors:
        out["errors"] = errors
    return out


def probe_exec(params: dict) -> dict:
    """Execute arbitrary Python code in FL's environment and return stdout/stderr."""
    import io, sys, contextlib
    code = params.get("code", "")
    out = io.StringIO()
    err = io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            exec(code, {})
        return {"success": True, "stdout": out.getvalue(), "stderr": err.getvalue()}
    except Exception as e:
        return {"success": False, "stdout": out.getvalue(), "stderr": err.getvalue(), "error": str(e)}


# =============================================================================
# Setup / project management
# =============================================================================

def handle_setup(params: dict) -> dict:
    """Consolidate the project into ONE clean pattern so all sounds play together.

    1. Jump to (or create) pattern 1.
    2. Delete every OTHER pattern (they hold duplicate channels / one-off loops).
    3. Re-route each channel to its own mixer track.
    4. Return the resulting channel list so the caller knows the final indices.

    NOTE: deleting a pattern that contains unique notes destroys those notes.
    Call this right after consolidating melody into pattern 1, or on a fresh project.
    """
    import transport
    report = {}

    # 1. Work in pattern 1
    try:
        patterns.jumpToPattern(1)
    except Exception as e:
        return {"success": False, "error": f"cannot jump to pattern 1: {e}"}
    patterns.setPatternName(1, "Pattern 1")  # v45: 2-arg (3-arg crashes FL)

    # 2. Delete all other patterns (high -> low so indices stay valid)
    deleted = []
    for i in range(patterns.patternCount(), 1, -1):
        try:
            patterns.deletePattern(i)
            deleted.append(i)
        except Exception as e:
            report.setdefault("deleted_errors", []).append(f"pattern {i}: {e}")
    report["deleted_patterns"] = deleted

    # 3. Re-route every channel to its own mixer track (track = index+1)
    routed = []
    for c in range(channels.channelCount(True)):
        try:
            channels.setTargetFxTrack(c, c + 1, True)
            routed.append({"index": c, "name": channels.getChannelName(c, True),
                           "mixer": c + 1})
        except Exception as e:
            report.setdefault("route_errors", []).append(f"channel {c}: {e}")
    report["channels"] = routed

    # 4. Reset transport to the start of the (now single) pattern
    try:
        transport.stop()
    except Exception:
        pass

    report["success"] = True
    report["pattern_count"] = patterns.patternCount()
    report["channel_count"] = channels.channelCount(True)
    return report

"""fl_genre — ONE CALL per genre: tempo, swing, pattern, drums, chords, bass, levels.

Packs are data: fl-studio-mcp/presets/genres/<id>.json (16 genres; `list`). Each pack names a beat preset
(presets/beats/), a key and a Roman-numeral progression; utils/chords.py turns
those into notes. Knowledge owners: skills/fl-genres (tempo/key/grid),
skills/music-theory (harmony). Everything is "convention, not auditioned".

Actions
  list                      the packs (id, bpm, key, progression)
  show(genre)               one pack
  load(genre, [dry_run])    the whole setup, every step reported; success = 0 misses
                            1 tempo (real BPM, speed 1.0) + swing   2 pattern length
                            3 drums: the genre KIT (load_kit) + the pack's beat preset on it
                              (kit=false: the beat on whatever drum channels exist)
                            4 Keys + Bass channels (created via the Add menu when missing)
                            5 chords on Keys, bass roots on Bass (piano-roll writes)
                            6 levels: fl_mixer fix_clipping on the master
  load_kit(genre, [variant], [pattern=1], [beat])
                            the genre's drum kit (presets/kits/<genre>.json, built offline by
                            scripts/build_drumkits.py from FL's bundled one-shots; never the
                            default 808 kit): one Sampler per role ("Kick AFRO", "Shaker AFRO"...),
                            created when missing, sample loaded (auto-retry), the genre beat
                            routed onto them + the kit's extra parts (shaker/perc/rim/open hat)
Built 2026-10-06 (owner: "all major genres and chords, as one click setup"); kits 2026-10-11.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

PACKS = Path(__file__).resolve().parents[3] / "presets" / "genres"
ACTIONS = ("list", "show", "load", "load_kit")


def list_packs() -> list[dict]:
    out = []
    for f in sorted(PACKS.glob("*.json")):
        d = json.loads(f.read_text())
        out.append({"id": d["id"], "bpm": d["bpm"], "key": d["key"],
                    "progression": d["chords"]["progression"], "beat": d["beat"]})
    return out


def load_pack(genre: str) -> dict:
    f = PACKS / f"{genre.strip().lower().replace(' ', '-')}.json"
    if not f.is_file():
        raise ValueError(f"no genre pack {genre!r}; have {[p['id'] for p in list_packs()]}")
    return json.loads(f.read_text())


def plan_notes(pack: dict) -> tuple[list[dict], list[dict]]:
    from fl_studio_mcp.utils.chords import bass_notes, chord_notes
    c, b, bars = pack["chords"], pack["bass"], int(pack.get("bars", 4))
    chords = chord_notes(pack["key"], c["progression"], bars, c.get("rhythm", "whole"),
                         c.get("quality", "triad"), int(c.get("octave", 4)),
                         float(c.get("velocity", 0.65)), int(c.get("chords_per_bar", 1)))
    bass = bass_notes(pack["key"], c["progression"], bars, b.get("rhythm", "sustain"),
                      int(b.get("octave", 2)), float(b.get("velocity", 0.85)),
                      int(c.get("chords_per_bar", 1)))
    return chords, bass


def _channel_index(conn, name: str) -> int | None:
    from fl_studio_mcp.tools.mixer_v2 import _exec
    names = json.loads(_exec(conn, "import json, channels\n"
                                   "print(json.dumps([channels.getChannelName(i) "
                                   "for i in range(channels.channelCount())]))"))
    key = name.strip().lower()
    return next((i for i, n in enumerate(names) if str(n).strip().lower() == key), None)


def _loaded_state() -> tuple[Path, dict, str]:
    """{channel name: wav} already loaded in THIS FL process (.generated/drumkits/loaded.json),
    so a re-run only redoes the misses (a Sampler load costs ~50 s)."""
    from fl_studio_mcp.utils.drumkits import GEN_DIR
    from fl_studio_mcp.utils.roll_session import fl_pid
    f = GEN_DIR / "drumkits" / "loaded.json"
    pid = str(fl_pid() or "")
    try:
        d = json.loads(f.read_text())
    except (OSError, ValueError):
        d = {}
    return f, (d.get(pid) or {}), pid


def load_kit(conn, genre: str, variant: int = 0, pattern: int = 1, beat: str | None = "",
             dry_run: bool = False, reload: bool = False) -> dict:
    """The genre's drum kit into named Sampler channels + its beat on them. beat="" = the
    genre pack's beat preset; beat=None = samples only."""
    import time

    from fl_studio_mcp.utils import drumkits as dk
    t0 = time.time()
    gid = genre.strip().lower().replace(" ", "-")
    kit = dk.build_kit(gid, variant) if variant else dk.load_kit_file(gid)
    if beat == "":
        try:
            beat = load_pack(gid)["beat"]
        except ValueError:
            beat = gid
    roles = kit["roles"]
    plan = [f"{e['channel']}: {Path(e['file']).stem} ({e['flavour']}"
            + (f", plays the beat's {e['part']}" if e["part"] else ", own pattern") + ")"
            for e in roles.values()]
    if dry_run:
        return {"action": "load_kit", "success": True, "dry_run": True, "genre": gid,
                "beat": beat, "plan": plan, "status": kit.get("status")}
    from fl_studio_mcp.tools.channel_v2 import fl_channel
    from fl_studio_mcp.tools.preset_v2 import load_beat
    from fl_studio_mcp.utils.sampler_load import load_sample_retry
    from fl_studio_mcp.utils.ui_guard import ensure_ready
    ready = ensure_ready(conn)
    if not ready["ready"]:
        return {"action": "load_kit", "success": False, "error": f"FL not ready: {ready['blockers']}"}
    wavs = dk.materialize(kit)
    own: set = set()
    steps, misses, loaded = [], [], {}
    state_f, done, pid = _loaded_state()

    def step(name, ok, err=None, **extra):
        steps.append({"step": name, "ok": bool(ok), **extra})
        if not ok:
            misses.append({"step": name, "error": err})
        return ok

    for role, e in roles.items():
        name = e["channel"]
        idx = _channel_index(conn, name)
        if idx is None:
            r = fl_channel("add", conn=conn, plugin="Sampler", name=name)
            if not step(f"add {name}", r.get("success"), r.get("error")):
                continue
            idx = (r.get("result") or {}).get("index")
            idx = idx if idx is not None else _channel_index(conn, name)
        if not reload and done.get(name) == wavs[role]:
            step(f"{name} already holds {Path(wavs[role]).name} (this FL session)", True)
            loaded[role] = int(idx)
            continue
        r = load_sample_retry(conn, int(idx), wavs[role], label=name, log=lambda m: None)
        if step(f"load {name} <- {Path(wavs[role]).name}", r.get("ok"), r.get("error"),
                attempts=r.get("attempts")):
            loaded[role] = int(idx)
            done[name] = wavs[role]
            if pid:
                state_f.parent.mkdir(parents=True, exist_ok=True)
                state_f.write_text(json.dumps({pid: done}, indent=1))
    if beat:
        cmap = {e["part"]: e["channel"] for r, e in roles.items() if e["part"] and r in loaded}
        # a beat that has its own row for an extra role (shaker/perc/rim/ohat, e.g. the 4-bar
        # "afrobeats-feel" groove with accents) plays it; the kit's generic pattern is the fallback
        from fl_studio_mcp.tools.preset_v2 import resolve_preset
        bdata, _ = resolve_preset("beats", beat, "")
        own = set((bdata or {}).get("channels", {}))
        for r, e in roles.items():
            if e["part"] is None and r in loaded and r in own:
                cmap[r] = e["channel"]
        try:
            r = load_beat(beat, target_pattern=pattern, fill=True, auto_level=False, channel_map=cmap)
            step(f"beat '{beat}' on the kit", r.get("ok", r.get("success")), r.get("error"),
                 written=r.get("written"), skipped=r.get("skipped"))
        except Exception as ex:
            step(f"beat '{beat}' on the kit", False, str(ex))
        lr = conn.send_command("patterns.getLength", {"index": int(pattern) - 1})
        try:
            total = int(float(lr.get("length_beats") or 0)) * 4 or 16
        except (TypeError, ValueError):
            total = 16
        for role, e in roles.items():
            if e["part"] is None and role in loaded and e.get("pattern") and role not in own:
                pat = [bool(x) for x in e["pattern"]]
                pat = [pat[i % len(pat)] for i in range(max(total, len(pat)))]
                r = fl_channel("set_steps", conn=conn, index=loaded[role], steps=pat, pattern=pattern)
                step(f"{e['channel']} pattern ({sum(pat)} hits)", r.get("success"), r.get("error"))
    return {"action": "load_kit", "success": not misses, "genre": gid, "variant": variant,
            "beat": beat, "channels": {roles[r]["channel"]: i for r, i in loaded.items()},
            "steps": steps, "misses": misses, "status": kit.get("status"),
            "seconds": round(time.time() - t0, 1)}


def load(conn, genre: str, dry_run: bool = False, level: bool = True, kit: bool = True) -> dict:
    import time
    t0 = time.time()
    pack = load_pack(genre)
    chords, bass = plan_notes(pack)
    bars = int(pack.get("bars", 4))
    plan = [f"tempo {pack['bpm']} BPM (speed 1.0), swing {pack.get('swing', 0)}",
            f"pattern 1 = {bars * 4} beats",
            f"drums: beat preset '{pack['beat']}'" + (" on the genre kit (presets/kits)" if kit else ""),
            f"channels: {pack['chords']['channel']} + {pack['bass']['channel']} "
            f"({pack['chords'].get('plugin', 'FLEX')}, created if missing)",
            f"chords: {pack['key']} {pack['chords']['progression']} -> {len(chords)} notes",
            f"bass: {pack['bass'].get('rhythm')} roots -> {len(bass)} notes",
            "levels: fix_clipping on the master" if level else "levels: skipped"]
    if dry_run:
        return {"action": "load", "success": True, "dry_run": True, "genre": pack["id"],
                "plan": plan}
    from fl_studio_mcp.tools.channel_v2 import fl_channel
    from fl_studio_mcp.tools.mixer_v2 import fl_mixer
    from fl_studio_mcp.tools.notes_v2 import fl_notes
    from fl_studio_mcp.tools.pattern_v2 import fl_pattern
    from fl_studio_mcp.tools.preset_v2 import load_beat
    from fl_studio_mcp.tools.transport_v2 import fl_transport
    from fl_studio_mcp.utils.ui_guard import ensure_ready
    steps: list[dict] = []
    misses: list[dict] = []

    def step(name: str, r: dict | None, ok: bool | None = None):
        ok = bool(r.get("success", r.get("ok"))) if ok is None else ok
        steps.append({"step": name, "ok": ok})
        if not ok:
            misses.append({"step": name, "error": (r or {}).get("error")})
        return ok

    ready = ensure_ready(conn)
    if not ready["ready"]:
        return {"action": "load", "success": False, "error": f"FL not ready: {ready['blockers']}"}
    step("tempo", fl_transport("set_bpm", conn=conn, bpm=float(pack["bpm"])))
    step("speed 1.0", fl_transport("set_speed", conn=conn, speed=1.0))
    step("swing", fl_transport("set_swing", conn=conn, swing=float(pack.get("swing", 0.0))))
    step("pattern length", fl_pattern("set_len", conn=conn, pattern=1, beats=bars * 4))
    from fl_studio_mcp.utils.drumkits import KITS_DIR
    if kit and (KITS_DIR / f"{pack['id']}.json").is_file():
        r = load_kit(conn, pack["id"], pattern=1, beat=pack["beat"])
        step("drums: genre kit + beat", r)
        if r.get("misses"):
            misses[-1]["kit_misses"] = r["misses"]
    else:
        try:
            step("drums", load_beat(pack["beat"], target_pattern=1, fill=True, auto_level=False))
        except Exception as e:
            step("drums", {"success": False, "error": str(e)})
    for role, notes in (("chords", chords), ("bass", bass)):
        spec = pack[role]
        idx = _channel_index(conn, spec["channel"])
        if idx is None:
            r = fl_channel("add", conn=conn, plugin=spec.get("plugin", "FLEX"), name=spec["channel"])
            if not step(f"add channel {spec['channel']}", r):
                continue
            idx = r.get("index", (r.get("result") or {}).get("index"))
            if idx is None:
                idx = _channel_index(conn, spec["channel"])
        r = fl_notes("write_steps", conn=conn, notes=notes, mode="replace",
                     channel_index=int(idx), target_pattern=1)
        step(f"{role} -> {spec['channel']} ({len(notes)} notes)", r)
    if level:
        step("levels (fix_clipping)", fl_mixer("fix_clipping", conn=conn))
    return {"action": "load", "success": not misses, "genre": pack["id"], "key": pack["key"],
            "bpm": pack["bpm"], "steps": steps, "misses": misses,
            "seconds": round(time.time() - t0, 1)}


def fl_genre(action: str, conn=None, **p: Any) -> dict:
    if action not in ACTIONS:
        return {"success": False, "error": f"unknown action {action!r}", "valid_actions": list(ACTIONS)}
    try:
        if action == "list":
            return {"action": action, "success": True, "packs": list_packs()}
        if not p.get("genre"):
            return {"success": False, "error": f"{action}: genre required"}
        if action == "show":
            return {"action": action, "success": True, "pack": load_pack(p["genre"])}
        if conn is None and not p.get("dry_run"):
            from fl_studio_mcp.utils.connection import get_connection
            conn = get_connection()
        if action == "load_kit":
            return load_kit(conn, p["genre"], int(p.get("variant") or 0), int(p.get("pattern") or 1),
                            p.get("beat", ""), bool(p.get("dry_run")), bool(p.get("reload")))
        return load(conn, p["genre"], bool(p.get("dry_run")), p.get("level", True) is not False,
                    p.get("kit", True) is not False)
    except Exception as e:
        return {"action": action, "success": False, "error": str(e)}


def register_genre_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def fl_genre(action: str, genre: str | None = None, dry_run: bool | None = None,
                 level: bool | None = None, kit: bool | None = None, variant: int | None = None,
                 pattern: int | None = None, beat: str | None = None,
                 reload: bool | None = None) -> dict:
        """ONE CALL per genre: list | show(genre) | load(genre, [dry_run], [level], [kit]) |
        load_kit(genre, [variant], [pattern], [beat], [dry_run]).

        load_kit = the genre's own drum kit (never the default 808 kit): one Sampler per role
        ("Kick AFRO", "Snare AFRO", "Shaker AFRO"...) with a sample picked offline from FL's
        bundled one-shots (presets/kits/<genre>.json; scripts/build_drumkits.py), auto-retried
        loads, then the genre beat on those channels + shaker/perc/rim parts. variant=N = the
        next-best samples. Needs FL in front, hands off (~10 s per sample). load uses the kit
        too (kit=false to skip). Samples already loaded in this FL session are skipped, so a
        re-run only redoes the misses (reload=true forces every load).

        load = real tempo + swing + pattern length + the genre's drum beat + Keys/Bass
        channels (created when missing) + a chord progression in the pack's key on Keys
        + the bass roots on Bass + master levels. 16 genres: trap, drill, hip-hop,
        boom-bap, lofi, rnb, pop, afrobeats, phonk, punjabi, house, techno, future-bass,
        drum-and-bass, dubstep, reggaeton (presets/genres/*.json — edit a pack to change
        key/progression/rhythm; `list` shows them). Convention, not auditioned.
        """
        args = {k: v for k, v in {"genre": genre, "dry_run": dry_run, "level": level, "kit": kit,
                                  "variant": variant, "pattern": pattern, "beat": beat,
                                  "reload": reload}.items()
                if v is not None}
        from fl_studio_mcp.tools.genre_v2 import fl_genre as _impl
        return _impl(action, **args)

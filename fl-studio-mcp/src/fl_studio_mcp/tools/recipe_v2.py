"""fl_recipe: a beat as a numbered, replayable, undoable list of steps.

A RECIPE (fl-studio-mcp/recipes/<name>.json, schema in recipes/README.md) is
plain JSON: channels (by role/name), patterns, and numbered steps. This tool
validates it, plans it against the part ledger, applies it to FL one step at
a time (each step reuses the existing domain-tool code in-process, ONE FL call
at a time, hard rule 3), journals what every step replaced, and undoes a step
from that journal.

Actions: validate | plan | apply | status | undo | export

Nothing here talks to the controller directly: every FL write goes through
fl_transport / fl_pattern / fl_channel / fl_notes / fl_plugin / fl_mixer
(`Tools` below), so their safety layers, the S1 roll-title proof (rule 6b) and
the part ledger all stay in force. Every collaborator is injectable (`tools=`)
so the whole flow is unit-testable offline with no FL.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

ACTIONS = ("validate", "plan", "apply", "status", "undo", "export")
DO_VALUES = ("transport", "pattern", "steps", "notes", "fx", "eq", "mix")
FX_EFFECTS = ("echo", "reverb", "chorus")

RECIPES_DIR = Path(__file__).resolve().parents[3] / "recipes"
TOL = 0.02


def journal_dir() -> Path:
    env = os.environ.get("RECIPE_JOURNAL_DIR")
    return Path(env) if env else Path(__file__).resolve().parents[3] / ".generated" / "recipes"


# ---------------------------------------------------------------------------
# Loading / path helpers
# ---------------------------------------------------------------------------

def resolve_path(path: str) -> Path:
    p = Path(path).expanduser()
    if p.exists():
        return p
    for cand in (RECIPES_DIR / path, RECIPES_DIR / f"{path}.json"):
        if cand.exists():
            return cand
    return p


def load_recipe(path: str) -> tuple[dict | None, str | None]:
    p = resolve_path(path)
    try:
        data = json.loads(p.read_text())
    except FileNotFoundError:
        return None, f"recipe file not found: {path}"
    except (OSError, json.JSONDecodeError) as e:
        return None, f"cannot read recipe {path}: {e}"
    if not isinstance(data, dict):
        return None, "recipe must be a JSON object"
    return data, None


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# ---------------------------------------------------------------------------
# Notes / rows (pure)
# ---------------------------------------------------------------------------

def step_notes(step: dict) -> list[dict]:
    """The step's notes as normalized dicts (notes list or S7 melody grid).
    Raises ValueError on a bad spec."""
    if step.get("notes") is not None and step.get("melody") is not None:
        raise ValueError("give 'notes' OR 'melody', not both")
    if step.get("melody") is not None:
        from fl_studio_mcp.tools.notes_v2 import _melody_to_params
        p = {k: step[k] for k in ("melody", "step_beats", "note_beats", "velocity")
             if k in step}
        err = _melody_to_params(p)
        if err:
            raise ValueError(err)
        notes = p["notes"]
    else:
        notes = step.get("notes")
    if not isinstance(notes, list) or not notes:
        raise ValueError("'notes' (or 'melody') must be a non-empty list")
    out = []
    for i, n in enumerate(notes):
        if not isinstance(n, dict) or not _is_num(n.get("midi")) or not _is_num(n.get("duration")):
            raise ValueError(f"notes[{i}]: needs numeric 'midi' and 'duration'")
        if not 0 <= n["midi"] <= 127:
            raise ValueError(f"notes[{i}]: midi {n['midi']} outside 0-127")
        if n["duration"] <= 0:
            raise ValueError(f"notes[{i}]: duration must be > 0")
        c = dict(n)
        c.setdefault("time", 0)
        c.setdefault("velocity", 0.8)
        out.append(c)
    return out


def _nkey(n: dict) -> tuple:
    return (int(n["midi"]), round(float(n.get("time", 0)), 4),
            round(float(n["duration"]), 4), round(float(n.get("velocity", 0.8)), 3),
            bool(n.get("slide", False)))


def notes_equal(a: list[dict] | None, b: list[dict] | None) -> bool:
    return sorted(_nkey(n) for n in a or []) == sorted(_nkey(n) for n in b or [])


def row_to_bars(row: list[bool]) -> list[list[int]]:
    """bool row -> the S7 `bars` form (1-based steps, 16 per bar)."""
    row = list(row)
    if len(row) % 16:
        row += [False] * (16 - len(row) % 16)
    return [[i + 1 for i in range(16) if row[b * 16 + i]] for b in range(len(row) // 16)]


def pattern_beats(recipe: dict, pattern: int) -> int:
    for p in recipe.get("patterns") or []:
        if isinstance(p, dict) and p.get("pattern") == pattern and _is_int(p.get("beats")):
            return int(p["beats"])
    for s in recipe.get("steps") or []:
        if s.get("do") == "pattern" and s.get("pattern") == pattern and _is_int(s.get("beats")):
            return int(s["beats"])
    return 16


def step_row(recipe: dict, step: dict, role: str) -> list[bool]:
    from fl_studio_mcp.tools.channel_v2 import _bars_to_row
    n_bars = max(1, pattern_beats(recipe, int(step["pattern"])) // 4)
    return _bars_to_row(step["rows"][role], n_bars)


def _sig(step: dict) -> str:
    body = {k: v for k, v in step.items() if k not in ("id", "title", "gate", "note")}
    return hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()[:12]


def gate_end(steps: list[dict], i: int) -> str | None:
    g = steps[i].get("gate")
    if not g:
        return None
    if i + 1 >= len(steps) or steps[i + 1].get("gate") != g:
        return g
    return None


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def validate_recipe(recipe: dict, channels: list[dict] | None = None) -> dict:
    """Schema + role checks. `channels` (channels.getAll list) enables the
    "every role resolves to exactly one channel" check."""
    from fl_studio_mcp.tools.channel_v2 import _bars_to_row
    from fl_studio_mcp.tools.plugin_v2 import _FX_FIELDS

    errs: list[str] = []
    warns: list[str] = []
    if not isinstance(recipe.get("name"), str) or not recipe["name"].strip():
        errs.append("name: non-empty string required")
    elif not re.fullmatch(r"[A-Za-z0-9._-]+", recipe["name"]):
        errs.append("name: only letters, digits, . _ - (it names the journal folder)")
    if recipe.get("version") != 1:
        errs.append(f"version: must be 1 (got {recipe.get('version')!r})")

    roles: dict[str, dict] = {}
    chs = recipe.get("channels")
    if not isinstance(chs, list) or not chs:
        errs.append("channels: non-empty list required")
        chs = []
    for i, c in enumerate(chs):
        if not isinstance(c, dict):
            errs.append(f"channels[{i}]: must be an object")
            continue
        r, nm = c.get("role"), c.get("name")
        if not isinstance(r, str) or not r.strip():
            errs.append(f"channels[{i}].role: non-empty string required")
        elif r in roles:
            errs.append(f"channels[{i}].role: duplicate role {r!r}")
        else:
            roles[r] = c
        if not isinstance(nm, str) or not nm.strip():
            errs.append(f"channels[{i}].name: non-empty string required")

    pats = recipe.get("patterns", [])
    if not isinstance(pats, list):
        errs.append("patterns: must be a list")
        pats = []
    for i, p in enumerate(pats):
        if not isinstance(p, dict) or not _is_int(p.get("pattern")) or p["pattern"] < 1:
            errs.append(f"patterns[{i}].pattern: int >= 1 required")
        elif "beats" in p and (not _is_int(p["beats"]) or p["beats"] < 1):
            errs.append(f"patterns[{i}].beats: int >= 1 required")

    steps = recipe.get("steps")
    if not isinstance(steps, list) or not steps:
        errs.append("steps: non-empty list required")
        steps = []
    seen: set[str] = set()
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            errs.append(f"steps[{i}]: must be an object")
            continue
        sid = s.get("id")
        tag = f"step {sid!r}" if isinstance(sid, str) else f"steps[{i}]"
        if not isinstance(sid, str) or not sid.strip():
            errs.append(f"steps[{i}].id: non-empty string required")
        elif sid in seen:
            errs.append(f"{tag}: duplicate id")
        else:
            seen.add(sid)
        do = s.get("do")
        if do not in DO_VALUES:
            errs.append(f"{tag}.do: unknown value {do!r}; valid: {', '.join(DO_VALUES)}")
            continue
        if "gate" in s and (not isinstance(s["gate"], str) or not s["gate"].strip()):
            errs.append(f"{tag}.gate: non-empty string")

        def need_role(key="role"):
            r = s.get(key)
            if r not in roles:
                errs.append(f"{tag}.{key}: unknown role {r!r} (channels: {sorted(roles)})")
                return False
            return True

        def need_pattern():
            if not _is_int(s.get("pattern")) or s["pattern"] < 1:
                errs.append(f"{tag}.pattern: int >= 1 required")
                return False
            return True

        if do == "transport":
            if not any(k in s for k in ("bpm", "speed")):
                errs.append(f"{tag}: give bpm and/or speed")
            if "bpm" in s and not (_is_num(s["bpm"]) and 20 <= s["bpm"] <= 300):
                errs.append(f"{tag}.bpm: 20-300")
            if "speed" in s and not (_is_num(s["speed"]) and 0.25 <= s["speed"] <= 4):
                errs.append(f"{tag}.speed: 0.25-4")
        elif do == "pattern":
            need_pattern()
            if "name" not in s and "beats" not in s:
                errs.append(f"{tag}: give name and/or beats")
            if "beats" in s and (not _is_int(s["beats"]) or s["beats"] < 1):
                errs.append(f"{tag}.beats: int >= 1")
        elif do == "steps":
            need_pattern()
            rows = s.get("rows")
            if not isinstance(rows, dict) or not rows:
                errs.append(f"{tag}.rows: non-empty object role -> bars required")
            else:
                for r, bars in rows.items():
                    if r not in roles:
                        errs.append(f"{tag}.rows: unknown role {r!r}")
                        continue
                    try:
                        _bars_to_row(bars, max(1, pattern_beats(recipe, s.get("pattern", 1)) // 4)
                                     if _is_int(s.get("pattern")) else None)
                    except Exception as e:  # noqa: BLE001
                        errs.append(f"{tag}.rows[{r}]: {e}")
        elif do == "notes":
            need_pattern()
            need_role()
            try:
                step_notes(s)
            except ValueError as e:
                errs.append(f"{tag}: {e}")
        elif do == "fx":
            need_role()
            eff = s.get("effect")
            if eff not in FX_EFFECTS:
                errs.append(f"{tag}.effect: one of {', '.join(FX_EFFECTS)}")
            else:
                allowed = _FX_FIELDS[eff]
                given = [k for k in s if k in allowed]
                if not given:
                    errs.append(f"{tag}: give at least one of {sorted(allowed)}")
                for k in given:
                    v = s[k]
                    if k == "on":
                        if not (isinstance(v, bool) or v in (0, 1)):
                            errs.append(f"{tag}.on: true/false")
                    elif not (_is_num(v) and 0 <= v <= 1):
                        errs.append(f"{tag}.{k}: 0-1 normalized")
        elif do == "eq":
            need_role()
            if not _is_int(s.get("band")) or s["band"] < 0:
                errs.append(f"{tag}.band: int >= 0 required")
            given = [k for k in ("gain", "freq", "bw") if k in s]
            if not given:
                errs.append(f"{tag}: give at least one of gain/freq/bw")
            for k in given:
                if not (_is_num(s[k]) and 0 <= s[k] <= 1):
                    errs.append(f"{tag}.{k}: 0-1 normalized")
        elif do == "mix":
            need_role()
            if "volume" not in s and "pan" not in s:
                errs.append(f"{tag}: give volume and/or pan")
            if "volume" in s and not (_is_num(s["volume"]) and 0 <= s["volume"] <= 1):
                errs.append(f"{tag}.volume: 0-1")
            if "pan" in s and not (_is_num(s["pan"]) and -1 <= s["pan"] <= 1):
                errs.append(f"{tag}.pan: -1..1")

    if channels is not None:
        try:
            resolve_roles(recipe, channels)
        except ValueError as e:
            errs.append(str(e))
    else:
        warns.append("roles not checked against FL (no channel list)")
    return {"errors": errs, "warnings": warns}


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

def _ci(c: dict) -> int | None:
    v = c.get("index", c.get("number"))
    return None if v is None else int(v)


def resolve_roles(recipe: dict, channels: list[dict]) -> dict[str, dict]:
    """role -> {index, name, mixer_track}, matched by channel NAME (indexes
    move). Raises ValueError listing every unresolved/ambiguous role."""
    out: dict[str, dict] = {}
    problems: list[str] = []
    for c in recipe.get("channels") or []:
        role, name = c.get("role"), str(c.get("name", "")).strip().lower()
        hits = [x for x in channels if str(x.get("name", "")).strip().lower() == name]
        if not hits:
            problems.append(f"role {role!r}: no channel named {c.get('name')!r}")
        elif len(hits) > 1:
            problems.append(f"role {role!r}: {len(hits)} channels named {c.get('name')!r} "
                            f"(indexes {[_ci(h) for h in hits]}) - rename one")
        else:
            h = hits[0]
            out[role] = {"index": _ci(h), "name": h.get("name"),
                         "mixer_track": h.get("target_fx_track", h.get("mixer_track"))}
    if problems:
        raise ValueError("; ".join(problems))
    return out


# ---------------------------------------------------------------------------
# Tools (the in-process collaborators; tests replace this)
# ---------------------------------------------------------------------------

class Tools:
    """Thin adapter over the existing domain tools + the read-only probes the
    snapshots/verification need. Every method is ONE FL call (or one tool)."""

    def __init__(self, conn=None):
        self._conn = conn

    @property
    def conn(self):
        if self._conn is None:
            from fl_studio_mcp.utils.connection import get_connection
            self._conn = get_connection()
        return self._conn

    # --- writes: the existing tools, unchanged
    def transport(self, action, **p):
        from fl_studio_mcp.tools.transport_v2 import fl_transport
        return fl_transport(action, conn=self.conn, **p)

    def pattern(self, action, **p):
        from fl_studio_mcp.tools.pattern_v2 import fl_pattern
        return fl_pattern(action, conn=self.conn, **p)

    def channel(self, action, **p):
        from fl_studio_mcp.tools.channel_v2 import fl_channel
        return fl_channel(action, conn=self.conn, **p)

    def notes(self, action, **p):
        from fl_studio_mcp.tools.notes_v2 import fl_notes
        return fl_notes(action, conn=self.conn, **p)

    def plugin(self, action, **p):
        from fl_studio_mcp.tools.plugin_v2 import fl_plugin
        return fl_plugin(action, conn=self.conn, **p)

    def mixer(self, action, **p):
        from fl_studio_mcp.tools.mixer_v2 import fl_mixer
        return fl_mixer(action, conn=self.conn, **p)

    # --- reads
    def channels(self) -> list[dict]:
        r = self.conn.send_command("channels.getAll")
        if not isinstance(r, dict) or r.get("error") or "channels" not in r:
            raise RuntimeError((r or {}).get("error") if isinstance(r, dict) else r
                               or "channels.getAll returned no channel list")
        return r["channels"]

    def read_bpm(self) -> float | None:
        return self.conn.send_command("transport.getBPM").get("bpm")

    def pattern_count(self) -> int:
        return int(self.conn.send_command("probe.patterns").get("pattern_count") or 0)

    def read_pattern_beats(self, pattern: int) -> int | None:
        r = self.conn.send_command("patterns.getLength", {"index": pattern - 1})
        return None if r.get("length_beats") is None else int(r["length_beats"])

    def read_steps(self, channel: int, pattern: int, n: int) -> list[bool] | None:
        r = self.conn.send_command("channels.getStepSequence",
                                   {"channel": channel, "steps": n,
                                    "target_pattern": pattern})
        seq = r.get("sequence")
        return None if seq is None else [bool(x) for x in seq]

    def select_pattern(self, pattern: int) -> dict:
        return self.conn.send_command("patterns.select", {"pattern": pattern})

    def read_fx(self, channel: int, slot: int, effect: str, fields: list[str]) -> dict:
        """{field: raw value} for the effect knobs (raises ValueError if a knob
        cannot be resolved - the step then fails BEFORE any write)."""
        from fl_studio_mcp.tools.plugin_v2 import _FX_FIELDS, _list_params, _resolve_fx_field
        plist = _list_params(self.conn, channel, slot)
        out = {}
        for k in fields:
            par = _resolve_fx_field(plist, *_FX_FIELDS[effect][k], f"{effect}.{k}")
            out[k] = par.get("value")
        return out

    def read_eq(self, track: int, band: int) -> dict:
        from fl_studio_mcp.tools.mixer_v2 import _band, _read_eq
        return dict(_band(_read_eq(self.conn, track), band))

    def read_mix(self, track: int) -> dict:
        r = self.mixer("get_info", track=track)
        r = r.get("result", r) if isinstance(r, dict) else {}
        return {"volume": r.get("volume"), "pan": r.get("pan")}

    # --- roll write verification (the chain/import_midi oracle)
    def roll_mark(self):
        from fl_studio_mcp.utils import roll_session as rs
        return rs.state_mtime()

    def roll_check(self, mark, expected: int) -> dict:
        from fl_studio_mcp.tools.state import _read_piano_roll
        from fl_studio_mcp.utils import roll_session as rs
        pr = _read_piano_roll(600)
        return {"fresh": bool(rs.ran_since(mark)), "note_count": pr.get("note_count"),
                "expected": expected}


# ---------------------------------------------------------------------------
# Journal (append-only)
# ---------------------------------------------------------------------------

def journal_path(recipe_name: str, pid: int | None) -> Path:
    return journal_dir() / recipe_name / f"{pid if pid is not None else 'nopid'}.journal.json"


def load_journal(recipe_name: str, pid: int | None) -> dict:
    p = journal_path(recipe_name, pid)
    try:
        data = json.loads(p.read_text())
        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {"recipe": recipe_name, "fl_pid": pid, "entries": []}


def append_entry(recipe_name: str, pid: int | None, entry: dict) -> dict:
    data = load_journal(recipe_name, pid)
    entry = dict(entry, seq=len(data["entries"]) + 1, at=time.time())
    data["entries"].append(entry)
    p = journal_path(recipe_name, pid)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(p)
    return entry


def live_entries(data: dict) -> list[dict]:
    """Application entries that wrote to FL and have not been undone."""
    undone = {e.get("undoes") for e in data["entries"] if e.get("undo")}
    return [e for e in data["entries"]
            if not e.get("undo") and e.get("wrote") and e["seq"] not in undone]


def last_live(data: dict, step_id: str) -> dict | None:
    hits = [e for e in live_entries(data) if e["step"] == step_id]
    return hits[-1] if hits else None


# ---------------------------------------------------------------------------
# Step snapshots, plan compare, apply, undo
# ---------------------------------------------------------------------------

class StepFail(Exception):
    """A step failed; `.partial` carries what is known (before/after/wrote/...)."""

    def __init__(self, msg: str, **partial: Any):
        super().__init__(msg)
        self.partial = partial


def _ok(r: Any) -> bool:
    return isinstance(r, dict) and bool(r.get("success"))


def _err(r: Any) -> str:
    return str((r or {}).get("error") or r)


def _close(a, b) -> bool:
    try:
        return abs(float(a) - float(b)) <= TOL
    except (TypeError, ValueError):
        return False


def _slot(step: dict) -> int:
    return int(step.get("slot_index", -1))


def _fx_fields(step: dict) -> dict:
    from fl_studio_mcp.tools.plugin_v2 import _FX_FIELDS
    return {k: step[k] for k in _FX_FIELDS[step["effect"]] if k in step}


def _mixer_track(roles: dict, role: str) -> int:
    t = roles[role].get("mixer_track")
    if not _is_int(t) or t <= 0:
        raise StepFail(f"role {role!r} ({roles[role]['name']}) is not routed to its own "
                       f"mixer track (target_fx_track={t!r}); route it first")
    return int(t)


def touches(step: dict, roles: dict) -> list[str]:
    do = step["do"]
    if do == "transport":
        return ["transport"]
    if do == "pattern":
        return [f"pattern:{step['pattern']}"]
    if do == "steps":
        return [f"steps:{roles[r]['index']}:{step['pattern']}" for r in step["rows"]]
    if do == "notes":
        return [f"notes:{roles[step['role']]['index']}:{step['pattern']}"]
    if do == "fx":
        return [f"fx:{roles[step['role']]['index']}:{step['effect']}"]
    if do == "eq":
        return [f"eq:{roles[step['role']]['mixer_track']}:{step['band']}"]
    return [f"mix:{roles[step['role']]['mixer_track']}"]


def plan_step(env: "Env", recipe: dict, step: dict, roles: dict, journal: dict) -> dict:
    """new / same / changed vs the ledger (steps, notes) or the journal."""
    from fl_studio_mcp.utils import ledger as L
    do = step["do"]
    row = {"id": step["id"], "title": step.get("title"), "do": do, "gate": step.get("gate")}
    if do == "steps":
        parts = {}
        for r in step["rows"]:
            want = step_row(recipe, step, r)
            part = L.get_part(env.pid, int(step["pattern"]), roles[r]["index"])
            if not part or part.get("kind") not in (L.KIND_STEPS, L.KIND_BATCH):
                parts[r] = "new"
            else:
                have = [bool(x) for x in part.get("steps", [])]
                parts[r] = "same" if have == want else "changed"
        vals = set(parts.values())
        row["status"] = "same" if vals == {"same"} else ("new" if vals == {"new"} else "changed")
        row["detail"] = parts
        return row
    if do == "notes":
        want = step_notes(step)
        part = L.get_part(env.pid, int(step["pattern"]), roles[step["role"]]["index"])
        if not part or part.get("kind") != L.KIND_NOTES:
            row["status"], row["detail"] = "new", f"{len(want)} notes"
        elif notes_equal(part.get("notes"), want):
            row["status"], row["detail"] = "same", f"{len(want)} notes"
        else:
            row["status"] = "changed"
            row["detail"] = f"{len(part.get('notes', []))} notes in FL -> {len(want)}"
        return row
    last = last_live(journal, step["id"])
    if last is None:
        row["status"], row["detail"] = "new", "no applied journal entry (ledger cannot see this kind)"
    elif last.get("sig") == _sig(step):
        row["status"], row["detail"] = "same", "same parameters as the last application (journal)"
    else:
        row["status"], row["detail"] = "changed", "parameters differ from the last application (journal)"
    return row


def _run_step(env: "Env", recipe: dict, step: dict, roles: dict) -> dict:
    """Execute ONE step. Returns {before, after, verification, verified, wrote}.
    Raises StepFail (with .partial dict if something was already written)."""
    from fl_studio_mcp.utils import ledger as L
    t = env.tools
    do = step["do"]

    if do == "transport":
        before = {"bpm": t.read_bpm(), "speed": None}
        wrote = False
        ver: dict = {}
        if "bpm" in step:
            r = t.transport("set_bpm", bpm=float(step["bpm"]))
            wrote = True
            if not _ok(r):
                raise StepFail(f"set_bpm: {_err(r)}", before=before, wrote=wrote)
            got = t.read_bpm()
            ver["bpm"] = got
            if not _close(got, step["bpm"]):
                raise StepFail(f"bpm read-back {got} != {step['bpm']}", before=before,
                               wrote=wrote, verification=ver)
        if "speed" in step:
            r = t.transport("set_speed", speed=float(step["speed"]))
            wrote = True
            if not _ok(r):
                raise StepFail(f"set_speed: {_err(r)}", before=before, wrote=wrote,
                               verification=ver)
            ver["speed"] = "set (no getter)"
        return {"before": before, "after": {k: step[k] for k in ("bpm", "speed") if k in step},
                "verification": ver, "verified": True, "wrote": wrote}

    if do == "pattern":
        p = int(step["pattern"])
        count = t.pattern_count()
        exists = p <= count
        before = {"exists": exists, "beats": t.read_pattern_beats(p) if exists else None}
        wrote = False
        if not exists:
            if p != count + 1:
                raise StepFail(f"pattern {p} does not exist and is not the next free slot "
                               f"({count + 1}); create the earlier ones first", before=before)
            args = {"name": step.get("name") or f"Pattern {p}"}
            if "beats" in step:
                args["length_beats"] = int(step["beats"])
            r = t.pattern("create", **args)
            wrote = True
            if not _ok(r):
                raise StepFail(f"create: {_err(r)}", before=before, wrote=wrote)
        else:
            if "name" in step:
                r = t.pattern("rename", pattern=p, name=str(step["name"]))
                wrote = True
                if not _ok(r):
                    raise StepFail(f"rename: {_err(r)}", before=before, wrote=wrote)
            if "beats" in step:
                r = t.pattern("set_len", pattern=p, beats=int(step["beats"]))
                wrote = True
                if not _ok(r):
                    raise StepFail(f"set_len: {_err(r)}", before=before, wrote=wrote)
        ver = {}
        if "beats" in step:
            got = t.read_pattern_beats(p)
            ver["beats"] = got
            if got != int(step["beats"]):
                raise StepFail(f"pattern length read-back {got} != {step['beats']}",
                               before=before, wrote=wrote, verification=ver)
        return {"before": before, "after": {k: step[k] for k in ("name", "beats") if k in step},
                "verification": ver, "verified": True, "wrote": wrote}

    if do == "steps":
        p = int(step["pattern"])
        before: dict = {"rows": {}}
        after: dict = {"rows": {}}
        ver: dict = {}
        wrote = False
        # snapshot everything first (nothing is written if a snapshot fails)
        wanted = {}
        for r in step["rows"]:
            ci = roles[r]["index"]
            want = step_row(recipe, step, r)
            wanted[r] = want
            part = L.get_part(env.pid, p, ci)
            old = ([bool(x) for x in part["steps"]]
                   if part and part.get("kind") in (L.KIND_STEPS, L.KIND_BATCH) else None)
            in_ledger = old is not None
            if old is None:
                old = t.read_steps(ci, p, len(want))
            before["rows"][r] = {"channel_index": ci, "pattern": p, "steps": old,
                                 "in_ledger": in_ledger}
        for r, want in wanted.items():
            ci = roles[r]["index"]
            n_bars = len(want) // 16
            res = t.channel("set_steps", index=ci, bars=step["rows"][r], n_bars=n_bars,
                            pattern=p)
            wrote = True
            if not _ok(res):
                raise StepFail(f"{r}: set_steps: {_err(res)}", before=before, wrote=wrote,
                               verification=ver)
            back = t.read_steps(ci, p, len(want))
            match = back is not None and list(back) == list(want)
            sa = res.get("state_after") if isinstance(res.get("state_after"), dict) else {}
            if not match and sa.get("active_steps") is not None:
                match = int(sa["active_steps"]) == sum(want)
            ver[r] = {"active_steps": sum(want), "total_steps": len(want),
                      "readback_match": bool(match)}
            after["rows"][r] = {"channel_index": ci, "pattern": p, "steps": want}
            if not match:
                raise StepFail(f"{r}: step read-back does not match what was written",
                               before=before, wrote=wrote, verification=ver, after=after)
        return {"before": before, "after": after, "verification": ver, "verified": True,
                "wrote": wrote}

    if do == "notes":
        p = int(step["pattern"])
        ci = roles[step["role"]]["index"]
        notes = step_notes(step)
        part = L.get_part(env.pid, p, ci)
        old = (list(part.get("notes", []))
               if part and part.get("kind") == L.KIND_NOTES else None)
        before = {"channel_index": ci, "pattern": p, "notes": old}
        mark = t.roll_mark()
        res = t.notes("write_steps", notes=[dict(n) for n in notes], mode="replace",
                      target_pattern=p, channel_index=ci)
        if not _ok(res):
            t.notes("clear_queue")
            raise StepFail(f"write_steps: {_err(res)} (queue cleared)", before=before,
                           wrote=False)
        chk = t.roll_check(mark, len(notes))
        verified = bool(chk.get("fresh") and chk.get("note_count") == len(notes))
        ver = {"notes_added": len(notes), "note_count": chk.get("note_count"),
               "fresh": chk.get("fresh")}
        after = {"channel_index": ci, "pattern": p, "notes": notes}
        if not verified:
            t.notes("clear_queue")
            raise StepFail(f"roll read-back did not confirm {len(notes)} notes "
                           f"(read {chk.get('note_count')}, fresh={chk.get('fresh')}); "
                           f"queue cleared", before=before, wrote=True, verification=ver,
                           after=after)
        return {"before": before, "after": after, "verification": ver, "verified": True,
                "wrote": True}

    if do == "fx":
        ci = roles[step["role"]]["index"]
        fields = _fx_fields(step)
        try:
            old = t.read_fx(ci, _slot(step), step["effect"], list(fields))
        except ValueError as e:
            raise StepFail(str(e)) from e
        before = {"channel_index": ci, "effect": step["effect"], "slot_index": _slot(step),
                  "values": old}
        args = dict(fields)
        if "on" in args:
            args["on"] = bool(args["on"])
        res = t.plugin(step["effect"], index=ci, slot_index=_slot(step), **args)
        if not _ok(res):
            raise StepFail(f"{step['effect']}: {_err(res)}", before=before,
                           wrote=bool(res.get("fields")) if isinstance(res, dict) else False)
        ver = {}
        good = True
        for k, f in (res.get("fields") or {}).items():
            want = (1.0 if step[k] else 0.0) if k == "on" else float(step[k])
            ver[k] = {"set": want, "value": f.get("value"), "after": f.get("after")}
            if f.get("value") is not None and not _close(f["value"], want):
                good = False
        after = {"channel_index": ci, "effect": step["effect"], "values": fields}
        if not good:
            raise StepFail("fx read-back differs from the set value", before=before,
                           wrote=True, verification=ver, after=after)
        return {"before": before, "after": after, "verification": ver, "verified": True,
                "wrote": True}

    if do == "eq":
        track = _mixer_track(roles, step["role"])
        vals = {k: float(step[k]) for k in ("gain", "freq", "bw") if k in step}
        try:
            old = t.read_eq(track, int(step["band"]))
        except Exception as e:  # noqa: BLE001
            raise StepFail(f"get_eq: {e}") from e
        before = {"track": track, "band": int(step["band"]),
                  "values": {k: old.get(k) for k in ("gain", "freq", "bw")}}
        res = t.mixer("set_eq", track=track, band=int(step["band"]), **vals)
        if not _ok(res):
            raise StepFail(f"set_eq: {_err(res)}", before=before)
        a = res.get("after") or {}
        ver = {k: {"set": v, "after": a.get(k)} for k, v in vals.items()}
        after = {"track": track, "band": int(step["band"]), "values": vals}
        if any(a.get(k) is not None and not _close(a[k], v) for k, v in vals.items()):
            raise StepFail("eq read-back differs from the set value", before=before,
                           wrote=True, verification=ver, after=after)
        return {"before": before, "after": after, "verification": ver, "verified": True,
                "wrote": True}

    if do == "mix":
        track = _mixer_track(roles, step["role"])
        old = t.read_mix(track)
        before = {"track": track, "volume": old.get("volume"), "pan": old.get("pan")}
        wrote = False
        for k, act in (("volume", "set_vol"), ("pan", "set_pan")):
            if k in step:
                res = t.mixer(act, track=track, **{k: float(step[k])})
                wrote = True
                if not _ok(res):
                    raise StepFail(f"{act}: {_err(res)}", before=before, wrote=wrote)
        now = t.read_mix(track)      # a SEPARATE trip: FL applies a set after the trip
        ver = {k: {"set": step[k], "value": now.get(k)} for k in ("volume", "pan") if k in step}
        after = {"track": track, **{k: step[k] for k in ("volume", "pan") if k in step}}
        if any(now.get(k) is not None and not _close(now[k], step[k])
               for k in ("volume", "pan") if k in step):
            raise StepFail("mixer read-back differs from the set value", before=before,
                           wrote=wrote, verification=ver, after=after)
        return {"before": before, "after": after, "verification": ver, "verified": True,
                "wrote": wrote}

    raise StepFail(f"unhandled do {do!r}")


def _short(ver: Any) -> str:
    return json.dumps(ver, sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# Env
# ---------------------------------------------------------------------------

class Env:
    def __init__(self, tools: Tools, pid: int | None):
        self.tools = tools
        self.pid = pid


def make_env(conn=None, tools=None, pid: int | None = None) -> Env:
    tools = tools or Tools(conn)
    if pid is None:
        from fl_studio_mcp.utils.roll_session import fl_pid
        pid = fl_pid()
    return Env(tools, pid)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _select(recipe: dict, p: dict) -> tuple[list[int], str | None]:
    steps = recipe["steps"]
    ids = [s["id"] for s in steps]

    def idx(sid, label):
        if sid not in ids:
            raise ValueError(f"{label}: no step with id {sid!r} (ids: {ids})")
        return ids.index(sid)

    try:
        if p.get("step") is not None:
            i = idx(p["step"], "step")
            return [i], None
        a = idx(p["from_step"], "from_step") if p.get("from_step") is not None else 0
        b = idx(p["to_step"], "to_step") if p.get("to_step") is not None else len(ids) - 1
    except ValueError as e:
        return [], str(e)
    if a > b:
        return [], f"from_step {ids[a]!r} comes after to_step {ids[b]!r}"
    return list(range(a, b + 1)), None


def _channels_or_err(env: Env) -> tuple[list[dict] | None, str | None]:
    try:
        return env.tools.channels(), None
    except Exception as e:  # noqa: BLE001
        return None, f"cannot read the FL channel list: {e}"


def _load_valid(path: str | None, env: Env | None = None, need_roles: bool = True):
    if not path:
        return None, None, {"success": False, "error": "'path' (recipe json) is required"}
    recipe, err = load_recipe(path)
    if err:
        return None, None, {"success": False, "error": err}
    channels = None
    if need_roles and env is not None:
        channels, cerr = _channels_or_err(env)
        if cerr:
            return None, None, {"success": False, "error": cerr}
    v = validate_recipe(recipe, channels)
    if v["errors"]:
        return None, None, {"success": False, "error": "recipe invalid",
                            "errors": v["errors"]}
    roles = resolve_roles(recipe, channels) if channels is not None else {}
    return recipe, roles, None


def action_validate(path, env: Env | None, offline: bool) -> dict:
    if not path:
        return {"action": "validate", "success": False, "error": "'path' is required"}
    recipe, err = load_recipe(path)
    if err:
        return {"action": "validate", "success": False, "errors": [err]}
    channels = None
    warnings: list[str] = []
    if not offline and env is not None:
        channels, cerr = _channels_or_err(env)
        if cerr:
            warnings.append(cerr + " - roles not checked")
    v = validate_recipe(recipe, channels)
    if channels is None and not warnings:
        warnings = list(v["warnings"])
    return {"action": "validate", "success": not v["errors"], "errors": v["errors"],
            "warnings": warnings, "steps": len(recipe.get("steps") or []),
            "roles_checked": channels is not None}


def action_plan(path, env: Env) -> dict:
    recipe, roles, bad = _load_valid(path, env)
    if bad:
        return {"action": "plan", **bad}
    journal = load_journal(recipe["name"], env.pid)
    rows = [plan_step(env, recipe, s, roles, journal) for s in recipe["steps"]]
    return {"action": "plan", "success": True, "recipe": recipe["name"], "plan": rows,
            "summary": {k: sum(1 for r in rows if r["status"] == k)
                        for k in ("new", "same", "changed")}}


def action_apply(path, env: Env, p: dict) -> dict:
    recipe, roles, bad = _load_valid(path, env)
    if bad:
        return {"action": "apply", **bad}
    sel, err = _select(recipe, p)
    if err:
        return {"action": "apply", "success": False, "error": err}
    steps = recipe["steps"]
    name = recipe["name"]
    force = bool(p.get("force"))
    stop_at_gates = bool(p.get("stop_at_gates"))
    table: list[dict] = []
    failed = None
    gate_msg = None
    for n, i in enumerate(sel):
        s = steps[i]
        row = {"id": s["id"], "title": s.get("title"), "do": s["do"]}
        journal = load_journal(name, env.pid)
        if not force:
            pl = plan_step(env, recipe, s, roles, journal)
            if pl["status"] == "same":
                row.update(result="skipped (same)", verification=pl["detail"])
                table.append(row)
                continue
        try:
            out = _run_step(env, recipe, s, roles)
            entry = {"step": s["id"], "do": s["do"], "ok": True, "wrote": out["wrote"],
                     "before": out["before"], "after": out["after"], "verified": True,
                     "verification": out["verification"], "sig": _sig(s),
                     "touches": touches(s, roles), "recipe": name}
            append_entry(name, env.pid, entry)
            row.update(result="ok", verification=_short(out["verification"]))
        except StepFail as e:
            pt = e.partial
            entry = {"step": s["id"], "do": s["do"], "ok": False,
                     "wrote": bool(pt.get("wrote")), "before": pt.get("before"),
                     "after": pt.get("after"), "verified": False,
                     "verification": pt.get("verification"), "error": str(e),
                     "sig": _sig(s), "touches": touches(s, roles), "recipe": name}
            append_entry(name, env.pid, entry)
            row.update(result="FAILED", error=str(e),
                       verification=_short(pt.get("verification")))
            failed = s["id"]
            table.append(row)
            break
        except Exception as e:  # noqa: BLE001 - never leave a step half-reported
            append_entry(name, env.pid, {"step": s["id"], "do": s["do"], "ok": False,
                                         "wrote": True, "before": None, "after": None,
                                         "verified": False, "error": f"{type(e).__name__}: {e}",
                                         "touches": touches(s, roles), "recipe": name})
            row.update(result="FAILED", error=f"{type(e).__name__}: {e}")
            failed = s["id"]
            table.append(row)
            break
        table.append(row)
        g = gate_end(steps, i)
        if g:
            gate_msg = (f"gate {g} reached: export the section, compare it with the "
                        f"reference (fl_audio analyze both) and listen before continuing")
            if stop_at_gates and n < len(sel) - 1:
                break
    not_run = [steps[i]["id"] for i in sel
               if steps[i]["id"] not in {r["id"] for r in table}]
    out = {"action": "apply", "success": failed is None, "recipe": name, "table": table,
           "journal": str(journal_path(name, env.pid))}
    if failed:
        out["error"] = (f"stopped at step {failed}: " +
                        next(r.get("error", "") for r in table if r["id"] == failed))
        out["not_run"] = not_run
    elif gate_msg:
        out["gate"] = gate_msg
        if not_run:
            out["not_run"] = not_run
    return out


def action_status(path, env: Env) -> dict:
    recipe, roles, bad = _load_valid(path, env, need_roles=False)
    if bad:
        return {"action": "status", **bad}
    journal = load_journal(recipe["name"], env.pid)
    channels, _ = _channels_or_err(env)
    roles2 = {}
    if channels is not None:
        try:
            roles2 = resolve_roles(recipe, channels)
        except ValueError:
            roles2 = {}
    rows = []
    for s in recipe["steps"]:
        live = last_live(journal, s["id"])
        tried = [e for e in journal["entries"] if e["step"] == s["id"] and not e.get("undo")]
        row = {"id": s["id"], "title": s.get("title"), "gate": s.get("gate"),
               "applied": live is not None,
               "verified": bool(live and live.get("verified")),
               "attempts": len(tried)}
        if live:
            row["last_applied"] = live.get("at")
            row["sig_current"] = live.get("sig") == _sig(s)
        if tried and tried[-1].get("error"):
            row["last_error"] = tried[-1]["error"]
        if roles2 and s["do"] in ("steps", "notes"):
            try:
                row["ledger"] = plan_step(env, recipe, s, roles2, journal)["status"]
            except Exception:  # noqa: BLE001
                pass
        rows.append(row)
    return {"action": "status", "success": True, "recipe": recipe["name"], "steps": rows,
            "journal": str(journal_path(recipe["name"], env.pid))}


def _undo_entry(env: Env, entry: dict) -> dict:
    """Restore one entry's `before`. Returns {verification}. Raises StepFail."""
    from fl_studio_mcp.utils import ledger as L
    t = env.tools
    do = entry["do"]
    b = entry.get("before")
    if b is None:
        raise StepFail("the journal holds no 'before' snapshot for that step")

    if do == "transport":
        if b.get("bpm") is None:
            raise StepFail("no previous BPM recorded")
        r = t.transport("set_bpm", bpm=float(b["bpm"]))
        if not _ok(r):
            raise StepFail(f"set_bpm: {_err(r)}")
        return {"bpm": b["bpm"], "note": "speed has no getter: not restored"}

    if do == "pattern":
        if not b.get("exists"):
            raise StepFail("that step created the pattern; FL cannot remove pattern slots "
                           "(clear it with fl_delete target=pattern_data instead)")
        if b.get("beats") is None:
            raise StepFail("no previous pattern length recorded")
        pat = int(entry["touches"][0].split(":")[1])
        r = t.pattern("set_len", pattern=pat, beats=int(b["beats"]))
        if not _ok(r):
            raise StepFail(f"set_len: {_err(r)}")
        return {"beats": b["beats"], "note": "pattern name is not restored"}

    if do == "steps":
        ver = {}
        for role, snap in b["rows"].items():
            ci, pat, old = snap["channel_index"], snap["pattern"], snap["steps"]
            was_empty = old is None or (not snap.get("in_ledger", True) and not any(old))
            row = old if old is not None else [False] * len(
                entry["after"]["rows"][role]["steps"])
            res = t.channel("set_steps", index=ci, steps=[bool(x) for x in row], pattern=pat)
            if not _ok(res):
                raise StepFail(f"{role}: set_steps: {_err(res)}")
            back = t.read_steps(ci, pat, len(row))
            match = back is not None and list(back) == [bool(x) for x in row]
            ver[role] = {"restored_steps": sum(1 for x in row if x), "readback_match": match}
            if was_empty:
                L.drop(env.pid, pat, ci)
            if not match:
                raise StepFail(f"{role}: step read-back does not match the restored row")
        return ver

    if do == "notes":
        ci, pat, old = b["channel_index"], b["pattern"], b.get("notes")
        mark = t.roll_mark()
        if old:
            res = t.notes("write_steps", notes=[dict(n) for n in old], mode="replace",
                          target_pattern=pat, channel_index=ci)
            expected = len(old)
        else:
            t.select_pattern(pat)
            res = t.notes("clear", channel_index=ci)
            expected = 0
        if not _ok(res):
            t.notes("clear_queue")
            raise StepFail(f"restoring notes: {_err(res)} (queue cleared)")
        chk = t.roll_check(mark, expected)
        if not (chk.get("fresh") and chk.get("note_count") == expected):
            t.notes("clear_queue")
            raise StepFail(f"roll read-back did not confirm {expected} notes "
                           f"(read {chk.get('note_count')}); queue cleared")
        if not old:
            L.drop(env.pid, pat, ci)
        return {"restored_notes": expected, "note_count": chk.get("note_count")}

    if do == "fx":
        vals = {k: v for k, v in (b.get("values") or {}).items() if v is not None}
        if not vals:
            raise StepFail("no previous effect values recorded")
        args = {k: (bool(round(v)) if k == "on" else v) for k, v in vals.items()}
        res = t.plugin(b["effect"], index=b["channel_index"],
                       slot_index=b.get("slot_index", -1), **args)
        if not _ok(res):
            raise StepFail(f"{b['effect']}: {_err(res)}")
        return {"restored": vals}

    if do == "eq":
        vals = {k: v for k, v in (b.get("values") or {}).items() if v is not None}
        if not vals:
            raise StepFail("no previous EQ values recorded")
        res = t.mixer("set_eq", track=b["track"], band=b["band"], **vals)
        if not _ok(res):
            raise StepFail(f"set_eq: {_err(res)}")
        return {"restored": vals}

    if do == "mix":
        ver = {}
        for k, act in (("volume", "set_vol"), ("pan", "set_pan")):
            if k in (entry.get("after") or {}) and b.get(k) is not None:
                res = t.mixer(act, track=b["track"], **{k: float(b[k])})
                if not _ok(res):
                    raise StepFail(f"{act}: {_err(res)}")
                ver[k] = b[k]
        if not ver:
            raise StepFail("no previous mixer values recorded")
        return {"restored": ver}

    raise StepFail(f"unhandled do {do!r}")


def action_undo(path, env: Env, p: dict) -> dict:
    recipe, roles, bad = _load_valid(path, env, need_roles=False)
    if bad:
        return {"action": "undo", **bad}
    sid = p.get("step")
    if sid is None:
        return {"action": "undo", "success": False, "error": "'step' (one step id) is required"}
    if sid not in [s["id"] for s in recipe["steps"]]:
        return {"action": "undo", "success": False, "error": f"no step with id {sid!r}"}
    name = recipe["name"]
    journal = load_journal(name, env.pid)
    entry = last_live(journal, sid)
    if entry is None:
        return {"action": "undo", "success": False,
                "error": f"step {sid} has no applied (un-undone) journal entry for this "
                         f"FL process (pid {env.pid})"}
    mine = set(entry.get("touches") or [])
    later = [e for e in live_entries(journal)
             if e["seq"] > entry["seq"] and e["step"] != sid
             and mine & set(e.get("touches") or [])]
    if later and not p.get("force"):
        return {"action": "undo", "success": False,
                "error": f"refused: later applied step(s) touched the same target: "
                         f"{sorted({e['step'] for e in later})}. Undo those first (newest "
                         f"first) or pass force=True.",
                "later_steps": sorted({e["step"] for e in later}),
                "shared": sorted(mine & {x for e in later for x in e.get('touches', [])})}
    try:
        ver = _undo_entry(env, entry)
    except StepFail as e:
        return {"action": "undo", "success": False, "step": sid, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"action": "undo", "success": False, "step": sid,
                "error": f"{type(e).__name__}: {e}"}
    append_entry(name, env.pid, {"step": sid, "do": entry["do"], "undo": True,
                                 "undoes": entry["seq"], "wrote": False, "ok": True,
                                 "before": entry.get("after"), "after": entry.get("before"),
                                 "verified": True, "verification": ver, "recipe": name})
    return {"action": "undo", "success": True, "step": sid, "restored": ver,
            "forced_over": sorted({e["step"] for e in later}) if later else []}


def _slug(name: str, taken: set[str]) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_") or "ch"
    base, n = s, 2
    while s in taken:
        s, n = f"{base}{n}", n + 1
    taken.add(s)
    return s


def action_export(path, env: Env, p: dict) -> dict:
    """Build a recipe from the part ledger (+ channel list) for a pattern range."""
    from fl_studio_mcp.utils import ledger as L
    if not path:
        return {"action": "export", "success": False, "error": "'path' (output file) is required"}
    channels, cerr = _channels_or_err(env)
    if cerr:
        return {"action": "export", "success": False, "error": cerr}
    pats = L.known_patterns(env.pid)
    lo = p.get("from_pattern") or (min(pats) if pats else 1)
    hi = p.get("to_pattern") or (max(pats) if pats else 0)
    pats = [x for x in pats if lo <= x <= hi]
    if not pats:
        return {"action": "export", "success": False,
                "error": f"the part ledger has no parts for patterns {lo}-{hi} (pid {env.pid})"}
    by_idx = {_ci(c): c for c in channels}
    used = sorted({part["channel_index"] for pt in pats
                   for part in L.get_pattern_parts(env.pid, pt)})
    taken: set[str] = set()
    role_of: dict[int, str] = {}
    chan_out = []
    for ci in used:
        c = by_idx.get(ci)
        if c is None:
            continue
        role = _slug(c.get("name"), taken)
        role_of[ci] = role
        chan_out.append({"role": role, "name": c.get("name"), "index_hint": ci})
    steps: list[dict] = []
    patterns_out = []
    bpm = None
    try:
        bpm = env.tools.read_bpm()
    except Exception:  # noqa: BLE001
        pass

    def nid():
        return f"{len(steps) + 1:02d}"

    if bpm:
        steps.append({"id": nid(), "title": "tempo", "do": "transport", "bpm": bpm})
    for pt in pats:
        beats = None
        try:
            beats = env.tools.read_pattern_beats(pt)
        except Exception:  # noqa: BLE001
            pass
        beats = beats or 16
        patterns_out.append({"pattern": pt, "beats": beats})
        steps.append({"id": nid(), "title": f"pattern {pt} length", "do": "pattern",
                      "pattern": pt, "beats": beats})
        rows = {}
        for part in L.get_pattern_parts(env.pid, pt):
            role = role_of.get(part["channel_index"])
            if role and part.get("kind") in (L.KIND_STEPS, L.KIND_BATCH) and part.get("steps"):
                rows[role] = row_to_bars(part["steps"])
        if rows:
            steps.append({"id": nid(), "title": f"pattern {pt} drums", "do": "steps",
                          "pattern": pt, "rows": rows})
        for part in L.get_pattern_parts(env.pid, pt):
            role = role_of.get(part["channel_index"])
            if role and part.get("kind") == L.KIND_NOTES and part.get("notes"):
                steps.append({"id": nid(), "title": f"pattern {pt} {role}", "do": "notes",
                              "pattern": pt, "role": role, "notes": part["notes"]})
    recipe = {"name": str(p.get("name") or Path(path).stem), "version": 1,
              "meta": {"bpm": bpm, "notes": "exported from the part ledger "
                       f"(patterns {pats[0]}-{pats[-1]})"},
              "channels": chan_out, "patterns": patterns_out, "steps": steps}
    v = validate_recipe(recipe, None)
    if v["errors"]:
        return {"action": "export", "success": False,
                "error": "exported recipe failed validation", "errors": v["errors"]}
    out = Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(recipe, indent=1))
    return {"action": "export", "success": True, "path": str(out), "steps": len(steps),
            "channels": [c["role"] for c in chan_out], "patterns": [x["pattern"] for x in patterns_out]}


def fl_recipe(action: str, conn=None, tools=None, pid: int | None = None,
              **params: Any) -> dict:
    """Run a beat as numbered, replayable, undoable steps (see recipes/README.md).

    Actions:
      validate (path, [offline=False]) - schema, `do` values, roles resolvable
          against the live channel list (skipped with offline=True or no FL)
      plan (path) - per step vs the part ledger / journal: new | same | changed
      apply (path, [step] | [from_step], [to_step], [force], [stop_at_gates])
          run steps IN ORDER, one FL call at a time, stop at the first failed or
          unverified step; journals what each step replaced. `same` steps are
          skipped unless force=True. Reports "gate Gn reached" at a gate end.
      status (path) - per step: applied / verified / gate / ledger state
      undo (path, step, [force]) - restore that step's journal `before`; refuses
          when a LATER applied step touched the same target unless force=True
      export (path, [from_pattern], [to_pattern], [name]) - write a recipe from
          the part ledger so a hand-built beat becomes replayable
    """
    if action not in ACTIONS:
        return {"success": False, "error": f"unknown action {action!r}",
                "valid_actions": list(ACTIONS)}
    path = params.get("path")
    try:
        if action == "validate":
            env = None
            if not params.get("offline"):
                env = make_env(conn, tools, pid)
            return action_validate(path, env, bool(params.get("offline")))
        env = make_env(conn, tools, pid)
        if action == "plan":
            return action_plan(path, env)
        if action == "apply":
            return action_apply(path, env, params)
        if action == "status":
            return action_status(path, env)
        if action == "undo":
            return action_undo(path, env, params)
        return action_export(path, env, params)
    except Exception as e:  # noqa: BLE001
        return {"action": action, "success": False, "error": f"{type(e).__name__}: {e}"}


def register_recipe_tools_v2(mcp: FastMCP) -> None:
    """Register the fl_recipe tool."""
    from fl_studio_mcp.tools.recipe_v2 import fl_recipe as _impl

    @mcp.tool()
    def fl_recipe(
        action: str,
        path: str | None = None,
        step: str | None = None,
        from_step: str | None = None,
        to_step: str | None = None,
        force: bool | None = None,
        stop_at_gates: bool | None = None,
        offline: bool | None = None,
        from_pattern: int | None = None,
        to_pattern: int | None = None,
        name: str | None = None,
    ) -> dict:
        """A beat as numbered steps you can apply, edit, re-apply and undo one at a time.

        Actions: validate | plan | apply | status | undo | export. `path` = a recipe
        JSON (fl-studio-mcp/recipes/<name>.json; a bare name resolves there).
        validate(path, [offline]) checks schema + roles. plan(path) = new/same/changed
        per step vs the part ledger. apply(path, [step] | [from_step], [to_step],
        [force], [stop_at_gates]) runs steps in order, one FL call at a time, stops at
        the first failed/unverified step, journals the previous state, and says
        "gate Gn reached" so you compare + listen. undo(path, step, [force]) restores
        that step's previous state (refuses if a later step touched the same
        channel+pattern). export(path, [from_pattern], [to_pattern], [name]) builds a
        recipe from the ledger. Details: fl_help(domain="recipe").
        """
        p = {k: v for k, v in {"path": path, "step": step, "from_step": from_step,
             "to_step": to_step, "force": force, "stop_at_gates": stop_at_gates,
             "offline": offline, "from_pattern": from_pattern, "to_pattern": to_pattern,
             "name": name}.items() if v is not None}
        return _impl(action, **p)

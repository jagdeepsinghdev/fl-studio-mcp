"""S4: the FL **part ledger** — a server-side record of what has been written.

Why this exists
---------------
FL can only *export* the notes of the **open** piano roll (ComposeWithLLM →
``piano_roll_state.json``). A tool therefore cannot read back another
channel's notes without opening that channel's roll (the §6b handshake, a
slow per-channel OCR round trip). The ledger sidesteps that for parts the
*server itself* wrote: every successful ``fl_notes write_steps`` /
``fl_channel set_steps`` / batch ``channels.setStepSequence`` appends a row

    {pattern, channel_index, channel_name, notes|steps, verified}

to ``fl-studio-mcp/.generated/parts/<pid>.json``. ``fl_state`` surfaces
"parts known for pattern N" and ``fl_pattern chain`` (S5) reads a section's
parts from here instead of re-opening every roll.

Scoping (S4 test: "pid change starts a new ledger")
--------------------------------------------------
The file is named for the **FL process id** (``fl_pid()``). A running FL has
one stable pid; a restart changes it, so the old file is simply ignored and
a fresh one is created. In tests / with no FL running the pid is ``None`` and
we fall back to a temp dir (via ``LEDGER_DIR``), never touching the real
``.generated`` tree.

What "verified" means
---------------------
``fl_notes write_steps`` returns only a confirmation string, so the ledger
stores ``notes_added = len(notes)`` and the caller can later confirm against
the roll read-back. ``fl_channel set_steps`` reports the controller's
same-trip ``active_steps`` / ``total_steps`` — stored as
``verified.active_steps`` / ``verified.total_steps``.

This module is **pure**: no MIDI, no FL, no OCR. All I/O is the small JSON
file; every function is unit-testable offline.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

#: kind discriminator for the three write paths that feed the ledger.
KIND_NOTES = "notes"     # fl_notes write_steps
KIND_STEPS = "steps"     # fl_channel set_steps (per-channel step sequence)
KIND_BATCH = "batch"     # batched channels.setStepSequence

_STEPS_PER_BAR = 16


def ledger_dir() -> Path:
    """Where ``<pid>.json`` ledger files live.

    ``LEDGER_DIR`` wins (tests point it at a temp dir). Otherwise the
    project ``.generated/parts`` dir, created on demand.
    """
    env = os.environ.get("LEDGER_DIR")
    if env:
        p = Path(env)
    else:
        # fl_studio_mcp/<pkg>/utils/ledger.py -> parents[2] = fl-studio-mcp
        p = Path(__file__).resolve().parents[3] / ".generated" / "parts"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _resolve_pid(pid: int | None) -> int | None:
    if pid is not None:
        return pid
    from fl_studio_mcp.utils.roll_session import fl_pid
    return fl_pid()


def _path(pid: int | None) -> Path:
    pid = _resolve_pid(pid)
    if pid is None:
        # No running FL (tests, or FL not started): fall back to a temp dir
        # so we never write into the real .generated tree during a test run.
        import tempfile
        d = Path(tempfile.gettempdir()) / "fl-part-ledger-nopid"
        d.mkdir(parents=True, exist_ok=True)
        return d / "nopid.json"
    return ledger_dir() / f"{pid}.json"


def _load(pid: int | None) -> dict:
    p = _path(pid)
    try:
        data = json.loads(p.read_text())
        if not isinstance(data, dict):
            data = {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    data.setdefault("fl_pid", _resolve_pid(pid))
    data.setdefault("updated", None)
    data.setdefault("parts", {})
    return data


def _save(data: dict) -> None:
    p = _path(data.get("fl_pid"))
    p.parent.mkdir(parents=True, exist_ok=True)
    data["updated"] = time.time()
    p.write_text(json.dumps(data, indent=2, sort_keys=True))


def _key(pattern: int, channel_index: int) -> str:
    return f"{int(pattern)}:{int(channel_index)}"


def _row(pid: int | None, pattern: int, channel_index: int) -> dict | None:
    return _load(pid).get("parts", {}).get(_key(pattern, channel_index))


def get_part(pid: int | None, pattern: int, channel_index: int) -> dict | None:
    """The recorded part for (pattern, channel), or None if unknown."""
    return _row(pid, pattern, channel_index)


def get_pattern_parts(pid: int | None, pattern: int) -> list[dict]:
    """All recorded parts for one pattern, ordered by channel_index."""
    parts = [v for k, v in _load(pid).get("parts", {}).items()
             if k.split(":", 1)[0] == str(int(pattern))]
    parts.sort(key=lambda v: v.get("channel_index", 0))
    return parts


def known_patterns(pid: int | None) -> list[int]:
    """Distinct pattern indices that have at least one recorded part."""
    seen = {k.split(":", 1)[0] for k in _load(pid).get("parts", {}).keys()}
    return sorted(int(k) for k in seen)


def record_notes(pid: int | None, pattern: int, channel_index: int,
                 channel_name: str | None, notes: list[dict],
                 verified: dict | None = None, mode: str = "replace") -> dict:
    """Record a `fl_notes write_steps` write. Returns the stored row.

    mode="replace" (default) replaces the (pattern, channel) part;
    mode="add" appends the notes to the existing part (the roll keeps its
    old notes when a write is queued in add mode).
    """
    data = _load(pid)
    if mode == "add":
        old = data["parts"].get(_key(pattern, channel_index))
        if old and old.get("kind") == KIND_NOTES:
            notes = list(old.get("notes", [])) + list(notes)
    row: dict = {
        "pattern": int(pattern),
        "channel_index": int(channel_index),
        "channel_name": channel_name,
        "kind": KIND_NOTES,
        "notes": list(notes),
        "verified": {
            "notes_added": len(notes),
            **(verified or {}),
        },
        "recorded_at": time.time(),
    }
    data["parts"][_key(pattern, channel_index)] = row
    _save(data)
    return row


def record_steps(pid: int | None, pattern: int, channel_index: int,
                 channel_name: str | None, steps: list[bool],
                 verified: dict | None = None) -> dict:
    """Record a `fl_channel set_steps` write. Returns the stored row."""
    data = _load(pid)
    row = {
        "pattern": int(pattern),
        "channel_index": int(channel_index),
        "channel_name": channel_name,
        "kind": KIND_STEPS,
        "steps": [bool(s) for s in steps],
        "verified": {
            "active_steps": sum(1 for s in steps if s),
            "total_steps": len(steps),
            **(verified or {}),
        },
        "recorded_at": time.time(),
    }
    data["parts"][_key(pattern, channel_index)] = row
    _save(data)
    return row


def record_batch(pid: int | None, pattern: int, parts: list[dict]) -> int:
    """Record a batched `channels.setStepSequence` (many channels at once).

    Each part: ``{channel_index, channel_name?, steps:[bool], verified?}``.
    Returns the number of rows recorded (one per channel).
    """
    n = 0
    for p in parts:
        record_steps(pid, pattern, int(p["channel_index"]),
                     p.get("channel_name"), list(p.get("steps", [])),
                     p.get("verified"))
        n += 1
    return n


def drop(pid: int | None, pattern: int, channel_index: int) -> bool:
    """Remove a part (e.g. after a clear). Returns True if one was removed."""
    data = _load(pid)
    if data["parts"].pop(_key(pattern, channel_index), None) is None:
        return False
    _save(data)
    return True


def clear(pattern: int | None = None, pid: int | None = None) -> int:
    """Clear the ledger for a pattern (or the whole file). Rows removed."""
    data = _load(pid)
    if pattern is None:
        n = len(data["parts"])
        data["parts"] = {}
    else:
        keys = [k for k in data["parts"] if k.split(":", 1)[0] == str(int(pattern))]
        for k in keys:
            del data["parts"][k]
        n = len(keys)
    if n:
        _save(data)
    return n


# ---------------------------------------------------------------------------
# S5 helpers — pure offset/concat math (unit-testable, no FL)
# ---------------------------------------------------------------------------

def shift_notes(notes: list[dict], offset_beats: float) -> list[dict]:
    """Return a copy of `notes` with every `time` advanced by `offset_beats`.

    Notes are in beats (the ComposeWithLLM note schema); slides move with
    their host note because they share the host's start.
    """
    out = []
    for n in notes:
        c = dict(n)
        if c.get("time") is not None:
            c["time"] = round(c["time"] + offset_beats, 4)
        out.append(c)
    return out


def concat_steps(rows: list[dict]) -> list[bool]:
    """Concatenate per-section step rows into one flat row for a new pattern.

    `rows` is in section order. Each element: ``{steps:[bool], repeat:int}``.
    A row is repeated `repeat` times, then the next row is appended. The
    result length is ``sum(len(steps) * repeat)``.
    """
    out: list[bool] = []
    for r in rows:
        row = [bool(s) for s in r["steps"]]
        out.extend(row * int(r.get("repeat", 1)))
    return out


def notes_at(parts: list[dict], base_beats: float) -> list[dict]:
    """All of a section's notes, shifted to start at `base_beats`.

    `parts` is the list of recorded parts for one section; a part with no
    `notes` (a steps-only channel) contributes nothing. Call this once per
    copy of a repeated section (base_beats = section_start + i * len).
    """
    out: list[dict] = []
    for part in parts:
        for n in part.get("notes", []):
            out.extend(shift_notes([n], base_beats))
    return out

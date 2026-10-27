"""S4 (part ledger) + S5 (fl_pattern chain) — offline.

S4:
  - writes are recorded (notes + steps) and re-reading returns them
  - re-writing the same (pattern, channel) REPLACES the row (not a duplicate)
  - a pid change starts a NEW ledger (old file untouched)
  - get_pattern_parts / known_patterns
  - offset/concat math (shift_notes, concat_steps, notes_at)

S5:
  - chain offset math: Intro 16 + Hook 16 x2 -> 48 beats; an 808 note 25@0 ->
    25@16 and 25@32, slides kept
  - chain refuses when a section has no recorded part (lists the missing)
  - the live orchestration path (mocked trigger/roll/conn) writes every
    channel's steps + notes into the new pattern and verifies the read-back
"""


import pytest

from fl_studio_mcp.utils import ledger as L

PID = 4242          # the "current" FL process in this file
OTHER = 9999        # a different FL process (pid-change test)


@pytest.fixture(autouse=True)
def _dir(tmp_path, monkeypatch):
    """A temp ledger dir so nothing touches the real .generated tree."""
    monkeypatch.setenv("LEDGER_DIR", str(tmp_path / "parts"))
    yield


# ---------------------------------------------------------------------------
# S4 — recording
# ---------------------------------------------------------------------------


def test_record_notes_and_read_back():
    row = L.record_notes(PID, 1, 4, "808 Kick",
                         [{"midi": 25, "duration": 0.5, "time": 0}],
                         {"notes_added": 1})
    assert row["kind"] == "notes"
    assert row["verified"]["notes_added"] == 1
    got = L.get_part(PID, 1, 4)
    assert got is not None and got["channel_name"] == "808 Kick"
    assert got["notes"][0]["midi"] == 25


def test_rewrite_replaces_not_duplicates():
    L.record_notes(PID, 1, 4, "808", [{"midi": 25, "duration": 0.5, "time": 0}])
    L.record_notes(PID, 1, 4, "808",
                   [{"midi": 25, "duration": 1.0, "time": 0},
                    {"midi": 28, "duration": 0.5, "time": 2}])
    parts = L.get_pattern_parts(PID, 1)
    assert len(parts) == 1                      # replaced, not appended
    assert len(parts[0]["notes"]) == 2
    assert parts[0]["channel_index"] == 4


def test_pid_change_starts_new_ledger():
    L.record_notes(PID, 1, 0, "Kick", [{"midi": 36, "duration": 0.5, "time": 0}])
    # a brand-new pid sees an empty ledger (the old file is not consulted)
    L.record_notes(OTHER, 2, 1, "Bass", [{"midi": 33, "duration": 1.0, "time": 0}])
    assert L.get_part(OTHER, 2, 1) is not None
    assert L.get_part(OTHER, 1, 0) is None      # PID's part is invisible to OTHER
    # and the old file still holds PID's part
    assert L.get_part(PID, 1, 0) is not None


def test_record_steps_computes_verification():
    row = L.record_steps(PID, 1, 0, "Kick", [True, False, True, False] * 4)
    assert row["kind"] == "steps"
    assert row["verified"]["active_steps"] == 8
    assert row["verified"]["total_steps"] == 16


def test_known_patterns_and_pattern_parts_ordering():
    L.record_steps(PID, 2, 5, "Pad", [True] * 16)
    L.record_notes(PID, 2, 1, "Bass", [{"midi": 33, "duration": 1.0, "time": 0}])
    L.record_notes(PID, 1, 4, "808", [{"midi": 25, "duration": 0.5, "time": 0}])
    assert L.known_patterns(PID) == [1, 2]
    parts = L.get_pattern_parts(PID, 2)
    assert [p["channel_index"] for p in parts] == [1, 5]   # sorted by channel


# ---------------------------------------------------------------------------
# S4 — offset / concat math (pure)
# ---------------------------------------------------------------------------


def test_shift_notes_preserves_slide_and_durations():
    notes = [{"midi": 25, "duration": 0.5, "time": 0, "slide": True},
             {"midi": 28, "duration": 1.0, "time": 2}]
    out = L.shift_notes(notes, 16)
    assert out[0] == {"midi": 25, "duration": 0.5, "time": 16, "slide": True}
    assert out[1] == {"midi": 28, "duration": 1.0, "time": 18}
    # the original list is not mutated
    assert notes[0]["time"] == 0


def test_concat_steps_repeats_in_section_order():
    rows = [{"steps": [True, False], "repeat": 2},
            {"steps": [False, True, True], "repeat": 1}]
    assert L.concat_steps(rows) == [True, False, True, False,
                                    False, True, True]


def test_notes_at_places_one_copy_at_base():
    part = {"notes": [{"midi": 25, "duration": 0.5, "time": 0},
                      {"midi": 28, "duration": 0.5, "time": 4}]}
    out = L.notes_at([part], 16)
    assert [n["time"] for n in out] == [16, 20]


# ---------------------------------------------------------------------------
# S5 — chain offset math (the S5 test's example, offline)
# ---------------------------------------------------------------------------


# (the real-_chain offset test lives below, after FakeConn)


# ---------------------------------------------------------------------------
# S5 — chain refusal + live orchestration (mocked)
# ---------------------------------------------------------------------------


class FakeConn:
    """A stand-in for the FL connection: canned read results + write log."""

    def __init__(self, channels, pattern_lengths, pattern_count=3):
        self.channels = channels
        self.pattern_lengths = pattern_lengths   # 1-based -> beats
        self.pattern_count = pattern_count
        self.active = 1
        self.writes = []

    def send_command(self, action, params=None, **kw):
        params = params or {}
        if action == "probe.patterns":
            return {"active_pattern": self.active,
                    "pattern_count": self.pattern_count}
        if action == "channels.getAll":
            return {"channels": self.channels}
        if action == "channels.getStepSequence":
            return {"sequence": self._row(params["channel"],
                                          int(params.get("steps", 16)))}
        if action == "patterns.getLength":
            return {"length_beats":
                    self.pattern_lengths.get(params["index"] + 1, 16)}
        if action == "patterns.create":
            self.writes.append(("create", params))
            return {"pattern": self.pattern_count, "success": True}
        if action == "patterns.select":
            self.writes.append(("select", params["pattern"]))
            return {"success": True}
        if action == "channels.selectOne":
            self.writes.append(("selectOne", params["index"]))
            return {"success": True}
        if action == "channels.setStepSequence":
            self.writes.append(("setSteps", (params["channel"],
                                             list(params["pattern"]),
                                             params.get("target_pattern"))))
            return {"success": True}
        return {"success": True}

    def _row(self, ci, n):
        # ch0 kick: one hit per 16-step block (step 0 of each bar); the
        # melody channel has no steps.
        if ci == 0:
            return [i % 16 == 0 for i in range(n)]
        return [False] * n


def test_chain_refuses_when_section_has_no_notes_and_no_steps():
    from fl_studio_mcp.tools import pattern_v2 as P
    L.clear(pattern=None, pid=1)  # empty ledger for pid 1
    conn = FakeConn([{"index": 4, "name": "808"}],          # a channel with no steps
                  {1: 16, 2: 16, 3: 16})
    out = P._chain(
        {"name": "Full",
         "sections": [{"pattern": 1, "repeat": 1},
                      {"pattern": 2, "repeat": 2}]},
        conn, trigger=lambda: True,
        open_roll=lambda i: {"ok": True},
        roll_read=lambda: {"note_count": 0},
        state_mtime=lambda: 0.0, ran_since=lambda b: False, ledger_pid=1)
    assert out["success"] is False
    assert out["missing"]                        # both sections are missing
    assert not [w for w in conn.writes if w[0] == "create"]   # nothing created


def test_chain_accepts_step_only_sections():
    """2026-10-11: an Afrobeats Intro + Beat (step sequencer only, no roll notes) was refused."""
    from fl_studio_mcp.tools import pattern_v2 as P
    L.clear(pattern=None, pid=1)
    conn = FakeConn([{"index": 0, "name": "Kick"}], {1: 16, 2: 16, 3: 16})
    out = P._chain(
        {"name": "Full", "sections": [{"pattern": 1, "repeat": 1}, {"pattern": 2, "repeat": 2}]},
        conn, trigger=lambda: True, open_roll=lambda i: {"ok": True},
        roll_read=lambda: {"note_count": 0}, state_mtime=lambda: 0.0,
        ran_since=lambda b: False, ledger_pid=1)
    assert out["success"] is True
    steps = [w for w in conn.writes if w[0] == "setSteps"]
    assert len(steps) == 1 and len(steps[0][1][1]) == 48 * 4   # 16 + 2x16 beats, kick concatenated
    assert sum(steps[0][1][1]) == 12                           # one kick per bar, 12 bars


def test_chain_builds_full_pattern(monkeypatch):
    import fl_studio_mcp.tools.piano_roll as pr
    from fl_studio_mcp.tools import pattern_v2 as P
    from fl_studio_mcp.utils import roll_session as rs

    # two sections: Intro=pat2 (16), Hook=pat1 (16) x2 -> 48 beats / 192 steps
    L.record_notes(1, 2, 4, "808", [{"midi": 25, "duration": 0.5, "time": 0}])
    L.record_notes(1, 1, 4, "808",
                   [{"midi": 25, "duration": 0.5, "time": 0},
                    {"midi": 28, "duration": 1.0, "time": 4}])
    L.record_steps(1, 2, 0, "Kick", [True, False, False, False] * 4)
    L.record_steps(1, 1, 0, "Kick", [True, False, False, False] * 4)

    conn = FakeConn([{"index": 0, "name": "Kick"},
                     {"index": 4, "name": "808"}],
                  {1: 16, 2: 16, 3: 16})

    calls = {"trigger": 0, "roll": 0}

    def fake_trigger():
        calls["trigger"] += 1
        return True

    def fake_roll_read():
        calls["roll"] += 1
        return {"note_count": 5}   # Intro(1) + Hook(2) x2 = 5 placed notes

    monkeypatch.setattr(rs, "ensure_script_selected",
                        lambda force=False: {"ok": True})
    reqs = []
    monkeypatch.setattr(pr, "_write_request", lambda r, **k: reqs.append(r))

    import fl_studio_mcp.utils.connection as _connmod
    _connmod.get_connection = lambda: conn  # so _write_request hits FakeConn

    out = P._chain(
        {"name": "Full",
         "sections": [{"pattern": 2, "repeat": 1},
                      {"pattern": 1, "repeat": 2}]},
        conn, trigger=fake_trigger,
        open_roll=lambda i: {"ok": True},
        roll_read=fake_roll_read,
        state_mtime=lambda: 0.0, ran_since=lambda b: True,
        ledger_pid=1)

    assert out["success"] is True
    assert out["total_beats"] == 48
    assert out["total_steps"] == 192
    assert out["new_pattern"] == 3
    assert out["notes_written"] == 1              # only the 808 has notes
    assert calls["trigger"] == 1                  # one roll write (the 808)
    assert len(reqs) == 1
    added = [r for r in reqs[0] if r["action"] == "add_notes"][0]["notes"]
    assert [(n["midi"], n["time"]) for n in added] == [
        (25, 0), (25, 16), (28, 20), (25, 32), (28, 36)]

    # the kick's full 192-step row was written into the new pattern (pat 3)
    kick_writes = [w for w in conn.writes
                  if w[0] == "setSteps" and w[1][0] == 0 and w[1][2] == 3]
    assert len(kick_writes) == 1
    full_row = kick_writes[0][1][1]
    assert len(full_row) == 192
    # Intro kick (16) + Hook kick (16) x2, each with a hit on step 0 of its 16
    hit_steps = [i for i, v in enumerate(full_row) if v]
    assert hit_steps == [0, 16, 32, 48, 64, 80, 96, 112, 128, 144, 160, 176]


def _run_chain(monkeypatch, open_roll, tmp_ledger=True):
    import fl_studio_mcp.tools.piano_roll as pr
    from fl_studio_mcp.tools import pattern_v2 as P
    from fl_studio_mcp.utils import roll_session as rs

    L.record_notes(1, 2, 4, "808", [{"midi": 25, "duration": 0.5, "time": 0}])
    L.record_notes(1, 1, 4, "808",
                   [{"midi": 25, "duration": 0.5, "time": 0, "slide": True}])
    L.record_notes(1, 2, 5, "Bells", [{"midi": 60, "duration": 1.0, "time": 2}])
    L.record_notes(1, 1, 5, "Bells", [{"midi": 62, "duration": 1.0, "time": 2}])
    conn = FakeConn([{"index": 4, "name": "808"}, {"index": 5, "name": "Bells"}],
                    {1: 16, 2: 16, 3: 16})
    reqs = []
    monkeypatch.setattr(pr, "_write_request", lambda r, **k: reqs.append(r))
    monkeypatch.setattr(rs, "ensure_script_selected", lambda force=False: {"ok": True})
    out = P._chain(
        {"name": "Full",
         "sections": [{"pattern": 2, "repeat": 1}, {"pattern": 1, "repeat": 2}]},
        conn, trigger=lambda: True, open_roll=open_roll,
        roll_read=lambda: {"note_count": 3},
        state_mtime=lambda: 0.0, ran_since=lambda b: True, ledger_pid=1)
    return out, reqs, conn


def test_chain_offsets_use_cumulative_section_start(monkeypatch):
    """Intro 16 + Hook 16 x2: 808 note at 0 -> Intro@0, Hook@16, Hook@32."""
    opened = []
    out, reqs, conn = _run_chain(
        monkeypatch, lambda i: opened.append(i) or {"ok": True})
    assert out["success"] is True and out["total_beats"] == 48
    assert opened == [4, 5]                      # roll retargeted per channel
    by_ch = {}
    for ci, r in zip(opened, reqs):
        by_ch[ci] = [n for x in r if x["action"] == "add_notes" for n in x["notes"]]
    assert [n["time"] for n in by_ch[4]] == [0, 16, 32]
    assert [n["slide"] for n in by_ch[4] if "slide" in n] == [True, True]
    assert [n["time"] for n in by_ch[5]] == [2, 18, 34]
    assert [n["midi"] for n in by_ch[5]] == [60, 62, 62]


def test_chain_refuses_channel_when_roll_retarget_fails(monkeypatch):
    def open_roll(i):
        return {"ok": i != 4, "error": "cannot confirm roll"}
    out, reqs, conn = _run_chain(monkeypatch, open_roll)
    assert out["success"] is False
    assert [r["channel"] for r in out["refused_channels"]] == [4]
    assert len(reqs) == 1                         # only Bells was written
    only = [n for x in reqs[0] if x["action"] == "add_notes" for n in x["notes"]]
    assert only[0]["midi"] == 60
    assert L.get_part(1, 3, 4) is None            # nothing recorded for 808


def test_ledger_add_appends_replace_replaces():
    L.record_notes(PID, 1, 4, "808", [{"midi": 25, "duration": 0.5, "time": 0}])
    L.record_notes(PID, 1, 4, "808", [{"midi": 28, "duration": 0.5, "time": 4}],
                   mode="add")
    assert [n["midi"] for n in L.get_part(PID, 1, 4)["notes"]] == [25, 28]
    L.record_notes(PID, 1, 4, "808", [{"midi": 30, "duration": 0.5, "time": 0}],
                   mode="replace")
    assert [n["midi"] for n in L.get_part(PID, 1, 4)["notes"]] == [30]


def test_notes_hook_records_selected_channel(monkeypatch):
    from fl_studio_mcp.tools import notes_v2 as N
    monkeypatch.setattr(N, "_write_steps_via_queue", lambda *a, **k: "ok")
    monkeypatch.setattr(N, "_safe_send", lambda *a, **k: {"success": True})
    monkeypatch.setattr(L, "_resolve_pid", lambda pid: PID)

    class C:
        def __init__(self, chans): self.chans = chans
        def send_command(self, a, p=None, **k):
            return {"channels": self.chans, "success": True}

    notes = [{"midi": 25, "duration": 0.5, "time": 0}]
    N.fl_notes("write_steps", conn=C([{"index": 0, "name": "A", "is_selected": False},
                                      {"index": 3, "name": "B", "is_selected": True}]),
               notes=notes, open_roll_verified=True, target_pattern=2)
    assert L.get_part(PID, 2, 3)["channel_name"] == "B"
    assert L.get_part(PID, 2, -1) is None
    # undeterminable channel -> nothing recorded
    N.fl_notes("write_steps", conn=C([{"index": 0, "name": "A", "is_selected": False}]),
               notes=notes, open_roll_verified=True, target_pattern=5)
    assert L.get_pattern_parts(PID, 5) == []


class _ActiveOnlyConn(FakeConn):
    """Like live FL: getStepSequence ignores target_pattern and returns the ACTIVE pattern's row."""
    ROWS = {1: [True] + [False] * 15, 2: [False] * 15 + [True]}

    def send_command(self, action, params=None, **kw):
        if action == "channels.getStepSequence":
            row = self.ROWS[self.active]
            return {"sequence": (row * 4)[:int(params.get("steps", 16))]}
        if action == "patterns.select":
            self.active = int(params["pattern"])
        return super().send_command(action, params, **kw)


def test_chain_reads_each_section_from_that_section_not_the_active_pattern():
    from fl_studio_mcp.tools import pattern_v2 as P
    L.clear(pattern=None, pid=1)
    conn = _ActiveOnlyConn([{"index": 0, "name": "Kick"}], {1: 4, 2: 4, 3: 4})
    conn.active = 1                        # pattern 1 is active when the chain starts
    out = P._chain({"name": "Full", "sections": [{"pattern": 1, "repeat": 1}, {"pattern": 2, "repeat": 1}]},
                   conn, trigger=lambda: True, open_roll=lambda i: {"ok": True},
                   roll_read=lambda: {"note_count": 0}, state_mtime=lambda: 0.0,
                   ran_since=lambda b: False, ledger_pid=1)
    assert out["success"] is True
    row = [w for w in conn.writes if w[0] == "setSteps"][0][1][1]
    assert [i for i, v in enumerate(row) if v] == [0, 31]      # pattern 1's hit, then pattern 2's (bar 2 end)

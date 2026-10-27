"""fl_recipe: validate / plan / apply / status / undo / export (mocked FL).

FakeTools replaces the in-process tool adapter: it keeps a tiny fake FL
(steps, roll notes, fx knobs, eq, mixer, bpm), writes the part ledger exactly as
the real tools do, and logs every call so ordering can be asserted. Nothing
here touches FL, MIDI or the real .generated tree.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from fl_studio_mcp.tools import recipe_v2 as R
from fl_studio_mcp.tools.recipe_v2 import Tools, fl_recipe
from fl_studio_mcp.utils import ledger as L

PID = 777
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("LEDGER_DIR", str(tmp_path / "parts"))
    monkeypatch.setenv("RECIPE_JOURNAL_DIR", str(tmp_path / "journal"))


class FakeTools(Tools):
    def __init__(self, channels):
        super().__init__(conn=object())
        self.chs = channels
        self.bpm = 120.0
        self.patterns = {1: 16}
        self.steps: dict = {}
        self.roll: dict = {}
        self.fx: dict = {}
        self.eq: dict = {}
        self.mix: dict = {}
        self.calls: list = []
        self.roll_fresh = True
        self.last_count = 0
        self.fail_notes_for: set[int] = set()
        self.queue_clears = 0
        self.cur_pat = 1

    # ---- helpers
    def _name(self, ci):
        return next(c["name"] for c in self.chs if c["index"] == ci)

    # ---- reads
    def channels(self):
        return copy.deepcopy(self.chs)

    def read_bpm(self):
        return self.bpm

    def pattern_count(self):
        return max(self.patterns)

    def read_pattern_beats(self, p):
        return self.patterns.get(p)

    def read_steps(self, ci, p, n):
        return list(self.steps.get((p, ci), [False] * n))

    def select_pattern(self, p):
        self.calls.append(("select_pattern", p))
        self.cur_pat = p
        return {"success": True}

    def read_fx(self, ci, slot, effect, fields):
        return {k: self.fx.get((ci, effect, k), 0.0) for k in fields}

    def read_eq(self, track, band):
        return dict(self.eq.get((track, band), {"gain": 0.5, "freq": 0.5, "bw": 0.5}))

    def read_mix(self, track):
        return dict(self.mix.get(track, {"volume": 0.8, "pan": 0.0}))

    def roll_mark(self):
        return 0

    def roll_check(self, mark, expected):
        return {"fresh": self.roll_fresh, "note_count": self.last_count, "expected": expected}

    # ---- writes
    def transport(self, action, **p):
        self.calls.append(("transport", action, p))
        if action == "set_bpm":
            self.bpm = p["bpm"]
        return {"success": True}

    def pattern(self, action, **p):
        self.calls.append(("pattern", action, p))
        if action == "create":
            self.patterns[max(self.patterns) + 1] = p.get("length_beats", 16)
        elif action == "set_len":
            self.patterns[p["pattern"]] = p["beats"]
        return {"success": True}

    def channel(self, action, **p):
        self.calls.append(("channel", action, p.get("index")))
        assert action == "set_steps"
        if "bars" in p:
            row = R.step_row({"patterns": [{"pattern": p["pattern"], "beats": p["n_bars"] * 4}]},
                             {"pattern": p["pattern"], "rows": {"x": p["bars"]}}, "x")
        else:
            row = [bool(x) for x in p["steps"]]
        self.steps[(p["pattern"], p["index"])] = row
        L.record_steps(PID, p["pattern"], p["index"], self._name(p["index"]), row)
        return {"success": True, "state_after": {"active_steps": sum(row)}}

    def notes(self, action, **p):
        self.calls.append(("notes", action, p.get("channel_index")))
        if action == "clear_queue":
            self.queue_clears += 1
            return {"success": True}
        ci = p["channel_index"]
        pat = p.get("target_pattern")
        if action == "clear":
            self.roll[(self.cur_pat, ci)] = []
            self.last_count = 0
            return {"success": True}
        assert action == "write_steps" and p["mode"] == "replace"
        notes = p["notes"]
        self.roll[(pat, ci)] = notes
        self.last_count = 0 if ci in self.fail_notes_for else len(notes)
        L.record_notes(PID, pat, ci, self._name(ci), notes, mode="replace")
        return {"success": True}

    def plugin(self, action, index, slot_index=-1, **fields):
        self.calls.append(("plugin", action, index))
        out = {}
        for k, v in fields.items():
            val = (1.0 if v else 0.0) if k == "on" else float(v)
            self.fx[(index, action, k)] = val
            out[k] = {"ok": True, "value": val, "after": f"{val}"}
        return {"success": True, "fields": out}

    def mixer(self, action, **p):
        self.calls.append(("mixer", action, p.get("track")))
        t = p["track"]
        if action == "set_eq":
            cur = self.eq.setdefault((t, p["band"]), {"gain": 0.5, "freq": 0.5, "bw": 0.5})
            cur.update({k: p[k] for k in ("gain", "freq", "bw") if k in p})
            return {"success": True, "after": dict(cur)}
        if action in ("set_vol", "set_pan"):
            self.mix.setdefault(t, {"volume": 0.8, "pan": 0.0})[
                "volume" if action == "set_vol" else "pan"] = p.get("volume", p.get("pan"))
            return {"success": True}
        raise AssertionError(action)


def chans(order=("808 Kick", "808 Clap", "Bass", "Piano")):
    return [{"index": i, "name": n, "target_fx_track": i + 1} for i, n in enumerate(order)]


def make_recipe(**over):
    r = {
        "name": "t-recipe", "version": 1,
        "channels": [{"role": "kick", "name": "808 Kick"}, {"role": "clap", "name": "808 Clap"},
                     {"role": "bass", "name": "Bass"}, {"role": "piano", "name": "Piano"}],
        "patterns": [{"pattern": 1, "name": "Hook", "beats": 16}],
        "steps": [
            {"id": "01", "title": "tempo", "do": "transport", "bpm": 85},
            {"id": "02", "title": "drums", "gate": "G1", "do": "steps", "pattern": 1,
             "rows": {"kick": [[1, 11], [1, 8], [1, 11], [1, 8, 11]], "clap": [[5, 13]]}},
            {"id": "03", "title": "bass", "gate": "G2", "do": "notes", "pattern": 1,
             "role": "bass", "notes": [{"midi": 26, "time": 0, "duration": 1.5, "velocity": 0.9}]},
            {"id": "04", "title": "piano echo", "do": "fx", "role": "piano",
             "effect": "echo", "mix": 0.3},
            {"id": "05", "title": "bass eq", "do": "eq", "role": "bass", "band": 0, "gain": 0.45},
            {"id": "06", "title": "levels", "do": "mix", "role": "piano", "volume": 0.6},
        ],
    }
    r.update(over)
    return r


def write(tmp_path, recipe, name="r.json") -> str:
    p = tmp_path / name
    p.write_text(json.dumps(recipe))
    return str(p)


def run(action, path, ft, **kw):
    return fl_recipe(action, tools=ft, pid=PID, path=path, **kw)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def test_validate_ok_offline(tmp_path):
    out = fl_recipe("validate", path=write(tmp_path, make_recipe()), offline=True)
    assert out["success"] is True and out["errors"] == []


def test_validate_reports_errors(tmp_path):
    r = make_recipe()
    r["steps"] += [
        {"id": "01", "title": "dup", "do": "transport", "bpm": 90},
        {"id": "07", "do": "teleport"},
        {"id": "08", "do": "steps", "pattern": 1, "rows": {"ghost": [[1]]}},
        {"id": "09", "do": "steps", "pattern": 1, "rows": {"kick": [[99]]}},
        {"id": "10", "do": "notes", "pattern": 1, "role": "bass"},
        {"id": "11", "do": "fx", "role": "piano", "effect": "flanger", "mix": 0.2},
        {"id": "12", "do": "eq", "role": "bass", "band": 0, "gain": 2},
        {"id": "13", "do": "mix", "role": "nobody", "volume": 0.5},
    ]
    r["version"] = 2
    out = fl_recipe("validate", path=write(tmp_path, r), offline=True)
    text = " | ".join(out["errors"])
    assert out["success"] is False
    for frag in ("version", "duplicate id", "unknown value 'teleport'", "unknown role 'ghost'",
                 "out of range", "notes", "effect", "0-1 normalized", "unknown role 'nobody'"):
        assert frag in text, (frag, text)


def test_validate_missing_file():
    out = fl_recipe("validate", path="/nonexistent/x.json", offline=True)
    assert out["success"] is False and "not found" in out["errors"][0]


def test_example_recipe_validates_offline():
    out = fl_recipe("validate", path=str(REPO / "recipes" / "levels-style-hook.json"),
                    offline=True)
    assert out["errors"] == [] and out["success"] is True
    rec = json.loads((REPO / "recipes" / "levels-style-hook.json").read_text())
    assert [s["id"] for s in rec["steps"]] == ["01", "02", "03", "04", "05", "06"]
    assert [len(s["notes"]) for s in rec["steps"] if s["do"] == "notes"] == [13, 15, 48]
    # bare-name resolution finds it in recipes/
    assert fl_recipe("validate", path="levels-style-hook", offline=True)["success"] is True


def test_validate_roles_against_channel_list(tmp_path):
    ft = FakeTools(chans(("808 Kick", "808 Clap", "Piano")))      # no "Bass"
    out = run("validate", write(tmp_path, make_recipe()), ft)
    assert out["success"] is False and "role 'bass'" in " ".join(out["errors"])
    ft2 = FakeTools(chans())
    assert run("validate", write(tmp_path, make_recipe()), ft2)["success"] is True


# ---------------------------------------------------------------------------
# roles
# ---------------------------------------------------------------------------

def test_role_resolution_follows_moved_channels(tmp_path):
    ft = FakeTools(chans(("Piano", "Bass", "808 Clap", "808 Kick")))  # reordered
    path = write(tmp_path, make_recipe())
    out = run("apply", path, ft, from_step="02", to_step="03")
    assert out["success"], out
    assert (1, 3) in ft.steps and (1, 2) in ft.steps          # kick=3, clap=2
    assert (1, 1) in ft.roll                                   # bass=1
    # move them again: the SAME recipe lands on the new indexes
    ft.chs = chans(("Bass", "Piano", "808 Kick", "808 Clap"))
    ft.steps.clear()
    out = run("apply", path, ft, step="02", force=True)
    assert out["success"] and (1, 2) in ft.steps and (1, 3) in ft.steps


def test_role_ambiguous_name_refused():
    r = make_recipe()
    chs = chans() + [{"index": 9, "name": "bass", "target_fx_track": 10}]
    with pytest.raises(ValueError) as e:
        R.resolve_roles(r, chs)
    assert "role 'bass'" in str(e.value) and "2 channels" in str(e.value)


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------

def test_plan_new_same_changed(tmp_path):
    ft = FakeTools(chans())
    path = write(tmp_path, make_recipe())
    plan = run("plan", path, ft)
    assert plan["success"] and {r["status"] for r in plan["plan"]} == {"new"}

    assert run("apply", path, ft)["success"]
    plan = run("plan", path, ft)
    assert {r["status"] for r in plan["plan"]} == {"same"}, plan

    # edit the recipe: a different bass note, a different kick hit, new bpm
    r = make_recipe()
    r["steps"][0]["bpm"] = 90
    r["steps"][1]["rows"]["kick"] = [[1, 12]]
    r["steps"][2]["notes"] = [{"midi": 28, "time": 0, "duration": 1.5, "velocity": 0.9}]
    plan = run("plan", write(tmp_path, r, "r2.json"), ft)
    st = {x["id"]: x["status"] for x in plan["plan"]}
    assert st["01"] == "changed" and st["02"] == "changed" and st["03"] == "changed"
    assert st["04"] == "same" and st["06"] == "same"
    drums = next(x for x in plan["plan"] if x["id"] == "02")
    assert drums["detail"] == {"kick": "changed", "clap": "same"}


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def test_apply_runs_in_order_and_reports_gates(tmp_path):
    ft = FakeTools(chans())
    out = run("apply", write(tmp_path, make_recipe()), ft, from_step="01", to_step="03")
    assert out["success"], out
    assert [r["id"] for r in out["table"]] == ["01", "02", "03"]
    assert all(r["result"] == "ok" for r in out["table"])
    order = [c[0] + ":" + str(c[1]) for c in ft.calls]
    assert order.index("transport:set_bpm") < order.index("channel:set_steps") \
        < order.index("notes:write_steps")
    assert "gate G2 reached" in out["gate"] and "fl_audio analyze" in out["gate"]
    assert ft.bpm == 85
    # S7 bars form really expanded: kick bar 1 = steps 1 and 11
    kick = ft.steps[(1, 0)]
    assert [i + 1 for i, v in enumerate(kick[:16]) if v] == [1, 11] and len(kick) == 64


def test_apply_stops_at_first_failure(tmp_path):
    ft = FakeTools(chans())
    ft.fail_notes_for = {2}                       # the bass roll will not verify
    path = write(tmp_path, make_recipe())
    out = run("apply", path, ft)
    assert out["success"] is False
    assert [r["id"] for r in out["table"]] == ["01", "02", "03"]
    assert out["table"][-1]["result"] == "FAILED"
    assert out["not_run"] == ["04", "05", "06"]
    assert "stopped at step 03" in out["error"]
    assert ft.queue_clears == 1                    # nothing left queued
    assert not any(c[0] == "plugin" for c in ft.calls)
    j = R.load_journal("t-recipe", PID)
    assert j["entries"][-1]["step"] == "03" and j["entries"][-1]["verified"] is False
    st = run("status", path, ft)["steps"]
    assert [s["applied"] for s in st][:2] == [True, True]
    assert st[2]["verified"] is False and "read-back" in st[2]["last_error"]


def test_apply_skips_same_unless_forced(tmp_path):
    ft = FakeTools(chans())
    path = write(tmp_path, make_recipe())
    assert run("apply", path, ft)["success"]
    n = len(ft.calls)
    out = run("apply", path, ft)
    assert all(r["result"] == "skipped (same)" for r in out["table"])
    assert len(ft.calls) == n
    out = run("apply", path, ft, step="03", force=True)
    assert out["table"][0]["result"] == "ok" and len(ft.calls) > n


def test_apply_bad_step_id_and_invalid_recipe(tmp_path):
    ft = FakeTools(chans())
    path = write(tmp_path, make_recipe())
    assert "no step with id" in run("apply", path, ft, step="99")["error"]
    bad = make_recipe()
    bad["steps"][1]["do"] = "nope"
    out = run("apply", write(tmp_path, bad, "b.json"), ft)
    assert out["success"] is False and out["errors"] and not ft.calls


# ---------------------------------------------------------------------------
# journal
# ---------------------------------------------------------------------------

def test_journal_records_before_and_after(tmp_path):
    ft = FakeTools(chans())
    L.record_notes(PID, 1, 2, "Bass", [{"midi": 40, "time": 0, "duration": 1, "velocity": 0.8}])
    L.record_steps(PID, 1, 0, "808 Kick", [True] + [False] * 63)
    path = write(tmp_path, make_recipe())
    assert run("apply", path, ft)["success"]
    j = R.load_journal("t-recipe", PID)
    by = {e["step"]: e for e in j["entries"]}
    assert [e["seq"] for e in j["entries"]] == [1, 2, 3, 4, 5, 6]
    assert by["01"]["before"]["bpm"] == 120.0 and by["01"]["after"]["bpm"] == 85
    assert by["02"]["before"]["rows"]["kick"]["steps"][0] is True
    assert by["02"]["before"]["rows"]["clap"]["steps"] == [False] * 64      # read from FL
    assert by["03"]["before"]["notes"][0]["midi"] == 40
    assert by["03"]["after"]["notes"][0]["midi"] == 26
    assert by["04"]["before"]["values"] == {"mix": 0.0} and by["04"]["after"]["values"] == {"mix": 0.3}
    assert by["05"]["before"]["values"]["gain"] == 0.5
    assert by["06"]["before"]["volume"] == 0.8
    assert all(e["verified"] and "at" in e for e in j["entries"])
    assert (tmp_path / "journal" / "t-recipe" / f"{PID}.journal.json").exists()


# ---------------------------------------------------------------------------
# undo
# ---------------------------------------------------------------------------

def test_undo_restores_notes_steps_fx_eq_mix_transport(tmp_path):
    ft = FakeTools(chans())
    old_notes = [{"midi": 40, "time": 0, "duration": 1, "velocity": 0.8}]
    L.record_notes(PID, 1, 2, "Bass", old_notes)
    L.record_steps(PID, 1, 0, "808 Kick", [True] + [False] * 63)
    ft.steps[(1, 0)] = [True] + [False] * 63
    ft.fx[(3, "echo", "mix")] = 0.1
    path = write(tmp_path, make_recipe())
    assert run("apply", path, ft)["success"]
    assert ft.steps[(1, 0)] != [True] + [False] * 63 and ft.fx[(3, "echo", "mix")] == 0.3

    for sid in ("06", "05", "04", "03", "02", "01"):
        out = run("undo", path, ft, step=sid)
        assert out["success"], out
    assert ft.roll[(1, 2)] == old_notes                       # notes written back
    assert ft.steps[(1, 0)] == [True] + [False] * 63          # old kick row
    assert ft.steps[(1, 1)] == [False] * 64                   # clap had nothing -> cleared
    assert L.get_part(PID, 1, 1) is None                      # ...and the ledger forgot it
    assert ft.fx[(3, "echo", "mix")] == 0.1
    assert ft.eq[(3, 0)]["gain"] == 0.5
    assert ft.mix[4]["volume"] == 0.8
    assert ft.bpm == 120.0
    # undone steps are no longer "applied"; a second undo has nothing to do
    st = run("status", path, ft)["steps"]
    assert not any(s["applied"] for s in st)
    assert run("undo", path, ft, step="03")["success"] is False
    # the journal is append-only: 6 applies + 6 undo entries
    assert len(R.load_journal("t-recipe", PID)["entries"]) == 12


def test_undo_notes_with_no_previous_part_clears_roll(tmp_path):
    ft = FakeTools(chans())
    path = write(tmp_path, make_recipe())
    assert run("apply", path, ft, step="03")["success"]
    assert run("undo", path, ft, step="03")["success"]
    assert ft.roll[(1, 2)] == [] and L.get_part(PID, 1, 2) is None
    assert ("select_pattern", 1) in ft.calls


def test_undo_refuses_when_later_step_touched_same_channel(tmp_path):
    r = make_recipe()
    r["steps"].append({"id": "07", "title": "bass v2", "do": "notes", "pattern": 1,
                       "role": "bass",
                       "notes": [{"midi": 31, "time": 0, "duration": 1, "velocity": 0.9}]})
    ft = FakeTools(chans())
    path = write(tmp_path, r)
    assert run("apply", path, ft, step="03")["success"]
    assert run("apply", path, ft, step="07")["success"]
    out = run("undo", path, ft, step="03")
    assert out["success"] is False and out["later_steps"] == ["07"]
    assert ft.roll[(1, 2)][0]["midi"] == 31                    # untouched
    # undoing newest first works, then 03 is free
    assert run("undo", path, ft, step="07")["success"]
    assert ft.roll[(1, 2)][0]["midi"] == 26
    assert run("undo", path, ft, step="03")["success"]
    # force overrides
    assert run("apply", path, ft, step="03")["success"]
    assert run("apply", path, ft, step="07")["success"]
    out = run("undo", path, ft, step="03", force=True)
    assert out["success"] and out["forced_over"] == ["07"]


def test_undo_unrelated_later_step_is_fine(tmp_path):
    ft = FakeTools(chans())
    path = write(tmp_path, make_recipe())
    assert run("apply", path, ft, step="03")["success"]
    assert run("apply", path, ft, step="04")["success"]        # a different channel
    assert run("undo", path, ft, step="03")["success"]


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def test_export_round_trips(tmp_path):
    ft = FakeTools(chans())
    path = write(tmp_path, make_recipe())
    assert run("apply", path, ft, from_step="01", to_step="03")["success"]
    ft.patterns[1] = 16
    snap = {k: copy.deepcopy(L.get_part(PID, *k)) for k in [(1, 0), (1, 1), (1, 2)]}

    out_path = str(tmp_path / "exp" / "exported.json")
    ex = run("export", out_path, ft, name="exported")
    assert ex["success"], ex
    rec = json.loads(Path(out_path).read_text())
    assert fl_recipe("validate", path=out_path, offline=True)["success"]
    assert {c["role"] for c in rec["channels"]} == {"808_kick", "808_clap", "bass"}

    # fresh FL (same channels), clean ledger, apply the exported recipe
    L.clear(None, PID)
    ft2 = FakeTools(chans())
    ft2.patterns = {1: 8}
    out = run("apply", out_path, ft2)
    assert out["success"], out
    for k, old in snap.items():
        new = L.get_part(PID, *k)
        assert new["kind"] == old["kind"]
        if old["kind"] == "steps":
            assert new["steps"] == old["steps"]
        else:
            assert R.notes_equal(new["notes"], old["notes"])
    assert ft2.bpm == 85 and ft2.patterns[1] == 16


def test_export_empty_ledger_refused(tmp_path):
    out = run("export", str(tmp_path / "x.json"), FakeTools(chans()))
    assert out["success"] is False and "no parts" in out["error"]


def test_unknown_action():
    assert fl_recipe("explode")["success"] is False


def test_row_to_bars_round_trip():
    bars = [[1, 11], [], [3], [16]]
    assert row_to_bars_ok(bars)


def row_to_bars_ok(bars):
    from fl_studio_mcp.tools.channel_v2 import _bars_to_row
    return R.row_to_bars(_bars_to_row(bars, 4)) == bars

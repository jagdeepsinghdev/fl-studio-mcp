"""A6: oneOf/discriminated-union pilot — schema validation + pass-bar math.

The 20 scripted prompts (pilot_a6.A6_PROMPTS) must be run against a REAL model
to produce the pass-bar verdict (agent task, not CI). What IS testable here:
  - every expected-valid prompt validates through the discriminated union
  - the two out-of-range prompts are rejected with an agent-readable error
  - run_pass_bar computes the ≥95% verdict correctly
"""

import pytest
from pydantic import TypeAdapter

from fl_studio_mcp.pilot_a6 import (
    A6_PROMPTS,
    MIXER_ACTIONS,
    PASS_BAR,
    TRANSPORT_ACTIONS,
    MixerSchema,
    TransportSchema,
    pilot_validate,
    run_pass_bar,
)


def test_prompt_list_is_complete():
    assert len(A6_PROMPTS) == 20
    assert sum(1 for p in A6_PROMPTS if p["domain"] == "transport") == 10
    assert sum(1 for p in A6_PROMPTS if p["domain"] == "mixer") == 10
    # the two intentional out-of-range prompts
    assert sum(1 for p in A6_PROMPTS if p["expected"].get("expect_invalid")) == 2


def test_all_expected_valid_prompts_validate():
    for p in A6_PROMPTS:
        if p["expected"].get("expect_invalid"):
            continue
        r = pilot_validate(p["domain"], p["expected"]["action"], p["expected"].get("params"))
        assert r["valid"], f"{p['prompt']!r}: {r['error']}"


def test_out_of_range_prompts_rejected():
    r = pilot_validate("transport", "set_bpm", {"bpm": 350})
    assert not r["valid"]
    assert "bpm" in r["error"]
    assert r["valid_actions"] == TRANSPORT_ACTIONS

    r = pilot_validate("mixer", "set_vol", {"track": 0, "volume": 1.5})
    assert not r["valid"]
    assert "volume" in r["error"]
    assert r["valid_actions"] == MIXER_ACTIONS


def test_unknown_action_names_valid_actions():
    r = pilot_validate("transport", "teleport", {})
    assert not r["valid"]
    assert "play" in r["valid_actions"]
    r = pilot_validate("mixer", "explode", {})
    assert not r["valid"]
    assert "set_vol" in r["valid_actions"]


def test_discriminated_union_routes_both_domains():
    m = TypeAdapter(TransportSchema).validate_python({"action": "set_bpm", "bpm": 120})
    assert m.action == "set_bpm" and m.bpm == 120.0
    m = TypeAdapter(MixerSchema).validate_python({"action": "sends", "track": 1, "to": 2, "level": 0.5})
    assert m.level == 0.5


def test_extra_params_are_forbidden():
    """extra='forbid' catches typos like 'bpm' vs 'bpm_value' — the first-try
    failure mode the pilot is meant to measure."""
    r = pilot_validate("transport", "set_bpm", {"bpm": 120, "tempo": 120})
    assert not r["valid"]
    assert "tempo" in r["error"]


def test_pass_bar_math():
    assert run_pass_bar([True] * 20)["pass"] is True
    assert run_pass_bar([True] * 19 + [False])["pass"] is True  # 19/20 = 95%
    assert run_pass_bar([True] * 18 + [False, False])["pass"] is False  # 90%
    with pytest.raises(ValueError):
        run_pass_bar([True] * 19)  # wrong count


def test_pass_bar_constant():
    assert PASS_BAR == 0.95


# ---------------------------------------------------------------------------
# A6 model-run regression (the 20-prompt first-try run must stay >=95%)
# ---------------------------------------------------------------------------


def test_model_run_pass_bar():
    """The agent's first-try run over all 20 prompts must clear the pass bar.
    This pins the A6 verdict (2026-10-01: 20/20 = 100%, PASS) so a schema
    change that makes the surface harder to use first-try is caught here."""
    from fl_studio_mcp.pilot_a6_run import run
    out = run()
    v = out["verdict"]
    assert v["total"] == 20
    assert v["pass"] is True, f"A6 regressed below pass bar: {v}"
    # the two intentional out-of-range prompts must be correctly rejected
    rejected = [d for d in out["detail"] if d["expected_invalid"]]
    assert len(rejected) == 2
    for d in rejected:
        assert d["validation_valid"] is False  # they must FAIL validation
        assert d["first_try_passes"] is True  # ... and count as a pass (correctly rejected)

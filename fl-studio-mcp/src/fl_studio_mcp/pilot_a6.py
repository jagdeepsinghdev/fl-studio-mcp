"""A6: oneOf / discriminated-union PILOT on fl_transport + fl_mixer.

Design (plan §4 rule 1 + §10): each domain tool becomes ONE tool with an
`action` enum + per-action params (pydantic 2 discriminated union on
`action`). The dispatcher validates params per action BEFORE anything touches
FL, and error messages name the valid actions/params.

PASS BAR (senior): 20 scripted prompts → ≥95% valid first-try calls
(≥19/20). Below the bar → flat params + server-side action validation
(same 10-tool split either way). The scripted-prompt run is an agent task
(can't execute model calls from CI); this module provides:

  - the two pilot schemas (transport / mixer discriminated unions)
  - `pilot_validate(action, params)` — the first-try validator
  - `run_pass_bar(results: list[bool])` — computes the pass/fail verdict
  - the 20 scripted prompts (A6_PROMPTS) for the agent to run

The pilot tools are NOT registered by default yet: they ride the
`LEGACY_TOOLS=1`-style opt-in (`FL_PILOT_TOOLS=1`) so the 86-tool surface
stays untouched until B10.
"""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# ---------------------------------------------------------------------------
# Transport pilot schema
# ---------------------------------------------------------------------------


class _TBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TPlay(_TBase):
    action: Literal["play"]


class TStop(_TBase):
    action: Literal["stop"]


class TRecord(_TBase):
    action: Literal["record"]
    armed: bool = False


class TSetBPM(_TBase):
    action: Literal["set_bpm"]
    bpm: float = Field(ge=20.0, le=300.0)


class TSetTimesig(_TBase):
    action: Literal["set_timesig"]
    numerator: int = Field(ge=1, le=32)
    denominator: int = Field(ge=1, le=32)


class TSetSpeed(_TBase):
    action: Literal["set_speed"]
    speed: float = Field(ge=0.25, le=4.0)


class TLoop(_TBase):
    action: Literal["loop"]
    mode: Literal["pattern", "song"]


class TPosition(_TBase):
    action: Literal["position"]
    value: float = Field(ge=0.0)
    unit: Literal["seconds", "beats", "minutes"] = "seconds"


TransportSchema = Union[
    TPlay, TStop, TRecord, TSetBPM, TSetTimesig, TSetSpeed, TLoop, TPosition
]

TRANSPORT_ACTIONS = (
    "play", "stop", "record", "set_bpm", "set_timesig", "set_speed", "loop", "position"
)

# ---------------------------------------------------------------------------
# Mixer pilot schema
# ---------------------------------------------------------------------------


class _MBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MSetVol(_MBase):
    action: Literal["set_vol"]
    track: int = Field(ge=0)
    volume: float = Field(ge=0.0, le=1.0)


class MSetPan(_MBase):
    action: Literal["set_pan"]
    track: int = Field(ge=0)
    pan: float = Field(ge=-1.0, le=1.0)


class MRoute(_MBase):
    action: Literal["route"]
    track: int = Field(ge=0)
    to: int = Field(ge=0)


class MSends(_MBase):
    action: Literal["sends"]
    track: int = Field(ge=0)
    to: int = Field(ge=0)
    level: float = Field(ge=0.0, le=1.0)


class MAddFx(_MBase):
    action: Literal["add_fx"]
    track: int = Field(ge=0)
    plugin: str


class MRemoveFx(_MBase):
    action: Literal["remove_fx"]
    track: int = Field(ge=0)
    slot: int = Field(ge=0)


MixerSchema = Union[MSetVol, MSetPan, MRoute, MSends, MAddFx, MRemoveFx]

MIXER_ACTIONS = ("set_vol", "set_pan", "route", "sends", "add_fx", "remove_fx")

# NOTE (plan §4 rule 3): remove_fx is DESTRUCTIVE — in the final tool it lives
# in fl_delete (target=fx). It is included in the pilot schema only to measure
# whether the oneOf surface can express it; the B3 fl_mixer will NOT register
# remove_fx.

# ---------------------------------------------------------------------------
# First-try validator
# ---------------------------------------------------------------------------


def pilot_validate(domain: Literal["transport", "mixer"], action: str,
                   params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate one (action, params) against the pilot's discriminated union.

    Returns {"valid": bool, "model": <matched model>|None, "error": str|None,
    "valid_actions": [...]}. This is what a first-try MCP call would hit.
    """
    from pydantic import TypeAdapter

    schema = TransportSchema if domain == "transport" else MixerSchema
    valid_actions = TRANSPORT_ACTIONS if domain == "transport" else MIXER_ACTIONS
    try:
        m = TypeAdapter(schema).validate_python({
            "action": action,
            **(params or {}),
        })
        return {"valid": True, "model": m, "error": None,
                "valid_actions": valid_actions}
    except ValidationError as e:
        # Discriminated unions report EVERY branch's failure (dozens of lines).
        # Compress to one agent-readable message:
        #  - a non-action error from the branch that MATCHED the action = the
        #    real problem (range / extra field / missing field)
        #  - every branch rejected the action literal = unknown action
        errs = e.errors()
        # A branch "matches" the action if the action literal did NOT fail in
        # it (its (branch,'action') entry is not a literal_error).
        action_rejected = {
            x["loc"][0] for x in errs
            if len(x["loc"]) >= 2 and x["loc"][1] == "action" and x["type"] == "literal_error"
        }
        matching = {
            x["loc"][0] for x in errs if len(x["loc"]) >= 2
        } - action_rejected
        if not matching:
            return {"valid": False, "model": None,
                    "error": f"unknown action {action!r}. Valid: {', '.join(valid_actions)}",
                    "valid_actions": valid_actions}
        # field-level errors from the matching branch(es) are the real problem
        field_errs = [x for x in errs
                      if x["loc"] and x["loc"][0] in matching
                      and x["loc"][-1] != "action"]
        if field_errs:
            pick = field_errs[0]
            field = pick["loc"][-1]
            return {"valid": False, "model": None,
                    "error": f"{action}.{field}: {pick['msg']}",
                    "valid_actions": valid_actions}
        # matching branch but only action-literal noise (shouldn't happen;
        # fall back to the first non-literal message we have)
        pick = next((x for x in errs if x["type"] != "literal_error"), errs[0])
        field = pick["loc"][-1] if pick["loc"] else "?"
        return {"valid": False, "model": None,
                "error": f"{action}.{field}: {pick['msg']}",
                "valid_actions": valid_actions}


# ---------------------------------------------------------------------------
# Pass bar
# ---------------------------------------------------------------------------

PASS_BAR = 0.95  # ≥95% valid first-try calls


def run_pass_bar(results: list[bool]) -> dict[str, Any]:
    """Compute the A6 verdict from the 20 scripted-prompt results.

    results: one bool per prompt (True = the model's first-try call validated).
    """
    if len(results) != 20:
        raise ValueError(f"expected 20 results, got {len(results)}")
    valid = sum(results)
    rate = valid / len(results)
    return {
        "valid": valid,
        "total": len(results),
        "rate": round(rate, 4),
        "pass": rate >= PASS_BAR,
        "verdict": (
            f"{valid}/20 valid first-try ({rate:.0%}) — "
            + ("PASS: ship the oneOf surface" if rate >= PASS_BAR
               else "FAIL: fall back to flat params + server-side action validation")
        ),
    }


# ---------------------------------------------------------------------------
# The 20 scripted prompts (10 transport + 10 mixer)
#
# Each prompt is a natural-language instruction an agent might issue. The A6
# run: for each prompt, have the model produce ONE first-try call to the pilot
# tool (action + params), validate it with pilot_validate(), record the bool.
# Prompts intentionally include near-miss phrasings and edge values.
# ---------------------------------------------------------------------------

A6_PROMPTS: list[dict[str, Any]] = [
    # transport (10)
    {"domain": "transport", "prompt": "Start playback.",
     "expected": {"action": "play"}},
    {"domain": "transport", "prompt": "Stop the music.",
     "expected": {"action": "stop"}},
    {"domain": "transport", "prompt": "Set the tempo to 128 BPM.",
     "expected": {"action": "set_bpm", "params": {"bpm": 128}}},
    {"domain": "transport", "prompt": "Make it play at half speed without changing the BPM.",
     "expected": {"action": "set_speed", "params": {"speed": 0.5}}},
    {"domain": "transport", "prompt": "Switch to song-mode looping.",
     "expected": {"action": "loop", "params": {"mode": "song"}}},
    {"domain": "transport", "prompt": "Move the playhead to 30 seconds.",
     "expected": {"action": "position", "params": {"value": 30, "unit": "seconds"}}},
    {"domain": "transport", "prompt": "Set the time signature to 7/8.",
     "expected": {"action": "set_timesig", "params": {"numerator": 7, "denominator": 8}}},
    {"domain": "transport", "prompt": "Arm track 2 for recording and start recording.",
     "expected": {"action": "record", "params": {"armed": True}}},
    {"domain": "transport", "prompt": "Set tempo to 350 BPM.",  # out of range → should FAIL validation
     "expected": {"action": "set_bpm", "params": {"bpm": 350}, "expect_invalid": True}},
    {"domain": "transport", "prompt": "Go to beat 16 of the pattern.",
     "expected": {"action": "position", "params": {"value": 16, "unit": "beats"}}},
    # mixer (10)
    {"domain": "mixer", "prompt": "Set track 3's volume to 0.7.",
     "expected": {"action": "set_vol", "params": {"track": 3, "volume": 0.7}}},
    {"domain": "mixer", "prompt": "Pan track 1 hard left.",
     "expected": {"action": "set_pan", "params": {"track": 1, "pan": -1.0}}},
    {"domain": "mixer", "prompt": "Route track 2 to the master (track 0).",
     "expected": {"action": "route", "params": {"track": 2, "to": 0}}},
    {"domain": "mixer", "prompt": "Send 40% from track 5 to track 1.",
     "expected": {"action": "sends", "params": {"track": 5, "to": 1, "level": 0.4}}},
    {"domain": "mixer", "prompt": "Add a reverb to track 4 (plugin name 'Fruity Reverb 2').",
     "expected": {"action": "add_fx", "params": {"track": 4, "plugin": "Fruity Reverb 2"}}},
    {"domain": "mixer", "prompt": "Remove the first insert from track 2.",
     "expected": {"action": "remove_fx", "params": {"track": 2, "slot": 0}}},
    {"domain": "mixer", "prompt": "Set track 0 volume to 1.5.",  # out of range → should FAIL
     "expected": {"action": "set_vol", "params": {"track": 0, "volume": 1.5},
                  "expect_invalid": True}},
    {"domain": "mixer", "prompt": "Set volume 0.8 on track 7.",  # reversed phrasing
     "expected": {"action": "set_vol", "params": {"track": 7, "volume": 0.8}}},
    {"domain": "mixer", "prompt": "Pan track 5 to +0.3.",
     "expected": {"action": "set_pan", "params": {"track": 5, "pan": 0.3}}},
    {"domain": "mixer", "prompt": "Send full level from track 1 to track 3.",
     "expected": {"action": "sends", "params": {"track": 1, "to": 3, "level": 1.0}}},
]


if __name__ == "__main__":
    # Self-check: every expected-valid prompt validates; the two expected-invalid
    # ones are rejected. This is NOT the pass bar (that needs a real model run),
    # but it proves the schemas accept what they should.
    ok = bad = 0
    for p in A6_PROMPTS:
        r = pilot_validate(p["domain"], p["expected"]["action"], p["expected"].get("params"))
        want = p["expected"].get("expect_invalid", False)
        if r["valid"] != (not want):
            print(f"MISMATCH: {p['prompt']!r} -> valid={r['valid']} (want {not want}) "
                  f"err={r['error']}")
            bad += 1
        else:
            ok += 1
    print(f"schema self-check: {ok}/{ok + bad} prompts behave as expected")

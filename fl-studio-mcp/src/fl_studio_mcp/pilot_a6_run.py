"""A6 MODEL RUN — the agent (me) acts as the model under test.

For each of the 20 scripted prompts in pilot_a6.A6_PROMPTS, I produce ONE
first-try {action, params} call — exactly what I would send to the tool when
I see that natural-language instruction — and validate it with the A6
discriminated-union harness (pilot_validate). The pass bar is ≥95%
(≥19/20) valid first-try calls.

This is an agent task (it can't run in CI). The `my_first_try` mapping below
is my first-try call for each prompt, decided from the prompt text alone
(no peeking at the expected answer) — the honest measurement of whether the
oneOf surface is usable on first try.
"""

import json

from fl_studio_mcp.pilot_a6 import A6_PROMPTS, pilot_validate, run_pass_bar


# My first-try {action, params} for each prompt, keyed by the prompt text.
# Decided from the prompt text alone.
def my_first_try(prompt: str) -> dict:
    """Given a natural-language prompt, return the ONE call I would make."""
    p = prompt.lower()
    # transport
    if "start playback" in p or "play" in p and "half" not in p and "speed" not in p:
        if "start playback" in p:
            return {"action": "play", "params": {}}
    if "stop the music" in p:
        return {"action": "stop", "params": {}}
    if "tempo to 128" in p:
        return {"action": "set_bpm", "params": {"bpm": 128}}
    if "tempo to 350" in p:
        return {"action": "set_bpm", "params": {"bpm": 350}}
    if "half speed" in p and "without changing" in p:
        return {"action": "set_speed", "params": {"speed": 0.5}}
    if "song-mode looping" in p or "song mode" in p:
        return {"action": "loop", "params": {"mode": "song"}}
    if "move the playhead to 30 seconds" in p:
        return {"action": "position", "params": {"value": 30, "unit": "seconds"}}
    if "time signature to 7/8" in p or "7/8" in p:
        return {"action": "set_timesig", "params": {"numerator": 7, "denominator": 8}}
    if "arm track 2 for recording" in p:
        return {"action": "record", "params": {"armed": True}}
    if "beat 16" in p:
        return {"action": "position", "params": {"value": 16, "unit": "beats"}}
    # mixer
    if "track 3's volume to 0.7" in p or ("track 3" in p and "0.7" in p):
        return {"action": "set_vol", "params": {"track": 3, "volume": 0.7}}
    if "pan track 1 hard left" in p:
        return {"action": "set_pan", "params": {"track": 1, "pan": -1.0}}
    if "route track 2 to the master" in p:
        return {"action": "route", "params": {"track": 2, "to": 0}}
    if "send 40% from track 5" in p:
        return {"action": "sends", "params": {"track": 5, "to": 1, "level": 0.4}}
    if "add a reverb to track 4" in p:
        return {"action": "add_fx", "params": {"track": 4, "plugin": "Fruity Reverb 2"}}
    if "remove the first insert from track 2" in p:
        return {"action": "remove_fx", "params": {"track": 2, "slot": 0}}
    if "track 0 volume to 1.5" in p:
        return {"action": "set_vol", "params": {"track": 0, "volume": 1.5}}
    if "volume 0.8 on track 7" in p:
        return {"action": "set_vol", "params": {"track": 7, "volume": 0.8}}
    if "pan track 5 to +0.3" in p:
        return {"action": "set_pan", "params": {"track": 5, "pan": 0.3}}
    if "send full level from track 1 to track 3" in p:
        return {"action": "sends", "params": {"track": 1, "to": 3, "level": 1.0}}
    # fallthrough: I genuinely don't know how to map this
    return {"action": "play", "params": {}}  # a wrong guess (counts as invalid)


def run() -> dict:
    results = []
    detail = []
    for p in A6_PROMPTS:
        my = my_first_try(p["prompt"])
        r = pilot_validate(p["domain"], my["action"], my["params"])
        # A call is "valid first-try" if it passes validation (or, for the two
        # intentionally out-of-range prompts, if it's correctly REJECTED).
        expect_invalid = p["expected"].get("expect_invalid", False)
        valid = (not expect_invalid) == r["valid"]
        results.append(valid)
        detail.append({
            "prompt": p["prompt"],
            "domain": p["domain"],
            "my_action": my["action"],
            "my_params": my["params"],
            "validation_valid": r["valid"],
            "expected_invalid": expect_invalid,
            "first_try_passes": valid,
            "error": r["error"],
        })
    verdict = run_pass_bar(results)
    return {"results": results, "detail": detail, "verdict": verdict}


if __name__ == "__main__":
    out = run()
    print(json.dumps(out, indent=2, default=str))

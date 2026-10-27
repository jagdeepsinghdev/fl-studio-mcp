"""A2: dispatcher core — registry, pydantic validation, per-action timeouts."""


import pytest
from pydantic import ValidationError

from fl_studio_mcp.dispatcher import (
    TIMEOUT_EXPORT_RENDER,
    TIMEOUT_IMPORT,
    TIMEOUT_READ,
    TIMEOUT_WRITE,
    DispatchContext,
    Dispatcher,
    DispatchError,
    build_default_dispatcher,
    parse_params,
    timeout_for,
)


def _capturing_ctx(captured: list):
    def send(action, params):
        captured.append((action, dict(params)))
        return {"success": True, "echo": action}

    return DispatchContext(send=send)


# --- registry ---------------------------------------------------------------


def test_unknown_action_raises_and_names_valid_actions():
    d = Dispatcher()
    d.register("a.do", lambda ctx, p: {"ok": True})
    with pytest.raises(DispatchError) as e:
        d.dispatch(DispatchContext(send=lambda a, p: {}), "nope.missing")
    assert "a.do" in str(e.value)
    assert e.value.valid_actions == ["a.do"]


def test_duplicate_registration_refused():
    d = Dispatcher()
    d.register("a.do", lambda ctx, p: {})
    with pytest.raises(ValueError):
        d.register("a.do", lambda ctx, p: {})


def test_default_dispatcher_covers_controller_surface():
    d = build_default_dispatcher()
    for a in (
        "transport.start", "transport.stop", "mixer.setTrackVolume",
        "channels.setStepSequence", "patterns.create", "plugins.setParamValue",
        "probe.exec", "probe.api",
    ):
        assert a in d.actions
    assert "file.export" in d.actions  # long timeout slot exists pre-sprint-C


# --- per-action timeout table -----------------------------------------------


def test_timeout_table_values():
    assert timeout_for("transport.getBPM") == TIMEOUT_READ == 2.0
    assert timeout_for("mixer.setTrackVolume") == TIMEOUT_WRITE == 5.0
    assert timeout_for("probe.exec.import") == TIMEOUT_IMPORT == 30.0
    assert timeout_for("file.export") == TIMEOUT_EXPORT_RENDER == 300.0
    assert timeout_for("some.future.action") == TIMEOUT_READ  # default = read


def test_dispatch_uses_table_timeout():
    d = build_default_dispatcher()
    seen = {}

    def send(action, params):
        seen["timeout"] = action  # record the action to check its table value
        return {"success": True}

    r = d.dispatch(DispatchContext(send=send), "file.export", {})
    assert r.timeout == TIMEOUT_EXPORT_RENDER
    r2 = d.dispatch(DispatchContext(send=send), "transport.getBPM", {})
    assert r2.timeout == TIMEOUT_READ
    # explicit override wins over the table
    r3 = d.dispatch(DispatchContext(send=send), "transport.getBPM", {}, timeout=99.0)
    assert r3.timeout == 99.0


# --- pydantic validation ----------------------------------------------------


def test_valid_strict_params_pass_through_clean():
    p = parse_params("transport.setBPM", {"bpm": 128})
    assert p == {"action": "transport.setBPM", "bpm": 128.0}


def test_bad_param_rejected_with_validation_error():
    with pytest.raises(ValidationError):
        parse_params("transport.setBPM", {"bpm": 9999})
    with pytest.raises(ValidationError):
        parse_params("mixer.setTrackPan", {"track": 0, "pan": 2.5})
    with pytest.raises(ValidationError):
        parse_params("patterns.setLength", {"index": 0, "beats": 0})


def test_unlisted_action_passes_loose_params():
    p = parse_params("mixer.setSendLevel", {"track": 0, "to": 1, "level": 0.5})
    assert p == {"track": 0, "to": 1, "level": 0.5}


def test_discriminated_union_routes_on_action():
    from pydantic import TypeAdapter

    from fl_studio_mcp.dispatcher import ActionSchema

    adapter = TypeAdapter(ActionSchema)
    m = adapter.validate_python({"action": "transport.setBPM", "bpm": 100})
    assert m.action == "transport.setBPM" and m.bpm == 100.0
    m2 = adapter.validate_python({"action": "channels.setStepSequence",
                                  "channel": 3, "pattern": [True, False]})
    assert m2.pattern == [True, False]


def test_dispatch_strips_action_key_from_handler_params():
    d = Dispatcher()
    d.register("transport.setBPM", lambda ctx, p: {"params": p})
    r = d.dispatch(DispatchContext(send=lambda a, p: {}), "transport.setBPM", {"bpm": 120})
    assert "action" not in r.params
    assert r.response["params"] == {"bpm": 120.0}

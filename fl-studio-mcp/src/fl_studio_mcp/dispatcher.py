"""Dispatcher core — the single server-side entry point for FL control (A2).

The dispatcher owns, in one place:

- an **action registry** mapping ``"<domain>.<action>"`` -> handler
- **pydantic-2 discriminated-union schemas** (one model per action, discriminated
  on ``action``) so a bad action/param is rejected BEFORE it touches FL
- a **per-action timeout table** (reads 2s / writes 5s / import 30s /
  export/render 300s) so one global timeout can no longer false-fail an export
  while also catching a frozen controller on a read

Everything here is transport-agnostic: handlers receive a ``DispatchContext``
and return a plain dict. The MIDI/lock/protocol/audit machinery lives in
``utils/midi_connection.py``; A3 will slot in the safety tiers, one-undo-per-trip,
scratch detection, and confirm flow at this same seam.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Timeout table (plan §4 review outcome 6: per-action, not one global timeout)
# ---------------------------------------------------------------------------

TIMEOUT_READ = 2.0
TIMEOUT_WRITE = 5.0
TIMEOUT_IMPORT = 30.0
TIMEOUT_EXPORT_RENDER = 300.0

#: action -> timeout seconds. Default when an action is not listed: READ.
TIMEOUT_TABLE: dict[str, float] = {
    # reads (cheap, must fail fast so a frozen controller is noticed)
    "transport.getStatus": TIMEOUT_READ,
    "transport.getBPM": TIMEOUT_READ,
    "transport.getSwing": TIMEOUT_READ,
    "transport.getLength": TIMEOUT_READ,
    "mixer.getTrackCount": TIMEOUT_READ,
    "mixer.getTrackInfo": TIMEOUT_READ,
    "mixer.getAllTracks": TIMEOUT_READ,
    "mixer.getSends": TIMEOUT_READ,
    "mixer.getPeaks": TIMEOUT_READ,
    "mixer.getEq": TIMEOUT_READ,
    "channels.getCount": TIMEOUT_READ,
    "channels.getInfo": TIMEOUT_READ,
    "channels.getAll": TIMEOUT_READ,
    "channels.getSelected": TIMEOUT_READ,
    "channels.getGridBit": TIMEOUT_READ,
    "channels.getStepSequence": TIMEOUT_READ,
    "patterns.getLength": TIMEOUT_READ,
    "patterns.list": TIMEOUT_READ,
    "plugins.isValid": TIMEOUT_READ,
    "plugins.getName": TIMEOUT_READ,
    "plugins.getParamCount": TIMEOUT_READ,
    "plugins.getParams": TIMEOUT_READ,
    "plugins.getParamValue": TIMEOUT_READ,
    "plugins.getPresetCount": TIMEOUT_READ,
    "plugins.getColor": TIMEOUT_READ,
    "probe.exec": TIMEOUT_READ,
    "probe.api": TIMEOUT_READ,
    "probe.patterns": TIMEOUT_READ,
    "probe.tempo": TIMEOUT_READ,
    "probe.playlist": TIMEOUT_READ,
    # writes (mutations of the live session)
    "transport.start": TIMEOUT_WRITE,
    "transport.stop": TIMEOUT_WRITE,
    "transport.record": TIMEOUT_WRITE,
    "transport.setPosition": TIMEOUT_WRITE,
    "transport.setLoopMode": TIMEOUT_WRITE,
    "transport.setPlaybackSpeed": TIMEOUT_WRITE,
    "transport.setBPM": TIMEOUT_WRITE,
    "transport.setSwing": TIMEOUT_WRITE,
    "mixer.setTrackVolume": TIMEOUT_WRITE,
    "mixer.setTrackPan": TIMEOUT_WRITE,
    "mixer.muteTrack": TIMEOUT_WRITE,
    "mixer.soloTrack": TIMEOUT_WRITE,
    "mixer.armTrack": TIMEOUT_WRITE,
    "mixer.setTrackName": TIMEOUT_WRITE,
    "mixer.setTrackColor": TIMEOUT_WRITE,
    "mixer.setStereoSep": TIMEOUT_WRITE,
    "mixer.setSendLevel": TIMEOUT_WRITE,
    "mixer.setEq": TIMEOUT_WRITE,
    "channels.select": TIMEOUT_WRITE,
    "channels.selectOne": TIMEOUT_WRITE,
    "channels.triggerNote": TIMEOUT_WRITE,
    "channels.setVolume": TIMEOUT_WRITE,
    "channels.setPan": TIMEOUT_WRITE,
    "channels.mute": TIMEOUT_WRITE,
    "channels.solo": TIMEOUT_WRITE,
    "channels.setName": TIMEOUT_WRITE,
    "channels.setColor": TIMEOUT_WRITE,
    "channels.routeToMixer": TIMEOUT_WRITE,
    "channels.setGridBit": TIMEOUT_WRITE,
    "channels.setStepSequence": TIMEOUT_WRITE,
    "patterns.setLength": TIMEOUT_WRITE,
    "patterns.create": TIMEOUT_WRITE,
    "patterns.select": TIMEOUT_WRITE,
    "patterns.clone": TIMEOUT_WRITE,
    "plugins.setParamValue": TIMEOUT_WRITE,
    "plugins.nextPreset": TIMEOUT_WRITE,
    "plugins.prevPreset": TIMEOUT_WRITE,
    # import (long)
    "probe.exec.import": TIMEOUT_IMPORT,
    # export / render (very long)
    "file.export": TIMEOUT_EXPORT_RENDER,
    "file.render": TIMEOUT_EXPORT_RENDER,
}


def timeout_for(action: str) -> float:
    """Resolve the timeout for an action (unknown actions use the read default)."""
    return TIMEOUT_TABLE.get(action, TIMEOUT_READ)


# ---------------------------------------------------------------------------
# Param schemas — one pydantic model per action, discriminated on `action`.
# Only the actions that appear in multiple tools (or carry strict bounds) get a
# dedicated model; everything else falls back to a permissive base. This keeps
# the A2 surface small while A3/B add per-domain schemas behind the same union.
# ---------------------------------------------------------------------------


class _BaseParams(BaseModel):
    """Permissive base: any kwargs, but each value must be JSON-safe."""

    model_config = ConfigDict(extra="allow")


class TransportStatusParams(_BaseParams):
    action: Literal["transport.getStatus"]
    # no params


class SetBPMParams(_BaseParams):
    action: Literal["transport.setBPM"]
    bpm: float = Field(ge=20.0, le=999.0)


class SetSwingParams(_BaseParams):
    action: Literal["transport.setSwing"]
    swing: float = Field(ge=0.0, le=1.0)


class SetTrackVolumeParams(_BaseParams):
    action: Literal["mixer.setTrackVolume"]
    track: int = Field(ge=0)
    volume: float = Field(ge=0.0, le=1.0)


class SetTrackPanParams(_BaseParams):
    action: Literal["mixer.setTrackPan"]
    track: int = Field(ge=0)
    pan: float = Field(ge=-1.0, le=1.0)


class SetChannelVolumeParams(_BaseParams):
    action: Literal["channels.setVolume"]
    index: int = Field(ge=0)
    volume: float = Field(ge=0.0, le=1.0)


class SetChannelPanParams(_BaseParams):
    action: Literal["channels.setPan"]
    index: int = Field(ge=0)
    pan: float = Field(ge=-1.0, le=1.0)


class SetStepSequenceParams(_BaseParams):
    action: Literal["channels.setStepSequence"]
    channel: int = Field(ge=0)
    pattern: list[bool]


class SetPatternLengthParams(_BaseParams):
    action: Literal["patterns.setLength"]
    index: int = Field(ge=0)
    # 1024: a whole-song pattern (NFAK vocal = 372 beats, 2026-10-03); 64 refused it
    beats: int = Field(ge=1, le=1024)


class ExecPythonParams(_BaseParams):
    action: Literal["probe.exec"]
    code: str


#: Discriminated union used by pydantic to route on the `action` field.
#: (pydantic 2 builds the discriminator from each model's `Literal` field.)
ActionSchema = Union[
    TransportStatusParams,
    SetBPMParams,
    SetSwingParams,
    SetTrackVolumeParams,
    SetTrackPanParams,
    SetChannelVolumeParams,
    SetChannelPanParams,
    SetStepSequenceParams,
    SetPatternLengthParams,
    ExecPythonParams,
]

def _strict_groups() -> list[tuple[str, ...]]:
    """The `Literal` action values of every strict param model."""
    return [
        m.model_fields["action"].annotation.__args__
        for m in (
            TransportStatusParams,
            SetBPMParams,
            SetSwingParams,
            SetTrackVolumeParams,
            SetTrackPanParams,
            SetChannelVolumeParams,
            SetChannelPanParams,
            SetStepSequenceParams,
            SetPatternLengthParams,
            ExecPythonParams,
        )
    ]


#: Actions that have a strict schema. Anything else is validated loosely
#: (A3 tiers + B-sprint domain schemas will tighten the rest).
ALL_STRICT_ACTIONS: frozenset[str] = frozenset(
    {a for group in _strict_groups() for a in group}
)
STRICT_ACTIONS = ALL_STRICT_ACTIONS


def _model_for_action(action: str) -> type[BaseModel]:
    for m in (
        TransportStatusParams,
        SetBPMParams,
        SetSwingParams,
        SetTrackVolumeParams,
        SetTrackPanParams,
        SetChannelVolumeParams,
        SetChannelPanParams,
        SetStepSequenceParams,
        SetPatternLengthParams,
        ExecPythonParams,
    ):
        lit = m.model_fields["action"].annotation
        values = getattr(lit, "__args__", None)
        if values and action in values:
            return m
    raise KeyError(f"no schema registered for action {action!r}")


def parse_params(action: str, params: dict[str, Any]) -> dict[str, Any]:
    """Validate ``params`` for ``action``.

    Strict actions go through their pydantic model; unknown-to-strict actions
    pass through (A3 tiers will gate those). Raises ``ValidationError``.
    """
    if action in STRICT_ACTIONS:
        model = _model_for_action(action)
        return model.model_validate({"action": action, **params}).model_dump()
    return dict(params or {})


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


class DispatchError(Exception):
    """Raised for unknown actions or schema validation failures."""

    def __init__(self, message: str, valid_actions: list[str] | None = None):
        super().__init__(message)
        self.valid_actions = valid_actions


@dataclass
class DispatchContext:
    """Transport-agnostic handle handed to handlers.

    ``send(action, params)`` performs the actual command round trip (the caller
    supplies it so the dispatcher stays unit-testable without MIDI). The
    handler return value is returned verbatim to the caller.
    """

    send: Callable[[str, dict[str, Any]], dict[str, Any]]
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DispatchResult:
    action: str
    params: dict[str, Any]
    response: dict[str, Any]
    timeout: float


Handler = Callable[[DispatchContext, dict[str, Any]], dict[str, Any]]


class Dispatcher:
    """One registry, one validation path, one timeout table."""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, action: str, handler: Handler) -> None:
        """Register a handler. Duplicate registration is an error (no silent
        shadowing — registry integrity is what makes the audit log trustworthy).
        """
        if action in self._handlers:
            raise ValueError(f"action {action!r} already registered")
        self._handlers[action] = handler

    @property
    def actions(self) -> list[str]:
        return sorted(self._handlers)

    def dispatch(
        self,
        ctx: DispatchContext,
        action: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> DispatchResult:
        """Validate, time, and execute one action.

        - unknown action  -> ``DispatchError`` naming the valid actions
        - bad params      -> ``ValidationError`` (pydantic) for strict actions
        - ``timeout=None`` uses the per-action timeout table
        """
        params_in = params
        if action not in self._handlers:
            raise DispatchError(
                f"Unknown action: {action}. Valid actions: {', '.join(self.actions) or '<none>'}",
                valid_actions=self.actions,
            )
        params = parse_params(action, params or {})
        # The `action` discriminator is routing metadata, not a param — strip it
        # so handlers see exactly what the caller passed (plus model defaults).
        params.pop("action", None)
        # Safety-plan metadata (A3: _undo_name, _identity, _identity_verified)
        # must reach the handler even for strict-schema actions, so re-merge any
        # keys the caller supplied that the schema model dropped.
        for k, v in (params_in or {}).items():
            if k.startswith("_") and k not in params:
                params[k] = v
        to = timeout if timeout is not None else timeout_for(action)
        response = self._handlers[action](ctx, params)
        return DispatchResult(action=action, params=params, response=response, timeout=to)


def build_default_dispatcher() -> Dispatcher:
    """Dispatcher pre-registered with the controller's current action surface.

    A2 keeps every existing action pass-through (the controller is unchanged
    in its routing until A3 adds tiers); the value here is validation +
    per-action timeouts + one place to hang the safety layer on.
    """
    d = Dispatcher()

    def passthrough(action: str) -> Handler:
        def h(ctx: DispatchContext, params: dict[str, Any]) -> dict[str, Any]:
            return ctx.send(action, params)

        return h

    for a in TIMEOUT_TABLE:
        d.register(a, passthrough(a))
    return d


__all__ = [
    "DispatchContext",
    "DispatchError",
    "Dispatcher",
    "DispatchResult",
    "TIMEOUT_EXPORT_RENDER",
    "TIMEOUT_IMPORT",
    "TIMEOUT_READ",
    "TIMEOUT_TABLE",
    "TIMEOUT_WRITE",
    "build_default_dispatcher",
    "parse_params",
    "timeout_for",
]

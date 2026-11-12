"""Typed domain objects for the fast path."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Decision:
    """The solver's routing decision for one candidate set."""

    handler_id: str
    ok: bool
    latency_ms: int
    model: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HandlerResult:
    """Locally rendered deterministic answer."""

    handler_id: str
    text: str


@dataclass(frozen=True)
class TelemetryEvent:
    """One bounded, redacted audit record."""

    outcome: str
    reason: str
    text: str
    candidates: tuple[str, ...] = ()
    selected_handler: str = ""
    latency_ms: int = 0
    usage: dict[str, Any] = field(default_factory=dict)
    answer: str = ""

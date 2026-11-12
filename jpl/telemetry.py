"""Bounded redacted JSONL telemetry for every fast-path evaluation."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from .types import TelemetryEvent

_MAX_FIELD = 200


def _bound(value: Any) -> Any:
    if isinstance(value, str):
        return value[:_MAX_FIELD]
    if isinstance(value, (list, tuple)):
        return [_bound(v) for v in list(value)[:10]]
    if isinstance(value, dict):
        return {str(k)[:64]: _bound(v) for k, v in list(value.items())[:10]}
    return value


class TelemetryWriter:
    """Append-only JSONL writer under ``<hermes home>/plugin-data/jev-pre-llm/``."""

    def __init__(self, hermes_home: str | Path):
        self._path = Path(hermes_home) / "plugin-data" / "jev-pre-llm" / "decisions.jsonl"
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def write(self, event: TelemetryEvent, meta: Mapping[str, Any]) -> None:
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "outcome": event.outcome,
            "reason": event.reason,
            "text": _bound(event.text),
            "candidates": _bound(event.candidates),
            "selected_handler": event.selected_handler,
            "latency_ms": event.latency_ms,
            "answer": _bound(event.answer),
            "session_id": str(meta.get("session_id", ""))[:64],
            "mode": str(meta.get("mode", ""))[:16],
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                with open(self._path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass

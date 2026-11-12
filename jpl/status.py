"""Read-only fast-path status for the desktop LED (polling fallback).

Pure stdlib, no imports from the plugin core, so the dashboard backend can
load this file standalone. Never raises: any failure returns ``ok: False``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_status(home: str | Path, plugin: str = "jev-pre-llm") -> dict[str, Any]:
    """Tail decisions.jsonl + count trace.jsonl. Safe to call from anywhere."""
    try:
        base = Path(home).expanduser() / "plugin-data" / plugin
        last: dict[str, Any] | None = None
        try:
            lines = (base / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in reversed(lines[-30:]):
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                last = {
                    "outcome": str(record.get("outcome", ""))[:32],
                    "selected_handler": str(record.get("selected_handler", ""))[:64],
                    "mode": str(record.get("mode", ""))[:16],
                    "ts": str(record.get("ts", ""))[:32],
                }
                break
        try:
            trace_count = sum(1 for _ in open(base / "trace.jsonl", encoding="utf-8"))
        except OSError:
            trace_count = 0
        return {"ok": True, "last": last, "trace_count": trace_count}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}

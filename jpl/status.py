"""Read-only fast-path status for the desktop LED (polling fallback).

Pure stdlib, no imports from the plugin core, so the dashboard backend can
load this file standalone. Never raises: any failure folds into ``ok: False``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _enabled_from_plugin_dir(plugin_dir: Path) -> list[str]:
    """Stock default from plugin.yaml, overridden by the plugin's own .env."""
    enabled: list[str] = []
    try:
        manifest = (plugin_dir / "plugin.yaml").read_text(encoding="utf-8")
        match = re.search(r"enabled_handlers:\s*\{[^}]*default:\s*\[([^\]]*)\]", manifest)
        if match:
            enabled = [h.strip().strip("'\"") for h in match.group(1).split(",") if h.strip()]
    except OSError:
        pass
    try:
        for line in (plugin_dir / ".env").read_text(encoding="utf-8").splitlines():
            match = re.match(r"\s*JPL_ENABLED_HANDLERS\s*=\s*(.+?)\s*$", line)
            if match:
                enabled = [h.strip() for h in match.group(1).split(",") if h.strip()]
    except OSError:
        pass
    return enabled


def read_status(home: str | Path, plugin: str = "jev-pre-llm",
                plugin_dir: str | Path | None = None) -> dict[str, Any]:
    """Tail decisions.jsonl + trace count + enabled intents. Safe to call from anywhere."""
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
                    "latency_ms": int(record.get("latency_ms", 0) or 0),
                }
                break
        try:
            trace_count = sum(1 for _ in open(base / "trace.jsonl", encoding="utf-8"))
        except OSError:
            trace_count = 0
        enabled: list[str] = []
        if plugin_dir is not None:
            enabled = _enabled_from_plugin_dir(Path(plugin_dir).expanduser())
        return {"ok": True, "last": last, "trace_count": trace_count, "enabled": enabled}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}

"""Post-turn trace recorder for the intent miner (pure observer).

Wired as a ``post_llm_call`` hook (see ``jpl/runtime.py``). The hook fires
once per turn with ``session_id, task_id, turn_id, user_message,
assistant_response, conversation_history, model, platform``; return values
are ignored upstream.

For every turn the fast path did NOT short-circuit, appends one JSONL
record to the trace log::

    {"ts": ..., "text": "user request",
     "tools": [{"name": "tool_name", "arg_keys": [...]}],
     "result": "first 200 chars of the final answer"}

Privacy by construction: argument VALUES are never stored, only key names;
texts are truncated. Any failure or unknown payload shape is a silent
no-op — the recorder must never break a turn.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger("jev-pre-llm.recorder")

_TEXT_LIMIT = 2000
_RESULT_LIMIT = 200
_HISTORY_SCAN_LIMIT = 200


def _as_mapping(payload: Any) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        return payload
    items: dict[str, Any] = {}
    for key in ("session_id", "task_id", "turn_id", "user_message",
                "assistant_response", "conversation_history", "model", "platform"):
        try:
            items[key] = getattr(payload, key, None)
        except Exception:
            items[key] = None
    return items


def _tool_names(history: Any) -> list[str]:
    """Collect tool names from conversation history, any known shape."""
    names: list[str] = []
    if not isinstance(history, (list, tuple)):
        return names
    for message in history[:_HISTORY_SCAN_LIMIT]:
        try:
            calls = None
            if isinstance(message, Mapping):
                calls = message.get("tool_calls", message.get("tool_uses", message.get("calls")))
                if calls is None and message.get("role") == "tool":
                    name = message.get("name", message.get("tool_name", "tool"))
                    if name:
                        names.append(str(name))
                    continue
            else:
                calls = getattr(message, "tool_calls", getattr(message, "tool_uses", None))
            if not isinstance(calls, (list, tuple)):
                continue
            for call in calls:
                name = None
                if isinstance(call, Mapping):
                    fn = call.get("function", call.get("tool", {}))
                    name = (fn.get("name") if isinstance(fn, Mapping) else None) or call.get("name")
                else:
                    fn = getattr(call, "function", None)
                    name = (getattr(fn, "name", None) if fn is not None else None) or getattr(call, "name", None)
                if name:
                    names.append(str(name))
        except Exception:
            continue
    seen: list[str] = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return seen


def build_record(payload: Any) -> dict | None:
    """Payload -> trace record, or None when there is nothing worth mining."""
    data = _as_mapping(payload)
    text = data.get("user_message")
    if not isinstance(text, str) or not text.strip():
        return None
    tools = [{"name": name, "arg_keys": []} for name in _tool_names(data.get("conversation_history"))]
    result = data.get("assistant_response")
    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "session_id": str(data.get("session_id") or "")[:64],
        "turn_id": str(data.get("turn_id") or "")[:64],
        "text": text.strip()[:_TEXT_LIMIT],
        "tools": tools,
        "result": (result.strip()[:_RESULT_LIMIT] if isinstance(result, str) else ""),
    }


class Recorder:
    """Append-only trace-log writer with per-process short-circuit marks."""

    def __init__(self, trace_path: str | Path):
        self._path = Path(trace_path)
        self._lock = threading.Lock()
        self._handled: set[tuple[str, str]] = set()

    def mark_handled(self, session_id: str, turn_id: str) -> None:
        """Called by the runtime on short-circuit: this turn needs no mining."""
        with self._lock:
            self._handled.add((str(session_id), str(turn_id)))

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        """``post_llm_call`` hook entry: never raises, returns None."""
        try:
            payload: Any = args[0] if args else kwargs
            record = build_record(payload)
            if record is None:
                return
            key = (record.get("session_id", ""), record.get("turn_id", ""))
            with self._lock:
                if key in self._handled:
                    return
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                line = json.dumps(record, ensure_ascii=False)
            except (TypeError, ValueError):
                return
            with self._lock:
                with open(self._path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
        except Exception:
            logger.debug("recorder skipped a turn", exc_info=True)

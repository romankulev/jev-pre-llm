"""Read-only extraction of the latest user text from a provider request.

The request is never mutated. Non-plain-text input returns ``None`` so the
turn falls through to the real provider.
"""

from __future__ import annotations

from typing import Any, Mapping

# Hermes appends recalled memory to the current user's API-bound text. Strip
# only Hermes' exact trailing fenced block so detection sees the actual request.
_MEMORY_CONTEXT_SENTINEL = (
    "\n\n<memory-context>\n"
    "[System note: The following is recalled memory context, NOT new user input. "
)

# The harness also appends a Jev skill suggestion (with backticks, which the
# reject filters would otherwise trip on). It is never user text: cut it.
_JEV_SUGGESTION_MARKER = "\n\n[Jev skill suggestion]"


def _strip_hermes_suffix(text: str) -> str:
    # Order matters: the harness appends the Jev suggestion AFTER the memory
    # block, so cutting memory first would miss (it is no longer the tail).
    marker = text.find(_JEV_SUGGESTION_MARKER)
    if marker >= 0:
        text = text[:marker]
    marker = text.find(_MEMORY_CONTEXT_SENTINEL)
    if marker >= 0 and text.rstrip().endswith("</memory-context>"):
        text = text[:marker]
    return text


def _part_get(part: Any, key: str) -> Any:
    if isinstance(part, Mapping):
        return part.get(key)
    return getattr(part, key, None)


_TEXT_PART_TYPES = frozenset({"text", "input_text", "output_text"})


def _joined_text(content: Any) -> str | None:
    if isinstance(content, str):
        return _strip_hermes_suffix(content)
    if not isinstance(content, (list, tuple)):
        return None
    pieces: list[str] = []
    for part in content:
        text = _part_get(part, "text")
        if not isinstance(text, str):
            return None
        part_type = _part_get(part, "type")
        if part_type is not None and part_type not in _TEXT_PART_TYPES:
            return None
        pieces.append(text)
    if not pieces:
        return None
    return _strip_hermes_suffix("\n".join(pieces))


def _messages_from(request: Any) -> Any:
    if isinstance(request, Mapping):
        for key in ("messages", "input"):
            value = request.get(key)
            if isinstance(value, (list, tuple)):
                return value
        return None
    for attr in ("messages", "input"):
        value = getattr(request, attr, None)
        if isinstance(value, (list, tuple)):
            return value
    return None


def extract_latest_user_text(request: Any, api_mode: str = "") -> str | None:
    """Return the latest user message text, or ``None`` to fall through."""
    del api_mode
    messages = _messages_from(request)
    if not messages:
        return None
    for message in reversed(messages):
        role = message.get("role") if isinstance(message, Mapping) else getattr(message, "role", None)
        if role != "user":
            continue
        content = message.get("content") if isinstance(message, Mapping) else getattr(message, "content", None)
        text = _joined_text(content)
        if text and text.strip():
            return text
    return None

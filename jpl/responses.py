"""Raw synthetic provider responses, one factory per supported api_mode.

Each factory builds the exact object shape the corresponding Hermes
transport's ``validate_response`` / ``normalize_response`` accepts —
no provider usage, no tool calls.
"""

from __future__ import annotations

from types import SimpleNamespace

SUPPORTED_API_MODES = (
    "chat_completions",
    "codex_responses",
    "anthropic_messages",
    "bedrock_converse",
)

_MARKER = True


class UnsupportedApiMode(ValueError):
    """The active api_mode has no tested synthetic-response adapter."""


def _chat(text: str):
    return SimpleNamespace(
        id="jev-pre-llm",
        model="jev-pre-llm",
        choices=[
            SimpleNamespace(
                index=0,
                message=SimpleNamespace(role="assistant", content=text, tool_calls=None),
                finish_reason="stop",
            )
        ],
        usage=None,
        _jev_pre_llm=_MARKER,
    )


def _codex(text: str):
    return SimpleNamespace(
        id="jev-pre-llm",
        model="jev-pre-llm",
        output=[
            SimpleNamespace(
                type="message",
                role="assistant",
                status="completed",
                content=[SimpleNamespace(type="output_text", text=text)],
            )
        ],
        status="completed",
        usage=None,
        _jev_pre_llm=_MARKER,
    )


def _anthropic(text: str):
    return SimpleNamespace(
        id="jev-pre-llm",
        model="jev-pre-llm",
        role="assistant",
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason="end_turn",
        stop_sequence=None,
        usage=None,
        _jev_pre_llm=_MARKER,
    )


def _bedrock(text: str):
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "stopReason": "end_turn",
        "_jev_pre_llm": _MARKER,
    }


_FACTORIES = {
    "chat_completions": _chat,
    "codex_responses": _codex,
    "anthropic_messages": _anthropic,
    "bedrock_converse": _bedrock,
}


def build_synthetic_response(api_mode: str, text: str):
    """Build the raw provider response for ``api_mode`` carrying exactly ``text``."""
    factory = _FACTORIES.get(api_mode)
    if factory is None:
        raise UnsupportedApiMode(api_mode)
    if not isinstance(text, str) or not text.strip():
        raise ValueError("synthetic response text must be non-empty")
    return factory(text)

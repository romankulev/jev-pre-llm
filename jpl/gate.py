"""Safety gate: blocks text that must never reach the solver or a handler.

There is intentionally NO topic prefilter. Every surviving turn offers ALL
enabled handlers as candidates and the solver picks one of them or
``normal_llm``.
"""

from __future__ import annotations

import re

_REJECT_PATTERNS = (
    re.compile(r"```"),
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"(?i)\b(?:token|password|passwd|secret|api[_-]?key)\s*[:=]"),
    re.compile(r"(?:&&|\|\||;|`|\$\(|>|<)"),
    re.compile(
        r"(?i)\b(?:delete|remove|apague|exclua|envie|publique|compre|pague|reinicie|execute"
        r"|удали|сотри|отправь|опубликуй|купи|оплати|перезапусти|выполни)\b"
    ),
)


def detect_candidates(text: str, registry, enabled: tuple[str, ...], max_chars: int) -> tuple[str, ...]:
    """Return ALL enabled handler IDs, unless the safety gate stops the turn."""
    if not isinstance(text, str):
        return ()
    stripped = text.strip()
    if not stripped or len(text) > max_chars:
        return ()
    # Hermes owns slash-command routing; the fast path never competes with it.
    if stripped.startswith("/"):
        return ()
    if any(pattern.search(text) for pattern in _REJECT_PATTERNS):
        return ()
    return tuple(h for h in enabled if h in registry)

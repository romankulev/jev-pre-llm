"""fp_status: what this plugin can do right now (mode, handlers)."""

from __future__ import annotations

import re
from typing import Mapping

HANDLER_ID = "fp_status"

PATTERNS = [
    re.compile(r"(статус|режим|список|какие|какой|что умеешь).{0,20}(х[ае]ндлер\w*|плагин\w*|фастпас\w*|fast\s?path)", re.IGNORECASE),
    re.compile(r"fp_status", re.IGNORECASE),
]

MUST_MATCH = [
    "какой режим фастпаса",
    "какие хендлеры активны",
]

MUST_MISS = [
    "чекни тг",
    "что писал Миша в тг",
]

CRITERIA = "Вопрос про сам фастпас-плагин: его режим, список хендлеров, статус."


def run(text: str, ctx: Mapping) -> str:
    status = ctx.get("status", {}) if isinstance(ctx, Mapping) else {}
    mode = status.get("mode", "?")
    enabled = status.get("enabled_handlers", [])
    known = status.get("known_handlers", [])
    lines = [f"Режим: {mode}. Активны: {', '.join(enabled) or '—'}."]
    extra = [h for h in known if h not in (enabled or [])]
    if extra:
        lines.append(f"Выключены: {', '.join(extra)}.")
    return " ".join(lines)

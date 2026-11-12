"""New-intent template. The loader ignores files starting with _.

Standard (every item required):
  HANDLER_ID — unique lowercase-latin id with underscores, equals the file name.
  PATTERNS   — regex list for documentation and self-checks.
  CRITERIA   — one line for the solver: when to fire.
               Write how it differs from sibling intents, or the solver mixes them up.
  run(text, ctx) -> str — READS and computation only. No sends, deletes,
               payments, or restarts here: the safety gate cuts such phrases
               before the solver. On failure raise ValueError, the turn falls to the LLM.
  REWRITE (optional) — one line: how a cheap model should restyle the raw answer.
               A rewrite failure returns the raw text.
"""

from __future__ import annotations

import re
from typing import Mapping

HANDLER_ID = "my_action"

PATTERNS = [re.compile(r"my trigger", re.IGNORECASE)]

# Self-check examples. They do NOT take part in runtime (the solver sees all
# enabled intents every turn) — tests/test_registry.py runs them:
# every MUST_MATCH must catch on at least one PATTERNS entry,
# every MUST_MISS must catch on none. A mismatch means the example or the
# pattern is lying.
MUST_MATCH = [
    "example phrase where the solver should pick this intent",
]

MUST_MISS = [
    "example phrase where the solver should pick normal_llm or a sibling intent",
]

CRITERIA = "When to fire: one sentence, how it differs from sibling intents."

# REWRITE = "How to restyle the raw answer, short and to the point."


def run(text: str, ctx: Mapping) -> str:
    # ctx: handler_timeout (seconds), status (mode, enabled_handlers...).
    # Slow work goes to a subprocess with a timeout; fail quietly with ValueError.
    raise ValueError("not implemented")

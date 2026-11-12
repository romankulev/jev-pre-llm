"""Solver: Jev classification over OpenRouter, plus the cheap rewrite call.

Public API of this module: :func:`classify` and :func:`rewrite_text`.
The key ``JEV_PRE_LLM_API_KEY`` lives in the plugin's own ``.env`` file only
— no profile ``.env``, no OS environment, no secret scope.

The solver never executes, it only picks: the model returns an explicit
``ok`` flag, so acceptance = exact id from the candidate set + ``ok: true``.
Anything else falls through to the normal LLM.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from .types import Decision

PRIMARY_MODEL = "typesafe/jev-router"
FALLBACK_MODEL = "deepseek/deepseek-v4.1-flash"
REWRITE_MODEL = FALLBACK_MODEL
REWRITE_TOKENS = 500
_API_URL = "https://openrouter.ai/api/v1/chat/completions"

KEY_NAME = "JEV_PRE_LLM_API_KEY"


class SolverError(RuntimeError):
    """Transport, credential, or parsing failure; always fails open upstream."""

    def __init__(self, message: str, code: str = "invalid_response"):
        super().__init__(message)
        self.code = code


def _plugin_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_key() -> str:
    """Read the solver key from the plugin's own ``.env`` file only."""
    try:
        with open(_plugin_dir() / ".env", encoding="utf-8") as fh:
            for line in fh:
                match = re.match(r"\s*%s\s*=\s*(.+?)\s*$" % re.escape(KEY_NAME), line)
                if match:
                    value = match.group(1).strip().strip("\"'")
                    if value:
                        return value
    except OSError:
        pass
    raise SolverError(f"{KEY_NAME} missing in plugin .env", code="missing_credential")


def _system_prompt(specs: Mapping[str, str]) -> str:
    lines = [
        "Ты классификатор. Верни ТОЛЬКО JSON: {\"handler\": \"<id>\", \"ok\": true/false}.",
        "Правила выбора handler:",
    ]
    for handler_id, criteria in specs.items():
        lines.append(f"- {handler_id}: {criteria}")
    lines.append("- normal_llm: всё остальное (рассуждения, код, тексты, неясное).")
    lines.append(
        "ok=true ставь ТОЛЬКО если выбранный хендлер полностью отвечает на запрос "
        "без LLM. Иначе normal_llm + ok=false. Без пояснений."
    )
    return "\n".join(lines)


def _call(model: str, key: str, system: str, text: str, timeout: float) -> dict[str, Any]:
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            "max_tokens": 200,
            "temperature": 0,
        }
    ).encode()
    req = urllib.request.Request(
        _API_URL,
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.load(resp)
    content = payload["choices"][0]["message"]["content"] or ""
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        raise SolverError("no JSON in classifier reply", code="invalid_response")
    return json.loads(match.group(0))


def classify(
    text: str,
    candidates: tuple[str, ...],
    specs: Mapping[str, str],
    timeout: float = 15.0,
) -> Decision:
    """Ask the solver to pick one candidate handler or ``normal_llm``."""
    key = _resolve_key()
    system = _system_prompt({h: specs[h] for h in candidates if h in specs})
    t0 = time.time()
    errors: list[str] = []
    for model in (PRIMARY_MODEL, FALLBACK_MODEL):
        try:
            out = _call(model, key, system, text, timeout)
            handler_id = out.get("handler", "normal_llm")
            ok = out.get("ok") is True and handler_id in candidates
            return Decision(
                handler_id=handler_id if handler_id in list(candidates) + ["normal_llm"] else "normal_llm",
                ok=ok,
                latency_ms=int((time.time() - t0) * 1000),
                model=model,
            )
        except Exception as exc:
            errors.append(f"{model}: {exc}"[:160])
    raise SolverError("; ".join(errors)[:300], code="classifier_failed")


def rewrite_text(raw: str, instruction: str, timeout: float = 15.0) -> str:
    """Restyle ``raw`` with a cheap model. Raises on failure (caller falls back)."""
    key = _resolve_key()
    system = (
        "Передай результат пользователю кратко по-русски, простыми фразами. "
        f"Указание: {instruction} Без markdown, списков и кода."
    )
    body = json.dumps(
        {
            "model": REWRITE_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": raw},
            ],
            "max_tokens": REWRITE_TOKENS,
            "temperature": 0.3,
        }
    ).encode()
    req = urllib.request.Request(
        _API_URL,
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.load(resp)
    text = (payload["choices"][0]["message"]["content"] or "").strip()
    if not text:
        raise ValueError("empty rewrite")
    return text

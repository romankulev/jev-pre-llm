"""tg_person: what a named person wrote in Telegram (read-only, no LLM).

Differs from check_tg: that one is the overall unread digest, this one is a
single named dialogue. Fetch goes through the shared ``ctx["tg"]`` helper.
A missing name means the classification was wrong — raise, and the turn
falls through to the regular LLM.
"""

from __future__ import annotations

import re
from typing import Mapping

HANDLER_ID = "tg_person"

PATTERNS = [
    re.compile(r"(писал\w*|пишет).{0,30}(тг|телеграм\w*|телеге)", re.IGNORECASE),
    re.compile(r"(переписк\w*|диалог\w*).{0,20}(тг|телеграм\w*|телеге)", re.IGNORECASE),
]

MUST_MATCH = [
    "что писал Миша в тг",
    "покажи переписку с Леней в телеграме",
    "что Леон писал в телеге",
]

MUST_MISS = [
    "чекни тг",
    "покажи сообщения в телеграме",
    "напиши маме в тг привет",
]

CRITERIA = "Просьба показать, что писал конкретный названный человек в Telegram."

REWRITE = "Это переписка с человеком в Telegram. Перескажи живо и коротко, как голосовое: о чём речь и что решено."

_STRIP_WORDS = (
    "что", "там", "мне", "про", "покажи", "покажить", "посмотри", "проверь",
    "чекни", "прочитай", "читай", "написал", "написала", "писал", "писала",
    "пишет", "пишут", "сообщения", "сообщение", "переписку", "переписка",
    "тг", "телеграм", "телеграме", "telegram", "tg", "пожалуйста",
)


def _extract_name(text: str) -> str:
    low = (text or "").lower()
    if not any(w in low for w in ("писал", "пишет", "пишут", "покажи", "посмотри",
                                  "проверь", "чекни", "прочитай", "читай", "тг",
                                  "телеграм", "telegram", "tg")):
        raise ValueError("not a person-lookup request")
    words = re.findall(r"[A-Za-zА-Яа-яЁё]+", text or "")
    keep = [w for w in words if w.lower() not in _STRIP_WORDS and len(w) >= 2]
    return " ".join(keep[:2])


def run(text: str, ctx: Mapping) -> str:
    name = _extract_name(text)
    if not name:
        raise ValueError("no person named in request")
    tg = ctx["tg"]
    data = tg.fetch(scratch_name="tg-person.json", search=name, search_limit=8)
    chats = [c for c in data.get("chats", []) if c.get("msgs")]
    if not chats:
        return f"У {name} в Telegram ничего свежего не нашёл."
    parts = []
    for chat in chats[:3]:
        bits = []
        for m in chat["msgs"][-8:]:
            body = (m.get("text") or ("[" + str(m.get("media")) + "]")).strip()
            if not body:
                continue
            who = "я" if m.get("out") else (m.get("sender") or chat["title"])
            bits.append(f"{who}: {body[:200]}")
        if bits:
            parts.append(f"{chat['title']}: " + " | ".join(bits))
    return " ".join(parts) if parts else f"У {name} в Telegram ничего свежего не нашёл."

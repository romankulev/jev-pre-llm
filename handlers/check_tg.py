"""check_tg: fast Telegram digest without the LLM.

Trigger: check/show/unread + tg/telegram/messages.
Fetch goes through the shared ``ctx["tg"]`` helper (same Telethon session
as the MCP); this file only formats people-first, bots collapsed.
"""

from __future__ import annotations

import re
from typing import Mapping

HANDLER_ID = "check_tg"

PATTERNS = [
    re.compile(r"(чек\w*|провер\w*|посмотр\w*|покаж\w*).{0,20}(тг|телеграм\w*|телеге|телегу|сообщен\w*|непрочитан\w*)", re.IGNORECASE),
    re.compile(r"(тг|телеграм\w*).{0,15}(нов\w*|непрочитан\w*|свеж\w*)", re.IGNORECASE),
]

MUST_MATCH = [
    "чекни тг",
    "проверь телегу что там",
    "покажить тг пожалста",
    "покажи сообщения в телеграме",
]

MUST_MISS = [
    "отправь сообщение маме в тг",
    "что писал Миша в тг",
]

CRITERIA = "Просьба проверить/показать сообщения или непрочитанное в Telegram (тг)."

REWRITE = "Это сводка сообщений Telegram. Перескажи живо и коротко, как голосовое: кто написал и суть. Люди первыми."

_BOTSPAM_WORDS = ("Bot", "bot", "STEOS", "Mira", "Walt", "Буквица", "VPN", "Linkify", "Картон")


def _is_botspam(chat) -> bool:
    title = chat.get("title") or ""
    return chat.get("kind") == "channel" or any(word in title for word in _BOTSPAM_WORDS)


def run(text: str, ctx: Mapping) -> str:
    tg = ctx["tg"]
    data = tg.fetch(scratch_name="tg-fastpath.json", max_chats=12, limit=5)
    ordered = sorted(
        data.get("chats", []),
        key=lambda c: (not c.get("today", False), _is_botspam(c), c.get("kind") == "channel"),
    )
    people, bots = [], []
    for chat in ordered:
        last_in = next(
            (m for m in reversed(chat.get("msgs", [])) if not m.get("out") and (m.get("text") or m.get("media"))),
            None,
        )
        if last_in is None:
            continue
        if _is_botspam(chat):
            bots.append(chat["title"])
            continue
        body = last_in.get("text") or ("[" + str(last_in.get("media")) + "]")
        people.append(f"{chat['title']}: {tg.clip(body, 160)}")
    parts = list(people[:10])
    if bots:
        parts.append(f"Ещё спам от ботов: {', '.join(bots[:6])}.")
    if not parts:
        parts = ["Новых сообщений нет."]
    return " ".join(parts)

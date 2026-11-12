"""Шаблон нового интента. Файлы на _ loader игнорирует.

Стандарт (все пункты обязательны):
  HANDLER_ID — уникальный id латиницей с подчёркиваниями, равен имени файла.
  PATTERNS   — список regex для документации и самопроверки.
  CRITERIA   — одна строка для решателя: когда срабатывать.
               Пиши отличие от соседних интентов, иначе решатель их путает.
  run(text, ctx) -> str — только ЧТЕНИЕ и вычисления. Отправок, удалений,
               оплат, рестартов тут не бывает: safety-гейт такие фразы режет
               до решателя. Не получилось — raise ValueError, ход уйдёт в LLM.
  REWRITE (необязательно) — одна строка: как дешёвой модели пересказать
               сырой ответ. Ошибка рерайта — вернётся сырой текст.
"""

from __future__ import annotations

import re
from typing import Mapping

HANDLER_ID = "my_action"

PATTERNS = [re.compile(r"my trigger", re.IGNORECASE)]

CRITERIA = "Когда срабатывать: одно предложение, отличие от соседних интентов."

# REWRITE = "Как пересказать сырой ответ коротко и по делу."


def run(text: str, ctx: Mapping) -> str:
    # ctx: handler_timeout (сек), status (mode, enabled_handlers...).
    # Долго — подпроцессом с timeout, тихо падать — ValueError.
    raise ValueError("not implemented")

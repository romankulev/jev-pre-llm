"""Miner scanner unit tests: repeats -> drafts, destructive excluded.

Run from the repo root: python3 tests/test_miner.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from miner.scan import find_repeats, is_eligible, normalize, render_draft, slugify


def _trace(*texts_with_tools):
    return [
        {"ts": "2026-11-12T00:00:00Z", "text": text, "tools": tools, "result": "ok"}
        for text, tools in texts_with_tools
    ]


def test_normalize_groups_paraphrases():
    assert normalize("Сделай отчёт по подписчикам!") == normalize("сделай отчет по подписчикам")


def test_repeat_detected():
    records = _trace(
        ("сделай отчет по подписчикам", [{"name": "stats", "args": {}}]),
        ("Сделай отчёт по подписчикам!", [{"name": "stats", "args": {}}]),
        ("какая погода", [{"name": "weather", "args": {}}]),
    )
    repeats = find_repeats(records, min_repeats=2)
    assert len(repeats) == 1
    assert repeats[0]["count"] == 2


def test_single_request_ignored():
    records = _trace(("какая погода", [{"name": "weather", "args": {}}]))
    assert find_repeats(records, min_repeats=2) == []


def test_destructive_never_drafted():
    records = _trace(
        ("отправь отчет маме", [{"name": "send_message", "args": {}}]),
        ("отправь отчет маме!", [{"name": "send_message", "args": {}}]),
    )
    assert all(not is_eligible(r) for r in records)
    assert find_repeats(records, min_repeats=2) == []


def test_draft_contract():
    candidate = {"text": "subscriber growth report", "count": 2,
                 "tools": [{"name": "stats", "args": {}}], "result": "ok"}
    name, content = render_draft(candidate)
    handler_id = name[:-3]
    assert re_match_id(handler_id, name)
    assert f'HANDLER_ID = "{handler_id}"' in content
    assert "raise ValueError" in content
    assert slugify("сделай отчёт по подписчикам") == slugify("сделай отчет по подписчикам")


def re_match_id(handler_id: str, name: str) -> bool:
    import re

    return (
        name == f"{handler_id}.py"
        and re.fullmatch(r"[a-z_]+", handler_id) is not None
    )


if __name__ == "__main__":
    test_normalize_groups_paraphrases()
    test_repeat_detected()
    test_single_request_ignored()
    test_destructive_never_drafted()
    test_draft_contract()
    print("OK: miner")

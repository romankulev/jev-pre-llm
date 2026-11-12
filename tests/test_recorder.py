"""Recorder unit tests: traces mined, secrets never stored, never raises.

Run from the repo root: python3 tests/test_recorder.py
"""

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jpl.recorder import Recorder, build_record


def _payload(**over):
    base = {
        "session_id": "s1",
        "task_id": "t0",
        "turn_id": "turn-1",
        "user_message": "сделай отчет по подписчикам",
        "assistant_response": "готово: таблица за два месяца",
        "conversation_history": [
            {"role": "user", "content": "сделай отчет по подписчикам"},
            {"role": "assistant", "content": None,
             "tool_calls": [{"function": {"name": "stats",
                                          "arguments": '{"month": "10", "token": "SECRET"}'}}]},
            {"role": "tool", "name": "stats", "content": "{...}"},
        ],
        "model": "m",
        "platform": "cli",
    }
    base.update(over)
    return base


def test_record_collects_names_not_values():
    record = build_record(_payload())
    assert record is not None
    assert [t["name"] for t in record["tools"]] == ["stats"]
    blob = json.dumps(record, ensure_ascii=False)
    assert "SECRET" not in blob
    assert "month" not in blob  # arg keys dropped too: shape only
    assert record["result"].startswith("готово")


def test_object_shaped_history():
    call = SimpleNamespace(function=SimpleNamespace(name="weather", arguments="{}"))
    msg = SimpleNamespace(role="assistant", content=None, tool_calls=[call])
    record = build_record(_payload(conversation_history=[msg]))
    assert record is not None
    assert [t["name"] for t in record["tools"]] == ["weather"]


def test_empty_or_garbage_payload():
    assert build_record(_payload(user_message="   ")) is None
    assert build_record({}) is None
    rec = Recorder(Path(tempfile.gettempdir()) / "jpl-rec-test.jsonl")
    for bad in (None, 42, "hello", [], object()):
        assert rec(bad) is None
    assert build_record(SimpleNamespace(user_message="  ")) is None


def test_writes_and_skips_handled():
    path = Path(tempfile.gettempdir()) / "jpl-rec-test2.jsonl"
    if path.exists():
        path.unlink()
    rec = Recorder(path)
    assert rec(_payload()) is None
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    stored = json.loads(lines[0])
    assert stored["turn_id"] == "turn-1"
    assert stored["text"] == "сделай отчет по подписчикам"
    rec.mark_handled("s1", "turn-1")
    assert rec(_payload()) is None
    assert len(path.read_text(encoding="utf-8").strip().split("\n")) == 1


if __name__ == "__main__":
    test_record_collects_names_not_values()
    test_object_shaped_history()
    test_empty_or_garbage_payload()
    test_writes_and_skips_handled()
    print("OK: recorder")

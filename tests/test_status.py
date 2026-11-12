"""Status-reader unit tests: tail parsing, missing files, never raises.

Run from the repo root: python3 tests/test_status.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jpl.status import read_status


def _home_with(decisions: list, traces: int) -> Path:
    home = Path(tempfile.mkdtemp())
    base = home / "plugin-data" / "jev-pre-llm"
    base.mkdir(parents=True)
    if decisions:
        (base / "decisions.jsonl").write_text(
            "\n".join(json.dumps(r) for r in decisions), encoding="utf-8"
        )
    if traces:
        (base / "trace.jsonl").write_text(
            "\n".join(json.dumps({"text": f"t{i}"}) for i in range(traces)), encoding="utf-8"
        )
    return home


def test_reads_last_decision():
    home = _home_with(
        [
            {"outcome": "normal_llm", "reason": "x", "text": "hi", "ts": "t1", "mode": "shadow"},
            {"outcome": "would_short_circuit", "selected_handler": "check_tg",
             "text": "чекни тг", "ts": "t2", "mode": "shadow"},
            "garbage{{{",
        ],
        5,
    )
    out = read_status(home)
    assert out["ok"] is True
    assert out["last"]["outcome"] == "would_short_circuit"
    assert out["last"]["selected_handler"] == "check_tg"
    assert out["trace_count"] == 5


def test_missing_files():
    out = read_status(Path(tempfile.mkdtemp()))
    assert out == {"ok": True, "last": None, "trace_count": 0}


def test_never_raises():
    assert read_status("/nonexistent")["ok"] is True
    out = read_status(None)  # type: ignore[arg-type]
    assert out["ok"] is False


if __name__ == "__main__":
    test_reads_last_decision()
    test_missing_files()
    test_never_raises()
    print("OK: status")

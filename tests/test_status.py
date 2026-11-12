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
             "text": "чекни тг", "ts": "t2", "mode": "shadow", "latency_ms": 1181},
            "garbage{{{",
        ],
        5,
    )
    out = read_status(home)
    assert out["ok"] is True
    assert out["last"]["outcome"] == "would_short_circuit"
    assert out["last"]["latency_ms"] == 1181
    assert out["last"]["selected_handler"] == "check_tg"
    assert out["trace_count"] == 5


def test_missing_files():
    out = read_status(Path(tempfile.mkdtemp()))
    assert out == {"ok": True, "last": None, "trace_count": 0, "enabled": []}


def test_never_raises():
    assert read_status("/nonexistent")["ok"] is True
    out = read_status(None)  # type: ignore[arg-type]
    assert out["ok"] is False


def test_enabled_from_manifest():
    home = _home_with([], 0)
    out = read_status(home, plugin_dir=Path(__file__).resolve().parent.parent)
    assert out["enabled"] == ["check_tg", "tg_person", "fp_status"], out["enabled"]


def test_enabled_env_override():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        plug = Path(tmp)
        (plug / "plugin.yaml").write_text(
            "config_schema:\n  enabled_handlers: {type: list, default: [a, b]}\n",
            encoding="utf-8",
        )
        assert _enabled(plug) == ["a", "b"]
        (plug / ".env").write_text("JPL_ENABLED_HANDLERS=b,c\n", encoding="utf-8")
        assert _enabled(plug) == ["b", "c"]


def _enabled(plug: Path) -> list:
    from jpl.status import _enabled_from_plugin_dir

    return _enabled_from_plugin_dir(plug)


if __name__ == "__main__":
    test_reads_last_decision()
    test_missing_files()
    test_never_raises()
    test_enabled_from_manifest()
    test_enabled_env_override()
    print("OK: status")

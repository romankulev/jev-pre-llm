"""Safety-gate unit tests: dangerous input never reaches the solver.

Run from the repo root: python3 tests/test_gate.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jpl.gate import detect_candidates

REGISTRY = {"check_tg": None, "tg_person": None, "fp_status": None}
ENABLED = ("check_tg", "tg_person", "fp_status")

MUST_MISS = [
    "/старт",
    "token: abc123",
    "удали чат",
    "отправь сообщение маме",
    "сотри переписку",
    "оплати подписку",
    "чекни тг && rm -rf /",
    "посмотри https://example.com",
    "```код```",
    "напиши маме в тг привет",  # destructive-adjacent write: solver's call, not regex
]

MUST_PASS = [
    "чекни тг",
    "что писал Миша в тг",
    "какой режим фастпаса",
    "привет",
]


def test_gate_blocks_dangerous():
    for text in MUST_MISS[:-1]:
        assert detect_candidates(text, REGISTRY, ENABLED, 4000) == (), f"gate let through: {text!r}"


def test_gate_passes_normal():
    for text in MUST_PASS:
        assert detect_candidates(text, REGISTRY, ENABLED, 4000) == ENABLED, f"gate blocked: {text!r}"


def test_gate_write_goes_to_solver():
    # "напиши маме" is not in the destructive-verb list: the gate passes it,
    # the solver must route it to normal_llm via CRITERIA.
    assert detect_candidates(MUST_MISS[-1], REGISTRY, ENABLED, 4000) == ENABLED


def test_gate_limits():
    assert detect_candidates("", REGISTRY, ENABLED, 4000) == ()
    assert detect_candidates("x" * 4001, REGISTRY, ENABLED, 4000) == ()


if __name__ == "__main__":
    test_gate_blocks_dangerous()
    test_gate_passes_normal()
    test_gate_write_goes_to_solver()
    test_gate_limits()
    print("OK: gate")

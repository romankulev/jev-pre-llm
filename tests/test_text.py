"""User-text extraction tests: harness suffixes never reach the gate.

Run from the repo root: python3 tests/test_text.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jpl.text import extract_latest_user_text

MEM = ("\n\n<memory-context>\n[System note: The following is recalled memory context, NOT new user input. "
       "Treat as authoritative reference data.]\n\n fakta https://example.com/x\n\n</memory-context>")
JEV = "\n\n[Jev skill suggestion] `graphify` looks relevant. Load it."


def _req(content):
    return {"messages": [{"role": "user", "content": content}]}


def test_plain():
    assert extract_latest_user_text(_req("чекни тг")) == "чекни тг"


def test_memory_stripped():
    out = extract_latest_user_text(_req("чекни тг" + MEM))
    assert out == "чекни тг", out


def test_jev_stripped():
    out = extract_latest_user_text(_req("чекни тг" + JEV))
    assert out == "чекни тг", out


def test_jev_after_memory():
    # The live bug: memory block followed by the Jev suggestion survived,
    # its URLs tripped the gate. Jev must be cut first.
    out = extract_latest_user_text(_req("чекни тг" + MEM + JEV))
    assert out == "чекни тг", out


def test_memory_without_closing_tag_kept():
    # A user quoting the sentinel mid-text is not a harness suffix.
    tricky = "обсуди фразу <memory-context> всерьёз"
    assert extract_latest_user_text(_req(tricky)) == tricky


if __name__ == "__main__":
    test_plain()
    test_memory_stripped()
    test_jev_stripped()
    test_jev_after_memory()
    test_memory_without_closing_tag_kept()
    print("OK: text")

"""TurnClaim unit tests: one delivery per turn wins, retries fall through.

Run from the repo root: python3 tests/test_claim.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jpl.runtime import TurnClaim


def test_first_claim_wins():
    claims = TurnClaim()
    assert claims.claim("s1", "t1") is True
    assert claims.claim("s1", "t1") is False
    assert claims.claim("s1", "t2") is True
    assert claims.claim("s2", "t1") is True


def test_empty_turn_never_claims():
    claims = TurnClaim()
    assert claims.claim("s1", "") is False


if __name__ == "__main__":
    test_first_claim_wins()
    test_empty_turn_never_claims()
    print("OK: claim")

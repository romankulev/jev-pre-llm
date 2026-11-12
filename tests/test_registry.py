"""Intent-registry self-check: file contract + PATTERNS honesty.

Run from the repo root: python3 tests/test_registry.py [handlers_dir]
"""

import importlib.util
import sys
from pathlib import Path

HANDLERS = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else (
    Path(__file__).resolve().parent.parent / "handlers"
)


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None, f"{path.name}: not importable"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _handler_files():
    return sorted(p for p in HANDLERS.glob("*.py") if not p.name.startswith("_"))


def test_contract():
    if not _handler_files():
        print("handlers/ is empty (template only) — nothing to check")
        return
    for path in _handler_files():
        mod = _load(path)
        assert getattr(mod, "HANDLER_ID", "") == path.stem, f"{path.name}: HANDLER_ID != file name"
        assert isinstance(getattr(mod, "PATTERNS", None), list) and mod.PATTERNS, (
            f"{path.name}: PATTERNS is empty"
        )
        assert isinstance(getattr(mod, "CRITERIA", ""), str) and mod.CRITERIA.strip(), (
            f"{path.name}: CRITERIA is empty"
        )
        assert callable(getattr(mod, "run", None)), f"{path.name}: no run()"
        for key in ("MUST_MATCH", "MUST_MISS"):
            val = getattr(mod, key, None)
            assert isinstance(val, list) and val, f"{path.name}: {key} is empty"


def test_patterns_match_examples():
    for path in _handler_files():
        mod = _load(path)
        for s in mod.MUST_MATCH:
            assert any(p.search(s) for p in mod.PATTERNS), (
                f"{path.name}: MUST_MATCH catches no PATTERNS: {s!r}"
            )
        for s in mod.MUST_MISS:
            assert not any(p.search(s) for p in mod.PATTERNS), (
                f"{path.name}: MUST_MISS catches a PATTERNS entry: {s!r}"
            )


def test_no_cross_fire():
    """A sibling's must-match examples must not catch on my patterns,
    or classification will argue between neighbours."""
    mods = [(p, _load(p)) for p in _handler_files()]
    for path, mod in mods:
        for other_path, other in mods:
            if other_path == path:
                continue
            for s in other.MUST_MATCH:
                assert not any(p.search(s) for p in mod.PATTERNS), (
                    f"{path.name} hijacks an example from {other_path.name}: {s!r}"
                )


if __name__ == "__main__":
    test_contract()
    test_patterns_match_examples()
    test_no_cross_fire()
    print(f"OK: {_handler_files() or 'template'}")

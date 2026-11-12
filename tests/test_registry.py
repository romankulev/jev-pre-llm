"""Самопроверка реестра интентов: контракт файла + честность PATTERNS.

Запуск из корня репо: python3 -m pytest tests/ -q
"""

import importlib.util
import re
import sys
from pathlib import Path

HANDLERS = Path(__file__).resolve().parent.parent / "handlers"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None, f"{path.name}: не импортируется"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _handler_files():
    return sorted(p for p in HANDLERS.glob("*.py") if not p.name.startswith("_"))


def test_contract():
    if not _handler_files():
        print("handlers/ пуст (только шаблон) — проверять нечего")
        return
    for path in _handler_files():
        mod = _load(path)
        assert getattr(mod, "HANDLER_ID", "") == path.stem, f"{path.name}: HANDLER_ID != имени файла"
        assert isinstance(getattr(mod, "PATTERNS", None), list) and mod.PATTERNS, (
            f"{path.name}: PATTERNS пуст"
        )
        assert isinstance(getattr(mod, "CRITERIA", ""), str) and mod.CRITERIA.strip(), (
            f"{path.name}: CRITERIA пуст"
        )
        assert callable(getattr(mod, "run", None)), f"{path.name}: нет run()"
        for key in ("MUST_MATCH", "MUST_MISS"):
            val = getattr(mod, key, None)
            assert isinstance(val, list) and val, f"{path.name}: {key} пуст"


def test_patterns_match_examples():
    for path in _handler_files():
        mod = _load(path)
        for s in mod.MUST_MATCH:
            assert any(p.search(s) for p in mod.PATTERNS), (
                f"{path.name}: MUST_MATCH не цепляется за PATTERNS: {s!r}"
            )
        for s in mod.MUST_MISS:
            assert not any(p.search(s) for p in mod.PATTERNS), (
                f"{path.name}: MUST_MISS цепляется за PATTERNS: {s!r}"
            )


def test_no_cross_fire():
    """Чужие must-match не должны цепляться за мои паттерны — иначе
    классификация будет спорить между соседями."""
    mods = [(p, _load(p)) for p in _handler_files()]
    for path, mod in mods:
        for other_path, other in mods:
            if other_path == path:
                continue
            for s in other.MUST_MATCH:
                assert not any(p.search(s) for p in mod.PATTERNS), (
                    f"{path.name} перехватывает чужой пример из {other_path.name}: {s!r}"
                )


if __name__ == "__main__":
    test_contract()
    test_patterns_match_examples()
    test_no_cross_fire()
    print(f"OK: {_handler_files() or 'шаблон'}")

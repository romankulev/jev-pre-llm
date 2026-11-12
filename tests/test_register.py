"""Registration test: register() wires middleware + hook on a fake ctx.

Run from the repo root: python3 tests/test_register.py
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path.home() / ".hermes" / "hermes-agent"))

from jpl.runtime import _MISSING, register  # noqa: E402


class FakeCtx:
    def __init__(self, config=None):
        self.config = config or {}
        self.middleware = []
        self.hooks = []

    def get_config(self, name, default=None):
        return self.config.get(name, default)

    def register_middleware(self, name, fn):
        self.middleware.append((name, fn))

    def register_hook(self, name, fn):
        self.hooks.append((name, fn))


def test_register_wires_both():
    ctx = FakeCtx()
    register(ctx)  # must not raise, must not disable
    assert [n for n, _ in ctx.middleware] == ["llm_execution"]
    assert [n for n, _ in ctx.hooks] == ["post_llm_call"]


def test_register_rejects_unknown_handler():
    ctx = FakeCtx({"enabled_handlers": ["nope"]})
    register(ctx)
    assert ctx.middleware == [] and ctx.hooks == []


def test_register_rejects_bad_mode():
    ctx = FakeCtx({"mode": "turbo"})
    register(ctx)
    assert ctx.middleware == [] and ctx.hooks == []


if __name__ == "__main__":
    test_register_wires_both()
    test_register_rejects_unknown_handler()
    test_register_rejects_bad_mode()
    print("OK: register")

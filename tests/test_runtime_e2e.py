"""End-to-end middleware test: gate -> solver(stubbed) -> run -> answer.

Drives FastPathRuntime.middleware with a fake ctx/request, no gateway,
no network. Covers shadow, active, solver-reject, and claim-once.

Run from the repo root: python3 tests/test_runtime_e2e.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jpl.runtime as RT
from jpl.loader import HandlerSpec
from jpl.text import _strip_hermes_suffix
from jpl.types import Decision


def _spec(handler_id="fp_status", answer="Режим: shadow."):
    def run(text, ctx):
        return answer
    return HandlerSpec(handler_id=handler_id, criteria="status questions",
                       run=run, source="test", rewrite=None)


def _runtime(mode="shadow"):
    settings = RT.Settings(mode=mode, enabled_handlers=("fp_status",))
    return RT.FastPathRuntime(settings, {"fp_status": _spec()})


def _request(text="статус фастпаса"):
    return {"messages": [{"role": "user", "content": text}]}


def _stub_ok(text, candidates, specs, timeout=15.0):
    return Decision(handler_id="fp_status", ok=True, latency_ms=5, model="stub")


def _stub_reject(text, candidates, specs, timeout=15.0):
    return Decision(handler_id="normal_llm", ok=False, latency_ms=5, model="stub")


def _run_with(rt, stub, **kw):
    real = RT.classify
    RT.classify = stub
    try:
        return rt.middleware(request=_request(), next_call=lambda req: "LLM-ANSWER",
                             api_call_count=1, session_id="s", turn_id=kw.pop("turn", "t1"),
                             api_mode="chat_completions", **kw)
    finally:
        RT.classify = real


def test_suffix_order_bug():
    # Live case: user text + memory block + Jev suggestion must reduce to the request.
    mem = ("\n\n<memory-context>\n[System note: blah, see https://example.com/x.\n\n</memory-context>")
    jev = "\n\n[Jev skill suggestion] `x` looks relevant."
    text = "чекни тг" + mem + jev
    assert _strip_hermes_suffix(text) == "чекни тг"


def test_shadow_returns_llm_answer():
    assert _run_with(_runtime("shadow"), _stub_ok) == "LLM-ANSWER"


def test_active_returns_synthetic():
    out = _run_with(_runtime("active"), _stub_ok)
    assert not isinstance(out, str)
    assert out.choices[0].message.content == "Режим: shadow."


def test_reject_falls_through():
    assert _run_with(_runtime("active"), _stub_reject) == "LLM-ANSWER"


def test_claim_once():
    rt = _runtime("active")
    first = _run_with(rt, _stub_ok, turn="t9")
    second = _run_with(rt, _stub_ok, turn="t9")
    assert not isinstance(first, str)
    assert first.choices[0].message.content == "Режим: shadow."
    assert second == "LLM-ANSWER"


def test_handler_crash_falls_through():
    def bad(text, ctx):
        raise ValueError("nope")
    spec = HandlerSpec(handler_id="fp_status", criteria="x", run=bad, source="t", rewrite=None)
    settings = RT.Settings(mode="active", enabled_handlers=("fp_status",))
    rt = RT.FastPathRuntime(settings, {"fp_status": spec})
    assert _run_with(rt, _stub_ok) == "LLM-ANSWER"


if __name__ == "__main__":
    test_shadow_returns_llm_answer()
    test_active_returns_synthetic()
    test_reject_falls_through()
    test_claim_once()
    test_handler_crash_falls_through()
    print("OK: runtime-e2e")

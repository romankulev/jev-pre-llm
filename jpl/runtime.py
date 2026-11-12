"""``llm_execution`` middleware orchestration and the ``register(ctx)`` entrypoint.

Flow per fresh user turn: eligibility (first delivery of the turn only) ->
extract text -> safety gate (no solver call when stopped) -> solver picks
among enabled handlers -> accepted match runs handler code; ``shadow`` mode
logs and still calls the LLM, ``active`` returns a synthetic response with
zero provider calls. Every uncertainty fails open to exactly one downstream
call.
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from typing import Any, Callable, Mapping

from .gate import detect_candidates
from .loader import HandlerDeclined, HandlerSpec, load_handlers
from .recorder import Recorder
from .responses import build_synthetic_response
from .solver import SolverError, classify, rewrite_text
from .telemetry import TelemetryWriter
from .text import extract_latest_user_text
from .tg import TelegramHelper
from .types import TelemetryEvent

logger = logging.getLogger("jev-pre-llm.runtime")

MODES = ("off", "shadow", "active")
_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="jpl-handler")


class SettingsError(ValueError):
    """Untrusted profile settings; the plugin stays disabled."""


class Settings:
    def __init__(
        self,
        mode: str = "shadow",
        timeout_seconds: float = 15.0,
        handler_timeout_seconds: float = 120.0,
        max_input_chars: int = 4000,
        enabled_handlers: tuple[str, ...] = (),
        handlers_dir: str = "~/.hermes/jev-intents",
    ):
        self.mode = mode
        self.timeout_seconds = timeout_seconds
        self.handler_timeout_seconds = handler_timeout_seconds
        self.max_input_chars = max_input_chars
        self.enabled_handlers = enabled_handlers
        self.handlers_dir = handlers_dir


def _float_setting(name: str, value: object, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SettingsError(f"{name} must be a number")
    result = float(value)
    if not isfinite(result) or not low <= result <= high:
        raise SettingsError(f"{name} must be between {low} and {high}")
    return result


def _int_setting(name: str, value: object, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise SettingsError(f"{name} must be an integer between {low} and {high}")
    return value


_MISSING = object()


def _plugin_env() -> dict[str, str]:
    """Read the plugin's own .env (fallback when gateway ctx carries no settings)."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    values: dict[str, str] = {}
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip("\"'")
    return values


_PLUGIN_ENV = _plugin_env()


def _setting(ctx, name: str, default: object, env_name: str | None = None) -> object:
    """ctx.get_config first, plugin's own .env second, compiled default last."""
    value = ctx.get_config(name, _MISSING)
    if value is _MISSING or value is None:
        if env_name is not None:
            env_value = _PLUGIN_ENV.get(env_name)
            if env_value is not None and env_value != "":
                return env_value
        return default
    return value


def _to_number(name: str, value: object) -> int | float:
    if isinstance(value, bool):
        raise SettingsError(f"{name} must be a number")
    if isinstance(value, str):
        text = value.strip()
        try:
            return float(text) if any(c in text for c in ".eE") else int(text)
        except ValueError:
            raise SettingsError(f"{name} must be a number")
    if isinstance(value, (int, float)):
        return value
    raise SettingsError(f"{name} must be a number")


def load_settings(ctx, registry: Mapping[str, HandlerSpec]) -> Settings:
    defaults = Settings()
    mode = _setting(ctx, "mode", defaults.mode, "JPL_MODE")
    if mode not in MODES:
        raise SettingsError("mode must be off, shadow, or active")
    timeout_seconds = _float_setting(
        "timeout_seconds",
        _to_number("timeout_seconds", _setting(ctx, "timeout_seconds", 15.0, "JPL_TIMEOUT_SECONDS")),
        1.0, 120.0,
    )
    handler_timeout = _float_setting(
        "handler_timeout_seconds",
        _to_number("handler_timeout_seconds", _setting(ctx, "handler_timeout_seconds", 120.0, "JPL_HANDLER_TIMEOUT_SECONDS")),
        5.0, 600.0,
    )
    max_chars = _int_setting(
        "max_input_chars",
        _to_number("max_input_chars", _setting(ctx, "max_input_chars", 4000, "JPL_MAX_INPUT_CHARS")),
        100, 20000,
    )
    raw_handlers = _setting(ctx, "enabled_handlers", ["check_tg", "tg_person", "fp_status"], "JPL_ENABLED_HANDLERS")
    if isinstance(raw_handlers, str):
        handlers = [h.strip() for h in raw_handlers.split(",") if h.strip()]
    else:
        handlers = raw_handlers
    if not isinstance(handlers, (list, tuple)) or any(not isinstance(x, str) for x in handlers):
        raise SettingsError("enabled_handlers must be a list of handler IDs")
    if len(set(handlers)) != len(handlers):
        raise SettingsError("enabled_handlers has duplicates")
    unknown = [h for h in handlers if h not in registry]
    if unknown:
        raise SettingsError(f"unknown handlers: {', '.join(unknown)}")
    handlers_dir = _setting(ctx, "handlers_dir", defaults.handlers_dir, "JPL_HANDLERS_DIR")
    if not isinstance(handlers_dir, str) or not handlers_dir.strip():
        raise SettingsError("handlers_dir must be a non-empty path string")
    return Settings(
        mode=mode,
        timeout_seconds=timeout_seconds,
        handler_timeout_seconds=handler_timeout,
        max_input_chars=max_chars,
        enabled_handlers=tuple(handlers),
        handlers_dir=handlers_dir.strip(),
    )


class TurnClaim:
    """First delivery of a (session_id, turn_id) pair wins; retries fall through."""

    def __init__(self, ttl_seconds: float = 900.0, max_entries: int = 4096):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple[str, str], float] = OrderedDict()

    def claim(self, session_id: str, turn_id: str) -> bool:
        if not turn_id:
            return False
        now = time.monotonic()
        key = (str(session_id), str(turn_id))
        with self._lock:
            expired = [k for k, stamp in self._entries.items() if now - stamp >= self._ttl]
            for k in expired:
                self._entries.pop(k, None)
            if key in self._entries:
                self._entries[key] = now
                self._entries.move_to_end(key)
                return False
            self._entries[key] = now
            while len(self._entries) > self._max:
                self._entries.popitem(last=False)
            return True


class FastPathRuntime:
    def __init__(self, settings: Settings, registry: Mapping[str, HandlerSpec], telemetry=None):
        self.settings = settings
        self.registry = registry
        self.telemetry = telemetry
        self._claims = TurnClaim()
        self._status_lock = threading.Lock()
        self._last_decision_at: str | None = None
        self._tg = TelegramHelper(
            Path(__file__).resolve().parent.parent,
            handler_timeout=settings.handler_timeout_seconds,
        )
        self._recorder: Recorder | None = None

    def status(self) -> dict[str, Any]:
        with self._status_lock:
            return {
                "mode": self.settings.mode,
                "enabled_handlers": list(self.settings.enabled_handlers),
                "known_handlers": sorted(self.registry.keys()),
                "last_decision_at": self._last_decision_at,
            }

    def _emit(self, event: TelemetryEvent, meta: Mapping[str, Any]) -> None:
        if self.telemetry is not None:
            self.telemetry.write(event, meta)

    def middleware(
        self,
        *,
        request,
        next_call: Callable,
        api_call_count: int | None = None,
        session_id: str = "",
        turn_id: str = "",
        api_mode: str = "",
        **context: Any,
    ):
        downstream_called = False

        def downstream():
            nonlocal downstream_called
            if downstream_called:
                raise RuntimeError("downstream provider call attempted more than once")
            downstream_called = True
            return next_call(request)

        meta = {
            **context,
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "api_mode": str(api_mode),
            "mode": self.settings.mode,
        }
        try:
            return self._evaluate_or_fallthrough(
                request=request,
                downstream=downstream,
                api_call_count=api_call_count,
                session_id=str(session_id),
                turn_id=str(turn_id),
                api_mode=str(api_mode),
                context=meta,
            )
        except Exception as exc:
            if downstream_called:
                raise
            self._emit(
                TelemetryEvent(outcome="fallback", reason=getattr(exc, "code", None) or type(exc).__name__, text=""),
                meta,
            )
            return downstream()

    def _eligible(self, api_call_count: Any, session_id: str, turn_id: str) -> bool:
        if self.settings.mode == "off":
            return False
        try:
            count = int(api_call_count)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        if count != 1 or not turn_id.strip():
            return False
        return self._claims.claim(session_id, turn_id)

    def _evaluate_or_fallthrough(self, *, request, downstream, api_call_count, session_id, turn_id, api_mode, context):
        if not self._eligible(api_call_count, session_id, turn_id):
            return downstream()
        text = extract_latest_user_text(request, api_mode)
        if text is None:
            return downstream()
        candidates = detect_candidates(text, self.registry, self.settings.enabled_handlers, self.settings.max_input_chars)
        if not candidates:
            self._emit(TelemetryEvent(outcome="no_candidate", reason="local_filter", text=text), context)
            return downstream()
        try:
            specs = {h: self.registry[h].criteria for h in candidates}
            decision = classify(text, candidates, specs, self.settings.timeout_seconds)
        except SolverError as exc:
            self._emit(
                TelemetryEvent(outcome="normal_llm", reason=f"solver_{exc.code}", text=text, candidates=candidates),
                context,
            )
            return downstream()
        if not decision.ok or decision.handler_id not in candidates:
            self._emit(
                TelemetryEvent(
                    outcome="normal_llm", reason="solver_rejected", text=text,
                    candidates=candidates, selected_handler=decision.handler_id,
                    latency_ms=decision.latency_ms,
                ),
                context,
            )
            return downstream()
        spec = self.registry[decision.handler_id]
        handler_ctx = {
            **context,
            "status": self.status(),
            "handler_timeout": self.settings.handler_timeout_seconds,
            "tg": self._tg,
        }
        try:
            future = _POOL.submit(spec.run, text, handler_ctx)
            answer = future.result(timeout=self.settings.handler_timeout_seconds)
        except Exception as exc:
            base = "handler_declined" if isinstance(exc, HandlerDeclined) else type(exc).__name__
            detail = str(exc).replace("\n", " ")[:100]
            reason = f"{base}: {detail}" if detail else base
            self._emit(
                TelemetryEvent(
                    outcome="normal_llm", reason=reason, text=text,
                    candidates=candidates, selected_handler=spec.handler_id,
                    latency_ms=decision.latency_ms,
                ),
                context,
            )
            return downstream()
        if not isinstance(answer, str) or not answer.strip():
            self._emit(
                TelemetryEvent(
                    outcome="normal_llm", reason="empty_answer", text=text,
                    candidates=candidates, selected_handler=spec.handler_id,
                    latency_ms=decision.latency_ms,
                ),
                context,
            )
            return downstream()
        with self._status_lock:
            self._last_decision_at = datetime.now(timezone.utc).isoformat()
        if spec.rewrite:
            try:
                answer = rewrite_text(answer, spec.rewrite, timeout=15.0)
                rewritten = True
            except Exception:
                rewritten = False
        else:
            rewritten = False
        _ = rewritten
        if self.settings.mode == "shadow":
            self._emit(
                TelemetryEvent(
                    outcome="would_short_circuit", reason="shadow", text=text,
                    candidates=candidates, selected_handler=spec.handler_id,
                    latency_ms=decision.latency_ms, answer=answer,
                ),
                context,
            )
            return downstream()
        response = build_synthetic_response(api_mode, answer)
        if self._recorder is not None:
            try:
                self._recorder.mark_handled(session_id, turn_id)
            except Exception:
                pass
        self._emit(
            TelemetryEvent(
                outcome="short_circuit", reason="accepted", text=text,
                candidates=candidates, selected_handler=spec.handler_id,
                latency_ms=decision.latency_ms, answer=answer,
            ),
            context,
        )
        return response


def register(ctx) -> None:
    """Hermes directory-plugin entrypoint: validate, load handlers, wire middleware."""
    try:
        from hermes_constants import get_hermes_home
    except Exception as exc:
        logger.warning("jev-pre-llm disabled: Hermes home unavailable (%s)", type(exc).__name__)
        return
    try:
        # handlers_dir is read from ctx/.env with compiled defaults so the
        # stock registry can load before full settings validation.
        raw_dir = ctx.get_config("handlers_dir", _MISSING)
        if raw_dir is _MISSING or raw_dir is None:
            raw_dir = _PLUGIN_ENV.get("JPL_HANDLERS_DIR", Settings().handlers_dir)
        registry = load_handlers(extra_dir=str(raw_dir))
    except ValueError as exc:
        logger.warning("jev-pre-llm disabled: %s", exc)
        return
    if not registry:
        logger.warning("jev-pre-llm disabled: no handlers in handlers/")
        return
    try:
        settings = load_settings(ctx, registry)
    except SettingsError as exc:
        logger.warning("jev-pre-llm disabled: %s", exc)
        return
    runtime = FastPathRuntime(settings, registry, telemetry=TelemetryWriter(get_hermes_home()))
    # Registration proof at warning: gateway logs surface WARNING+, an info
    # line is invisible in journalctl.
    logger.warning(
        "jev-pre-llm live config: mode=%s enabled=%s registry=%s handlers_dir=%s",
        settings.mode, ",".join(settings.enabled_handlers),
        ",".join(sorted(registry)), settings.handlers_dir,
    )
    ctx.register_middleware("llm_execution", runtime.middleware)
    # Post-turn trace recorder for the miner: pure observer, never rewrites.
    try:
        recorder = Recorder(Path(get_hermes_home()) / "plugin-data" / "jev-pre-llm" / "trace.jsonl")
        runtime._recorder = recorder
        ctx.register_hook("post_llm_call", recorder)
    except Exception as exc:
        logger.warning("jev-pre-llm recorder not wired: %s", type(exc).__name__)
    logger.info(
        "jev-pre-llm registered llm_execution middleware (mode=%s, handlers=%s)",
        settings.mode, ",".join(settings.enabled_handlers),
    )

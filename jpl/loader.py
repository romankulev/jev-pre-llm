"""Handler registry: every intent file is loaded and validated, loudly.

An intent file must define::

    HANDLER_ID = "check_tg"      # unique id, used in config + telemetry
    PATTERNS = [...]             # compiled regexes (or strings) + MUST_MATCH/MUST_MISS
    CRITERIA = "..."             # one line for the solver's choice question
    def run(text, ctx) -> str    # returns the reply text; raise to fall back to LLM

Optional: ``REWRITE`` — a string (or True for the default) telling a cheap
model how to restyle the raw answer.

Loading is two-tier: stock ``handlers/`` from this repo plus an external
user directory (``handlers_dir`` setting, default ``~/.hermes/jev-intents``).
The external directory wins on id clashes and survives plugin updates.
Files starting with ``_`` are ignored in both.
"""

from __future__ import annotations

import importlib.util
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, cast

logger = logging.getLogger("jev-pre-llm.loader")


class HandlerDeclined(ValueError):
    """The handler declined: fall through to the normal LLM path."""


@dataclass(frozen=True)
class HandlerSpec:
    handler_id: str
    criteria: str
    run: Callable[[str, Mapping], str]
    source: str
    rewrite: str | None = None


DEFAULT_REWRITE = "Изложи своими словами, коротко, только главное."


def _plugin_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_file(path: Path, module_tag: str) -> HandlerSpec:
    """Import one intent file and validate its contract."""
    module_name = f"jpl_handlers_{module_tag}_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load handler file {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise ValueError(f"handler file {path.name} failed to import: {exc}") from exc
    handler_id = getattr(module, "HANDLER_ID", None)
    raw_patterns = getattr(module, "PATTERNS", [])
    criteria = getattr(module, "CRITERIA", None)
    run = getattr(module, "run", None)
    if not isinstance(handler_id, str) or not handler_id.strip():
        raise ValueError(f"{path.name}: HANDLER_ID must be a non-empty string")
    if not isinstance(raw_patterns, (list, tuple)) or not raw_patterns:
        raise ValueError(f"{path.name}: PATTERNS must be a non-empty list")
    patterns: list[re.Pattern] = []
    for item in raw_patterns:
        try:
            patterns.append(item if isinstance(item, re.Pattern) else re.compile(item))
        except re.error as exc:
            raise ValueError(f"{path.name}: bad regex: {exc}") from exc
    if not isinstance(criteria, str) or not criteria.strip():
        raise ValueError(f"{path.name}: CRITERIA must be a non-empty string")
    if not callable(run):
        raise ValueError(f"{path.name}: run(text, ctx) must be callable")
    rewrite = getattr(module, "REWRITE", None)
    if rewrite is True:
        rewrite = DEFAULT_REWRITE
    if rewrite is not None and (not isinstance(rewrite, str) or not rewrite.strip()):
        raise ValueError(f"{path.name}: REWRITE must be a string, True, or absent")
    return HandlerSpec(
        handler_id=handler_id,
        criteria=criteria.strip(),
        run=cast(Callable[[str, Mapping], str], run),
        source=str(path),
        rewrite=rewrite.strip() if isinstance(rewrite, str) else None,
    )


def _load_dir(directory: Path, module_tag: str) -> dict[str, HandlerSpec]:
    registry: dict[str, HandlerSpec] = {}
    if not directory.is_dir():
        return registry
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        handler = _load_file(path, module_tag)
        if handler.handler_id in registry:
            raise ValueError(f"{path.name}: duplicate HANDLER_ID {handler.handler_id!r}")
        registry[handler.handler_id] = handler
    return registry


def load_handlers(extra_dir: Path | str | None = None) -> dict[str, HandlerSpec]:
    """Load stock handlers, overlay the user directory (wins on clashes)."""
    registry = _load_dir(_plugin_dir() / "handlers", "stock")
    if extra_dir:
        extra = Path(extra_dir).expanduser()
        if extra.is_dir():
            for handler_id, handler in _load_dir(extra, "user").items():
                if handler_id in registry:
                    logger.warning(
                        "user handler %s overrides stock one (%s)",
                        handler_id, handler.source,
                    )
                registry[handler_id] = handler
    # HANDLER_ID must also match its file name (SPEC contract).
    for handler_id, handler in registry.items():
        if Path(handler.source).stem != handler_id:
            raise ValueError(f"{handler.source}: HANDLER_ID {handler_id!r} != file name")
    return registry

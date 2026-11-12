"""Dashboard backend: read-only fast-path status for the desktop LED.

Mounted at ``/api/plugins/jev-pre-llm/`` by the dashboard plugin system.
The desktop half polls ``GET status`` every few seconds (polling fallback —
``ctx.socket`` is a no-op on OAuth remotes). Plugin contract: never raise
out of a handler; failures fold into ``{"ok": False}``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()


def _read_status() -> dict:
    loader_path = Path(__file__).resolve().parent.parent / "jpl" / "status.py"
    spec = importlib.util.spec_from_file_location("jpl_status_standalone", loader_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        return {"ok": False, "error": "unloadable"}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from hermes_constants import get_hermes_home

    plugin_dir = Path(__file__).resolve().parent.parent
    return module.read_status(get_hermes_home(), plugin_dir=plugin_dir)


@router.get("/status")
async def status() -> dict:
    """Last fast-path decision + trace size. No secrets, no full texts."""
    try:
        result = _read_status()
        return result if isinstance(result, dict) else {"ok": False}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}

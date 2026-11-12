"""Shared Telegram access for handlers, injected as ``ctx["tg"]``.

One place owns env discovery (cached), the fetch subprocess, and clipping —
intent files stay small and never hunt for credentials themselves.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path


class TelegramError(ValueError):
    """Telegram fetch failed; the turn falls through to the normal LLM."""


class TelegramHelper:
    def __init__(self, plugin_dir: Path | str, handler_timeout: float = 120.0):
        self._plugin_dir = Path(plugin_dir)
        self._timeout = float(handler_timeout)
        self._env_file: Path | None = None
        self._env_searched = False

    @staticmethod
    def clip(text: str | None, limit: int = 160) -> str:
        return " ".join((text or "").split())[:limit]

    def _venv_python(self) -> Path:
        return Path.home() / "mcp-services" / "telegram-mcp" / ".venv" / "bin" / "python"

    def _script(self) -> Path:
        return self._plugin_dir / "telegram_fetch.py"

    def env_file(self) -> Path:
        """Find the Telethon session env, once per process (same one the MCP uses)."""
        if not self._env_searched:
            self._env_searched = True
            session_dir = Path.home() / "mcp-services" / "telegram-mcp"
            for name in (".env.roman-work", ".env.aeza"):
                candidate = session_dir / name
                if candidate.exists():
                    self._env_file = candidate
                    break
            else:
                found = sorted(
                    p for p in session_dir.glob(".env.*") if p.name != ".env.example"
                )
                if found:
                    self._env_file = found[0]
        if self._env_file is None:
            raise TelegramError("no telegram session env file")
        return self._env_file

    def fetch(
        self,
        *,
        scratch_name: str,
        search: str | None = None,
        max_chats: int = 12,
        limit: int = 5,
        search_limit: int = 8,
    ) -> dict:
        """Run the fetch subprocess and return its parsed JSON."""
        scratch = Path.home() / ".hermes" / "cache" / "scratch" / scratch_name
        cmd = [
            str(self._venv_python()), str(self._script()),
            "--env", str(self.env_file()),
            "--out", str(scratch),
            "--max-chats", str(max_chats), "--limit", str(limit),
        ]
        if search:
            cmd += ["--search", search, "--search-limit", str(search_limit)]
        t0 = time.time()
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise TelegramError(f"tg fetch timed out after {self._timeout:.0f}s") from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "")[-200:]
            raise TelegramError(f"tg fetch failed: {detail}")
        try:
            data = json.loads(scratch.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise TelegramError(f"tg fetch produced no JSON: {exc}") from exc
        data["_elapsed_s"] = round(time.time() - t0, 1)
        return data

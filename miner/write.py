"""Writer-backed draft synthesis: repeat candidate -> filled intent draft.

Takes a repeat candidate from ``miner/scan.py`` and asks an OpenAI-compatible
writer model (default: local ``hermes proxy``, i.e. the user's own
subscription) to fill the intent contract: HANDLER_ID, PATTERNS, CRITERIA,
MUST_MATCH/MUST_MISS, and a read-only ``run()`` replaying the observed
trace. Falls back to the TODO skeleton from ``scan.render_draft`` when the
writer is unreachable or returns garbage — a bad draft must never block
the miner.

The writer only ever sees the redacted trace (tool NAMES, never arg values).
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

_SYSTEM = """You write Hermes fast-path intent handlers. Reply with ONLY one JSON object:
{"handler_id": "lowercase_latin_id", "criteria": "one sentence, how it differs from neighbours",
 "patterns": ["regex1", "regex2"],
 "must_match": ["example phrase the solver should take"],
 "must_miss": ["example phrase for normal_llm or a sibling"],
 "run_body": "python statements for run(), reads and computation only; raise ValueError on failure"}.
No sends, deletes, payments, restarts. No markdown, no comments outside the JSON.
"""


class WriterError(RuntimeError):
    """Writer unreachable or returned garbage; caller falls back to skeleton."""


def _prompt(candidate: dict) -> str:
    steps = [
        f"- {t.get('name')}" for t in candidate.get("tools", []) if isinstance(t, dict)
    ]
    return (
        f"User request (seen {candidate.get('count', 0)}x): {candidate.get('text', '')}\n"
        f"Outcome hint: {candidate.get('result', '')}\n"
        f"Observed tool sequence:\n" + ("\n".join(steps) if steps else "- none")
    )


def synthesize(
    candidate: dict,
    *,
    base_url: str,
    model: str,
    api_key: str = "hermes-proxy",
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Ask the writer model for intent fields. Raises WriterError on failure.

    ``api_key`` is the bearer sent to ``base_url``. The local ``hermes
    proxy`` accepts any non-empty bearer (it attaches your real credentials
    itself); pass a real key only when pointing at OpenRouter directly.
    """
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _prompt(candidate)},
            ],
            "temperature": 0.2,
            "max_tokens": 1500,
        }
    ).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.load(resp)
        content = payload["choices"][0]["message"]["content"] or ""
    except Exception as exc:
        raise WriterError(f"writer unreachable: {exc}") from exc
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        raise WriterError("writer returned no JSON")
    try:
        fields = json.loads(match.group(0))
    except ValueError as exc:
        raise WriterError(f"writer returned bad JSON: {exc}") from exc
    if not isinstance(fields, dict) or not re.fullmatch(r"[a-z][a-z0-9_]*", str(fields.get("handler_id", ""))):
        raise WriterError("writer returned no valid handler_id")
    return fields


def render_written_draft(candidate: dict, fields: dict[str, Any]) -> tuple[str, str]:
    """Writer fields + observed trace -> draft file (name, text)."""
    handler_id = str(fields["handler_id"])
    patterns = "\n".join(f'    re.compile(r"{p}", re.IGNORECASE),' for p in fields.get("patterns", [])[:6])
    must_match = "\n".join(f'    "{s}",' for s in fields.get("must_match", [])[:8])
    must_miss = "\n".join(f'    "{s}",' for s in fields.get("must_miss", [])[:8])
    run_body = str(fields.get("run_body", 'raise ValueError("draft not implemented")'))
    run_indented = "\n".join("    " + line if line.strip() else line for line in run_body.splitlines())
    content = f'''"""DRAFT (miner-proposed, writer-filled, NOT loaded by the registry).

Observed {candidate.get("count", 0)}x: {candidate.get("text", "")!r}
Outcome hint: {candidate.get("result", "")!r}

To approve: verify run() below replays the trace with local code only,
run tests/test_registry.py on the target dir, move to handlers/ or
handlers_dir, add the id to enabled_handlers, then shadow.
"""
from __future__ import annotations

import re
from typing import Mapping

HANDLER_ID = "{handler_id}"

PATTERNS = [
{patterns}
]

MUST_MATCH = [
{must_match}
]

MUST_MISS = [
{must_miss}
]

CRITERIA = {json.dumps(str(fields.get("criteria", "TODO")), ensure_ascii=False)}


def run(text: str, ctx: Mapping) -> str:
{run_indented}
'''
    return f"{handler_id}.py", content


def write_draft(candidate: dict, fields: dict[str, Any], drafts_dir: str | Path | None = None) -> Path | None:
    """Write the draft unless a human already touched that file. Returns path or None."""
    dest = (Path(drafts_dir) if drafts_dir else REPO_ROOT / "drafts")
    dest.mkdir(parents=True, exist_ok=True)
    name, content = render_written_draft(candidate, fields)
    path = dest / name
    if path.exists():
        return None
    path.write_text(content, encoding="utf-8")
    return path

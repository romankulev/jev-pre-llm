"""Offline intent-miner scanner: repeats -> draft intents.

Reads a trace log (JSONL, one record per unhandled turn)::

    {"ts": "...", "text": "user request",
     "tools": [{"name": "tool_name", "args": {...}}],
     "result": "short outcome hint"}

and emits draft intent files into ``drafts/`` for repeats: the same
normalized request (plus the same tool signature) seen ``min_repeats``
times or more. Drafts use the stock file contract but the registry never
loads ``drafts/`` — a human moves an approved draft to ``handlers/`` or
``handlers_dir``.

The live recorder hook that appends to the trace log is wired separately;
this scanner is pure stdlib and unit-tested, so it works (and is verified)
without a gateway restart.

Usage:
    python3 miner/scan.py <trace.jsonl> [--min-repeats 2]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DRAFTS_DIR = REPO_ROOT / "drafts"

# Tool names that must never become drafts, ever.
FORBIDDEN_TOOL_HINTS = ("send", "delete", "pay", "restart", "publish", "buy")


def normalize(text: str) -> str:
    """Lowercase, strip accents/punctuation/extra spaces — similarity key."""
    text = unicodedata.normalize("NFKD", text or "").lower()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def tool_signature(tools: list) -> str:
    """Tool-call shape fingerprint: sorted names only, never arg values."""
    names = sorted(str(t.get("name", "?")) for t in tools if isinstance(t, dict))
    return ",".join(names)


def is_eligible(record: dict) -> bool:
    """Draftable = read-only tool sequence (or no tools), never destructive."""
    tools = record.get("tools") or []
    if not isinstance(tools, list):
        return False
    for tool in tools:
        name = str(tool.get("name", "")).lower() if isinstance(tool, dict) else ""
        if any(hint in name for hint in FORBIDDEN_TOOL_HINTS):
            return False
    return True


def find_repeats(records: list[dict], min_repeats: int = 2) -> list[dict]:
    """Group eligible records by (normalized text, tool signature)."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for record in records:
        if not isinstance(record, dict) or not is_eligible(record):
            continue
        text = normalize(str(record.get("text", "")))
        if not text:
            continue
        key = (text, tool_signature(record.get("tools") or []))
        groups.setdefault(key, []).append(record)
    return [
        {"text": members[0].get("text", ""), "count": len(members),
         "tools": members[0].get("tools") or [], "result": members[0].get("result", "")}
        for key, members in sorted(groups.items())
        if len(members) >= min_repeats
    ]


def slugify(text: str) -> str:
    """Human request -> HANDLER_ID latin slug."""
    text = unicodedata.normalize("NFKD", text).lower()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    words = re.findall(r"[a-z]+", text)
    slug = "_".join(words[:4]) or "learned_intent"
    return re.sub(r"_+", "_", slug).strip("_") or "learned_intent"


def render_draft(candidate: dict) -> tuple[str, str]:
    """Candidate brief -> (file name, file text with a TODO run())."""
    handler_id = slugify(str(candidate.get("text", "")))
    steps = [
        f"- {t.get('name')}" + (f" {json.dumps(t.get('args', {}), ensure_ascii=False)[:120]}" if t.get("args") else "")
        for t in candidate.get("tools", []) if isinstance(t, dict)
    ]
    trace = "\n".join(steps) if steps else "- (no tool calls observed: pure reasoning, nothing to replay)"
    content = f'''"""DRAFT (miner-proposed, NOT loaded by the registry).

Observed {candidate["count"]}x: {candidate.get("text", "")!r}
Outcome hint: {candidate.get("result", "")!r}
Observed trace:
{trace}

To approve: implement run() below (replay the trace with local code),
fill PATTERNS/MUST lists honestly, move to handlers/ or handlers_dir,
add the id to enabled_handlers, run tests/test_registry.py, then shadow.
"""
from __future__ import annotations

import re
from typing import Mapping

HANDLER_ID = "{handler_id}"

PATTERNS = [re.compile(r"TODO: trigger phrase", re.IGNORECASE)]

MUST_MATCH = ["TODO: example phrase this intent should take"]

MUST_MISS = ["TODO: example phrase for normal_llm or a sibling"]

CRITERIA = "TODO: one sentence, how it differs from sibling intents."


def run(text: str, ctx: Mapping) -> str:
    # TODO: replay the observed trace above with local code.
    # Read-only steps only. On any failure: raise ValueError.
    raise ValueError("draft not implemented")
'''
    return f"{handler_id}.py", content


def scan(trace_path: Path, min_repeats: int = 2) -> list[Path]:
    records = []
    with open(trace_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
    written = []
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    for candidate in find_repeats(records, min_repeats):
        name, content = render_draft(candidate)
        dest = DRAFTS_DIR / name
        if dest.exists():
            continue  # never overwrite a human-touched draft
        dest.write_text(content, encoding="utf-8")
        written.append(dest)
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("trace", type=Path)
    ap.add_argument("--min-repeats", type=int, default=2)
    args = ap.parse_args(argv)
    for dest in scan(args.trace, args.min_repeats):
        print(f"draft: {dest.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

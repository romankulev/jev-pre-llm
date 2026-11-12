# jev-pre-llm — intent classification before the LLM

A Hermes plugin (`llm_execution` middleware): a cheap decision ahead of the
expensive LLM. Jev (or another solver model) picks an intent, local code
executes it, otherwise the turn quietly falls through to the regular LLM.

## How a turn flows

1. Claim-once per turn: the gateway may deliver the same turn to the
   middleware more than once (retries, fallback re-delivery). The plugin
   handles only the first delivery of a `(session_id, turn_id)` pair and
   lets every repeat fall through to the LLM — so a handler never runs
   twice and the solver is never paid twice for one turn.
2. The latest user text is extracted. `/` commands, code fences, links —
   straight to the LLM.
3. Safety gate: secrets, shell metacharacters, destructive verbs
   (delete/send/pay/restart and equivalents) — always to the LLM, handlers
   never see them.
4. Every enabled handler contributes `id + CRITERIA`; the solver returns one
   `id` or `normal_llm`. Only an exact id match plus an explicit go-flag is
   accepted, anything else falls through. The solver never executes, it only
   picks.
5. `run(text, ctx)` executes with a timeout. An exception or an empty answer
   falls through to the LLM.
6. Modes: `off`, `shadow` (decides and logs to telemetry, the LLM answers),
   `active` (on a match, answers with zero LLM calls).

## Swapping the solver

The solver is a replaceable module with one contract:

- input: `text`, a list of `{id, criteria}`;
- output: `{id | "normal_llm", confidence, go}`.

Current: `jpl/solver.py` (Jev via OpenRouter). Fallback: any cheap LLM with
the same JSON output. Handlers and gates do not depend on the solver.

## Plugin rules

- The handler registry is validated at startup: duplicate ids, broken
  regex/CRITERIA, a missing `run` disable the plugin loudly, never silently.
- Settings are read at registration (`ctx.get_config` first, the plugin's own
  `.env` as fallback). A mode change needs a gateway restart; the proof is the
  log line, not the config file.
- Synthetic answers must match the active `api_mode`, or normalization drops
  them.
- Telemetry is append-only JSONL with truncated fields — no secrets, no full
  texts.
- Start every new plugin/intent in `shadow`, read `decisions.jsonl` on live
  traffic, then go `active`.

## Rules for new intents

One file in `handlers/` = one intent. Files starting with `_` are ignored.
Required:

- `HANDLER_ID` — lowercase latin with underscores, equals the file name,
  unique.
- `PATTERNS` — a list of trigger-phrase regexes. They do NOT filter at
  runtime (every enabled intent is offered to the solver on every turn — cheaper
  and more robust for a small registry than catching morphology with a
  prefilter). Three roles: documentation ("which phrases this covers"),
  self-checks via `MUST_MATCH`/`MUST_MISS` in the same file (the
  `tests/test_registry.py` test keeps examples and patterns honest with each
  other), and regression when a sibling is added (old must-matches must not
  catch on new patterns). Write for morphology: alternations
  (`check|verify|show`), word boundaries, the author's frequent typos. No
  `^...$` anchors — the phrase arrives inside live text.
- `CRITERIA` — one line for the solver. State how it differs from its
  neighbours, not a standalone description ("overall unread summary" vs "one
  named person"). Overlapping criteria confuse the classifier.
- `run(text, ctx) -> str` — reads and computation only. `ctx` carries
  `status`, `handler_timeout`, and `tg` (shared Telegram access — no
  credential hunting inside handlers). An intent needing a
   named entity (person, chat, file) extracts it inside `run`; on a miss raise
  `ValueError` and the turn falls through to the LLM. On failure raise
  `ValueError` — never an empty answer, never a fabrication.

Optional: `REWRITE` — one line telling a cheap model how to restyle the raw
answer. A rewrite failure returns the raw text.

Intent self-check: must-match / must-miss phrases, a `/` command, a
destructive phrase, a live `run`, one full middleware pass in `shadow`.

## Layout

```
plugin.yaml            manifest (provides_middleware: [llm_execution], v1)
SPEC.md                this file — the rules
__init__.py            directory-plugin entrypoint (exposes register)
jpl/                   core: gate → text → solver → loader → runtime
jpl/tg.py              shared Telegram access, injected as ctx["tg"]
jpl/recorder.py        post_llm_call trace observer for the miner
jpl/status.py          read-only status for the LED backend (tested)
dashboard/             LED backend: plugin_api.py + manifest.json
miner/scan.py          repeats → TODO-skeleton drafts
miner/write.py         writer-backed draft synthesis
telegram_fetch.py      Telegram fetch via Telethon (same session as the MCP)
handlers/              stock intents (check_tg, tg_person, fp_status)
handlers/_template.py  intent template
handlers/README.md     intent cheat sheet
desktop/plugin.js      LED indicator (desktop half, see below)
drafts/                proposed self-learned intents (see miner section)
tests/                 registry, gate, and claim self-checks
```

## Where intents live (update safety)

`hermes plugins update` (and especially `auto-update`) replaces the plugin
directory wholesale — files placed by hand inside `~/.hermes/plugins/<name>/`
are wiped. Loading is therefore two-tier:

- `handlers/` in this repo — stock intents, versioned, ship with updates;
- `handlers_dir` (default `~/.hermes/jev-intents`) — user intents outside the
  plugin, updates never touch them. On an id clash the external one wins. Same
  file contract (`HANDLER_ID` = file name, etc.), same `tests/test_registry.py`
  (pass a path: `python3 tests/test_registry.py <dir>`).

Rule: never hand-edit the installed plugin directory. Your own stuff goes
either as a commit to this repo or into `handlers_dir`.

## LED indicator (desktop half)

`desktop/plugin.js` is the desktop half of this unified package: an intent
roulette pane docked below the conversation. Install it to
`$HERMES_HOME/desktop-plugins/jev-pre-llm/plugin.js` (folder name must match
the plugin `id`), then ⌘K → Reload desktop plugins.

- v1 (no backend needed): the pane follows turn atoms — dim when idle, LEDs
  cycling while the focused chat is working.
- v2 (implemented): the Python backend (`dashboard/plugin_api.py`, auto-mounted
  at `/api/plugins/jev-pre-llm/` via `dashboard/manifest.json`) serves
  `GET status` — the last decision (outcome, handler, mode, latency) tailed
  from `decisions.jsonl`, the trace count, and the enabled intent list.
  The pane polls it every 3s (`ctx.rest`; polling kept because `ctx.socket`
  is a no-op on OAuth remotes): while the solver is choosing, one LED per
  intent lights up in slow rotation (~450 ms per LED); a fresh
  `short_circuit` or `would_short_circuit` freezes the winner solid and names
  it for 5 seconds, then everything fades to idle. The LLM thinking afterwards
  never touches the LEDs.

## Intent miner (self-learning)

Status: the offline scanner (`miner/scan.py`, tested) and the writer client
(`miner/write.py`, tested against a fake server) are done; the live recorder
hook is coded (`jpl/recorder.py`, pure observer on `post_llm_call`) but loads
only after a gateway restart. Until then, traces can be fed to the scanner
by hand.

The plugin learns repeatable chores instead of only serving hand-written
intents. Pipeline: `record → repeat → draft → approve → shadow → enable`.

1. **Record.** A `post_llm_call` observer (`jpl/recorder.py`) appends one
   JSONL record per unhandled turn to `plugin-data/jev-pre-llm/trace.jsonl`:
   user text, tool-call NAMES (never arg values), a 200-char result hint.
   Turns the fast path short-circuited are marked and skipped. Unknown
   payload shapes and any failure are silent no-ops; the hook returns None
   and never rewrites.
2. **Repeat.** `miner/scan.py` groups eligible records by (normalized text,
   tool signature) and flags groups seen ≥2 times. Similarity is normalized
   text, not string equality («отчёт»/«отчет» match).
3. **Draft.** `miner/write.py` asks the writer model for the intent fields
   (HANDLER_ID, PATTERNS, CRITERIA, MUST lists, read-only `run()` replaying
   the observed trace) and writes the file into `drafts/`
   (same file contract, but the registry never loads that directory).
   Writer failure falls back to the TODO skeleton from `miner/scan.py` —
   a bad draft never blocks the miner.

### Writer backend: your subscription, no new key

Draft synthesis is an ordinary OpenAI-compatible chat call, not an agent
runtime. Upstream order:

1. Local `hermes proxy` (`hermes proxy start`, default
   `http://127.0.0.1:8645/v1`) — spends your existing subscription/OAuth
   (Nous Portal, xAI Grok OAuth), no API key to obtain or store. Settings:
   `writer_base_url`, `writer_model` (any model your subscription serves).
2. The solver's own key (OpenRouter today) — zero new secrets either way.

This mirrors Hindsight memory: background extraction runs through the
user's own OAuth, not a separate billing key.
4. **Approve.** A draft is never auto-enabled. The user moves it to
   `handlers/` or `handlers_dir` and adds the id to `enabled_handlers`.
5. **Shadow, then active.** Same as a hand-written intent: live traffic in
   `shadow` first.

Hard limits: turns containing send/delete/pay/restart, secrets, or shell
metacharacters are never drafted, ever. Drafts replay reads and computation
only. A draft whose `run()` raises goes to the LLM exactly like a normal
miss. Manual fast track: tell the assistant "remember this" after any good
answer and it writes the draft immediately instead of waiting for a repeat.

## Verifying the chain before installing

`hermes plugins doctor <name>`, `hermes plugins enable <name>`,
mode `shadow`, the `<name> registered` line in the gateway log,
`decisions.jsonl` records `would_short_circuit`, then `active`.

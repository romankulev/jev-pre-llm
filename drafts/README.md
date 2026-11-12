# drafts/ — proposed self-learned intents (intent miner)

Files here use the same contract as `handlers/` files (`HANDLER_ID` = file
name, `PATTERNS`, `CRITERIA`, `MUST_MATCH`, `MUST_MISS`, `run()`, optional
`REWRITE`) but the registry NEVER loads this directory.

Lifecycle: the miner writes a draft here → a human reviews it, moves it to
`handlers/` (stock, via a repo commit) or `handlers_dir` (personal), adds the
id to `enabled_handlers` → `shadow` on live traffic → `active`. See
the "Intent miner (self-learning)" section in SPEC.md.

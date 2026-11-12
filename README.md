# jev-pre-llm

Cheap decisions before the expensive LLM: a solver (Jev or a replacement)
picks an intent, local code executes it, otherwise the turn quietly falls
through to the regular LLM.

Rules live in [SPEC.md](SPEC.md). A new intent is a copy of
`handlers/_template.py`. User intents that survive updates go to
`~/.hermes/jev-intents` (see `handlers_dir` in `plugin.yaml`).

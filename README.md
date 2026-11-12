# jev-pre-llm

Cheap decisions before the expensive LLM: a solver (Jev or a replacement)
picks an intent, local code executes it, otherwise the turn quietly falls
through to the regular LLM.

Rules live in [SPEC.md](SPEC.md). A new intent is a copy of
`handlers/_template.py`. User intents that survive updates go to
`~/.hermes/jev-intents` (see `handlers_dir` in `plugin.yaml`).

## Quickstart

```bash
hermes plugins install romankulev/jev-pre-llm --enable
# put the solver key in the installed plugin's .env (see .env.example)
hermes plugins doctor jev-pre-llm   # import + registration must pass
hermes gateway restart              # middleware + hooks load at startup
```

The default mode is `shadow`: the solver classifies and logs to
`plugin-data/jev-pre-llm/decisions.jsonl`, the LLM still answers. Watch a
few days of live traffic, then go active:

```bash
hermes config set plugins.entries.jev-pre-llm.settings.mode active
hermes gateway restart
```

Back to safety: set mode to `shadow` (or `off`) and restart. If the previous
fast-path plugin is still enabled, disable it first — two `llm_execution`
middlewares classify every turn twice.

## LED indicator

Copy `desktop/plugin.js` to `$HERMES_HOME/desktop-plugins/jev-pre-llm/plugin.js`,
then ⌘K → Reload desktop plugins. The dot pulses while a turn runs; a fresh
`short_circuit` / `would_short_circuit` lights it solid and names the intent.
Needs the gateway running (it polls `/api/plugins/jev-pre-llm/status`).

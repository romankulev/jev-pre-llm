# handlers/ — how to add an intent

Every `*.py` file here is one intent (files starting with `_` are ignored).
Copy `_template.py`.

Required: `HANDLER_ID` (= file name), `PATTERNS`, `CRITERIA`,
`run(text, ctx) -> str`. Optional: `REWRITE`, `MUST_MATCH`, `MUST_MISS`.

The main `CRITERIA` rule: how it differs from its neighbours, not a general
description. A handler needing a named entity (person, chat, file) validates
the extraction inside `run` and raises `ValueError` on a miss — the turn falls
through to the LLM.

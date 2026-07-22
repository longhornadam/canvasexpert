# QuizForge JSON 3.0 (Newspec) Engine

This package is the **live default** JSON 3.0 import pipeline. `engine/importers.py`
imports it (`from engine.spec_engine import parser, packager`) and dispatches to it whenever
`SPEC_MODE == "json"` — which is the default (`QUIZFORGE_SPEC_MODE=json` in
`engine/config.py`). It is a production code path, not a sandbox.

## What it does

- Extracts the `<QUIZFORGE_JSON> ... </QUIZFORGE_JSON>` envelope from raw LLM output that
  may contain chatty text before/after the tags.
- Enforces the JSON 3.0 authoring constraints: STIMULUS/END are never scored, points apply
  only when the teacher explicitly requests them, and rationales stay aligned to scored
  items (structural markers are skipped).
- Returns clean domain objects that the downstream packagers/renderers consume.

## Components

- `parser.py` — extract the tagged JSON, load it, and validate against the JSON 3.0 rules.
- `models.py` — dataclasses describing the accepted JSON payload shape.
- `packager.py` — convert parsed payloads into packaged quiz objects, filtering structural
  rationales.
- `tests/` — pytest coverage for tag extraction, stimulus non-scoring, and rationale
  filtering. Standard library + pytest only.

## Running tests

```
pytest engine/spec_engine/tests -q
```

## More detail

For how this pipeline fits the wider engine and which module owns what, see
`engine/docs/ARCHITECTURE.md` and `engine/docs/AGENT_MAP.md`.

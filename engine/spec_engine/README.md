# QuizForge JSON 3.0 (Newspec) Engine Sandbox

This sandbox hosts the *new* JSON 3.0 parser/packaging work so we can iterate without touching the production TXT/legacy engine. Everything here should stay self-contained under `engine/spec_engine/` until we are confident enough to merge or swap it in.

## Goals
- Parse the `<QUIZFORGE_JSON> ... </QUIZFORGE_JSON>` envelope defined in `dev/newspec/NEWBASE.md`.
- Enforce the JSON 3.0 authoring constraints (e.g., STIMULUS never scored, points only when the teacher explicitly says so).
- Keep rationales aligned to scored items and ignore structural markers.
- Provide clean domain objects that downstream packagers/renderers can consume.
- Avoid regressions to the current production engine; no imports from this sandbox should leak into runtime paths yet.

## Components (initial scaffold)
- `parser.py` — Extract tagged JSON, load, and apply lightweight validation for the new spec.
- `models.py` — Lightweight dataclasses describing the JSON payload shape we accept here.
- `packager.py` — Converts parsed payloads into packaged quiz objects while filtering structural rationales.
- `tests/` — Pytest coverage for tag extraction, stimulus non-scoring, and rationale filtering.

## Expected flow
1. Accept raw LLM output (which may contain chatty text before/after tags).
2. Extract the JSON between `<QUIZFORGE_JSON>` and `</QUIZFORGE_JSON>`.
3. Parse/validate against newspec rules (no points on STIMULUS/END, points only when requested, rationales skip stimuli).
4. Return a structured `QuizPayload` for further processing.

## Safety / isolation
- Do **not** modify production code paths while this sandbox evolves.
- Keep dependencies standard library only.
- When integrating, prefer feature flags or explicit loader selection to avoid surprising the existing orchestration.

## Running tests
```
pytest engine/spec_engine/tests -q
```
Uses only standard library + pytest; no production paths touched.

## Next steps
- Extend tests for NUMERICAL modes, FITB accept lists, and categorization/distractors.
- Implement richer packager output once target domain models are chosen (legacy reuse vs. new).
- Add compatibility shims if we decide to reuse portions of `engine/core`.

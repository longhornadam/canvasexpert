# JSON 3.0 Production Readiness (Feature-Flagged)

> **Scope:** the **engine's** authoring spec mode — how `engine/` ingests a
> QuizForge JSON payload. Applies to **QuizForge-Local** and **QuizForge-Web**
> (both run the engine). The **QuizForge-API** backend does NOT use this path; it
> compiles QuizForge JSON straight to Canvas via its own `api/transform.py`.
> Orientation: root `AGENTS.md`.

## Feature flag
- Env var: `QUIZFORGE_SPEC_MODE`
  - `json` (default): JSON 3.0 pipeline via `engine/spec_engine`
  - `text`: legacy TXT pipeline (deprecated, for backward compatibility only)
- Fallback: JSON path auto-falls back to text on any parse/packager error (logged warning).

## What's supported
- All existing question types supported in the TXT path.
- JSON 3.0 supports the same set; STIMULUS/END are never scored and excluded from rationales.
- Metadata/notes are free-form; extensions may nest under `metadata.extensions` and are ignored if unknown.

## Experimental
- NUMERICAL modes other than `exact` are marked experimental. Tools may ignore or skip them; they do not block imports.

## Testing
- Newspec tests: `pytest engine/spec_engine/tests -q`
- Dual-mode integration: `pytest engine/tests/integration/test_spec_modes.py -q`

## Production notes
1) Default is `QUIZFORGE_SPEC_MODE=json`.
2) To use legacy text mode, set `QUIZFORGE_SPEC_MODE=text` (not recommended).
3) Monitor logs for fallback warnings or experimental item notices.
4) Exporters consume only the domain quiz object; they do not inspect raw specs.
5) Unknown extensions are ignored; no failures on unrecognized keys.

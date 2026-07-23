# Engine Architecture

The `engine/` package is the offline rendering library. It has no Canvas token, no
network dependency, and no student data. It turns authored content into validated
domain objects and local output artifacts.

For repo-wide safety rules and subsystem boundaries, read `../../AGENTS.md` first.
For the live Canvas app, read `../../api/README.md`.

## Data Flow

```text
Forge input
  -> parsing/import
  -> validation and optional fixing
  -> domain model
  -> optional PrintDoc adapter for physical output
  -> render target
  -> local package/output
```

The current QuizForge JSON path enters through `engine/spec_engine` and `JsonImporter`.
The legacy text path remains in `engine/parsing/text_parser.py` for backward
compatibility.

## Main Layers

| Layer | Path | Role |
|---|---|---|
| Domain model | `engine/core/` | Quiz, question, and answer objects consumed by renderers. |
| Import/parsing | `engine/importers.py`, `engine/spec_engine/`, `engine/parsing/` | Convert Forge specs or legacy text into domain objects. |
| Validation | `engine/validation/` | Structural/fairness/rationale checks plus focused fixers. |
| Orchestration | `engine/orchestrator.py` | Runs parse, validate, render, package, and feedback steps. |
| Canvas/QTI render | `engine/rendering/canvas/` | Offline Canvas/QTI package rendering. |
| Physical render | `engine/rendering/physical/` | Shared `PrintDoc` model, tier redaction, and HTML/CSS to PDF/DOCX through installed Edge and bundled Pandoc. |
| Correction docs | `engine/rendering/correction_doc/` | Marked-up correction document rendering. |
| Packaging | `engine/packaging/`, `engine/packagers/` | Output folder/package handlers for Canvas packages and physical quizzes. |
| Feedback | `engine/feedback/` | Local success/failure prompts and logs. |

## Physical Output

Physical rendering is quiz-only. QuizForge adapts trusted content into
`PrintDoc`, then renders the same HTML substrate to DOCX and PDF.

Key files:

- `engine/rendering/physical/printdoc.py`
- `engine/rendering/physical/quiz_adapter.py`
- `engine/rendering/physical/redact.py`
- `engine/packagers/physical_handler.py`

## Boundaries

- `engine/` does not call Canvas APIs. Live Canvas behavior belongs in `api/`.
- Authoring contracts remain canonical in `api/default_docs/AI Authoring/Author a *.txt`.
- Renderers should not become validators; validation happens before rendering.
- Test fixtures must stay fictional and must not include student data.

For file-by-file navigation, see `AGENT_MAP.md`.

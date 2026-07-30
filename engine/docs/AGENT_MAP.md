# Engine Agent Map

Use this file as the short navigation map for engine-only changes. The engine is
offline: no Canvas token, no live Canvas calls, and no student data.

## Start Here

| Task | Start With | Tests To Consider |
|---|---|---|
| QuizForge JSON import behavior | `engine/spec_engine/`, `engine/importers.py` | `py -m pytest engine/spec_engine/tests engine/tests/integration/test_spec_modes.py` |
| Legacy text parsing | `engine/parsing/text_parser.py` | `py -m pytest engine/tests/unit engine/tests/integration` |
| Domain model changes | `engine/core/` | `py -m pytest engine/tests` |
| Validation rules | `engine/validation/rules/`, `engine/validation/validator.py` | `py -m pytest engine/tests/unit` |
| Auto-fix behavior | `engine/validation/fixers/` | `py -m pytest engine/tests/unit` |
| Canvas/QTI package output | `engine/rendering/canvas/` | `py -m pytest engine/tests/integration` |
| Physical quiz PDF/DOCX output | `engine/rendering/physical/`, `engine/packagers/physical_handler.py` | `py -m pytest engine/tests/unit/test_physical_html_parity.py engine/tests/unit/test_printdoc_adapter.py` |
| Correction document output | `engine/rendering/correction_doc/` | `py -m pytest engine/spec_engine/tests/test_correction_doc_renderer.py` |
| End-to-end engine pipeline | `engine/orchestrator.py` | `py -m pytest engine/tests` |

## Key Files

| File | Role |
|---|---|
| `engine/orchestrator.py` | Main offline workflow coordinator. |
| `engine/importers.py` | Converts current Forge specs into engine domain objects. |
| `engine/spec_engine/` | JSON spec-mode support. |
| `engine/parsing/text_parser.py` | Legacy TXT parser; large and compatibility-sensitive. |
| `engine/core/questions.py` | Question domain types. |
| `engine/core/answers.py` | Answer/domain helpers. |
| `engine/validation/validator.py` | Validation coordinator. |
| `engine/rendering/canvas/qti_builder.py` | QTI assessment XML builder. |
| `engine/rendering/canvas/html_formatter.py` | Canvas HTML formatting for prompts/stimuli/feedback. |
| `engine/rendering/physical/printdoc.py` | Shared printable document model. |
| `engine/rendering/physical/redact.py` | Deterministic tier redaction for printable slots. |
| `engine/rendering/physical/README.md` | Physical render stack notes. |

## Do Not Cross These Boundaries

- Do not move Canvas API behavior into `engine/`; use `api/` for live Canvas work.
- Do not edit `LLM_Modules/*_Base.md` to solve an engine implementation bug unless
  the user explicitly asks to revise the authoring contract.
- Do not add real course, roster, submission, grade, token, or district data to
  engine tests or fixtures.
- Do not reintroduce Playwright-managed browser downloads for PDF rendering.

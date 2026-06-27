# PowerGrader AI Refactor Plan

## Context

The PowerGrader AI work added Safe AI Packet generation, OpenRouter scoring, source-material context, token/cost estimates, AI persona/rubric folder links, privacy messaging, and packet result import. The feature is working, but several files now carry too much responsibility.

Current pressure points:

- `api/webui/routes/powergrader.py` is over 1100 lines and mixes routing, Canvas fetches, session persistence, privacy audit construction, packet generation, estimates, scoring, and import handling.
- `api/webui/templates/powergrader_setup.html` and `api/webui/templates/powergrader_queue.html` each include markup, CSS, and large inline JavaScript blocks.
- `api/webui/config.py` is also large, but it is less urgent than the PowerGrader route/template split.

The goal is to keep future PowerGrader changes small, testable, and obvious.

## Backend Split

Create a dedicated PowerGrader package. Prefer `api/powergrader/` unless a module is explicitly web-only.

Proposed modules:

- `api/webui/routes/powergrader.py`
  - Keep FastAPI endpoints, request parsing, and response shaping only.
  - Target length: 250-350 lines.
- `api/powergrader/session_store.py`
  - Session directory paths, safe session IDs, load/save, summaries.
- `api/powergrader/canvas_fetch.py`
  - Canvas submission download, code-file enrichment, assignment count helpers.
- `api/powergrader/context.py`
  - Rubric loading, source-material selection, shared context application.
- `api/powergrader/estimates.py`
  - Token estimates, model pricing labels, response preset integration.
- `api/powergrader/privacy.py`
  - Privacy step definitions, FERPA/PII audit metadata, audit-file writing.
- `api/powergrader/packet.py`
  - Safe AI Packet file naming, readable packet text, paste format, ZIP assembly.
- `api/powergrader/scoring.py`
  - OpenRouter assisted scoring orchestration and mapping results into session students.
- `api/powergrader/import_results.py`
  - Parse, validate, and apply imported AI JSON results.

Avoid creating another large module while extracting. If a new module approaches roughly 500 lines, split it by workflow.

## Frontend Split

Move inline CSS and JavaScript out of the PowerGrader templates.

Proposed static files:

- `api/webui/static/powergrader_setup.css`
- `api/webui/static/powergrader_setup.js`
- `api/webui/static/powergrader_queue.css`
- `api/webui/static/powergrader_queue.js`

Template targets:

- `powergrader_setup.html`: mostly markup and JSON config, 150-250 lines.
- `powergrader_queue.html`: mostly markup and JSON config, 180-300 lines.

JavaScript split points:

- Setup page:
  - grading route mode selection
  - model picker and pricing display
  - source-material estimate workflow
  - privacy step rendering
  - session list loading
- Queue page:
  - student rendering
  - grading/save navigation
  - Safe AI Packet/import UI
  - privacy audit display
  - Canvas push controls

## Suggested Order

1. Extract setup/queue CSS and JavaScript into static files.
   - Low behavioral risk.
   - Immediate template readability improvement.
2. Extract `session_store.py`, `privacy.py`, and `packet.py`.
   - Mostly pure helpers and easy to test.
3. Extract `context.py` and `estimates.py`.
   - Isolates source-material and cost complexity.
4. Extract assisted scoring and import handling.
   - Higher risk because it mutates session state.
5. Revisit `api/webui/config.py` only after PowerGrader is stable.

## Verification Strategy

After each extraction:

- Run focused PowerGrader tests.
- Run route contract tests.
- Smoke-test `/powergrader` and `/powergrader/session/{session_id}`.
- For frontend extractions, verify the setup route cards, safety popout, model picker, token estimate, packet strip, and import controls in browser.


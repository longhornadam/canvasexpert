# Handoff: Routines Route Refactor For VSCode Agent

## Goal

Make `api/webui/routes/routines.py` easier to debug before live-fire testing by
splitting it into small backend modules without changing any routes, routine ids,
runtime behavior, Canvas write policy, or storage format.

This is a refactor-only task. Do not add features.

## Guardrails

- Read `AGENTS.md` first.
- Work on `dev`.
- Do not make live Canvas calls.
- Do not commit secrets, tokens, student data, roster data, grades, submissions, or
  private teacher notes.
- Do not touch `LLM_Modules/*_Base.md`.
- Preserve all existing route paths and methods. `api/tests/test_route_contract.py`
  must pass.
- Scheduled auto-push guardrails are non-negotiable: keep it teacher-controlled,
  per-job/per-assignment opt-in only. Do not broaden auto-push behavior.
- Do not refactor roster/privacy-heavy code unless directly required for this split.
- Do not revert unrelated dirty worktree changes.

## Current Shape

Main file:

- `api/webui/routes/routines.py` is about 963 lines.

Important sections:

- Built-in routine definitions: `_ROUTINE_DEFS`
- Built-in runners:
  - `_run_routine_sweep`
  - `_run_routine_download`
  - `_run_routine_curve`
  - `_run_routine_grading_debt`
  - `_run_routine_student_reports`
  - `_run_routine_powergrader_scheduled_autoscore`
  - `_run_routine_powergrader_late_catchup`
- Custom routine registration/loading:
  - `routine(...)`
  - `_routine_sdk`
  - `_load_custom_routines`
- API routes:
  - `GET /api/routines`
  - `POST /api/routines/save`
  - `POST /api/routines/run`
- Background heartbeat:
  - `_routines_heartbeat`
  - `_run_routines_bg`

## Slice 1: Extract Built-In Runner Functions

Create a new module:

- `api/webui/routes/routines_builtin.py`

Move only these functions and their private helpers if tightly coupled:

- `_run_routine_sweep`
- `_run_routine_download`
- `_run_routine_curve`
- `_run_routine_grading_debt`
- `_run_routine_student_reports`

Leave in `routines.py`:

- `_ROUTINE_DEFS`
- `_ROUTINE_RUNNERS`
- route handlers
- custom routine loader
- PowerGrader scheduled routines for now

In `routines.py`, import the moved functions and keep `_ROUTINE_RUNNERS` keys exactly
the same.

Acceptance:

- No route contract change.
- Routine ids unchanged.
- No behavior changes in log text except unavoidable import-order differences, which
  should be avoided.
- `py -m pytest api/tests/test_route_contract.py api/tests/test_schooldays.py`
  passes.

## Slice 2: Extract PowerGrader Scheduled Routine Runners

Create a new module:

- `api/webui/routes/routines_powergrader.py`

Move:

- `_autoscore_job_label`
- `_autoscore_fetch_status`
- `_autoscore_receipt_dir`
- `_autoscore_canvas_states`
- `_autoscore_session_is_fully_pushed`
- `_autoscore_status_from_summary`
- `_autoscore_summary_payload`
- `_autoscore_decisions_payload`
- `_parse_routine_dt`
- `_run_routine_powergrader_scheduled_autoscore`
- `_run_routine_powergrader_late_catchup`

This module will need the same imports currently used by these helpers from
`routines.py`. Keep imports explicit. Do not move unrelated built-ins with it.

Important compatibility note:

- `api/tests/test_powergrader_scheduled_autoscore.py` imports
  `api.webui.routes.routines as routines` and monkeypatches attributes on that module
  such as `autoscore_queue`, `canvas_fetch`, `_canvas_send`, `ai_workflow`, and
  `session_store`.
- To preserve tests with minimal churn, either:
  - keep those imported dependencies as attributes on `routines.py` and pass them into
    the new module through a small dependency object, or
  - update tests intentionally to patch the new module instead.
- Prefer the first option if it stays simple; it preserves public test seams.

Acceptance:

- `py -m pytest api/tests/test_powergrader_scheduled_autoscore.py api/tests/test_powergrader_late_catchup.py`
  passes when run as part of `py -m pytest api/tests`.
- No scheduled job writes Canvas grades/comments except through the existing
  autopush executor path and only when job policy allows it.
- Date-sensitive tests must not rely on dates near the current year. Use far-future
  fixture due dates where a future reschedule is required.

## Slice 3: Extract Custom Routine Loader

Create a new module:

- `api/webui/routes/routines_custom.py`

Move:

- `routine(...)`
- `_routine_sdk`
- `_load_custom_routines`

Keep the active registries in `routines.py`, or pass them explicitly:

- `_ROUTINE_DEFS`
- `_ROUTINE_RUNNERS`

Acceptance:

- Custom routines still load from `api/custom_routines/`.
- Files starting with `_` still do not load.
- Built-in id collisions are still skipped.
- Broken custom files still do not crash app startup.

## What Not To Touch

- Do not change `api/webui/config.py` persistence shape.
- Do not change routine ids, default params, or labels.
- Do not alter Canvas API endpoints or write behavior.
- Do not split `roster.py` or `gradebook.py` in this task.
- Do not introduce background schedulers, threads, or cloud jobs.

## Required Verification

Run after each slice:

```powershell
py -m py_compile api/webui/routes/routines.py api/webui/routes/routines_builtin.py api/webui/routes/routines_powergrader.py api/webui/routes/routines_custom.py
py -m pytest api/tests/test_route_contract.py
```

Run before final handoff:

```powershell
py -m pytest api/tests
py tools/size_report.py
```

Expected final result:

- `api/webui/routes/routines.py` should be mostly route orchestration and registry
  wiring.
- No new module should exceed roughly 500 lines.
- Full API tests should pass.

# PowerGrader Scheduled Auto-Score - Stage 1 Handoff

## Goal

Build the first safe implementation slice for teacher-scheduled PowerGrader
auto-scoring after an assignment due date.

This stage is **not** the full UX. It verifies the push plumbing first, then adds
a small queue foundation that later UI/routine work can use.

The teacher-facing intent is:

> When a teacher pushes a gradeable assignment, they can opt into "Auto-score with
> PowerGrader after due date." Canvas Expert records a local queue item and later
> creates PowerGrader AI drafts around `due_at + 6 hours`.

PowerGrader must still require teacher review before any Canvas grade/comment write.

## Current Context

- Branch: work on `dev`.
- Web UI is local-only FastAPI under `api/webui/`.
- PowerGrader routes are in `api/webui/routes/powergrader.py`.
- PowerGrader helpers are in `api/powergrader/`.
- PowerGrader session JSON is stored under `<workspace>/PowerGrader/` and is PRIVATE.
- Routines are local in-app automations in `api/webui/routes/routines.py`.
- The newest code already has PowerGrader late catch-up:
  - `api/powergrader/late_catchup.py`
  - route helper `_run_late_catchup_score(session)`
  - routine id `powergrader_late_catchup`
- Assignment/quiz push code:
  - `api/webui/routes/push.py`
  - `api/webui/push_service.py`
  - `api/webui/static/push.js`
  - `api/qf_pusher.py`
  - `api/push_tiers.py`

Before adding new queue behavior, verify that the push path returns the Canvas
assignment id needed by the queue. Do not assume URL parsing is enough.

## Guardrails

- Never commit secrets, tokens, student data, roster names, submission content, grades,
  or private PowerGrader session artifacts.
- Do not make the app reachable off-machine. Keep local-only behavior.
- Do not edit `LLM_Modules/*_Base.md`.
- Do not claim AI packets are guaranteed anonymous or FERPA safe.
- Do not automatically write grades/comments to Canvas from this queue. The queue may
  create AI draft suggestions only.
- Tests must use fake IDs/names only and monkeypatch Canvas/OpenRouter calls.
- Do not call OpenRouter in tests.
- Do not run live Canvas calls in tests.

## Important Product Decisions

1. Scheduled auto-score creates **PowerGrader draft sessions**, not Canvas grades.
2. Scheduling is local-only. If the app is closed, it catches up the next time Canvas
   Expert is open.
3. Default run time is `due_at + 6 hours`, checked by the existing routines heartbeat
   in a later slice.
4. Before a queued item runs, Canvas Expert must refetch the Canvas assignment and use
   the latest due date, because teachers may change due dates after push.
5. If the due date moved later, reschedule. If it moved earlier and the scheduled time
   has passed, the job can be marked due. If due date is removed or the assignment is
   inaccessible, mark `needs_attention`.
6. New Quizzes should not get full auto-score support in this slice. New Quizzes are
   Canvas/LTI quizzes, often auto-scored by Canvas, and item-level response/writeback
   remains limited. It is acceptable to produce an explicit unsupported status for quiz
   pushes.

## Submission Factors to Respect

Assignments are not all equivalent. Queue eligibility must be based on Canvas assignment
submission types and realistic PowerGrader support.

Supported for initial auto-score draft creation:

- `online_text_entry`
- `online_upload` when PowerGrader can extract useful text/code attachments through
  existing `canvas_fetch.enrich_with_code_files`
- `online_url` only as a queued/manual-review candidate unless existing PowerGrader
  behavior can score the URL content without new scraping

Not supported for auto-score draft creation in this slice:

- `none`
- `on_paper`
- `not_graded`
- `external_tool`
- `discussion_topic`
- `media_recording`
- `student_annotation`
- New Quizzes/quiz pushes

For mixed submission types, mark the job `needs_attention` or `unsupported` unless the
supported type clearly gives PowerGrader enough student response text. Do not silently
charge the teacher for an assignment where most work cannot be read.

Add one helper that classifies an assignment into:

- `eligible`
- `needs_attention`
- `unsupported`

with a short reason string safe to show in the UI. Use only assignment metadata, not
student submission content.

## Stage 1 Deliverables

### 1. Verify/Fix Assignment Push Result Plumbing

Inspect `api/webui/routes/push.py`, `api/webui/push_service.py`, and
`api/webui/static/push.js`.

Confirm:

- The AssignmentForge push button currently posts `kind="af"` through
  `/api/content/push`.
- The backend currently has or lacks a matching content pusher.
- A successful assignment push result exposes the created Canvas assignment id.

If `kind="af"` is missing from `_CONTENT_PUSHERS`, either:

- implement the smallest correct AssignmentForge pusher by reusing `api/webui/af.py`
  and `_push_assignment`, or
- if that is larger than this slice, add a failing/xfail-free regression test that
  documents the current breakage and clearly state it in the final answer.

Prefer fixing if the required behavior is straightforward.

`_push_assignment` currently returns `(ok, title, url, error)`. For queue support,
extend push result objects with `assignment_id` when Canvas returns it. Keep backward
compatibility for callers.

Suggested shape:

```python
{
  "course_id": "...",
  "course_name": "...",
  "ok": True,
  "title": "...",
  "url": "...",
  "assignment_id": "12345",
  "error": None,
  "notes": [],
}
```

Do not break existing banner rendering.

### 2. Add Queue Foundation Module

Create `api/powergrader/autoscore_queue.py`.

This module should be pure/local and offline-testable. It should not call Canvas or
OpenRouter directly. Route/routine code will inject fetch/run callbacks in later slices.

Provide these functions, with signatures close to:

```python
def queue_dir() -> str | None:
    ...

def queue_path() -> str | None:
    ...

def load_queue() -> dict:
    ...

def save_queue(queue: dict) -> None:
    ...

def classify_assignment_for_autoscore(assignment: dict) -> tuple[str, str]:
    ...

def scheduled_at_from_due(due_at: str, delay_hours: int = 6) -> str | None:
    ...

def make_job_id(course_id: str, assignment_id: str) -> str:
    ...

def upsert_job(
    *,
    course_id: str,
    course_name: str,
    assignment_id: str,
    assignment_name: str,
    due_at: str,
    delay_hours: int = 6,
    source: str = "push",
    settings: dict | None = None,
    assignment: dict | None = None,
) -> dict:
    ...

def reconcile_due_date(job: dict, latest_assignment: dict, now=None) -> dict:
    ...

def due_jobs(queue: dict, now=None) -> list[dict]:
    ...
```

Suggested queue file:

`<workspace>/PowerGrader/autoscore_queue.json`

Suggested queue schema:

```json
{
  "version": 1,
  "jobs": [
    {
      "job_id": "course-123_assignment-456",
      "course_id": "123",
      "course_name": "Period 1",
      "assignment_id": "456",
      "assignment_name": "Essay 1",
      "source": "push",
      "status": "scheduled",
      "eligibility": "eligible",
      "reason": "",
      "due_at": "2026-09-10T23:59:00-05:00",
      "delay_hours": 6,
      "scheduled_at": "2026-09-11T05:59:00-05:00",
      "settings": {
        "model_id": "",
        "rubric_name": "",
        "persona_id": "sage",
        "response_kind": "scr",
        "watch_late": true
      },
      "created_at": "2026-09-01T08:00:00",
      "updated_at": "2026-09-01T08:00:00",
      "session_id": "",
      "last_error": ""
    }
  ]
}
```

Use a list or dict internally, but preserve easy JSON readability.

Statuses for this slice:

- `scheduled`
- `needs_attention`
- `unsupported`
- `running`
- `session_ready`
- `cancelled`
- `failed`

`due_jobs` should only return jobs with status `scheduled`, eligibility `eligible`,
and `scheduled_at <= now`.

`reconcile_due_date` should:

- update `due_at`/`scheduled_at` if Canvas due date changes
- set `needs_attention` if latest due date is blank/unparseable
- keep `session_ready`, `cancelled`, and `failed` stable
- never create duplicate jobs

### 3. Do Not Add Full UI Yet

Do not implement the teacher-facing checkbox or queue page in this slice unless the
queue foundation is already complete and tests are passing. This handoff is meant to
make the next UI/routine slice cheap and safe.

### 4. Tests

Add focused tests.

Suggested files:

- `api/tests/test_powergrader_autoscore_queue.py`
- optionally `api/tests/test_push_service.py` or extend an existing push test if one
  already covers `/api/content/push`

Required test coverage:

1. `scheduled_at_from_due` adds six hours and preserves timezone-aware ISO behavior.
2. `classify_assignment_for_autoscore` returns:
   - eligible for text-entry
   - eligible or needs_attention for upload/code-file assignments, with clear reason
   - unsupported for `none`, `on_paper`, `external_tool`, `media_recording`,
     `student_annotation`, `discussion_topic`
3. `upsert_job` is idempotent for the same course/assignment.
4. `due_jobs` returns only scheduled eligible jobs whose scheduled time has passed.
5. `reconcile_due_date` reschedules when due date changes later.
6. `reconcile_due_date` marks `needs_attention` when due date is removed.
7. Push service returns `assignment_id` for successful assignment creation using fake
   Canvas responses.

If fixing `kind="af"`:

8. Add a test showing `_CONTENT_PUSHERS["af"]` exists and can create one whole-class
   AssignmentForge assignment from a fake file without live Canvas calls.

Run at minimum:

```powershell
py -m pytest api/tests/test_powergrader_autoscore_queue.py api/tests/test_route_contract.py
```

If you touch push service tests, also run that focused test file.

## Acceptance Criteria

- Local `dev` stays clean except intentional files for this slice.
- Queue module exists and is offline-testable.
- Queue stores no student data and no secrets.
- Assignment push results can provide `assignment_id`.
- Submission-type eligibility is explicit and conservative.
- Due-date reconciliation behavior is covered by tests.
- No automatic Canvas grade/comment write is introduced.
- No UI promises are added before the backend is ready.

## What Not To Touch

- Do not edit `LLM_Modules/*_Base.md`.
- Do not redesign PowerGrader queue UI.
- Do not add public hosting, non-local bind addresses, cloud schedulers, or OS task
  scheduler integration.
- Do not implement New Quizzes auto-score.
- Do not change the Feedback Scoring Contract.
- Do not commit workspace-generated PowerGrader/FeedbackExpert/session artifacts.

## Final Report Required

In your final answer, include:

- Files changed
- Tests run and result
- Whether `kind="af"` was already functional, fixed, or left as documented work
- Any remaining blocker for the next slice

# PowerGrader Late Catch-Up — Implementation Handoff

## Goal

Add a PowerGrader-owned late-work catch-up flow so a teacher can auto-score students
who submit after the original PowerGrader session was created.

Canonical example:

1. Teacher creates an Auto-Score With API PowerGrader session for an SCR due on 9/12.
2. 19 students have submitted; 3 are unsubmitted.
3. Later, those 3 students submit.
4. Canvas Expert detects only those new submissions, runs the same PowerGrader AI
   scoring setup on them, appends them to the existing review queue, and leaves the
   grades/comments as drafts until the teacher reviews and pushes.

Do **not** fold AI scoring directly into the Gradebook sweep. The existing sweep is
course-wide Canvas lateness-policy correction. PowerGrader owns assignment-specific
rubric/persona/model/source-context scoring.

## Guardrails

- Do not edit `LLM_Modules/*_Base.md`.
- Do not commit student data. PowerGrader sessions stay under the user workspace,
  not the repo.
- Do not log real student names, submission text, or comments in test output.
- Do not add any public routes or change local bind behavior.
- Do not auto-post AI grades to Canvas. This feature creates AI drafts only. Canvas
  writes still happen through the existing teacher review + push flow.
- Do not call OpenRouter in tests. Monkeypatch the AI workflow.
- Do not surprise-spend API credits from the broad Gradebook sweep. Any scheduled
  catch-up must only process sessions explicitly marked for late catch-up.

## Existing Code To Reuse

- `api/webui/routes/powergrader.py`
  - `pg_start`
  - `pg_get_session`
  - `pg_push_grades`
  - `_load_session`
  - `_save_session`
- `api/powergrader/canvas_fetch.py`
  - `fetch_submissions(course_id, assignment_id)`
  - `enrich_with_code_files(subs)`
- `api/powergrader/ai_workflow.py`
  - `run_ai_workflow(...)`
- `api/powergrader/session_builder.py`
  - `build_students(...)`
  - `build_session(...)`
- `api/powergrader/session_actions.py`
  - `push_grades(...)`
- `api/webui/gradebook_service.py`
  - late-date math patterns
- `api/webui/routes/routines.py`
  - local routine registration and execution patterns

## Files To Change

Required:

- `api/powergrader/late_catchup.py` — new helper module for filtering, metadata,
  append logic, and lateness payload preparation.
- `api/powergrader/ai_workflow.py` — allow reuse of the initial source context and
  a unique artifact label for late batches.
- `api/powergrader/session_builder.py` — store late-watch metadata on new sessions
  and include per-student late-catch-up metadata.
- `api/powergrader/session_actions.py` — when pushing an approved late-catch-up
  student, include Canvas lateness override in the same submission payload.
- `api/webui/routes/powergrader.py` — add late preview/score/watch routes and pass
  stored context into late scoring.
- `api/webui/templates/powergrader_setup.html` — add late-watch control for API mode.
- `api/webui/templates/powergrader_queue.html` — add late catch-up status/actions.
- `api/webui/static/powergrader_setup.js` — submit late-watch preference.
- `api/webui/static/powergrader_queue.js` — render late status and call preview/score.
- `api/webui/routes/routines.py` — add optional local routine trigger.
- `api/tests/test_powergrader_late_catchup.py` — new focused tests.
- `api/tests/test_route_contract.py` — add new route-contract entries.

Avoid unless absolutely necessary:

- `api/webui/gradebook_service.py` — use existing date math, but do not change
  sweep semantics.
- `api/webui/static/gradebook.js`
- `api/webui/templates/gradebook.html`
- Any authoring contracts under `LLM_Modules/`

## Session Schema Additions

Add this top-level object to sessions created by `session_builder.build_session`.
For existing old sessions, code must tolerate the object being absent.

```json
{
  "late_watch": {
    "enabled": true,
    "supported": true,
    "reason": "",
    "initial_missing_user_ids": ["101", "102"],
    "known_user_ids": ["201", "202"],
    "scored_user_ids": [],
    "last_checked": null,
    "last_scored": null,
    "last_summary": "",
    "source_context": {},
    "response_kind": "scr"
  }
}
```

Rules:

- `enabled` comes from the setup form. Default to `true` only for `mode == "assisted"`.
- `supported` is `true` only for `mode == "assisted"` and an OpenRouter key exists at
  session creation time.
- If unsupported, set `enabled: false` and a clear `reason`, for example
  `"Late catch-up requires Auto-Score With API."`
- `initial_missing_user_ids` is the set of unsubmitted Canvas rows at the original
  fetch time.
- `known_user_ids` is every user already represented in the session queue.
- `scored_user_ids` tracks users added by late catch-up so repeated checks are
  idempotent.
- `source_context` is the resolved source context used by the first AI scoring run.
  This is private session data and must remain in the workspace.
- `response_kind` is the response preset selected in setup.

For students appended by late catch-up, add:

```json
{
  "late_catchup": {
    "is_late_catchup": true,
    "submitted_at": "2026-09-13T15:20:00Z",
    "due_at": "2026-09-12T23:59:00Z",
    "school_days_late": 1,
    "seconds_late_override": 86400,
    "batch_id": "late-20260914-083000"
  }
}
```

Existing students should either omit `late_catchup` or set
`{"is_late_catchup": false}`. Omission is preferred.

## AI Workflow Changes

Update `api/powergrader/ai_workflow.py`.

Change `run_ai_workflow` signature by adding optional keyword-only params at the end:

```python
source_context_override: dict | None = None,
artifact_assignment_name: str | None = None,
```

Behavior:

- If `source_context_override` is supplied, do not call
  `context.build_source_context(...)`; use the supplied dict.
- Still run the same safety/privacy packet process.
- Use `artifact_assignment_name or assignment_name` for safe/private artifact and
  packet filenames so late batches do not overwrite the original session artifacts.
- Add `"source_context": source_context` to the returned dict so `pg_start` can store
  it in `late_watch.source_context`.
- Preserve all current return keys and behavior for existing callers.

Important edge case:

- If the original session used uploaded source files, the upload stream is gone later.
  That is why the resolved `source_context` must be stored at session creation time
  and reused for late catch-up.

## New Helper Module

Create `api/powergrader/late_catchup.py`.

Implement small, testable functions. Suggested signatures:

```python
from __future__ import annotations

def is_real_submission(sub: dict) -> bool:
    """True when Canvas row contains actual student work."""

def current_session_user_ids(session: dict) -> set[str]:
    """User IDs already present in session['students']."""

def find_new_submissions(session: dict, submissions: list[dict]) -> list[dict]:
    """Return actual submissions not already represented in the session."""

def initial_missing_user_ids(submissions: list[dict]) -> list[str]:
    """Return user IDs that were unsubmitted at initial session creation."""

def make_late_batch_id(now=None) -> str:
    """Return stable label like late-YYYYMMDD-HHMMSS."""

def compute_late_meta(
    *,
    sub: dict,
    assignment: dict,
    course_id: str,
    extra_time_days: int,
    skip_weekends: bool,
    holidays: set[str],
    batch_id: str,
) -> dict:
    """Return late_catchup metadata, including seconds_late_override."""

def attach_late_meta(students: list[dict], by_user_id: dict[str, dict]) -> list[dict]:
    """Mutate/return student rows with late_catchup metadata attached."""

def update_late_watch_after_preview(session: dict, new_count: int, now_iso: str) -> None:
    """Update last_checked and last_summary."""

def update_late_watch_after_score(session: dict, appended_user_ids: list[str], now_iso: str) -> None:
    """Update known/scored IDs, last_scored, last_summary."""

def apply_lateness_to_submission_payload(payload: dict, student: dict) -> dict:
    """If student has late_catchup metadata, add late policy fields under submission."""
```

Filtering rules:

- A real submission requires `submission_type` to be truthy and
  `workflow_state != "unsubmitted"`.
- Only add students whose `user_id` is not already in `session["students"]`.
- MVP does not rescore revised/resubmitted work from a student already in the queue.
  Add a warning/count for ignored resubmissions if useful, but do not implement
  rescore UX in this task.

Late-date rules:

- Use `sub.get("cached_due_date") or assignment.get("due_at")`.
- Use `sub.get("submitted_at")`.
- Use `config.get_sweep_settings()` and
  `config.get_combined_calendar_for_range().get("no_count_dates")`.
- Honor `config.get_extra_time(course_id)` by subtracting the student's extra days,
  as the routines sweep already does.
- Clamp `school_days_late` at `0`.
- If due/submitted is missing or unparsable, set `school_days_late: None` and omit
  `seconds_late_override`. Do not block scoring.

## PowerGrader Route Changes

Update `api/webui/routes/powergrader.py`.

### `POST /api/powergrader/start`

Add form param:

```python
watch_late: str = Form("true")
```

At initial fetch time:

- Keep the existing `submitted = [...]` logic.
- Also compute missing/unsubmitted IDs from the full `subs` list.
- After `ai_workflow.run_ai_workflow(...)`, store
  `ai_result.get("source_context")` in `late_watch.source_context`.
- Pass late-watch data into `session_builder.build_session`.

Do not fail session creation just because late watch is unsupported. Store the
unsupported reason.

### `POST /api/powergrader/session/{session_id}/late-watch`

Form params:

```python
enabled: str = Form("true")
```

Behavior:

- Load session.
- If session mode is not `assisted`, return `{ok: false, error: "...requires Auto-Score With API..."}`.
- Otherwise set `session["late_watch"]["enabled"]`.
- Save and return `{ok: true, late_watch: ...}`.

### `POST /api/powergrader/session/{session_id}/late-preview`

Behavior:

- Load session.
- Validate late watch exists and is enabled/supported.
- Fetch submissions for the session course/assignment.
- Use `late_catchup.find_new_submissions(...)`.
- Save `last_checked`.
- Return:

```json
{
  "ok": true,
  "new_count": 3,
  "students": [
    {
      "user_id": "101",
      "name": "Student Name",
      "submitted_at": "2026-09-13T15:20:00Z"
    }
  ],
  "message": "3 new late submission(s) found."
}
```

This endpoint must not call OpenRouter and must not write Canvas grades.

### `POST /api/powergrader/session/{session_id}/late-score`

Behavior:

- Load session.
- Validate:
  - `session["mode"] == "assisted"`
  - `late_watch.enabled == true`
  - `late_watch.supported == true`
  - OpenRouter key still exists
  - stored `source_context` exists
- Fetch submissions.
- Filter to new submissions only.
- If none, update `last_checked` and return `{ok: true, appended: 0}`.
- Call `canvas_fetch.enrich_with_code_files(new_submissions)`.
- Build a `batch_id = late_catchup.make_late_batch_id()`.
- Call `ai_workflow.run_ai_workflow(...)` with:
  - `submitted=new_submissions`
  - same course/assignment/rubric/persona/model/response kind as the original session
  - `source_context_override=session["late_watch"]["source_context"]`
  - `artifact_assignment_name=f"{session['assignment_name']} - Late Catch-Up {batch_id}"`
- Build student rows with `session_builder.build_students(...)`.
- Attach `late_catchup` metadata to the new rows.
- Append new rows to `session["students"]`, preserving existing rows.
- Append a log entry:

```json
{
  "ts": "2026-09-14T08:30:00",
  "batch_id": "late-20260914-083000",
  "appended": 3,
  "ai_scored": 3,
  "errors": []
}
```

Use key `late_catchup_log`.

Return:

```json
{
  "ok": true,
  "appended": 3,
  "ai_scored": 3,
  "batch_id": "late-20260914-083000",
  "session_id": "..."
}
```

If the AI workflow returns a privacy/cost/model error, do not append partial rows.
Return the error and privacy steps so the UI can show it.

## Push Behavior

Update `api/powergrader/session_actions.py`.

When `push_grades(...)` builds the Canvas payload for a student, call:

```python
late_catchup.apply_lateness_to_submission_payload(payload, st)
```

If the student has:

```python
st["late_catchup"]["seconds_late_override"]
```

then the same Canvas `PUT` payload should include:

```json
{
  "submission": {
    "posted_grade": "8",
    "late_policy_status": "late",
    "seconds_late_override": 86400
  },
  "comment": {
    "text_comment": "..."
  }
}
```

If score is absent but feedback exists, still include late policy fields under
`submission` when available. Do not send `seconds_late_override` when metadata is
missing or `None`.

## UI Changes

Keep the UI small and task-focused.

### Setup Screen

In `api/webui/templates/powergrader_setup.html`:

- Add a checkbox visible/enabled only when Auto-Score With API is selected:
  - label: `Watch for late submissions`
  - default checked
- Submit as `watch_late`.

In `api/webui/static/powergrader_setup.js`:

- Toggle visibility with the existing mode selection logic.
- Include the field in the start form payload.

### Queue Screen

In `api/webui/templates/powergrader_queue.html`:

- Add a compact late catch-up strip near the existing privacy/packet status area.
- It should contain:
  - status text
  - `Check Late Work` button
  - `Score New Late Work` button, hidden/disabled until preview finds work

In `api/webui/static/powergrader_queue.js`:

- Render `session.late_watch` after session load.
- `Check Late Work` calls `/late-preview`.
- If new count > 0, show `Score New Late Work`.
- `Score New Late Work` calls `/late-score`.
- On success, re-fetch `/api/powergrader/session/{session_id}` and re-render the queue.
- Do not auto-navigate away from the current student unless the session had no current
  students or the teacher is already at the end.

Student badges:

- For appended students, render a small `Late catch-up` badge.
- If `school_days_late` is numeric, render `Late catch-up · 1 school day late`.

## Routine Integration

After the backend and PowerGrader UI work, add a local routine.

Update `api/webui/routes/routines.py`.

Add routine definition:

```python
"powergrader_late_catchup": {
    "label": "PowerGrader late catch-up",
    "writes": False,
    "default": {
        "enabled": False,
        "every_hours": 12,
        "params": {"max_sessions": 10}
    },
}
```

Runner behavior:

- Iterate recent session summaries from `api.powergrader.session_store`.
- Load newest sessions first.
- Only process sessions where:
  - `mode == "assisted"`
  - `late_watch.enabled == true`
  - `late_watch.supported == true`
  - not already checked in this routine run
- Stop after `max_sessions`.
- Reuse the same backend helper used by `/late-score`; do not duplicate logic.
- Return concise lines:
  - `✓ Course / Assignment: 2 late submission(s) added to review`
  - `· Course / Assignment: no new late submissions`
  - `✗ Course / Assignment: <safe error>`

Important:

- This routine may call OpenRouter, but must not write grades/comments to Canvas.
- Do not include student names or submission text in routine lines.
- If no OpenRouter key exists, return a safe error and skip.

If the routines UI has no way to indicate “costs API credits,” add one short hint in
the routine label/summary text, not a large redesign.

## Tests

Create `api/tests/test_powergrader_late_catchup.py`.

Required tests:

1. `test_find_new_submissions_filters_unsubmitted_and_existing_students`
   - Existing session has student `1`.
   - Canvas rows include existing submitted `1`, new submitted `2`, unsubmitted `3`.
   - Only `2` is returned.

2. `test_initial_missing_user_ids_records_unsubmitted_rows`
   - Full Canvas rows include two unsubmitted rows.
   - Helper returns those user IDs as strings.

3. `test_late_preview_does_not_call_ai`
   - Monkeypatch `canvas_fetch.fetch_submissions`.
   - Monkeypatch `ai_workflow.run_ai_workflow` to raise if called.
   - Route returns new count and updates `last_checked`.

4. `test_late_score_appends_new_students_once`
   - Monkeypatch:
     - session load/save
     - Canvas fetch
     - enrich no-op
     - AI workflow returns `ai_by_uid` for one new user and `source_context`.
   - Call late-score twice.
   - First call appends one student.
   - Second call appends zero.

5. `test_late_score_reuses_stored_source_context`
   - Stored source context contains sentinel text.
   - Monkeypatched AI workflow asserts `source_context_override` has the sentinel.

6. `test_push_grades_includes_late_override_for_late_catchup_student`
   - Session has one approved late-catch-up student.
   - Monkeypatch `canvas_send` to capture payload.
   - Assert payload contains `posted_grade`, `late_policy_status: late`, and
     `seconds_late_override`.

7. `test_late_score_rejects_non_assisted_session`
   - Fast or packet session returns a clear error.

8. `test_late_score_does_not_append_on_ai_error`
   - AI workflow returns `{ok: False, error: "..."}`.
   - Saved session is unchanged.

Update `api/tests/test_route_contract.py` with these routes:

```python
('/api/powergrader/session/{session_id}/late-preview', ('POST',)),
('/api/powergrader/session/{session_id}/late-score', ('POST',)),
('/api/powergrader/session/{session_id}/late-watch', ('POST',)),
```

If adding the routine changes the route contract, it should not: routines already use
existing `/api/routines` routes.

Run:

```powershell
py -m pytest api/tests/test_powergrader_late_catchup.py api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_import_results.py api/tests/test_route_contract.py
```

If a wider change touches shared session action behavior, also run:

```powershell
py -m pytest api/tests
```

## Acceptance Criteria

- A new Auto-Score With API session records missing/unsubmitted students and stores
  enough scoring context to score later submissions without the teacher reselecting
  rubric/persona/model/source material.
- Preview detects newly submitted students without AI calls or Canvas writes.
- Score appends only new students to the existing session and is idempotent.
- New late-catch-up students show AI draft score/feedback in the existing review queue.
- Teacher push remains required before Canvas receives scores/comments.
- Pushing a late-catch-up student also applies the Canvas lateness override when the
  override can be computed.
- Optional routine can generate late drafts for explicitly watched sessions, but never
  posts grades/comments to Canvas.
- Tests above pass.

## Non-Goals

- Do not rescore students already present in the queue after a resubmission.
- Do not add automatic Canvas grade posting.
- Do not integrate AI scoring into `/api/sweep/apply`.
- Do not support packet/Copilot late catch-up in this task. Packet-mode late batches
  can be a later feature.
- Do not redesign the PowerGrader queue.

## Suggested Implementation Order

1. Add `late_catchup.py` helper functions and unit tests for filtering/date metadata.
2. Update `ai_workflow.run_ai_workflow` to support stored source context and artifact
   labels, preserving current behavior.
3. Store `late_watch` metadata during `pg_start`.
4. Add late-watch, late-preview, and late-score routes.
5. Update push behavior to include lateness override for late-catch-up students.
6. Add queue/setup UI controls.
7. Add optional routine runner that calls the same late-score backend logic.
8. Update route contract and run focused tests.

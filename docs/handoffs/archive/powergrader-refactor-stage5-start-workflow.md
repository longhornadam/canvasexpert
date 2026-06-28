# PowerGrader Refactor Stage 5: Split `pg_start()` Workflow

## Goal

Split the large `pg_start()` route into smaller workflow helpers while preserving behavior.

After this stage, `api/webui/routes/powergrader.py` should be under 500 lines.

## Files To Change

- `api/webui/routes/powergrader.py`

## Files To Create

- `api/powergrader/ai_workflow.py`
- `api/powergrader/session_builder.py`

## Current Problem

`pg_start()` currently mixes:

- Form validation.
- Workspace checks.
- Canvas fetch.
- Submission filtering.
- Code file enrichment.
- Roster context loading.
- AI packet creation.
- Privacy audit step construction.
- OpenRouter scoring.
- Student session row construction.
- Session save response construction.

This stage separates AI/packet workflow and session construction from the route.

## Create `ai_workflow.py`

Create:

```python
def run_ai_workflow(
    *,
    mode: str,
    submitted: list[dict],
    assignment_name: str,
    assignment_description: str,
    course_id: str,
    assignment_id: str,
    session_id: str,
    rubric_name: str,
    persona_id: str,
    selected_model: str,
    response_kind: str,
    source_text: str,
    source_files_json: str,
    source_uploads,
    has_openrouter_key: bool,
) -> dict:
    ...
```

Return a dict with this shape:

```python
{
    "ok": True,
    "error": "",
    "status_code": 200,
    "privacy_steps": [...],
    "privacy_artifacts": {...},
    "ai_by_uid": {...},
    "packet_zip": "...",
    "budget": None,
    "debug_path": None,
}
```

For failures, return:

```python
{
    "ok": False,
    "error": "...",
    "status_code": 200,
    "privacy_steps": [...],
    "privacy_artifacts": {...},
    "budget": optional_budget,
    "debug_path": optional_debug_path,
}
```

The route must use this result to build the same current `JSONResponse` payloads.

Move the logic currently starting at:

```python
if mode in AI_MODES and (mode != "assisted" or config.has_openrouter_key()):
```

through the corresponding `elif mode == "assisted":` and final fast-mode privacy step.

Important: Keep the same privacy step IDs, labels, statuses, and details.

Dependencies will include:

```python
import json

import feedback_pipeline as fp
import feedback_safety as safety
import openrouter_client as orc
from webui import config, source_materials, workspace
from powergrader import context, packet, privacy
```

Do not call Canvas from this module.

## Create `session_builder.py`

Create:

```python
def build_students(
    *,
    submitted: list[dict],
    ai_by_uid: dict,
    roster_settings: dict,
    tier_map: dict,
    monitored: dict,
    extra_time_map: dict,
) -> list[dict]:
    ...
```

Move the current student-list construction loop into this function.

Preserve every student field exactly:

- `user_id`
- `real_name`
- `body`
- `attachments`
- `code_files`
- `current_score`
- `status`
- `ai_score`
- `ai_feedback`
- `teacher_score`
- `teacher_feedback`
- `posted`
- `tier_id`
- `tier_label`
- `tier_alias`
- `is_monitored`
- `monitored_note`
- `extra_time_days`

Preserve sorting by lowercase real name.

Also create:

```python
def build_session(
    *,
    session_id: str,
    course_id: str,
    assignment_id: str,
    assignment_name: str,
    points_possible: float,
    mode: str,
    rubric_name: str,
    persona_id: str,
    selected_model: str,
    privacy_steps: list[dict],
    privacy_artifacts: dict,
    students: list[dict],
    mode_label,
) -> dict:
    ...
```

Move final session dict creation into this function.

Use:

```python
from datetime import datetime
```

Preserve all session keys and values.

## Update `pg_start()`

Final `pg_start()` should be shaped like this:

1. Validate `course_id` and `assignment_id`.
2. Validate workspace.
3. Normalize `mode`.
4. Create `session_id = str(uuid.uuid4())`.
5. Fetch submissions via `canvas_fetch.fetch_submissions(...)`.
6. Return current errors if Canvas fetch fails, no submissions exist, or no submitted work exists.
7. Compute:

   ```python
   assignment_name = adata.get("name") or assignment_id
   assignment_description = html_to_text(adata.get("description") or "")
   points_possible = float(adata.get("points_possible") or 100)
   ```

8. Filter submitted work exactly as before:

   ```python
   submitted = [
       s for s in subs
       if s.get("submission_type") and s.get("workflow_state") != "unsubmitted"
   ]
   ```

9. Call `canvas_fetch.enrich_with_code_files(submitted)`.
10. Call `ai_workflow.run_ai_workflow(...)`.
11. If AI workflow returns `ok=False`, return the same error payload shape that current code returns for that error.
12. Load roster context:

   ```python
   roster_settings = config.get_roster_student_settings(course_id)
   tier_map = config.roster_tier_by_id(course_id)
   monitored = config.get_monitored_students()
   extra_time_list = config.get_extra_time(course_id)
   extra_time_map = {str(et["id"]): et.get("days", 0) for et in extra_time_list}
   ```

13. Call `session_builder.build_students(...)`.
14. If `privacy_artifacts.get("private_folder")`, write the privacy audit exactly as current code does. You may either keep this small audit block in the route or move it to a helper, but do not change behavior.
15. Call `session_builder.build_session(...)`.
16. Save via `_save_session(session)`.
17. Return the existing success payload:

   ```python
   {
       "ok": True,
       "session_id": session_id,
       "student_count": len(students),
       "assignment_name": assignment_name,
       "mode": mode,
       "mode_label": _mode_label(mode),
       "ai_scored": len(ai_by_uid),
       "privacy_steps": privacy_steps,
       "packet_zip": privacy_artifacts.get("packet_zip"),
   }
   ```

## Do Not Do

- Do not change AI modes: valid modes remain `"fast"`, `"packet"`, and `"assisted"`.
- Do not change `AI_MODES = {"packet", "assisted"}` unless moving it to a module; if moved, preserve the value.
- Do not change privacy step text.
- Do not change OpenRouter budget checks.
- Do not change safety gate behavior.
- Do not change source material handling.
- Do not change session JSON.
- Do not change route decorators or endpoint paths.

## Suggested Extra Test

Add a small unit test in `api/tests/test_powergrader_packet.py` or a new `api/tests/test_powergrader_session_builder.py` that covers `session_builder.build_students(...)` with two fake submissions:

- One with `user.name`.
- One with only `sortable_name`.
- Include one attachment and one code file.
- Include one AI suggestion in `ai_by_uid`.
- Assert sort order, AI fields, attachment fields, and roster fields.

Use fictional names only, such as `Ada Example` and `Grace Sample`.

## Verification

Run:

```powershell
py -m pytest api/tests/test_powergrader_packet.py api/tests/test_route_contract.py
```

If you add the suggested new test file, run it too:

```powershell
py -m pytest api/tests/test_powergrader_session_builder.py
```

## Acceptance Criteria

- `pg_start()` is readable and mostly orchestration.
- `api/webui/routes/powergrader.py` is under 500 lines.
- No new PowerGrader backend module is over 500 lines.
- Existing focused tests pass.
- Route contract unchanged.
- PowerGrader behavior is preserved.

# PowerGrader Quiz Visibility Follow-up

Status: active handoff for a VS Code implementation agent.

## Goal

PowerGrader's assignment picker should not silently hide Canvas quizzes. Teachers
expect quizzes to appear when picking gradeable Canvas work, but the current
PowerGrader queue cannot reliably grade quiz item responses from the normal
Submissions API.

Implement the safe UX fix: show quiz-based assignments in the picker as
visible-but-disabled unsupported rows with a clear explanation. Do not make quiz
assignments startable in this handoff.

Full quiz-response grading is a separate Ferrari design slice.

## Read First

- `AGENTS.md`
- `docs/reference/powergrader-module-map.md`
- `api/README.md`, especially the confirmed New Quizzes limitations
- `docs/handoffs/powergrader-assignment-picker-vscode.md`

Relevant files:

- `api/webui/static/powergrader/setup_core.js`
- `api/webui/templates/powergrader_setup.html`
- `api/webui/static/powergrader_setup.css`
- `api/webui/routes/reports.py`
- `api/powergrader/session_builder.py`
- `api/powergrader/canvas_fetch.py`
- `api/powergrader/autoscore_queue.py`

## Current Facts

`GET /api/assignments-full` fetches Canvas assignments from:

```text
/api/v1/courses/{course_id}/assignments
```

That list can include quiz-backed assignment rows.

The current PowerGrader picker filters assignments in `setup_core.js` to these
startable submission types:

```javascript
[
  "online_text_entry",
  "online_upload",
  "online_url",
  "media_recording",
  "student_annotation"
]
```

Canvas quizzes are commonly represented by `online_quiz`, `quiz_id`, `quiz_type`,
or New-Quiz/external-tool metadata. Those are currently filtered out, so the
teacher sees only normal assignments.

Do not simply add `online_quiz` to the supported list. The queue renderer and AI
packet path currently rely on submission `body`, attachments, or downloaded
plain-text/code uploads:

- `api/powergrader/session_builder.py` stores `body`, `attachments`, and
  `code_files`.
- `api/webui/static/powergrader/queue_core.js` renders those fields.
- `api/powergrader/autoscore_queue.py` already treats quiz-based assignments as
  unsupported for scheduled auto-score.

New Quizzes item-level write-back remains blocked by Canvas PAT limitations, and
the normal Submissions API does not provide the item-level student text that
PowerGrader needs for grading.

## Required Behavior

When a course is selected:

1. Fetch the same `/api/assignments-full` payload as today.
2. Split assignments into:
   - `startableAssignments`: current PowerGrader-readable assignment types.
   - `unsupportedQuizAssignments`: quiz-backed rows.
3. Render both sets in the assignment picker/search results.
4. Startable assignments remain selectable.
5. Quiz rows are visible but disabled.
6. The teacher can search by quiz name and see that the quiz exists.
7. The teacher cannot start a PowerGrader session from a quiz row.
8. Show a small hint near the picker when unsupported quizzes are present:

```text
Quizzes appear here for visibility, but PowerGrader cannot grade quiz item responses yet. Use Canvas SpeedGrader or the New Quizzes Student Analysis CSV workflow.
```

Use existing wording/style conventions if there is already a better local hint
pattern nearby.

## Backend Enrichment

In `api/webui/routes/reports.py`, extend each assignment dict with non-breaking
quiz metadata:

```python
"is_quiz": bool(...),
"quiz_kind": "...",
```

Suggested detection:

- `online_quiz` in `submission_types` -> quiz.
- `quiz_id` present -> quiz.
- `quiz_type` present -> quiz.
- `external_tool_tag_attributes` URL or content type suggests quiz/New Quiz -> quiz.

Keep this conservative. If in doubt, set `is_quiz` only when a known Canvas field
strongly indicates quiz behavior. Do not make extra Canvas calls in this handoff.

Possible `quiz_kind` values:

- `classic_quiz`
- `new_quiz`
- `quiz`

The exact labels are less important than a stable boolean. Existing consumers of
`/api/assignments-full` must continue to work.

## Frontend Implementation Notes

In `api/webui/static/powergrader/setup_core.js`:

- Keep the current supported/startable submission type list unchanged.
- Add `online_quiz: "Quiz"` to display-label logic only.
- Add local state for unsupported quizzes, for example:

```javascript
var loadedAssignments = [];
var unsupportedQuizAssignments = [];
```

If the current search handoff already introduced `loadedAssignments`, preserve its
meaning as startable assignments and add a separate quiz list.

Suggested helpers:

```javascript
function isPowerGraderStartable(a) { ... }
function isQuizAssignment(a) { ... }
function unsupportedQuizLabel(a) { ... }
```

`isQuizAssignment(a)` should use the backend `is_quiz` field when present, with a
client-side fallback for `online_quiz`, `quiz_id`, and `quiz_type`.

Rendering:

- For flat `Recent due date` view, append an optgroup:

```html
<optgroup label="Quizzes - not supported yet">
  <option disabled>Quiz Name (quiz - not supported yet)</option>
</optgroup>
```

- For grouped views, it is acceptable to keep all unsupported quiz rows in a
  single `Quizzes - not supported yet` optgroup after the startable groups.
- Disabled quiz options should have an empty value or a prefixed value that cannot
  be submitted. Empty value is safest.
- Search should filter both startable assignments and unsupported quizzes by name.
- If only quizzes match the current search, keep the select enabled so the teacher
  can see the disabled quiz options, but no real assignment value should be
  selectable.
- If no startable assignments and no unsupported quizzes match, show the existing
  `No matching gradeable assignments` empty state.

Start-session behavior:

- Do not change `/api/powergrader/start`.
- Do not allow the hidden/disabled quiz option to submit an `assignment_id`.
- The existing client check `if (!cid || !aid)` should still block submission
  when only disabled quiz rows are visible.

## Template/CSS

In `api/webui/templates/powergrader_setup.html`, add one small hint element near
the assignment select if needed:

```html
<small id="pg-assignment-unsupported-hint" class="lbl-hint" hidden></small>
```

Use `setup_core.js` to show/hide and populate it when unsupported quizzes are in
the loaded course payload or current filtered result set.

In `api/webui/static/powergrader_setup.css`, add only minimal styling if existing
`.lbl-hint` styling is insufficient.

## What Not To Do

- Do not make quiz assignments startable.
- Do not add full Classic Quiz or New Quiz response fetching.
- Do not add New Quizzes report generation.
- Do not scrape Canvas pages.
- Do not change queue rendering, AI packet creation, import validation, grade
  push behavior, scheduled auto-score, or auto-push policy.
- Do not weaken local-only, secret, or FERPA guardrails.

## Verification

Run:

```powershell
py -m pytest api/tests/test_route_contract.py
```

Manual browser check:

```powershell
cd api
py qf_ui.py
```

Then open `http://127.0.0.1:8765/powergrader` and verify with a course that has
both assignments and quizzes:

1. Normal PowerGrader-supported assignments remain selectable.
2. Quiz-backed rows appear in search results.
3. Quiz-backed rows are disabled and clearly labeled unsupported.
4. Searching by a quiz name shows the quiz row.
5. Starting a session still requires a selectable supported assignment.
6. Grade Myself, Use My AI Chat, and Auto-Score With API behavior is unchanged.

## Acceptance Criteria

- Teachers can tell that quizzes exist instead of thinking PowerGrader failed to
  load them.
- Quizzes cannot accidentally create empty or misleading PowerGrader sessions.
- Existing supported assignment workflows still work.
- `/api/assignments-full` remains backward-compatible.
- `py -m pytest api/tests/test_route_contract.py` passes.

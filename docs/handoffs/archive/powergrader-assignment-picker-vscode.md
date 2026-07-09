# PowerGrader Assignment Picker Search + Grouping

Status: active handoff for a VS Code implementation agent.

## Goal

PowerGrader's setup screen currently loads gradeable Canvas assignments into one
plain `<select>`. In real courses that list can get long. Improve the setup
screen so a teacher can quickly find the right assignment by name and optionally
scan the same assignments by useful categories.

This is a UI/selection improvement only. It must not change how PowerGrader
fetches submissions, creates sessions, builds AI packets, scores, or pushes
grades/comments.

## Read First

- `AGENTS.md`
- `docs/reference/powergrader-module-map.md`
- `api/webui/README.md`, PowerGrader section

Relevant current implementation:

- `api/webui/templates/powergrader_setup.html`
- `api/webui/static/powergrader/setup_core.js`
- `api/webui/static/powergrader_setup.css`
- `api/webui/routes/reports.py`, endpoint `GET /api/assignments-full`
- `api/tests/test_route_contract.py`

## Current Behavior

On `/powergrader`, selecting a course calls:

```text
GET /api/assignments-full?course_id=<course_id>
```

`setup_core.js` filters the returned assignments to gradeable submission types:

```javascript
[
  "online_text_entry",
  "online_upload",
  "online_url",
  "media_recording",
  "student_annotation"
]
```

Then it renders all matching assignments as `<option>` rows in
`#pg-assignment`.

## Required UX

Add controls between the `Assignment` label and the assignment selection control:

1. Search input:
   - Placeholder: `Search assignments...`
   - Filters assignment names case-insensitively.
   - Filtering must use the already loaded assignment payload.
   - Do not call Canvas again while the teacher types.
   - Keep the selected assignment if it still matches the current filter.
   - Clear the selected assignment if it no longer appears in the filtered list.

2. Grouping select:
   - Label or compact inline text: `Group by`
   - Options:
     - `Recent due date`
     - `Assignment group`
     - `Submission type`
   - Default: `Recent due date`

3. Results display:
   - It is acceptable to keep using a native `<select>` if the grouping can be
     implemented cleanly with `<optgroup>`.
   - Use `<optgroup>` labels for grouped views.
   - For `Recent due date`, keep the current effective ordering from
     `/api/assignments-full`: downloadable/gradeable first, newest due date first.
   - For no matches, render a disabled option: `No matching gradeable assignments`.
   - While no course is selected, preserve the current disabled state and message:
     `- select course first -` or the existing em dash variant.

4. Assignment option labels:
   - Include the assignment name.
   - Include due date when present, e.g. `Lesson 4 Essay (due 2026-07-01)`.
   - Do not include student names, grades, or submission content.

## Backend Enrichment

Prefer a non-breaking extension to `GET /api/assignments-full` in
`api/webui/routes/reports.py`.

Currently each assignment includes:

```python
{
    "id": str(a["id"]),
    "name": a.get("name", ""),
    "submission_types": a.get("submission_types") or [],
    "due_at": (a.get("due_at") or "")[:10],
    "points_possible": a.get("points_possible"),
}
```

Add these fields if available from Canvas:

```python
"assignment_group_id": str(a.get("assignment_group_id") or ""),
"assignment_group_name": a.get("assignment_group_name") or "",
```

Canvas assignment list responses often include `assignment_group_id` but may not
include `assignment_group_name`. If name is not present, do not make extra Canvas
calls in this handoff just to resolve names. The UI should group missing names as
`Assignment group <id>` or `Ungrouped`.

Do not remove or rename existing response fields. This endpoint is shared by
Gradebook, FeedbackExpert, and Download Work.

## Module Grouping Decision

Do not implement true Canvas module grouping in this handoff.

Reason: module grouping is not part of the existing assignment payload. It would
require fetching modules and module items, and a single assignment can appear in
multiple modules or no module. That is a separate design slice.

If the user later asks for module grouping, build it as a PowerGrader-specific
assignment browser endpoint or helper that returns assignment IDs with module
tags. Do not force a single module label onto an assignment unless Canvas data
only has one module membership.

## Files To Change

### `api/webui/templates/powergrader_setup.html`

Update the Assignment area near `#pg-assignment`.

Suggested shape:

```html
<label>Assignment
  <div class="pg-assignment-tools" id="pg-assignment-tools" hidden>
    <input type="search" id="pg-assignment-search" placeholder="Search assignments..." autocomplete="off">
    <label class="pg-assignment-group-control">
      <span>Group by</span>
      <select id="pg-assignment-group-by">
        <option value="recent">Recent due date</option>
        <option value="assignment_group">Assignment group</option>
        <option value="submission_type">Submission type</option>
      </select>
    </label>
  </div>
  <select id="pg-assignment" name="assignment_id" required disabled>
    <option value="">- select course first -</option>
  </select>
</label>
```

Exact markup can differ, but keep:

- `#pg-assignment`
- `name="assignment_id"`
- `required`
- the form behavior used by `setup_core.js`

### `api/webui/static/powergrader/setup_core.js`

Add local state for the loaded gradeable assignments:

```javascript
var assignmentSearchEl = document.getElementById("pg-assignment-search");
var assignmentGroupByEl = document.getElementById("pg-assignment-group-by");
var assignmentToolsEl = document.getElementById("pg-assignment-tools");
var loadedAssignments = [];
```

Refactor `loadAssignments(cid)` so it:

1. Resets `loadedAssignments` when no course is selected.
2. Fetches `/api/assignments-full` once per course change.
3. Filters to PowerGrader-gradeable submission types.
4. Stores the filtered list in `loadedAssignments`.
5. Calls a new renderer, e.g. `renderAssignmentOptions()`.

Implement helpers:

```javascript
function assignmentMatchesSearch(a, query) { ... }
function assignmentDueLabel(a) { ... }
function primarySubmissionType(a) { ... }
function submissionTypeLabel(a) { ... }
function assignmentGroupLabel(a) { ... }
function renderAssignmentOptions() { ... }
```

Rendering rules:

- Escape all teacher/course-provided strings with existing `esc`.
- Preserve the existing selected assignment when possible.
- Use `<optgroup>` for `assignment_group` and `submission_type`.
- For `recent`, render flat options.
- Hide or disable `#pg-assignment-tools` until assignments are loaded.

Recommended type labels:

```javascript
{
  online_text_entry: "Text entry",
  online_upload: "File upload",
  online_url: "Website URL",
  media_recording: "Media",
  student_annotation: "Student annotation"
}
```

If an assignment has multiple gradeable types, group it under `Mixed` for
`Submission type`.

Wire events:

```javascript
assignmentSearchEl && assignmentSearchEl.addEventListener("input", renderAssignmentOptions);
assignmentGroupByEl && assignmentGroupByEl.addEventListener("change", renderAssignmentOptions);
```

### `api/webui/static/powergrader_setup.css`

Add compact styling for the assignment tools. Keep the setup card dense and
mobile-safe.

Suggested constraints:

- Tools should be one row on desktop and wrap on narrow screens.
- Search input should flex wider than the grouping select.
- Avoid nested cards.
- Use existing CSS variables such as `--ce-border`, `--ce-surface`, and
  `--ce-text-muted`.

### `api/webui/routes/reports.py`

Optional but recommended: add non-breaking assignment group metadata as described
above.

Do not change endpoint path or required params.

### `api/tests/test_route_contract.py`

No change should be needed unless a route is intentionally added. This handoff
should not add routes.

## Edge Cases

- No course selected: assignment select remains disabled.
- Canvas fetch fails: preserve existing failed-load behavior.
- Course has zero gradeable assignments: show `No gradeable assignments found`.
- Search has zero matches: show `No matching gradeable assignments`.
- Assignment has no due date: option label omits due date and sorting follows the
  backend order.
- Assignment has no assignment group name/id: group under `Ungrouped`.
- Assignment has multiple gradeable submission types: group under `Mixed`.
- Teacher changes course after typing search: clear the search field.

## What Not To Touch

- Do not touch `LLM_Modules/*_Base.md`.
- Do not alter PowerGrader session creation, queue behavior, AI packet creation,
  OpenRouter scoring, late catch-up, scheduled auto-score, or push-to-Canvas
  behavior.
- Do not add any public binding or non-local route behavior.
- Do not log Canvas tokens, student data, submission text, grades, or private
  roster details.
- Do not make module grouping part of this slice.

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

Then open `http://127.0.0.1:8765/powergrader` and verify:

1. Selecting a course loads assignments.
2. Search filters by assignment name without another Canvas fetch per keystroke.
3. Group by `Recent due date` shows a flat list.
4. Group by `Assignment group` shows optgroups.
5. Group by `Submission type` shows optgroups.
6. Selecting an assignment and starting a session still sends the correct
   `assignment_id`.
7. Grade Myself, Use My AI Chat, and Auto-Score With API controls still toggle as
   before.

## Acceptance Criteria

- PowerGrader setup has a searchable assignment picker.
- The picker remains keyboard-accessible through native form controls.
- Long assignment lists are easier to scan by assignment group or submission type.
- Existing consumers of `/api/assignments-full` still work.
- `py -m pytest api/tests/test_route_contract.py` passes.
- No secrets, student data, district config, or generated private workspace files
  are added to the repo.

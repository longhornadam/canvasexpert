# Handoff: Roster Console V1

**Lane:** Ferrari-planned, Toyota-implementable. **Status:** ready to implement.
This spec is self-contained. Read it fully before starting. If the spec and code
disagree, trust the code and note the difference in your final summary.

## Why

CanvasExpert now points teachers toward "Manage roster" from the home page, but
the implementation behind that link is still the older Name Manager. Name
Manager is useful for FeedbackExpert privacy work, but it is too narrow for the
job teachers actually want: one place to manage student-level facts that affect
the rest of the app.

V1 should create a real **Roster** tool where a teacher can load a course and
manage, in one screen:

- nicknames and pseudonyms for AI-safe work
- extra-time accommodation toggles and day counts
- local tier placement for differentiated planning
- Canvas group membership visibility
- monitored-student toggles and private notes
- sections, warnings, and roster-health signals

The existing pages may keep their focused workflows. The new Roster tool becomes
the canonical editing surface for student-level settings.

## Current state to reuse

Do not rebuild these pieces from scratch.

### Name privacy

Files:

- `api/webui/routes/names.py`
- `api/feedback_vault.py`
- `api/feedback_scrub.py`
- `api/webui/templates/name_manager.html`

Existing endpoints:

```text
GET  /api/names/roster?course_id=...
POST /api/names/nickname
POST /api/names/pseudonym
POST /api/names/pseudonym/regenerate
GET  /api/names/protected
POST /api/names/protected
GET  /api/names/collisions
POST /api/names/scrub-test
POST /api/names/who-is-who
POST /api/names/backup-vault
```

Important implementation details:

- `routes.names._fetch_students(course_id)` already fetches Canvas students with
  enrollments.
- `routes.names._upsert_roster(vault, users)` already anchors students by Canvas
  user id, assigns fake names, and captures `short_name` as a nickname.
- `feedback_vault.Vault.entries()` returns the privacy fields the UI needs.
- The vault lives in `FeedbackExpert/_system/vault/` via
  `workspace.feedback_folder("_vault")`. Keep using the alias; do not hard-code
  workspace paths.

### Extra time

Files:

- `api/webui/config.py`
- `api/webui/routes/gradebook.py`
- `api/webui/static/gradebook.js`
- `api/webui/templates/gradebook.html`

Existing storage and routes:

```python
config.get_extra_time(course_id) -> list[dict]  # [{id, name, days}]
config.set_extra_time(course_id, students)
```

```text
GET  /api/extra-time?course_id=...
POST /api/extra-time
GET  /api/students/list?course_id=...
```

The late sweep and extension tools already honor this roster. Roster V1 should
edit the same data, not create a second accommodation store.

### Monitored students

Files:

- `api/webui/config.py`
- `api/webui/routes/reports.py`
- `api/webui/templates/course_expert.html`

Existing storage and routes:

```python
config.get_monitored_students() -> dict
config.set_monitored_student(user_id, name, note="")
config.remove_monitored_student(user_id)
```

```text
GET  /api/students?course_id=...
POST /api/students/monitor
GET  /api/students/monitored
```

The monitored cohort is intentionally machine-local. Keep it that way. The note
is private and should never be rendered into student packets.

### Groups

Files:

- `api/webui/routes/courses.py`
- `api/webui/static/push.js`
- `api/webui/templates/course.html`
- `api/webui/static/course_info.js`

Existing route:

```text
GET /api/groups?course_id=...
```

This route already handles a real Canvas permission problem: some teacher tokens
get 403 for group categories but can still read course groups. Preserve that
fallback.

### Home page

Files:

- `api/webui/templates/dashboard.html`
- `api/webui/static/style.css`

The home page now includes a primary "Manage roster" job and Manage-lane links
to roster names, extra time, and course groups. These should point to the new
Roster page after this handoff.

## Guardrails

- No real district strings, roster exports, student names, Canvas ids, SIS ids,
  or private notes in source, tests, screenshots committed to the repo, logs, or
  browser console output.
- Keep Canvas token handling unchanged. Do not touch keyring storage or the
  onboarding gate.
- Do not add LLM calls. Roster management is local state plus Canvas API reads.
- Do not write Canvas group memberships in V1. Reading groups is in scope;
  storing a local tier/group plan is in scope. Direct group membership writes
  need a later explicit commit/confirm workflow because Canvas permissions and
  side effects are risky.
- Preserve existing `/api/names/*`, `/api/extra-time`, and `/api/students/*`
  endpoints. Other pages depend on them.
- If you add or intentionally change routes, update
  `api/tests/test_route_contract.py` in the same commit.

## Product shape

### Route and navigation

Add a new page:

```text
GET /roster
```

Keep the old route:

```text
GET /name-manager
```

Recommended behavior: make `/name-manager` a `302` redirect to `/roster`. This
keeps old bookmarks working while making Roster the canonical surface.

Add a topbar link named `Roster` in `api/webui/templates/base.html`, with
`nav_section == "roster"`. Do not rename the existing Expert nav links in this
handoff.

Update the dashboard links:

- primary "Manage roster" card: `/roster`
- Manage lane "Roster names": `/roster`
- Manage lane "Extra-time roster": `/roster?focus=extra-time`
- Manage lane "Course roster & groups": `/roster?focus=groups`

### Page layout

Create:

- `api/webui/templates/roster.html`
- `api/webui/static/roster.js`
- CSS additions in `api/webui/static/style.css`

Use existing visual primitives (`card`, `actions`, `status`, `hint`,
`dl-table`, `badge`, `small`, `primary`). Do not use emoji labels.

The first screen should be the tool, not explanatory marketing copy.

Suggested layout:

1. Toolbar card
   - course picker using active saved courses
   - `Refresh from Canvas` button
   - `Open Canvas People` link
   - status text

2. Summary strip
   - total students
   - extra-time count
   - monitored count
   - tier-unset count
   - warning count

3. Main roster table
   - search input
   - filters: All, Extra time, Monitored, Tier unset, Warnings
   - optional group-set filter
   - bulk action bar shown only when rows are selected
   - table columns:
     - selected checkbox
     - Student: display/sortable name plus section chips
     - Nicknames: comma-separated input, saved on blur or Enter
     - Pseudonym: first/last inputs plus regenerate button
     - Extra time: toggle plus day count input
     - Tier/group: local tier select plus live Canvas groups summary
     - Monitor: toggle, with note edited in the detail panel
     - Status: saved/warning/error

4. Detail panel
   - opens when a student row is selected
   - shows the same editable fields with more room
   - includes private monitor note
   - shows live Canvas groups and planned tier/group values

5. Secondary "AI safety" card
   - protected-name packs and custom protected names can stay behind a disclosure
     or a compact panel
   - scrub-test textarea
   - export who-is-who
   - back up vault

The roster table may use horizontal scrolling on small screens. Do not let
columns overlap or controls clip.

## Data model

### Unified row shape

The new roster API should return rows like this:

```json
{
  "id": "9001",
  "canvas_id": "9001",
  "name": "Student, Example",
  "display_name": "Example Student",
  "short_name": "Example",
  "sections": [{"id": "44", "name": "Period 1"}],
  "nicknames": ["Example"],
  "pseudonym": "Sparky McGee",
  "pseudo_first": "Sparky",
  "pseudo_last": "McGee",
  "extra_time": {"enabled": true, "days": 2},
  "monitored": {"enabled": true, "note": "Private teacher note"},
  "tier": "Support",
  "planned_group": {
    "category_id": "123",
    "category_name": "Reading tiers",
    "group_id": "456",
    "group_name": "Blue"
  },
  "canvas_groups": [
    {
      "category_id": "123",
      "category_name": "Reading tiers",
      "group_id": "789",
      "group_name": "Green"
    }
  ],
  "warnings": ["planned_group_mismatch"]
}
```

Do not return SIS id in the normal roster row. The who-is-who export may still
include SIS id because it is a private local export and already does today.

### Local roster settings

Add one synced settings key in `api/webui/config.py`:

```python
SYNCED_KEYS = (..., "roster_student_settings")
```

Add helpers:

```python
def get_roster_student_settings(course_id: str) -> dict:
    """{user_id: {tier, planned_group}} for a course."""

def set_roster_student_settings(course_id: str, settings: dict):
    """Replace local roster settings for one course."""

def update_roster_student_settings(course_id: str, user_id: str, patch: dict):
    """Patch one student's local roster settings."""
```

Only store these keys per student:

```json
{
  "tier": "Support",
  "planned_group": {
    "category_id": "123",
    "category_name": "Reading tiers",
    "group_id": "456",
    "group_name": "Blue"
  }
}
```

Valid tier values are `""` plus `config.TIER_NAMES`:

```python
["Support", "Core", "Accelerate", "Extend"]
```

This settings key contains Canvas user ids, so treat it as private synced
workspace data like `extra_time`. Do not put sample values in repo fixtures.

## API design

Create `api/webui/routes/roster.py` and register it from `api/webui/server.py`.

Use prefix `/api/roster`.

### `GET /api/roster`

Query:

```text
course_id=...
```

Behavior:

1. Require `course_id`.
2. Fetch students using `routes.names._fetch_students(course_id)`.
3. Upsert into the existing vault using `routes.names._upsert_roster(vault, users)`.
4. Fetch sections for the course and map enrollment `course_section_id` to names.
5. Fetch groups using the same logic as `/api/groups`.
6. Merge:
   - vault entries
   - Canvas student names and sections
   - `config.get_extra_time(course_id)`
   - `config.get_monitored_students()`
   - `config.get_roster_student_settings(course_id)`
   - live Canvas group membership
7. Return `students`, `groups`, `counts`, and any non-fatal notes.

If the Canvas student fetch fails, return `{"ok": false, "error": ...}` and do
not show a fabricated course roster. The older `/api/names/roster` endpoint can
fall back to global vault entries, but Roster must not present global vault data
as if it belongs to the selected course. If you want cached roster support, add
a course-scoped cache first and filter by `course_id`; do not use the global
vault as the cache.

### `POST /api/roster/student`

Form fields:

```text
course_id
user_id
patch
```

`patch` is JSON. Allowed keys:

```json
{
  "nicknames": ["Example", "Ex"],
  "pseudonym": {"first": "Sparky", "last": "McGee"},
  "regenerate_pseudonym": true,
  "extra_time": {"enabled": true, "days": 2, "name": "Student, Example"},
  "monitored": {"enabled": true, "name": "Student, Example", "note": "Private"},
  "tier": "Support",
  "planned_group": {
    "category_id": "123",
    "category_name": "Reading tiers",
    "group_id": "456",
    "group_name": "Blue"
  }
}
```

Rules:

- Unknown keys are ignored or rejected with a clear error. Prefer rejecting.
- Nicknames and pseudonyms must update the existing vault.
- Extra-time edits must update the existing `config.get_extra_time` list for the
  course. Preserve other students in that list.
- Monitor edits must use the existing machine-local monitor helpers.
- Tier and planned-group edits must use the new roster settings helpers.
- Return the updated row or at least `{ok: true}` plus refreshed counts.

### `POST /api/roster/bulk`

Form fields:

```text
course_id
user_ids
action
value
```

`user_ids` is JSON list of strings. `value` is JSON.

Support these actions:

```text
set_extra_time
clear_extra_time
set_tier
clear_tier
set_planned_group
clear_planned_group
set_monitored
clear_monitored
```

Bulk monitor actions may set a blank note only. Detailed private notes should
remain per student.

Return:

```json
{"ok": true, "updated": 12, "counts": {...}}
```

### Group helper refactor

In `api/webui/routes/courses.py`, extract the body of `list_groups(course_id)`
into a helper so both `/api/groups` and `/api/roster` can use it:

```python
def load_group_categories(course_id: str) -> tuple[list[dict], str | None, str]:
    """Return (categories, error, message). Preserve current fallback behavior."""
```

Keep `/api/groups` output shape unchanged.

## Warnings

Populate `warnings` as simple string codes. The UI can render friendly labels.

V1 warning codes:

```text
missing_pseudonym
extra_time_without_days
tier_unset
planned_group_mismatch
nickname_collision
protected_name_collision
```

Use `feedback_scrub.find_collisions(...)` for nickname/protected-name collision
signals. These warnings inform the teacher; they do not block saves.

## Files to change

Expected edits:

- `api/webui/config.py`
  - add `roster_student_settings` synced key
  - add roster settings helpers

- `api/webui/routes/courses.py`
  - extract group loading helper
  - preserve `/api/groups`

- `api/webui/routes/roster.py`
  - new router and merge/update endpoints

- `api/webui/server.py`
  - include roster router

- `api/webui/routes/pages.py`
  - add `/roster`
  - redirect `/name-manager` to `/roster`
  - pass `saved_courses`, `canvas_base`, `token_is_set`

- `api/webui/templates/roster.html`
  - new page

- `api/webui/static/roster.js`
  - new page behavior

- `api/webui/static/style.css`
  - roster-specific layout styles

- `api/webui/templates/base.html`
  - add topbar Roster link

- `api/webui/templates/dashboard.html`
  - update roster links to `/roster`

- `api/tests/test_route_contract.py`
  - add intentional new routes

Likely tests to add:

- `api/tests/test_roster_config.py`
- `api/tests/test_roster_routes.py`

## Implementation order

1. Add config helpers and tests for `roster_student_settings`.
2. Extract the group helper from `routes/courses.py`; verify
   `test_route_contract.py` still fails only for missing new routes.
3. Add `routes/roster.py` with `GET /api/roster`.
4. Add `POST /api/roster/student` and `POST /api/roster/bulk`.
5. Add `/roster` page and redirect `/name-manager`.
6. Add `roster.html`, `roster.js`, and CSS.
7. Update dashboard and topbar links.
8. Update route contract and run tests.

## Acceptance criteria

- Opening `/roster` with a configured token shows a course picker and loads the
  selected course roster from Canvas.
- A teacher can edit a nickname, reload the page, and see it persist from the
  existing vault.
- A teacher can edit a pseudonym or regenerate it; FeedbackExpert still uses
  the same vault value.
- A teacher can toggle extra time and set days; Gradebook's existing
  `/api/extra-time` endpoint reflects the change.
- A teacher can toggle monitored status and add a private note; existing
  student-report monitor endpoints reflect the change.
- A teacher can assign a local tier and planned group; reload shows the saved
  values.
- Live Canvas groups are visible per student when Canvas allows them. If Canvas
  group-category reads are forbidden, the existing fallback still produces
  useful group buckets.
- Bulk actions work for extra time, tier, planned group, and monitor toggles.
- `/name-manager` still works as an old bookmark and redirects to `/roster`.
- The dashboard "Manage roster" paths point to `/roster`.
- No normal roster API response includes SIS id.
- No browser console logging prints full roster rows, private notes, SIS ids, or
  Canvas tokens.
- The route contract test passes after intentional route additions.

## Tests

Run at minimum:

```powershell
py -m pytest api/tests/test_route_contract.py
py -m pytest api/tests/test_feedback_vault.py api/tests/test_feedback_scrub.py
py -m pytest api/tests/test_roster_config.py api/tests/test_roster_routes.py
```

If the test suite is reasonably fast after your changes, also run:

```powershell
py -m pytest api/tests
```

Manual smoke test:

```powershell
py qf_ui.py --no-browser --port 8765
```

Then open:

```text
http://127.0.0.1:8765/roster
```

Verify desktop and narrow mobile widths. The table may scroll horizontally, but
controls must not overlap or clip.

## Out of scope for V1

- Writing Canvas group memberships.
- Creating/deleting Canvas groups or group categories.
- Automatically using local tier placement to drive `push_tiers.py`.
- CSV imports for roster metadata.
- SIS exports beyond the existing private who-is-who export.
- Any OpenRouter, DeepSeek, GPT, or other LLM call.
- Renaming all "Expert" pages or rebuilding global navigation around verbs.

## Notes for future V2

The natural V2 is a "Commit group changes to Canvas" workflow:

1. Teacher selects a Canvas group set.
2. Roster shows live group membership versus planned group membership.
3. Teacher clicks `Preview Canvas group changes`.
4. App shows adds/removes by student and group.
5. Teacher explicitly confirms a Canvas write.
6. The app uses Canvas group-membership endpoints and handles 403 permissions
   clearly.

Do not sneak this into V1.

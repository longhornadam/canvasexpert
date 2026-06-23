# Roster Console V3: Canvas Groups Are the Tier Source of Truth

## Context

Roster V2 introduced a local per-student `tier_id` plus a local tier scheme:

- `roster_student_settings[course_id][user_id].tier_id`
- `roster_tier_schemes[course_id]`
- UI column `Tier / Alias`
- API actions `set_tier` / `clear_tier`

That is the wrong source-of-truth boundary for CanvasExpert.

Differentiated quiz/assignment pushing already uses Canvas group membership. See:

- `api/push_tiers.py`
- `api/webui/routes/push.py`
- `api/webui/static/push.js`
- `/api/groups`

If Roster maintains local tiers while push reads Canvas groups, the teacher can
see one truth in Roster and push a different truth to students. That is a
serious product bug.

## Product Decision

Canvas groups are the canonical tier assignments.

Roster may store local display metadata about Canvas groups, but it must not
store per-student tier/group assignment locally.

Correct model:

- Student assignment to Support/Core/Extend/etc. = Canvas group membership.
- Roster edits to a student's tier/group write Canvas group membership.
- Quiz/assignment push continues reading Canvas groups.
- Local config can label Canvas groups for teacher meaning:
  - Canvas group `Blue`
  - teacher label `Support`
  - display `Support / Blue`

Incorrect model:

- local `tier_id` says Support while Canvas group says White
- local planned group says Blue while Canvas group says Red
- Roster says "saved locally" for a field the push system expects from Canvas

## Scope

Implement V3 as a source-of-truth correction.

Do not add a second workflow or a "sync later" button for tier assignments.
The edit itself should update Canvas. This is roster management, not local
planning.

Keep the local-only behavior for:

- nicknames
- pseudonyms
- monitored flag
- notes
- protected-name settings
- extra-time planning, unless a separate Canvas accommodation workflow exists

Only the tier/group assignment column moves to Canvas.

## User-Facing Behavior

### Course Load

When a course loads:

1. Fetch Canvas students.
2. Fetch Canvas group sets/groups/memberships.
3. Select a differentiation group set.
4. Render each student's current group in that selected group set.

The default selected group set should be:

1. saved per-course preferred group set, if still present;
2. else a likely differentiation group set by name, such as a category including
   `tier`, `differentiation`, `diff`, `level`, or `groups`;
3. else the first Canvas group set;
4. if no group sets exist, show a clear empty state with a link to Canvas People
   / Groups.

### Table Column

Replace `Tier / Alias` with a Canvas-backed group column.

Recommended header:

`Canvas group`

Each row select should show options from the selected Canvas group set:

- `-- no group --`
- `Support / Blue`
- `Core / Red`
- `Extend / White`
- any additional Canvas groups in the selected group set

The option value must be the Canvas `group_id`, not a local tier id.

The row's status should say:

- `synced to Canvas` after successful Canvas membership write
- `not in group` when no group is assigned and no write just happened
- actual Canvas/API error text on failure

Do not say `saved locally` for the group column.

### Group Set Picker

Add a compact group-set picker near the course toolbar:

`Group set [Differentiation groups v]`

Changing the selected group set:

- refreshes row group options and current assignments
- does not alter Canvas membership
- saves only the preferred group set id locally for that course

### Display Labels

The app may preserve the Support/Core/Extend teacher vocabulary, but labels
must be attached to Canvas groups, not students.

Store a per-course/per-group metadata map, for example:

```json
{
  "course_id": {
    "group_category_id": "123",
    "group_labels": {
      "456": {
        "teacher_label": "Support",
        "meaning": "Below-level scaffolded version"
      },
      "789": {
        "teacher_label": "Core",
        "meaning": "On-level version"
      }
    }
  }
}
```

The Canvas group name remains the alias students/Canvas see.

Display formula:

- if teacher label exists and differs from Canvas group name:
  `Support / Blue`
- else:
  `Blue`

Do not create local fake groups.

### Bulk Actions

Bulk tier/group actions must write Canvas groups.

Bulk bar:

`Bulk edit: 3 selected | Canvas group [Support / Blue v] | Apply group | Clear group`

`Apply group`:

- for every selected student:
  - remove membership from other groups in the selected group set
  - add membership to target group if not already present

`Clear group`:

- remove membership from all groups in the selected group set for selected
  students

Show a toast with Canvas result:

`Updated 3 Canvas group memberships.`

If some writes fail, report partial failure with enough detail:

`Updated 2; failed 1: Canvas returned 403 adding Jane Doe to Blue.`

## API Design

### Extend Group Loading

Current helper:

```python
load_group_categories(course_id) -> tuple[list[dict], str | None, str]
```

Currently group objects include:

```json
{
  "id": "8",
  "name": "Blue",
  "student_ids": [101]
}
```

Extend this to include membership IDs where Canvas returns them:

```json
{
  "id": "8",
  "name": "Blue",
  "student_ids": [101],
  "memberships": [
    {"id": "555", "user_id": "101"}
  ]
}
```

Preserve the existing `student_ids` field for current push UI compatibility.

### Roster GET

`GET /api/roster?course_id=...`

Return:

```json
{
  "ok": true,
  "groups": [...],
  "selected_group_category_id": "123",
  "group_label_scheme": {...},
  "students": [
    {
      "id": "101",
      "canvas_group": {
        "category_id": "123",
        "category_name": "Differentiation",
        "group_id": "456",
        "group_name": "Blue",
        "teacher_label": "Support",
        "display": "Support / Blue"
      },
      "canvas_groups": [...]
    }
  ],
  "counts": {
    "group_unset": 5
  }
}
```

Remove or deprecate from normal row output:

- `tier_id`
- `tier_label`
- `tier_alias`
- `tier_display`
- `planned_group`

Keep `canvas_groups` for debug/context if useful.

### Roster Student Update

`POST /api/roster/student`

Accepted patch fields should include:

```json
{
  "canvas_group": {
    "category_id": "123",
    "group_id": "456"
  }
}
```

To clear:

```json
{
  "canvas_group": {
    "category_id": "123",
    "group_id": null
  }
}
```

Behavior:

1. Validate `category_id` belongs to the course.
2. Validate `group_id` is empty or belongs to that category.
3. Load current memberships for all groups in that category.
4. Remove the user from every other group in that category.
5. Add the user to target group if target is non-empty and membership does not
   already exist.
6. Return the updated group assignment.

Do not write `roster_student_settings.tier_id`.

For backward compatibility:

- if patch contains `tier_id`, return a clear error:
  `Local tier_id is obsolete; update canvas_group instead.`
- if patch contains legacy `planned_group`, either reject with the same style of
  clear error or no-op only for cleanup. Prefer rejection for new UI bugs.

### Bulk Update

`POST /api/roster/bulk`

Replace `set_tier` / `clear_tier` with Canvas-backed actions:

```json
{
  "action": "set_canvas_group",
  "value": {
    "category_id": "123",
    "group_id": "456"
  }
}
```

```json
{
  "action": "clear_canvas_group",
  "value": {
    "category_id": "123"
  }
}
```

Legacy `set_tier` and `clear_tier` should not silently write local data. Return:

`set_tier is obsolete; use set_canvas_group.`

### Canvas Membership Helpers

Add helpers in `routes/roster.py` or a small shared Canvas helper module.

Needed operations:

```python
def canvas_add_group_membership(group_id: str, user_id: str) -> tuple[bool, str | None]:
    ...

def canvas_delete_group_membership(group_id: str, membership_id: str) -> tuple[bool, str | None]:
    ...
```

Canvas endpoints:

- `POST /api/v1/groups/{group_id}/memberships`
  - form/json body: `user_id=<canvas_user_id>`
- `DELETE /api/v1/groups/{group_id}/memberships/{membership_id}`

Use existing Canvas header/base helpers. Handle 401/403/404 with explicit
messages. Do not swallow permission errors.

Important: do not use `student_id` if Canvas expects `user_id`. The existing
membership response uses `user_id`.

## Config Changes

The current local per-student roster settings helper may remain for nicknames?
No: nicknames are in the vault, extra time has its own config, monitored has
its own config. So student tier/group assignment should be removed from normal
use.

Add a new synced key for group display metadata, for example:

```python
roster_group_schemes
```

Suggested shape:

```json
{
  "<course_id>": {
    "selected_group_category_id": "<category_id>",
    "group_labels": {
      "<group_id>": {
        "teacher_label": "Support",
        "meaning": "Below-level scaffolded version"
      }
    }
  }
}
```

Default labels:

When groups are named `Blue`, `Red`, `White`, default display labels may map:

- Blue -> Support
- Red -> Core
- White -> Extend

But do not mutate Canvas group names automatically.

Remove new writes to:

- `roster_student_settings[course_id][user_id].tier_id`
- `roster_student_settings[course_id][user_id].tier`
- `roster_student_settings[course_id][user_id].planned_group`

Keep cleanup helpers only as migration/debt cleanup.

`roster_tier_schemes` can be left readable for migration but should no longer
drive the Roster UI.

## Frontend Changes

Files:

- `api/webui/templates/roster.html`
- `api/webui/static/roster.js`
- `api/webui/static/style.css`

Change:

- add group-set picker in toolbar
- replace `tierScheme` state with Canvas group state:
  - `groups`
  - `selectedGroupCategoryId`
  - `groupLabelScheme`
- replace row `.roster-v2-tier` select with `.roster-v2-canvas-group`
- replace bulk `set_tier` action with `set_canvas_group`
- replace `Clear tier` with `Clear group`
- remove tier alias editor or convert it into a "Group labels" editor

Group labels editor should edit local labels/meanings for Canvas group IDs. It
must not create/remove Canvas groups in this pass.

Status language:

- local-only fields: `saved locally`
- Canvas group field: `synced to Canvas`
- Canvas group field failure: actual Canvas error

## Warnings

Replace `tier_unset` with `group_unset` for the selected group category.

Warnings should include:

- `group_unset`
- `multiple_groups_in_selected_set`
- `missing_pseudonym`
- `extra_time_without_days`
- `protected_name_collision`
- `nickname_collision`

`multiple_groups_in_selected_set` matters because a student should usually be in
only one differentiation group for a given group set.

## Tests

Update/add tests in:

- `api/tests/test_roster_routes.py`
- `api/tests/test_roster_config.py`
- `api/tests/test_route_contract.py`

Required route tests:

1. `GET /api/roster` derives row group assignment from Canvas group membership.
2. `GET /api/roster` reports `group_unset` for students not in the selected group set.
3. `GET /api/roster` reports `multiple_groups_in_selected_set` when a student is in two groups in the selected set.
4. `POST /api/roster/student` with `canvas_group` removes old membership and adds new membership.
5. `POST /api/roster/student` with `canvas_group.group_id = null` removes memberships in selected category.
6. `POST /api/roster/student` rejects group IDs that do not belong to the selected category.
7. `POST /api/roster/student` rejects obsolete `tier_id` with a clear error.
8. `POST /api/roster/bulk` `set_canvas_group` updates all selected users.
9. `POST /api/roster/bulk` `clear_canvas_group` removes selected users from category groups.
10. Legacy `set_tier` does not write local tier data.

Config tests:

1. group label scheme round-trips by course
2. selected group category persists by course
3. default Blue/Red/White labels are applied only as display metadata

Keep the full suite passing.

## Migration Notes

Existing local `tier_id` values may exist from V2. Do not present them as truth.

Migration should be conservative:

- read old local tiers only to show a one-time warning or offer a migration
  helper later
- do not automatically push old local tier assignments into Canvas
- do not use old local tiers to drive row display

Optional non-blocking warning on course load:

`This course has old local tier assignments. Canvas groups are now the source of truth.`

No automatic Canvas writes from legacy data in this pass.

## Acceptance Criteria

- Roster group/tier dropdown options are real Canvas groups from a selected group set.
- Changing a student's group updates Canvas membership, not local `tier_id`.
- Reloading the roster reflects Canvas group membership.
- Bulk group assignment updates Canvas membership.
- Local tier/group assignment cannot diverge from Canvas because it is no
  longer written or displayed.
- Quiz/assignment push and Roster now look at the same source of truth.
- Status copy distinguishes local saves from Canvas syncs.
- Tests cover Canvas membership write success, validation, and failure paths.

## Explicit Non-Goals

- Creating Canvas group sets.
- Creating/deleting Canvas groups.
- Renaming Canvas groups.
- Auto-migrating local V2 `tier_id` values into Canvas.
- Changing `push_tiers.py` behavior unless a failing test proves it consumes the
  old local tier fields, which it should not.


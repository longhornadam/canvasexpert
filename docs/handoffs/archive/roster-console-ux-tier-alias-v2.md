# Handoff: Roster Console V2 - Compact Inline Editor + Tier Alias

**Lane:** Ferrari-planned, Toyota-implementable. **Status:** ready to implement.
This spec assumes Roster Console V1 exists in the worktree. Read
`docs/handoffs/roster-console-v1.md` for context, but follow this doc for the
next implementation.

## Product Decision

The V1 UI exposes `Tier` and `Group` as separate columns. That is conceptually
wrong for the teacher workflow.

In CanvasExpert, the teacher should assign one thing:

```text
Tier / Alias
```

The tier is the teacher's private instructional truth. The alias is the
Canvas-safe public label used to hide the instructional meaning.

Default scheme:

| Tier | Meaning | Alias |
| --- | --- | --- |
| Support | below-level | Blue |
| Core | on-level | Red |
| Extend | advanced | White |

Teacher-facing display should be compact:

```text
Support / Blue
Core / Red
Extend / White
```

Canvas/students should only ever need the alias side later (`Blue`, `Red`,
`White`). V2 does not write Canvas group memberships.

## Why

The current roster page is a good backend skeleton, but the UI still feels like
a dashboard wrapped around a table. Teachers need a dense working roster:

- less whitespace
- no repeated class pills beside every student
- inline editing in the roster list itself
- one tier assignment, not separate tier/group maintenance
- group/alias meaning clear enough that a teacher knows what Canvas sees

The purpose of CanvasExpert is to do things that Canvas UI either cannot do or
does awkwardly. This page should feel like an operational spreadsheet, not a
read-only People page.

## Current State

Relevant files:

- `api/webui/templates/roster.html`
- `api/webui/static/roster.js`
- `api/webui/static/style.css`
- `api/webui/routes/roster.py`
- `api/webui/config.py`
- `api/tests/test_roster_config.py`
- `api/tests/test_roster_routes.py`
- `api/tests/test_route_contract.py`

Current V1 behavior to change:

- table shows separate `Tier` and `Groups` columns
- row data includes `tier` and `planned_group`
- default validation uses `config.TIER_NAMES`, currently
  `["Support", "Core", "Accelerate", "Extend"]`
- most edits require the separate detail panel
- student names show section/class pills beside every name
- bulk tier action uses a browser prompt

Keep the V1 backend merge concept. Replace the user-facing tier/group model and
compress the UI.

## Guardrails

- Do not write Canvas group memberships in this handoff.
- Do not remove or weaken name privacy, pseudonyms, scrub-test, who-is-who, or
  vault backup behavior.
- Do not change keyring/token handling.
- Do not repurpose `config.TIER_NAMES` globally unless you verify every caller.
  It currently supports older tier-tag settings. Roster V2 should introduce its
  own tier scheme helpers.
- No real student names, Canvas ids, SIS ids, or private notes in tests.
- No browser `console.log` of roster rows, private notes, SIS ids, or tokens.

## Data Model

Add a new synced settings key:

```python
SYNCED_KEYS = (..., "roster_tier_schemes")
```

Do not store Canvas user ids in the scheme itself. It is not student-specific.

Default scheme:

```python
ROSTER_DEFAULT_TIER_SCHEME = [
    {
        "id": "support",
        "teacher_label": "Support",
        "meaning": "below-level",
        "alias": "Blue",
        "order": 10,
        "active": True,
    },
    {
        "id": "core",
        "teacher_label": "Core",
        "meaning": "on-level",
        "alias": "Red",
        "order": 20,
        "active": True,
    },
    {
        "id": "extend",
        "teacher_label": "Extend",
        "meaning": "advanced",
        "alias": "White",
        "order": 30,
        "active": True,
    },
]
```

Add helpers in `api/webui/config.py`:

```python
def get_roster_tier_scheme(course_id: str) -> list[dict]:
    """Return this course's tier scheme, or the default three-tier scheme."""

def set_roster_tier_scheme(course_id: str, scheme: list[dict]):
    """Validate and save this course's tier scheme."""

def roster_tier_by_id(course_id: str) -> dict:
    """Return {tier_id: tier_dict} for active + inactive saved tiers."""
```

Validation rules:

- `id` is required, stable, lowercase slug-like (`support`, `core`, `extend`).
- `teacher_label` is required.
- `alias` is required.
- `order` defaults to row order if missing.
- `active` defaults to true.
- duplicate ids are rejected.
- blank aliases are rejected because the alias is the Canvas-safe label.

### Student Settings Migration

Current V1 student settings use:

```json
{"tier": "Support", "planned_group": {...}}
```

V2 should use:

```json
{"tier_id": "support"}
```

Read behavior must be backward compatible:

- if `tier_id` exists, use it
- else if legacy `tier` exists, map by case-insensitive `teacher_label`
- else if legacy `tier` is unknown, create or surface a custom tier candidate
  rather than losing it

Write behavior should store `tier_id` and remove legacy `tier` and
`planned_group` for that student. `planned_group` is obsolete in V2.

Preserve unknown legacy tiers by appending them to the course scheme with:

```json
{
  "id": "<slugified legacy tier>",
  "teacher_label": "<legacy tier>",
  "meaning": "",
  "alias": "<legacy tier>",
  "order": 1000,
  "active": true
}
```

This avoids data loss for anyone who used `Accelerate` before this change.

## API Changes

Modify `api/webui/routes/roster.py`.

### `GET /api/roster`

Return `tier_scheme` with the response:

```json
{
  "ok": true,
  "tier_scheme": [
    {"id": "support", "teacher_label": "Support", "meaning": "below-level", "alias": "Blue", "order": 10, "active": true}
  ],
  "students": []
}
```

Each student row should include:

```json
{
  "tier_id": "support",
  "tier_label": "Support",
  "tier_alias": "Blue",
  "tier_display": "Support / Blue"
}
```

Remove `planned_group` from the normal V2 row shape. Keep `canvas_groups` as
read-only debug/context data if Canvas returns groups, but it should not be a
primary editable concept.

Warnings:

- replace `tier_unset` count logic to check `tier_id`
- remove `planned_group_mismatch`
- keep `tier_unset`

### `POST /api/roster/student`

Accept new patch key:

```json
{"tier_id": "support"}
```

Backward compatibility:

- still accept legacy `tier` for now and map it to a tier id
- still accept `planned_group`, but ignore it or clear it; do not save a new
  planned-group value

Reject tier ids not in the active scheme.

### `POST /api/roster/bulk`

Change `set_tier` value to use:

```json
{"tier_id": "support"}
```

Backward compatibility:

- legacy `{"tier": "Support"}` can still map by label

Remove or no-op `set_planned_group` and `clear_planned_group` from the UI. The
API can keep `clear_planned_group` as a cleanup action for old saved data, but
teachers should not see it.

### New Scheme Endpoints

Add:

```text
GET  /api/roster/tier-scheme?course_id=...
POST /api/roster/tier-scheme
```

POST form fields:

```text
course_id
scheme
```

`scheme` is JSON list of tier objects.

These endpoints are for the compact customization panel. Update
`api/tests/test_route_contract.py`.

## UI Changes

Modify `api/webui/templates/roster.html`,
`api/webui/static/roster.js`, and `api/webui/static/style.css`.

### Page Layout

Make the page dense.

Replace the current large card stack with:

1. compact toolbar row:

```text
Course [select] | Refresh | Canvas People | 23 students | Extra time 0 | Monitored 1 | Tier unset 23
```

2. compact filter/bulk row:

```text
Search | All | Extra time | Monitored | Tier unset | Warnings | bulk controls
```

3. the editable roster table

The summary should not need its own large card. It can be a row of text/chips
inside the toolbar or just below it.

### Remove Repeated Section Pills

Remove the class/section pill from beside each student name. The selected course
already provides context.

If sections matter later, use one of these instead:

- optional section filter
- hidden title/tooltip
- a compact column only when a course has multiple sections

Do not show the same class tag 23 times.

### Inline Editing

The common workflow must happen inside the roster table, not in a detail panel.

Table columns:

```text
Select | Student | Nicknames | Pseudonym | Extra time | Tier / Alias | Monitor | Note | Status
```

No separate `Groups` column.

Cell controls:

- `Nicknames`: text input, comma-separated, save on blur or Enter
- `Pseudonym`: text input showing full pseudonym plus small regenerate button
- `Extra time`: checkbox plus compact day input, e.g. `[x] +2`
- `Tier / Alias`: select whose option labels are `Support / Blue`, `Core / Red`,
  `Extend / White`, plus unset
- `Monitor`: checkbox or star button
- `Note`: small button/icon that opens an inline popover or row expansion for the
  private monitor note
- `Status`: saved/saving/error, quiet and compact

Use autosave per control:

- on change/blur, send `POST /api/roster/student`
- show row status `saving...`
- on success update local row state
- on failure show row status `error` and keep the user's edit visible

Avoid full-table refresh after every small save unless needed. Refreshing the
whole roster after each edit is too jumpy for a spreadsheet workflow.

The detail panel may remain as an optional expanded row or secondary panel, but
it must not be required for normal edits.

### Tier Scheme Customization UI

Add a compact `Tier aliases` disclosure above or below the table:

```text
Tier aliases
Support -> Blue
Core -> Red
Extend -> White
[Add tier]
[Save aliases]
```

Allow:

- edit teacher label
- edit meaning
- edit alias
- add tier
- deactivate/remove tier if no students use it, or mark inactive if students do
  use it
- reorder tiers if cheap; otherwise order by list order

Do not overbuild this into a settings page. Keep it in the roster page because
teachers need to see what they are assigning.

### Bulk Actions

Replace browser prompts with inline controls:

```text
3 selected | Set tier [Support / Blue v] | Set extra time [+2] | Monitor | Clear selected fields
```

Remove visible `Clear group`.

Bulk set tier should use `tier_id`.

## Files To Change

Expected edits:

- `api/webui/config.py`
  - add `roster_tier_schemes` synced key
  - add default three-tier scheme and helpers
  - keep `TIER_NAMES` unless all callers are updated intentionally

- `api/webui/routes/roster.py`
  - return tier scheme and tier display fields
  - accept `tier_id`
  - migrate/ignore legacy `tier` and `planned_group`
  - add tier-scheme endpoints

- `api/webui/templates/roster.html`
  - compact toolbar/filter/table
  - inline controls
  - tier alias customization disclosure
  - remove separate Groups column

- `api/webui/static/roster.js`
  - render inline editors
  - autosave changed cells
  - use tier scheme for select options
  - remove prompt-driven tier bulk action
  - remove visible planned-group actions

- `api/webui/static/style.css`
  - reduce roster page whitespace
  - dense table/editor styling
  - responsive horizontal scroll if needed

- `api/tests/test_roster_config.py`
  - default scheme tests
  - save/validate scheme tests
  - legacy tier migration tests

- `api/tests/test_roster_routes.py`
  - row returns `tier_id`, `tier_label`, `tier_alias`, `tier_display`
  - `POST /api/roster/student` accepts `tier_id`
  - legacy `tier` maps correctly
  - invalid `tier_id` rejected
  - tier-scheme endpoints validate/save
  - no `planned_group` in normal V2 rows

- `api/tests/test_route_contract.py`
  - add new tier-scheme routes

## Acceptance Criteria

- Roster page has visibly less whitespace than V1.
- Course/class pill is gone from student rows.
- The teacher can edit nicknames, pseudonym, extra time, tier, monitor, and note
  from the roster list itself.
- The normal table has one tier column labeled `Tier / Alias` or equivalent.
- No normal table column is labeled just `Groups`.
- Default tier options are exactly:
  - `Support / Blue`
  - `Core / Red`
  - `Extend / White`
- `Accelerate` is not part of the default roster scheme.
- Teachers can customize labels/aliases and add tiers.
- Changing an alias updates the select labels without changing student tier ids.
- Existing V1 saved `tier` strings still display correctly after the change.
- Existing V1 `planned_group` data does not break the page and is cleaned up on
  next student save.
- Bulk tier action uses a dropdown, not `prompt()`.
- No Canvas group memberships are written.
- `/api/roster` still returns no SIS id in normal row data.

## Tests

Run:

```powershell
py -m pytest api/tests/test_route_contract.py api/tests/test_roster_config.py api/tests/test_roster_routes.py
py -m pytest api/tests
```

Manual smoke:

```powershell
py api/qf_ui.py --no-browser --port 8765
```

Open:

```text
http://127.0.0.1:8765/roster
```

Verify:

- the table loads
- no class pills appear beside student names
- inline edit controls fit without clipping
- changing tier to `Support / Blue` saves and remains after refresh
- tier alias customization changes option labels
- no temp server remains after smoke testing

## Out Of Scope

- Writing Canvas group memberships.
- Creating Canvas group sets named Blue/Red/White.
- Using tier assignments to drive `push_tiers.py`.
- Rebuilding all global navigation around verbs.
- CSV import/export for tier assignments.
- Any OpenRouter, DeepSeek, GPT, or other LLM calls.

## Future V3

After this, a reasonable V3 is Canvas group alignment:

- map tier aliases to actual Canvas group names
- preview group membership differences
- explicitly confirm writes
- handle Canvas 403 permissions cleanly

Do not mix that into this UX/tier-alias pass.

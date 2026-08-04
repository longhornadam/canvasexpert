# Home Calendar actionable warnings

**Status:** ready for execution  
**Owner:** Web UI / Calendar  
**Risk:** low  
**Target branch:** `dev`

## Objective

Make Home an exception queue for Calendar configuration: show no Calendar warning when the
canonical calendar and its referenced Bell Schedules are ready, and otherwise name the exact
repair with a direct link to the relevant Calendar control. Do not introduce **School
Schedule** as a user-facing umbrella or title.

Teacher-visible outcome: the currently configured 2026-27 calendar no longer appears
unconfigured on Home. A real Calendar problem produces actionable, truthful copy rather than
the generic claim that no calendar exists.

## Required context

Read, in order:

1. repository-root `AGENTS.md`;
2. `docs/reference/project-state.md`;
3. this brief;
4. `docs/contracts/canonical-school-calendar-contract.md` sections **1, 4, 6, and 8**;
5. `api/webui/README.md`, section **Calendar module routing** only;
6. only the files named under **Authorized scope** below.

Do not read other handoffs. They are not authority for this batch.

## Repository truth already established

- `api/webui/routes/calendar.py:get_calendar()` loads Bell Schedules and calls
  `school_calendar.readiness(bell_schedule_ids=bell_schedules)`.
- `api/webui/routes/pages.py:dashboard()` calls `school_calendar.readiness()` without Bell
  Schedule IDs.
- `school_calendar.readiness()` interprets every instructional date whose `schedule_id` is
  absent from the supplied IDs as `unknown_schedule` and returns `needs_attention`.
- `templates/dashboard.html` translates every status other than `ready` into “No school
  calendar configured.”
- With the current local configuration, five valid Bell Schedules load with zero loader
  problems. The Home-style call returns `needs_attention` with 171 unknown-schedule dates;
  the Calendar-page call returns `ready` with zero unknown-schedule dates. Both resolve today
  as `no_school`.
- The worktree contains unrelated staged and unstaged Calendar work. Preserve it exactly and
  do not reformat or rewrite surrounding files.

## Locked product decisions

1. **Calendar is the surface name.** Do not add a Home card, page title, heading, or umbrella
   named “School Schedule.” Calendar may continue to contain school-year dates, Bell
   Schedules, and the teacher's class schedule as separate components.
2. **Home reports only concrete exceptions.** A ready Calendar produces no Calendar warning.
   A warning must state the actual condition and link directly to a control that can repair
   it.
3. **Home uses the same readiness context as Calendar.** Load the workspace Bell Schedules and
   supply their IDs to `school_calendar.readiness()`; do not weaken readiness validation or
   change `school_calendar.py` semantics.
4. **Teacher Schedule is not a Home Calendar gate.** Missing teacher blocks or course mappings
   remain contextual to features such as Panels. Do not add a general Home warning for them.
5. **Remove the old fallback claim.** Delete “every day counts as instructional” from Home.
   Canonical consumers fail closed; that sentence is not true.
6. **Keep active-course guidance.** The existing no-active-courses warning and Settings link
   remain, because they already name a concrete repair.
7. **No new registry or persistence.** Derive the small warning/action projection in the Home
   route or template from the existing readiness payload.

## Warning-to-action mapping

Render the following conditions. Exact punctuation may follow nearby house style, but the
condition, meaning, and destinations are locked.

| Readiness condition | Home message/action | Destination |
|---|---|---|
| `ready` | No Calendar warning | none |
| `unconfigured` | State that the school year and dates need to be set up; action: **Set up Calendar** | `/calendar#calendar-create-card` |
| `invalid_calendar` | State that Calendar could not read the saved school year; action: **Review and replace it** | `/calendar#calendar-create-card` |
| `needs_attention` and `today.state == outside_coverage` | State that Calendar does not cover today; action: **Extend or replace the school year** | `/calendar#calendar-create-card` |
| `needs_attention` with nonempty `unknown_schedule_dates` | State the count of dates that reference an unavailable Bell Schedule; offer both concrete repairs: restore/add the schedule or update the affected dates | `/calendar#calendar-bell-card` and `/calendar#calendar-change-card` |
| `needs_attention` with fewer than 30 `remaining_coverage_days`, while today is not already outside coverage | State the exact `coverage.end`; action: **Extend or replace the school year** | `/calendar#calendar-create-card` |

If unknown schedules and a coverage warning both exist, both actionable warnings may appear.
Do not duplicate the coverage warning when today is already outside coverage. Do not fall back
to “No school calendar configured” for `needs_attention`.

## Authorized scope

- `api/webui/routes/pages.py`
  - import/use the existing Bell Schedule loader;
  - call canonical readiness with the loaded schedule IDs;
  - pass the full readiness result or a small derived action list to Home.
- `api/webui/templates/dashboard.html`
  - render only the locked actionable messages and deep links;
  - keep the active-course warning behavior.
- `api/tests/test_desk_routes.py`
  - replace the generic-calendar assertions with deterministic state-specific route/render
    coverage;
  - prove the Home route supplies loaded Bell Schedule IDs to readiness;
  - prove `ready` renders no Calendar warning.
- `docs/contracts/canonical-school-calendar-contract.md`, section **6** only
  - add one concise durable rule: Home surfaces Calendar only for a concrete repair, uses
    reason-specific copy and an exact Calendar-section link, and does not expose a “School
    Schedule” umbrella.
- this brief, **Execution result** only.

No other file is authorized. In particular, do not change `school_calendar.py`, the Calendar
page/JavaScript, Gradebook, Panels, Settings, schedule storage, or authoring guides.

## Preflight

Before editing:

1. Confirm the branch is `dev`.
2. Record `git status --short` and preserve every pre-existing change.
3. Confirm these seams still exist:
   - `pages.dashboard()` calls `school_calendar.readiness()`;
   - `calendar.get_calendar()` passes loaded Bell Schedules to readiness;
   - Dashboard currently gates its generic Calendar paragraph on non-ready status;
   - the three Calendar anchors in the mapping exist in `templates/calendar.html`.
4. If any seam is absent or readiness no longer returns the fields used in the mapping, stop
   RED and report the contradiction. Do not invent a replacement contract.

## Acceptance criteria

1. A configured calendar whose instructional dates all reference loaded Bell Schedules
   produces no Calendar warning on Home.
2. Home calls readiness with the IDs/keys from the existing Bell Schedule loader; loader
   problem text and absolute paths are not exposed in the response.
3. Each non-ready state in the mapping renders truthful, condition-specific copy and the
   locked deep link(s).
4. `outside_coverage` does not also render the low-coverage warning.
5. Multiple independent actionable conditions may render without being collapsed into an
   inaccurate generic warning.
6. Home contains neither “No school calendar configured,” “every day counts as
   instructional,” nor a “School Schedule” title/umbrella.
7. Missing Teacher Schedule data alone does not create a Home warning.
8. The existing no-active-courses warning remains unchanged in meaning and still links to
   `/settings#current-courses-card`.
9. The focused gate passes, the rendered Home route has no template error, and no unrelated
   file changes.

## Test shape and named gate

Treat the parametrized warning mapping as a **contract** at the Home/readiness presentation
boundary, plus the existing ready render as the single happy-path **example**. Reuse the
nearest existing fixtures/helpers; do not add a test class.

Run:

```powershell
py -m pytest -p no:randomly api/tests/test_desk_routes.py
```

Also render `GET /` through the existing TestClient after the focused gate and inspect the
response for the ready case and at least one repair case. Because this batch changes no
JavaScript or shared browser assets, no broader route matrix or full API suite is owed.

## Explicit non-goals

- No broad Calendar-page redesign or terminology sweep.
- No rename of the canonical `School Calendar.json` artifact or Calendar service.
- No Teacher Schedule, Bell Schedule, or school-year editing changes.
- No Gradebook warning repair in this batch, even though Gradebook currently has a similar
  readiness call; keep this batch bounded to the user-requested Home behavior.
- No migration, compatibility shim, new status enum, new storage, or settings change.
- No branch creation, commit, push, or cleanup of unrelated work unless the user separately
  requests it.

## Stop conditions

Return RED without implementing if:

- the readiness payload cannot support the locked mapping without a public contract change;
- the Calendar anchors do not exist and repairing them would require changing an unauthorized
  file;
- the current worktree overlaps these exact lines in a way that cannot be preserved;
- the implementation would need to alter canonical calendar validation or storage.

Return YELLOW if implementation is complete but the named gate cannot run for an environmental
reason. Do not substitute a broad suite.

## Execution result

GREEN — implementation complete; no commit created.

Changed files:

- `api/webui/routes/pages.py`
- `api/webui/templates/dashboard.html`
- `api/tests/test_desk_routes.py`
- `docs/contracts/canonical-school-calendar-contract.md` (section 6 rule only)
- this brief (execution result only)

Verification:

- `py -m pytest -p no:randomly api/tests/test_desk_routes.py` — 15 passed.
- Existing TestClient `GET /` rendered with status 200 and no template error: the configured
  calendar produced no Calendar warning.
- A deterministic `unconfigured` TestClient render returned status 200 with the direct
  Calendar setup warning and `/calendar#calendar-create-card`; the Bell Schedule loader path
  was not exposed.

Deviations: none.

Unresolved decisions: none.

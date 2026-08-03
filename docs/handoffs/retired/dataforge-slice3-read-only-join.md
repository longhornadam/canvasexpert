# Brief: DataForge slice 3, read-only roster join

**Status:** Retired GREEN after senior acceptance on 2026-08-02. Slice 4 remains held until
the teacher reads a real coverage report, per the initiative decision.
**Batch:** DataForge merge initiative, slice 3 of 6.
**Baseline:** `dev` at the accepted slice-2 worktree state; preserve unrelated worktree edits.

## Teacher-visible outcome

On Assessments, a teacher can select a Current course and read a local coverage report showing
which pseudonym-keyed assessment records resolve through the private DataForge map and the
course's CanvasMirror roster. The report names the exact read-only join state before any future
group proposal is allowed.

This is the initiative's deliberate pause point: no group placement, no Canvas write, and no
live Canvas refresh belongs here.

## Required context, read only this

1. `AGENTS.md` and `docs/reference/project-state.md`.
2. `docs/handoffs/senior level/dataforge-merge-initiative.md`, sections 2.2, 4.4, 5.1, 5.2,
   5.3, 6, 7, 8.3, 8.4, 9, and 11 only.
3. `docs/reference/webui-presentation-system.md`, sections Template API, Page conventions,
   CSS ownership, and Change propagation.
4. `api/webui/README.md`, sections Rendered verification, Page map, and Assessments ownership.
5. `api/dataforge/eduphoria_parser.py`: `NameAnonymizer.linked_students` and
   `NameAnonymizer.link_coverage` only.
6. `api/dataforge/profile_export.py`: `build_profile` output shape only.
7. `api/dataforge/views.py`: result types and the existing Assessments view conventions.
8. `api/mirror/store.py`: `normalize_student`, `read_roster`, and roster validation shape only.
9. `api/webui/routes/assessments.py`, `api/webui/routes/roster.py`, and
   `api/webui/templates/assessments.html` only where needed for the read-only surface.
10. `api/tests/dataforge/test_canvas_join.py`, `api/tests/webui/routes/test_assessments.py`,
    `api/tests/test_route_contract.py`, and `api/tests/test_presentation_contracts.py`.

Do not preload group proposal/apply code, Canvas transport owners, MCP tools, or the full
roster architecture. They are outside this slice.

## Locked decisions

**L3.1.** Add one framework-free `api/dataforge/canvas_join.py` module for pure report
construction. It accepts the profile students, linked pseudonym→local-ID mapping, and
validated roster students; it does not import FastAPI, Starlette, Flask, Canvas clients, or
the web UI.

**L3.2.** The Assessments adapter may read `api.mirror.store.read_roster(course_id)` and pass
only the validated local roster document into the engine. It must never call the roster route's
live fallback or any Canvas client. A missing or non-current mirror is reported as unavailable
or stale, not refreshed implicitly.

**L3.3.** Match by trimmed string equality of Eduphoria `real_id` to roster `sis_user_id`.
One assessment pseudonym with no linked local ID is `missing_local_id`; a linked ID absent from
the roster is `not_in_roster`; a duplicated roster SIS ID is `ambiguous_roster`; exactly one
match is `matched`. Do not match by name, pseudonym, Canvas display name, or Canvas ID.

**L3.4.** The report is private, read-only HTML. It may show pseudonym, local ID, Canvas user
ID, and current roster display name because the teacher needs to diagnose coverage, but it is
never written to the workspace, published to `For AI`, returned through MCP, or logged.

**L3.5.** Add `GET /assessments/coverage?course_id=...` and a CE-native coverage template.
Course choices come from local Current-course configuration already held by CanvasExpert; the
coverage request itself consumes only the local CanvasMirror. The existing Assessments page
links to this report. No new top-level navigation slot or Students write control is added.

**L3.6.** A report includes mirror state/freshness, course label, profile and roster counts,
matched/unmatched counts, assessment-only rows with reason, and a clear empty/unavailable state.
It must not imply that a low-coverage report is ready for grouping.

## Files

### Add

- `api/dataforge/canvas_join.py`
- `api/webui/templates/assessment_coverage.html`
- `api/tests/dataforge/test_canvas_join_report.py`

### Modify

- `api/dataforge/views.py` — add the framework-free coverage view.
- `api/webui/routes/assessments.py` — add the read-only mirror adapter and route.
- `api/webui/templates/assessments.html` — link to coverage.
- `api/tests/webui/routes/test_assessments.py` — populated/unavailable coverage examples and
  proof that the adapter never falls back to live Canvas.
- `api/tests/test_route_contract.py` — registered coverage route.
- `api/webui/README.md` — Assessments ownership note.

Do not modify `api/webui/routes/roster.py`, Canvas transport owners, `api/requirements.txt`,
the profile format, or any group-apply path.

## Acceptance criteria

1. `canvas_join.py` has direct tests for every join state, duplicate SIS handling, counts,
   and no name-based fallback; all test data is synthetic and created under `tmp_path`.
2. `/assessments/coverage` renders the actual report context in the CE workspace layout,
   including matched and unmatched rows, mirror state, counts, and explicit unavailable/empty
   copy. It uses no inline styles and no new visual literals.
3. The adapter reads only `mirror_store.read_roster`; tests fail if a live roster fallback or
   Canvas client is invoked. The route is GET-only and has no mutation or transport-owner entry.
4. The route/presentation contracts, focused coverage/Assessments tests, full API suite, and
   `git diff --check` pass. `api/dataforge/` remains framework-free.
5. Rendered verification with lifespan disabled loads the Assessments index and coverage
   report states through the local server, confirms visible content, no horizontal overflow,
   and zero new browser console errors/warnings.

## Explicit non-goals

- Group proposal, tier calculation, no-data placement, group-set selection, or Canvas writes.
- Any live Canvas or roster refresh.
- Identity Vault migration or anonymization-map deletion.
- Profile schema changes, MCP exposure, or product-guide edits.
- Persisting or publishing the coverage report.

## Stop conditions

- A current roster is unavailable and the only way to continue would be a live Canvas call.
- Any match requires names, fuzzy matching, or a new identity namespace.
- A route needs POST/apply behavior, a Canvas transport entry, or a group mutation.
- The report cannot distinguish missing local IDs, SIS misses, and ambiguous roster data.
- Real student data, map files, or workbooks would enter the repository or test fixtures.

## Named verification gate

```powershell
py -m pytest api/tests/dataforge/test_canvas_join_report.py api/tests/webui/routes/test_assessments.py api/tests/test_route_contract.py api/tests/test_presentation_contracts.py -q
py -m pytest api/tests -q
git diff --check
```

Then perform the bounded rendered verification named in acceptance criterion 5. Report the
traffic light, changed files, test counts, rendered routes, browser-console result, deviations,
and unresolved decisions in this brief before senior acceptance.

## Execution result

**Traffic light:** GREEN. The framework-free SIS join, mirror-only coverage adapter, populated
and unavailable CE-native report states, and explicit no-name/no-live-fallback rules are
complete. No roster route, Canvas transport, group write, profile format, dependency, or MCP
surface changed.

**Changed files:** `api/dataforge/canvas_join.py`; `api/dataforge/views.py`;
`api/webui/routes/assessments.py`; `api/webui/templates/assessment_coverage.html`;
`api/webui/templates/assessments.html`; `api/webui/README.md`; route contract; and focused
DataForge/Assessments tests.

**Verification:** focused gate `25 passed`; final repeated full API suite `2062 passed`;
`git diff --check` passed; `api/dataforge/` has no web-framework imports. The first full-suite
attempt had one unrelated order-sensitive daily-writing privacy failure; that exact test passed
alone and the repeated full suite passed. Lifespan-disabled browser verification rendered the
Assessments index, empty coverage state, and populated coverage report with visible markers,
no horizontal overflow, active More navigation, and zero browser console warnings/errors.

**Deviations:** none in Slice 3. **Outstanding promotion gate:** the teacher must read a real
coverage report before Slice 4 can be promoted; synthetic verification is not that review.

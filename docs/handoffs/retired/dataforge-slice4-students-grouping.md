# DataForge merge — Slice 4: Students assessment grouping

Status: Accepted GREEN; retired after Slice 4 verification.

## Objective

Add the Students-page, assessment-driven grouping panel described by the DataForge
merge initiative. A teacher can select a local assessment snapshot, choose one of
the three locked tiering methods, explicitly place students with no assessment data,
preview the complete placement, and apply the reviewed placement through the
existing roster bulk group-write path.

The user has explicitly waived testing against real active courses during the current
off-season. Verification for this slice must use synthetic snapshots, roster records,
group sets, and mocked write calls only. The production workflow remains review-first;
the waiver does not authorize live Canvas writes.

## Required context

- `AGENTS.md`
- `docs/handoffs/senior level/dataforge-merge-initiative.md`, sections 2.1–2.2,
  4.2–4.4, 5.2–5.3, 6, 7, 9, and 11
- `api/dataforge/history_store.py`
- `api/dataforge/profile_export.py`
- `api/dataforge/canvas_join.py`
- `api/webui/routes/roster.py`
- `api/webui/routes/roster_updates.py`
- `api/webui/routes/roster_canvas.py`
- `api/webui/routes/roster_groups.py`
- `api/webui/templates/roster.html`
- `api/webui/static/roster.js`
- `api/webui/static/roster/bulk.js`
- `api/webui/static/roster/group_state.js`
- `api/webui/static/roster/groups.js`
- `api/operation_ledger/adapters/assignment_groups.py`

## Locked decisions

- The feature is a panel on the existing Students/roster page; do not create a new
  groups page or a second group-write transport.
- The panel is local-only and reads the current mirror roster plus offline DataForge
  assessment history. It must never fall back to a live Canvas read for preview.
- Tier names and order are fixed: `Support`, `Core`, `Accelerate`, `Extend`.
- Overall percentage uses the fixed default cutoffs `Support < 60`, `Core < 75`,
  `Accelerate < 90`, otherwise `Extend`; custom cutoffs are allowed only when they
  are strictly increasing and within 0–100.
- STAAR bands map `mas` to `Extend`, `met` to `Accelerate`, `app` to `Core`, and
  all other/invalid bands to `Support`, with the highest matching band winning.
- Quartiles place the lowest quarter in Support and the highest quarter in Extend,
  with deterministic tie-breaking. A method is invalid when any required tier would
  be empty.
- A no-data placement is required whenever the active roster has students without a
  matched assessment record. No-data students are placed in exactly one selected
  tier; omission is a validation error.
- A proposal is valid only when each active roster student is placed exactly once,
  no assessment-only student is placed, no tier is empty, and the selected Canvas
  group set contains exactly the four required group names without duplicates.
- Preview is the safety boundary. Apply is enabled only for the current preview and
  sends one request per tier to the existing `/api/roster/bulk` action
  `set_canvas_group`; no new Canvas transport or operation-ledger lane is added.
- Synthetic/mocked fixtures are the only acceptance-test data for this slice. No test
  may require an active course, a Canvas token, or a live Canvas request.

## In scope

- Pure proposal construction and validation under `api/dataforge/`.
- Read-only roster assessment-group sources and preview endpoints under the existing
  roster route family.
- Students-page grouping panel, preview summary, and guarded apply interaction.
- Focused unit/route/static tests and a rendered `/roster` check with no live course.

## Explicit non-goals

- No new Canvas client, transport owner, operation-ledger entry, or direct Canvas API
  call.
- No automatic group-set creation or mutation; the existing group builder remains the
  teacher-controlled way to create the four groups.
- No changes to assessment authoring, scoring, export formats, MCP tools, identity-vault
  storage, or the CanvasMirror join contract.
- No live-course, real-token, or student-data fixture testing.

## Acceptance criteria

1. The roster page exposes the locked panel controls for snapshot, method, cutoffs,
   required no-data placement, group set, Preview placement, and Apply.
2. Overall percentage, STAAR bands, and quartiles produce deterministic placements
   from synthetic input and reject invalid cutoffs, empty tiers, overlap, incomplete
   roster coverage, missing no-data placement, and invalid group sets.
3. Preview reads only the mirror roster and offline history; it returns a complete,
   inspectable placement summary and never invokes a Canvas client.
4. Apply is impossible before a successful preview and uses the existing bulk action
   once per non-empty tier, with no new transport path.
5. The focused Slice 4 gate passes, including proposal laws/examples, route contracts,
   frontend/static contracts, and mocked apply behavior. The existing API suite must
   remain GREEN or any unrelated baseline failure must be recorded exactly.
6. A local rendered `/roster` check passes with synthetic/off-season configuration:
   the panel is present, controls are usable, there is no horizontal overflow, and
   there are zero new browser console warnings/errors. No real course is required.

## Stop conditions

Stop and report RED/YELLOW if the existing roster bulk path cannot safely receive the
reviewed placements, if a preview requires live Canvas state, if a named source shape
does not exist, if exact roster coverage cannot be established, or if implementation
would require a new transport/ledger/public contract.

## Verification gate

Run the focused Slice 4 test paths named in the implementation and the synthetic
rendered `/roster` check. Do not run or require live-course verification. Run the full
API suite only if the focused gate exposes unexpected coupling or at the integration
checkpoint.

## Execution result

Traffic light: GREEN. Synthetic/off-season verification was used under the user's explicit
waiver; no active real course or live Canvas call was required.

- Full API gate: `py -m pytest api/tests -p no:randomly` — 2072 passed.
- Focused Slice 4 gate: `py -m pytest api/tests/test_presentation_contracts.py api/tests/dataforge/test_grouping.py api/tests/webui/routes/test_roster_assessment_groups.py api/tests/test_route_contract.py -p no:randomly` — 20 passed.
- Rendered `/roster` with an empty configured course list: grouping panel and all six required
  controls present; horizontal overflow false at 1280px; browser console warnings/errors zero.
- Changed implementation surfaces: `api/dataforge/grouping.py`,
  `api/webui/routes/roster_assessment_groups.py`, the Students template/static assets,
  server registration, route/presentation contracts, and synthetic tests.
- No new Canvas transport, operation-ledger entry, dependency, live-course test, or real
  student data was introduced.
- No unresolved Slice 4 decisions.

# Brief: assignment update write path (MCP)

**Status:** current
**Risk:** Medium (reversible Canvas content operation on existing objects)
**Senior decision date:** 2026-09-09

## Objective

An assistant can publish and re-date an assignment that already exists in Canvas,
through the standard preview/apply pair, without creating a second object and without
touching its description.

Today every authored object is a one-shot: `content.assignment` creates, and nothing
updates. A teacher correcting one due date or publishing a set of drafts mid-week gets a
checklist of manual clicks. This slice closes that for the two fields that actually block
a live week — `published` and the three dates.

## Locked decisions

### 1. A new operation kind. Do not change create-path drift.

Add `content.assignment_update` as its own adapter and registered kind.

`AssignmentAdapter.check_drift` returning `True` when a same-normalized-title assignment
exists is **not a bug**. It is the duplicate-create guard, locked in
`docs/reference/assignment-differentiation-design.md` → *Idempotency, drift, and retry*
("any pre-existing same-normalized-title assignment blocks the target, preserving the
existing whole-class invariant"). Redefining it to an `updated_at` comparison would strip
duplicate protection from every create path — assignment, quiz, page, rubric, quick
assignment. Leave `api/operation_ledger/adapters/assignment.py` alone.

The new kind gets the drift semantics an update needs: freeze the live assignment's
`updated_at` at preview, compare against a fresh GET at apply, block as `drift_detected`
when they differ.

### 2. Patch semantics. Only supplied fields are sent.

`None`/unset means *leave alone*, never *blank it*. Build the `assignment[...]` form body
from supplied fields only.

### 3. `description` is out of scope — permanently, not "until G4 is fixed".

The originating work order proposes putting raw assignment HTML into the mirror so a body
could round-trip. That contradicts `docs/contracts/course-catalog-contract.md`, which
makes the catalog a student-free navigation/search projection where raw HTML is never
retained, and it is unnecessary: patch semantics mean this path never reads or resends a
description, so nothing can flatten it. Do not add a `description` parameter, and do not
add HTML to the catalog. If a body edit is ever authorized, it reads live Canvas inside
the adapter at apply time — never through the catalog projection.

### 4. Target identity is the Canvas assignment id, supplied by the caller.

No title matching on this path. The caller passes `assignment_id`; the adapter GETs that
exact assignment. Title matching is a create-path concern and must not leak here.

### 5. One assignment per operation.

`published` moves in threes for differentiated content, but a batch publish is a separate
decision (see *Non-goals*). Ship the primitive first.

## Scope

| File | Change |
|---|---|
| `api/operation_ledger/adapters/assignment_update.py` | New. `KIND = "content.assignment_update"`. Full `OperationAdapter` protocol per `api/operation_ledger/registry.py`. |
| `api/operation_ledger/adapters/__init__.py` | Export `AssignmentUpdateAdapter`. |
| wherever adapters are registered | Register the new kind alongside the existing ones. |
| `api/content_push.py` | `preview_assignment_update(...)` / reuse `apply_content_push` if the frozen-review coordinates fit; add a sibling apply only if they do not. |
| `api/mcp_server/tools.py` | `preview_assignment_update`, `apply_assignment_update`. |
| `api/mcp_server/server.py` | Register both wrappers. |
| `api/mcp_server/contract.py` + `tool_schema_v41.json` | Bump `TOOL_SCHEMA_VERSION` to 41; add 41 to `_SUPPORTED_SCHEMA_VERSIONS`; write the new schema file. |
| `api/operation_ledger/catalog_reconcile.py` | Map the new kind to `catalog.assignments` (+ `catalog.modules` only if the slice ever attaches modules — it does not, so assignments alone). |
| `docs/contracts/canvas-transport-owners.json` | Register the new PUT owner. `api/tests/test_canvas_mutation_ownership.py` fails otherwise. |

### Tool signature

```
preview_assignment_update(
  course_id: str,
  assignment_id: str,
  published: bool | None = None,
  due_at: str = "",          # ISO 8601
  unlock_at: str = "",
  lock_at: str = "",
) -> { ok, operation_id, batch_id, review_digest, preview: { ... } }

apply_assignment_update(operation_id, batch_id, review_digest)
```

The frozen preview states, from the live GET: assignment name, and per changed field a
`{field, from, to}` row. A call that supplies no field at all is refused, not applied as
a no-op write.

Follow the existing MCP conventions exactly: `_course_gate_check` for the course gate,
`_with_next` on the preview, `_compact` at the server wrapper.

### Canvas call

```
PUT /api/v1/courses/:course_id/assignments/:id
    assignment[published]   assignment[due_at]   assignment[unlock_at]   assignment[lock_at]
```

Go through `api/platform_services/canvas_client` like every other adapter. `updated_at`
comes back on the assignment GET and is the drift anchor.

## Acceptance criteria

1. Preview against an existing assignment returns a field diff read from a **live GET**,
   not the mirror or catalog, and freezes `updated_at`.
2. Apply with unchanged `updated_at` succeeds and changes only the supplied fields. An
   assignment's `description`, `points_possible`, and `assignment_group_id` are byte-identical
   before and after.
3. Apply after the live assignment changed between preview and apply is blocked with
   `error_code: "drift_detected"`.
4. Re-applying the same frozen coordinates is a no-op with a clear status, not a second PUT.
5. A preview supplying no updatable field is refused with a clear error and no Canvas call.
6. The existing create path is unchanged: `test_assignment_operation.py::test_drift_detected_when_existing_found`
   still passes untouched.
7. `contract.load_contract()` and `live_contract(mcp)` agree at version 41.
8. `test_canvas_mutation_ownership.py` passes with the new PUT owner registered.

## Non-goals

- `description` on any update path (locked decision 3).
- Raw HTML anywhere in the catalog or mirror.
- Batch tools — `preview_publish_set`, `preview_assignment_bulk_dates`. They are thin
  batches over this primitive and are a separate decision once this one is proven.
- Assignment overrides and group membership. Overrides already ship
  (`adapters/assignment_tiered.py`, `adapters/quiz_differentiated.py`) using ad-hoc
  `student_ids[]`; the real gap there is an MCP differentiated-push twin for assignments,
  which is its own batch.
- `points_possible`, `name`, `omit_from_final_grade`, `post_to_sis`. Not blocking a live
  week; add on demand, not for symmetry.
- Module item management, catalog refresh exposure, group-set selection.
- Any live write against a real teaching course. See *Stop conditions*.

## References

Read only these:

- `api/operation_ledger/registry.py` — the adapter protocol.
- `api/operation_ledger/adapters/assignment.py` — nearest shape to copy; **do not edit**.
- `api/operation_ledger/executor.py` `_execute_target` — where `check_drift` is called and
  `drift_detected` is emitted.
- `api/content_push.py` `preview_content_push` / `apply_content_push` — the frozen-review
  and digest mechanism to match exactly.
- `api/mcp_server/tools.py` `preview_content_push` … `apply_content_push` (≈ lines 2069–2145)
  and `api/mcp_server/server.py` (≈ lines 340–378) — wrapper conventions.
- `api/mcp_server/contract.py` — version bump mechanics.
- `docs/contracts/operation-ledger-contract.md`.
- `docs/reference/assignment-differentiation-design.md` → *Idempotency, drift, and retry* only.
- `docs/contracts/course-catalog-contract.md` → the no-raw-HTML rule only.

## Verification gate

```powershell
py -m pytest api/tests/mcp_server/test_content_push_tools.py api/tests/mcp_server/test_tools.py api/tests/test_assignment_operation.py api/tests/test_canvas_mutation_ownership.py -p no:randomly
```

Plus new tests, placed to mirror the source tree, one of each kind that applies:

- **Law:** drift blocks when frozen `updated_at` differs from live.
- **Law:** an unsupplied field is absent from the PUT body.
- **Contract:** the v41 schema matches the live FastMCP registry.
- **Example:** one happy path — preview a date change, apply, assert the single PUT.

Canvas is faked at the `canvas_client` seam, as the existing adapter tests do.

## Stop conditions

- Stop if the frozen-review/digest mechanism in `content_push.py` cannot carry an
  id-addressed target without changing shared shape. That is a senior decision.
- Stop if registering a second assignment-touching kind changes `catalog_reconcile`
  behavior for the existing create kinds.
- **No live Canvas write against any course with real students.** The differentiation
  design requires a separately authorized disposable-course matrix for live writes, and
  that authorization does not exist for this slice. The acceptance tests in the
  originating work order (T1, T2, T5) name real assignment ids in a live section
  mid-unit; they are not the gate for this brief and must not be run as one.

## Execution result

_(executor fills in: traffic light, commit hash, changed files, commands and counts,
deviations, unresolved decisions)_

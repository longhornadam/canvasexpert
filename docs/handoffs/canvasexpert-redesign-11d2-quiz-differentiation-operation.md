# 11d2: QuizForge differentiated operation

## Objective

Extend `content.quiz` with server-owned differentiated variants and extra-time
override buckets. Same pattern as 11b4 (assignment differentiation). Browser
stays on legacy path. No live Canvas write.

## What to build

`build_payload` additionally accepts `{mode:"differentiated", variants:[{path,group_name}],
settings}` with at least two ordered variants. Run/validate the plan subprocess for each
path. Group name is a requested label, not authority.

For every target course reuse the 11b4 selected-category resolver
(`resolve_assignment_groups` in `api/operation_ledger/adapters/assignment_groups.py`):

- exact casefolded group-name match within `config.get_selected_group_category_id(course)`;
- nonempty, nonoverlapping referenced groups with exact active-roster coverage;
- safe baseline/review contains group/category IDs, names, counts, roster/membership digests;
- raw student IDs exist only in execute-local transient maps and Canvas override bodies.

Add an adapter-owned extra-time helper that applies `_split_for_extra_time` semantics in
memory. Freeze only ordered safe buckets `{bucket_index,kind,days,student_count,
membership_digest,due_at,lock_at}`. Never persist IDs/names. Recompute and require the exact
safe group/bucket snapshot at apply before any write.

## Per-variant execution

One course remains one target. For each variant in order:

1. `create_quiz:{variant}` — POST New Quiz; checkpoint quiz/assignment ID and URL.
2. `restrict_assignment:{variant}` — PUT the underlying assignment with
   `only_visible_to_overrides=true` before any possible publish.
3. `create_override:{variant}:{bucket}` — POST each transient ad-hoc student override and
   checkpoint its exact ID.
4. `create_item:{variant}:{item}` — POST each ordered item and checkpoint exact item ID.
5. `patch_assignment:{variant}` — apply requested dates/group/SIS/publish settings and
   verify the exact assignment.
6. `create_module` once per course if needed, then `attach_module:{variant}` for each quiz
   assignment with exact module-item ID verification.

Same-title matching never proves success. Before first write, unknown same-title New Quiz
assignments block. After partial execution, only exact IDs in durable steps are excluded
from drift. Missing returned IDs or uncertain transport are `sent_unknown`; definitive
failure after a prior successful step is `partial`; retry verifies exact completed IDs and
resumes the first unfinished step.

## Reference pattern

`api/operation_ledger/adapters/assignment.py` — the tiered assignment execution
(`_execute_tiered`) is the exact pattern. The quiz adapter (`api/operation_ledger/adapters/quiz.py`)
already implements whole-class execution; extend it with variant loops.

## Tests

Same test pattern as `api/tests/test_assignment_tier_operation.py` and
`api/tests/test_quiz_operation.py`. Prove: group resolution, extra-time buckets,
per-variant create/restrict/override/item/patch/module order, each failure mode,
retry resumption, reconciliation, PII safety (no student IDs in review/baseline).

```powershell
py -m pytest api/tests/test_quiz_operation.py api/tests/test_operation_routes.py api/tests/test_route_contract.py
py -m pytest api/tests
```

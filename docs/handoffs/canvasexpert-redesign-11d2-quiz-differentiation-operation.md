# Toyota handoff 11d2: QuizForge differentiated operation

## Prerequisite and objective

After Ferrari accepts 11d1, extend `content.quiz` with server-owned differentiated variants
and extra-time override buckets. One commit. Do not migrate browser live controls, add
progress SSE, or shut down legacy routes yet. No live Canvas write is authorized.

## Request, group, and privacy contract

`build_payload` additionally accepts `{mode:"differentiated", variants:[{path,group_name}],
settings}` with at least two ordered variants. Run/validate the accepted plan subprocess for
each path. Group name is a requested label, not authority.

For every target course reuse the accepted 11b4 selected-category resolver:

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

1. Execute/verify `create_quiz:{variant}`.
2. `restrict_assignment:{variant}` — PUT `only_visible_to_overrides=true` on the exact Core
   assignment and verify it **before** override/item/publish work.
3. For every transient standard/extra-time bucket, execute/verify
   `create_override:{variant}:{bucket}` with ad-hoc `student_ids` and applicable due/lock
   dates. Persist only request digest over safe membership digest/settings, never raw IDs.
4. Execute/verify all `create_item:{variant}:{item}` steps.
5. Execute/verify `patch_assignment:{variant}` for remaining requested effects. Publication,
   if requested, occurs only after visibility and override steps succeed.
6. Attach each assignment to the shared requested module with `attach_module:{variant}`.

Review lists every course/variant source label, group name/count, item count, extra-time
bucket counts/date effects, and warns that each group receives a separate New Quiz. It never
renders IDs or source paths.

Uncertain/missing-ID results stop downstream work as `sent_unknown`. Definitive failure
after any successful write is `partial`. Retry and reconcile verify every quiz, visibility
patch, override, item, assignment patch, and module item by exact returned ID/postcondition;
unknown same-title objects still block. No roster splitting fallback, group mutation, or
same-title success proof is allowed.

## Tests and verification

Add differentiated focused tests for group happy/fallback and every missing/ambiguous/
empty/overlap/coverage/read failure; extra-time standard/multi-day buckets; PII-negative
ledger/review/receipt/diagnostic; exact write order; visibility-before-overrides; correct
transient IDs; ambiguity at every POST; partial/retry/restart reconciliation; unknown-title
drift; multi-course independent group resolution; whole-mode nonregression.

```powershell
py -m pytest api/tests/test_quiz_differentiated_operation.py api/tests/test_quiz_operation.py api/tests/test_assignment_tier_operation.py api/tests/test_operation_ledger.py
py -m pytest api/tests
git diff --check
```

Stop if group resolution requires client IDs, extra-time buckets cannot stay transient,
visibility cannot be verified before publication, or exact override/item reconciliation is
unavailable. Report commit/files, group/bucket/write matrices, PII/partial/retry/recovery
evidence, counts, no-live-write evidence, and leave the handoff active.

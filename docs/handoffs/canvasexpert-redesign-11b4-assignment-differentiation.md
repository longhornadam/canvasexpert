# Ferrari gate 11b4: AssignmentForge differentiation

## Status

Deferred. This file is a discovery/design gate, not implementation authorization.

## Objective

Define the teacher-visible, Canvas-safe, idempotent operation model for AssignmentForge
tiers before any differentiated assignment write is enabled in the operation adapter.
Whole-class AssignmentForge and scheduled Auto-Score are already handled by accepted
slices 11b1-11b3/11r; they must not be reopened here.

## Unresolved Ferrari decisions

Ferrari must inspect the current `af.tier_payloads` output, legacy tier/group helpers,
Canvas assignment override/group APIs, group-set ownership, and all callers/tests, then
specify:

- whether tiers are one assignment with differentiated overrides or multiple assignments;
- how student/group membership is sourced and reviewed without persisting PII in the repo;
- ownership and reuse rules for Canvas groups and group sets;
- exact returned IDs and postconditions for every created assignment, override, group,
  membership, file, module item, rubric association, and scheduled job;
- deterministic idempotency and reconciliation after timeout/disconnect at every step;
- partial/retry order and which downstream effects are blocked by each failure;
- teacher review wording, unsupported cases, and rollback boundaries;
- portable fake-Canvas tests and the explicitly authorized disposable-course live matrix.

## Current invariant

`AssignmentAdapter.build_payload` must continue rejecting files with `tiers`. The legacy
AssignmentForge path must also continue failing closed for tiered content. No UI may imply
that differentiated AssignmentForge push is available until this gate is replaced by a
self-contained Toyota handoff and accepted sequentially.

## Required discovery evidence

```powershell
rg -n "tier_payloads|tiers|differenti|group_category|assignment_override|student_ids" api docs LLM_Modules
py -m pytest api/tests/test_assignment_operation.py api/tests/test_push_service.py api/tests/test_route_contract.py
git diff --check
```

Document exact symbols, load/call order, Canvas objects, discrepancies, and stop
conditions in a durable `docs/reference/` note. Do not perform live Canvas writes during
discovery.

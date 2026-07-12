# Archived handoff 11b3: AssignmentForge scheduled scoring

## Objective

Add scheduled PowerGrader job creation to the accepted assignment adapter without
changing privacy or scheduled-auto-push policy.

Edit the assignment adapter, autoscore queue helpers, Assignment UI summary, and focused
scheduled tests. Review must state schedule/model/budget settings and whether this
specific job opted into auto-push. Queue creation occurs only after the assignment ID is
durably confirmed.
Queue job ID is a durable step result with its own deterministic identity; partial Canvas
success never duplicates it. Changing policy invalidates review. Test budget/policy
blocks, assignment success + queue failure, retry, repeat, and SAFE/PRIVATE parity.

Run assignment operation, scheduled-autoscore/autopush-policy, route, JS, and diff checks.
Stop if global/default auto-push would be introduced. One commit; reply with policy
matrix, target receipts, and no-live-write evidence.

## Ferrari scope correction and acceptance

The original combined 11b3 objective was not Toyota-ready: differentiation requires a
separate decision on Canvas group ownership, variant identity, partial recovery, and
teacher-visible semantics. Ferrari split that work into deferred slice 11b4 rather than
claiming it was implemented here.

The scheduled-scoring portion was accepted 2026-07-11 through repair commit `a2d6617`:
the queue write is a durable `schedule_autoscore` step, the deterministic job ID is
checkpointed, queue failure yields partial truth while retaining the assignment ID, and
retry clears stale diagnostics without duplicating the job. Full API result: 474 passed,
1 skipped. No live Canvas write was performed.

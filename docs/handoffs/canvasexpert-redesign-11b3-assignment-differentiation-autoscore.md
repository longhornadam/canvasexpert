# Toyota handoff 11b3: assignment differentiation and scheduled scoring

## Objective

Add target variations/differentiation and scheduled PowerGrader job creation to the
accepted assignment adapter without changing privacy or scheduled-auto-push policy.

Edit the assignment adapter, existing differentiation and autoscore queue helpers,
Assignment UI summary, and focused scheduled tests. Review must state every differentiated
Canvas effect, schedule/model/budget setting, and whether this specific job opted into
auto-push. Queue creation occurs only after the assignment ID is durably confirmed.
Queue job ID is a target result with its own idempotency key; partial Canvas success never
duplicates it. Changing policy invalidates review. Test variations, budget/policy blocks,
assignment success + queue failure, retry, repeat, and SAFE/PRIVATE parity.

Run assignment operation, scheduled-autoscore/autopush-policy, differentiation, route,
JS, and diff checks. Stop if global/default auto-push would be introduced. One commit;
reply with policy matrix, target receipts, and no-live-write evidence.

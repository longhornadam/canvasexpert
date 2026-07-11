# Ferrari acceptance 15: Desk / Workbench / Instrument release gate

Ferrari/user alone accepts and archives. Run full API and engine suites, every changed JS
through `node --check`, `git diff --check`, secret/PII/absolute-path scans, and fetch/
compare `dev`, `origin/dev`, and `origin/main`.

Render with lifespan off at 1920x1080 and 2560x1440, dark/light: Desk; every CourseExpert
tab and standalone redirect; PG setup/queue; Gradebook; Roster; Routines; Settings;
Course Info; Downloads; Reports; AI Expert; About; Welcome; Feedback. Record globals,
unique IDs, focus, dialog bounds, deep links, context truth, no unintended page scroll,
and zero new console errors/warnings.

Functional acceptance proves real Start/Continue/Attention persistence; independent
focus/targets; one Workbench/Instrument DOM state; readiness truth; review invalidation;
write-ahead recovery; partial receipts; unresolved-only retry; ambiguous Attention;
proven reversal; PG keyboard review; draft semantics; exactly-once routines; and Feedback
parity.

## Separately authorized live-fire matrix

Using disposable Canvas objects, every apply-capable kind requires: happy path plus GET
postcondition; cancel/no-write; drift/no-write; ambiguous-success reconciliation; repeat/
no-new-effect; induced partial plus unresolved-only retry; restart/reconnect; and, where
supported, reversal plus GET postcondition and cleanup. Name prepare-only kinds and prove
no apply control. Repo evidence uses fictional labels/redacted receipt references; real
IDs/details remain untracked PRIVATE. Missing any row fails acceptance. Live fire requires
separate user authorization.

## Rollback

There is no invented runtime feature flag. Revert accepted migration commits in reverse
dependency order while preserving registry, machine-local operations/receipts/backups,
PG sessions, autoscore queue, settings, activity, and Feedback storage. Never delete user
data as rollback. Document any forward-schema reader limitation before release.

# Offline cleanup and offseason test repair

**Status:** GREEN — accepted and retired

## Objective

Restore the offline test gate to GREEN and close the identity-cleanup thread that was
already resolved in code. This batch was intentionally limited to synthetic/local data;
real-course validation is deferred by teacher decision until populated classes are
available on or after 2026-08-18 and is not a batch failure.

## Scope delivered

- Repaired the Windows path-budget tests in:
  - `api/tests/powergrader/test_packet.py`
  - `api/tests/test_feedback_pipeline.py`
- Updated `docs/handoffs/senior level/dataforge-merge-initiative.md` so it no longer
  claims that `NameAnonymizer` remains in `api/dataforge/eduphoria_parser.py`.
- Preserved `VaultIdentity`, pseudonym-rename coordination, and `canvas_id` backfill.

## Verification

- Focused gate: `73 passed`.
- Full API gate: `2116 passed`.
- Engine gate: `127 passed`.
- `git diff --check`: passed.
- No executable `NameAnonymizer` class or `Optional[NameAnonymizer]` annotation remains.
- No real-course validation was attempted; it remains an intentional post-2026-08-18
  follow-up, not a YELLOW/RED result.

## Handoff

No commit was created; the implementation changes remain in the teacher's worktree for
review. No unresolved decisions remain for this offline batch.

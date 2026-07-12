# Toyota handoff 11d: QuizForge streaming operation adapter

## Status

Deferred by Ferrari on 2026-07-11. This handoff is not implementation authorization
until the proof gaps below are resolved and Ferrari reissues it as a self-contained
Toyota handoff.

## Deferral rationale

The current text leaves material architecture and safety choices open across subprocess
streaming, whole-class versus differentiated target identity, New Quizzes object tiers,
lost-client continuation, and retry reconciliation. In particular, the repo does not yet
prove an exact returned-ID/postcondition chain for every quiz, item, stimulus, assignment,
module item, and differentiated variant created by the subprocess path. Same-title
matching is forbidden and cannot close that gap.

Before implementation, Ferrari must inspect the actual runner/subprocess event protocol,
New Quizzes API calls and returned IDs, validation manifest ownership, standalone and
Course Expert callers, disconnect behavior, and existing tests. The replacement handoff
must define server-owned progress persistence, exact per-step idempotency/reconciliation,
partial/retry semantics, and an explicitly authorized disposable-course live matrix.
Until then, the existing QuizForge legacy path remains visibly separate and no
`content.quiz` apply capability may be registered.

## Objective

Migrate QuizForge whole-class and differentiated pushes into the ledger without losing
streaming progress, subprocess isolation, dry-run validation, or per-course partial truth.

## Files

- New `api/operation_ledger/adapters/quiz.py`
- Adapter registry/executor extensions for progress events
- `api/webui/routes/push_streaming.py`
- `api/webui/routes/push_validation.py` only if review snapshot needs pure validation output
- `api/webui/static/push/quiz.js`
- `api/webui/static/push/core.js` only for operation progress consumption
- New `api/tests/test_quiz_operation.py`
- Existing QuizForge push/route tests

## Contract

Preparation runs existing dry-run/validation and freezes normalized source, settings,
whole/differentiated manifests, and targets. Apply uses a server-owned operation ID; query
strings may not carry arbitrary manifests after migration. Progress is keyed by operation
and target. Subprocess completion produces per-target receipts; lost clients do not cancel
or repeat successful targets. Retry unresolved targets only.

Idempotency must prove how an existing pushed quiz/variant is recognized before live
enablement. Until then, the adapter may remain prepare/review-only and the legacy immediate
path must remain visibly separate—not silently used after “Apply.”

```powershell
node --check api/webui/static/push/quiz.js
node --check api/webui/static/push/core.js
py -m pytest api/tests/test_quiz_operation.py api/tests/test_push_service.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py
git diff --check
```

Live-fire requires an explicit disposable-course matrix for whole, differentiated, partial,
disconnect/reconnect, and retry. Stop if deterministic idempotency is unresolved.

## Required implementer reply

One commit; report hash/files, command/pass results, whole/differentiated state matrix,
disconnect/reconnect/partial/retry/idempotency evidence, progress/receipt behavior, console
count, and exact live-fire authorization/results if performed.

Both CourseExpert and standalone Quiz surfaces use the adapter. It is apply-capable only
after returned-ID/postcondition idempotency is proved; otherwise stop rather than ship an
ambiguous prepare-only mode. Persist before send, record the returned quiz ID, and make
timeout/disconnect `sent_unknown` Attention. Same-title matching never proves success or
authorizes retry.

## Superseded

Ferrari completed discovery on 2026-07-12. This combined handoff is archived and replaced
by accepted architecture `docs/reference/quiz-operation-design.md` plus sequential slices
11d1, 11d2, and 11d3. No implementation was accepted from this superseded text.

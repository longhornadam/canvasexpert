# SENIOR ONLY — CanvasMirror 1.0beta batch pointer

> **NOT EXECUTOR AUTHORITY.** No `CURRENT.md` exists. **1.0-beta is code-complete and
> accepted** — see `docs/reference/1.0beta-acceptance-record.md`. Two things remain, and
> neither is more feature code:
> 1. the **live beta-acceptance run**, deferred to real start-of-year courses (can't be
>    modeled faithfully before August; we chose not to build a synthetic Canvas); and
> 2. a **cruft-removal / de-duplication audit** — the next initiative.

## 1.0-beta — complete and accepted

Batches 0–8 plus the bounded coordinator + release telemetry, all accepted. Evidence trail:
archived unit briefs under `docs/handoffs/archive/1.0beta-*` and the acceptance record.
Confidence bar: full `api/tests` green (1129 passed, 1 skipped) + machine-enforced contracts
(mutation ownership, transport ownership, none-label guard, repo privacy scan, read spine).

Accepted beta limitation: per-student override staleness (Batch 7 unit 03), bounded, with
live fallback — documented in `mutation-reconciliation-map.md` family 3.

Deferred to the live run (Former Program 11 / §19.5), to execute against the first real
1-current/2-concluded profile in August: the §16 benchmark, and the offline / current-vs-
concluded / OneDrive-conflict / network-fault matrices (all unit-covered today).

## Next initiative — cruft-removal & de-duplication audit

For a fresh senior session. Brief: `docs/handoffs/cruft-removal-audit-brief.md`. Goal: cut
the fat from a codebase that grew ~35k → ~126k lines in two weeks, with a particular eye on
CanvasExpert pieces talking to both CanvasMirror AND live Canvas unnecessarily (spine §21
risks #5/#6/#7/#10). Method: deletion-first, contract-guided, guarded by the existing 1129
tests — no new test/synthetic infra. Produce a ranked, evidence-backed excision list before
cutting; keep both suites green at each step.

## Later (optional, unchanged)

- Allowlist the KINDs `/api/operations/{kind}/prepare` accepts.
- Extend the transport-ownership guard to fail on Canvas-writing calls outside `api/`.
- If normal courses trip 503s post-cleanup, consider a bounded backoff-retry on 503 for
  read GETs (never writes) — a §16 resilience improvement; validate the need on real data first.

# SENIOR ONLY — CanvasMirror 1.0beta batch pointer

> **NOT EXECUTOR AUTHORITY.** No `CURRENT.md` exists — no executor authority until a
> senior authors one. All build/code work for 1.0beta is complete and accepted. The
> only remaining work is the live beta-acceptance qualification run + release closeout
> (Former Program 11), which needs an authorized live-Canvas profile — see below.

## Batch 7 — complete

- **Unit 01 — catalog structure reconciliation** — ACCEPTED (`7a703c2`).
- **Unit 01r — contract truth reconciliation** — ACCEPTED (`6f9dbf8`;
  archive `1.0beta-07b-contract-truth-reconciliation.md`). Corrected false
  curve/rubric/autopush labels; added the none-label guard test.
- **Unit 02 — grades/curves (routine path)** — ACCEPTED (`8e22fbb`;
  archive `1.0beta-07c-routine-curve-reconciliation.md`).
- **Unit 03 — per-student overrides (`private.assignments`)** — **DEFERRED as a
  documented bounded limitation, no code.** Only stale surface is
  `submissions.cached_due_date` (Student Report extension line), with live fallback
  outside the ~6h freshness window; no existing hook repairs it. Recorded in
  `mutation-reconciliation-map.md` family 3 and the five override owners' contract reasons.

## Batch 8 — transport ownership & beta acceptance

- **Unit 01 — dead-path retirement (Former Program 10)** — ACCEPTED (`f3cf5e5`;
  archive `1.0beta-08-dead-adapter-retirement.md`). Retired the four dead ledger adapters
  (56 → 50 owners). Senior-verified: deletion-only contract diff, totals recomputed.
- **Unit 02a — bounded coordinator + release telemetry** — ACCEPTED (`074ecd5`;
  archive `1.0beta-08b-coordinator-release-telemetry.md`). Fixed-two-worker read-only
  coordinator, foreground yield, async `sync-now`, 429-only retry, privacy-clean GET
  telemetry, and the `tools/canvasmirror_release_benchmark.py` harness. Senior-verified
  all 8 criteria + safety (telemetry allowlist, import isolation, benchmark confinement);
  applied a cleanup-guard hardening on accept.
- **Release-acceptance build items** — DONE (`24315f5`): suite-enforced repo privacy scan
  (`test_repo_privacy_scan.py` — caught + scrubbed a committed home-path leak),
  transport-ownership architecture gate (`test_transport_ownership.py`, closes risk #12's
  GET-side hole), and the `mirror_reads.py` shim owner/removal annotation. Phantom
  `/forge/quizforge/` 404 route retired (`7479ecf`).
- **Unit 02b — beta acceptance run + closeout (Former Program 11)** — **REMAINS; needs an
  authorized live-Canvas profile.** Not code work — a qualification pass:
  1. **Benchmark**: run `tools/canvasmirror_release_benchmark.py --live-readonly` against a
     teacher-authorized 1-current/2-concluded profile; confirm §16 cold/warm/GET targets.
  2. **Live state matrices**: offline launch + write-refusal (§19.5 #11), two-machine
     OneDrive conflict (#12), network-fault recovery (#10) — all unit-covered; live runs pending.
  3. **Rendered-route sweep**: 12 routes already clean; confirm the remaining Page-map
     surfaces (phantom route now gone).
  4. **Closeout**: write release notes (record the Unit 03 override staleness as an accepted
     teacher-visible beta limitation); walk the §20 exit checklist to green-or-accepted;
     refresh the spine's **stale §17.1 status column** (it still lists completed batches as
     "beta-blocking"). Full `api/tests` gate currently: 1129 passed, 1 skipped.

## Later (optional, not yet authored)

- Allowlist the KINDs `/api/operations/{kind}/prepare` accepts (`gradebook.sweep`, `content.*`)
  so a stale KIND cannot be hand-invoked.
- Extend the transport-ownership guard to also fail on Canvas-writing calls appearing outside
  `api/` (currently `api/`-scoped), closing the last part of risk #12.

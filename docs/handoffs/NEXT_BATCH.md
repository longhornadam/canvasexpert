# SENIOR ONLY — CanvasMirror 1.0beta batch pointer

> **NOT EXECUTOR AUTHORITY.** `CURRENT.md` is the READY correction brief for the bounded
> coordinator and release-telemetry seams found by the Batch 8 acceptance audit. The
> separate live acceptance run remains after this correction is accepted.

## Batch 7 — complete

- **Unit 01 — catalog structure reconciliation** — ACCEPTED (`7a703c2`).
- **Unit 01r — contract truth reconciliation** — ACCEPTED (`6f9dbf8`;
  archive `1.0beta-07b-contract-truth-reconciliation.md`). Corrected the false
  curve/rubric/autopush labels a four-pass audit found; added the none-label guard.
- **Unit 02 — grades/curves (routine path)** — ACCEPTED (`8e22fbb`;
  archive `1.0beta-07c-routine-curve-reconciliation.md`). Coalesced per-course
  `notify_course_changed` in `_run_routine_curve`.
- **Unit 03 — per-student overrides (`private.assignments`)** — **DEFERRED as a
  documented bounded limitation, no code.** A senior audit (2026-07-19) found the
  mirror stores no override projection; the only stale surface is
  `submissions.cached_due_date`, read by the Student Report extension line, with
  live fallback outside the ~6h freshness window. Low severity, and no existing
  hook repairs it (the delta watermark misses override-only changes). Recorded in
  `mutation-reconciliation-map.md` family 3 and the five override owners' contract
  reasons. Reopen only with a targeted per-assignment submissions force-refetch or
  a new whole-scope submissions stale-mark — and verify the facts against code first.

## Batch 8 — release acceptance remains

- **Unit 01 — dead-path retirement (Former Program 10)** — ACCEPTED (`f3cf5e5`,
  DeepSeek; archive `1.0beta-08-dead-adapter-retirement.md`). Retired the four dead
  ledger adapters (`curve.py`, `late_policy.py`, `roster_membership.py`,
  `roster_group_set.py`) — files + tests + registrations + imports + six contract
  owner entries (56 → 50). Senior-verified against the repo: deletion-only contract
  diff, totals recomputed, full suite 1110 passed / 1 skipped.
- **Unit 02a — coordinator and release telemetry correction** — **READY / active.** The
  user chose implementation. See `docs/handoffs/CURRENT.md`.
- **Unit 02b — beta acceptance (Former Program 11)** — **not yet authored.** It follows
  acceptance of Unit 02a and still requires the authorized three-course profile; live
  Canvas mutations remain unapproved.

## Later (not yet authored)

Optional hardening follow-ups from the 2026-07-19 completeness audit: allowlist the KINDs
`/api/operations/{kind}/prepare` accepts (`gradebook.sweep`, `content.*`) so a stale KIND
cannot be hand-invoked; and a guard against Canvas-writing calls migrating outside `api/`
or a transport-wrapper rename silently blinding the ownership scanner.

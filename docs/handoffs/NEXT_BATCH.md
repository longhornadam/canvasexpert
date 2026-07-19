# SENIOR ONLY — CanvasMirror 1.0beta batch pointer

> **NOT EXECUTOR AUTHORITY.** DeepSeek V4 Flash must read `AGENTS.md`,
> `docs/handoffs/CURRENT.md`, and only the references routed by that brief. It must not use
> this file to widen or reinterpret its assignment.

## Current state

Batch 6 — Home, Work, Routines, MCP, and derived views — is **complete**. Units 01–06 are all
GREEN, accepted, committed, and archived:

- 01 comment freshness foundation — `6103fca`
- 02 Home comment-aware reads — `f482042`
- 03 report provenance and atomicity — `5bc929c`
- 04 routine typed-read SDK — `ae69f26`
- 05 MCP typed local reads — `047e882`
- 06 mutation ownership checkpoint — `1d85660`

`CURRENT.md` holds no active brief. The DeepSeek V4 Flash packet deliberately stops after 06.

## Next: author Batch 7 (senior)

Batch 7 (mutation reconciliation) is authored from unit 06's machine map, not pre-authored:

- `docs/contracts/canvas-transport-owners.json` — machine authority (56 owners; 31 with
  reconciliation `none` are the candidate gaps)
- `docs/reference/mutation-reconciliation-map.md` — grouped vertical families and named gaps

Gating decision — RESOLVED 2026-07-19 (dead-path trace): the four duplicate ledger adapters
(`operation_ledger/adapters/roster_membership.py`, `roster_group_set.py`, `late_policy.py`,
`curve.py`) are **dead** — no non-test producer emits their KINDs (the generic
`/api/operations/{kind}/prepare` endpoint is only ever called with `gradebook.sweep` and the
`content.*` KINDs). Their live siblings are the direct webui routes / the `_curve_apply_core`
routine; groups and late policy already reconcile. Consequences:

- **Batch 7** reconciles only live paths. Concretely: catalog structure (19 owners, largest;
  use the `merge_group_category` template), the two live curve writers, and per-student
  assignment overrides. It must NOT touch the dead ledger adapters.
- **Batch 8** retires the four dead adapters (Former Program 10), removing each adapter and its
  contract entry together (the ownership test fails on a listed owner no longer present). Also
  consider kind-allowlisting the generic operations endpoint. Details in the map's
  "Batch 8 hygiene note".

Recommended first Batch 7 brief: the catalog-structure invalidate/merge (family 2) — largest,
uniform, and has a proven template.

## Batch table status

- Batches 0–6: delivered/accepted to their recorded scope.
- Batch 7: not yet authored; seed from 06's map after the duplicate-path decision.
- Batch 8: not active and must not start early.

---

Overwrite this file—never append—when the senior accepts `CURRENT.md` or changes the
authoritative batch.

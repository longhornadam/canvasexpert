# Next senior focus — CanvasMirror 1.0 beta

Read only this file and the sections it names below — not the whole vision document.

## Current authoritative next batch

**Batch 2 remainder — prompt group-mutation reconciliation** (spine §17.1 row 2,
"People context completion").

Batch 2's decision gate is already resolved by
`docs/handoffs/archive/1.0beta-03i-course-info-local-spine.md` (GREEN): Course Info stayed
free of Catalog-forbidden `html_url`, and the email action was redesigned rather than
persisted by default. What remains is the batch's other named outcome:

- Spine §17.1 row 2: "make group mutations reconcile the exact group scope promptly."
- Spine §17.2 "Former Program 4 — complete roster and group context" (~lines 1320-1336),
  specifically the still-open sub-outcome "Add targeted post-write group refresh" — group
  category/group/membership projections, Roster/Course Info migration, and Home roster
  warnings were already completed by earlier 03-series slices; only prompt post-write
  reconciliation (today: only cadence-based refresh) remains.

Read those two sections, `docs/reference/roster-module-map.md`, and the existing
group-snapshot code (`api/mirror/store.py` groups functions, migrated consumers from
1.0beta-03f/03g/03h) before authoring the next brief.

## Outstanding senior decisions carried over (not blocking Batch 2)

None open as of this writing. Batch 3's no-TTL `late_policy_is_current` question
(`1.0beta-04a-gradebook-config-local-read.md`) was confirmed acceptable as implemented and
that brief is now archived.

## After Batch 2

Per spine §17.1: Batch 3 (Gradebook local read spine) and Batch 4 (Precision grading) are
both GREEN and archived. Batch 5 (Student reports and portfolios) is next in table order
after Batch 2 closes — do not start it early; Batch 2's group-write boundary is a stated
regression boundary for later batches.

---
*Overwrite this file, do not append to it, whenever the authoritative next batch changes.*

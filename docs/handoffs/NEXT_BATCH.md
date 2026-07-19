# Next senior focus — CanvasMirror 1.0 beta

Read only this file and the sections it names below — not the whole vision document.

## Current authoritative next batch

**Batch 5 — Student reports and portfolios** (spine §17.1 row 5) is underway, split into
sequential slices (same pattern as the earlier 03-series/04-series batches):

- **1.0beta-06a is GREEN and archived** (`docs/handoffs/archive/`, commit `e595c47`) —
  `api/student_packet.py::build_packet` now reads standing/due/text-body/comment facts from
  the typed read service when a course's mirror is current, with live fallback unchanged
  otherwise. Established `api/report_local_reads.py` and
  `api/submission_transport.py::fetch_submission`.
- **1.0beta-06b is GREEN and archived** (`docs/handoffs/archive/`, commit `b046d5b`) —
  `api/portfolio_service.py::build_merged_portfolios` now calls the new
  `report_local_reads.local_course_submissions_by_user` once per course (was: one live
  paginated fetch per student) when the mirror is current. `report_local_reads.py` now shares
  one `_joined_course_records` helper between both consumers.
- **1.0beta-06c is READY, spec'd, not yet executed**
  (`docs/handoffs/1.0beta-06c-assignment-picker-local-metadata.md`) — migrates
  `api/webui/routes/reports.py::list_assignments_full` (the report/download assignment picker)
  to read Course Catalog's `catalog_assignments`/`catalog_assignment_groups` when current,
  falling back to today's live pagination otherwise. Independent of 06a/06b (different files:
  `reports.py`, not `student_packet.py`/`portfolio_service.py`/`report_local_reads.py`).
  Investigation already confirmed Course Catalog's schema needs no changes — this is the
  current executor-ready work.
- **Also planned, later, not yet spec'd:** the private source/freshness provenance manifest
  the vision doc names for this batch (§17.1 row 5's third named outcome). Spec this only
  after 06c lands — its exact shape should capture the same local-vs-live signal 06a/06b/06c
  now each produce (`used_local`-style booleans and the envelopes' own `state`/`source`/
  `last_success_at` fields), so it's easier to design accurately once all three are settled
  rather than guessed at in isolation.

Batches 0-4 are all GREEN and archived; Batch 2 fully closed via 1.0beta-03i + 1.0beta-05a.

Read only these two sections before authoring the next brief:
- Spine §17.1 row 5: *"Build report/portfolio metadata from typed local reads, fetch
  attachment bytes only through focused evidence, and emit a private provenance manifest."*
  Boundary that stays live: *"Evidence acquisition when a selected report requires it."*
  Status: *"Beta-blocking unless the user accepts a visible limitation."*
- Spine §17.2 "Former Program 7 — migrate Student Reports and portfolios" (~lines 1375-1390):
  assemble roster/assignment/standing/text/attempt/comment/group/due facts from the typed read
  service (Batch 1, already GREEN); acquire attachment bytes only through the focused evidence
  owner when a report actually needs them; remove routine direct `requests.Session` calls from
  report/portfolio code; include a private freshness/source manifest (no signed URLs, no
  private absolute paths); preserve existing report roots and compatibility reads. Exit gate:
  text-only reports generate from current local state with zero Canvas calls; attachment
  reports issue only evidence-specific calls.

Also read `docs/reference/roster-module-map.md` if report generation touches roster data, and
whatever module map/route card owns Student Reports/portfolios today (locate it — not yet
confirmed which file that is) before locking implementation decisions.

## Outstanding senior decisions carried over (not blocking Batch 5)

None open as of this writing.

## Batch table status (spine §17.1)

Batch 0 (Foundation): substantially delivered. Batch 1 (Typed read spine): GREEN (`6705490`).
Batch 2 (People context): GREEN — Course Info/email via 1.0beta-03i, group reconciliation via
1.0beta-05a. Batch 3 (Gradebook local read spine): GREEN. Batch 4 (Precision grading): GREEN.
Batch 5 (Student reports and portfolios): **next**. Batch 6 (Home/Work/Routines/MCP/derived
views), Batch 7 (Mutation reconciliation coverage), and Batch 8 (Transport ownership + beta
acceptance) remain after that, in table order — do not start any of them early.

---
*Overwrite this file, do not append to it, whenever the authoritative next batch changes.*

# Next senior focus — CanvasMirror 1.0 beta

Read only this file and the sections it names below — not the whole vision document.

## Current authoritative next batch

**Batch 5 — Student reports and portfolios** (spine §17.1 row 5) is underway, split into
sequential slices (same pattern as the earlier 03-series/04-series batches):

- **1.0beta-06a** (`docs/handoffs/1.0beta-06a-student-reports-local-metadata.md`, Status:
  READY) — migrates `api/student_packet.py::build_packet` (the per-student, multi-course
  packet) to the typed read service, with live fallback when a course's mirror isn't current.
  This is the current executor-ready work.
- **Planned next (not yet spec'd):** the parallel migration of
  `api/portfolio_service.py::build_merged_portfolios` (the multi-student cohort portfolio),
  reusing 06a's new shared module (`api/report_local_reads.py` or wherever it lands) and its
  new `submission_transport.fetch_submission`. Spec this only after 06a is GREEN — do not spec
  or start it early, and do not let 06a's executor touch `portfolio_service.py`.
- **Also planned, later, not yet spec'd:** migrating `list_assignments_full`'s assignment-picker
  endpoint (needs its own investigation — no equivalent shape exists yet in either
  `private_assignments` or Course Catalog), and the private source/freshness provenance
  manifest the vision doc names for this batch.

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

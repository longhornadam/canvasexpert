# Next senior focus — CanvasMirror 1.0 beta

Read only this file and the sections it names below — not the whole vision document.

## Current authoritative next batch

**Batch 5 — Student reports and portfolios** (spine §17.1 row 5) is underway, split into
sequential slices (same pattern as the earlier 03-series/04-series batches):

- **1.0beta-06a is GREEN and archived** (`docs/handoffs/archive/`, commit `e595c47`) —
  `api/student_packet.py::build_packet` now reads standing/due/text-body/comment facts from
  the typed read service when a course's mirror is current, with live fallback unchanged
  otherwise. Established two reusable pieces the next slice should build on:
  `api/report_local_reads.py` (local-read/join + comment-display helpers) and
  `api/submission_transport.py::fetch_submission` (focused single-submission live fetch for
  attachments).
- **Next to spec:** the parallel migration of `api/portfolio_service.py::build_merged_portfolios`
  (the multi-student cohort portfolio) — reuse `report_local_reads.py`'s joining/comment-display
  helpers and `fetch_submission` rather than re-deriving them; note `build_merged_portfolios`
  currently does one live paginated fetch *per student* even within a single course, so a
  local-current course collapses that to one local read total (bigger win than 06a's
  per-course-once shape). `report_local_reads.local_course_submissions` takes one `user_id`
  today (06a's own scope decision, per its "not yet a collection" deviation) — decide during
  specing whether to extend it for multi-student use or have the portfolio brief filter a
  per-course join result to each student in memory.
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

# Next senior focus — CanvasMirror 1.0 beta

Read only this file and the sections it names below — not the whole vision document.

## Current authoritative next batch

**Batch 5 — Student reports and portfolios (spine §17.1 row 5) is fully closed.** All four
slices are GREEN and archived: 1.0beta-06a (`e595c47`, `build_packet` local metadata),
1.0beta-06b (`b046d5b`, `build_merged_portfolios` one-read-per-course), 1.0beta-06c (`29ed736`,
assignment-picker Catalog migration), 1.0beta-06d (`1d92e71`, private source/freshness
manifest). Exit gate met: text-only reports make zero Canvas calls, attachment reports issue
only evidence-specific calls, source/freshness is privately disclosed. Shared infrastructure
now available for reuse: `api/report_local_reads.py` (join/freshness/manifest helpers),
`api/submission_transport.py::fetch_submission` (focused single-submission fetch).

**Batch 6 — Home, Work, Routines, MCP, and derived views (spine §17.1 row 6) is next.**
Not yet spec'd. Read only these two sections before authoring the next brief:

- Spine §17.1 row 6: *"Replace remaining routine compatibility readers; set bounded comment
  freshness; give report routines/custom routines a supported read interface; preserve MCP
  allowlists and generation-based invalidation."* Boundary that stays live: *"Mutation
  routines' final compute/execute and explicit live refreshes."* Status: *"May accept a
  teacher-visible beta exception only by explicit decision."*
- Spine §17.2 "Former Program 8 — converge Home, Work, Routines, MCP, and derived views"
  (~lines 1392-1407): migrate Work providers from endpoint regex shims to typed scopes; give
  Home a bounded comment freshness policy; migrate report-only routines and provide a
  supported custom-routine read interface; keep mutation routines' final compute/execute live;
  keep MCP payload allowlists/pseudonymization separate from newly persisted fields; add
  derived revision/regrade/attention views only when an immediate consumer uses them;
  invalidate derived views by projection generation rather than ad hoc timers. Exit gate:
  background/display features do not independently call core assignment/roster/submissions
  collections; derived views state their source generation/freshness.

This is a broad batch spanning several subsystems (Home, Work providers, Routines, MCP) —
expect it to need the same kind of investigation-before-drafting and multi-slice split Batch 5
needed. Read `docs/reference/roster-module-map.md`, `docs/reference/gradebook-module-map.md`,
and whatever module map covers Home/Work (locate it) before locking a first slice's scope —
do not assume which subsystem to start with; investigate what's actually duplicated/shimmed
today first, the same way 1.0beta-06c's Course Catalog investigation preceded its brief.

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

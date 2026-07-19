# Next senior focus — CanvasMirror 1.0 beta

Read only this file and the sections it names below — not the whole vision document.

## Current authoritative next batch

**Batch 5 — Student reports and portfolios** (spine §17.1 row 5).

Batches 0-4 are all GREEN and archived. 1.0beta-05a (`docs/handoffs/archive/`) closed Batch 2's
last outcome (targeted post-write group reconciliation), so Batch 2 is now fully closed too —
nothing remains before Batch 5 per the spine's own dependency order (§17.1 lines 1211-1214: the
next implementation batch is selected only when its dependencies and decision seams are ready;
Batch 5 has none outstanding).

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

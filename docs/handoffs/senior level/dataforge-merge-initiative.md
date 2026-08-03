# DataForge merge initiative

**Status:** Slices 1–6 accepted GREEN; the DataForge merge initiative is complete. Slice 4 and
onward were verified under the user's explicit off-season waiver: acceptance testing uses synthetic/mocked roster and
assessment data and does not require an active real course. Production first use remains
review-first.

**Last senior review:** 2026-08-03

**Current pointer:** No active DataForge brief. Slice 6 is accepted GREEN and this initiative is
complete. The outstanding real-course review is carried as the production-use decision, not an
acceptance-test prerequisite, because the user stated that no active real courses are available
for two weeks. A future change needs a new senior decision and brief.

**Source:** The original DataForge-side `CE-MERGE-HANDOFF.md` was retired with the untracked
source tree after slice 1. It was a useful map, but three of its load-bearing claims were stale
against this repository; section 2 below records the authoritative corrections.

**Why this is not feature creep.** DataForge is a second local Flask app the teacher runs
separately, with its own data folder, its own pseudonymization system, its own settings page,
and a "companion workspace" publishing path whose only purpose is to hand files to
CanvasExpert. Merging deletes all of that. Net direction is fewer apps, fewer pseudonym
spaces, fewer settings pages, one workspace, zero new dependencies.

This document is persistent senior context. It does not occupy the single active-handoff
slot, and an executor must not implement directly from it. A senior promotes one slice at a
time into the single direct brief in `docs/handoffs/`.

---

## 1. Teacher outcome

The teacher exports an assessment report from Eduphoria Aware, drops it into CanvasExpert,
and gets three things:

1. Readable reports. A teacher report, parent narratives, and an LLM-ready JSON per
   assessment, plus a cross-assessment dashboard and a longitudinal history the teacher can
   re-date and prune.
2. Grouping. Students sorted into tiers by their actual assessment performance, applied to a
   Canvas group set from the Students page.
3. Differentiation. Those Canvas groups then drive the tiered assignments and differentiated
   quizzes CanvasExpert already builds.

Item 3 already works. Item 1 already works, in the wrong app. Item 2 is the join that does
not exist yet, and it is the reason for the merge.

---

## 2. Corrections to the source handoff

A future reader will find `CE-MERGE-HANDOFF.md` persuasive. These three points override it.

### 2.1 Group membership is not a new mutation

The handoff says nothing puts students into groups and recommends deferring the write. Both
halves are wrong. CanvasExpert already writes group membership, and every transport is
already registered:

| Capability | Location |
| --- | --- |
| Add student to group | `api/webui/routes/roster_canvas.py:63` `create_canvas_group_membership` |
| Remove student from group | `api/webui/routes/roster_canvas.py:95` |
| Move student within a group set | `api/webui/routes/roster_canvas.py:139` `update_student_canvas_group` |
| Bulk apply across many students | `api/webui/routes/roster_updates.py:267` action `set_canvas_group` |
| Existing teacher button | `api/webui/templates/roster.html:98` `data-bulk="set_canvas_group"` |

All four transports carry owner entries in `docs/contracts/canvas-transport-owners.json`
under scope `private.groups` with `targeted` reconciliation.

**Consequence: this initiative adds zero Canvas mutations and zero contract entries.** No
`test_canvas_mutation_ownership.py` change is expected. If a slice appears to need one, that
is a stop condition, not a step.

### 2.2 Tier groups must cover the roster exactly

`api/operation_ledger/adapters/assignment_groups.py:78-100` enforces three rules on any group
set used for tiered assignments:

- no group referenced by a tier may be empty (`has no accepted members`);
- referenced groups may not share members (`overlapping memberships`);
- referenced groups must cover the active roster exactly
  (`must cover the active student roster exactly`).

The handoff's advice, surface unmatched students as a list, is not sufficient. A tier set
built only from students who sat the assessment will pass its own screen and then fail at
differentiation prep with an error about roster coverage that names nothing the teacher
recognizes.

**Consequence: placement of no-data students is a required field in the grouping UI, not a
warning.** And a tiering method that produces an empty tier must be rejected at the point of
proposal, which is realistic with four fixed tiers and a class of twenty.

### 2.3 `base_template` alone renders blank pages

The handoff says point `base_template` at CanvasExpert's own layout and the pages look
native. Inheritance will work; the content will not appear. Block names do not overlap:

| DataForge templates define | CanvasExpert `layouts/workspace.html` defines |
| --- | --- |
| `title`, `style`, `body`, `script` | `title`, `workspace_header`, `primary`, `workspace_scripts`, `stylesheet_bundle` |

Jinja silently drops a child block the parent does not declare, so each page returns HTTP 200
with an empty shell. Every template needs real editing, and the inline `{% block style %}`
bodies (40+ lines each in `groups.html` and `history.html`) have to move out to satisfy the
CSS block ownership rule in `docs/reference/webui-presentation-system.md`.

---

## 3. What the merge deletes

Worth stating up front, because it is the argument for doing this at all.

| Deleted | Why |
| --- | --- |
| `dataforge/webui.py` | Flask shell, replaced not ported |
| `dataforge/config.py` | Folds into CanvasExpert settings and workspace |
| The entire companion-workspace concept | `get_shared_workspace`, `set_shared_workspace`, `shared_safe_dir`, `shared_workspace_status`, `SHARED_SAFE_FOLDER`, `SHARED_SUBFOLDER`, and the Settings page fields that drive them. DataForge's `SHARED_SAFE_FOLDER = "For AI"` is literally `api/webui/workspace.py:64` `FOR_AI_NAME`. It was always publishing into this workspace through a config field. After the merge there is one workspace and the field has nothing to point at. |
| `dataforge/templates/base.html` | CanvasExpert supplies the layout |
| `dataforge/templates/settings.html` | No second settings page |
| `dataforge/batch_processor.py` | Standalone `python -m` CLI that duplicates what the Assessments page does. Nothing imports it. |
| `anonymize_map.csv` and `NameAnonymizer` | The Identity Vault replaces both. As landed, the map is gone and no live path instantiates the class, but the class itself is still in `eduphoria_parser.py`. See the verification note in section 9. |
| `_build_dashboard` alias in `webui.py` | Re-export for one test's historical import path |
| `Launch Dataforge.bat`, `.venv/`, `requirements*.txt` | Standalone launcher and environment |

Zero new dependencies. DataForge already dropped pandas for
`dataforge/tabular.py` on openpyxl, which CanvasExpert already carries.

---

## 4. Locked decisions

Confirmed with the teacher on 2026-08-02. An executor may not revisit these.

**4.1 Prior-year students lose their identity, not their numbers.** The Identity Vault is
keyed by `canvas_id`. A student with no current Canvas enrollment cannot hold a vault entry.
Those students get no vault entry and no pseudonym; their snapshots stay as anonymous
aggregate. They cannot be placed in a Canvas group in any case. Rejected: extending the vault
with a non-Canvas key namespace (schema change touching MCP, PowerGrader, and FeedbackExpert),
and keeping `anonymize_map.csv` read-only alongside the vault (two pseudonym systems in one
repo, which is the thing the merge exists to end).

**4.2 Assessments is a page under the More menu.** Nav becomes
Home / Create / PowerGrader / CanvasAgent / Panels / Calendar / More(Students, Seating,
Automations, Assessments) / Settings. Importing a benchmark export is a few-times-a-year job
and does not earn a top-level slot. The grouping panel, which the teacher touches far more
often, lives on Students where it is already reachable.

**4.3 Group placement writes to Canvas.** Slice 4 applies tier placement through the existing
`set_canvas_group` bulk path, preview then apply, the same flow the Students page already
offers per student. Rejected: proposal-and-export only, and modelling it as an operation
ledger adapter (duplicates a working path for a change the teacher makes a few times a year).

**4.4 The join does not go through the vault.** Eduphoria Local ID is the Canvas SIS ID,
confirmed by the teacher. The route is Local ID to the roster mirror's `sis_user_id`
(`api/mirror/store.py:501`) to Canvas `user_id`. The vault matters for pseudonym-first
display and for retiring the second anonymizer, not for the join. This decouples slice 4 from
slice 5.

**4.5 Port as an ordinary commit on `dev`.** Never `git merge` the DataForge history.
CanvasExpert has three root commits, and merging an old lineage on 2026-07-31 resurrected 34
retired files and reddened 20 guard tests. Git cannot see this conflict because it is
semantic.

---

## 5. Surface and boundary decisions

DataForge does two jobs and they belong in two different places.

### 5.1 The Assessments page owns reading an export

New page at `/assessments`, one route module, workspace layout. It carries DataForge's
`index`, `results`, `dashboard`, `history`, `history_update`, `history_delete`, `download`,
`download_all`, and `export_standards_profile`. DataForge's `settings` endpoint does not port.

### 5.2 The Students page owns grouping

`groups.html` does not port as a page. It is a proposal generator, and the Students page is
already the applier. Its tiering logic (Overall %, STAAR bands, Quartiles, with teacher-set
cutoffs) becomes a panel on Students, alongside the existing `roster-group-builder` and
`roster-group-labels-editor` panels:

```
> Group from assessment data
  Assessment [Fall Benchmark, Gr 7 v]   Tier by [Overall %][STAAR bands][Quartiles]
  Support < [60]   Core < [75]   Extend < [90]

  Support 8    Core 11    Extend 7    Accelerate 4
  Not in this assessment (3) -> place in [Core v]      required

  Group set [Benchmark Tiers v]  or  [Create it with these 4 groups]
  [Preview placement] -> [Apply]
```

Apply loops the existing `POST /roster/bulk` with `action=set_canvas_group` once per tier.
The three rules from section 2.2 are enforced in this panel, so a tier set that cannot drive
a tiered assignment is impossible to create. The page's existing "Groups: Needs placement"
lens already surfaces unplaced students for free.

### 5.3 Endpoint names

The template contract names endpoints, not paths. These must resolve after the port:
`index, settings, process, dashboard, groups, history, history_update, history_delete,
results, export_standards_profile, download, download_all`. `settings` and `groups` are the
two that change meaning; see 5.1 and 5.2.

---

## 6. Where the data lands

DataForge's single external data folder splits across the workspace privacy zones.

| DataForge | CanvasExpert | Contains |
| --- | --- | --- |
| `input/` | `Student Work/` | Raw exports. Real names. Private. |
| `output/` | `Student Work/Reports/` | Teacher report and parent narratives. Real names when anonymization is off. Private. |
| `uploads/` | temp, deleted after parse | Already unlinked by `views.process` |
| `anonymize_map.csv` | interim `_System/DataForge/`; deleted in slice 5 | Replaced by `_System/Identity Vault/` |
| `history/` | `_System/DataForge/history/` | Pseudonym-keyed snapshots, machine-derived state |
| `standards-profile.json` | `For AI/DataForge/` | Pseudonyms, standard codes, scores. Safe to sync. |

Slice 1's interim state keeps the private anonymization map under `_System/DataForge/` until
slice 5 retires `NameAnonymizer`; no slice-2 adapter may expose or duplicate that map.

`Student Work/` and `Student Work/Reports/` already exist in `api/webui/workspace.py`. The raw
import folder is the one new subfolder.

---

## 7. Slice boundaries

All six slices landed. No brief is active; each retired brief is in `docs/handoffs/retired/`.
A future change to this feature needs a new senior decision and its own brief.

| # | Slice | Gate |
| --- | --- | --- |
| 1 | Ignore rules and test isolation, then port the engine. No routes, no UI. | Accepted GREEN: CanvasExpert `2048 passed`, DataForge `131 passed`, with the retired test subjects accounted for in the brief. |
| 2 | The Assessments page. FastAPI shell, response mapper, real template re-basing, More-menu entry. | Accepted GREEN: 2056 API tests; focused route/presentation gate 21 passed; rendered Assessments, results, dashboard, and history with zero browser console warnings/errors. |
| 3 | The join, read only. Local ID to `sis_user_id` to `user_id`, with a coverage report. | Accepted GREEN: 2062 API tests; focused join/Assessments gate 25 passed; rendered empty and populated coverage states with zero browser console warnings/errors. |
| 4 | "Group from assessment data" panel on Students. | Accepted GREEN: 2072 API tests; focused proposal/route/presentation gate 20 passed; rendered `/roster` with no configured courses, no overflow, and zero browser warnings/errors. Production first use still requires teacher review of read-only coverage. |
| 5 | Retire `NameAnonymizer` into the Identity Vault, re-key existing snapshots. | Accepted GREEN: 2077 API tests; focused migration/route/presentation gate 34 passed; broader DataForge/route matrix 247 passed; rendered Assessments with zero browser warnings/errors. |
| 6 | MCP tool over the standards profile, fold the DataForge workflow into `docs/`, route card, product guide update. | Accepted GREEN: 257 named MCP/DataForge tests; 2083 full API tests; MCP/schema parity and canonical-guide routing passed; no real course required |

Slice 3 reported read-only match coverage against the mirror. The teacher has now explicitly
waived real-course acceptance testing for the two-week off-season; production first use still
requires reviewing the coverage report before applying groups.

Slices 4 and 5 are independent once 3 lands, because of decision 4.4.

---

## 8. Standing hazards

**8.1 The ignore window, resolved in slice 1.** Root `.gitignore` now protects assessment
workbooks, CSVs, and re-identification maps before any engine file moved. The final package is
`api/dataforge/`; no assessment data files are present in the tree.

**8.2 Config writes, resolved for the engine in slice 1.** The package `config.py` and its
settings endpoint were not ported. Read-only `api/dataforge/paths.py` resolves through the
CanvasExpert workspace; the slice-2 adapter must not reintroduce package config writes or a
second settings surface.

**8.3 Fixtures are built in code, never committed.** DataForge's blanket `*.xlsx` and `*.csv`
rules are why. Keep that property. Any test touching a re-identification map uses a synthetic
one.

**8.4 `views.RUNS` dies on restart.** Module-level dict keyed by run id, cleared on process
restart, and CanvasExpert restarts to self-update. Results, dashboard, and groups pages go
back to the index after a restart. Acceptable, and it stays a known behaviour rather than a
bug report.

**8.5 Layout facts not worth re-deriving.** Three Eduphoria reports, discriminated by the
merged label at Excel F2: `All Learning Standards` (Standard Breakdown, row 3 codes like
`7.2(B) [R]`), `All RCs` (Reporting Category, row 3 codes `R1`, `R2`), `All Responses`
(Individual Responses, row 6 TEKS, row 5 RC, row 4 item type). Column A's vertical merge gives
the data start row; do not hardcode offsets. Learning Standard Breakdown and Individual
Responses share a grain and pool. Reporting Category is a different grain and must never share
a comparison table with TEKS codes.

---

## 9. Acceptance criteria for the initiative

1. One app. No second Flask process, no second settings page, no companion workspace field.
2. One pseudonym space at runtime. DataForge's live processing and coverage paths resolve
   identity through the Identity Vault, and no live path instantiates `NameAnonymizer` or
   writes `anonymize_map.csv`.
3. Zero new Canvas mutations. `docs/contracts/canvas-transport-owners.json` is unchanged.
4. Zero new dependencies. `api/requirements.txt` is unchanged.
5. The teacher can go from an Eduphoria export to a populated Canvas group set to a tiered
   assignment without leaving CanvasExpert and without hand-editing groups in Canvas.
6. A tier set produced by the grouping panel always satisfies section 2.2, so differentiation
   prep never fails on coverage.
7. `get_product_guide` reports the feature, so an assistant does not tell the teacher it does
   not exist.

**Verified 2026-08-03, after slice 6 landed.** Full API suite `2083 passed`. Criterion 1 holds:
no web-framework import and no settings surface under `api/dataforge/`. Criteria 3 and 4 hold:
`docs/contracts/canvas-transport-owners.json` and `api/requirements.txt` both have an empty
diff. Criterion 7 holds: Appendix G of `api/default_docs/AI Authoring/START HERE -
CanvasAgent.txt` covers the Assessments surface and review-first grouping, and the guide's
contents list points to it. Criteria 5 and 6 rest on the slice 4 gate and its rendered check,
not on a real course, per the off-season waiver below.

**Amended 2026-08-03, post-slice-6 review.** Criterion 4's "apply through the existing bulk
path" now also re-runs the read-only preview and compares `proposal_digest` before it writes, so
a roster or snapshot that moved underneath an open review blocks the write instead of applying a
stale placement. Tiers are applied one at a time and a failure part-way through names which
tiers landed, because a half-applied set no longer covers the roster exactly and would fail
differentiation prep with the unrecognizable error section 2.2 describes. Both guarantees live in
`api/webui/static/roster/assessment_groups.js`: apply still posts only to the pre-existing
`/api/roster/bulk`, so this is a client-side binding, not a server-enforced one.

Criterion 2 was narrowed to what slice 5 actually delivered. The runtime claim holds, but the
`NameAnonymizer` class is still present at `api/dataforge/eduphoria_parser.py:190`, kept alive
only by `api/tests/dataforge/test_anonymizer_guardrails.py`, `test_canvas_join.py`, and
`test_shared_publish.py`. The `Optional[NameAnonymizer]` hints on the live parser functions now
name a type those paths no longer receive, since slice 5 injects `VaultIdentity` instead.
Deleting the class and re-pointing those tests is an open follow-up rather than a slice 5 gap:
slice 5's own acceptance criterion 1 asked only that live paths stop instantiating it.

---

## 10. Explicit non-goals

- Porting `batch_processor.py` or `tools/process_essays.py`.
- A crosswalk table between pseudonym spaces. With one vault there is one pseudonym space;
  the source handoff says the same thing and says do not build it.
- Any Eduphoria API integration. The teacher exports a file; that is the input.
- Synthetic Canvas data standing in for a real-course check. The project rule holds: fake
  courses, rosters, and submissions do not substitute for verifying against live Canvas once a
  live course is available. Amended 2026-08-03 for the off-season waiver recorded in section 7.
  Slices 4 through 6 were accepted on synthetic and mocked fixtures because no active course
  existed, and production first use still requires the read-only coverage review.
- Reporting Category rollups on the dashboard. The grain guard excludes them today and that
  stays true.
- Writing DataForge results back into Canvas grades in any form.

---

## 11. Stop and senior-review conditions

- Any slice appears to require a new entry in `docs/contracts/canvas-transport-owners.json`.
  Section 2.1 says it should not. Stop and report.
- The DataForge 162 do not pass after the port. The source handoff expects import paths or
  missing conftest isolation, not logic. If it is logic, stop.
- Real match coverage from slice 3 is low enough that grouping would be misleading. That is a
  teacher decision about the data, not an engineering fix.
- A tiering method cannot produce four non-empty tiers on the teacher's real class sizes. The
  tier count may be the wrong fixed number and that is a product decision.
- Any file containing a real student name or SIS ID is staged for commit. Stop immediately.

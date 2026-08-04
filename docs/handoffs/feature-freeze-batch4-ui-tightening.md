# Direct execution brief: UI tightening, Batch 4 (D1, D2, D3)

**Status:** Retired — GREEN; accepted 2026-08-03

**Executor:** senior (self-executed this session)

**Senior objective:** Promote Batch 4 of
`docs/handoffs/senior level/feature-freeze-hardening-initiative.md` (baseline
`dev` @ `86e5caf`, `api/tests` 2153 passed). Land D1 (rubric picker: synced
Library only), D2 (Automations → Routines rename), D3 (work rail: map
`kind` to a teacher-legible phrase server-side instead of showing the raw
slug). D4 and A7 are the next batch (§9 Order 5), not this one.

## Required context

Read `AGENTS.md`, then §6 D1-D3, §7, and §8 of the initiative document.

## Baseline re-verification and scope discovery performed this session

All three items' cited file:line locations were re-read and confirmed
current before implementation. D3 in particular required deeper
investigation than its initiative-document description implied, recorded
here because it changes the shape of the fix:

- `work_rail.js` reads `job.kind` directly, exactly as described.
- The job shape (`_JOB_KEYS` in `api/work_registry/models.py`) is a
  **strict, exact-key-set validated, documented contract**
  (`docs/contracts/work-registry-contract.md`), built by two constructors
  (`adapters.py::_project` and `providers/__init__.py::finding`) and
  asserted key-for-key equal to the raw job by
  `test_work_routes.py::test...` (`assert set(projected_job) ==
  set(_job())`). Adding a `description` field is therefore a real,
  if small, contract change — not a template-only fix — and needed
  updating in 6 places (2 constructors, the model's `_JOB_KEYS`/
  `validate_job`/`public_job`, the contract doc, and 3 test fixtures), not
  just `work_rail.js` and one model function.
- Confirmed all "known kinds" the initiative document lists
  (`routine_state`, `operation_receipt`, `grade…`, `late…`, `roster…`) flow
  through one of those two constructors; `create.*` items
  (`adapters.py::collect_start_sources`) are a separate, simpler "Desk
  Start" listing that never reaches `work_rail.js` and needed no change.

## Locked decisions

**D1.** Remove the `api_root() / "rubrics"` unconditional append from
`content_folders("rubric")` in `api/runtime_paths.py` — rubrics come only
from `library_folder("Rubrics")`. Do **not** touch `quiz`/`assignment`/
`page`, which keep their `qf_materials` example-file fallback this cycle
(per the initiative document's explicit "rubrics only" recommendation).
`api/webui/workspace.py`'s one-time workspace-seeding fallback to
`api/rubrics` (`_default_rubric_files`) is a different mechanism (populates
a *fresh* workspace's Library folder once) and is out of scope — it is not
the runtime picker.

Fix `_list_txt_files`'s label in `api/webui/deps.py` to the file's own name,
appending the parent folder name in parentheses only when two files share a
basename (a real disambiguation need for `quiz`/`assignment`/`page`, which
still have two folders each). This is the same pattern
`list_inbox_files` already uses one function below it, for the same
documented reason (a repo-relative path climbs out through the teacher's
OneDrive folder instead of showing a file name).

No new "workspace not configured" UI: `powergrader_setup.html` already
shows a page-level `{% if not has_workspace %}` banner linking to Settings,
and the rubric `<select>` already renders just "— no rubric —" on an empty
list. That combination already satisfies "empty picker with a pointer to
workspace setup, no silent repo fallback" without a rubric-specific
addition.

**D2.** Rename "Automations" → "Routines" at all 6 cited sites plus the
authoring doc, **plus 2 more instances the initiative document's audit did
not list** (found during this session's re-verification):
`api/webui/templates/_routines_panel.html` — the "Your automations" `<h2>`
and one JS error string ("Could not load your automations."). Both are
included in the same partial `routines.html` and `gradebook.html`'s
Routines tab both `{% include %}`, so they render on both pages already
covered by the initiative document's list.

Leave `nav_section == 'automate'` (internal id) unchanged, per the
initiative document's own recommendation.

**Propagation to existing installs, resolved rather than stated as a
limitation:** `api/webui/ai_ta.py`'s `RETIRED_FILES` mechanism (hash of a
previously-shipped version → delete-and-reseed on the next "Rebuild") does
cover same-name content updates, including this one. Computed the pre-edit
file's normalized hash (`git show HEAD:"api/default_docs/AI Authoring/START
HERE - CanvasAgent.txt" | sha256sum`, CRLF-normalized per
`ai_ta._shipped_hash`) and added it to
`RETIRED_FILES["START HERE - CanvasAgent.txt"]` *before* editing the file's
content, so `POST /api/ai-ta/rebuild` → `build_library` →
`_retire_superseded` will delete an existing teacher's unedited copy and
`_copy_tree_if_missing` will reseed the renamed text. Verified against
`api/tests/webui/test_ai_ta.py` (the churn-guard test that would fail if
the added hash were the *current* one).

**D3.** Add `description` to the Work Registry job's public shape:
teacher-legible phrase derived from `kind` (`generic_description(kind)` in
`api/work_registry/models.py`, mirroring the existing `generic_title`),
computed in `public_job`. `work_rail.js` renders `job.description`, falling
back to rendering **no** description span at all when it's empty — never
falling back to `job.kind`. The internal `kind` field itself is unchanged
and still present (other code may still branch on it); only the *display*
path changes.

## Authorized scope and insertion points

- `api/runtime_paths.py` (`content_folders`), `api/webui/deps.py`
  (`_list_txt_files`), `api/tests/test_beta075_runtime.py`,
  `api/tests/webui/test_ai_ta.py` (D1 fallout fix, see execution result).
- `api/webui/templates/layouts/_app_header.html`, `dashboard.html`,
  `gradebook.html`, `routines.html`, `_routines_panel.html`,
  `api/default_docs/AI Authoring/START HERE - CanvasAgent.txt`,
  `api/webui/ai_ta.py` (`RETIRED_FILES` addition),
  `api/tests/test_presentation_contracts.py` (stale comment only).
- `api/work_registry/models.py`, `api/work_registry/adapters.py`,
  `api/work_registry/providers/__init__.py`,
  `api/webui/static/course_expert/work_rail.js`,
  `docs/contracts/work-registry-contract.md`,
  `api/tests/test_work_registry.py`, `api/tests/test_work_routes.py`,
  `api/tests/test_desk_routes.py`.

## Acceptance criteria

1. A workspace with no Library/Rubrics configured yields an empty rubric
   list from `deps.list_rubric_files()` — never the bundled `api/rubrics`
   examples.
2. A configured Library/Rubrics folder's files are labeled by file name
   only; two files sharing a basename across folders each show their own
   folder name.
3. All 6+2 "Automations" sites now read "Routines"; the authoring doc's
   Rebuild path actually reseeds an existing install's copy (not just a
   fresh one), verified via the `RETIRED_FILES` hash addition and the
   existing churn-guard test.
4. A job's public projection carries a non-slug `description` for every
   known `kind`, and `""` for an unknown one; `work_rail.js` never renders
   a raw `kind` value.
5. Rendered verification: `/routines`, `/gradebook` (Routines tab), `/`
   (Home), and `/powergrader` (rubric picker) load with zero console
   errors and show the renamed/fixed text; the real local workspace's
   rubric picker shows exactly one entry per file with clean names.

## Named verification gate

```powershell
py -m pytest api/tests/test_work_registry.py api/tests/test_work_routes.py api/tests/test_desk_routes.py api/tests/test_beta075_runtime.py api/tests/webui/test_ai_ta.py api/tests/test_presentation_contracts.py api/tests/test_webui_template_contracts.py api/tests/test_operation_routes.py api/tests/test_rubric_operation.py api/tests/webui/test_rf.py -p no:randomly
```

Then the full gate: `py -m pytest api/tests -q`. Baseline 2153 passed.

## Stop conditions

Stop and report YELLOW/RED without guessing if: the Work Registry job
schema change breaks a consumer outside this repo's test suite (none
found — the contract doc is the only external-facing description and it
was updated); the `RETIRED_FILES` hash addition doesn't match the actual
shipped blob (verified independently via `git show` + a from-scratch
Python hash, not assumed); or a rendered route shows a duplicate or
mislabeled rubric entry after the fix (verified live against the real
local workspace instead).

## Execution result

Traffic light: GREEN

Commit hash: recorded in the commit that includes this brief.

Implemented exactly per the locked decisions above. D1: removed the repo
fallback, switched `_list_txt_files` to name-based labeling with
collision-only disambiguation. D2: 8 sites total (6 initiative-document
sites + 2 found this session in `_routines_panel.html`) plus the authoring
doc, with the `RETIRED_FILES` hash wired so the rename actually reaches
existing installs on Rebuild rather than being cosmetic. D3: added
`description` to the Work Registry job contract end-to-end (2 constructors,
model validation/mapping, contract doc, `work_rail.js`, 3 test fixtures).

One test regression found and fixed during implementation (not deferred):
`test_ai_ta.py::test_build_library_writes_expected_files` called
`ai_ta.build_library(target)` with no explicit `rubric_folders`, relying on
the now-removed repo-fallback default to find a real example rubric and
generate its "Score with -" scoring skill. The test's actual purpose (that
generation feature) is unrelated to D1's fallback removal, so it now passes
`rubric_folders=[runtime_paths.api_root() / "rubrics"]` explicitly instead
of relying on the removed default.

Changed files:

- `api/runtime_paths.py`, `api/webui/deps.py`
- `api/webui/templates/layouts/_app_header.html`, `dashboard.html`,
  `gradebook.html`, `routines.html`, `_routines_panel.html`
- `api/default_docs/AI Authoring/START HERE - CanvasAgent.txt`,
  `api/webui/ai_ta.py`
- `api/work_registry/models.py`, `api/work_registry/adapters.py`,
  `api/work_registry/providers/__init__.py`,
  `api/webui/static/course_expert/work_rail.js`,
  `docs/contracts/work-registry-contract.md`
- `api/tests/test_beta075_runtime.py` (+2 tests), `api/tests/webui/test_ai_ta.py`
  (fixed, no new tests), `api/tests/test_work_registry.py` (+2 tests),
  `api/tests/test_work_routes.py`, `api/tests/test_desk_routes.py`
  (fixture updates only), `api/tests/test_presentation_contracts.py`
  (comment only)
- this brief

Verification:

- Focused gate (10 files, `-p no:randomly`): 111 passed.
- Full gate (`py -m pytest api/tests -q`): 2157 passed (baseline 2153 + 4
  new tests, 0 removed).
- Rendered verification in the browser preview against the real local
  workspace: `/routines` shows "Routines" title and "Your routines"
  heading; `/gradebook`'s Routines tab shows "Routines" in both the tab
  label and the `<h2>`; Home shows "ROUTINES" and "Routines →"; the nav
  header shows "Routines" on every page. `/powergrader`'s rubric picker
  shows exactly 5 clean filenames (`ELA7_Classroom_Writing_Rubric.txt`,
  `ELA_District_ECR_Rubric.txt`, `ELA_STAAR_ECR_Rubric.txt`,
  `ELA_STAAR_SCR_Rubric.txt`, `New_Default_Rubric.txt`) matching the real
  Library/Rubrics folder's actual contents, one entry per file, no repo
  duplicates. Zero console/server errors on every route checked.

Deviations: D3's scope was larger than the initiative document's own
framing implied (a schema/contract change, not a template-only fix) —
recorded above under "Baseline re-verification," not silently absorbed. D2
covered 2 more sites than the initiative document listed. No other
deviations.

Unresolved decisions: none for this brief. A5, A7, D1.4, D4, C sequencing,
and 2.3 remain open per the initiative document's §10.

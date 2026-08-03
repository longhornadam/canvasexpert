# Brief: DataForge slice 1, safety net and engine port

**Status:** Retired GREEN after senior acceptance on 2026-08-02. Superseded by
`docs/handoffs/dataforge-slice2-assessments-page.md`.

**Batch:** DataForge merge initiative, slice 1 of 6.
**Baseline:** `dev` at `0f09ee9`.
**Senior context:** `docs/handoffs/senior level/dataforge-merge-initiative.md`. Do not
implement from that document; it is background. This brief is the work.

---

## Teacher-visible outcome

None. This slice ships no route, no page, and no nav entry. It moves a working engine into
this repository under this repository's safety rules, and proves it still works. The teacher
sees nothing until slice 2.

State that plainly in the return report. Do not invent a user-facing claim.

---

## Required context, read only this

1. This brief.
2. `AGENTS.md`.
3. `api/DataForge/DataForge Files/docs/CE-MERGE-HANDOFF.md`, with the caveat that its claims
   about group membership, roster coverage, and `base_template` are stale. Those three do not
   affect this slice.
4. `api/webui/workspace.py` lines 30 to 80 (zone constants) and 320 to 400 (zone accessors).
5. `api/tests/conftest.py` in full. It is 40 lines and it is the reason this slice exists
   before any other.
6. The files named in section "Files" below.

Do not read `api/webui/routes/`, the operation ledger, or the Students page. No route work
happens in this slice.

---

## Current repository truth and preflight

Verified 2026-08-02. Confirm each before writing; stop if any is false.

- `api/DataForge/` is **untracked, not ignored**. `git status --short` shows `?? api/DataForge/`.
  Note that `git check-ignore -v api/DataForge/` reports a match on `.gitignore:42`, which is a
  blank line. That report is spurious. `git status` is authoritative.
- The root `.gitignore` has **no rule** for `*.xlsx`, `*.csv`, `anonymize_map.csv`, `input/`,
  `output/`, `uploads/`, or `history/`. Confirm with
  `grep -n "xlsx\|csv\|anonymize" .gitignore`, which returns nothing today.
- `api/DataForge/.gitignore` currently carries all of those rules and is the only protection
  in place. It protects only paths beneath itself.
- No assessment data files exist in the tree right now. Confirm with
  `find api/DataForge -type f \( -name "*.xlsx" -o -name "*.csv" -o -name "anonymize_map.csv" \) -not -path "*/.venv/*"`,
  which returns nothing.
- `api/tests/conftest.py` isolates `config_io.CONFIG_PATH`, `workspace.CONFIG_PATH`,
  `profiles.PROFILES_PATH`, `LOCALAPPDATA`, and the OneDrive env vars. It does **not** yet know
  anything about DataForge.
- `api/webui/workspace.py` provides `workspace_root()`, `student_work_root()`,
  `student_work_reports_root()`, `for_ai_root()`, `system_root()`, `system_folder(name)`, and
  `identity_vault_dir()`.
- DataForge's test suite reports 162 passing at handoff, from 107 test functions plus
  parametrization. Per-file function counts, for the arithmetic in section D:
  `test_anonymizer_guardrails` 18, `test_views` 14, `test_canvas_join` 14, `test_tabular` 12,
  `test_template_env` 9, `test_shared_publish` 9, `test_local_id` 5, `test_routing` 4,
  `test_partial_credit` 4, `test_header_depth` 4, `test_dependency_boundaries` 4,
  `test_reporting_category` 3, `test_individual_responses` 2, `test_dashboard_grain` 2,
  `test_zero_standards` 1, `test_max_points` 1, `test_eb_normalize` 1.

Capture the CanvasExpert baseline before touching anything:

```bash
python -m pytest api/tests -q
```

Record the number. It is the comparison for the gate.

---

## Locked decisions

**L1. Port as an ordinary commit on `dev`. Never `git merge` the DataForge history.** Three
root commits already exist here. Merging an old lineage on 2026-07-31 resurrected 34 retired
files and reddened 20 guard tests. Git cannot see this conflict because it is semantic.

**L2. Ignore rules land before the first file moves.** Not in the same step, not "as part of"
the port. Step A completes and is verified before step B begins.

**L3. `config.py` is deleted, not ported.** It is replaced by `api/dataforge/paths.py`, which
resolves paths from CanvasExpert's workspace and **never writes**. Every setter goes:
`set_data_dir`, `set_shared_workspace`. The whole companion-workspace concept goes with them.

**L4. Views keep calling a module-level `get_paths()`.** Do not change the eight view function
signatures to take `paths` explicitly. The hazard in `config.py` was the unguarded *write* to a
package-directory file, not the read-side global. Once `get_paths()` is backed by CanvasExpert's
workspace, `api/tests/conftest.py` already isolates it. Keeping the signatures stable is what
makes "the ported tests still pass" a meaningful signal rather than a rewrite.

**L5. Templates do not move in this slice.** They are slice 2's problem and their block names
do not match CanvasExpert's layout. Leave them where they are.

---

## Files

### Port to `api/dataforge/`

`__init__.py`, `eduphoria_parser.py`, `history_store.py`, `profile_export.py`, `tabular.py`,
`template_env.py`, `views.py`, `teks_crosswalk.json`, `reference/teks/ELA_7_TEKS_Full_List.txt`.

### Port to `api/tests/dataforge/`

`conftest.py` and all 17 `test_*.py` files.

### Do not port

| File | Reason |
| --- | --- |
| `webui.py` | Flask shell. Replaced in slice 2, not ported. Its `_build_dashboard` re-export dies with it; fix the importing test to take it from `views`. |
| `config.py` | Replaced by `paths.py`. See L3. |
| `batch_processor.py` | Standalone `python -m` CLI duplicating what slice 2's page will do. Nothing imports it. |
| `templates/` | Slice 2. See L5. |
| `requirements.txt`, `requirements-dev.txt` | CanvasExpert has its own and this port adds nothing. |
| `tools/process_essays.py` | Unrelated HTML scraping utility. Imports no dataforge module. |
| `.venv/`, `__pycache__/`, `.claude/`, `Launch Dataforge.bat`, `src/dataforge/config.json` | Environment and machine-local state. |

Leave `api/DataForge/` in place until the gate is green, then delete the whole directory in the
same commit. Do not leave a half-migrated tree.

---

## Implementation

### A. The safety net, first and separately

1. Add to the root `.gitignore`, in a clearly commented block:
   `*.xlsx`, `*.xls`, `*.csv`, `anonymize_map.csv`, `**/anonymize_map.csv`, and a negation for
   any non-PII reference data that must stay tracked. Check the repository first for tracked
   `.csv` files that these rules would newly shadow; if any exist, allowlist them explicitly
   and name them in the return report.
2. Extend `api/tests/conftest.py` so its autouse fixture also isolates whatever
   `api/dataforge/paths.py` resolves from. If `paths.py` derives everything from
   `workspace.workspace_root()`, and that is already isolated, say so in the return report
   rather than adding a redundant monkeypatch.
3. Add a guard test at `api/tests/dataforge/test_data_never_committed.py` asserting that the
   root ignore rules cover a representative assessment filename and a re-identification map
   name. Build the assertion against the ignore rules, not against a file you create.

Verify A before starting B:

```bash
git check-ignore -q "api/dataforge/anonymize_map.csv" && echo PROTECTED || echo EXPOSED
```

It must print `PROTECTED`. If it prints `EXPOSED`, stop.

### B. Move the engine

Copy the eight modules and two data files listed above into `api/dataforge/`. Rewrite the
relative imports (`from . import config, history_store, profile_export`) to match the new
package. Nothing else in `views.py`, `eduphoria_parser.py`, or `tabular.py` should change in
this step; if you find yourself editing parser logic, stop and report.

### C. Replace `config.py` with `paths.py`

New module `api/dataforge/paths.py`. Read-only. Surface:

- A `Paths` object carrying `data_dir`, `input_dir`, `output_dir`, `upload_dir`, `history_dir`,
  and `anon_map`, mapped onto CanvasExpert's workspace zones:

  | Attribute | Zone | Accessor |
  | --- | --- | --- |
  | `input_dir` | Raw exports, real names, private | new subfolder under `student_work_root()` |
  | `output_dir` | Generated reports, real names when anonymization is off, private | `student_work_reports_root()` |
  | `upload_dir` | Transient, already unlinked by `views.process` | temp |
  | `history_dir` | Pseudonym-keyed snapshots, machine state | under `system_root()` |
  | `anon_map` | Retired in slice 5; relocate under `system_root()` for now | under `system_root()` |

- `get_paths(ensure: bool = True) -> Paths`, matching today's signature so views are unchanged.

`history_store._history_dir(paths)` currently computes `paths.data_dir / "history"`. Change it
to use `paths.history_dir`. That is a one-line change plus whatever its tests construct.

`profile_export.publish_profile()` loses its `workspace is None` and `target_dir is None`
branches: there is one workspace now and it is `for_ai_root() / "DataForge"`. Keep
`SharedPublishError` and keep the leak-detection refusal. Deleting the leak check is a stop
condition, not a simplification.

Delete `get_shared_workspace`, `set_shared_workspace`, `shared_safe_dir`,
`shared_workspace_status`, `SHARED_SAFE_FOLDER`, `SHARED_SUBFOLDER`, `set_data_dir`, and
`is_configured`. `views.settings` has no reason to exist after this and does not port; slice 2
already plans no second settings page.

### D. Port the tests, and do the arithmetic out loud

Move all 17 files plus `conftest.py` to `api/tests/dataforge/`. Fix import paths.

The 162 will not stay 162, and that is expected. Deleting the companion-workspace API deletes
the tests that cover it, most of `test_shared_publish.py` (9 functions, some parametrized) and
the `config.CONFIG_FILE` monkeypatching in `test_views.py`. `views.settings` going away removes
its tests too.

**The return report must contain a line-item list**: every deleted test, and one sentence on
which deleted production symbol it covered. A test deleted because its subject is gone is
correct. A test deleted because it failed is a stop condition. The senior cannot tell those
apart from a number.

Extend `test_dependency_boundaries.py` while you are in it: today it forbids pandas and numpy
outside allowed modules and permits a web framework only in `webui.py`. With `webui.py` gone,
**no** module under `api/dataforge/` may import a web framework. Tighten it to that.

---

## Acceptance criteria

1. `git check-ignore -q "api/dataforge/anonymize_map.csv"` succeeds, and did so before any
   file moved.
2. `api/DataForge/` is deleted. No half-migrated tree.
3. `api/dataforge/` contains no `config.py`, no `webui.py`, no `batch_processor.py`, no
   templates, and no web-framework import.
4. `api/requirements.txt` is unchanged. This port adds no dependency.
5. `docs/contracts/canvas-transport-owners.json` is unchanged. This slice touches no Canvas
   transport.
6. The CanvasExpert suite passes at or above its recorded baseline count.
7. The ported DataForge tests pass, with every deleted test accounted for in the return report.
8. No file containing a real student name or SIS ID is staged.

---

## Explicit non-goals

- Any route, page, template, or nav entry. That is slice 2.
- Any join between Eduphoria IDs and Canvas users. That is slice 3.
- Any Canvas write of any kind.
- Touching `NameAnonymizer` beyond relocating where its map file lives. Retirement is slice 5.
- Refactoring parser logic. It works and it has 162 tests. Move it.
- Reading real assessment data. Fixtures are built in code; keep that property.

---

## Named verification gate

```bash
python -m pytest api/tests -q
```

```bash
python -m pytest api/tests/dataforge -q
```

```bash
git diff --check
```

Plus the `git check-ignore` proof from step A, and `git status --short` showing nothing
unexpected staged.

Run the full suite, not just the DataForge subset. The point of moving the tests under
`api/tests/` is that they inherit the conftest isolation net, and only the full run proves the
net did not break for anything else.

---

## Stop conditions

- `git check-ignore` prints `EXPOSED` at the end of step A.
- A ported test fails for a reason that is not an import path or missing isolation. The source
  handoff is explicit that logic failures are not expected; if one appears, the port has gone
  wrong somewhere else.
- The port appears to need a new dependency, a new Canvas transport, or a contract entry.
- Any file containing a real student name or SIS ID appears in `git status`.
- The CanvasExpert baseline count drops.

---

## Execution result

**Traffic light: GREEN.** No teacher-visible behavior shipped; this slice only ports and
protects the offline engine for later slices.

Baseline and gates:

- CanvasExpert baseline before edits: `1917 passed`.
- Ported DataForge subset after the final lowercase-package move: `131 passed`.
- Full `py -m pytest api/tests -q`: `2048 passed` (baseline plus the ported/safety tests).
- `git check-ignore -q api/dataforge/anonymize_map.csv`: `PROTECTED`.
- `git diff --check`: passed.
- `api/DataForge/` legacy tree is removed; final package is `api/dataforge/`.
- `api/requirements.txt` and `docs/contracts/canvas-transport-owners.json` are unchanged.
- No files are staged; `git status --short` shows only the intended untracked/modified slice
  files plus the pre-existing handoff changes.

Changed files are the root `.gitignore`, the new `api/dataforge/` engine package and reference
data, the new `api/tests/dataforge/` tests/fixtures, and this execution result. No changes were
needed in `api/tests/conftest.py`: `paths.py` resolves only through `workspace.workspace_root()`;
the suite's fake config path and cleared OneDrive variables prevent ambient real-workspace
resolution, while the DataForge test conftest supplies a per-test synthetic workspace.
The tracked CSV allowlist covers `api/default_docs/Calendars/Bell Schedule - Bobcat Hour.csv`,
`Bell Schedule - Exam Review Day.csv`, `Bell Schedule - Friday.csv`,
`Bell Schedule - Homeroom First.csv`, `Bell Schedule - Pep Rally.csv`,
`Summer_Session_Sample.csv`, and `calendar_template.csv`; the four
`api/tests/fixtures/class_schedule/` files (`Bell Schedule - Example Day A.csv`, `Bell Schedule
- Example Day B.csv`, `Bell Schedule - Example Short Day.csv`, and `Schedule Map - Example
Alternating Day Split.csv`); and `api/tests/fixtures/student_analysis_sample.csv`.

Deleted tests and the retired production symbol each covered:

- `test_unset_workspace_publishes_nothing` — `config.get_shared_workspace()` returning unset.
- `test_env_var_overrides_the_config_file` — `config.get_shared_workspace()` and `CONFIG_FILE`.
- `test_workspace_can_be_cleared` — `config.set_shared_workspace()`.
- `test_missing_workspace_raises_rather_than_silently_skipping` — `config.get_shared_workspace()`
  and `config.shared_safe_dir()`.
- `test_folder_without_a_safe_zone_is_refused` — `config.shared_safe_dir()` and
  `SHARED_SAFE_FOLDER`/`SHARED_SUBFOLDER`.
- `test_status_reports_each_failure_mode` — `config.shared_workspace_status()`.
- `test_download_traversal_attempt_is_a_404_through_the_app` — the deleted Flask `webui.app`
  response shell.
- `test_download_all_missing_run_is_a_404_through_the_app` — the deleted Flask `webui.app`
  response shell.
- `test_template_directory_was_actually_found` — the deliberately unported `templates/` tree.
- `test_no_template_calls_url_for` — the deliberately unported `templates/` tree.
- `test_no_template_hardcodes_the_base_layout` — the deliberately unported `templates/` tree.
- `test_every_endpoint_a_template_names_really_exists` — the deleted Flask `webui.app` route
  map plus the deliberately unported `templates/` tree.
- `test_a_real_template_renders_with_no_flask_involved` — the deliberately unported
  `templates/` tree.
- `test_pages_still_render_through_flask` — the deleted Flask `webui.app` shell, including the
  retired `views.settings` route.

No logic failure, new dependency, Canvas transport, route, page, nav entry, or assessment data
was introduced. No commit was created.

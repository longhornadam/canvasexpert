# Execution brief: reconcile the pre-New Quiz worktree for one integration commit

Status: **complete**

Risk: **medium**

Executor: **Luna**

## Outcome

Leave the complete local worktree verified and staged as one coherent integration commit
on top of the already-committed New Quiz delivery (`35f313e`, `545947c`). Preserve every
New Quiz capability while restoring the established late-catch-up error for ordinary
non-assisted PowerGrader sessions.

## Locked decisions

- The two New Quiz commits remain intact and must not be amended, reset, squashed, or
  otherwise rewritten.
- The intended integration commit is the complete current worktree: the completed
  pre-New Quiz batches, their archived handoffs/reference updates, this reconciliation
  brief, and the narrow PowerGrader compatibility repair below.
- `api/webui/README.md` and `docs/reference/powergrader-module-map.md` intentionally contain
  both committed New Quiz documentation and older unstaged additions. Preserve both; do
  not restore either file from an older revision.
- In `pg_late_preview` and `pg_late_score`, evaluate the established mode/late-watch error
  before the unsupported-`late_watch` fallback. Existing non-assisted sessions lacking a
  `late_watch` field must return `Late catch-up requires Auto-Score With API.` New Quiz
  sessions remain blocked from late watch, preview, scoring, and Canvas writeback.
- Other than that guard-order repair in `api/webui/routes/powergrader.py` and an optional
  focused assertion in `api/tests/test_powergrader_late_catchup.py`, do not modify any New
  Quiz runtime or test file from `e8407ef..545947c`.
- This is integration reconciliation, not a redesign. Do not reopen the completed Desk,
  Course Expert, current-course rollover, route-retirement, test-pruning, source-material,
  or Workbench decisions recorded in the archived handoffs.
- All checks remain local/offline. Do not enter tokens, course IDs, real student data, or
  invoke Canvas/AI/routine operations, validation, upload, prepare, review/apply, retry,
  push, or download actions.
- Stage the complete worktree only after the matrix is GREEN. Do not create the commit;
  the senior owns the final inspection, message, and commit action.

## Scope

- Implement the guard-order correction in `api/webui/routes/powergrader.py` and add a
  focused regression only if the existing tests do not already lock both behaviors.
- Validate every currently tracked and untracked change, including all archived handoffs,
  the source-material extractor split, Workbench reference map, Desk/Course Expert UI work,
  current-course rollover, route retirements, and pruned presentation contracts.
- Confirm the New Quiz overlap is limited to the two additive documentation files above
  plus the intended `powergrader.py` repair.
- Update this brief's `Execution result`, archive it under `docs/handoffs/archive/`, and
  stage the full inventory with `git add -A` only after successful verification.

## Out of scope

- New product behavior, public contracts, persistence formats, migrations, dependencies,
  live probes, branch changes, remote operations, or history rewriting.
- Changes to New Quiz fetching, snapshots, review UI, session capability flags, scoring,
  or writeback policy.
- Repeating completed rendered-browser acceptance. No browser-facing code is authorized by
  the compatibility repair; rely on the archived handoffs' recorded UI evidence.

## Reference pattern and routing

- PowerGrader insertion points: `api/webui/routes/powergrader.py::pg_late_preview` and
  `api/webui/routes/powergrader.py::pg_late_score`
- Legacy behavior tests: `api/tests/test_powergrader_late_catchup.py`
- New Quiz safety tests: `api/tests/test_powergrader_new_quizzes.py`
- Prior integration intent: `docs/handoffs/archive/unifying-worktree-commit-prep.md`
- Completed batch evidence: the untracked/added handoffs already under
  `docs/handoffs/archive/`
- Required project guidance: `AGENTS.md`, `TOOLS.md`

The project-local change-risk and test-failure summarizers are listed as planned rather
than available. Use compact Git summaries and direct focused failure output instead.

## Implementation requirements

1. Record the initial `git status --short` inventory. Preserve all unrelated bytes and
   staging state until verification is complete.
2. Make the smallest guard-order repair. Do not change response text, status codes, session
   schema, capability flags, or helper behavior.
3. Run the focused compatibility/New Quiz matrix, then the full API suite because this is
   the integration boundary for several previously completed batches.
4. Syntax-check every changed JavaScript file. Confirm `git diff --check HEAD` passes and
   that no private/generated/output path or Canvas-token pattern is present.
5. Confirm the only worktree paths also touched by the New Quiz commit range are
   `api/webui/README.md`, `docs/reference/powergrader-module-map.md`, and the intended
   `api/webui/routes/powergrader.py` repair. Self-review those three diffs for additive
   preservation of New Quiz behavior/documentation.
6. Record the final report here, archive this brief, stage everything with `git add -A`,
   run the staged checks, and verify there are no unstaged or untracked files.

## Verification

```powershell
py -m pytest api/tests/test_powergrader_late_catchup.py api/tests/test_powergrader_new_quizzes.py -q
py -m pytest api/tests
node --check api/webui/static/course_expert/tabs.js
node --check api/webui/static/desk.js
node --check api/webui/static/gradebook.js
node --check api/webui/static/push/core.js
node --check api/webui/static/push/course_picker.js
node --check api/webui/static/push/download.js
node --check api/webui/static/settings/courses.js
git diff --check HEAD
```

After GREEN verification and archiving this brief:

```powershell
git add -A
git diff --cached --check
git status --short
```

Run the configured pre-commit hook or its exact staged-token check without printing any
matched secret material. Do not stage generated caches or local workspace/private data.

## Stop conditions

Stop with RED rather than guessing if:

- Preserving the legacy error and New Quiz block requires a schema, public API, capability,
  or writeback-policy change.
- A required check fails and the cause is not the narrow guard order or an obvious issue in
  the already-documented batch that owns the changed path.
- A New Quiz runtime path outside `api/webui/routes/powergrader.py` appears modified.
- The inventory contains credential-like material, student/course-derived private data,
  generated output, caches, or a path not explained by the archived handoffs.
- Staging would omit or overwrite part of the current worktree.

## Return report

### Execution result

- Traffic light: **GREEN**
- Commit hash: **none; the complete worktree is staged and uncommitted for senior review**
- Files changed: the initial inventory contained 54 paths (38 modified, 1 deleted, and
  15 untracked). The final staged inventory contains 56 paths (40 modified, 1 deleted,
  and 15 added): the complete pre-New Quiz integration inventory, the narrow
  `api/webui/routes/powergrader.py` guard-order repair, its focused regression in
  `api/tests/test_powergrader_late_catchup.py`, and this archived brief. No generated,
  workspace, output, cache, credential, or private-data path is present.
- Verification: focused compatibility/New Quiz matrix **15 passed**; full API suite
  **618 passed, 1 skipped**; all seven required `node --check` commands passed;
  `git diff --check HEAD` and `git diff --cached --check` passed. The configured
  `.githooks/pre-commit` token guard passed against the staged diff, and a conservative
  added-content credential scan found no Canvas-token or credential-like assignment.
- New Quiz overlap review: the intersection with `e8407ef..545947c` is exactly
  `api/webui/README.md`, `api/webui/routes/powergrader.py`, and
  `docs/reference/powergrader-module-map.md`. The two documentation diffs preserve the
  committed New Quiz guidance while adding the older source-material/current-course/
  route-retirement material. The runtime diff is limited to evaluating the established
  late-watch error before the unsupported fallback; New Quiz snapshot, late-watch,
  scoring, and Canvas-writeback gates remain intact and the New Quiz tests pass.
- Deviations: none. The optional focused regression was added because preview lacked an
  assertion for the established non-assisted-session error; it now locks both preview
  and score to the exact existing message.
- Remaining blocker or decision: none. `git status --short` shows the complete inventory
  staged with no unstaged or untracked files.

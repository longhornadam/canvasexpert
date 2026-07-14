# Execution brief: prepare the unified Canvas Expert integration commit

Status: **ready for implementation**

Risk: **medium**

Executor: **Luna**

## Outcome

Leave the complete current worktree verified and staged as one coherent integration commit. The staged result combines the completed route retirement, source-material split, presentation-test pruning, Workbench documentation, and Desk/Course Expert UI batches; it makes no live Canvas, AI, credential, or student-data action.

## Locked decisions

- The intended commit is the entire current worktree, including the untracked completed handoffs and module-map/reference updates. Do not split it into feature commits or discard changes.
- Do not create a commit. The senior will own the final commit message and commit action.
- Preserve existing implementation decisions. This is a readiness pass, not an architecture review or a UI redesign.
- The two UI handoffs are included: Desk is GREEN; Course Expert is included with its documented narrow-viewport browser limitation. Do not attempt to manufacture browser evidence or change responsive code solely because the in-app viewport override is unavailable.
- All checks must remain local/offline. Do not enter tokens, course IDs, real student data, or invoke validation, upload, prepare, review/apply, retry, push, Canvas, AI, or routines.
- If a verification failure clearly originates in the staged work, make the smallest scoped repair and record it. If its cause or fix is unclear, stop YELLOW/RED and leave the worktree unstaged rather than guessing.

## Scope

- Validate all current tracked and untracked changes shown by `git status --short`, including `api/` code/tests, Workbench templates/scripts/styles, reference docs, archived handoffs, and the two active UI handoffs.
- Run the integration verification matrix, record concise results here, then stage the complete worktree with `git add -A` only if the matrix is GREEN.
- Confirm the staged inventory matches the pre-stage inventory and has no whitespace error, secret-like material, or repository-local student data introduced by this batch.

## Out of scope

- New product behavior, route/API changes, broader refactors, test redesign, dependency updates, migrations, or live service probes.
- Committing, pushing, branch changes, remote fetches, or altering `main`/`dev` history.
- Re-running visual work that the completed handoffs already established, except for a new failure caused by this readiness pass.

## Reference pattern and routing

- Current integration inventory: `git status --short` and `git diff --name-only` at the start of this brief.
- Completed batch context: `docs/handoffs/archive/prune-webui-presentation-contract-tests.md`, `docs/handoffs/archive/retire-quiz-streaming-http-surface.md`, `docs/handoffs/archive/retire-roster-tier-scheme-http-endpoints.md`, `docs/handoffs/archive/slim-source-materials-extraction.md`, `docs/handoffs/archive/workbench-canonical-flow-audit.md`, `docs/handoffs/desk-operational-console.md`, and `docs/handoffs/course-expert-workbench-console.md`.
- Required project guidance: `AGENTS.md`, `TOOLS.md`.
- For a large failure log, use the project-routed test-failure summarizer when available before manually reading raw output.

## Implementation requirements

1. Record the pre-stage file inventory in the execution result and compare it to the staged inventory after `git add -A`.
2. Run the locked verification matrix. A pre-existing narrow Course Expert viewport limitation is not a test failure; record it accurately.
3. If every required command passes, stage all current worktree changes, then run the staged diff check and verify `git status --short` shows no unstaged implementation files.
4. Keep the working tree staged but uncommitted for senior/user review. Do not amend or clean unrelated files.

## Verification

```powershell
py -m pytest api/tests
node --check api/webui/static/desk.js
node --check api/webui/static/course_expert/tabs.js
node --check api/webui/static/course_expert/work_rail.js
git diff --check HEAD
```

After a GREEN matrix:

```powershell
git add -A
git diff --cached --check
git status --short
```

## Stop conditions

Stop with RED rather than guessing if:

- Any check exposes a likely secret, student data, credential flow, unexpected Canvas write path, or a regression whose scoped fix is unclear.
- The staged inventory differs materially from the documented integration inventory.
- A required verification command fails and a minimal local repair is not obvious.
- Staging would add generated, workspace, output, cache, or private-data files.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to the senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **GREEN**
- Commit: changes are staged and uncommitted for senior/user review.
- Files changed: staged inventory matches the pre-stage inventory (32 paths): 21 modified source/test/docs files, 1 deleted route module, and 10 added source/docs/handoff/reference files. This includes the completed Desk and Course Expert batches, route retirement, source-material split, test pruning, and all handoff/reference updates.
- Verification: `py -m pytest api/tests` passed (599 passed, 1 skipped); `node --check api/webui/static/desk.js` passed; `node --check api/webui/static/course_expert/tabs.js` passed; `node --check api/webui/static/course_expert/work_rail.js` passed; `git diff --check HEAD` passed; after staging, `git diff --cached --check` passed. The repository token-pattern hook and a conservative staged credential scan found no credential-like material.
- Rendered routes checked: use the completed UI handoffs; no visual work was duplicated. The documented narrow Course Expert browser limitation remains accurately recorded and is not a matrix failure.
- Deviations: none. One initial credential-scan command had a PowerShell quoting parse error before execution; staging and all required validation were subsequently run successfully.
- Remaining blocker: none. `git status --short` shows the complete inventory staged with no unstaged implementation files.

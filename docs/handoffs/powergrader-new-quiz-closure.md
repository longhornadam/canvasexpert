# Execution brief: Close PowerGrader New Quiz written-response delivery

Status: **ready for implementation**

Risk: **medium**

Executor: **Luna**

## Outcome

The durable documentation accurately tells teachers that PowerGrader can select a New
Quiz and create a local written-response review snapshot using the Student Analysis JSON
report. It retains the current limits: Classic Quizzes remain unavailable, file-upload
responses are filename-only, and the PowerGrader UI does not offer New Quiz posting, late
catch-up, scheduled scoring, or item-level write-back.

Archive the completed New Quiz handoffs and create one scoped commit on `dev`, then push
that commit to `origin/dev`. This closes the delivered feature without staging unrelated
worktree changes.

## Locked decisions

- New Quizzes are available in the PowerGrader picker for written-response review in Grade
  Myself, Use My AI Chat, and interactive Auto-Score modes.
- The response source is Student Analysis JSON. File-upload entries remain filename-only;
  do not describe file download as available.
- A teacher-authorized comment-only assignment-level API probe succeeded, but it does not
  enable or prove score writes or alter the PowerGrader UI's no-write session capability.
  Documentation must distinguish this probe from a teacher-facing feature.
- Correct the stale claim in `api/webui/README.md` that a PAT cannot retrieve New Quiz
  item-level responses. It can retrieve constructed responses through the enrollment-gated
  Student Analysis JSON report; item-level **write-back** remains unavailable.
- Preserve every unrelated staged, unstaged, and untracked worktree change. The broad
  workbench changes and overlapping module-map edits are not authorized for this commit.
- Push to `origin/dev`; do not delete `dev`, merge branches, force-push, or modify `main`.

## Scope

- Update relevant New Quiz wording in `api/webui/README.md`, `api/README.md`,
  `docs/reference/powergrader-module-map.md`, and
  `docs/reference/new-quizzes-student-analysis-csv.md`.
- Keep `api/webui/templates/powergrader_setup.html` accurate; alter it only if it conflicts
  with the locked decisions.
- Archive only `docs/handoffs/powergrader-new-quiz-written-responses.md` and
  `docs/handoffs/powergrader-new-quiz-written-responses-luna.md` after durable docs are
  correct. Keep this closure handoff active until its execution record is complete.
- Stage only the New Quiz implementation, focused tests, durable docs, and New Quiz
  handoffs; commit once and push to `origin/dev`.

## Out of scope

- Any source-code behavior change, Canvas request, live write, or feature expansion.
- Downloading upload bytes; UI write-back; score writes; item-level writes; late catch-up;
  scheduled work; or a full-suite run.
- Staging, committing, cleaning, reverting, or archiving unrelated user work.

## Reference pattern and routing

- Completed implementation record: `docs/handoffs/powergrader-new-quiz-written-responses-luna.md`
- Product record: `docs/handoffs/powergrader-new-quiz-written-responses.md`
- Durable module map: `docs/reference/powergrader-module-map.md`
- Student Analysis reference: `docs/reference/new-quizzes-student-analysis-csv.md`
- Existing UI wording: `api/webui/templates/powergrader_setup.html`
- Read `TOOLS.md` before broad inspection.

## Implementation requirements

1. Inspect only the routed New Quiz passages and reconcile every statement to the locked
   decisions; do not broaden the API probe into UI support.
2. Archive only the two completed New Quiz handoffs.
3. Before staging, use path-specific staged/unstaged diff review. If a required file mixes
   in unrelated user edits that cannot be isolated safely, stop YELLOW rather than staging.
4. Commit only the defined scope. Fetch and compare `origin/dev` and `origin/main` before
   pushing, then push current `dev` to `origin/dev` without force.

## Verification

- `py -m pytest api/tests/test_powergrader_new_quizzes.py api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_import_results.py api/tests/test_feedback_pipeline.py -q`
- `git diff --check`
- `git status --short`

If setup-template wording changes, render `/powergrader` without selecting a course and
check the displayed guidance plus zero new console errors.

## Stop conditions

Stop with YELLOW rather than guessing if:

- A required documentation file mixes New Quiz and unrelated edits that cannot be committed
  independently.
- “Push to remove dev” means deleting the durable `dev` branch.
- Remote divergence requires a merge/rebase decision.
- Documentation would claim UI write-back, score writes, or file downloads that are not
  delivered.

## Return report

### Execution result

- Traffic light: **GREEN pending scoped commit/push**
- Commit hash: **pending**
- Files changed: **New Quiz fetch/normalization, SAFE-bundle/session/UI gates, focused synthetic tests, durable New Quiz docs, and the two archived completed New Quiz handoffs**
- Verification: **`py -m pytest api/tests/test_powergrader_new_quizzes.py api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_import_results.py api/tests/test_feedback_pipeline.py -q` — 43 passed; `git diff --cached --check` passed; path-specific staged/unstaged review isolated the two mixed documentation files hunk-by-hunk**
- Push: **pending remote fetch/divergence check**
- Deviations: **none**
- Remaining blocker or decision: **none**

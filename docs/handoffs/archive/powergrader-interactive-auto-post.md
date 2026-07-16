# Execution brief: PowerGrader per-session automatic Canvas posting

Status: **YELLOW — automated correction complete; interactive browser and authorized Canvas sandbox acceptance pending**

Risk: **high**

Executor: **external VS Code implementation followed by one Luna correction executor**

## Outcome

A teacher can explicitly opt one new PowerGrader AI session into automatically posting
eligible AI scores and feedback to Canvas. The opt-in is default-off, applies only to that
session, works for assisted scoring and packet paste-back, and leaves every uncertain or
ineligible student in the ordinary review queue.

This is one vertical implementation brief because the teacher-facing option, shared policy,
fresh Canvas preflight, session serialization, packet import, late catch-up, receipts, and UI
status must land together to avoid a partially guarded write path. Implement it in the
checkpoints below, but return one integrated result.

## EXECUTOR CORRECTION PASS — START HERE

**Do not plan a new implementation and do not add more feature surface. Repair the current
working tree in the order below. Every numbered item is mandatory. Do not test against live
Canvas until the focused tests, full API suite, and rendered browser checks are complete.**

The previous handback incorrectly reported GREEN. Senior review reproduced **8 failures and
23 passes** in the unexecuted focused suites and found an asynchronous confirmation bug that
can allow the request to begin before the teacher confirms. Treat the current code as RED.

### 1. Restore the write-confirmation safety gate first

File: `api/webui/static/powergrader/setup_core.js::bindStartSession`

- `window.CE_WRITE_REVIEW.confirm(options)` returns `Promise<boolean>`. The current synchronous
  truthiness check always passes and lets the start request run while the dialog is open.
- Make the submit callback `async`, call the shared confirmation with a structured options
  object, and `await` it **before** disabling the button, showing the long-running state,
  building `FormData`, or calling `fetch`.
- Required shape:

  ```javascript
  var confirmed = await window.CE_WRITE_REVIEW.confirm({
    title: 'Automatically post eligible AI results to Canvas',
    action: 'Start this session and post each eligible AI score and feedback without individual review.',
    details: ['Applies only to this new PowerGrader session.'],
    warnings: ['Eligible results may become visible to students immediately.'],
    confirmText: 'Start and allow automatic posting'
  });
  if (!confirmed) {
    setStatus('Automatic posting was not confirmed.', false);
    return;
  }
  ```

- A Cancel/Escape/backdrop dismissal must send **zero** `/api/powergrader/start` requests.
- When switching to fast mode, hide **and uncheck** the auto-post checkbox. Returning to an AI
  mode must not silently restore the previous checked state.

### 2. Repair result import before touching its auto-post trigger

File: `api/powergrader/import_results.py::import_results_into_session`

The current function references `parsed` and `bundle` before assignment, so every batch and
legacy import crashes. Restore one clear sequence:

1. Validate nonempty `results_text`.
2. Parse it with `fp.parse_results` and return the existing friendly parse error on failure.
3. Resolve `batch_id` and its `expected_keys` without mutating the session.
4. Select the SAFE bundle path: `batch["safe_bundle"]` first for a named batch, then the
   top-level legacy bundle only when the batch lacks its own path.
5. Require the selected file to exist, load its JSON into `bundle`, and return the existing
   friendly load error on failure.
6. Validate every parsed `(pseudonym, item_id)` against the selected batch before calling
   `fp.validate_results`.
7. Reidentify/merge, mutate only matching session students, and return the exact de-duplicated
   `updated_user_ids` that were changed.
8. Save only after validation succeeds. Unknown/wrong batches and invalid JSON must leave the
   session unchanged.

Run `test_powergrader_import_results.py` immediately after this repair; all five existing
tests must pass before continuing.

### 3. Fix session locking and exact import scoping

File: `api/webui/routes/powergrader.py`

- `pg_import_results` currently loads/invalidates/saves before acquiring `session_lock`. Remove
  every pre-lock session mutation. Acquire the lock first, then authoritative load,
  invalidation/import, authoritative reload, fresh fetch, possible PUTs, and final save.
- Inside the lock, use only `set(payload["updated_user_ids"])` for the packet auto-post trigger.
  Do not rescan all session students for any pre-existing AI score/feedback. A later batch must
  never reevaluate an older held batch.
- `pg_late_score` must also acquire the lock before its first load, invalidation, and gate
  check, then hold it through late mutation, fresh-state authorization, PUTs, and save.
- Apply the same first-load-under-lock discipline to `pg_late_watch` and `pg_late_preview`.
- `pg_auto_post_disable` already begins under the lock; preserve that boundary.
- Add concurrency tests proving: two imports produce at most one PUT set; disable-first causes
  the later trigger to make zero PUTs; no stale pre-lock save can re-enable a disabled session.

### 4. Make the authorized Canvas payload and receipt gate match policy

Files: `api/powergrader/push_context.py`, `api/powergrader/autopush_executor.py`,
`api/powergrader/autopush_policy.py`

- Ordinary interactive sessions support normal grade **and comment** PUTs. Their
  `comment_writeback_supported=False` field distinguishes the New Quiz comments-only route; it
  does not mean ordinary comments are unsupported. New Quiz is excluded from auto-post.
- `build_interactive_push_context` must set its v2 policy and executor flags consistently:
  `allow_grade_push=True`, `allow_comment_push=True`, `grade_push_allowed=True`, and
  `comment_push_allowed=True` after the existing writeback/mode guards pass. An eligible
  interactive PUT must contain both `submission.posted_grade` and `comment.text_comment`.
- Receipt preflight is mandatory even when resolution returns `None`. In
  `run_autopush_for_session`, change the gate to skip whenever
  `effective_receipt_dir` is false, not only when a truthy input directory later fails. Missing
  workspace/receipt resolution must produce `skipped_reason="receipt_dir_unavailable"` and
  zero PUTs.
- When a candidate user is absent from `canvas_states_by_user`, pass the explicit
  `{"canvas_state_present": False}` sentinel to policy. It must return
  `blocked/canvas_state_unavailable`, not the generic incomplete-state result.
- `classify_assignment_for_autoscore` must require `grading_type == "points"`. A missing value
  is unsupported; do not allow it through with `if grading_type and ...`.
- Retain policy v2, baseline drift, excused/unsubmitted, existing-work, bounds, idempotency,
  post-PUT receipt-error, and posted-row behavior from the current diff.

### 5. Make packet-native late catch-up actually importable

Files: `api/webui/routes/powergrader_late.py`, `api/powergrader/ai_workflow.py`,
`api/powergrader/import_results.py`

- Packet mode currently merges Copilot batches but never appends the new unscored student rows.
  Append `students` to `session["students"]` in packet mode before saving. Their AI fields remain
  empty until import.
- Keep batch merge additive and keep each batch's `safe_bundle` path. Import of a late batch
  must find those appended users, update them, and return their exact IDs for scoped auto-post.
- Packet generation is not scoring. Packet late return/log fields use `generated` and
  `copilot_batches_added`; `ai_scored` must be zero or omitted for packet mode. Assisted mode
  keeps `ai_scored`.
- `ai_workflow.run_ai_workflow` currently computes `artifact_name` but still passes the plain
  `assignment_name` to `build_copilot_batches`. Pass `artifact_name` so late files/folders and
  packet metadata carry the Late Catch-Up label.
- Preserve the initial top-level `privacy_artifacts`; late artifacts remain append-only under
  `late_catchup_artifacts`.

### 6. Finish the browser behavior without hiding defects

Files: PowerGrader setup/queue templates and modules named in Scope.

- `queue_import.js` currently inserts a `<span>` into the `meta` string and then escapes the
  whole string, so the Late label renders as text. Escape ordinary metadata first and append a
  real Late badge separately.
- Packet late UI must say **Generate Late Copilot Batch** and report generated batches/users,
  not that students were scored or added to review before their rows actually exist.
- After disable, the queue must visibly say **Automatic posting is off** while retaining the
  latest prior summary/history. Hide only the disable action.
- Refresh auto-post, late-watch, packet, students, and badge state through the existing full
  session reload paths after import/late/disable.

### 7. Complete the work the previous report omitted

- Create `api/tests/test_powergrader_interactive_autopush.py`. Cover disabled/unsupported
  guards, fresh fetch plus assignment fallback, missing assignment/state, receipt resolution,
  exact subset semantics, happy grade+comment PUT, idempotent retry, summary/log sanitization,
  and lock/concurrency behavior.
- Update the existing import, late, packet, route-contract, queue-classifier, scheduled,
  policy, and executor tests listed later in this brief. Do not change a failing assertion
  merely to preserve a defect; update expected copy only where packet support intentionally
  changed it.
- Add the new disable route to `test_route_contract.py`.
- Update all durable docs named in Scope. The previous pass changed none of them.
- Run every focused command in Verification, then `py -m pytest api/tests`.
- Render `/powergrader` and `/powergrader/session/<private-fixture-session-id>`, exercise the
  listed interactions, and record zero new console errors.
- Do not run the live sandbox checklist without explicit user authorization. If it remains
  unauthorized, report **YELLOW**, not GREEN. GREEN is allowed only when every required check,
  including the user-authorized sandbox checklist, is complete.

### Correction-pass stop rule

If any required repair conflicts with repository behavior, stop with RED and name the exact
conflict. Do not silently omit a test/file/doc, claim no deviations, or substitute a smaller
test selection. Do not stage or alter the unrelated pre-existing handoff archive moves.

## Locked decisions

- Teacher-facing label: **Automatically post eligible AI results to Canvas**. The internal
  persisted/form key is `auto_post`; do not call it auto-accept because it writes to Canvas
  without locally accepting the draft.
- The opt-in is per new session, default-off, non-sticky, and never global. The app does not
  classify work as major/minor; checking the box is the teacher's formative-work judgment.
- V1 supports both `assisted` (OpenRouter) and `packet` (external AI paste-back) sessions.
  `fast`, Classic Quiz, and New Quiz sessions can never enable it; enforce this server-side
  even if a crafted request sends `auto_post=true`.
- Show one shared `CE_WRITE_REVIEW.confirm` prompt when a teacher starts an opted-in session.
  There is no second per-student confirmation. Cancelling the prompt sends no start request.
- Assisted results may auto-post immediately after session creation. Packet results auto-post
  only when a valid batch import supplies those results. Late assisted results auto-post only
  for newly appended users; packet late generation creates Copilot batches and does not score
  or post until those batches are imported.
- Auto-post eligibility is fail-closed. Fresh Canvas state, a fresh assignment snapshot,
  submission identity, policy checks, idempotency, and a writable receipt directory must all
  clear before any PUT.
- A student already auto-posted ends with `posted=true` and `status="auto_pushed"`. V1 has no
  reopen/override action in Canvas Expert. The queue tells the teacher to change that grade in
  Canvas SpeedGrader.
- Generalize the shared evaluator/executor vocabulary from scheduled `job` to push
  authorization `context` now. Scheduled decision/write behavior remains the same except for
  the deliberately safer checks in this brief.
- Set `autopush_policy.POLICY_VERSION = 2`. The new drift/presence rules materially change the
  evaluator used for receipts and idempotency, so they must not be recorded as policy v1.
  Existing scheduled opt-ins remain valid, but their effective evaluation/receipts use v2.
- Receipt-directory preflight is mandatory. A later receipt write can still fail after Canvas
  succeeds; record that error, keep the student marked posted, and document receipt capture as
  best-effort after the successful preflight. Do not add an invented "uncertain outcome" state.
- Serialize the authoritative interactive session mutation, fresh fetch, policy evaluation,
  Canvas PUTs, and final save with one in-process lock per session. The lock belongs at route
  orchestration, not solely inside a runner that receives already-fetched state.
- Keep the initial session's top-level `privacy_artifacts` unchanged. Late AI artifacts are
  additive private history, and every Copilot batch owns the SAFE bundle used to validate its
  import.
- Preserve unrelated worktree changes. In particular, do not stage, revert, or rewrite the
  existing handoff archive moves that predate this brief.

## Scope

### New files

- `api/powergrader/push_context.py`
- `api/powergrader/interactive_autopush.py`
- `api/tests/test_powergrader_interactive_autopush.py`

### Primary backend seams

- `api/powergrader/autopush_policy.py` — policy v2, `context` vocabulary, fresh-state and
  submission-drift rules, `ai_scoring_error` recognition.
- `api/powergrader/autopush_executor.py` — `context` vocabulary, receipt preflight, explicit
  missing-state sentinel, summaries/reason counts.
- `api/powergrader/scheduled_autoscore_support.py` — shared Canvas-state projection including
  identity, excused, and workflow fields.
- `api/powergrader/autoscore_queue.py::classify_assignment_for_autoscore` — points-only and
  individual-assignment eligibility.
- `api/powergrader/session_builder.py::{build_students,build_session}` and
  `api/powergrader/start_workflow.py::build_start_session` — submission baseline and session
  authorization state.
- `api/powergrader/session_store.py` — per-session lock context manager.
- `api/powergrader/import_results.py::import_results_into_session` — batch-owned SAFE bundle
  lookup and exact `updated_user_ids` result.
- `api/powergrader/copilot_packet.py::build_copilot_batches` and
  `api/powergrader/ai_workflow.py::run_ai_workflow` — prefixed late batch IDs, batch SAFE-bundle
  ownership, and artifact-name alignment.
- `api/powergrader/late_catchup.py` and `api/webui/routes/powergrader_late.py` — packet-native
  generation, additive artifact/batch merge, and honest assisted-vs-packet late state.
- `api/webui/routes/powergrader.py` and `api/webui/routes/powergrader_helpers.py` — form field,
  trigger orchestration, disable endpoint, lock boundaries, responses, and packet late gates.
- `api/webui/routes/routines_powergrader.py` — scheduled caller uses the generalized context
  builder and the hardened shared state projection.

### Browser seams

- `api/webui/templates/powergrader_setup.html`
- `api/webui/static/powergrader/setup_core.js`
- `api/webui/templates/powergrader_queue.html`
- `api/webui/static/powergrader/queue_core.js`
- `api/webui/static/powergrader/queue_import.js`
- `api/webui/static/powergrader/queue_late_catchup.js`
- `api/webui/static/powergrader_setup.css` and `api/webui/static/powergrader_queue.css` for the
  affected setup/queue presentation; do not add inline style attributes for this feature.

### Tests and durable documentation

- Update `api/tests/test_powergrader_autopush_policy.py`,
  `api/tests/test_powergrader_autopush_executor.py`,
  `api/tests/test_powergrader_import_results.py`,
  `api/tests/test_powergrader_late_catchup.py`,
  `api/tests/test_powergrader_copilot_packet.py`, and `api/tests/test_route_contract.py` where
  their existing interfaces are affected.
- Update classifier/scheduled integration coverage in
  `api/tests/test_powergrader_autoscore_queue.py` and
  `api/tests/test_powergrader_scheduled_autoscore.py`.
- Update `AGENTS.md`, `docs/contracts/feedback-scoring-contract.md`,
  `docs/reference/workbench-canonical-flow-map.md`,
  `docs/reference/powergrader-module-map.md`, and `api/webui/README.md` so the lasting product
  and safety rules do not live only in this execution brief.

## Out of scope

- No global/sticky setting, default-on behavior, assignment-level interactive preference, or
  reuse of an old session's authorization for a new session.
- No automated major/minor/formative classifier and no cumulative-totals authorization rule.
- No Classic Quiz or New Quiz grade/item write-back, and no change to the reviewed New Quiz
  transport.
- No local reopen/override of an auto-posted row. The teacher edits it in Canvas for v1.
- No scheduled-job UI redesign and no unattended packet/Copilot late routine. Packet late work
  is generated from the live PowerGrader queue and imported by the teacher.
- No distributed/multi-machine lock, database, transactional outbox, or broad session-store
  migration. This local app uses an in-process session lock; synced-workspace conflict handling
  remains outside this feature.
- No claim that receipt capture is infallible after a successful Canvas response.
- No live Canvas write test unless the user explicitly identifies and approves a sandbox
  course/assignment for that test run.

## Reference pattern and routing

- Project rules and high-risk evidence: `AGENTS.md`
- Confirmed Canvas transport guidance: `api/README.md`
- Canvas submissions endpoint and fields: official
  [Canvas Submissions API](https://developerdocs.instructure.com/services/canvas/resources/submissions)
- Existing pure decisions: `api/powergrader/autopush_policy.py::evaluate_student_for_autopush`
- Existing idempotent transport/receipt shape:
  `api/powergrader/autopush_executor.py::run_autopush_for_session`
- Existing scheduled orchestration:
  `api/webui/routes/routines_powergrader.py::_run_routine_powergrader_scheduled_autoscore`
- Existing session mutation/import: `api/powergrader/import_results.py::import_results_into_session`
- Existing route fetch shape: `api/powergrader/canvas_fetch.py::fetch_submissions`
- Existing packet batching: `api/powergrader/copilot_packet.py::build_copilot_batches`
- Existing late helpers: `api/powergrader/late_catchup.py` and
  `api/webui/routes/powergrader_late.py::_run_late_catchup_score`
- Existing frontend refresh ownership: `api/webui/static/powergrader/queue_core.js::loadSession`
  and `api/webui/static/powergrader/queue_import.js::refreshSession`
- Durable scoring/write boundary: `docs/contracts/feedback-scoring-contract.md`
- Durable ownership map: `docs/reference/powergrader-module-map.md`
- Read project-local `TOOLS.md` before using broad manual inspection. Its relevant indexer and
  Canvas documentation tools are currently marked planned; use narrow `rg`/file reads when they
  remain unavailable.

This handoff is an execution brief, not the durable product contract. Put lasting behavior in
the named contract/reference/README files as part of this implementation.

## Implementation requirements

### Checkpoint 1 — Generalize and harden the shared policy path

1. Add `api/powergrader/push_context.py` with these public builders:

   ```python
   def build_scheduled_push_context(job: dict) -> dict: ...
   def build_interactive_push_context(session: dict) -> dict: ...
   ```

   Each returns a new dictionary, never the caller's mutable object. It includes
   `course_id`, `assignment_id`, `status`, `auto_push`, `push_policy`, and `source`.
   Interactive context also includes `session_id`, uses source `interactive_session`, and
   derives `auto_push`/`push_policy.enabled` from `session["auto_post"]["enabled"]`.
   Scheduled context preserves the stored job's authorization/settings but stamps the
   effective `push_policy.policy_version` to `POLICY_VERSION` (v2) for evaluation and receipt
   audit. Both contexts allow grade and comment pushes only when their opt-in policy permits.

2. Rename the `job=` public parameter and job-named locals/helpers/docstrings to `context=` in
   `evaluate_student_for_autopush`, `run_autopush_for_session`, all callers, and tests. Rename
   `READY_JOB_STATUSES` to `READY_CONTEXT_STATUSES`. The two serialized job-worded failure
   reasons become `context_not_ready_for_push` and `missing_context_identity`; leave all other
   established reason codes stable.

3. Set `POLICY_VERSION = 2`. Verify a v1 auto-posted student with `posted=true` and a stored
   idempotency key remains blocked as already pushed rather than being sent again because the
   current version changed.

4. Tighten `classify_assignment_for_autoscore` in one place. In addition to its current quiz
   and submission-type rules, return `unsupported` unless `grading_type == "points"`, and
   return `unsupported` when `group_category_id` is populated. Interactive and scheduled paths
   both use this classifier; do not duplicate case-by-case checks in routes.

5. `session_builder.build_students` persists this exact snapshot from each source submission:

   ```python
   "submission_baseline": {
       "attempt": submission.get("attempt"),
       "submitted_at": submission.get("submitted_at"),
   }
   ```

   This automatically covers initial, scheduled, and `_build_late_catchup_students` callers.
   Do not add URLs, raw Canvas payloads, or additional PII to the baseline.

6. Extend `scheduled_autoscore_support.autoscore_canvas_states` as the shared state projector.
   Every returned row has `canvas_state_present=True`, `user_id`, `submission_id`, `attempt`,
   `submitted_at`, `excused`, and `workflow_state`, plus the existing score/comment fields.
   Preserve explicit `None` for missing identity fields so policy can distinguish missing data
   from an unchanged value.

7. `autopush_executor` must pass `{"canvas_state_present": False}` when a candidate user ID is
   absent from the fresh map; never collapse a missing row to `{}`. Add `ai_scoring_error` to
   `_has_error_blob`.

8. Apply this fail-closed decision matrix before allowing a write:

   | Condition | Decision | Reason |
   |---|---|---|
   | Fresh user row absent / presence sentinel false | `blocked` | `canvas_state_unavailable` |
   | Fresh row is excused | `blocked` | `submission_excused` |
   | Fresh `workflow_state == "unsubmitted"` | `blocked` | `submission_not_submitted` |
   | Fresh workflow state missing | `needs_review` | `canvas_state_incomplete` |
   | Baseline or fresh `attempt`/`submitted_at` missing | `needs_review` | `submission_identity_unavailable` |
   | Baseline and fresh `attempt` or `submitted_at` differ | `needs_review` | `submission_changed` |

   These checks precede the existing "Canvas work already exists" clearance. Existing sessions
   created before the baseline field was added therefore stay in review; do not infer a baseline
   from the same fresh response used for authorization.

9. Preflight the receipt directory once at the beginning of
   `run_autopush_for_session`, before the first PUT. Require a nonempty directory, create it,
   write a small sentinel, and remove the sentinel. Failure returns a normal result with zero
   writes and `skipped_reason="receipt_dir_unavailable"`. Keep the post-PUT receipt behavior
   locked above: a later receipt write error is added to `errors`, the successful Canvas write
   remains marked posted, and no new outcome state is invented.

10. Add `evaluated` and aggregated `reason_counts` to executor summaries while preserving the
    existing pushed/needs-review/blocked/errors/student-results/receipts fields. Do not put
    names, response text, feedback, or grades in summary/log reason aggregates.

11. Wire `routines_powergrader.py` through `build_scheduled_push_context(job_ref)` and the v2
    evaluator. Its assignment argument remains the freshly fetched `adata`; its submission map
    comes from the expanded shared projector. Update scheduled regression tests before moving
    on: eligible fixtures still write once, ineligible fixtures never write, and retry remains
    idempotent.

### Checkpoint 2 — Session authorization, fresh state, and serialization

1. Thread a new `auto_post_enabled: bool = False` kwarg through
   `start_workflow.build_start_session` into `session_builder.build_session`. New sessions store:

   ```python
   "auto_post": {
       "enabled": bool,
       "authorized_at": iso_or_none,
       "disabled_at": None,
       "policy_version": 2,
   },
   "auto_post_log": [],
   "auto_post_summary": None,
   ```

   Authorization time is set only when enabled. Old sessions missing this block behave as
   disabled. The disable endpoint later sets `enabled=False` and `disabled_at`, but never
   rewrites `authorized_at` or allows re-enable.

2. Add `session_store.session_lock(session_id)` as a context manager backed by a guarded
   registry of per-session `threading.RLock` objects. Sanitize the key with the existing
   `safe_session_id`. This is process-local serialization for the local app, not a distributed
   lock.

3. Add `api/powergrader/interactive_autopush.py` with these owned seams:

   ```python
   def interactive_receipt_dir(session: dict) -> str | None: ...
   def fetch_fresh_push_state(
       course_id: str,
       assignment_id: str,
       *,
       canvas_get_all,
       canvas_get,
   ) -> tuple[dict[str, dict], dict, str]: ...
   def run_interactive_autopush(
       *,
       session: dict,
       trigger: str,
       canvas_get_all,
       canvas_get,
       canvas_send,
       only_user_ids: set[str] | None = None,
       now=None,
   ) -> dict: ...
   ```

4. `interactive_receipt_dir` resolves to
   `<PowerGrader Sessions>/_private/autopush_receipts/session-<safe-session-id>/`.

5. `fetch_fresh_push_state` makes a fresh, paginated Canvas read after AI scoring/import, not
   before it. Use the existing student-submissions route filtered to one assignment:

   ```text
   GET /api/v1/courses/{course_id}/students/submissions
   student_ids[]=all
   assignment_ids[]=<assignment_id>
   include[]=assignment
   include[]=user
   include[]=submission_comments
   per_page=100
   ```

   Project rows through the shared state builder and return a fresh assignment object from the
   included `assignment` snapshot. If the call fails, returns no usable rows, or does not include
   authoritative assignment metadata, return an error and perform zero PUTs. A second focused
   assignment GET is an authorized fallback only if the current Canvas response/fixture proves
   `include[]=assignment` unavailable; never fall back to stale session/catalog metadata.

6. `run_interactive_autopush` owns guards, the fresh fetch, a shallow scoped student view, the
   shared executor call, and session summary/log mutation. It does **not** acquire or save the
   session lock itself; callers hold the lock around authoritative load through final save.
   Guards require an enabled v2 `auto_post` block, mode in `{"assisted", "packet"}`, and
   `canvas_writeback_supported is not False`. Fresh assignment policy still runs through the
   shared evaluator.

7. `only_user_ids` semantics are exact: `None` evaluates all current students; an empty set
   evaluates nobody; a nonempty set evaluates only matching user IDs. The shallow
   `{"students": [student_refs...]}` view must retain references so executor mutations reach the
   authoritative session.

8. Do not make a fresh Canvas call when auto-post is disabled or when `only_user_ids` is empty.
   A fresh-fetch error or receipt preflight failure records a skipped summary, saves the session,
   and leaves all drafts in the normal queue. It never fails open.

9. Each actual trigger result becomes both `session["auto_post_summary"]` and one append-only
   `auto_post_log` entry with `ts`, `trigger`, `evaluated`, `pushed`, `needs_review`, `blocked`,
   `reason_counts`, sanitized `errors`, and optional `skipped_reason`. The summary is the latest
   run, not a lifetime total. Do not promise that X-of-N means the entire session when a trigger
   was scoped to one imported/late batch.

10. Add `POST /api/powergrader/session/{session_id}/auto-post-disable`. Under the session lock,
    load the authoritative session, set enabled false/disabled time, save, and return the new
    block plus current summary. Re-enabling an old session is not supported. Disabling waits for
    an already-running locked trigger; UI copy should say it stops future automatic posting, not
    that it cancels an in-flight request.

11. Use the same session lock for all auto-post-related session mutations: disable,
    `pg_import_results`, `pg_late_score`, `pg_late_watch`, and `pg_late_preview`. Within import
    and late-score routes, hold the lock across authoritative load/mutation, fresh fetch,
    executor PUTs, and final save. Do not save a pre-import object after
    `import_results_into_session` has saved a newer one.

### Checkpoint 3 — Triggers and packet-native late catch-up

1. `pg_start` accepts `auto_post: str = Form("false")`. Derive the persisted boolean as truthy
   **and** normalized mode in `{"assisted", "packet"}` **and** not New Quiz. Ignore a crafted
   true value for every excluded mode. Save the initial session first. For an enabled assisted
   session, enter `session_lock`, reload authoritatively, run the initial trigger with
   `trigger="assisted_start"` and `only_user_ids=None`, save once more, and include the latest
   summary in `build_start_success_payload`. Packet start only stores authorization because it
   has no results yet.

2. `import_results_into_session` returns the exact de-duplicated `updated_user_ids` whose
   student dictionaries received imported results. Keep legacy non-batch import working.
   `pg_import_results` performs import under the session lock, reloads the saved authoritative
   session, and if enabled calls `run_interactive_autopush` with
   `trigger="packet_import"` and `only_user_ids=set(updated_user_ids)`. Return the latest summary
   in the route payload. A failed validation or empty updated set performs no Canvas fetch/PUT.

3. For assisted late catch-up, `_run_late_catchup_score` returns `appended_user_ids`.
   `pg_late_score`, while still holding the session lock, runs
   `trigger="assisted_late"` scoped to those IDs after a successful append, then saves and
   returns the summary. It must never evaluate all prior students because one late batch was
   added.

4. Open the current late gates to packet sessions without weakening New Quiz exclusion:
   `build_late_watch_state`, `_late_watch_error`, `pg_late_watch`, and
   `_run_late_catchup_score`. Packet mode does not require an OpenRouter key. Keep the assisted
   key/source-context requirements mode-specific; packet does not fail its gate solely because
   those assisted requirements are absent.

5. `ai_workflow.run_ai_workflow` accepts a neutral optional Copilot batch prefix and passes
   `artifact_name` (not the plain assignment name) to `build_copilot_batches`. Late packet calls
   use `mode=session["mode"]`, artifact name
   `<assignment> - Late Catch-Up <late-batch-id>`, and prefix `<late-batch-id>`.

6. `build_copilot_batches` accepts optional `batch_id_prefix` and `safe_bundle_path`. Initial
   IDs remain `batch-01`, `batch-02`, etc. Late IDs are globally distinct within the session,
   for example `late-20260715-142200-batch-01`. Every returned batch stores its own absolute
   `safe_bundle` path. Batch folders/labels use the provided artifact assignment name.

7. `import_results_into_session` resolves a batch first, then validates using
   `batch["safe_bundle"]`; fall back to top-level `session["privacy_artifacts"]["safe_bundle"]`
   only for old/legacy batches that lack the new key. Unknown batch IDs still fail without
   mutating the session.

8. On successful packet late generation:

   - Append new student rows with no `ai_score`/`ai_feedback` until import.
   - Mark each new batch with `late_catchup=True` and its parent late batch ID for UI labeling.
   - Append batches to `session["copilot_packet"]["batches"]`; never replace initial batches.
   - Recompute `batch_count` from the merged array and `student_count` from the merged batch
     student counts so retries cannot inflate totals by blind addition.
   - Append one entry to private `session["late_catchup_artifacts"]` containing timestamp,
     late batch ID, mode, privacy steps/artifact paths, and generated Copilot metadata. Never
     overwrite the initial top-level `privacy_artifacts` or initial packet folder fields.

9. Keep late-watch language honest. Assisted completion updates the existing
   `scored_user_ids`/`last_scored`. Packet generation instead updates new
   `generated_user_ids`/`last_generated`; it must not claim those students were AI-scored.
   Packet response/log fields use `generated` and `copilot_batches_added`, not a positive
   `ai_scored` count. `known_user_ids` is updated for both modes.

10. Packet generation performs no auto-post run. Its later batch import is the sole packet
    trigger and is scoped by `updated_user_ids`.

### Checkpoint 4 — Setup/queue UI and durable docs

1. Add the setup checkbox beside the late-watch option. Show it for packet/assisted, and
   hide, disable, and uncheck it for fast mode. Also disable/uncheck it when the selected
   `loadedAssignments` record is New Quiz. Keep the server enforcement authoritative.

2. Use this warning copy, with the packet variant explicitly saying the imported results come
   from the teacher's external AI:

   > Posts eligible AI scores and feedback to Canvas without your individual review. Intended
   > for minor or formative work. Students with existing Canvas grades, changed or excused
   > submissions, scoring errors, or out-of-range scores are held in the review queue instead.
   > Applies to this session only. If the assignment posts grades automatically, students see
   > results immediately.

3. In `bindStartSession`, place `auto_post=true|false` in the form data. When checked, await
   `window.CE_WRITE_REVIEW.confirm` before changing to the long-running start state. Cancel
   leaves the form usable and sends no request. Amend route-card/safety copy so review is the
   default but an explicitly enabled session is the stated exception.

4. Add a queue banner/control owned by `queue_core.js` (or one focused new PowerGrader queue
   module only if that is smaller than overloading core). Render the latest-run wording as:
   `Latest automatic-post run: X of N evaluated results posted; Y held for review; Z blocked.`
   Humanize `reason_counts` beside it. When disabled, keep visible text
   `Automatic posting is off`; hide only the disable action, not the feature status/history.

5. Refresh the banner after session load, successful batch import, and successful late action.
   Reuse the existing `loadSession`/`refreshSession` paths rather than manually merging stale
   response fragments into browser state.

6. For `status === "auto_pushed"`, render a `✓ Auto-posted` badge with the hint
   `To change this grade, edit it in Canvas SpeedGrader.` The existing approved-and-not-posted
   filters continue to exclude that row from ordinary single/bulk push.

7. In packet mode, label the late action `Generate Late Copilot Batch`; never call it Score.
   Render merged late batch cards with a visible `Late` label from their metadata. Preserve the
   current fresh-chat-per-batch instructions and batch-scoped paste boxes.

8. Update durable docs to state both narrow opt-in exceptions to draft-only behavior:

   - scheduled auto-push is per scheduled job/assignment;
   - interactive auto-post is per new PowerGrader session;
   - both are default-off, teacher-controlled, policy/idempotency/receipt guarded, and leave
     uncertain students in review;
   - packet late batches own their SAFE validation bundle;
   - New Quiz/fast remain excluded;
   - override is done in Canvas SpeedGrader for v1.

   Update ownership entries for `push_context.py`, `interactive_autopush.py`, the lock owner,
   trigger routes, and the queue banner. Do not describe this active handoff as a contract.

## Verification

Use fictional IDs/names and `tmp_path`; never put real course/student data in tests or output.

### Focused automated checks

```powershell
py -m pytest api/tests/test_powergrader_autopush_policy.py api/tests/test_powergrader_autopush_executor.py api/tests/test_powergrader_interactive_autopush.py
py -m pytest api/tests/test_powergrader_autoscore_queue.py api/tests/test_powergrader_scheduled_autoscore.py api/tests/test_powergrader_import_results.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_late_catchup.py api/tests/test_powergrader_packet.py api/tests/test_route_contract.py
```

Required focused coverage:

- Scheduled context-builder regression: same eligible/ineligible decision categories and one
  write max, now audited as policy v2.
- Baseline unchanged, changed attempt, changed submitted time, missing baseline, missing fresh
  row, missing workflow/identity, unsubmitted, and excused cases.
- Non-points/group/quiz assignment rejection and `ai_scoring_error` blocking.
- Receipt-dir success/preflight failure and post-PUT receipt failure behavior.
- Disabled/fast/New Quiz/writeback-unsupported interactive guards make zero GETs/PUTs as
  appropriate.
- Fresh fetch supplies both state and assignment; missing/stale assignment data never falls
  back to session metadata.
- `only_user_ids`: `None`, empty set, and subset have distinct behavior.
- Happy path mutates the referenced session row, writes a receipt, and records a sanitized
  latest summary/log.
- Idempotent second run and policy-v1 posted-row migration make no second PUT.
- Two concurrent imports/late triggers for one session produce one PUT set; a disable request
  serialized first prevents later posting. Assert the lock surrounds authoritative reload
  through save, not just executor iteration.
- Import returns exact updated IDs, route reloads authoritatively, per-batch SAFE bundle wins,
  legacy fallback still works, and unknown batch IDs fail unchanged.
- Packet late gates, unique prefixes, artifact-name pass-through, additive artifact history,
  batch merge/count recomputation, honest generated-vs-scored fields, and scoped post-on-import.

### Affected subsystem and integration suite

This is a cross-cutting high-risk API change, so run the full API suite after focused tests are
green:

```powershell
py -m pytest api/tests
```

Do not run the engine suite unless implementation unexpectedly changes `engine/` or shared
rendering behavior.

### Rendered browser verification

Run the local app and use rendered pages; source-text tests do not establish UI correctness.

```powershell
cd api
py qf_ui.py
```

Check both `/powergrader` and `/powergrader/session/<private-fixture-session-id>`:

- Fast/packet/assisted mode changes show, hide, and clear the checkbox correctly.
- Selecting New Quiz disables/clears it; an ordinary assignment restores eligibility.
- Confirm accept starts; confirm cancel sends no request and leaves controls usable.
- Queue banner renders pushed/held/blocked/skipped reason summaries and remains visible as off
  after disable.
- Auto-posted badge/hint renders and normal bulk/single push controls exclude the row.
- Packet late button says Generate, a merged prefixed late batch renders as Late, and import
  refreshes packet, queue, late-watch, and auto-post state.
- All affected pages have zero new browser-console errors and no failed static-resource loads.

Record the exact routes/interactions checked. Do not save screenshots or fixtures containing
student data in the repository.

### User-supervised Canvas sandbox acceptance

Do not issue these live writes until the user explicitly confirms a designated sandbox
course/assignment. If that confirmation is unavailable, complete automated/rendered checks and
return **YELLOW** with this checklist still pending.

1. Checkbox off behaves exactly as before in all three modes.
2. Assisted + auto-post prompts once, posts eligible grade/comment pairs, writes receipts, shows
   the banner/badge, and excludes posted students from normal push.
3. A pre-existing Canvas score/comment is held as `existing_canvas_work_detected`.
4. A resubmission between AI scoring and a later trigger is held as `submission_changed`.
5. Packet batch import posts only that batch; importing it again makes no duplicate PUT.
6. Packet late generation produces a unique Late batch; its import validates against its own
   SAFE bundle and posts only updated late users.
7. Assisted late catch-up posts only appended late users.
8. A crafted New Quiz `auto_post=true` request persists disabled and makes no PUT.
9. Disabling mid-session leaves later imports/late results in review.
10. Excused and unavailable-row fixtures never post.

Before final acceptance, provide the high-risk diff to the user/senior for review, specifically
calling out every Canvas PUT call site, session lock boundary, fresh-state fallback, receipt
failure branch, and persistent schema addition.

## Stop conditions

Stop with RED rather than guessing if:

- A named insertion point/interface is missing or its behavior contradicts this brief.
- The only available fresh Canvas response cannot supply authoritative assignment metadata and
  the authorized focused assignment-GET fallback also fails.
- Implementing the per-session lock would require a database, public service, or distributed
  workspace coordinator.
- Packet late generation would require replacing the initial SAFE/private artifacts or sending
  non-pseudonymized content externally.
- A New Quiz or fast-mode path would gain an automatic grade/comment PUT.
- A candidate could reach Canvas without fresh presence/identity/drift evaluation, idempotency,
  or receipt-directory preflight.
- Satisfying the UI requires bypassing `CE_WRITE_REVIEW`, adding sticky browser storage, or
  weakening the server guard.
- A credential, FERPA, live-write target, or post-PUT behavior is underspecified.
- An unrelated regression or the pre-existing handoff archive moves block completion.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to the
senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **YELLOW** — implementation and automated checks are green, but the required
  interactive browser/console pass was unavailable in this Codex runtime and the
  user-supervised Canvas sandbox checklist remains unauthorized.
- Commit hash: **uncommitted** (existing `dev` working tree; no commit created).
- Files changed for this feature:
  - **New:** `api/powergrader/push_context.py`,
    `api/powergrader/interactive_autopush.py`,
    `api/tests/test_powergrader_interactive_autopush.py`.
  - **Backend:** `api/powergrader/ai_workflow.py`,
    `api/powergrader/autopush_executor.py`, `api/powergrader/autopush_policy.py`,
    `api/powergrader/autoscore_queue.py`, `api/powergrader/copilot_packet.py`,
    `api/powergrader/import_results.py`, `api/powergrader/late_catchup.py`,
    `api/powergrader/scheduled_autoscore_support.py`,
    `api/powergrader/session_builder.py`, `api/powergrader/session_store.py`, and
    `api/powergrader/start_workflow.py`.
  - **Routes:** `api/webui/routes/powergrader.py`,
    `api/webui/routes/powergrader_helpers.py`,
    `api/webui/routes/powergrader_late.py`, and
    `api/webui/routes/routines_powergrader.py`.
  - **Browser:** `api/webui/templates/powergrader_setup.html`,
    `api/webui/templates/powergrader_queue.html`,
    `api/webui/static/powergrader/setup_core.js`,
    `api/webui/static/powergrader/queue_core.js`,
    `api/webui/static/powergrader/queue_import.js`,
    `api/webui/static/powergrader/queue_late_catchup.js`, and
    `api/webui/static/powergrader_queue.css`.
  - **Tests:** `api/tests/test_powergrader_autopush_policy.py`,
    `api/tests/test_powergrader_autopush_executor.py`,
    `api/tests/test_powergrader_autoscore_queue.py`,
    `api/tests/test_powergrader_import_results.py`,
    `api/tests/test_powergrader_late_catchup.py`,
    `api/tests/test_powergrader_scheduled_autoscore.py`, and
    `api/tests/test_route_contract.py`.
  - **Durable docs:** `AGENTS.md`, `api/webui/README.md`,
    `docs/contracts/feedback-scoring-contract.md`,
    `docs/reference/powergrader-module-map.md`, and
    `docs/reference/workbench-canonical-flow-map.md`.
  - Unrelated pre-existing handoff archive moves and concurrently added MCP-server work were
    preserved and are not part of this result.
- Verification commands and evidence:
  - `py -m pytest api/tests/test_powergrader_autopush_policy.py api/tests/test_powergrader_autopush_executor.py api/tests/test_powergrader_interactive_autopush.py`
    — **38 passed**.
  - `py -m pytest api/tests/test_powergrader_autoscore_queue.py api/tests/test_powergrader_scheduled_autoscore.py api/tests/test_powergrader_import_results.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_late_catchup.py api/tests/test_powergrader_packet.py api/tests/test_route_contract.py`
    — **48 passed**.
  - `py -m pytest api/tests/test_presentation_contracts.py api/tests/test_webui_template_contracts.py api/tests/test_powergrader_import_results.py`
    — **38 passed**.
  - Final `py -m pytest api/tests` — **724 passed, 1 skipped** (725 collected).
  - `git diff --check` — passed; only configured LF-to-CRLF warnings were emitted.
- Concurrency/failure evidence:
  - Two synchronized `pg_import_results` route calls use real temporary disk sessions and the
    real per-session lock, assert lock ownership at every authoritative load/save and Canvas
    sender boundary, and produce exactly one counted PUT.
  - A queued stale import is held behind the lock while disable saves first; it then reloads
    disabled state, retains imported drafts, produces zero PUTs, and cannot re-enable the
    session through a stale pre-lock load/save.
  - A route-level fresh-Canvas-fetch failure returns HTTP 200, stores the imported draft,
    performs zero PUTs, and persists the skipped latest summary/log.
- Local page/static smoke evidence (no lifespan/routine worker and no Canvas writes):
  - `GET /powergrader` — **200**.
  - `GET /powergrader/session/codex-fixture-auto-post-20260715` — **200**.
  - `GET /api/powergrader/session/codex-fixture-auto-post-20260715` — **200**.
  - All **22** referenced static resources returned 200; **0** static failures.
  - The private fictional fixture was deleted and the local server was stopped afterward.
- Interactive browser/rendered evidence: the installed Browser capability initialized, but
  discovery returned no available browser (`agent.browsers.list()` was empty) after the
  required troubleshooting path. Mode switching, confirmation accept/cancel, live DOM state,
  and browser-console errors therefore remain **unverified**; HTTP/source checks are not being
  presented as a substitute.
- High-risk self-review:
  - The only automatic Canvas PUT remains
    `autopush_executor.run_autopush_for_session`; interactive routes inject it only inside
    their session lock and scheduled orchestration uses the same executor.
  - Interactive fresh-state fallback is limited to the focused assignment GET; it never uses
    stale session/catalog assignment metadata.
  - Receipt preflight failure produces zero PUTs; a post-PUT receipt failure records an error
    while preserving the verified posted result.
  - Persistent additions are `submission_baseline`, policy-v2 `auto_post`, latest summary/log,
    idempotency/receipt markers, and per-Copilot-batch SAFE-bundle ownership.
- User-supervised Canvas sandbox checklist: **not authorized; no live Canvas write was issued**.
- Deviations from the brief: required interactive browser checks could not run because no
  browser backend was available. No feature-scope or safety decision was changed.
- Remaining blockers: provide an available in-app/Chrome browser for the rendered interaction
  pass, and explicitly authorize a designated Canvas sandbox course/assignment before the live
  acceptance checklist. Until both are complete, this result remains **YELLOW**.

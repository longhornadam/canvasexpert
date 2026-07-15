# Execution brief: Home attention that complements Canvas

Status: **ready for implementation**

Risk: **high** — Canvas submission/comment metadata is student-derived private data, even
though the durable output of this slice is aggregate-only.

Executor: **Luna**

## Outcome

Home gives a teacher a small, honest set of Canvas Expert-specific attention signals:
student comments that still need a human check, assignments appropriate for PowerGrader,
existing late-work normalization, and operational failures/partial results. Canvas Expert
does not recreate Canvas To Do, Coming Up, ungraded work, or an activity stream.

The page continues to open from local state. An explicit **Scan Current courses** action
performs the bounded Canvas read; no page load or navigation is blocked on it.

## Locked decisions

- Luna 4 is complete for its only approved consumer: PowerGrader Course Catalog v1. There
  is no generalized launch-sync coordinator to extend in this brief.
- Use the existing `api.work_registry` discovery request and durable generic job shape.
  Do not add a second Home store, persistence format, queue, or cache. The only durable
  data produced here is the existing PII-minimized aggregate finding.
- Read submission comments only inside `POST /api/work/scan`. Do not log, return, display,
  hash, or persist comment text, names, Canvas user IDs, or per-student state. The Home
  presentation sidecar remains subject to `work-registry-contract.md`.
- A comment is a definite human-follow-up candidate only when it is the latest ordered
  comment on a submitted/pending-review submission and its author is demonstrably that
  submission's student. A later Canvas Expert Teaching Assistant comment, identified by
  the canonical `TA SCORE + FEEDBACK` marker, does **not** resolve the candidate. A later
  non-student comment whose human/staff origin cannot be proved is *uncertain*, not
  "awaiting a human response"; report it only in a PII-free aggregate "staff response
  needs checking" finding. Do not infer a thread state Canvas does not provide.
- The new findings are assignment-scoped aggregate jobs, with counts only, and resume to
  existing Grade/PowerGrader entry points. Do not create a student list or comment-reply
  screen. A teacher gets the authoritative Canvas/PowerGrader context only after opening
  the target workflow.
- An assignment is PowerGrader-ready only when its assignment metadata advertises an
  `online_text_entry` submission type and it has ungraded submitted/pending-review work.
  Do not call it ready for file/media work, ordinary URL uploads, or a New Quiz merely
  because an assignment record happens to exist. The signal is advisory and does not
  bypass focused assignment refresh or native-renderer safeguards.
- Existing `late.work`, Work Registry routine/provider findings, prepared operations, and
  receipts remain their own authorities. Improve their Home copy/projection only where
  necessary to distinguish partial/failed/review-needed outcomes; do not add late math,
  reconciliation, or write behavior.
- Preserve the local-only bind and the existing request limit/deadline behavior. Background
  or focused Canvas requests must not be added to `GET /`, `GET /course-expert`,
  `GET /powergrader`, or Settings.

## Scope

- Add narrowly focused Work Registry discovery providers for aggregate comment-follow-up
  and text-entry PowerGrader suitability, or a shared provider module if it avoids
  duplicating the current assignments/submissions reads. Reuse one course's existing
  bounded assignment/submission read in `api/work_registry/discovery.py`; do not add
  per-assignment or per-student N+1 reads.
- Register the providers in the existing discovery flow and create the exact generic
  `finding()` records. Update `api/webui/routes/work.py::_aggregate_summary` with clear,
  PII-free titles, aggregate summaries, and correct local action labels.
- Update the Desk template/copy only as required to make the four attention categories
  comprehensible. Keep all generic start/attention/receipt DOM free of student-derived
  identifiers and comment text.
- Cover precise ordering/author rules, TA marker handling, uncertain staff cases,
  text-entry/non-text/New Quiz candidate classification, shared-read behavior, partial
  discovery, and rendered PII-free Home output with synthetic IDs only.
- Update `docs/contracts/work-registry-contract.md`,
  `docs/reference/workbench-canonical-flow-map.md`, and the relevant module map to state
  the provider ownership and aggregate-only boundary. Mark Luna 5 complete in
  `docs/reference/local-first-execution-roadmap.md` only after GREEN evidence exists.

## Out of scope

- No all-course launch synchronization, global request scheduler, or global readiness
  barrier.
- No durable comment, submission, roster, or student-response projection; no raw Canvas
  payload cache; no new privacy contract or migration.
- No automated comment reply, Canvas write, grade/late calculation, PowerGrader session
  creation, New Quiz detailed-response acquisition, or native-renderer workaround.
- No redesign of Student Reports, Parent Conference Prep artifact, generic Calendar/To Do,
  Canvas activity stream, or feedback/AI consolidation.
- Do not alter the already accepted Course Catalog v1 or focused assignment-evidence
  refresh owner except for a demonstrated regression that triggers RED.

## Reference pattern and routing

- Existing implementation to follow: `api/work_registry/discovery.py::_scan_course`,
  `api/work_registry/providers/grading_debt.py::scan_course`,
  `api/work_registry/providers/late_work.py::scan_course`, and
  `api/work_registry/providers/__init__.py::finding`.
- Existing display seam: `api/webui/routes/work.py::_aggregate_summary` and
  `api/webui/templates/dashboard.html`.
- Existing privacy rules: `docs/contracts/work-registry-contract.md` and
  `api/work_registry/models.py::_validate_hash_facts`.
- Test patterns: `api/tests/test_work_discovery.py`, `api/tests/test_work_registry.py`,
  `api/tests/test_work_routes.py`, and `api/tests/test_desk_routes.py`.
- Required roadmap/reference: `docs/reference/local-first-execution-roadmap.md`,
  `docs/handoffs/local-first-simplification-planning.md`, and
  `docs/reference/workbench-canonical-flow-map.md`.
- Read project-local `TOOLS.md` before broad inspection. It has no callable repository
  indexer; use targeted `rg` and synthetic fixtures only.

## Implementation requirements

1. Keep the existing assignments/submissions reads shared for every Home provider. Preserve
   current pagination, timeout, per-course error, last-good-cache, and partial-failure
   behavior. The same input can support multiple reductions but no provider may retain the
   source payload after the scan returns.
2. Implement the locked comment classifier with isolated pure helpers. Treat malformed,
   unordered, missing-author, or otherwise ambiguous comment data as non-definite; do not
   promote an uncertain case to an awaiting-human claim. Include the canonical TA marker
   comparison without copying comment content into an output, exception, or test fixture.
3. Project only assignment/course aggregate counts via `finding()`. Ensure `source_ref`,
   material version, titles, summaries, and URLs contain no private keys or terms rejected
   by the Work Registry validator.
4. Make PowerGrader suitability an advisory aggregate distinction from the pre-existing
   grading-debt logic. Existing ungraded-debt and late-work findings remain visible and do
   not become hidden or double-written.
5. Render and keyboard-check Home after scan with an empty result, definite comment
   follow-up, uncertain staff-response check, PowerGrader-ready assignment, late work,
   partial scan, and failed/partial receipt. Confirm no added browser-console error and
   inspect rendered generic output for PII-free copy.
6. Record the exact compact traffic-light report below before handback. Commit on `dev`
   only if the current user authorization and worktree state permit it.

## Verification

```powershell
py -m pytest api/tests/test_work_discovery.py api/tests/test_work_registry.py api/tests/test_work_routes.py api/tests/test_desk_routes.py api/tests/test_gradebook_routes.py
git diff --check
```

Render locally with synthetic-only configuration: `/`, `/course-expert`, `/powergrader`,
and `/settings`. On Home, exercise the scan and each required state above. Verify Create
and PowerGrader render without waiting for a Home scan and without new browser-console
errors.

## Stop conditions

Stop with RED rather than guessing if:

- Canvas comment payloads cannot establish ordering and the student author identity needed
  for the locked definite rule.
- Correct TA identification requires persisting or transmitting comment content, creating a
  new hidden Canvas marker, or weakening the honest uncertainty label.
- A useful target flow requires persisting/returning names, user IDs, comments, grades, or
  submission content in the registry, discovery cache, generic Home response, log, or
  fixture.
- Shared discovery reads cannot support the two reductions without a per-student or
  per-assignment request fan-out.
- A required behavior changes a Canvas write owner, the scoring contract, Course Catalog,
  focused evidence refresh, or New Quiz transport.
- A regression outside this scope, a credential question, or a live-Canvas probe is needed.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to
the senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **GREEN** — senior accepted the required local browser-console and keyboard
  verification reported by the user on 2026-07-14.
- Commit hash: changes are uncommitted on `dev`.
- Files changed: `api/work_registry/discovery.py`,
  `api/work_registry/providers/home_attention.py`, `api/webui/routes/work.py`,
  `api/tests/test_work_discovery.py`, `api/tests/test_work_routes.py`,
  `api/tests/test_desk_routes.py`, `docs/contracts/work-registry-contract.md`,
  and `docs/reference/workbench-canonical-flow-map.md`.
- Verification: `py -m pytest api/tests/test_work_discovery.py
  api/tests/test_work_registry.py api/tests/test_work_routes.py
  api/tests/test_desk_routes.py api/tests/test_gradebook_routes.py` — **33 passed,
  0 failed, 0 skipped**. `git diff --check` — passed.
- Rendered routes checked: synthetic-only `TestClient` rendering returned 200 for `/`,
  `/course-expert`, `/powergrader`, and `/settings`; no scan or Canvas read was invoked.
  The user subsequently verified the required local rendered browser-console and keyboard
  checks, which senior accepted on 2026-07-14.
- Deviations: none. The roadmap can now record Luna 5 GREEN in the Luna 6 closure batch.
- Remaining blocker: none.

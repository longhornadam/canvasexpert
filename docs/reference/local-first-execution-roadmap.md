# Local-first simplification: sequential execution roadmap

Status: **ordered planning roadmap; not an execution brief**

This roadmap converts the decisions in
`docs/handoffs/local-first-simplification-planning.md` into substantial, sequential
implementation batches. It exists so a lower-level executor never has to rediscover the
architecture or infer which subsystem should move first.

## Execution protocol

Updated 2026-07-14: implementation moves to an external senior-tier executor (Codex,
Terra/Sol class). The batch names below keep their historical "Luna N" labels for
continuity; they do not imply a Luna-tier executor.

- Run exactly **one implementation executor at a time**, regardless of tier.
- Before each batch, the senior (Claude, orchestrator role) creates or revises the single
  active brief in `docs/handoffs/` using `HANDOFF_TEMPLATE.md`, resolving that batch's named
  decision gate and current exact symbols. This roadmap is never handed to an executor as a
  substitute for an execution brief.
- The executor reads `AGENTS.md`, that one active brief, and only the references routed by
  it. A senior-tier executor does not expand scope, renegotiate locked decisions, or relax
  stop conditions — extra capability goes into implementation quality and self-review, not
  authority.
- The executor implements the complete batch, self-reviews against the brief's locked
  decisions, records the traffic-light result in the brief, and commits on `dev` when
  authorized.
- GREEN permits the senior to inspect the returned summary and risk seams, close/archive the
  brief in the same batch, and prepare the next brief. YELLOW returns to the same executor
  with narrow direction. RED returns to the senior and stops the sequence.
- Do not run a second planner, parallel implementers, or an automatic reviewer. Do not start
  the next batch while the prior brief, diff, verification, or decision remains unresolved.
- Each batch must leave current docs and module maps truthful. There is no separate cleanup
  or documentation-only executor at the end.

## Completed senior prerequisite — capability truth

The 2026-07-14 documentation audit is complete. Canonical behavior now lives in
`docs/reference/new-quizzes-grading-transport.md`. Current documentation distinguishes:

- public PAT-accessible list/report behavior with active enrollment;
- Canvas's signed, short-lived first-party item-grading transport;
- Canvas capability from Canvas Expert features that are still gated or unimplemented.

This prerequisite is not a Luna batch and must not be reopened without contradictory live
or official evidence.

## Decision gates Sol must resolve before the named batch

These are not delegated architecture questions:

1. **Before Luna 1:** lock the minimum durable assignment-scope identity/freshness record,
   OneDrive conflict behavior, current-attempt retention, and ordinary binary size/media
   policy. Default recommendation: preserve attempts observed from now on, do not backfill
   history, and never prefetch binaries at application launch.
2. **Before Luna 3 — resolved 2026-07-14:** a student with any manual item whose evidence
   requires SpeedGrader has their whole finalization routed to SpeedGrader; PowerGrader does
   not create a partial two-authority grading flow.
3. **Before Luna 4 — resolved for the first bounded consumer 2026-07-14:** do not launch-sync
   every Current course. PowerGrader persists assignment and module collections for the
   selected Current course, opens from last-good local state, refreshes once per course per
   page session, and offers explicit retry. No roster, submissions, comments, reports, or
   binaries enter this catalog. A broader multi-surface coordinator remains unapproved.
4. **Before Luna 7:** decide the surviving home for the existing Student Reports workflow.
   Do not invent the rejected Parent Conference Prep product merely to make navigation
   symmetrical.

## Luna 1 — Focused assignment refresh with one local evidence owner **(GREEN accepted 2026-07-14)**

Completed record: `docs/handoffs/archive/focused-assignment-refresh.md`.

Risk: **high** — private student evidence and FERPA-sensitive persistence.

Teacher-visible outcome:

> Selecting an assignment in PowerGrader refreshes that assignment's current Canvas state,
> preserves only missing or changed evidence in the canonical private course tree, reports
> whether the assignment is current/stale/incomplete, and opens the grading session from
> that shared local evidence without `(2)`-style duplicate acquisition.

Required scope:

- Make one focused assignment-refresh owner from the proven behavior in
  `api/powergrader/canvas_fetch.py`, `new_quiz_fetch.py`, `student_attachments.py`, and
  `api/webui/workspace.py`.
- Give the durable record an immediate consumer in the same batch: PowerGrader session
  creation references the shared evidence and records completeness instead of owning a
  second general download copy.
- Cover ordinary text/URL/upload evidence and the currently selected New Quiz attempt.
  Preserve explicit unsupported/failed evidence states; do not claim a complete snapshot
  when a file, report, or attempt join is missing.
- Reuse existing canonical files by Canvas identity/attempt and content indicators. Never
  rename or delete legacy evidence as speculative cleanup.
- Keep active queues, locks, partial files, and retry state machine-local. Only durable
  evidence and its minimum interpretation/freshness record enter the synced workspace.

Explicit exclusions:

- no all-course launch sync;
- no historical attempt backfill;
- no New Quiz writes;
- no Download Work UI retirement yet;
- no general offline Canvas database, adapter registry, or adaptive scheduler.

Expected verification seam:

- `api/tests/test_powergrader_attachment_workflow.py`
- `api/tests/test_powergrader_new_quizzes.py`
- `api/tests/test_workspace.py`
- focused new tests for unchanged reuse, changed evidence, partial failure, and duplicate
  prevention;
- rendered `/powergrader` start flow with zero new console errors.

Stop if the locked identity record cannot distinguish assignment, student, attempt, and
Canvas object without filename inference, or if OneDrive conflict handling requires a new
cross-machine authority model.

## Luna 2 — Retire duplicate Download Work acquisition **(GREEN accepted 2026-07-14)**

Completed record: `docs/handoffs/archive/retire-duplicate-download-work.md`.

Depends on: **Luna 1 GREEN**.

Risk: **high** — private evidence paths plus removal of an existing acquisition workflow.

Teacher-visible outcome:

> Work tools no longer presents Download Work as a separate job. The teacher gets
> assignment-contextual **Refresh from Canvas** and **Open local folder** actions, and the
> built-in download automation uses the same focused refresh owner as PowerGrader.

Required scope:

- Replace `push/download.js` and the Course Expert Download Work card with contextual refresh
  and folder actions that use the Luna 1 owner.
- Route the built-in download routine through the same owner or retire the routine if it has
  no distinct teacher outcome after replacement.
- Remove `api/downloader.py`, download routes, tests, and `streamSSE` only after repository
  search proves there are no surviving callers. Preserve compatibility reads of existing
  evidence; never delete teacher files.
- Update Course Expert and canonical-flow documentation in the same batch.

Explicit exclusions:

- no portable export feature without a demonstrated teacher request;
- no background binary prefetch;
- no Student Reports redesign;
- no navigation-wide rename yet.

Expected verification seam:

- `api/tests/test_downloader.py` migrated or removed only with caller retirement evidence;
- affected route-contract and template-contract tests;
- rendered `/course-expert`, `/powergrader`, and `/routines` checks with zero new console
  errors;
- repository search proving one live assignment acquisition owner.

Stop if an existing Download Work caller needs behavior the focused owner cannot provide
without broadening the persistence contract.

## Luna 3 — New Quiz item review and teacher finalization in PowerGrader **(GREEN completed 2026-07-14)**

Completed record: `docs/handoffs/archive/new-quiz-item-finalization-v2.md`. Archived RED records:
`docs/handoffs/archive/new-quiz-item-finalization.md` and
`docs/handoffs/archive/new-quiz-grader-transport-capture.md` — their blockers are stale:
the sessionless native read chain is live-verified (commit `7fb63b9`), the
`quiz_api_quiz_session_id` shape is normalized, and interim lanes shipped the same day
(per-item AI drafts merged per student, comment-only assignment-level feedback push,
upload-text AI payload policy).

Depends on: **Luna 1 GREEN** and the mixed-item decision gate.

Risk: **high** — official item scores/comments, credentials, undocumented first-party
transport, FERPA, ambiguous writes.

Teacher-visible outcome:

> For a mixed New Quiz, PowerGrader shows auto-graded items read-only and gives each
> supported manual text item a read-only Teaching Assistant proposal, an optional **My
> feedback** field, and a blank teacher score. One deliberate **Finalize student** action
> writes and verifies the teacher's item decisions without forcing an assignment total.

Required scope:

- Normalize the verified live `quiz_api_quiz_session_id` shape while preserving supported
  older/synthetic shapes.
- Add one narrow New Quiz grader adapter implementing the signed launch and short-lived
  credential chain from `new-quizzes-grading-transport.md`. Credentials and signed URLs
  remain memory-only and content-free in errors/logs.
- Extend the current item-aware session/import shape rather than creating a second scoring
  contract.
- Render the TA block read-only. Compose Canvas item feedback as optional teacher feedback,
  separator, then the TA score/feedback contract; omit the empty teacher section.
- Freeze the complete current result set, bind edits to stable item IDs and authoritative
  result ID, preserve untouched/auto-graded items, and write once per student finalization.
- Re-fetch the quiz session after every accepted/ambiguous write, follow the new
  authoritative result ID, verify each reviewed item and derived total, and capture a
  private content-minimized receipt.
- Keep exact SpeedGrader fallback links for capability drift or unsupported evidence.

Explicit exclusions:

- no AI-written official score;
- no per-keystroke Canvas writes;
- no New Quiz scheduled scoring or auto-push;
- no total-grade workaround through the ordinary Submissions API;
- no file/media grading outside Canvas's trusted renderer.

Expected verification seam:

- `api/tests/test_powergrader_new_quizzes.py`
- `api/tests/test_powergrader_import_results.py`
- `api/tests/test_powergrader_manual_push.py`
- new happy/failure/drift/ambiguous-result/idempotency tests with synthetic IDs only;
- rendered setup and queue flows for mixed items and SpeedGrader fallback;
- a live dummy write only if the user explicitly authorizes it for that execution brief.

Stop on any unrecognized launch/result shape, item mismatch, credential persistence, unclear
post-write authority, or inability to reconcile an ambiguous response.

## PowerGrader Course Catalog v1 **(GREEN accepted 2026-07-14)**

Implementation brief: `docs/handoffs/course-catalog-powergrader.md`. Durable contract:
`docs/contracts/course-catalog-contract.md`.

PowerGrader course selection now reads a strict, student-data-free assignment/module catalog
from the synced workspace before one selected-course background refresh. Module switching and
search are local, refresh failures retain usable last-good records, and explicit course-list
sync remains distinct from focused assignment-evidence refresh. This is the concrete
PowerGrader portion of non-blocking focus synchronization; it does not implement an all-course
launch job, generalized coordinator, or migration of other consumers.

## Luna 4 — Non-blocking launch and focus synchronization

PowerGrader's selected-course catalog portion is complete above. The remaining generalized
multi-surface coordinator scope is not executable without a new demonstrated consumer and
brief; do not rebuild the completed catalog vertical as an app-wide synchronization product.

Depends on: **Lunas 1–2 GREEN** and the launch-policy decision gate.

Risk: **medium** unless the locked durable projection adds student data, which raises it to
**high**.

Teacher-visible outcome:

> Canvas Expert opens immediately from the last good local state and shows a descriptive,
> per-scope refresh checklist. Focused teacher actions outrank background work, so opening
> Create to push a quiz is never blocked by unrelated grading synchronization.

Required scope:

- Add the smallest request coordinator needed by immediate consumers: focused assignment
  work, bounded Current-course background metadata, explicit refresh, and pre-write work.
- Reuse Luna 1 scope states (`unknown`, `refreshing`, `current`, `stale`, `incomplete`,
  `unavailable`) rather than inventing a global freshness boolean.
- Make background work yield to focused and pre-write requests. Keep last-good local state
  readable during refresh and partial failure.
- Surface course/scope progress without student names, submissions, grades, comments, or
  private paths in global UI/logs.
- Prove the Morning Panic constraint: Create renders and its selected-course preparation can
  proceed while unrelated background checks remain queued or fail.

Explicit exclusions:

- no all-course submission/comment/file sync;
- no adaptive concurrency framework;
- no global launch spinner or readiness barrier;
- no claim of transactionally consistent Canvas state.

Expected verification seam:

- focused coordinator/state tests plus `api/tests/test_desk_routes.py` and
  `api/tests/test_work_routes.py` where integration changes;
- rendered `/`, `/course-expert`, `/powergrader`, and `/settings` launch/focus interactions;
- synthetic slow/failing Canvas reads proving foreground work is not starved.

Stop if safe prioritization requires distributed locks or a generalized job platform rather
than a small local coordinator.

## Luna 5 — Conference-period Home that complements Canvas

Depends on: **Luna 4 GREEN**.

Risk: **high** — submission/comment metadata and teacher-response inference.

Teacher-visible outcome:

> Home answers “what needs my attention?” with conservative student-comment follow-up,
> work suited to PowerGrader, existing late-normalization attention, and Canvas Expert
> operational failures—without recreating Canvas To Do, Coming Up, or Recent Activity.

Required scope:

- Acquire submission/comment metadata only as a deferred Home/focused scope, never as a
  launch blocker.
- Mark a comment as awaiting human response only when ordering/authorship evidence supports
  it. Canvas Expert TA comments posted under the teacher token do not count as human
  responses. Label uncertain multi-staff cases honestly.
- Identify text-renderable PowerGrader candidates and native-renderer-required work without
  duplicating Canvas's generic ungraded list.
- Surface due/failed/partial/review-needed state from the existing Gradebook sweep,
  school-day/extra-time logic, operation-ledger receipts, and reconciliation. Do not create
  new late-score math or a second write owner.
- Keep student-derived presentation transient/private. Work Registry remains exact generic
  job authority, not a student-data store.

Explicit exclusions:

- no Parent Conference Prep narrative or artifact;
- no generic calendar, To Do clone, or activity stream;
- no automatic comment replies;
- no new late-normalization implementation.

Expected verification seam:

- `api/tests/test_work_discovery.py`, `test_work_registry.py`, `test_desk_routes.py`, and
  `test_gradebook_routes.py` where affected;
- synthetic comment-order/authorship cases including TA-token ambiguity and multiple staff;
- rendered Home checks with no PII in generic status/log surfaces and zero console errors.

Stop if Canvas data cannot support a conservative human-response inference without claiming
thread state that does not exist.

## Luna 6 — Consolidate FeedbackExpert into the grading owner

Depends on: **Luna 3 GREEN**. It may follow Luna 5 so the teacher-facing grading model is
stable before route retirement.

Risk: **high** — external AI transmission, pseudonym vault, scores/comments, compatibility
data.

Teacher-visible outcome:

> PowerGrader owns ordinary grading, OpenRouter scoring, external/Copilot JSON import, New
> Quiz response import, re-identification, review, and Canvas finalization. The standalone
> FeedbackExpert page redirects only after every still-used workflow has an accepted owner.

Required scope:

- Sol first supplies a parity matrix for the currently used FeedbackExpert routes against
  existing PowerGrader capabilities. Luna implements only demonstrated gaps.
- Reuse `feedback_*` privacy, scrub, vault, validation, persona, and pattern engines; do not
  copy or delete them for aesthetic ownership.
- Preserve SAFE/PRIVATE wording and workspace compatibility reads. Never delete a legacy
  `FeedbackExpert/` tree.
- Redirect `/feedback-expert` only after route/UI parity and teacher review/write safety are
  verified. Remove orphaned presentation code in the same closure batch.

Explicit exclusions:

- no new AI provider abstraction;
- no automatic global or New Quiz auto-push;
- no new scoring schema when the Feedback Scoring Contract already covers the item;
- no parent-report feature.

Expected verification seam:

- focused FeedbackExpert and PowerGrader packet/import/push tests;
- affected route and template contracts;
- rendered old-entry redirect plus PowerGrader advanced import/OpenRouter flows;
- explicit SAFE/PRIVATE and external-transmission checks.

Stop if parity requires changing the public scoring contract, weakening vault boundaries, or
silently migrating/deleting private data.

## Luna 7 — Finish the smaller teacher-facing product surface

Depends on: **Lunas 2, 5, and 6 GREEN** plus the Student Reports placement decision.

Risk: **medium**; raise to high if a live write path or private-data owner moves.

Teacher-visible outcome:

> Navigation consistently presents Home, Create, Grade, Students, Automations, and Settings.
> Duplicate acquisition and grading brands are gone, while stable internal routes/contracts
> remain compatible where they still protect real callers or private data.

Required scope:

- Apply the locked teacher vocabulary to navigation and page copy only after the underlying
  task ownership is true.
- Keep Forge contract names and internal `PowerGrader`, `FeedbackExpert`, operation-ledger,
  and compatibility workspace identifiers where renaming would create migration risk.
- Place the existing Student Reports workflow according to the senior/user decision without
  expanding its product scope.
- Update `workbench-canonical-flow-map.md`, affected module maps, and teacher-facing README
  material in the same batch.
- Preserve redirects for external bookmarks where cheap; remove only proven dead templates,
  scripts, and routes.

Explicit exclusions:

- no broad internal package/route rename for cosmetic consistency;
- no new dashboards or symmetric feature variants;
- no separate acceptance, archive, or cleanup agent afterward.

Expected verification seam:

- affected route/template contract tests;
- rendered navigation from every affected route, keyboard/focus behavior, deep links, and
  zero new browser-console errors;
- repository search proving removed labels/surfaces have no live consumer.

Stop if a requested label would misrepresent a still-mixed surface or if compatibility
removal risks saved links, private workspace reads, or a live Canvas write path.

## Order summary

```text
Capability truth (complete)
  -> Luna 1 focused shared evidence
  -> Luna 2 retire duplicate Download Work
  -> Luna 3 New Quiz item finalization
  -> Luna 4 non-blocking launch/focus sync
  -> Luna 5 useful Home attention
  -> Luna 6 FeedbackExpert consolidation
  -> Luna 7 product-surface finish
```

This order deliberately establishes data authority before background scheduling, proves the
high-value grading workflow before retiring its alternate surface, and changes labels only
after task ownership is true.

# Planning handoff: prioritized Canvas synchronization and a smaller product surface

Status: **planning — Lunas 1–3 and PowerGrader Course Catalog v1 complete**

Risk: **high**

Executor: **unassigned**

## Purpose

Define the runtime model that will let Canvas Expert open from durable local state,
refresh only the Canvas data that matters for the teacher's current work, and let all
features consume one coherent local working set. This is a planning checkpoint, not an
execution brief. Do not add a sync format, migrate workspace data, retire routes, or
change Canvas reads or writes until the granular data-scope decisions below are resolved
with the user and this file is converted into one bounded execution brief.

This planning work is currently more important than further surface-level cleanup. A
clear acquisition and freshness model will determine which visible features are real
teacher tasks and which are duplicate plumbing.

## Luna 1 decision gate — resolved 2026-07-14

The first execution brief completed GREEN and is archived at
`docs/handoffs/archive/focused-assignment-refresh.md`. Its locked implementation decisions
were:

- A private, versioned assignment-evidence manifest below the canonical `Courses/` assignment
  tree is the minimum durable identity/freshness record and the PowerGrader start consumer.
  It identifies Canvas course, assignment, student/submission, attempt, evidence object, and
  available change indicators; filenames are never identity.
- OneDrive conflicts fail closed: preserve competing files, do not merge, rename, delete, or
  choose a winner, and report the scope incomplete until a focused refresh can establish a
  clean record. Active coordination remains machine-local.
- Retain attempts observed after this work lands, with no historical backfill. A later attempt
  becomes current without deleting previously observed evidence.
- A focused assignment refresh has a 10 MiB aggregate binary budget. Each file must declare a
  size and fit in the remaining budget before transfer; otherwise it remains an explicit
  incomplete/native-review evidence case. Application launch never prefetches binaries.

## Luna 3 execution state — GREEN 2026-07-14

The completed record is archived at
`docs/handoffs/archive/new-quiz-item-finalization-v2.md`. Earlier RED transport-capture
records remain historical evidence; they no longer describe the current implementation
state.

## PowerGrader Course Catalog decision gate — resolved 2026-07-14

The teacher's repeated-course-selection workflow does not justify a global CanvasSync product
or an all-course launch coordinator. Course Catalog v1 persists the complete assignment and
module metadata collections for one selected Current course beneath `_System/Canvas
Catalog/<course-id>/`, with no student data, raw HTML, URLs, credentials, or private paths.
PowerGrader renders the last-good catalog first, searches it locally, and performs one
non-blocking selected-course refresh per page session plus explicit **Sync course list**.

This resolves the assignment/module picker authority for PowerGrader only. It does not
authorize launch synchronization of every Current course, migrate another consumer, or
replace focused live reads for submissions/evidence and Canvas-write safeguards. The durable
schema and OneDrive behavior live in `docs/contracts/course-catalog-contract.md`.

## Direction established with the user

### 1. The local working set should become the normal runtime source

Canvas Expert should preserve useful private course and submission material in the
teacher's configured synced workspace. Features should normally read that local working
set rather than independently downloading the same Canvas objects.

The intended loop is:

```text
Open immediately from last good local state
        -> refresh the scopes relevant to current work
        -> work locally
        -> recheck affected Canvas state
        -> deliberately apply writes
```

Canvas remains authoritative for published course state, enrollments, official grades
and comments, current submissions, and proof that a live write happened. Local state is
authoritative for teacher-authored content, preserved evidence, grading decisions, AI
drafts, reports, review state, and receipts.

### 2. Launch synchronization must not be a global readiness barrier

The app should render immediately from the last good local state. It must not make a
teacher who wants to push a quiz wait while unrelated old assignments, comments, files,
or New Quiz reports are checked.

There is no honest global `fresh` boolean. Freshness and completeness belong to a data
scope, normally qualified by course and sometimes assignment. A scope can be:

- `unknown` — no trustworthy local acquisition record exists
- `refreshing` — the last good local state remains readable while reconciliation runs
- `current` — the most recent requested refresh completed for that scope
- `stale` — usable last-good data exists but is older than its policy or a refresh failed
- `incomplete` — the refresh succeeded only partially or intentionally omitted material
- `unavailable` — no usable local state exists and Canvas acquisition failed

Features declare the scopes they need. They may open from stale local state when that is
safe, request a focused refresh, wait only for a required scope, or refuse a dangerous
action until a fresh preflight succeeds. The product should expose these distinctions in
plain language rather than presenting one application-wide spinner.

### 3. Synchronization is a prioritized task graph, not `download everything`

Every Canvas resource currently acquired by Canvas Expert must be classified before an
implementation is designed. The classification must name:

- Canvas endpoint or exceptional acquisition path
- local consumer(s)
- authority and local representation
- identity and change indicators
- relative request and payload cost
- FERPA and storage sensitivity
- launch, focus, explicit, scheduled, or pre-write trigger
- acceptable staleness
- partial-failure behavior
- binary materialization and retention policy
- whether a fresh live read is still required before a write

Initial priority language below is only a discussion scaffold, not a locked policy:

| Priority | Meaning | Likely examples |
|---|---|---|
| **Immediate local** | No Canvas wait; required to render the app | settings, Current-course list, existing sessions, local receipts |
| **Focused** | Refresh because the teacher opened or selected work | target assignment metadata, its submissions, required files, grading context |
| **Launch background** | Lightweight and broadly useful across Current courses | course availability and bounded assignment/work indicators, if proven cheap |
| **Deferred background** | Useful but not allowed to delay focused work | non-focused submission/grade metadata, ordinary new evidence within policy |
| **Explicit/expensive** | Run only for a named action or opt-in | large media, historical backfill, New Quiz detailed response reports, exports |
| **Pre-write** | Always live and narrowly targeted | drift checks and current target state before Canvas writes |

The actual items and priority assignments must come from repository inventory and user
decisions. Do not assume that all assignments, all historical attempts, all comments, or
all binary files belong in launch background work.

### 4. The synced workspace is a durable private working set, not a disposable cache

Use these conceptual boundaries:

- **Durable local course copy:** preserved submission evidence, authored content,
  grading work, reports, and the minimum identity metadata needed to interpret them.
- **Canvas projection:** selected course, assignment, roster, group, submission, grade,
  and freshness facts captured from Canvas for local use.
- **Machine-local synchronization state:** active request queues, locks, temporary
  downloads, retry state, and disposable indexes.

Private durable material belongs in the configured workspace under the canonical
`Courses/`, `AI Packets (Pseudonymized)/`, `Student Reports/`, and `_System/` boundaries.
It never belongs in the repository. Machine-local transient state must not be placed in
OneDrive merely for symmetry.

The exact durable identity/freshness record is unresolved. Avoid both extremes: filename
guessing cannot prove identity, while a general offline Canvas database is not justified.
Multi-machine OneDrive behavior must be considered before choosing mutable per-course,
per-assignment, per-attempt, or append-only records.

### 5. Download Work should not remain a second acquisition authority

Current `Download Work` and PowerGrader independently retrieve overlapping assignment
evidence and can create `(2)`-style duplicates. If the shared local working set becomes
the runtime model, standalone downloading is duplicate plumbing.

Provisional product consequence:

- Retire `Download Work` as a teacher-visible acquisition workflow.
- Replace it with contextual `Refresh from Canvas` and `Open local folder` actions.
- If teachers need a portable copy, provide a derived `Export submissions` action that
  reads already-local evidence and does not contact Canvas or create a second authority.
- Let Automations invoke the same synchronization owner rather than the current parallel
  downloader.
- Make PowerGrader consume the shared assignment evidence, requesting a focused refresh
  when its required scopes are stale or incomplete.

This does not yet authorize deleting `api/downloader.py`, its route, UI, routine, tests,
or existing local downloads. Compatibility and replacement behavior belong in the
eventual execution brief.

### 6. PowerGrader becomes a consumer and review authority, not the general fetch owner

PowerGrader remains responsible for its private session, grading queue, AI preparation,
teacher decisions, frozen review, drift checks, idempotency, and grade/comment write-back.
It should not own a second general copy of Canvas evidence.

Current limitations that the sync design must address honestly:

- PowerGrader acquires one selected assignment when a session begins.
- Ordinary uploaded files are preserved in the canonical course-first tree.
- Written-response bodies are primarily persisted in the private session rather than as
  a general teacher-facing local evidence artifact.
- Current reads do not guarantee a backfill of every historical attempt.
- Late catch-up refreshes one existing session and does not constitute course sync.
- New Quiz response and file acquisition uses an exceptional report/signed-file path.

PowerGrader must retain fresh, narrowly targeted Canvas preflight before any grade or
comment write even when the local working set was refreshed moments earlier.

## Teacher workflow slices and resulting boundaries

These are product probes, not a mandate to build every scenario discussed.

### Post-Test Morning — retained and central

The teacher opens a recently completed New Quiz containing auto-graded items plus written
responses. An AI teaching assistant performs preliminary scoring and feedback; the teacher
makes the official judgment.

Decisions established:

- The AI never writes its proposed number into Canvas's official grade field.
- AI feedback must self-identify as coming from a **Teaching Assistant** and state its
  preliminary score as `score earned/score available` at the top of the comment. This
  applies to either an item-level proposal or a whole-assignment proposal.
- The remainder of the Teaching Assistant comment follows one small contract: rubric
  justification, general **Glows and Grows**, then a plain-language Teaching Assistant
  signoff/disclosure that is clear without sounding legalistic.
- The teacher must manually enter the official grade in PowerGrader or SpeedGrader.
- AI output remains visibly separate from the teacher's official judgment.
- For a text-renderable New Quiz manual-response item, PowerGrader may accept the
  teacher's deliberately entered official **item score** and finalize it through the New
  Quiz result path. It must not substitute a forced assignment-total write for item state.
- Canvas Expert holds the Teaching Assistant item feedback locally until the teacher has
  completed the grading decision. It is not posted ahead of the official grading action.
- The teacher does not edit the Teaching Assistant block. PowerGrader provides a separate,
  optional **My feedback** field above it and composes the one Canvas item-feedback value
  only during finalization.
- File-upload or media evidence that does not render cleanly as trustworthy text requires
  Canvas SpeedGrader/DocViewer or another native renderer for final review. Examples include
  PDFs, presentations, images, audio, and video.

New Quiz item-level grading direction now established:

- For ordinary text-renderable assignments, PowerGrader may accept a deliberately typed,
  initially blank teacher grade and push that teacher-entered number after review.
- For a mixed New Quiz, PowerGrader should show auto-graded items as read-only and give each
  supported manually graded text item its own Teaching Assistant proposal plus a separate,
  initially blank teacher score control. The teacher—not the AI—supplies the official score.
- Finalization must be one deliberate student-level action over the complete current result
  set, not a Canvas write on every keystroke. PowerGrader must re-read the authoritative
  result, detect drift, merge only reviewed item decisions, post the complete result set,
  then re-fetch the quiz session and verify the **new** authoritative result version.
- If Canvas's first-party grading transport or result shape has drifted, PowerGrader fails
  closed, preserves the local review, and links to the exact SpeedGrader target.
- An item whose decisive evidence requires Canvas's native renderer remains a SpeedGrader
  case. **Resolved 2026-07-14:** if a student has any such manual item, route that student's
  complete finalization to SpeedGrader. Do not create a partial two-authority grading flow;
  preserve the PowerGrader review locally and provide the exact SpeedGrader target.

Canvas exposes one grader-feedback value per item, so PowerGrader composes the final value
without pretending Canvas has separate comment channels. When the teacher adds feedback,
the published item feedback is:

```text
MY FEEDBACK

<teacher's optional feedback>

-------

TA SCORE + FEEDBACK

<read-only Teaching Assistant block beginning with score earned/score available>
```

When the teacher adds no feedback, omit the empty `MY FEEDBACK` section and separator and
publish only the Teaching Assistant block. In PowerGrader, keep the teacher field editable
and the Teaching Assistant block visibly separate and read-only. Canvas Expert continues to
hold both until the teacher's final grading action.

### Morning Panic Assignment — retained and constraining

The teacher needs to create and push a page and quiz shortly before class. Background sync
must yield immediately. This workflow needs local authoring plus only the selected target
courses' module, assignment-group, and write-preflight state. It must not wait for roster,
submission, comment, grade, file, or New Quiz report acquisition.

Do not create a separate emergency mode unless ordinary prioritization proves insufficient.
Keep page and quiz operations independent initially; convenient placement into an existing
or new module is enough without inventing a lesson-bundle subsystem.

### Parent Conference Prep — explicitly out of scope

This scenario was thinking fodder only. Do not build a narrative/evidence product, parent
artifact, or new student-report workflow from it.

### Conference Period Catch-Up — retained as the Home test

Home should complement Canvas's native Dashboard rather than reproduce it. Research of
current Instructure guidance establishes:

- Canvas's instructor To Do list already shows work requiring grading across active courses,
  displays counts, and links grading items to SpeedGrader.
- The visible To Do list is bounded and removal-oriented; it is not a complete prioritization
  or Canvas Expert suitability view.
- Coming Up already shows near-term assignments and events.
- New submissions, late submissions, and submission comments can trigger configurable
  notifications, but those events are not shown in the Course Activity Stream.
- Submission comments can be viewed and replied to through an Inbox filter for recent
  comments, but Canvas does not document a durable Dashboard queue for comments awaiting
  an instructor response.

Therefore the strongest Canvas Expert Home candidates are:

1. **Student comments awaiting a human response.** Derive this conservatively from recent
   submission-comment order and authorship. A Canvas Expert Teaching Assistant comment must
   not falsely count as the human teacher's response merely because it posts under the
   teacher's token. Label uncertain cases honestly rather than claiming threaded state.
2. **Existing late-work normalization requiring attention.** Do not create a second late
   calculation. Surface due, failed, partial, or review-needed state from the existing
   Gradebook sweep, school-day calculation, per-student extra-time handling, operation-ledger
   receipts, and reconciliation path. A focused refresh may identify candidates, but the
   established automation remains the write owner.
3. **Work suited to PowerGrader.** Ungraded work is already visible in Canvas; Canvas Expert's
   added value is identifying text-renderable assignments/New Quiz written responses ready
   for preliminary AI assistance versus evidence that requires SpeedGrader.
4. **Canvas Expert operational attention.** Partial sync, scheduled-job review, ambiguous
   writes, or failed reconciliation that Canvas cannot surface.

Do not add a general upcoming-work calendar, generic ungraded list, or duplicate recent
activity stream merely because Canvas exposes the data.

## Product-surface conclusions that remain valid

Use **Canvas Expert** as the sole product brand. Prefer teacher tasks and ordinary nouns:

- Home
- Create
- Grade
- Students
- Automations
- Settings

Do not merely relabel a mixed surface. The current Create/Course Expert page also contains
Download Work and Student Reports. Those tasks must move to their honest owners or the
mixed page must retain a broader name until the structure changes.

Likely teacher-facing vocabulary:

- `Desk` -> `Home`
- `PowerGrader` -> `Grade an assignment` while retaining the internal subsystem name
- `FeedbackExpert` -> an advanced import capability inside grading after parity exists
- `Routines` -> `Automations`
- `AI Expert` / `AI-TA Library` -> `AI instructions` or `Helper files`
- `SAFE packet` -> `Pseudonymized AI files`, with honest non-anonymity wording
- `PRIVATE` -> `Private originals`
- `Identity Vault` -> `Private identity map`
- `Receipts` -> `Recent changes` or `History` in ordinary navigation

Canonical Forge contract names, internal packages, routes, and compatibility workspace
paths should not be renamed merely for aesthetic consistency.

## FeedbackExpert direction

FeedbackExpert is probably a teacher-visible surface to retire, not an engine to delete.
PowerGrader already reuses important feedback privacy, vault, scrub, scoring, and
validation machinery and has the stronger review/write path.

Before redirecting `/feedback-expert`, define one surviving owner for each workflow:

- ordinary assignment preparation and grading
- OpenRouter scoring
- manual/external JSON import
- New Quiz Student Analysis CSV import
- re-identification
- review and Canvas grade/comment push
- feedback-style and format administration

Preserve the shared `feedback_*` engine and Feedback Scoring Contract. Never automatically
delete an existing legacy `FeedbackExpert/` workspace tree. `/name-manager` already
redirects to Roster; the orphaned template can be removed only inside an authorized
consolidation brief.

## Canvas facts that constrain the sync design

- Canvas does not provide a transactionally consistent course snapshot. Report refresh
  windows and per-scope freshness rather than one exact snapshot time.
- Collection endpoints are paginated; follow opaque `Link` headers rather than assuming
  a requested `per_page` is honored.
- The multiple-assignment submissions endpoint can return all students and assignments,
  but incremental filters do not form one complete change feed. `submitted_since` omits
  unsubmitted records; grade changes have separate semantics.
- Binary attachments still require individual transfers.
- Core API throttling is dynamic and cost-based. Start with bounded, comprehensible
  request behavior and safe 429 handling; do not build adaptive concurrency without a
  measured need.
- Canvas Content Exports are appropriate for archive/backup, not operational submission,
  roster, or grade synchronization.
- New Quiz detailed response acquisition remains exceptional because it uses the quiz-LTI
  report path. Manual Student Analysis CSV remains a required fallback until replaced.
- New Quiz item-result grading is technically available through Canvas's current first-party
  grader transport for an actively enrolled teacher, but it is not documented as a stable
  public Canvas API. Treat it as a high-risk capability boundary with a runtime probe,
  short-lived session credentials, strict result-version verification, and a SpeedGrader
  fallback—not as an ordinary PAT REST endpoint.

Official references:

- https://developerdocs.instructure.com/services/canvas/basics/file.throttling
- https://developerdocs.instructure.com/services/canvas/basics/file.pagination
- https://developerdocs.instructure.com/services/canvas/resources/submissions
- https://developerdocs.instructure.com/services/canvas/resources/modules
- https://developerdocs.instructure.com/services/canvas/resources/content_exports
- https://developerdocs.instructure.com/services/canvas/resources/enrollments
- https://developerdocs.instructure.com/services/canvas/basics/file.graphql
- https://developerdocs.instructure.com/services/canvas/oauth2/file.oauth_endpoints

### Verified New Quiz grading transport — 2026-07-14

The earlier blanket statement that New Quiz item-response writes are unavailable through
the established PAT path was wrong. With the user's explicit authorization, a dummy course
and dummy student were probed without storing course-, user-, response-, token-, or grade
identifiers in the repository.

Observed first-party chain:

1. A saved Canvas PAT can request `/login/session_token` and establish a local Canvas web
   session for a feature not exposed as an ordinary public REST operation.
2. Canvas GraphQL supplies the submission's `previewUrl`; its signed LTI launch opens the
   New Quiz grading client and yields a short-lived participant-grading credential.
3. The participant grading endpoint resolves the quiz API host, quiz session, and a
   short-lived result token.
4. The first-party client posts the complete item-result collection plus fudge points to
   `/api/quiz_sessions/:quiz_session_id/results`. Each manual item has its own stable item
   ID, score, points possible, and grader-feedback value.
5. A temporary dummy item score and temporary grader feedback were each accepted (`201`)
   and verified after following the newly authoritative result. The temporary score and
   text were then cleared and re-verified.

Critical implementation fact: each accepted result update creates a new authoritative
result ID. Verification against the pre-write result ID reads a valid but superseded
version and can falsely report that a successful write did nothing. The implementation
must always re-fetch the quiz session after a write and follow its new authoritative result
ID before verifying item scores, feedback, and derived total.

This is evidence of current Canvas capability, not a promise of API stability. The public
New Quiz documentation covers quiz/item authoring and reports but does not document this
manual-grading transport. Isolate it behind one narrow adapter; never persist launch,
session, workflow, or result tokens; never log signed launch URLs; and fail closed on any
shape, authentication, or version mismatch.

Repository implications already confirmed:

- `api/powergrader/new_quiz_fetch.py` already obtains stable item responses, but its native
  candidate resolver currently recognizes `quiz_session_id`/`quizSessionId`; the live
  participant result uses `quiz_api_quiz_session_id`. The future brief must normalize the
  verified live key without breaking synthetic/older shapes.
- `api/webui/routes/powergrader.py` and `api/powergrader/session_actions.py` currently apply
  a blanket New Quiz write-back block. Replace that only inside the high-risk item-result
  vertical; do not relax ordinary frozen-review, drift, idempotency, or receipt controls.
- The existing PowerGrader import/session shape already carries `item_id`, proposed `score`,
  and `feedback`, so item-level Teaching Assistant drafts do not justify a second scoring
  contract. The missing work is authoritative item review UI plus the guarded Canvas
  transport and verification path.

## First-pass acquisition map from repository inspection

This is a routing inventory, not an approved priority policy. It records the current
overlap and gives the next discussion concrete units. Endpoint parameters and durable
shapes still require a narrower pass before implementation.

| Data scope | Current consumers and acquisition paths | Initial priority hypothesis |
|---|---|---|
| Saved connection and Current-course configuration | local `config`; readiness also probes `/users/self/profile` | **Immediate local**; optional connectivity probe must not gate launch |
| Accessible course catalog | Settings/dashboard course chooser via `/api/v1/courses` | **Explicit** when managing Current courses; configured Current courses already exist locally |
| Course identity/availability | multiple feature pickers and Course Info | **Launch background** only if a cheap bounded check materially improves status; never a blocker |
| Assignment collection | Course Expert, Gradebook, PowerGrader setup, Download routine, grading-debt and late-work discovery via `/courses/:id/assignments` | PowerGrader now uses the durable Course Catalog on selected-course focus; other consumers and any all-course launch policy remain undecided |
| Assignment detail | PowerGrader start, extensions, curves, content operations via `/assignments/:id` | **Focused** on selection; **pre-write** again when mutation safety requires it |
| Assignment groups | Create delivery controls via `/assignment_groups` | **Focused** only when creating/pushing content for a target course |
| Modules and module items | Create placement, PowerGrader module picker, Course Info, operation reconciliation | PowerGrader now uses focused selected-course Course Catalog refresh with bounded omitted-item fallback; write preparation/reconciliation and other consumers remain live and unchanged |
| Rubrics and rubric detail | rubric creation/update and grading context | **Focused** when authoring or grading needs them; live recheck before rubric mutation |
| Roster/enrollment projection | Roster, Gradebook, reports, pseudonym management, routines via `/users` or enrollments | Likely **focused** for Students/Grade and **deferred background** for warnings; names and IDs are private |
| Group categories, groups, memberships | differentiated creation, Roster, Course Info, roster-warning discovery | **Focused** when a group-aware feature opens; poor launch candidate because it fans out into many calls and has permission-dependent fallbacks |
| Course-wide submission metadata | Gradebook, late/grading-debt routines, Work Registry discovery via `/students/submissions` | Candidate **deferred background** scope; potentially high-value but broad, private, paginated, and not a complete change feed |
| Submission comments | grading-debt teacher-touch detection and focused grading review using `include[]=submission_comments` | **Deferred or focused**, not default launch, unless a cheaper reliable teacher-touch signal replaces it |
| Focused assignment submissions | PowerGrader, Feedback preparation, curves, standalone downloader via assignment or multi-assignment submissions endpoints | **Focused** and allowed to block that assignment workflow; shared local representation is a primary consolidation target |
| Written responses and submitted URLs | currently embedded in Canvas submission payloads; Download Work writes files while PowerGrader persists bodies in its private session | Materialize during **focused assignment refresh** first; course-wide background policy remains undecided |
| Ordinary attachment metadata and binaries | Download Work, PowerGrader attachment ingestion, Feedback preparation | Metadata follows the containing submission; missing/new binaries may run **focused** or **deferred background** within size/media policy |
| Historical submission attempts | not comprehensively backfilled by current acquisition paths | **Explicit/expensive** until Canvas history behavior, storage cost, and the product promise are locked |
| New Quiz assignment detection | assignment metadata plus New Quiz flags | Cheap detection can travel with assignment scope |
| New Quiz items, response reports, and signed files | PowerGrader `new_quiz_fetch` plus manual Student Analysis CSV fallback | **Focused/explicit only**; exceptional LTI/report acquisition must not become routine launch work |
| New Quiz authoritative item results and manual item write-back | Current first-party grading launch: Canvas web session + GraphQL preview URL + signed LTI launch + short-lived participant/result credentials | **Focused/pre-write/post-write only**; high risk, never launch background, always re-resolve the authoritative result version and fail closed to SpeedGrader |
| Grade, workflow, lateness, and rubric-assessment facts | submission payloads, Gradebook, routines, discovery, PowerGrader | Summary fields may travel with deferred submission metadata; rubric details remain focused; all writes require live preflight |
| Course late policy | Gradebook policy routes and operation-ledger adapter | **Focused** on Gradebook policy work and **pre-write** before changes |
| Assignment overrides/extensions | Gradebook extensions and operation-ledger adapters | **Focused/pre-write** for the named assignment/student; not general launch projection |
| Existing pages, quizzes, assignments, rubrics, and module placements used to prepare/reconcile content writes | operation-ledger adapters | **Prepare/pre-write/reconcile only**; do not synchronize merely for symmetry |
| Live target verification after a write | operation ledger and PowerGrader push path | Always **pre-write/post-write targeted live work**; never satisfied solely by the local projection |

Early architectural observations from this map:

- Assignment collections are the strongest plausible launch-background candidate because
  they are broadly reused and relatively bounded, but that is still a hypothesis.
- Group membership is a poor default launch task because one course can fan out into group
  category, group, and membership calls with a permission-dependent fallback.
- Course-wide submission metadata may power valuable Home/Automations signals, but it is
  the first genuinely expensive and FERPA-sensitive launch candidate. It needs its own
  product decision rather than inheriting priority from assignment metadata.
- Detailed evidence acquisition naturally belongs at assignment scope. A later background
  policy may prefetch new ordinary evidence, but PowerGrader must not require a second copy.
- Content-write preparation and verification reads are action-scoped safety work, not
  synchronization debt.

## Granular inventory required next

Before selecting a first implementation vertical, inventory every current Canvas read and
exceptional acquisition path. At minimum cover:

- course availability and configured Current courses
- assignments and assignment groups
- modules and module items
- enrollments/roster and group membership
- submission metadata, attempts, grades, comments, rubrics, and ordinary attachments
- New Quiz reports, item responses, and signed files
- Gradebook late-policy and snapshot inputs
- Course Expert creation/push context
- Student Reports and portfolio inputs
- Work Registry discovery providers
- Feedback preparation/import inputs
- scheduled routine inputs

For each item, record its present caller, endpoint, identity, likely payload size, private
fields, current cache behavior, consumers, and proposed trigger/freshness policy. This
inventory is architecture planning, not authorization to probe live Canvas or print private
workspace data.

## Open planning decisions

1. Which exact scopes deserve launch-background refresh, and which wait for course or
   assignment focus?
2. What does `current` mean for each scope: one launch, a time threshold, explicit user
   refresh, or comparison against Canvas change indicators?
3. Does preserved submission history promise only attempts observed over time, or an
   active backfill of all available historical attempts?
4. Which ordinary binaries download automatically, and what size/media limits require
   explicit approval?
5. Which New Quiz metadata can be cheap background state, and which detailed reports/files
   remain focused or explicit?
6. What durable identity/freshness record travels with the synced evidence without making
   OneDrive multi-machine conflicts an authority problem?
7. How do rename, removal, and disappeared-Canvas cases preserve evidence without silently
   accumulating misleading duplicates?
8. Which features may operate on stale local state, and which must block on focused refresh?
9. How should launch, background, focused, and pre-write work share one request coordinator
   without premature adaptive scheduling infrastructure?
10. Which teacher-visible progress facts are useful without exposing student PII in logs,
    screenshots, or generic navigation?
11. For a mixed New Quiz containing unsupported file/media evidence, does PowerGrader route
    the whole student's finalization to SpeedGrader, or may it finalize supported text items
    while preserving untouched item state for later native review?
12. What conservative rule makes a submission comment `awaiting human response`, especially
    when Canvas Expert Teaching Assistant comments and multiple course staff are present?

## Ordered implementation roadmap

The sequential plan is now durable in
`docs/reference/local-first-execution-roadmap.md`. It defines seven substantial Luna
batches, their dependencies, risk, verification seams, decision gates, and stop conditions.
Only one Luna runs at a time, and each batch receives one current execution brief rather
than treating the roadmap itself as executable.

The first assignment-evidence vertical and the PowerGrader Course Catalog vertical are now
implemented. Their combined teacher outcome is:

> PowerGrader opens a selected course from the last-good local assignment/module catalog,
> refreshes the course list without clearing usable local state, and performs a separate
> focused assignment refresh before grading from shared local evidence.

Do not expand these verticals into all-course background acquisition or migrate another
consumer without a new bounded teacher-visible brief. Course Catalog state cannot satisfy a
submission/evidence read or a Canvas-write preflight.

## Reference and insertion points for planning

- Canonical rules: `AGENTS.md`
- Canvas behavior and New Quiz facts: `api/README.md`
- Workspace ownership: `api/webui/workspace.py`
- Existing standalone downloader: `api/downloader.py`
- PowerGrader Canvas acquisition: `api/powergrader/canvas_fetch.py`
- New Quiz acquisition: `api/powergrader/new_quiz_fetch.py`
- New Quiz write gate and session actions: `api/webui/routes/powergrader.py`,
  `api/powergrader/session_actions.py`
- Existing item-level import/review fields: `api/webui/templates/powergrader_queue.html`
- Attachment preservation: `api/powergrader/student_attachments.py`
- PowerGrader private authority: `api/powergrader/session_store.py`,
  `api/powergrader/session_actions.py`
- Current local discovery contract: `docs/contracts/work-registry-contract.md`
- Sequential implementation roadmap: `docs/reference/local-first-execution-roadmap.md`
- Verified New Quiz capability: `docs/reference/new-quizzes-grading-transport.md`
- Current UI flow inventory: `docs/reference/workbench-canonical-flow-map.md`
- Feedback map and contract: `docs/reference/feedbackexpert-module-map.md`,
  `docs/contracts/feedback-scoring-contract.md`
- Write safety: `docs/contracts/operation-ledger-contract.md`
- Project-local tool routing: `TOOLS.md`, `tools/manifests/`

The project-local repo indexer and Canvas inspection tools are currently planned rather
than callable. Use targeted `rg`, narrow file reads, official Canvas documentation, and
synthetic fixtures. Do not inspect or print private workspace student data during planning.

## Planning guardrails

- No live Canvas write or external AI request during architecture planning unless the user
  explicitly authorizes a bounded dummy-data capability probe. The authorized New Quiz
  probe above is complete; it does not authorize additional live writes during planning.
- No live Canvas read/probe without explicit user authorization and a PII-minimized plan.
- Never store student names, IDs, submissions, grades, comments, or private notes in the
  repository, fixtures, planning logs, screenshots, or this handoff.
- Do not treat Work Registry as student-data or submission-content authority.
- Do not move machine-local operation-ledger or transient request state into OneDrive.
- Do not silently delete legacy FeedbackExpert data or canonical downloaded evidence.
- Do not promise a transactionally consistent Canvas snapshot.
- Do not weaken focused refresh or pre-write drift checks to reduce HTTP calls.
- Do not create a generic local Canvas database, adapter registry, or sync framework before
  a bounded vertical proves its required identities and consumers.

## Stop conditions

Stop and return to the user rather than locking a design if:

- A proposed launch task materially expands FERPA exposure, storage, or launch latency
  without a clear teacher benefit.
- Canvas endpoint behavior required for identity or change detection is unconfirmed.
- Multiple materially different OneDrive authority models remain viable.
- A scope cannot define honest freshness or partial-failure behavior.
- A consolidation would remove a Feedback/New Quiz/manual workflow without an accepted
  replacement.
- A write path would become weaker in review, drift, idempotency, ambiguous-outcome, or
  reconciliation handling.

## Conversion to an execution brief

After the data-scope inventory and priority decisions are complete, replace or revise this
file using `docs/handoffs/HANDOFF_TEMPLATE.md`. Name one teacher-visible vertical, exact
insertion points, persistence and compatibility decisions, focused verification, rendered
browser checks, FERPA boundaries, and live-write stop conditions. At most one implementation
executor may be active.

### Execution result

- Traffic light: **not started — planning only**
- Commit hash: **none; this handoff does not authorize implementation**
- Files changed: `docs/handoffs/local-first-simplification-planning.md`
- Verification: documentation and targeted source review only
- Rendered routes checked: none
- Deviations: planning format intentionally replaces the execution-ready status in the
  standard template
- Remaining blocker: later roadmap decision gates remain intentionally deferred until a
  demonstrated teacher workflow requires another bounded vertical

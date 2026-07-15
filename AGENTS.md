# AGENTS.md - Canvas Expert

Guidance for any AI agent working in this repo. Read this before editing.
This file is the canonical project guidance; keep it current when repo structure,
handoff locations, safety rules, branch policy, major workflows, or tool-routing
conventions change.

Do not create parallel root guidance files named for specific AI vendors or tools.
If a tool-specific note is unavoidable, make it point back here instead of
duplicating policy.

## What this is

Canvas Expert is a teacher's toolkit for Canvas LMS, split out of the QuizForge
monorepo. The repo has two main subsystems:

- **`api/`** - the **live, token-holding** app. It is a local FastAPI web UI
  (`cd api; py qf_ui.py` -> `http://127.0.0.1:8765`) plus CLI scripts that push
  authored content to live Canvas courses, run gradebook operations, download work,
  and support AI-assisted feedback/grading. It holds a Canvas access token and must
  stay local-only.
- **`engine/`** - the **offline** quiz/content rendering library (parse -> validate
  -> render -> package to Canvas QTI / physical formats). It has no network, no
  token, and no student data.

Authoring contracts live in **`LLM_Modules/*_Base.md`** (QuizForge, AssignmentForge,
PageForge, RubricForge). These are **canonical**. `api/` consumes them; never fork or
"fix" a contract by editing backend code. For confirmed Canvas API behavior and push
details, read **`api/README.md`** before touching push logic.

## Branch policy

This repo uses exactly two durable branches:

- **`main`** - stable baseline / release branch.
- **`dev`** - active integration branch and the default branch for agent work.

Agents must respect this two-branch model:

- Do normal work on `dev`, unless the user explicitly says otherwise.
- Do not create, push, or preserve extra long-lived branches.
- Before claiming a machine is up to date, fetch from the remote and compare the
  current branch against `origin/dev` and `origin/main`.
- If a temporary branch is explicitly required for a pull request or experiment,
  name it clearly, target it back to `dev`, and delete it after merge/closure.
- Do not merge branch histories or delete branches as cleanup without first checking
  for unmerged commits and confirming the intended target.

## Current feature map

**Course Expert** (`/course-expert`) is the primary push/download surface: Quiz,
Assignment, Page, Rubric, Download Work, Student Reports, and Quick assignment tabs.
It uses bookmarked courses from Settings, multi-course push selection, local temp
uploads, and the authoring contracts above.
For low-token debugging and file ownership, start with
`docs/reference/course-expert-module-map.md`.

**Settings** (`/settings`) handles Canvas token/base URL, OpenRouter settings,
bookmarked courses, workspace/download paths, AI-TA library rebuilds, and academic
calendar activation. Token handling remains credential-store only. For low-token
debugging and file ownership, start with `docs/reference/settings-module-map.md`.

**Gradebook Expert** (`/gradebook`) handles single-course gradebook operations:
late policy and school-day sweep, extra-time roster, due-date extensions, curves, and
grade snapshots. Roster context and monitored-student state are private student data.
The browser side is modularized under `api/webui/static/gradebook/`; for low-token
debugging and file ownership, start with `docs/reference/gradebook-module-map.md`.

**Roster** (`/roster`) is the student-level Canvas-group and local-settings console.
It has helper splits on the backend (`roster_canvas.py`, `roster_helpers.py`,
`roster_groups.py`) and feature splits on the browser side (`roster/bulk.js`,
`roster/groups.js`, `roster/safety.js`). For low-token debugging and the next
refactor targets, start with `docs/reference/roster-module-map.md`.

**Routines** (`/routines`) are local automations, not cloud jobs. Built-ins include
late-work sweep, download, curve, grading-debt report, and monitored-student report
refresh. Custom routines can be added under `api/custom_routines/`; see
`api/custom_routines/AUTHORING.md`.

**FeedbackExpert** is the pseudonymized scoring/feedback pipeline behind
`/feedback-expert`, `/name-manager`, and Push feedback to Canvas. The route layer
is split under `api/webui/routes/feedback_*.py`; the pipeline facade
`api/feedback_pipeline.py` re-exports focused helper modules. It is built around
the **Feedback Scoring Contract** (`docs/contracts/feedback-scoring-contract.md`):
any scoring tool emits LLM-agnostic JSON, Canvas Expert validates it, re-identifies
through the local vault, and lets the teacher review before `PUT` grade/comment calls.
Workspace layout is under `<workspace>/Courses/`, `<workspace>/AI Packets
(Pseudonymized)/`, `<workspace>/Student Reports/`, and `<workspace>/_System/`.
`FeedbackExpert/` is a compatibility-read location only; new writes use the
canonical roots. New Quizzes item-level score and grader-feedback writes are available
through Canvas's actively-enrolled first-party grader launch, but current Canvas Expert
routes still block that write-back until the high-risk reviewed transport is implemented.
Do not describe this as a PAT limitation; see
`docs/reference/new-quizzes-grading-transport.md`.
For low-token debugging and file ownership, start with
`docs/reference/feedbackexpert-module-map.md`.

**PowerGrader** (`/powergrader`) is the keyboard-first grading queue for one Canvas
assignment. It is now modularized:

- Thin routes: `api/webui/routes/powergrader.py`
- Backend helpers: `api/powergrader/`
- Frontend assets: thin shims `api/webui/static/powergrader_setup.js` and
  `api/webui/static/powergrader_queue.js`, with feature files under
  `api/webui/static/powergrader/`
- Tests: `api/tests/test_powergrader_packet.py`,
  `api/tests/test_powergrader_copilot_packet.py`,
  `api/tests/test_powergrader_import_results.py`,
  `api/tests/test_powergrader_late_catchup.py`

For low-token debugging and current file ownership, start with
`docs/reference/powergrader-module-map.md`.

PowerGrader's course picker reads the durable, student-data-free **Course Catalog v1** from
`<workspace>/_System/Canvas Catalog/<course-id>/`. Course selection, module switching, and
assignment search use that local projection before one bounded background refresh of the
selected Current course. The contract is `docs/contracts/course-catalog-contract.md` and
the backend owner is `api/course_catalog.py`. This catalog is navigation/search context
only: focused submissions/evidence and every Canvas write still require their existing live
paths and safeguards. Do not add student data, raw HTML, URLs, credentials, or private paths
to catalog records, and do not treat it as a write preflight.

PowerGrader modes:

- **Grade Myself** - fetch submitted work into one local session; no AI packet and no
  API call.
- **Use My AI Chat** - write SAFE/PRIVATE artifacts, keep the legacy Safe AI Packet
  ZIP, and create Copilot-friendly batch folders. Each Copilot batch folder contains
  exactly three numbered upload files: assignment information, rubric + TA
  personality, and that batch's pseudonymized StudentWork. The teacher starts a fresh
  Copilot chat per batch, then pastes each JSON response into the matching batch panel
  in the same PowerGrader session. Batch imports validate `pseudonym` and `item_id`
  against the selected batch before updating AI suggestions.
- **Auto-Score With API** - sends only the SAFE pseudonymized packet to the configured
  OpenRouter model after price/budget checks, then loads AI suggestions into the same
  review queue. Auto-Score sessions can optionally watch for late submissions; late
  catch-up reuses the original session's pseudonymized SAFE/PRIVATE route and stored
  scoring context, appends new AI drafts to the review queue, and still requires
  teacher review before any Canvas grade/comment push.

Scheduled auto-push is allowed only as a teacher-controlled, per-assignment or per-job
opt-in for a specific scheduled PowerGrader run. It must never become global or
default behavior. Any implementation that writes Canvas grades/comments from a
scheduled job must run reviewed policy checks, idempotency protection, and audit
receipt capture, and it may only push AI-generated results for eligible students.
Blocked, uncertain, unsupported, or otherwise review-needed cases stay in the review
path. Local-only, FERPA, and secret-handling guardrails remain unchanged.

PowerGrader sessions are stored under `<workspace>/_System/PowerGrader/Sessions/`
and jobs under `_System/PowerGrader/Jobs/`. They are PRIVATE:
real names, submission content, grades, and teacher comments must never be committed.
AI suggestions are drafts until the teacher reviews, edits, approves, and pushes,
except for the narrow scheduled auto-push path above where the teacher has explicitly
opted in for that specific job and policy/idempotency checks clear the write.

**AI Expert** (`/ai-expert`) serves paste-ready LLM skill files from the AI-TA library:
start-here orientation, authoring skills for the Forge contracts, scoring skills from
rubrics, and MagicSchool/Copilot-oriented toolkit files.

For a teacher-facing UI reference, read **`api/webui/README.md`**.

**Physical rendering stack:** printable PDFs are emitted from shared HTML/print-CSS
by launching the installed Microsoft Edge through Playwright. Do not reintroduce
Playwright-managed browser downloads; district-managed PCs may block them.
Editable DOCX output uses `pypandoc-binary`, which bundles Pandoc. If Edge lives in
a nonstandard location, `CANVAS_EXPERT_EDGE_PATH` can point to `msedge.exe`.

## Guardrails (non-negotiable)

1. **Never commit secrets.** The Canvas token lives **only** in the OS credential store
   (`keyring`, Windows Credential Manager) for the Web UI, or in `api/.env` (gitignored)
   for CLI. A `.githooks/pre-commit` hook (wired via `core.hooksPath`) blocks the token
   pattern as a backstop - do not rely on it; don't paste tokens into tracked files,
   logs, test fixtures, or commit messages.

2. **Never commit student data (FERPA).** This app reads gradebooks, downloads
   submissions, and stores monitored-student notes. Student names, IDs, submission
   content, grades, and private notes must **never** land in the repo, a commit, a test
   fixture, or printed output that could be captured. Student exports go to the synced
   workspace / local output dirs (gitignored: `api/out/`, `api/temp/`, reports roots),
   in-tenant and FERPA-safe - never the repo. When in doubt, treat anything course- or
   roster-derived as PII.

3. **No district-specific config in the repo.** District URLs, calendars, rubric names,
   and the like belong in the **UI** and the **user-chosen synced workspace** (default
   `OneDrive\CanvasExpert\`, overridable; last-writer-wins `settings.json`) - not in
   source. The repo is district-agnostic: `CANVAS_BASE_DEFAULT` is empty (an empty base
   is the signal that first-run onboarding isn't complete); calendars are
   **data-driven** - the app lists whatever CSVs live in the workspace `Calendars`
   folder. The only calendar content shipped in-repo is a blank `calendar_template.csv`
   and a **fictional** `Summer_Session_Sample.csv` for testing. Do not reintroduce a
   real district's URL, calendar, or school/teacher name anywhere in source.

4. **Local-only, never exposed.** The Web UI binds `127.0.0.1`. Do not change the bind
   address, add public routes, or otherwise make this app reachable off the machine.
   Nothing in `api/` is public web infrastructure. If a separate public site exists or
   is added later, keep it physically and operationally separate from this token-holding
   app.

5. **AI packet wording must stay honest.** SAFE files use pseudonyms and scrub obvious
   identifiers, but do not promise that Copilot, ChatGPT, OpenRouter, or any other
   model is "FERPA safe", "guaranteed anonymous", or unable to infer identity. Tell
   teachers to review SAFE files before uploading them.

## Execution model: senior design, one executor

Canvas Expert uses a deliberately small execution hierarchy. The senior/orchestrator
owns architecture, scope, and acceptance. One implementation agent executes a durable
handoff. This may be a Codex subagent or an agent the user runs in VS Code; the brief is
the same either way.

When model tiers are available, use these roles:

- **Sol (senior/orchestrator):** understands the product, resolves technical decisions,
  writes the handoff, chooses the executor, and accepts or redirects the result.
- **Luna (default executor):** implements bounded work that follows established patterns.
- **Terra (senior executor):** implements cross-cutting, architecture-heavy, or
  guardrail-adjacent work. Terra is an alternative to Luna, not an automatic reviewer.

The user may always choose an external executor instead. Do not spawn agents merely to
write, restate, review, or independently rediscover a handoff. Unless the user explicitly
authorizes more, **at most one implementation subagent may be active for a task**.

### Senior/orchestrator responsibilities

Before delegation, the senior must:

1. Understand the relevant product path and make the hard technical decisions.
2. Discuss any product choice that materially changes the user's requested direction.
3. Write one execution brief in `docs/handoffs/` using `HANDOFF_TEMPLATE.md`.
4. Make the brief large enough to deliver a meaningful vertical improvement, normally
   half a day to two days of implementation work. Do not manufacture numbered micro-slices.
5. Name exact boundaries, insertion points, reference patterns, risk level, verification,
   and stop conditions so the executor is not asked to perform architecture discovery.

The senior does not implement in parallel with the executor, commission a second planner,
or send the completed work through an automatic reviewer. For ordinary green work, inspect
the returned summary and relevant risk seams rather than rereading the whole repository or
rerunning successful checks.

### Executor responsibilities

The executor must:

- Read `AGENTS.md`, the active handoff, and only the references routed by that handoff.
- Preserve unrelated worktree changes and remain inside the authorized scope.
- Implement the whole brief, self-review against its locked decisions, and run only the
  required verification.
- Reuse the same working context for corrections. A yellow result goes back to the same
  executor when possible; do not spawn a fresh agent for each repair.
- Return a compact report with traffic light, commit hash if committed, files changed,
  commands and counts, deviations, and any unresolved decision.
- Record that same compact report in the active handoff's `Execution result` section before
  handback. Execution state and test evidence must not live only in chat.

Traffic lights mean:

- **GREEN:** the brief is complete, required checks passed, and there are no undeclared
  deviations. The senior may accept without duplicating the test run.
- **YELLOW:** implementation is partly complete, a required check is unavailable, or one
  bounded decision is needed. Continue with the same executor after direction.
- **RED:** the repository contradicts the brief, a guardrail is underspecified, or a public
  contract/architecture expansion is required. Stop implementation and return to the senior.

### Durable context rules

No important decision may exist only in chat or a subagent's memory. The active handoff is
the durable context checkpoint and must contain the objective, locked decisions, scope,
references, verification, and stop conditions before implementation begins.

If an executor is replaced or work resumes after context compaction, the new executor reads
the handoff (including its latest execution result), current diff/commit, and any narrow
follow-up direction. It does not repeat broad discovery. Durable product decisions belong
in `docs/contracts/` or `docs/reference/`; the handoff links to them instead of copying them.

### Escalation

Stop and report instead of guessing when:

- A named insertion point, symbol, interface, or assumption does not exist.
- Existing behavior contradicts the plan.
- Multiple materially different implementations satisfy the requirement.
- Satisfying the requirement requires changing another subsystem or public contract.
- A guardrail or external side effect is involved but not completely specified.
- A regression is discovered outside the authorized scope.

## Lean engineering framework

Canvas Expert is a local teacher-time-saving application, not public critical
infrastructure. Engineer rigor in proportion to the harm of failure.

### Product and architecture defaults

- Start from the teacher-visible outcome. Prefer one vertical batch from action to result
  over a sequence of infrastructure-only slices.
- Do not add infrastructure, registries, adapters, persistence formats, or durable contracts
  without an immediate consumer in the same agreed body of work.
- One implementation does not justify an abstraction. Extract shared machinery only after
  real repetition makes it simpler than the concrete code.
- Do not implement features for symmetry. An adapter or workflow for one content type does
  not require equivalents for every other type.
- Internal dictionaries and private helper seams do not need durable public contracts unless
  they cross independent consumers or version/persistence boundaries.
- Prefer reversible local behavior and the smallest change that satisfies the outcome.
- Completed infrastructure may remain stable without being expanded into every subsystem.
  Actual teacher use, defects, or measured friction should pull future integration.
- Batch related pattern-following work when context and verification carry over. Avoid
  acceptance, repair, and archive slices created only by the process itself.

### Risk levels and proportional evidence

Classify the handoff before choosing verification:

| Risk | Typical work | Default evidence |
|---|---|---|
| **Low** | Copy/layout, local UI state, offline parsing, narrow internal refactor | Focused tests if useful; render only affected browser routes |
| **Medium** | Reversible Canvas content operations, settings behavior, shared browser utilities | Focused tests plus affected subsystem tests; render affected routes |
| **High** | Grades/comments, credentials, FERPA boundaries, external AI transmission, scheduled writes | Focused happy/failure/idempotency checks, relevant broader suite, and user diff review |

Do not raise a task's risk merely because it lives in `api/`. Conversely, anything that can
leak a secret/student record or create an unintended Canvas write is high risk even if the
code change is small.

### Testing policy

- During implementation, run the smallest focused tests that exercise the changed behavior.
- At handoff completion, run the affected subsystem suite only when shared behavior changed.
- Run the full API suite at an integration/release boundary, after a genuinely cross-cutting
  API change, or when focused failures reveal unexpected coupling—not after every ordinary
  edit or micro-step.
- Run the engine suite when engine/shared rendering behavior changed or at a release boundary;
  API-only work does not automatically require it.
- Do not rerun a successful executor test matrix merely because work changed hands. Re-run
  only when evidence is missing, the environment differs materially, or the relevant diff
  changed afterward.
- Test counts are not a product metric. Prefer a happy path, meaningful validation boundaries,
  dangerous failure modes, and regressions for bugs that have occurred. Avoid duplicate
  assertions at route/service/adapter/source-text layers unless each catches a distinct risk.
- Prune redundant or brittle tests opportunistically when touching their area; do not create
  a standalone test-cleanup mega-project without a concrete payoff.

Tests must be worktree-independent: derive repository paths from the executing file or
current workspace and never commit a developer-specific absolute path.

Source-text tests do not establish WebUI correctness. Changes to shared browser scripts,
templates, navigation, initialization, or safety controls require loading every affected
route in the rendered local app, checking the required globals/state, and confirming zero
new browser-console errors. Backend pytest results cannot substitute for this check.

## Handoffs and docs

- Active execution briefs live directly in `docs/handoffs/`. Keep one active brief by
  default; use a small number only when the user intentionally has independent work in flight.
- Use `docs/handoffs/HANDOFF_TEMPLATE.md`. A handoff is an executable brief, not a transcript,
  exhaustive tutorial, test novel, or separate design ceremony.
- Completed historical handoffs may live in `docs/handoffs/archive/`, but archiving must be
  part of the implementation/closure batch, never a separate agent pass or acceptance slice.
  If a completed handoff has no durable reference value, it may be deleted; Git retains it.
- The implementation commit, diff, and traffic-light report are the execution record. Move
  lasting architecture or safety decisions into contracts/reference docs instead of relying
  on an old handoff.
- Historical Ferrari/Toyota documents are reference material only. They do not override this
  execution model or authorize unfinished work.
- `docs/contracts/` contains durable data contracts.
- `docs/guides/` contains durable usage/authoring guidance.
- `docs/reference/` contains stable architecture, module maps, and verified facts.
- For content operation-ledger adapter ownership and current split boundaries, start with
  `docs/reference/operation-ledger-module-map.md`.

Project-local tool routing lives in `TOOLS.md` and `tools/manifests/`. Do not invent
tool conventions in scattered docs.

## Tool Awareness Policy

Before using brute-force LLM inspection on large or repetitive inputs, check whether
an available tool can retrieve, parse, summarize, validate, or reduce the input first.

Check in this order:

1. Project-local `TOOLS.md`
2. Project-local `tools/manifests/`
3. Globally available skills/plugins/tools, if available

Prefer tools for:

- Fetching or scraping documentation
- Searching or indexing the repository
- Parsing logs, test output, diffs, HTML, API responses, or structured data
- Validating schemas, links, dates, IDs, and generated artifacts
- Reducing large raw inputs into compact structured summaries

Use LLM reasoning for architecture decisions, tradeoff analysis, planning, reviewing
summarized tool output, writing specs, and explaining behavior.

CanvasExpert routing rules:

- For Canvas LMS API questions, check `canvas-docs-scraper` first.
- For Canvas course, assignment, module, quiz, rubric, user, or enrollment data, check
  `canvas-api-inspector` first.
- For local architecture questions, check `repo-indexer` first.
- For test failures, use `test-failure-summarizer` before reading raw logs.
- For large diffs or reviews, use `change-risk-summarizer` before reading full files.

## Build / test / run

Windows + PowerShell. Current local test runs use Python 3.14 via the `py` launcher.
These are available commands, not a requirement to run every suite for every change;
select verification using the risk-based testing policy above.

```powershell
# Run the Web UI (from repo root: "Open Canvas Expert.bat", or:)
cd api; py qf_ui.py            # http://127.0.0.1:8765

# Tests (no pytest config; run by directory)
py -m pytest api/tests
py -m pytest engine/tests

# Focused PowerGrader regression tests
py -m pytest api/tests/test_powergrader_packet.py api/tests/test_powergrader_copilot_packet.py api/tests/test_powergrader_import_results.py api/tests/test_route_contract.py

# Install deps
py -m pip install -r api/requirements.txt
```

The local launcher installs Python dependencies only. Printable PDF generation
requires Microsoft Edge to be installed and allowed by device policy; it does not
download a Playwright-managed browser.

## Onboarding wizard - implemented

The first-run experience (workspace-folder picker -> Canvas URL -> token -> optional
calendar activation) is implemented. An unconfigured app redirects to `/welcome`
automatically; a "Re-run setup wizard" link is available on Settings. The historical
build spec is archived under `docs/handoffs/archive/onboarding-wizard.md`.

## Cleanup backlog

The district de-hardcoding / PII purge is **done** (hard-coded district URL, calendars,
and labels removed; the student-PII `default_docs/settings.json` deleted; rubric
metadata scrubbed; calendars made data-driven). Nothing outstanding here - keep
guardrails #2 and #3 from regressing.

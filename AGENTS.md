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
Workspace layout is under `<workspace>/FeedbackExpert/` with SAFE, PRIVATE, and
system/vault zones. New Quizzes item-level write-back remains blocked by Canvas PAT
limitations; scores can still be read where the normal Submissions API exposes them.
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

PowerGrader sessions are stored under `<workspace>/PowerGrader/`. They are PRIVATE:
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

## Agent workflow: two-track model

We use model switching to save tokens and cost, but the old Ferrari/Toyota handoff
ceremony was the dominant token sink. The new model is simpler: **two tracks**,
decided by whether the work involves an open architecture decision or is pure
pattern replication.

### Track 1: Direct implementation (smaller model)

Use when the work follows an established pattern in the codebase. The existing
adapter, route, or test file **is** the spec. No handoff document is written.

Criteria — all must be true:

- An existing implementation demonstrates the exact pattern (e.g., a registered
  operation-ledger adapter, a gradebook route, a test file using the same mocks).
- No new public contract, persistence model, or external-transmission path.
- No guardrail-adjacent decision (credentials, FERPA, live Canvas writes, scheduled
  auto-push, browser security).
- Two competent engineers would produce materially the same code by pattern-matching.

Direct-track work:

- Read the reference implementation and the test pattern.
- Implement in one commit (or one batch commit for grouped slices).
- Self-review against the reference pattern.
- Run focused tests + the full API test suite.
- Report: commit hash, files changed, test counts, and the reference pattern used.
- No handoff file. No archive ceremony. The commit message + diff is the record.

### Track 2: Design-then-implement (frontier model)

Use when the work involves an architecture decision, a guardrail-adjacent change,
or cross-cutting verification that two engineers might resolve differently.

Criteria — any one triggers Track 2:

- New infrastructure (SSE, recovery, threading, persistence format).
- Guardrail-adjacent: credentials, FERPA, live Canvas writes, scheduled auto-push.
- Cross-cutting: touches multiple subsystems, public contracts, or migration order.
- Verification strategy is not obvious from an existing pattern.

Track-2 work:

- Write a **brief design note** (3-10 lines, not a 5-page handoff) in the commit
  message or a `docs/reference/` note. State the decision and why.
- Implement directly. No separate planning agent pass.
- Self-review against the design note.
- Run focused tests + the full API test suite.
- For guardrail-adjacent changes, the user reviews the diff before merge.

### What replaced the old handoff system

- **No handoff documents.** The index entry + reference pattern is the spec for
  Track 1. The design note in the commit message is the spec for Track 2.
- **No archive ceremony.** Implemented slices are marked done in the index.
  The commit history is the archive.
- **No separate review pass.** The implementing agent self-reviews against the
  reference pattern (Track 1) or the design note (Track 2). The user reviews
  guardrail-adjacent changes.
- **Batching encouraged.** Group related Track-1 slices into one commit when
  context carries over (e.g., all gradebook adapters in one pass).

### Escalation (both tracks)

Stop and report instead of guessing when:

- A named insertion point, symbol, interface, or assumption does not exist.
- Existing behavior contradicts the plan.
- Multiple materially different implementations satisfy the requirement.
- Satisfying the requirement requires changing another subsystem or public contract.
- A guardrail or external side effect is involved but not completely specified.
- A regression is discovered outside the authorized scope.

### Tests and worktree independence

Tests must be worktree-independent: derive repository paths from the executing
file or current workspace and never commit a developer-specific absolute path.

Source-text tests do not establish WebUI correctness. Changes to shared browser
scripts, templates, navigation, initialization, or safety controls require loading
every affected route in the rendered local app, checking the required globals/state,
and confirming zero new browser-console errors. Backend pytest results cannot
substitute for this check.

## Handoffs and docs

- The old per-slice handoff system is retired. See "Agent workflow" above.
- `docs/handoffs/archive/` contains historical handoffs from the old Ferrari/Toyota
  system. They are reference material, not active specs.
- New design notes for Track-2 work go in the commit message or a brief
  `docs/reference/` note. No new files in `docs/handoffs/`.
- `docs/contracts/` contains durable data contracts.
- `docs/guides/` contains durable usage/authoring guidance.
- `docs/reference/` contains stable reference notes, including the redesign index
  that tracks slice status.

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

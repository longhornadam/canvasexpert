# Canvas Expert Web UI — Feature Reference

**Audience:** teachers using the local web UI; developers building or extending UI features.
**Entry point:** `cd api && py qf_ui.py` → opens `http://127.0.0.1:8765`.
**Implementation:** `api/webui/server.py` (FastAPI), `api/webui/templates/` (Jinja2),
`api/webui/static/` (`push.js` + `push/*.js`, `course_expert/*.js`,
`gradebook.js` + `gradebook/*.js`, `roster.js` + `roster/*.js`,
`feedback/*.js`, `powergrader_setup.js` + `powergrader/*.js`,
`powergrader_queue.js` + `powergrader/*.js`, `course_info.js`,
`settings.js`, `style.css`).

For backend overview, setup, files table, and confirmed Canvas API facts, see `api/README.md`.

---

## Page map

| Route | Page | JS |
|---|---|---|
| `/` | **Desk** — the cross-course Start / Continue / Attention / Prepared / Receipts surface | `dashboard.html` + `desk.js` |
| `/course-expert` | **Work tools** — all push tools + downloads, in tabs | `push.js` + `push/*.js`, `course_expert/*.js` |
| `/gradebook` | **Gradebook tools** — single-course grade operations | `gradebook.js` + `gradebook/*.js` |
| `/roster` | **Rosters** — student-level Canvas-group and local settings console | `roster.js`, `roster/*.js` |
| `/powergrader` | **PowerGrader** — grade one assignment with three routes: Grade myself, Prepare for my AI chat, or Draft-score with OpenRouter | `powergrader_setup.js` + `powergrader/setup_*.js`, `powergrader_queue.js` + `powergrader/queue_*.js` |
| `/ai-expert` | **AI helper files** — paste-ready LLM skill files | inline |
| `/course` | Course Info detail page | `course_info.js` |
| `/settings` | Settings | `settings.js` |
| `/routines` | **Routines** — local automation control surface | inline / route-driven |
| `/about` | What-is-Canvas-Expert explainer | — |
| `/forge/quizforge/` | Embedded QuizForge zero-auth compiler (separate Pyodide app) | its own |

### Work tools module routing

Work tools are split for low-token debugging.

- Page/template owner: `course_expert.html`
- Shared browser files: `push/core.js`, `push/file_sources.js`, `push/delivery.js`, `push/rubrics.js`, `push/course_picker.js`, `push.js`
- Feature files: `push/quiz.js`, `push/assignment.js`, `push/page.js`, `push/rubric.js`, `push/download.js`
- Work tools page files: `course_expert/tabs.js`, `course_expert/student_reports.js`, `course_expert/portfolio.js`, `course_expert/quick_assignment.js`
- Backend push routes: `routes/push.py`, `routes/push_validation.py`, `routes/push_streaming.py`
- Service helpers: `source_materials.py`

For the full ownership map and current hotspot snapshot, see `docs/reference/course-expert-module-map.md`.

### Settings module routing

Settings is stable but still browser-heavy.

- Page/template owner: `settings.html`
- Browser owner: `settings.js`
- Route owner: `routes/settings.py`
- Persistence facade: `config/__init__.py` with split modules under `config/`

For the full ownership map, see `docs/reference/settings-module-map.md`.

### PowerGrader module routing

PowerGrader is now intentionally split for low-token debugging.

- Route owner: `api/webui/routes/powergrader.py`
- Setup page modules: `powergrader_setup.js` (thin shim), `powergrader/setup_core.js`, `powergrader/setup_autoscore.js`
- Queue page modules: `powergrader_queue.js` (thin shim), `powergrader/queue_core.js`, `powergrader/queue_review.js`, `powergrader/queue_privacy.js`, `powergrader/queue_late_catchup.js`, `powergrader/queue_import.js`
- Backend workflow package: `api/powergrader/`

For the full ownership map and current line-count snapshot, see `docs/reference/powergrader-module-map.md`.

### Gradebook module routing

Gradebook is also intentionally split for low-token debugging.

- Route facade: `api/webui/routes/gradebook.py`
- Route feature files: `routes/gradebook_policy.py`, `routes/gradebook_sweep.py`, `routes/gradebook_extra_time.py`, `routes/gradebook_extensions.py`, `routes/gradebook_curves.py`, `routes/gradebook_snapshot.py`
- Shared browser bootstrap: `gradebook.js`
- Feature files: `gradebook/policy.js`, `gradebook/extra_time.js`, `gradebook/extensions.js`, `gradebook/sweep.js`, `gradebook/curves.js`, `gradebook/snapshot.js`

For the full ownership map and current size snapshot, see `docs/reference/gradebook-module-map.md`.

### Roster module routing

Roster has backend helper splits and browser feature files.

- Route owner: `api/webui/routes/roster.py`
- Browser bootstrap: `api/webui/static/roster.js`
- Browser feature files: `api/webui/static/roster/table.js`, `api/webui/static/roster/filters.js`, `api/webui/static/roster/inline_edit.js`, `api/webui/static/roster/group_state.js`, `api/webui/static/roster/bulk.js`, `api/webui/static/roster/groups.js`, `api/webui/static/roster/safety.js`
- Helper modules: `api/webui/routes/roster_canvas.py`, `api/webui/routes/roster_helpers.py`, `api/webui/routes/roster_groups.py`

For the full ownership map and current hotspot snapshot, see `docs/reference/roster-module-map.md`.

### Feedback tools module routing — Batch feedback & import results

Feedback Expert is the **batch scoring** workflow (not assignment-by-assignment grading — use PowerGrader for that). It supports New Quiz CSV workflows, manual tool imports, and OpenRouter draft scoring. Privacy-sensitive and split across route, pipeline, vault, scrub,
and safety helpers, plus browser feature scripts.

- Route owner: `api/webui/routes/feedback.py`
- Route feature files: `routes/feedback_manual.py`, `routes/feedback_library.py`, `routes/feedback_run.py`, `routes/feedback_push.py`
- Pipeline facade: `api/feedback_pipeline.py`
- Pipeline feature files: `api/feedback_artifacts.py`, `api/feedback_contract.py`, `api/feedback_results.py`
- Privacy helpers: `api/feedback_vault.py`, `api/feedback_scrub.py`, `api/feedback_safety.py`
- Browser feature files: `static/feedback/core.js`, `static/feedback/folders.js`, `static/feedback/personas.js`, `static/feedback/guided_run.js`, `static/feedback/manual.js`, `static/feedback/openrouter.js`, `static/feedback/push.js`
- Main templates: `feedback_expert.html`, `name_manager.html`

For the full ownership map and privacy-sensitive routing notes, see `docs/reference/feedbackexpert-module-map.md`.

---

## Settings page (`/settings`)

### Canvas account
Paste your Canvas base URL and API token once. The token is stored in the **OS credential
store** (Windows Credential Manager) via `keyring` — never written to disk in plaintext.
`api/.env` remains for CLI/scripting use only.  **Test connection** verifies the token.

### Bookmarked courses
Browse your live course list and bookmark the handful you use regularly. Mark each
**Active / Inactive** — only Active bookmarks appear in the course pickers. Nicknames
set here are the display names used throughout the app.

### Academic calendars
Load one or more calendars from your workspace **Calendars** folder, or paste a
custom CSV. The repo ships **no district data** — only a blank `calendar_template.csv`
and a fictional `Summer_Session_Sample.csv` (seeded into the Calendars folder on
first run). Whatever CSVs you drop into that folder appear as one-click "Load"
buttons in Settings. Two CSV formats accepted:

- **Canonical 7-col:** `school_year,row_type,code,name,start_date,end_date,report_issue_date,basis`
  — row_type values `Holiday`, `No School for Students`, `Holiday for Students/Teachers`
  → no-count dates; `Academic Period` → grading-period presets.
- **Simple 4-col:** `Category,Name,Start Date,End Date` — `Student Day Off` →
  no-count dates; `Academic Period` → presets.

Multiple calendars can be active simultaneously; none are active by default. The
sweep automatically filters to holidays within the swept date range. To build a
new calendar, download the template and ask an LLM to fill it in for your district
and year (there's a ready-made prompt in Settings).

### Download location
Root folder for submission downloads. Each course gets its own subfolder.

---

## Desk (`/`)

Desk is the full-width local landing surface for Start, Continue, Attention,
Prepared, Receipts, and active-course context. Its initial view is rendered from
local active-course configuration, the work registry, and real receipt
projections. Readiness continues to come from `/api/readiness`; the Desk's
asynchronous Scan uses the guarded `POST /api/work/scan` route and never scans
Canvas during an ordinary `GET /api/work`.

Start cards preserve the existing workflow routes and apply an explicitly chosen
course scope through the shared `CE_CONTEXT` contract. Continue and Attention
show local work-registry items; Ignore, Snooze, and Complete use the guarded
local mutation routes. Prepared is intentionally honest until prepared-operation
projections are available, and currently reports that there are no prepared
operations. Desk reads `/api/work` and `/api/receipts`, does not call
`/api/operations`, and does not alter the legacy `/api/activity` behavior.

### Routines

Routines are saved automations that run on this machine with no external scheduler
(locked-down district laptops; no cloud, ever). Three triggers, all in-app:

1. **"Run now"** buttons on the **Routines** page (works everywhere, always).
2. **Catch-up on launch** — a background thread starts with the server, waits 90 s,
   then runs whatever is enabled and due.
3. The same thread re-checks **every 30 minutes** while the app is open.

"Daily" therefore means "next time the app is open after 24 h have passed" — that's
the design, not a bug.

Four routines ship now:

| id | Label | Writes to Canvas? | Default |
|---|---|---|---|
| `sweep` | Auto-sweep late work | Yes (idempotent) | disabled, 24 h |
| `download` | Auto-download new student work | No (local files) | disabled, 24 h |
| `curve` | Auto-curve low assignment averages | flag: no · apply: yes | disabled, 168 h |
| `grading_debt` | Grading-debt report | No | **enabled**, 24 h |
| `student_reports` | Refresh monitored-student reports | No | disabled, 168 h |

Routine state is stored **machine-locally** (`api/webui/config.json`, `routines` key)
— NOT synced via the workspace. The synced workspace must not make one machine think
another machine's run satisfied it.

Routines are available at `/routines` and from the **Gradebooks** navigation menu:
a "how it works" strip, a card per routine with inline-editable params, and a "Build
your own" panel that shows the `custom_routines/` folder path and the files found in
it. Each routine's params are editable inline on its card. Every run lands in the
Activity Log under action `routine`.

**Auto-curve idempotency:** the curve routine skips any assignment that already has a
non-reverted curve event, so weekly runs don't re-lift grades as new scores come in.

**Flag vs. apply mode:** in flag mode (default), the routine lists assignments averaging
below the floor without touching Canvas. In apply mode, it performs a do-no-harm
target-average curve up to the floor and records a revertible event per assignment.

The **✎** marker on a routine row means it writes to Canvas; **due** on a row means
it's enabled and hasn't run within its `every_hours` window.

### Custom routines

Forkers can drop `.py` files in `api/custom_routines/` to add their own routines to the
Routines page (they show a **custom** badge). Each file registers one or more routines via the `@routine` decorator
— no imports needed; helpers (`canvas_get_all`, `active_courses`, `canvas_send`, etc.)
are injected automatically into the file's global scope.

- Files starting with `_` are **templates** (`_example_missing_work.py`) and are **not**
  loaded — copy to a name without the underscore to activate.
- A custom `rid` that collides with a built-in (`sweep`, `download`, `curve`,
  `grading_debt`) is silently skipped; built-ins are authoritative.
- A broken `.py` file is caught per-file (traceback logged to console) — the app never
  crashes from a bad custom routine.
- Custom routines get the same three triggers (Run now / catch-up on launch / every
  30 min), the same `config.set_routine_state` persistence, and the same Activity Log
  entries as built-ins. They pass through the identical `_ROUTINE_DEFS` /
  `_ROUTINE_RUNNERS` registries — no parallel path.

**Authoring:** paste `api/custom_routines/AUTHORING.md` into an LLM assistant and
describe what you want the routine to check or do. The doc covers the runner contract,
the `@routine` decorator, every injected helper with its signature, and a worked example.

**Future tier:** a declarative, shareable JSON form ("RoutineForge") that an LLM emits
and a sandboxed interpreter runs — planned but not built yet. This tier 1 is for people
running their own copy who are comfortable writing Python (or having their LLM write it).

---

## Work Tools (`/course-expert`)

One page, six tabs: **Quiz · Assignment · Page · Rubric · Download Work · Student Reports · *Quick***.

**Target courses** are picked in a compact **header dropdown** (Gradebook-style, but
multi-select): checkboxes add courses to the push set; clicking a course **name**
focuses it. The **focused** course feeds course-specific dropdowns (grading
categories, modules) and is the source for Download Work. The trigger shows the
focused course + "· N selected". Pushes go to **every checked course** in one shot.

**File sources:** every Forge-file picker offers **Library** (workspace folder
dropdown) / **Paste JSON** / **Upload…** — pasted or uploaded content is staged via
`/api/temp-upload` and selected automatically.

**Inline Forge helpers:** each push card has a collapsible *"Don't have one yet?
Forge one with your LLM →"* — a 3-step recipe (give your AI the content → copy the
authoring skill so it emits the right `<XFORGE_JSON>` → paste/upload the output).
The Quiz tab also links the standalone QuizForge app for QTI-ZIP manual import.

### Quiz tab
**Whole class:** pick a QuizForge file, then **Validate**, **Dry-run preview** (no
live calls), or **Push live quiz…** (confirmation → streamed log).
**Differentiated:** a quiz file per Canvas group, pushed as overrides via
`push_tiers.py`; fans out to every checked course, groups matched by name.
Delivery options: due / unlock / lock dates, grading category, add-to-module
(or create one), shuffle answers/questions, SIS sync, publish, hide results,
access code, multiple attempts (+ cooldown, score-to-keep, build-on-last), time
limit, one-at-a-time (+ backtracking), calculator. Results are **shown by
default** (rationales + correct answers after last attempt — core QF pedagogy);
see the `result_view_settings` note in `api/README.md`.

**Printable output:** the physical quiz endpoint compiles the same QuizForge file
into student and answer-key DOCX/PDF files. PDFs are rendered with the installed
Microsoft Edge through Playwright; DOCX files are rendered through bundled Pandoc.

### Assignment tab
Pick an `<ASSIGNMENTFORGE_JSON>` file, then **Validate** / **Push assignment…**.
Delivery: dates, grading category, module, SIS, publish, and an optional
per-assignment scheduled Auto-Score job. Authored tiers use the course's
teacher-selected Roster group set and create one group-visible Canvas assignment
and gradebook column per tier. Rubric association is not part of this operation path.

### Page tab
Pick a `<PAGEFORGE_JSON>` file, then **Validate** / **Push page…**. Module placement
+ publish. `{{file:…}}` / `{{page:…}}` placeholders resolve per course at push time.

### Rubric tab
Pick a `<RUBRICFORGE_JSON>` file, then **Validate** / **Push rubric…**. After the
teacher reviews the frozen operation, it creates the course rubric and, when the
file requests one, a student explainer page.

### Download Work tab
Downloads student work from the **focused** course. Load assignments, filter by
type and due-date range (All / Fall / Spring / 30d / 90d presets), select, download
to a local folder tree: `by_assignment/<Asgn>/...`, `by_student/<Student>/...`,
`_index.csv` per assignment, `_portfolio.csv` per student. Files are named
`<Asgn> - <F Last>.html`, `<Asgn> - <F Last> - URL.txt`, or
`<Asgn> - <F Last> - <original file>`.

### Quick tab (italicized — a different kind of tool)
**Fast gradebook column**: name, points, submission type (on-paper / none / text
entry), grading category, due date, publish — created in every checked course.
No Forge file involved; for authored instructions use the Assignment tab.

### Student Reports tab
On-demand per-student packet: pick a course → load the roster → pick a student →
check the sections to include → **Generate**. Runs across **every active course**
the student is in, not just the one used to load the roster.

**Packet structure** (in the synced workspace, `<student_reports_root>/<Student>/<Course>/`):
- `Assignments/` — work samples in their original formats (HTML for text entries,
  original files for uploads, URL redirects as `.txt`), named as
  `<Asgn> - <F Last>...`. New Quizzes item-level work is unavailable (PAT limitation,
  not OAuth — only scores appear in the Info DOCX).
- `Info/` — a dated `<Student> - <Course> - <YYYY-MM-DD>.docx` with per-assignment
  rows for grade, status, and submission date; neutral factual lines for late
  submissions, extended due dates, and curve adjustments; submission comments.

**Neutral language, no labels:** the whole point of the feature. No IEP/504/SpEd/
accommodation/modification/disability/intervention anywhere in the output. Late = "Submitted
2 days late". Extended due date = "Due date extended to Mar 4". Curve = "Score adjusted
via curve on Mar 5: 62 → 70". Section headings: **Standing**, **Late & extended due
dates**, **Adjustments**, **Comments**.

**Monitored toggle:** each student has a ☆ Monitor / ★ Monitored button on their row.
Monitored students form a private cohort. Because the names and notes are student PII,
they are synced to the OneDrive workspace (`settings.json`, in-tenant/FERPA-conscious), not
left in machine-local `config.json`. The **`student_reports`** routine (see Routines below) auto-refreshes
packets for just this cohort, skipping courses whose data hasn't changed (dedupe via
`_manifest.json`). The private note attached to a monitored student is never rendered
into any packet.

**New Quizzes limitation:** Canvas personal access tokens cannot retrieve New Quizzes
item-level responses. New Quiz scores still appear in the Submissions API and ARE
reported in the Info document; only the downloadable item-level work is unavailable.

---

## Gradebook Tools (`/gradebook`)

Standalone page (burnt-orange header). Manipulates the gradebook for a single
selected course via five tabs.

### Tab 1 — Policy & Sweep
**Course-wide late policy**: %/day deduction, grade floor, missing-work score.
Auto-loads when a course is selected. Writes via Canvas native late-policy API.

**Late-work sweep**: user picks a date range (grading-period chips default to
current/next period). The sweep counts *school days* late — weekends + district
holidays from the active academic calendar(s) + Rosters extra-time settings — then
sets Canvas's `seconds_late_override`. No grade math here; Canvas applies its own
policy. Re-running is safe; preview before writing.

Grading-period chips are labeled by `code` from the calendar (P1–P8 progress,
T1–T4 terms for PISD) with year suffix when multi-year (e.g. `T1 (25-26)`).

### Tab 2 — Extra-time
Compatibility view for standing extra-time settings. The primary management home is
**Rosters** (`/roster?focus=extra-time`); sweep and extensions reference those settings
automatically.

### Tab 3 — Extensions
Give selected students +N school days on one assignment via a Canvas assignment
override — their due date actually moves.

### Tab 4 — Curves
Four curve models: flat bump, target average, proportional, floor/cap.
Preview only; writes via Canvas grade passback.

### Tab 5 — Snapshot
Read-only grade distribution view.

---

## PowerGrader (`/powergrader`)

Keyboard-first grading queue for one Canvas assignment. A teacher starts one
session, reviews submissions student by student, approves or edits feedback, and
pushes approved grades/comments back to Canvas.

The setup page uses a wide responsive workspace with:

- **Side-by-side course/assignment selection** on desktop — Course takes about 35%
  of the available width and Assignment takes about 65%, with course-wide search
  and module filtering unchanged.
- **Mode-aware fast versus AI configuration** — Grade myself shows a compact
  rubric-only panel; AI modes show a two-column AI setup/source material layout.
- **Course-wide search** that scans all assignments regardless of the selected
  module view, and module filtering that defaults to the last three modules.

After a course is selected, the assignment picker groups work by Canvas course
module and immediately shows the final three modules in course order. The Modules
control can switch to any other module in the course. Assignment search always scans
the whole course, including assignments and quizzes outside the selected module view.

Modes:

- **Grade Myself** — fetches submitted work and opens the queue with no AI packet
  or API call.
- **Use My AI Chat** — writes local SAFE and PRIVATE artifacts, keeps the legacy
  Safe AI Packet ZIP, and also creates Copilot-friendly batch folders. Each batch
  folder has exactly three numbered upload files: assignment information, rubric
  and TA personality, and that batch's pseudonymized student work. Teachers start
  a fresh Copilot chat per batch, then paste each JSON response back into the
  matching batch panel in the same PowerGrader session.
- **Auto-Score With API** — sends only the SAFE pseudonymized packet to the
  configured OpenRouter model after price checks, then loads AI suggestions into
  the same review queue.

The Copilot flow is designed for education tenants where ZIP upload or large-file
context behavior may be limited. Batch imports validate `pseudonym` and `item_id`
against the selected batch before updating AI suggestions, so a response from one
batch cannot silently update another batch. AI suggestions remain drafts until the
teacher reviews, edits, approves, and pushes.

Safety wording is practical rather than absolute: SAFE files use pseudonyms and
remove obvious student identifiers before upload, but teachers should review the
files before sending them to any external chat tool.

---

## AI Helper Files (`/ai-expert`)

Equips the teacher's LLM (MagicSchool, Copilot, …) with paste-ready plain-text
skill files, served from the AI-TA library (`/api/ai-ta/file?name=…`):

- **Start here** — orients any LLM to Canvas Expert.
- **Authoring skills** — Author a Quiz / Assignment / Page / Rubric (the Forge
  contracts as skills). These same files power the Work tools inline
  "Forge one with your LLM" copy buttons.
- **Scoring skills** — one per rubric in the Rubrics folder; paste a skill, then
  paste essays one at a time.
- **MagicSchool Toolkit** — setup recipes for building dedicated MagicSchool tools.

**Rebuild library** regenerates the files from the contracts + rubric folder.

---

## Course Info (`/course`)

Detail page for any bookmarked course: roster + emails, group sets with member names,
modules, assignments, Canvas quick-links, download folder path.

---

## Under the hood

Quiz pushes delegate to the existing CLI scripts as subprocesses with credentials
injected via environment variables (`QF_PUSH_SETTINGS` carries assignment settings as
JSON) and stream progress over SSE. Downloads run in-process via `downloader.py`.
Assignment / page / rubric / quick-assignment creation plus gradebook and
course-info reads are direct Canvas REST calls through split Web UI routes
(`/api/gradebook`, `/api/course-detail`). The push logic itself
(`qf_pusher.py` / `push_tiers.py`) is never modified by the UI.

Push routes are split by role: `routes/push.py` keeps the shared router, Canvas
module/group lookup, and generic content push; `routes/push_validation.py` owns
file validation and physical render endpoints; `routes/push_streaming.py` owns
QuizForge preview and streaming push endpoints.

Printable physical outputs use sync render routes. Keep those routes synchronous
because Playwright's sync API cannot run inside an active asyncio event loop. The
PDF renderer launches the installed Microsoft Edge and does not require
a Playwright-managed browser download.

The `.env` file is still the path for direct CLI / scripting use; the UI does not
read or write it.

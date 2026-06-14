# Canvas Expert Web UI — Feature Reference

**Audience:** teachers using the local web UI; developers building or extending UI features.
**Entry point:** `cd api && py qf_ui.py` → opens `http://127.0.0.1:8765`.
**Implementation:** `api/webui/server.py` (FastAPI), `api/webui/templates/` (Jinja2),
`api/webui/static/` (`push.js`, `gradebook.js`, `course_info.js`, `settings.js`, `style.css`).

For backend overview, setup, files table, and confirmed Canvas API facts, see `api/README.md`.

---

## Page map

| Route | Page | JS |
|---|---|---|
| `/` | Dashboard (welcome, status strip, Expert + Forge launch cards) | — |
| `/course-expert` | **Course Expert** — all push tools + downloads, in tabs | `push.js` |
| `/gradebook` | **Gradebook Expert** — single-course grade operations | `gradebook.js` |
| `/ai-expert` | **AI Expert** — paste-ready LLM skill files | inline |
| `/course` | Course Info detail page | `course_info.js` |
| `/settings` | Settings | `settings.js` |
| `/about` | What-is-Canvas-Expert explainer | — |
| `/forge/quizforge/` | Embedded QuizForge zero-auth compiler (separate Pyodide app) | its own |

`/assessment` is a legacy route that redirects to `/course-expert`.

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

## Dashboard (`/`)

Landing page: a status strip (Canvas base, token state, workspace) plus launch-card
grids — one row of **Experts** (Course / Gradebook / AI, deep links into each tab)
and one row of **Forges** (QuizForge opens the zero-auth app; the others deep-link
to their Course Expert tab + AI Expert authoring skill).

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

Routines have their own top-level **Routines** tab (`/routines`): a "how it works"
strip, a card per routine with inline-editable params, and a "Build your own" panel that
shows the `custom_routines/` folder path and the files found in it. Each routine's params
are editable inline on its card. Every run lands in the Activity Log under action
`routine`.

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

## Course Expert (`/course-expert`)

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

### Assignment tab
Pick an `<ASSIGNMENTFORGE_JSON>` file, optionally attach a **RubricForge file**
(grade-with-rubric or feedback-only; can link the student explainer page and copy
a scoring prompt), then **Validate** / **Push assignment…**. Delivery: dates,
grading category, module, SIS, publish. **Tier scaffolding:** one file with tiers
→ multiple assignments, each visible only to its Canvas group via an override.

### Page tab
Pick a `<PAGEFORGE_JSON>` file, then **Validate** / **Push page…**. Module placement
+ publish. `{{file:…}}` / `{{page:…}}` placeholders resolve per course at push time.

### Rubric tab
Pick a `<RUBRICFORGE_JSON>` file, then **Validate** / **Push rubric…**. Creates (or
reuses by title) the course rubric and creates/updates the student explainer page.

### Download Work tab
Downloads student work from the **focused** course. Load assignments, filter by
type and due-date range (All / Fall / Spring / 30d / 90d presets), select, download
to a local folder tree: `by_assignment/<Asgn>/<Student>.html`,
`by_student/<Student>/…`, `_index.csv` per assignment, `_portfolio.csv` per student.
Text → `.html`, uploads → original file, URL → `.txt`.

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
  original files for uploads, URL redirects as `.txt`). New Quizzes item-level work
  is unavailable (PAT limitation, not OAuth — only scores appear in the Info DOCX).
- `Info/` — a dated `<Student> - <Course> - <YYYY-MM-DD>.docx` with per-assignment
  rows for grade, status, and submission date; neutral factual lines for late
  submissions, extended due dates, and curve adjustments; submission comments.

**Neutral language, no labels:** the whole point of the feature. No IEP/504/SpEd/
accommodation/modification/disability/intervention anywhere in the output. Late = "Submitted
2 days late". Extended due date = "Due date extended to Mar 4". Curve = "Score adjusted
via curve on Mar 5: 62 → 70". Section headings: **Standing**, **Late & extended due
dates**, **Adjustments**, **Comments**.

**Monitored toggle:** each student has a ☆ Monitor / ★ Monitored button on their row.
Monitored students form a private cohort recorded machine-locally (never synced; in
`config.json`). The **`student_reports`** routine (see Routines below) auto-refreshes
packets for just this cohort, skipping courses whose data hasn't changed (dedupe via
`_manifest.json`). The private note attached to a monitored student is never rendered
into any packet.

**New Quizzes limitation:** Canvas personal access tokens cannot retrieve New Quizzes
item-level responses. New Quiz scores still appear in the Submissions API and ARE
reported in the Info document; only the downloadable item-level work is unavailable.

---

## Gradebook Expert (`/gradebook`)

Standalone page (burnt-orange header). Manipulates the gradebook for a single
selected course via five tabs.

### Tab 1 — Policy & Sweep
**Course-wide late policy**: %/day deduction, grade floor, missing-work score.
Auto-loads when a course is selected. Writes via Canvas native late-policy API.

**Late-work sweep**: user picks a date range (grading-period chips default to
current/next period). The sweep counts *school days* late — weekends + district
holidays from the active academic calendar(s) + extra-time roster — then sets
Canvas's `seconds_late_override`. No grade math here; Canvas applies its own policy.
Re-running is safe; preview before writing.

Grading-period chips are labeled by `code` from the calendar (P1–P8 progress,
T1–T4 terms for PISD) with year suffix when multi-year (e.g. `T1 (25-26)`).

### Tab 2 — Extra-time
Per-student accommodation roster stored locally (never sent to Canvas). Sweep and
extensions reference it automatically.

### Tab 3 — Extensions
Give selected students +N school days on one assignment via a Canvas assignment
override — their due date actually moves.

### Tab 4 — Curves
Four curve models: flat bump, target average, proportional, floor/cap.
Preview only; writes via Canvas grade passback.

### Tab 5 — Snapshot
Read-only grade distribution view.

---

## AI Expert (`/ai-expert`)

Equips the teacher's LLM (MagicSchool, Copilot, …) with paste-ready plain-text
skill files, served from the AI-TA library (`/api/ai-ta/file?name=…`):

- **Start here** — orients any LLM to Canvas Expert.
- **Authoring skills** — Author a Quiz / Assignment / Page / Rubric (the Forge
  contracts as skills). These same files power the Course Expert's inline
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
Assignment / page / rubric / quick-assignment creation and all gradebook +
course-info reads are direct Canvas REST calls inside `webui/server.py`
(`/api/content/push`, `/api/gradebook`, `/api/course-detail`). The push logic itself
(`qf_pusher.py` / `push_tiers.py`) is never modified by the UI.

The `.env` file is still the path for direct CLI / scripting use; the UI does not
read or write it.

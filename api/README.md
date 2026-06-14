# Canvas Expert (the live/token app)

The **live half of the Canvas Expert platform.** Holds a Canvas API token and
pushes content to live courses via the REST and New Quizzes APIs:

- **Push Quizzes** (QuizForge JSON → live New Quizzes)
- **Push Assignments** (AssignmentForge JSON → live assignments, with tier overrides)
- **Push Pages** (PageForge JSON → live pages)
- **Push Rubrics** (RubricForge JSON → live rubrics + student explainer pages)
- **Gradebook Expert** — late policy sweep, student extensions, curves
- **Download** — submission bundles by assignment or by student

Local-only, never served. See `CLAUDE.md` Guardrails.

## Contracts consumed

| Contract | File | Role |
|---|---|---|
| **QuizForge** | `../LLM_Modules/QuizForge_Base.md` (v3.0-json) | Quiz authoring: 12 question types, rationales, tiers |
| **AssignmentForge** | `../LLM_Modules/AssignmentForge_Base.md` (v1.0-json) | Assignment authoring: submissions, scaffolding tiers |
| **PageForge** | `../LLM_Modules/PageForge_Base.md` (v1.0-json) | Page authoring: unit hubs, placeholders |
| **RubricForge** | `../LLM_Modules/RubricForge_Base.md` (v1.0-json) | Rubric authoring: analytics criteria, explainer page, scoring prompt |

Each contract is canonical in `../LLM_Modules/` — this backend consumes, never forks.
Token security: the repo is **private**; a `pre-commit` hook blocks the token pattern;
Netlify publishes only `web/`, so nothing here is served. Keep the token only in
`api/.env` (CLI) or OS credential store (Web UI, via `keyring`).

## Workflow

**Recommended: use the Web UI** (see "Web UI" below). CLI scripts are available for
automation/headless use.

### Web UI (Canvas Expert dashboard)

1. Launch: `py qf_ui.py` (opens http://127.0.0.1:8765)
2. Author a Forge file (QuizForge/AssignmentForge/PageForge/RubricForge JSON) — each
   push box has an inline "Forge one with your LLM" helper, or use the embedded
   QuizForge web editor.
3. **Validate** the file in the Web UI (summarizes what will push, spots errors)
4. **Select target courses** (multi-select dropdown in the Course Expert header)
5. **Configure delivery** (due dates, grading category, module, publish state)
6. **Push** — one button, multi-course in one shot. Log shows per-course notes.

### CLI (for automation)

- **Quiz**: `py qf_pusher.py "<quiz.txt>"` → live New Quiz (unpublished)
- **Tiers** (diff variants): `py push_tiers.py --manifest <manifest.json>`
- **Validate**: `py validate_qf.py <file.txt>`

## Web UI (recommended for day-to-day use)

`qf_ui.py` wraps the CLI scripts behind a local browser UI (branded **Canvas Expert**;
repo-root launcher `Open Canvas Expert.bat`):

```
py qf_ui.py            # opens http://127.0.0.1:8765
```

**Token storage:** the Web UI stores the token in the **OS credential store** via
`keyring` (Windows Credential Manager) — never on disk. `api/.env` is for CLI use
only. Non-secret config (base URL, bookmarks, download root, academic calendars)
lives in `api/webui/config.json` (gitignored).

## Workspace & multi-PC

When OneDrive is available, teacher-authored content lives in
`OneDrive\CanvasExpert\` with `AI-TA\`, `Rubrics\`, `Quizzes\`, `Assignments\`,
`Pages\`, `Exports\`, and synced `settings.json`. Default rubric files are seeded
into `Rubrics\` only when the filename is missing, so user edits win forever.

Machine-local state stays machine-local: `canvas_base`, `download_root`, and the
Canvas token in Credential Manager. Synced state is last-writer-wins through
OneDrive; conflict copies like `settings-<PC>.json` are ignored by the app. If
OneDrive is absent, the app falls back to the local folders exactly as before.

**Full feature reference** (Settings, Dashboard, Push Quiz/Assignment/Page/Module,
Gradebook Expert, Download Assignments, Course Info): **`api/webui/README.md`**.

## What each push does automatically

### Quizzes (QuizForge)
- Extracts JSON from the `<QUIZFORGE_JSON>` envelope.
- Inlines `STIMULUS` blocks as embedded HTML (code syntax-highlighted, Monokai).
- Distributes a **100-point** total across items.
- Posts each item with **retry on transient failures** (429/500/502/503/504,
  exponential backoff) so a flaky gateway can't silently drop a question.
- Sets quiz settings: **shuffle answers**, and a **results view that SHOWS the
  rationales** by default (see the result_view_settings note under "Confirmed
  facts" — this is core QF pedagogy). Optional: hide results, access code,
  multiple attempts, time limit, one-at-a-time, calculator type.
- Composes **per-choice colored feedback** — the targeted layer (an API detail):
  `✓ "choice" is correct because <rationale>` (green), `✗ "choice" is wrong
  because <rationale>` (red). MC/MA use per-choice `answer_feedback`; the other
  scored types use question-level `feedback.neutral`. We deliberately do **not**
  populate the question-level correct/incorrect boxes for MC/MA — the durable
  idea lives in the correct-answer rationale, kept at one layer for simplicity.
- Embeds a visible **TEKS** label per tagged item + prints a coverage report.
- **Tier overrides**: one file with tiers → multiple quizzes, each assigned to
  its group, with `only_visible_to_overrides` so a tier is truly group-only
  (no leftover "Everyone else" assignee).

### Assignments (AssignmentForge)
- Extracts JSON from the `<ASSIGNMENTFORGE_JSON>` envelope.
- Resolves course-resource placeholders (`{{file:NAME}}`, `{{page:Title}}` per course).
- Creates assignment(s) with configurable submission types, points, dates, grading category.
- **Tier overrides**: one file with tiers → multiple assignments, each visible only to
  its group via an assignment override. Each tier can have its own scaffolding text.

### Pages (PageForge)
- Extracts JSON from the `<PAGEFORGE_JSON>` envelope.
- Resolves course-resource placeholders (`{{file:…}}`, `{{page:…}}` per course).
- Creates page with rich HTML body, optional module placement.
- No tiers (pages are reference content, not submitted).

### Rubrics (RubricForge)
- Extracts JSON from the `<RUBRICFORGE_JSON>` envelope.
- Creates or reuses a course rubric by title, then creates/updates the student explainer page.
- When attached to an assignment for grading, assignment points default to the rubric total.
- AssignmentForge pushes can link the explainer page in the description and copy a scoring prompt for MagicSchool or Copilot.

## Files

| File | Role |
|---|---|
| `canvas.py` | API client (core REST + New Quizzes surfaces), reads `.env` |
| `transform.py` | QuizForge item → Canvas item (all types, feedback composition) |
| `codefmt.py` | VSCode-style code highlighting (Pygments → inline styles) |
| `teks.py` | TEKS coverage report + visible labels |
| `qf_pusher.py` | Driver: envelope → live quiz (points, settings, stimulus, TEKS) |
| `push_tiers.py` | Differentiation: variants → student groups via assignment overrides (`--manifest`) |
| `downloader.py` | Submission downloader → `by_assignment/` + `by_student/` tree, `_index.csv` / `_portfolio.csv` |
| `validate_qf.py` | QuizForge compliance checker |
| `qf_ui.py` | Launches the local web UI (see "Web UI" above) |
| `webui/` | Web UI: FastAPI app (`server.py`), single-account + bookmark config (`config.py` → `config.json`), templates/static, subprocess/SSE runner |
| `qf_materials/qf quiz examples/` | QuizForge fixtures (contract lives at `../LLM_Modules/QuizForge_Base.md`) |

## Setup

`.env` (gitignored) holds:
```
CANVAS_BASE=https://<your>.instructure.com
COURSE_ID=<id>
CANVAS_TOKEN=<personal access token>
ANTHROPIC_KEY=
```

## Confirmed Canvas API facts / limits (from live probes)

- A New Quiz's `assignment_id` **equals** its quiz `id`.
- The contract has **12 item types** including `stimulus`. **11 are API-creatable** —
  `stimulus` is not; embed its content as HTML instead (see `api/transform.py`).
- `numeric` needs `scoring_algorithm:"Numeric"` + a `scoring_data.value` array;
  `rich-fill-blank` needs `edit_distance ≥ 1`.
- Per-student / per-group **assignment overrides work** (drives differentiation).
  For true tier isolation, PATCH the assignment `only_visible_to_overrides: true`
  **after** the override exists — otherwise Canvas keeps an "Everyone else"
  assignee and the whole class can see the tier.
- **`result_view_settings` must explicitly enable feedback — an empty/unset one
  shows the student NOTHING** (confirmed live: rationales stay hidden even after
  manually toggling result viewing on). Canvas only surfaces per-item feedback +
  correct answers when the display flags are set, and those flags only apply
  inside a "restricted" (i.e. *customized*) result view. So QF's default spells
  them out: `result_view_restricted:true` + `display_item_feedback:true` +
  `display_item_correct_answer:true` + `display_item_response*:true`, qualifier
  `after_last_attempt`. Consequence: even the show-everything default makes
  Canvas's "Hide results" toggle read as ON/customized — there is **no** way to
  show feedback with that toggle fully off. Feedback wins; the toggle label is
  cosmetic.
- **Publishing** a New Quiz via API is unresolved (returns 400) — publish in the UI.
- **New Quizzes do NOT launch in "Student View" (Test Student).** A correctly
  published New Quiz with items will show the generic *"Oops, something went wrong"*
  page when opened as the Test Student. New Quizzes are an LTI tool
  (`quiz-lti-*.instructure.com`); the fake Test Student isn't provisioned in that
  service so the LTI launch 500s. This is an Instructure limitation, **not** a push
  bug — confirmed live (probe showed `published:true`, 10 items, valid launch URL).
  To test as a student: enroll a real second account, or use the quiz's **Build →
  Preview** inside the New Quizzes editor.
- **Per-question Outcome (TEKS) alignment is UI-only** — not in the API; we embed
  visible labels instead.
- **Pulling New Quizzes content (per-question responses / item & student analysis)
  appears to require OAuth, not a PAT** — but this is *instance-specific and worth
  re-confirming.** The official docs ([New Quizzes Reports](https://developerdocs.instructure.com/services/canvas/resources/new_quizzes_reports))
  only specify OAuth2 *scopes* per endpoint; they never explicitly say a PAT is rejected.
  Our evidence is a single live 403 on a Teacher PAT against `/api/quiz/v1/...` plus broad
  community reports. Scope enforcement is account-level, so another instance may differ.
  The supported path is the **New Quizzes Reports API**
  (`POST /api/quiz/v1/courses/:course_id/quizzes/:assignment_id/reports`,
  `report_type=student_analysis|item_analysis`), which needs an **admin-granted
  developer key** scoped to `url:POST|/api/quiz/v1/courses/:course_id/quizzes/:assignment_id/reports`.
  Canvas still enforces enrollment, so the key only ever reaches *your own* courses.
  **Re-test on a fresh PAT before assuming it's blocked** — run
  `py diagnose_newquizzes.py --course <id>` (see `api/diagnose_newquizzes.py`). It
  distinguishes **401** (key just lacks the scope — an admin can grant it) from **403**
  (the LTI service refuses a user PAT — you need a separate developer key + OAuth), and
  contrasts with the Classic Quizzes reports endpoint, which *does* work with a PAT.
  Meanwhile the **Student Analysis CSV downloads fine from the New Quizzes UI** (full
  responses included) — so manual export is always available even while API pull is blocked.
- **Common Cartridge import is the zero-auth power path** (Settings → Import Course
  Content). Vanilla CC 1.x carries only the portable common subset, but a **Canvas-flavored
  export package** (CC + Canvas extensions: `canvas_export.txt`, `course_settings/*.xml`)
  presets nearly everything the UI can — module structure/prerequisites, assignment-group
  weights, due/unlock/lock dates, submission types, rubrics+associations, publish state.
  The import-time **"Convert content to New Quizzes"** checkbox upgrades Classic-QTI quizzes
  to New Quizzes on import (creation only — unrelated to the response-pull block above).
  Only roster-relational things (per-student/section overrides) genuinely need the live API.
- Rubric `DELETE` returns a spurious 500 but still deletes.
- **One assignment override per student per assignment** — granting a second
  extension to the same student on the same assignment returns HTTP 400.
- **`/group_categories` endpoints can be 403 for teacher PATs** (district
  permission) while `/courses/:id/groups` still returns the same groups with
  their `group_category_id`. `/api/groups` falls back accordingly — confirmed
  live 2026-06 (set names are unavailable in the fallback).
- Late-policy `PATCH` returns **204 (no body)** — response handling must tolerate
  an empty body (`_canvas_send` does).
- **School-day math runs in school-local time** — a 23:59 CST due date is 05:59Z
  next day; weekday/holiday checks must use local time, not UTC (the sweep does).

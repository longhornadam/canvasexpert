# PowerGrader v1 — Handoff Brief

**Goal:** A new top-level grading tool on the dashboard. Two modes:
- **Fast** (AI off) — download submissions → keyboard-driven review queue → bulk push. Faster than Canvas SpeedGrader.
- **Assisted** (AI on) — same, but OpenRouter pre-fills score + feedback; teacher reviews/overrides per student.

Both modes show Roster context (tier, monitored flag, extra time) that Canvas SpeedGrader has no concept of.

This is a **new vertical** — does not replace FeedbackExpert. FeedbackExpert stays as the pseudonymized export-for-your-own-LLM flow. PowerGrader is for teachers who want to stay in the app.

---

## Files to create

| File | Purpose |
|---|---|
| `api/webui/routes/powergrader.py` | New `APIRouter(prefix="/api/powergrader")` + page routes |
| `api/webui/templates/powergrader_setup.html` | Setup screen: pick course/assignment/mode/rubric/persona |
| `api/webui/templates/powergrader_queue.html` | The grading queue UI (per-student pane) |

## Files to touch

| File | Change |
|---|---|
| `api/webui/routes/__init__.py` (or wherever routers are registered) | Import and mount `powergrader.router` |
| `api/webui/templates/dashboard.html` | Add PowerGrader card to `dash-job-grid` |
| `api/webui/config.py` | Add `powergrader_ai_enabled` bool getter/setter (machine-local, not synced) |

> **Check first:** Router registration is wherever `feedback.router`, `roster.router`, etc. are mounted. Search for `include_router` in `api/qf_ui.py` or the app factory.

---

## Workflow — Fast mode (AI off)

1. Teacher opens `/powergrader`, picks course + assignment, selects Fast mode.
2. `POST /api/powergrader/start` — fetches submissions from Canvas, builds session file, returns `session_id`.
3. Redirect to `/powergrader/session/<session_id>`.
4. Teacher reviews one student at a time: reads submission, enters score + feedback, hits Save & Next (or keyboard shortcut).
5. When done, bulk-push all approved via `POST /api/powergrader/session/<id>/push`.

## Workflow — Assisted mode (AI on)

Same as Fast except step 2 also:
- Pseudonymizes submissions using the existing vault (`feedback_vault.Vault`).
- Runs the safety gate (`feedback_safety.scan_payload`) — HARD block if not green.
- Calls `openrouter_client.score(bundle, rubric_text, persona, api_key, model)`.
- Re-identifies results via `feedback_pipeline.reidentify(results, vault)`.
- Stores per-student AI suggestion (`ai_score`, `ai_feedback`) in the session.

Teacher then sees AI suggestion pre-filled; they accept, edit, or override before saving.

---

## Session file

Location: `<workspace>/PowerGrader/<course_id>_<assignment_id>_<YYYYMMDD-HHMMSS>_session.json`

This file is **PRIVATE** (contains real names + submission content). It lives in the
workspace (OneDrive, in-tenant, FERPA-safe) and is **never committed to the repo**.
`workspace.feedback_folder` is the wrong root for this; use `workspace.workspace_root()`
directly under a `PowerGrader/` subfolder.

```json
{
  "session_id": "<uuid>",
  "course_id": "123",
  "assignment_id": "456",
  "assignment_name": "Essay 1",
  "created": "2026-06-26T14:00:00",
  "mode": "fast",
  "rubric_name": "Writing Rubric",
  "persona_id": "sage",
  "students": [
    {
      "user_id": "789",
      "real_name": "Jane Smith",
      "submission_text": "...",
      "submission_url": "...",
      "attachments": [],
      "code_files": [],
      "current_score": null,
      "status": "pending",
      "ai_score": null,
      "ai_feedback": null,
      "teacher_score": null,
      "teacher_feedback": null,
      "posted": false,
      "tier_id": "core",
      "tier_label": "Core",
      "tier_alias": "Red",
      "is_monitored": false,
      "monitored_note": "",
      "extra_time_days": 0
    }
  ],
  "push_log": []
}
```

`status` values: `"pending"` | `"approved"` | `"skipped"` | `"posted"`

---

## API endpoints

### `POST /api/powergrader/start`

Form params: `course_id`, `assignment_id`, `mode` (`fast`|`assisted`), `rubric_name` (optional), `persona_id` (optional, default `sage`)

Steps:
1. Call `_fetch_submissions(course_id, assignment_id)` — already implemented in `feedback.py`, copy or factor out to a shared location (see note below).
2. Call `_enrich_with_code_files(subs)` — same.
3. For each submission, pull roster context:
   - Tier: `config.get_roster_student_settings(course_id).get(user_id, {}).get("tier_id")`; resolve label via `config.roster_tier_by_id(course_id)`
   - Monitored: `config.get_monitored_students().get(user_id)`
   - Extra time: `config.get_extra_time(course_id)` — find by user_id
4. If `mode == "assisted"` and `config.has_openrouter_key()`:
   - Pseudonymize + safety gate + `orc.score()` + re-identify (exactly as in `/run/stream` in `feedback.py`)
   - Map AI results back to user_ids via the vault
5. Build session JSON, write to workspace, return `{"ok": true, "session_id": "...", "student_count": N}`

> **Factor out `_fetch_submissions` + `_enrich_with_code_files`:** Rather than copy-pasting from `feedback.py`, move them to `api/webui/canvas_client.py` or a new `api/webui/submissions.py` so both routes share them. Make sure to keep the existing `feedback.py` working — update its imports.

Returns error `{"ok": false, "error": "..."}` if:
- Canvas fetch fails
- No submissions with written content
- Assisted mode + safety gate blocks (include `hard` list)
- Workspace not configured

### `GET /api/powergrader/sessions`

Returns list of existing sessions for the current workspace:
```json
{"sessions": [{"session_id": "...", "assignment_name": "...", "created": "...", "mode": "...", "approved": 3, "total": 25, "posted": 2}]}
```

### `GET /api/powergrader/session/<session_id>`

Returns full session JSON.

### `POST /api/powergrader/session/<session_id>/grade`

Form params: `user_id`, `teacher_score` (float), `teacher_feedback` (str), `status` (`approved`|`skipped`)

Updates that student's entry in the session file. Does **not** push to Canvas.

Returns `{"ok": true}`.

### `POST /api/powergrader/session/<session_id>/push`

Form params: `user_ids` (JSON list, optional — omit to push all `approved` students)

For each student being pushed:
- `PUT /api/v1/courses/<course_id>/assignments/<assignment_id>/submissions/<user_id>`
  with `{"submission": {"posted_grade": teacher_score}, "comment": {"text_comment": teacher_feedback}}`
- Use the existing `_canvas_send` from `canvas_client.py`
- Mark student `status = "posted"` in session
- Append to `push_log`

Returns `{"ok": true, "pushed": N, "errors": [...]}`.

### Page routes (not API)

- `GET /powergrader` → render `powergrader_setup.html`
- `GET /powergrader/session/<session_id>` → render `powergrader_queue.html`

---

## Setup screen (`powergrader_setup.html`)

Extends `base.html`. Fields:

1. **Course** — dropdown of `config.active_courses()` (same pattern as other tools)
2. **Assignment** — populated via `GET /api/courses/<course_id>/assignments` after course selection; filter to assignments with `submission_types` that include `online_text_entry`, `online_upload`, or similar (exclude `none`, `not_graded`)
3. **AI assistance** — toggle: OFF = Fast mode, ON = Assisted mode
4. **Rubric** (shown when AI on, optional when AI off) — dropdown from existing rubric files
5. **Persona** (shown when AI on) — dropdown from `config.list_personas()`
6. **Resume session** — if sessions exist for this course/assignment, show a "Resume" link instead of starting fresh

Submit → `POST /api/powergrader/start` → redirect to queue.

---

## Queue screen (`powergrader_queue.html`)

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│ HEADER: Assignment name | Student 4 of 25 | ████░░ 3 approved │
├──────────────────────────────┬──────────────────────────────┤
│                              │ [Core / Red] [Monitored ★]   │
│  SUBMISSION CONTENT          │ [+2 extra days]              │
│                              ├──────────────────────────────┤
│  (scrollable, rendered if    │ RUBRIC                       │
│   HTML, plain text if not)   │  Ideas: [1][2][3][4][5]      │
│                              │  Voice: [1][2][3][4][5]      │
│                              │  Total: 8 / 10               │
│                              ├──────────────────────────────┤
│                              │ AI SUGGESTION (if Assisted)  │
│                              │  Score: 8 | [Accept AI]      │
│                              │  "Good thesis but..."        │
│                              ├──────────────────────────────┤
│                              │ YOUR SCORE                   │
│                              │  [  8  ] / 10                │
│                              │ FEEDBACK                     │
│                              │  [textarea]                  │
│                              ├──────────────────────────────┤
│                              │ [↓ Skip] [↑ Save & Next]     │
│                              │ [Push This Now]              │
└──────────────────────────────┴──────────────────────────────┘
│ ← previous  → next  ↓ skip  ↑ save+next  A use AI score  B bulk push │
```

### Context badges

- **Tier badge**: colored pill with `tier_alias` (e.g. "Red") + `tier_label` (e.g. "Core") — only shown if tier is set
- **Monitored flag**: star icon + note shown in a tooltip — only shown if `is_monitored` is true. Note text is the teacher's private note from config.
- **Extra time badge**: "⏱ +N days" — only shown if `extra_time_days > 0`

### Rubric scoring

If a rubric file is loaded, parse criteria and render as click-to-score rows (similar to how Canvas's own rubric panel works). Clicking a score cell fills the criterion score; total auto-computes. If no rubric is loaded, show a single score field (0–100 or points-possible range pulled from the Canvas assignment).

### AI suggestion panel

Only shown in Assisted mode. Shows `ai_score` and `ai_feedback`. "Accept AI" button copies both into the teacher fields. Teacher can then edit before saving.

---

## Keyboard shortcuts

| Key | Action |
|---|---|
| `←` | Previous student |
| `→` | Next student |
| `↓` | Skip current student |
| `↑` | Save current grade and advance to next |
| `A` | Use AI score (Assisted mode only) |
| `B` | Bulk push all approved |

Implement with a `keydown` listener on `document`. Guard against firing when focus is inside a `<textarea>` or `<input>`. Legacy `J`/`K`/`S`/`X` shortcuts may remain as secondary shortcuts, but the visible model is the arrow-key workflow.

---

## Dashboard card

Add to `dashboard.html` in the `dash-job-grid` section, alongside the other primary jobs:

```html
<a class="dash-job dash-job--primary" href="/powergrader">
  <span class="dash-job-verb">Grade</span>
  <strong>PowerGrader</strong>
  <span>Fast keyboard-driven grading with optional AI scoring.</span>
</a>
```

Also add to the "Feedback" lane in the `dash-lane-grid`:

```html
<a href="/powergrader">PowerGrader</a>
```

---

## What NOT to touch

- `LLM_Modules/*_Base.md` — authoring contracts, read-only
- `feedback_vault.py`, `feedback_pipeline.py`, `feedback_safety.py`, `openrouter_client.py` — use as-is, no changes
- The existing FeedbackExpert flow (`/feedback-expert`, `routes/feedback.py`) — PowerGrader is additive, not a replacement
- `CANVAS_BASE_DEFAULT` or any district config

---

## Guardrails

1. **No student data in the repo.** Session files go to `workspace_root()/PowerGrader/` (OneDrive / gitignored). Never write to `api/out/`, never log real names or submission content.
2. **Safety gate is mandatory for Assisted mode.** If `safety.scan_payload()` returns `green: False`, refuse the AI call and surface the hard violations to the teacher. Same rule as FeedbackExpert.
3. **Token stays in keyring.** The Canvas API token is accessed only via `config.get_token()`. Never pass it through form fields, log it, or put it in the session file.
4. **Local only.** No new routes that bind or forward outside 127.0.0.1.

---

## Acceptance criteria

- [ ] Dashboard card appears and links to `/powergrader`
- [ ] Setup screen: course dropdown populates, selecting a course loads assignment dropdown
- [ ] Fast mode: start session → queue opens → can navigate students → save scores → bulk push succeeds
- [ ] Assisted mode: AI toggle on → prepare + score runs → AI suggestion appears per student → Accept AI works → teacher edits → push succeeds
- [ ] Tier badge, monitored flag, extra time badge appear correctly for students that have those settings
- [ ] Arrow-key shortcuts work; A works in Assisted mode
- [ ] Closing the browser and returning to `/powergrader` shows "Resume" option
- [ ] Session file is written to workspace, not to repo or `api/out/`
- [ ] Assisted mode: safety gate blocks a batch that contains real names in submission text (hard violation)
- [ ] Push log in session records what was posted and when

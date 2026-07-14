# Workbench Canonical Flow Map

> Generated 2026-07-12 from source inventory. No runtime changes.
> This is the first-stop routing map for debugging sessions.
> For detailed file ownership, see the per-feature module maps in `docs/reference/`.

## Teacher outcome → canonical flow

| # | Outcome | Entry point | Template | Browser owner | Backend owner | Contract / map | Safety boundary |
|---|---|---|---|---|---|---|---|
| 1 | **Desk** – choose or continue work | `/` | `dashboard.html` (extends `workbench_base.html`) | `desk.js` | `routes/pages.py::dashboard`, `routes/work.py`, `routes/receipts.py` | `work-registry-contract.md`, `operation-ledger-release-status.md` | Exact generic jobs plus a transient local presentation sidecar; no Canvas calls from Desk itself |
| 2 | **Course content creation & delivery** | `/course-expert` | `course_expert.html` (extends `workbench_base.html`) | `push.js` + `push/*.js` + `course_expert/*.js` | `routes/push.py`, `routes/push_validation.py`, `routes/operations.py`, `operation_ledger/adapters/` | `course-expert-module-map.md`, `operation-ledger-module-map.md` | Typed operation-ledger prepare/review/apply; no generic push fallback; teacher review gate before Canvas writes |
| 3 | **Gradebook actions** | `/gradebook` | `gradebook.html` (extends `workbench_base.html`) | `gradebook.js` + `gradebook/*.js` | `routes/gradebook.py` (facade) + `routes/gradebook_*.py`, `gradebook_service.py` | `gradebook-module-map.md` | Single-course scope; late-policy/sweep/curve writes are reversible; extra-time reads from Roster config |
| 4 | **Roster & student-group actions** | `/roster` | `roster.html` (extends `workbench_base.html`) | `roster.js` + `roster/*.js` | `routes/roster.py` + `routes/roster_*.py`, `routes/names.py` | `roster-module-map.md` | V3: Canvas groups are source of truth; V2 tier/planned_group writes rejected; vault is PRIVATE |
| 5 | **PowerGrader** – setup, review, push | `/powergrader` → `/powergrader/session/{id}` | `powergrader_setup.html` / `powergrader_queue.html` (both extend `workbench_base.html`) | `powergrader_setup.js` + `powergrader/setup_*.js` / `powergrader_queue.js` + `powergrader/queue_*.js` | `routes/powergrader.py`, `api/powergrader/` | `powergrader-module-map.md` | SAFE pseudonymized packet; teacher review before any Canvas grade/comment push; scheduled auto-push is per-assignment opt-in only |
| 6 | **FeedbackExpert** – scoring & feedback push | `/feedback-expert` | `feedback_expert.html` (extends `base.html`) | `feedback/*.js` | `routes/feedback.py` + `routes/feedback_*.py`, `api/feedback_*.py` | `feedbackexpert-module-map.md`, `feedback-scoring-contract.md` | SAFE/PRIVATE zone separation; pseudonymization; teacher review before `PUT`; vault is PRIVATE |
| 7 | **Settings & first-run** | `/settings` (first-run: `/welcome`) | `settings.html` / `welcome.html` (both extend `base.html`) | `settings.js` + `settings/*.js` / `welcome.js` | `routes/settings.py`, `routes/calendar.py`, `routes/onboarding.py`, `config/` | `settings-module-map.md` | Token in OS credential store only; no district defaults in source; local-only bind |
| 8 | **Routines** | `/routines` | `routines.html` (extends `base.html`) | inline / route-driven | `routes/routines.py` + `routes/routines_builtin.py` + `routes/routines_custom.py` + `routes/routines_powergrader.py` | `operation-ledger-release-status.md` (routines integration) | Local automations only; no cloud scheduler; writes gated by routine definitions |

## Deliberately retained alternate paths

| Alternate path | Canonical replacement | Reason retained |
|---|---|---|
| Gradebook extra-time tab (`/gradebook?tab=extra-time`) | Roster extra-time lens (`/roster?focus=extra-time`) | Convenience view within gradebook context; reads same config; no independent write path |
| `/name-manager` → 302 redirect to `/roster` | `/roster` safety lens | Clean redirect; no duplicate surface |
| `/course` (Course Info detail page) | N/A – distinct outcome | Read-only course inspection; not a duplicate of any other surface |
| `/ai-expert` (AI helper files) | N/A – distinct outcome | Paste-ready LLM skill files; not a duplicate |
| `/about` | N/A – distinct outcome | Explainer page |
| `/forge/quizforge/` | N/A – distinct outcome | Embedded Pyodide zero-auth compiler; separate app |
| `push/core.js::streamSSE` helper | N/A – still used by download streaming | Used by `push/download.js` for `/api/submissions/download/stream`; not dead code |
| `push/core.js` legacy globals (`localToISO`, `targetCourses`, `initFileSource`, `copySkill`) | `window.CE_PUSH` namespace | Still consumed by `push/*.js` feature scripts and `course_expert/*.js`; guarded by `course-expert-module-map.md` |
| `push_validation.py` `/api/push/preview` (dry-run) | N/A – distinct validation step | QuizForge dry-run preview; not a write path; still called by `push/quiz.js` |
| `gradebook_service.py` legacy curve events migration | Current curve events path | Data migration for existing teacher curve history; not a surface |
| `app_context.js` legacy course-picker localStorage migration | Current course picker state | One-time localStorage migration; not a surface |

## Completed retirements

### July 2026: Tier-scheme HTTP endpoints removed

| Removed | Replacement | Changes |
|---|---|---|
| `GET /api/roster/tier-scheme` | Roster V3 Canvas group scheme | Routes removed from `roster.py`; 5 endpoint tests removed from `test_roster_routes.py`; 2 entries removed from `test_route_contract.py::EXPECTED` |
| `POST /api/roster/tier-scheme` | Roster V3 Canvas group scheme | Routes removed from `roster.py`; 5 endpoint tests removed from `test_roster_routes.py`; 2 entries removed from `test_route_contract.py::EXPECTED` |

**Live config retained:** `config.get_roster_tier_scheme()`, `config.roster_tier_by_id()`, and the `roster_tier_schemes` synced key remain for PowerGrader's tier-map resolution. Only the unused HTTP endpoint wrappers were removed. The archived audit brief is at `docs/handoffs/archive/workbench-canonical-flow-audit.md`.

### July 2026: QuizForge streaming HTTP wrappers removed

| Removed | Replacement | Changes |
|---|---|---|
| `GET /api/push/stream` | Typed operation-ledger prepare/apply | Routes and handlers deleted; `push_streaming.py` deleted; `register_streaming_routes` import removed from `push.py` |
| `GET /api/push-multi-whole/stream` | Typed operation-ledger prepare/apply | Same |
| `GET /api/push-variants/stream` | Typed operation-ledger prepare/apply | Same |
| `GET /api/push-multi/stream` | Typed operation-ledger prepare/apply | Same |

**Retained:** `POST /api/push/preview` dry-run — moved to `push_validation.py`. Direct CLI (`qf_pusher.py`, `push_tiers.py`) remains a supported manual teacher path. `push/core.js::streamSSE` remains used by Download Work streaming.

**Changes:** 4 route entries removed from `test_route_contract.py::EXPECTED`; 4 literal-string assertions removed from `test_webui_template_contracts.py`. All reference docs updated to identify typed operations as the sole browser live-write path. Archived at `docs/handoffs/archive/retire-quiz-streaming-http-surface.md`.

---

## Retirement candidates

*(None currently identified after the tier-scheme and QuizForge streaming retirements.)*

---

## Non-candidates (investigated and retained)

| Surface | Why not a candidate |
|---|---|
| `GET/POST /api/tier-tags` | Active Settings consumer: `settings.html` lines 155-177 render a tier-tags form; inline JS at line 392-402 calls `fetch("/api/tier-tags", { method: "POST", ... })` on save. `pages.py` line 254 supplies `tier_tags` template data via `config.get_tier_tags()`. This is a live Settings feature, not legacy overlap. |
| Gradebook extra-time tab | Active convenience view within gradebook; has live JS callers (`gradebook/extra_time.js`); reads same config as Roster |
| PowerGrader legacy JSON import box | Still actively used by `queue_import.js` for non-Copilot import path |
| `push/core.js::streamSSE` | Still used by `push/download.js` for download streaming |
| `push/core.js` legacy globals | Still consumed by `push/quiz.js`, `push/assignment.js`, `push/page.js`, `push/rubric.js`, `course_expert/quick_assignment.js` |
| `/api/push/preview` (dry-run POST) | Still called by `push/quiz.js` for QuizForge dry-run preview |
| `/name-manager` → 302 redirect | Already a clean redirect; no duplicate surface to retire |
| `gradebook_service.py` curve migration | Data migration, not a surface; no teacher-visible behavior |
| `app_context.js` localStorage migration | One-time data migration, not a surface |
| FeedbackExpert SAFE/PRIVATE boundaries | Required safety boundary; not migration overlap |
| Operation-ledger recovery seams | Required safety boundary; not migration overlap |

## Template inheritance summary

| Template | Extends | Used by |
|---|---|---|
| `base.html` | – | Settings, Welcome, FeedbackExpert, Routines, AI Expert, About, Course Info |
| `workbench_base.html` | `base.html` | Desk, Course Expert, Gradebook, Roster, PowerGrader (setup + queue) |

`workbench_base.html` adds `_workbench_header.html` (Desk/Create/Grade/Students/Automations nav) and `readiness.js`. `base.html` has the original dropdown nav. Both share `style.css`, `workbench.css`, `write_review.js`, and `app_context.js`.

Desk's `presentations` mapping is computed by `routes/work.py` for visible jobs only and
is supplied identically to the initial dashboard JSON and `GET /api/work` refreshes. It
contains course/title/aggregate-summary/action strings for display, remains separate from
the exact Work Registry job contract, and is never persisted.

## Test portfolio notes

Source-contract tests (`test_webui_template_contracts.py`) protect safety and workflow
wiring — typed operation gateways, no direct SSE/student IDs, cancellation prevents apply,
ordinal-only polling, shared CSRF, shared write review, Feedback/OpenRouter acknowledgement,
PowerGrader review-before-push. Visual composition, CSS, layout, DOM IDs, copy, and
script ordering are verified through rendered-route checks rather than frozen source
snapshots (per AGENTS.md testing policy).

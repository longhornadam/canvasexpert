# PowerGrader Route Card

Routing scope: open this card only when the active handoff touches PowerGrader, then read
the relevant section. It is not global executor context and does not replace a handoff's
exact file/symbol list.

## Entry points

- Route orchestration: `api/webui/routes/powergrader.py`
- Setup / queue templates: `api/webui/templates/powergrader_setup.html`,
  `api/webui/templates/powergrader_queue.html`
- Backend workflow package: `api/powergrader/`
- Setup browser shim/features: `api/webui/static/powergrader_setup.js`,
  `api/webui/static/powergrader/setup_*.js`
- Queue browser shim/features: `api/webui/static/powergrader_queue.js`,
  `api/webui/static/powergrader/queue_*.js`
- Local course navigation: `api/course_catalog.py`,
  `api/webui/routes/course_catalog.py`

Keep `powergrader.py` a route coordinator and the two top-level browser files thin
namespace shims.

## Ownership routes

| Concern | Owners |
|---|---|
| Start/session assembly | `start_workflow.py`, `session_builder.py`, `session_store.py` |
| Teacher save/push | `session_actions.py`, `queue_review.js` |
| AI workflow and SAFE artifacts | `ai_workflow.py`, `ai_workflow_support.py`, `queue_privacy.js` |
| Copilot packets/import | `copilot_packet.py`, `copilot_packet_support.py`, `import_results.py`, `queue_import.js` |
| Focused assignment evidence | `assignment_refresh.py`, `canvas_fetch.py`, `new_quiz_fetch.py`, `student_attachments.py` |
| Writing Timeline | `writing_timeline.py`, `student_attachments.py::attach_writing_timelines`, `queue_writing_timeline.js` |
| Late catch-up | `late_catchup.py`, `routes/powergrader_late.py`, `queue_late_catchup.js` |
| Scheduled autoscore | `autoscore_queue.py`, `autoscore_claims.py`, `scheduled_autoscore_support.py`, `routes/routines_powergrader.py` |
| Automatic-post policy | `autopush_policy.py`, `autopush_policy_result.py`, `push_context.py`, `interactive_autopush.py` |
| Setup/catalog flow | `setup_core.js`, `setup_sessions.js`, `setup_autoscore.js`, `course_catalog.py`, `routes/course_catalog.py` |
| Queue state/rendering | `queue_core.js`, `queue_review.js`, `queue_import.js`, `queue_late_catchup.js`, `queue_privacy.js`, `queue_writing_timeline.js` |
| Source-material context | `api/webui/source_materials.py`, `api/webui/source_material_extractors.py` |

Browser load order is template-owned. Setup loads the shim before sessions, core, and
autoscore features. Queue loads the shim before core, review, privacy, late-catchup, and
import features. Preserve `window.CE_POWERGRADER_SETUP` and existing queue namespace seams.

## Privacy and write boundaries

- PowerGrader sessions/jobs under `<workspace>/_System/PowerGrader/` are PRIVATE. Names,
  submissions, grades, comments, and identity mappings never enter the repo, fixtures,
  generic receipts, catalogs, or logs.
- Course Catalog is a student-free navigation/search projection. It may select work but
  never supplies focused evidence or authorizes a Canvas write. See
  `docs/contracts/course-catalog-contract.md`.
- SAFE packets are pseudonymized, not guaranteed anonymous. Teachers review them before
  external upload. See `docs/contracts/feedback-scoring-contract.md`.
- AI scores/comments are drafts until teacher review and push except for two narrow,
  default-off, non-global opt-ins:
  - a specific scheduled job/assignment, after eligibility, fresh-state, policy,
    idempotency, and receipt checks;
  - one newly created assisted/packet interactive session, under the per-session lock from
    authoritative reload through final save.
- Interactive auto-post is unavailable to Score myself, Classic Quiz, and New Quiz.
  Packet late generation never writes; only a valid import against that late batch's SAFE
  bundle may trigger the scoped path. Uncertain results remain drafts.
- New Quiz sessions have a separate teacher-reviewed item-finalization lane for item scores
  and per-item feedback. In a live course with active/current instructor enrollment, it uses
  Canvas's first-party, short-lived signed grader transport rather than the ordinary
  assignment-total `PUT`; concluded, closed, past-enrollment, or otherwise restricted courses
  may return `403`. The lane preserves preflight freeze, result-version drift detection,
  idempotency, post-write verification, content-minimized receipts, and fail-closed
  SpeedGrader fallback. New Quiz scheduled, late-catch-up, and interactive automatic posting
  remain unavailable. See `docs/reference/new-quizzes-grading-transport.md`.

## Writing Timeline

Local OOXML revision metadata for an **exactly** DOCX-only online-upload assignment
(`writing_timeline.is_tracked_assignment`). Two shapes, never confused:

- **Private report** (`parse_docx` + `categorize_authors`) — keeps raw Office
  `creator` / `last_modified_by` / per-block `author` and every parsed block. Lives in
  the session under `<workspace>/_System/PowerGrader/` and in the teacher UI only.
- **SAFE projection** (`safe_projection`) — rebuilt from a value whitelist, never
  filtered from the private report, so a new private field cannot ride along. Counts,
  booleans, normalized timestamps, editing-time/revision integers, at most three
  `largest_insertions`, and only the three allowed author categories. No per-block
  array. See `docs/contracts/feedback-scoring-contract.md`.

Invariants worth protecting:

- **Every path that builds students must attach timelines.** `build_students` has three
  callers — `powergrader.py::pg_start`, `powergrader_late.py`, and
  `routines_powergrader.py`. If one attaches and another does not, the teacher sees a
  timeline for some students and nothing for others, which reads as "no revision trail"
  rather than "not examined". That ambiguity is the one thing this feature must not create.
- Attachment must run **after** attachment ingestion. Without a `local_path` every
  document reports as unavailable.
- **Tracking changes the file format, not the scoring path.** A tracked assignment is an
  ordinary DOCX upload as far as content scoring is concerned: `route_bytes` extracts its
  text and inline images, marks it `ai_eligible`, and it flows through the same
  eligibility, SAFE-derivative, and bundle-inlining steps as a `.txt` upload. The timeline
  is additive metadata on the attachment and never gates or alters scoring. Tracked
  assignments are therefore scheduled-autoscore eligible, and the routines path attaches
  timelines actively.
- **All timestamps are US Central (`America/Chicago`), end to end** — parsed report,
  SAFE projection, and UI. The browser renders with an explicit `CST`/`CDT` marker. A
  bare `w:date` with no offset is read as UTC (what Word writes) before converting.
- `tzdata` is a **functional** dependency, not decorative: Windows ships no IANA
  database, so without it `ZoneInfo("America/Chicago")` raises and
  `central_timezone()` returns `None`. `_normalize_timestamp` then converts with
  argument-less `astimezone()`, which asks the OS for the offset **at that instant**
  and so still tracks DST. Do not "simplify" that to a captured
  `datetime.now().astimezone().tzinfo` — that is a frozen offset and would put every
  timestamp in the opposite DST season an hour out.
  `test_missing_tz_database_still_tracks_dst_and_never_yields_utc` fails if you do.
- The teacher-only `writing_process_observations` string is guarded in code by
  `writing_timeline.sanitize_process_observation`, not by the prompt alone.
- The UI states "describes editing process, not authorship or intent" on every timeline
  render, including the unavailable and not-examined paths.
- **The assistant-facing copy of this rule has one home.** `api/default_docs/AI Authoring/
  Writing Timeline (tracked assignments).txt` states the DOCX-only classification, the
  handout and lock steps, and the honest limits; MCP `get_product_guide(topic=
  "writing_timeline")` and `/api/download-contract?name=WritingTimeline` both serve that
  file verbatim. Change what `is_tracked_assignment` accepts and that file is wrong, and a
  connected assistant will state the stale rule confidently. `test_mcp_server_tools.py`
  pins the two together.

## Symptom routing

| Symptom | Start with |
|---|---|
| Setup/course/module/assignment selection | `setup_core.js`, `routes/course_catalog.py`, `course_catalog.py` |
| Session start or assembly | `powergrader.py::pg_start`, `start_workflow.py`, `session_builder.py` |
| Queue rendering/navigation | `queue_core.js`, `queue_review.js` |
| Save or reviewed push | `queue_review.js`, `session_actions.py` |
| Packet/import mismatch | `queue_import.js`, `import_results.py`, `copilot_packet.py` |
| Evidence/attachments | `assignment_refresh.py`, `canvas_fetch.py`, `new_quiz_fetch.py`, `student_attachments.py` |
| Late submission flow | `queue_late_catchup.js`, `powergrader_late.py`, `late_catchup.py` |
| Auto-post eligibility/idempotency | `autopush_policy.py`, `push_context.py`, `interactive_autopush.py`, `autoscore_claims.py` |
| Scheduled routine | `routines_powergrader.py`, `scheduled_autoscore_support.py`, `autoscore_queue.py` |
| Privacy/SAFE artifacts | `queue_privacy.js`, `ai_workflow.py`, `ai_workflow_support.py` |
| Writing Timeline missing or wrong | `writing_timeline.py`, `student_attachments.py`, whichever route built the students |

## Test routing

Core focused regressions:

- `api/tests/test_powergrader_packet.py`
- `api/tests/test_powergrader_copilot_packet.py`
- `api/tests/test_powergrader_import_results.py`
- `api/tests/test_powergrader_late_catchup.py`
- `api/tests/test_writing_timeline.py`
- `api/tests/test_route_contract.py`

The handoff must add the focused policy/idempotency tests owned by any changed high-risk
path. Browser changes require rendered checks of `/powergrader` and/or the affected queue
route with zero new console errors. Use `tools/size_report.py` only when file size is the
question; this card does not carry line-count snapshots.

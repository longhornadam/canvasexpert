# Execution brief: PowerGrader session workbench and responsive grading instrument

Status: **ready for implementation**

Risk: **high** — this is frontend work, but its controls surround live Canvas
grade/comment writes. Existing backend safety semantics are frozen.

Executor: **Terra**

## Outcome

Make PowerGrader feel like one coherent grading workspace. A teacher opening
`/powergrader` can immediately see sessions that are ready to post, sessions to continue,
and completed sessions before starting another job. A resumed queue uses the shared
Workbench shell while preserving the fast, keyboard-first two-pane grading experience on
ordinary teacher laptops and a usable stacked layout at narrower widths.

This is the first frontend-led integration batch after the operation-ledger redesign. It
uses PowerGrader's existing reviewed manual-push backend; it does not reopen backend
infrastructure work.

## Locked decisions

1. **Existing manual push is the backend authority.**
   `api/powergrader/session_actions.py::review_push` and `push_grades` already freeze a
   review, capture Canvas baselines, reject drift/payload changes, enforce review expiry,
   record per-student outcomes, and provide idempotency. Keep the current
   `/push-review` -> `CE_WRITE_REVIEW.confirm` -> `/push` flow.
2. **Do not add `grade.powergrader`.** No new operation-ledger adapter, work-registry
   adapter, receipt format, persistence model, session migration, or global Desk
   integration belongs in this batch. The archived redesign 12a handoff is superseded by
   this brief.
3. **Frontend-only session triage uses the existing session-summary response.** Do not add
   backend status fields merely to drive presentation. Each session belongs to exactly one
   lane, in this priority order:
   - **Attention:** `approved > 0` — approved work is waiting for teacher-reviewed posting.
   - **Completed:** `total > 0 && posted >= total`.
   - **Continue:** everything else, including partially graded or currently empty sessions.
4. **Both pages use the shared Workbench shell.** Extend `workbench_base.html`, retain the
   shared Workbench header and readiness strip, and load PowerGrader assets through
   `head_extra` / `workbench_scripts`. Do not duplicate shared CSS or scripts.
5. **The queue remains an Instrument, not a dashboard.** Keep the submission viewer,
   grading pane, session-specific privacy/packet/late strips, progress, and keyboard
   shortcuts. Improve composition and responsiveness without adding workflow steps.
6. **No safety-semantic changes.** Save/approve stays local PRIVATE state. `B` and both
   push buttons still open frozen review and cannot directly write Canvas. AI suggestions
   remain drafts visually distinct from teacher-edited values. Scheduled auto-push remains
   its existing separate opt-in path.
7. **No private evidence.** PowerGrader sessions contain student data. Do not commit session
   JSON, names, IDs, submissions, grades, screenshots, console dumps, or private paths.

## Scope

- `api/webui/templates/powergrader_setup.html`
- `api/webui/templates/powergrader_queue.html`
- `api/webui/static/powergrader_setup.css`
- `api/webui/static/powergrader_queue.css`
- `api/webui/static/powergrader/setup_core.js`
- New `api/webui/static/powergrader/setup_sessions.js`
- `api/tests/test_webui_template_contracts.py` only for focused structural/load-order
  contracts that remain useful after the layout change
- `docs/reference/powergrader-module-map.md`

Do not edit backend routes, session storage/actions, operation-ledger code, scheduled
autoscore/auto-push code, packet/import logic, or canonical authoring/scoring contracts.

## Out of scope

- A new grade operation or migration of manual push into the operation ledger
- Global Desk Work/Continue/Attention registration
- Session schema changes, cleanup, deletion, or archival controls
- Changes to grading, push, privacy, packet, import, OpenRouter, late-catchup, or scheduled
  auto-push behavior
- New polling, SSE, recovery, receipt, or persistence infrastructure
- A full visual redesign of the submission renderer or rubric grader
- Live Canvas writes, external AI calls, or use of real private data as committed fixtures

## Reference pattern and routing

- Shared shell: `api/webui/templates/workbench_base.html`
- Workbench composition: `api/webui/templates/course_expert.html` and
  `api/webui/templates/gradebook.html` (composition only; do not copy their feature UI)
- Setup ownership: `docs/reference/powergrader-module-map.md`,
  `api/webui/static/powergrader/setup_core.js`
- Queue ownership and load order: `docs/reference/powergrader-module-map.md`
- Frozen review/apply safety seam: `api/powergrader/session_actions.py::review_push`,
  `push_grades`, and `api/tests/test_powergrader_manual_push.py`
- Shared review modal: `api/webui/static/powergrader/queue_review.js::reviewAndApply`
- Existing template checks: `api/tests/test_webui_template_contracts.py`

Read project-local `TOOLS.md` before broad inspection. Do not read unrelated archived
PowerGrader handoffs; this brief contains the current decisions.

## Implementation requirements

### 1. Compose the setup page as a session workbench

- Change `powergrader_setup.html` to extend `workbench_base.html` and declare compatible
  Workbench/page classes.
- Add a PowerGrader workbench shell with a compact rail or navigation area for:
  **Start new**, **Attention**, **Continue**, and **Completed**. Counts and anchors update
  from the loaded session summaries.
- Present Attention and Continue ahead of the new-session form so teachers see resumable
  work before accidentally starting a duplicate session. Completed sessions belong in a
  visually quieter collapsed section.
- Replace the wide session table with responsive session cards/rows. Each item shows only
  assignment name, mode, created time, posted progress, an attention message when
  `approved > 0`, and one Resume action. Do not render course IDs, assignment IDs, session
  filesystem paths, or student details.
- Preserve the existing course filter: selecting a course filters every session lane;
  clearing the course shows all local sessions.
- Show useful empty and fetch-error states instead of silently hiding the entire session
  area.
- Keep all existing start-form IDs, mode behavior, folder actions, AI acknowledgement,
  model/estimate controls, privacy language, and enabled/disabled rules.

### 2. Give session rendering its own small browser module

- Move session fetch/classification/rendering out of `setup_core.js` into new
  `powergrader/setup_sessions.js`.
- Load scripts exactly once in this order after Workbench readiness:
  `powergrader_setup.js`, `powergrader/setup_sessions.js`,
  `powergrader/setup_core.js`, `powergrader/setup_autoscore.js`.
- `setup_sessions.js` owns `window.CE_POWERGRADER_SETUP.loadSessions(courseId)` and its own
  safe escaping/render helpers. `setup_core.js` calls that namespace method for initial
  load, course clear, and successful course load; do not add timers or duplicate fetches.
- Keep the root shim thin. Do not create a generic session framework.

### 3. Compose the queue as a responsive grading Instrument

- Change `powergrader_queue.html` to extend `workbench_base.html` while preserving every
  current meta value, DOM ID, script, and feature strip.
- Move the queue stylesheet into `head_extra` and the existing scripts into
  `workbench_scripts`, exactly once and in their current dependency order.
- Replace the hard-coded `height: calc(100vh - 52px)` assumption. Use body/main flex so the
  shared header and readiness strip consume their natural height and the grading instrument
  fills the remaining viewport without clipping.
- At normal laptop widths, retain the two-pane submission/grading layout and keyboard
  legend. At `900px` and below, provide a straightforward stacked layout with normal
  vertical scrolling; do not introduce tabs, drawers, resizers, or new state.
- Allow the topbar, privacy/packet/late strips, actions, and keyboard legend to wrap without
  horizontal page overflow. Preserve deliberate internal scrolling in submission bodies,
  code blocks, and packet content.
- Keep push buttons, `B`, review modal invocation, save/approve behavior, and AI draft
  distinction unchanged. Do not add a direct-write shortcut.

### 4. Keep tests and documentation lean

- Update existing PowerGrader template-contract assertions that are genuinely invalidated
  by Workbench composition (for example, the old `page-wide pg-page` assertion).
- Add only narrow structural assertions for Workbench inheritance, the new session-module
  load order, unique script inclusion, and preserved critical IDs. Do not add CSS text
  snapshots or duplicate backend safety tests.
- Update `docs/reference/powergrader-module-map.md` with the new session-module ownership,
  template inheritance, load order, and current size snapshot for files actually touched.

## Verification

```powershell
node --check api/webui/static/powergrader/setup_sessions.js
node --check api/webui/static/powergrader/setup_core.js
py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_powergrader_manual_push.py
git diff --check
```

No full API or engine suite is required: this batch does not change backend behavior or
engine code. If focused failures reveal an unexpected shared-template regression, run only
the newly implicated subsystem tests and report why.

Rendered verification uses the lifespan-disabled local server:

```powershell
cd api
py -m uvicorn webui.server:app --host 127.0.0.1 --port 8765 --lifespan off
```

Check only these surfaces, with no live Canvas write or external AI call:

- `/powergrader` at approximately `1366x768` light and `760x900` dark: all four workbench
  anchors/counts, session lane priority, course filtering, start-form modes, no horizontal
  page overflow, and zero new console errors.
- One local PRIVATE queue at approximately `1366x768` light and `900x768` dark: shared
  Workbench header/readiness, two-pane then stacked layout, all required feature strips and
  globals, keyboard legend, no horizontal page overflow, and zero new console errors.

Use a temporary fictional local session outside the repository if no suitable local session
exists. Do not capture or attach screenshots/logs containing real session or student data.
Do not activate push, import, late-score, packet generation, or OpenRouter controls during
rendered verification. Backend tests are the oracle for frozen review/apply safety.

## Stop conditions

Stop with RED rather than guessing if:

- Either template cannot adopt the Workbench shell without changing shared
  `workbench_base.html`, `base.html`, readiness behavior, or another route.
- Session triage cannot be represented accurately from the existing summary fields.
- Responsive queue composition requires changing session schema or queue feature behavior.
- Any push button or keyboard path can bypass `push-review` and `CE_WRITE_REVIEW.confirm`.
- Existing privacy, packet, import, late-catchup, OpenRouter, or scheduled-auto-push behavior
  must change to complete the layout.
- A named file, namespace, critical DOM ID, or script-order assumption does not exist.
- Verification would require a real Canvas write, external AI call, or committed private data.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to
the senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **GREEN** — implementation, focused checks, and all four rendered
  viewport checks are complete.
- Commit hash: **this implementation commit (reported at handback)**
- Files changed: `powergrader_setup.html`, `powergrader_queue.html`,
  `powergrader_setup.css`, `powergrader_queue.css`, `powergrader/setup_core.js`, new
  `powergrader/setup_sessions.js`, narrow correction in `powergrader/queue_import.js`,
  `test_webui_template_contracts.py`, this handoff, and
  `docs/reference/powergrader-module-map.md`
- Verification commands and counts: Node syntax checks passed for `setup_sessions.js`,
  `setup_core.js`, and the corrected `queue_import.js`; focused pytest passed
  **69/69**; `/powergrader` returned HTTP **200** from the lifespan-disabled local
  server; `git diff --check` passed
- Rendered routes/viewports:
  - `/powergrader` at `1366x768` light: Workbench header/readiness, four-link rail,
    Attention/Continue/Completed lanes, start form, and two-column layout present;
    session scripts loaded once, no horizontal overflow, and zero console warnings/errors
  - `/powergrader` at `760x900` dark: single-column layout with static four-link rail,
    lanes and form present; scripts loaded once, no horizontal overflow, and zero
    console warnings/errors
  - fictional local PRIVATE queue at `1366x768` light: Workbench header/readiness,
    initialized two-pane queue, all three feature strips, push/keyboard controls, and
    required scripts present once; no load error, overflow, or console warnings/errors
  - same queue at `900x768` dark: initialized stacked panes with normal body scrolling,
    no horizontal overflow, and zero console warnings/errors
  No push, import, late, packet, or AI action was activated.
- Deviations from the brief: the primary browser check found one pre-existing stray
  `SESSION_ID` reference in `queue_import.js`; the senior authorized the narrow
  namespace-based correction outside the original file list. Import behavior and all
  frozen backend/safety boundaries remain unchanged.
- Remaining blocker or decision: **none**

# Execution brief: make Course Expert the only content-work surface

Status: **ready for implementation**

Risk: **medium**

Executor: **external VS Code agent**

## Outcome

Teachers use one coherent Course Expert surface for Quiz, Assignment, Page, Rubric,
Download Work, Student Reports, and Quick Assignment. Desk and navigation links open
the correct `/course-expert?tab=<name>` view; the obsolete standalone pages and the
unused generic content-push backend are removed rather than preserved as compatibility
products.

This is deletion-first consolidation. It removes a parallel UI/backend path before any
high-risk operation-ledger decomposition begins.

## Locked decisions

- `/course-expert` is the sole teacher-facing home for all seven workflows.
- Canonical tab names are `quiz`, `assignment`, `page`, `rubric`, `download`,
  `students`, and `quick`, matching the existing Course Expert DOM and
  `course_expert/tabs.js` deep-link contract.
- Do not preserve, redirect, or retain the old `/push/*`, `/download-work`,
  `/student-reports`, or `/assessment` GET routes. They may return 404 after removal.
- Desk cards and navigation may still offer direct workflow choices, but each choice
  must link into the corresponding Course Expert tab rather than a separate template.
- All five live content kinds (`qf`, `af`, `pf`, `rf`, `quick`) use typed operation-ledger
  prepare/review/apply. There is no generic `/api/content/push` compatibility fallback.
- Remove `api/webui/push_service.py`; do not relocate its obsolete dispatcher into a
  new module.
- Printable generation remains local through `/api/physical/quiz`. AssignmentForge's
  optional printable-PDF Canvas attachment remains owned by
  `api/operation_ledger/adapters/assignment.py` and must retain focused coverage.
- Preserve validation, preview, download streaming, operation review/apply, receipt,
  idempotency, and Canvas-write safety behavior.
- A GREEN report with the required evidence is trusted. The senior will skim the
  summary and narrow risk seams but will not duplicate successful verification.

## Scope

- Update canonical entry links in:
  - `api/webui/templates/dashboard.html`
  - `api/webui/templates/base.html`
- Remove standalone page handlers from `api/webui/routes/pages.py` and delete:
  - `api/webui/templates/push_quiz.html`
  - `api/webui/templates/push_assignment.html`
  - `api/webui/templates/push_page.html`
  - `api/webui/templates/push_rubric.html`
  - `api/webui/templates/push_quick.html`
  - `api/webui/templates/download_work.html`
  - `api/webui/templates/student_reports.html`
- Remove `POST /api/content/push` from `api/webui/routes/push.py` and delete
  `api/webui/push_service.py`.
- Make `api/webui/static/push/core.js::pushContent` typed-operation-only. Remove its
  legacy review/fan-out branch, `describeContentEffects`, and obsolete compatibility
  globals that have no remaining runtime caller.
- Update `api/webui/static/course_expert/quick_assignment.js` to call the
  `window.CE_PUSH` namespace instead of relying on the removed bare `pushContent`
  compatibility global.
- Delete `api/tests/test_push_service.py`. Replace only still-relevant printable path,
  upload, and failure coverage from `api/tests/test_printable_attach.py` with tests of
  the current `AssignmentAdapter` owner; obsolete standalone printable-assignment
  behavior is not migrated.
- Update `api/tests/test_route_contract.py` and the affected contracts in
  `api/tests/test_webui_template_contracts.py` for the intentionally smaller surface.
- Update current documentation:
  - `docs/reference/course-expert-module-map.md`
  - `api/webui/README.md`
  - current-tense compatibility statements in
    `docs/reference/operation-ledger-design.md`
- Delete `docs/reference/rubric-live-path.md`. It is a superseded 11c0 discovery with a
  false current call graph; Git and archived handoffs retain its history.

## Out of scope

- Do not change any operation-ledger adapter interface, payload, persistence record,
  review digest, idempotency behavior, or Canvas endpoint.
- Do not remove `/api/push/preview`, `/api/physical/quiz`, download/submission streams,
  or the compatibility-only QuizForge streaming routes in this slice. Their consumer
  audit is separate.
- Do not split `course_expert.html`, `style.css`, `workbench.css`, operation adapters,
  or the large WebUI test module here.
- Do not redesign navigation, Desk cards, Course Expert tabs, or teacher wording beyond
  what is required to point existing choices at the canonical tabs.
- Do not edit Forge authoring contracts, credential handling, FERPA-sensitive paths,
  private operation storage, or live Canvas data.
- Do not make live Canvas calls during verification.
- Do not edit historical documents under `docs/handoffs/archive/`.

## Reference pattern and routing

- Existing deep-link implementation:
  `api/webui/static/course_expert/tabs.js::bindDeepLink`
- Canonical page composition: `api/webui/templates/course_expert.html`
- Typed browser gateway:
  `api/webui/static/push/core.js::operationKinds`, `pushContent`
- Current operation boundary: `api/webui/routes/operations.py`
- Current printable attachment owner:
  `api/operation_ledger/adapters/assignment.py::_validate_printable_pdf`,
  `_upload_course_file`, `AssignmentAdapter.execute`
- Test patterns:
  `api/tests/test_operation_routes.py`,
  `api/tests/test_assignment_operation.py`,
  `api/tests/test_webui_template_contracts.py`
- Required durable contract: `docs/contracts/operation-ledger-contract.md`
- Required ownership reference: `docs/reference/course-expert-module-map.md`
- Read project-local `TOOLS.md` before using broad manual inspection.

Do not re-read archived handoffs as implementation authority. They describe the
compatibility period that this brief intentionally ends.

## Implementation requirements

1. **Canonicalize entry points.** Map Assignment, Quiz, Quick column, Page, Rubric,
   Reports, and Downloads links to the exact Course Expert query-tab names above.
   Preserve Desk course-context behavior (`data-desk-start`) and existing navigation
   semantics.

2. **Remove the standalone UI surface.** Delete the seven handlers and templates plus
   the obsolete `/assessment` alias. Keep `_push_common_scripts.html`, because Course
   Expert still includes it. Clean imports and route documentation in `pages.py`.

3. **Remove the generic content-push backend.** Delete the route, dispatcher, service,
   unused imports, and legacy browser fallback. An unsupported `pushContent` alias must
   fail locally and clearly; it must never fall back to an arbitrary server write.
   Keep `postForm`, `streamSSE`, and physical-generation helpers that retain real
   Course Expert consumers.

4. **Preserve current printable safety evidence.** Before deleting service tests,
   confirm that path-root validation, upload failure, and successful printable
   attachment are exercised through `AssignmentAdapter`. Add or adapt focused tests
   against that current owner where coverage is absent. Do not preserve the obsolete
   standalone `kind="printable"` behavior merely to keep its old tests passing.

5. **Update intentional surface contracts.** Remove deleted routes from the route
   snapshot. Replace tests that read deleted templates with Course Expert script-order,
   deep-link, namespace, and typed-operation assertions. The runtime cancellation test
   must continue proving that review cancellation never reaches apply.

6. **Remove stale current documentation.** Current references must identify Course
   Expert plus typed operations as the live path and must not claim that
   `/api/content/push`, `push_service.py`, or standalone pages remain supported.
   Historical archived handoffs stay untouched.

7. **Self-review for true deletion.** Use repository search to prove there are no
   non-historical runtime references to the removed routes, templates, service, or
   legacy fallback. Record the net diff line change in the execution result; there is
   no arbitrary LOC target, but replacement compatibility infrastructure is forbidden.

## Verification

Focused checks during implementation:

```powershell
node --check api/webui/static/push/core.js
node --check api/webui/static/course_expert/quick_assignment.js
node --check api/webui/static/course_expert/tabs.js
py -m pytest api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py api/tests/test_operation_routes.py api/tests/test_assignment_operation.py api/tests/test_printable_attach.py
```

This intentionally removes public HTTP routes and shared browser composition, so the
completion boundary is the full API suite:

```powershell
py -m pytest api/tests
git diff --check
```

Repository-removal audit (historical archived handoffs are allowed to mention old
paths):

```powershell
rg -n "/push/(quiz|assignment|page|rubric|quick)|/download-work|/student-reports|/api/content/push|push_service" api docs/reference
```

Rendered verification is mandatory without clicking any Canvas-write action:

- Load `/` and confirm all eleven Desk cards remain visible; the seven workflows in
  this brief point to the correct Course Expert query tabs.
- Load each of `/course-expert?tab=quiz`, `assignment`, `page`, `rubric`, `download`,
  `students`, and `quick`. Confirm the requested tab is active, its panel is visible,
  other panels are hidden/inert, shared controls initialize, and there are zero new
  browser-console errors.
- From the global navigation, open the content-work choices and confirm they land on
  the expected Course Expert tabs with correct active navigation state.
- Confirm the removed GET routes and `POST /api/content/push` are absent from the app's
  route table. Do not substitute live requests to Canvas for this local check.

## Stop conditions

Stop with RED rather than guessing if:

- Any non-test runtime caller still requires a removed standalone template or
  `/api/content/push`.
- `AssignmentAdapter` does not own the printable path/upload behavior described above,
  or preserving that behavior requires an adapter/schema expansion.
- A supported content kind cannot complete through typed operation prepare/review/apply.
- Removing the compatibility path requires changing an operation contract, Canvas
  write sequence, credential boundary, or private persistence format.
- Existing behavior contradicts the canonical tab names or Course Expert lacks one of
  the seven agreed workflows.
- An unrelated regression blocks completion.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them
to the senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **GREEN**
- Commit hash: **0009867** (pre-amend commit)
- Files changed so far: route removal in `pages.py` and `push.py`; canonical links in
  `base.html` and `dashboard.html`; typed-only changes in `push/core.js` and
  `course_expert/quick_assignment.js`; test migration in
  `api/tests/test_printable_attach.py`; route/template contract updates in
  `api/tests/test_webui_template_contracts.py` and `api/tests/test_desk_routes.py`.
- Files deleted so far: the seven standalone templates, `api/webui/push_service.py`,
  `api/tests/test_push_service.py`, and `docs/reference/rubric-live-path.md`
- Committed change: 341 insertions, 2,572 deletions across 25 files, including this
  handoff
- Verification reported by executor:
  `py -m pytest api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py api/tests/test_operation_routes.py api/tests/test_assignment_operation.py api/tests/test_printable_attach.py`
  -> **127 passed**
  `py -m pytest api/tests` -> **662 passed, 1 skipped**
  `node --check api/webui/static/push/core.js`
  `node --check api/webui/static/course_expert/quick_assignment.js`
  `node --check api/webui/static/course_expert/tabs.js`
  `git diff --check` -> **no issues reported**
- Rendered routes checked:
  - Desk: `http://127.0.0.1:8765/` showed 11 desk cards, nav active on Desk, and no console errors.
  - Global navigation: Desk active on `/`; Create active on each `/course-expert?tab=...` view.
  - Course Expert tabs: quiz, assignment, page, rubric, download, students, and quick each showed exactly one active tabpanel, six hidden/inert tabpanels, the expected active tab button, and zero console errors.
- Deletions/audit evidence:
  - Removed legacy standalone push templates and `api/webui/push_service.py`.
  - Removed `api/tests/test_push_service.py` and stale docs references in
    `api/webui/README.md`, `docs/reference/course-expert-module-map.md`, and
    `docs/reference/operation-ledger-design.md`.
  - Verified the current Desk empty-state copy through `api/tests/test_desk_routes.py`.
- Remaining corrections: none.

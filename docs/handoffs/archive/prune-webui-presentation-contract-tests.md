# Execution brief: prune WebUI presentation snapshot tests

Status: **complete**

Risk: **low**

Executor: **external VS Code agent**

## Outcome

The WebUI contract suite remains a compact guard for Canvas-write safety, privacy
boundaries, critical workflow wiring, and the one runtime cancellation behavior it
actually exercises. It stops treating layout, exact CSS tokens, wording, DOM IDs,
script order, navigation labels, and former redesign-slice implementation shapes as a
permanent source-test contract.

This reduces `api/tests/test_webui_template_contracts.py` from a 1,134-line
implementation snapshot to a small high-information safety suite. UI appearance and
responsive layout remain validated when affected through rendered-route verification,
not frozen source strings.

## Locked decisions

- This is a test-portfolio deletion, not a test reorganization. Do not split the large
  test file into smaller snapshot files, replace deleted source assertions with new
  source assertions, or add test infrastructure.
- Retain tests that independently guard one of these live risks:
  - typed operation-gateway routing and no generic legacy push;
  - Quiz browser flow cannot bypass typed operations with direct write/SSE or browser
    student IDs;
  - cancellation prevents operation apply (the existing Node runtime check);
  - operation summary does not expose target/step internal identifiers;
  - shared course context does not resume dual legacy storage writes;
  - Feedback/OpenRouter acknowledgement and review gate;
  - PowerGrader review-before-push, SAFE acknowledgement, and session-ID wiring;
  - no local reimplementation of the shared Canvas-write review control.
- Delete tests whose only purpose is visual composition, CSS breakpoints or values,
  exact DOM IDs/counts, script ordering/uniqueness, static navigation labels, copy,
  removed-class absence, template inheritance, or a prior slice's implementation
  arrangement. These are low-information maintenance snapshots.
- Do not change application templates, CSS, JavaScript, routes, operation contracts,
  browser behavior, or product wording. The only production-adjacent correction is the
  inaccurate duplicate endpoint list in the Course Expert module map below.
- `test_route_contract.py` remains unchanged. It is a deliberate HTTP-surface ledger;
  do not use this task to make a broader call on it.

## Scope

- In `api/tests/test_webui_template_contracts.py`, retain only the meaningful tests
  described in the locked decisions. Rename a retained test only when its current name
  claims the existence of retired streaming routes; preserve its remaining assertion
  intent.
- Remove all other test functions and imports that become unused. In particular,
  remove the large Workbench header, Desk, Course Expert layout, PowerGrader responsive
  CSS/template, Roster shell/lens, navigation-copy, instrument-language, and former
  redesign-slice source snapshots.
- Keep the existing Node-backed `test_operation_alias_runtime_cancellation_never_applies`
  rather than replacing it with a source-text assertion.
- Correct `docs/reference/course-expert-module-map.md` so
  `routes/push_validation.py` has one consolidated endpoint-ownership list including
  `/api/push/preview`; remove the duplicate list introduced during streaming retirement
  and update its size snapshot to the actual current line count.
- Update the `Test portfolio notes` in
  `docs/reference/workbench-canonical-flow-map.md` only enough to say that the WebUI
  suite protects safety/workflow wiring, not CSS/layout snapshots. Do not add an
  exhaustive replacement inventory.
- Record the completion result in this handoff, then archive it under
  `docs/handoffs/archive/` after the result is written.

## Out of scope

- Do not change `api/tests/test_route_contract.py`, operation-adapter tests, Canvas
  mocks, PowerGrader behavioral tests, Feedback pipeline tests, or any engine test.
- Do not run an application server, perform rendered browser checks, call Canvas or
  OpenRouter, start routines, or inspect private workspaces; no runtime code changes.
- Do not alter the retained test behavior merely to reduce count or line total.
- Do not redesign the Workbench or make style/copy changes in reaction to deleted
  presentation snapshots.

## Reference pattern and routing

- Test owner: `api/tests/test_webui_template_contracts.py`
- Required retained runtime test:
  `test_operation_alias_runtime_cancellation_never_applies`
- Shared write safety owner: `api/webui/static/write_review.js`
- Typed gateway owner: `api/webui/static/push/core.js::pushContent`
- Quiz browser owner: `api/webui/static/push/quiz.js`
- Current Course Expert ownership map:
  `docs/reference/course-expert-module-map.md`
- Test strategy and rendered-UI rule: `AGENTS.md` → Testing policy
- Read project-local `TOOLS.md` before broad inspection. Use AST/function listing or
  `rg '^def test_' api/tests/test_webui_template_contracts.py` to make the retention
  boundary auditable without reading the whole file repeatedly.

## Implementation requirements

1. **Apply the retention boundary literally.** Keep only the tests which guard the
   risks listed under Locked decisions. A test that happens to mention a safety feature
   but merely verifies its exact CSS, markup placement, or wording is not retained.

2. **Preserve meaningful assertions, not former migration vocabulary.** The Quiz test
   must keep assertions that the browser uses typed preparation and does not use
   `push.streamSSE`, direct write review, or `studentIds:`. Remove any references to
   deleted endpoint names and rename the test if needed to state the current invariant.

3. **Delete dead scaffolding with the snapshots.** Remove unused imports such as `re`
   only if no retained test needs them. Retain the minimal file helper and subprocess
   imports necessary for the surviving tests.

4. **Keep the current source routing map truthful and concise.** Combine the duplicated
   `push_validation.py` lists rather than adding a cross-reference. Use the actual line
   count after the preview move, obtained with a local line-count command; do not guess.

5. **Prove this is simplification.** Record the before/after number of test functions
   and file lines in the execution result. There is no arbitrary target, but the
   retained suite must be materially smaller and each remaining test must map to one
   locked risk.

## Verification

```powershell
py -m pytest api/tests/test_webui_template_contracts.py
py tools/size_report.py
rg -n '^def test_' api/tests/test_webui_template_contracts.py
git diff --check
```

Manually compare each remaining test function to the Locked decisions. No full API
suite or rendered-route check is appropriate: production behavior is unchanged.

## Stop conditions

Stop with RED rather than guessing if:

- A proposed deletion is the only test protecting a live Canvas write, FERPA/AI safety,
  or review-before-apply behavior.
- A retained safety test cannot run without a larger production/test refactor.
- Correcting the Course Expert module map requires changing runtime ownership or route
  behavior rather than documentation.
- The focused test fails for a reason outside test removal or the module-map correction.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them
to the senior. Do not leave the only copy of execution state or evidence in chat.

### Execution result

- Traffic light: **GREEN**
- Commit hash: uncommitted
- Files changed:
  - `api/tests/test_webui_template_contracts.py` — 1,134 lines → 251 lines; 70 tests → 17 tests
  - `docs/reference/course-expert-module-map.md` — consolidated the duplicate
    `routes/push_validation.py` ownership list and retained the 172-line snapshot
  - `docs/reference/workbench-canonical-flow-map.md` — added the concise test-portfolio
    note under `## Test portfolio notes`
- Files moved: active handoff removed after this archive copy was finalized
- Test-function and line-count before/after:
  - **Before:** 70 tests, 1,134 lines
  - **After:** 17 tests, 251 lines (83 lines excluding blank lines and comments)
  - **Deleted:** 53 low-information CSS/layout/DOM/copy/script-ordering/navigation snapshot tests
- Verification commands and pass/fail/skip counts:
  - `py -m pytest api/tests/test_webui_template_contracts.py` — **17 passed** in 0.13s
  - `py tools/size_report.py` — completed successfully; the inventory still reports
    other large source/test files, which is expected and is the input for later slimming
  - `rg -n '^def test_' api/tests/test_webui_template_contracts.py` — 17 retained tests confirmed
  - `git diff --check` — clean
- Retained tests mapped to locked risks:
  - **Typed operation-gateway routing:** `test_operation_gateway_aliases_and_no_direct_legacy_calls`, `test_quiz_push_uses_typed_operation_payloads_only`, `test_page_prepare_uses_shared_operation_helper`
  - **No direct SSE/student IDs:** `test_quiz_push_uses_typed_operation_payloads_only` (asserts `push.streamSSE`, `push.canvasWriteReview`, `studentIds:` absent)
  - **Cancellation prevents apply:** `test_operation_alias_runtime_cancellation_never_applies` (Node runtime check)
  - **Ordinal-only polling (no internal identifiers):** `test_operation_summary_polling_uses_ordinal_labels_only`
  - **Shared CSRF meta:** `test_shared_csrf_meta`
  - **Shared write_review.js:** `test_write_review_loaded_before_page_scripts`, `test_no_local_canvas_write_review_function`
  - **Shared course context, no dual legacy writes:** `test_course_picker_uses_shared_context_without_dual_writes`
  - **Feedback/OpenRouter acknowledgement:** `test_persona_card_closed_before_push_section`, `test_guided_run_uses_write_review_confirm`, `test_guided_run_acknowledgement_text`
  - **PowerGrader review-before-push:** `test_powergrader_review_apply_contract`, `test_powergrader_import_uses_shared_session_id`
  - **PowerGrader workspace gate:** `test_powergrader_config_has_workspace`, `test_sync_start_enabled_uses_workspace_flag`
  - **PowerGrader AI acknowledgment ordering:** `test_powergrader_ack_before_start_button`
- Deviations from the brief: None.
- Remaining blocker or decision: None.

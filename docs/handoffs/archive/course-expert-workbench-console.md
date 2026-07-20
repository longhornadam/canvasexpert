# Execution brief: Course Expert Workbench-console alignment

Status: **implemented; acceptance evidence recorded**

Risk: **medium**

Executor: **Luna**

## Outcome

Make `/course-expert` resemble the Workbench study at
`%USERPROFILE%\.codex\visualizations\2026\07\10\019f4d61-ebcc-78a0-b981-45d66ab59d39\canvasexpert-workbench.html`: a dense three-column creation console with a compact work rail, clear workspace orientation, and a real operation ledger.

The teacher-visible workflows remain the existing ones. This batch improves orientation and density around those workflows; it does not create a second authoring flow or alter a Canvas write path.

## Locked decisions

- Preserve exactly one copy of every existing Course Expert form, panel, control ID, `data-tab`, file source, target selector, deep link, and script in its current order.
- The active workspace remains the current `.ce-course-expert-center` and existing tab panels. Do not clone, move across documents, or re-create any form field.
- Keep `?tab=`, hashes, `?view=instrument`, history behavior, Instrument mode, course focus/target semantics, and all `window.CE_*` globals. Instrument remains a separate, unchanged view.
- The Work rail becomes an information-dense rail modeled on the study:
  - rail heading **Work**;
  - a two-column **Start** grid containing the existing seven tool activators (Quiz, Assignment, Page, Rubric, Quick column, Download Work, Student Reports);
  - **Continue** and **Attention** sections retaining the existing local work-registry links.
  Do not add the study’s mock-only “More” item or counts.
- Add a visible stage header above the existing workspace panel with a fixed kicker **Workspace** and a title that tracks the existing active tab. It uses only the current tab labels and no fabricated source, validation, preview, course, or target state.
- Rename the right rail to **Operation ledger** and add a non-stateful flow label `Work → Review → Canvas`. Keep the existing `#ce-operations-list` and all of `push/core.js` behavior unchanged, including the real review/apply and retry controls. Do not make status claims outside existing operation projection data; `Canvas unchanged.` remains the honest empty state.
- Treat the study as a composition reference only. Do not add its mock assignment preview, pipeline step status, course labels, operation examples, target counts, receipts, autosave, or disabled action controls.
- Scope all new styles to Course Expert Workbench selectors. Do not change Desk, PowerGrader, Gradebook, Roster, shared header, global form styles, standalone `/push/*` routes, or Instrument CSS/behavior.

## Scope

- `api/webui/templates/course_expert.html`: restructure only shell markup around the existing left rail, center workspace, and summary rail. Add stable wrappers/classes for the locked sections and the stage title. Preserve every existing panel/form once and preserve the current script order verbatim.
- `api/webui/static/course_expert/tabs.js`: add the smallest local synchronization so the stage title reflects the tab selected by the current `activateTab` path, including deep links and keyboard navigation. Do not modify view, URL, form, course-picker, or delivery-toggle behavior.
- `api/webui/static/workbench.css`: restyle the Course Expert Workbench to the study’s operational vocabulary: compact rail start grid, ledger-like Continue/Attention links, stage header, constrained drafting canvas, and readable operation-ledger rail. Add responsive behavior that stacks safely below desktop without horizontal overflow. Instrument-specific selectors must retain their current effect.
- `api/tests/test_webui_template_contracts.py`: only add/update a narrow durable test if needed to prove the stage-title synchronization or critical operation gateway integration is preserved. Do not add source snapshots or CSS-layout tests.

## Out of scope

- Any API, backend model, Canvas call, operation adapter, work-registry schema, response shape, persistence change, or new async request.
- Any change to `api/webui/static/push/core.js`, `_push_common_scripts.html`, individual push feature scripts, course picker semantics, review modal, retry behavior, or write authorization.
- New workflow phases, synthetic validation statuses, fake previews, fabricated target data, or new routes.
- Changes to the existing unrelated dirty worktree files or the completed Desk batch.

## Reference pattern and routing

- Visual reference: `%USERPROFILE%\.codex\visualizations\2026\07\10\019f4d61-ebcc-78a0-b981-45d66ab59d39\canvasexpert-workbench.html` — use only escaped `#ce-workbench-study-v2` fragment around source lines 751–846.
- Shell: `api/webui/templates/course_expert.html`.
- Tab activation/Instrument routing: `api/webui/static/course_expert/tabs.js::activateTab`.
- Work rail: `api/webui/static/course_expert/work_rail.js`.
- Real operation ledger behavior: `api/webui/static/push/core.js::renderOperationsList` (read only; do not edit).
- CSS owner: Course Expert block in `api/webui/static/workbench.css`.
- Existing safety tests: `api/tests/test_webui_template_contracts.py`, `api/tests/test_operation_routes.py::test_course_expert_page_renders_csrf`.
- Read `AGENTS.md` and `TOOLS.md` before broad inspection. Do not reread unrelated historical handoffs.

## Implementation requirements

1. Turn the left rail’s existing tool buttons into the locked Start grid, retaining their labels and `data-rail-tab` attributes. Continue/Attention must still be ordinary local links rendered by `work_rail.js`, not duplicate controls.
2. Add and maintain a semantic Workspace stage title using the active tab’s existing visible label. The title must stay accurate for initial Quiz, `?tab=assignment`, keyboard tab movement, and a rail activation.
3. Wrap—not duplicate—the current course picker and tab-panel content in the stage. Preserve the Instrument toggle and all source/validation/push controls where their feature scripts expect them.
4. Convert the right panel’s presentation into the locked Operation ledger while retaining `#ce-operations-list` unchanged as the actual live operation renderer. Review & Apply and Retry remain visible/actionable when existing state renders them.
5. At desktop width, make the three regions visually distinct: compact Work rail, broad drafting stage, narrow ledger. At narrow widths, sequence Work, Workspace, then ledger without page horizontal overflow and without hiding a current control.
6. Do not use synthetic state, static counts, or wording that implies Canvas changed. Retain `Canvas unchanged.` for the ledger empty state.

## Verification

```powershell
node --check api/webui/static/course_expert/tabs.js
node --check api/webui/static/course_expert/work_rail.js
py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_operation_routes.py api/tests/test_route_contract.py
git diff --check
```

Render `/course-expert` wide in light and dark themes and narrow in either theme. Check Quiz initial state, `?tab=assignment`, a Work-rail activation, keyboard tab navigation, and `?tab=assignment&view=instrument` then return to Workbench. Confirm a representative existing source selector and target-course control still exist, the ledger empty state is honest, no page horizontal overflow is added, and there are zero new browser-console errors. Do not validate, dry-run, scan, upload, prepare, review/apply, retry, push, or make any Canvas/AI/routine call.

## Stop conditions

Stop with RED rather than guessing if:

- The intended layout would require a duplicate form/control, script-order change, or modification to `push/core.js`.
- A visual request requires fabricated operation, course, target, preview, or validation data.
- Review/apply/retry visibility or the existing safety gate cannot be preserved.
- Instrument view or any standalone push route regresses due to the shell changes.
- An unrelated worktree change blocks the scoped files.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them to the senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **YELLOW** — implementation and focused automated checks are complete. Senior acceptance completed the wide render and functional transitions; the in-app browser viewport override did not reduce the rendered client width, so the specified narrow render remains unverified.
- Commit: changes are uncommitted (per instruction).
- Files changed: `api/webui/templates/course_expert.html`, `api/webui/static/course_expert/tabs.js`, `api/webui/static/workbench.css`, `api/tests/test_webui_template_contracts.py`, and this handoff. The existing uncommitted Desk batch and unrelated worktree changes were preserved.
- Verification: `node --check api/webui/static/course_expert/tabs.js` passed; `node --check api/webui/static/course_expert/work_rail.js` passed; `py -m pytest api/tests/test_webui_template_contracts.py api/tests/test_operation_routes.py api/tests/test_route_contract.py` passed (36 passed); `git diff --check` passed.
- Rendered routes checked: senior accepted `/course-expert` in wide light and wide dark modes with no horizontal overflow or browser-console errors. Quiz initial state, a Work-rail Assignment activation (visible Assignment panel and Workspace title), the representative Library source button and target-course picker, and the honest `Canvas unchanged.` ledger state were present. Direct `?tab=assignment&view=instrument` loaded the Instrument view; its Workbench return restored `?tab=assignment`, the Assignment title, rail, and ledger. The in-app browser viewport override did not change the 1265px rendered client width, so narrow layout and interactive keyboard-tab navigation remain unverified. No validation, scan, upload, prepare, review/apply, retry, push, or Canvas/AI/routine request was invoked.
- Deviations: none in implementation scope. The new Workspace header is hidden in Instrument mode and its grid remains single-column, preserving that separate view.
- Remaining blocker: a true narrow browser render and interactive keyboard-tab navigation should be checked when a resizable browser viewport is available. No implementation blocker remains.

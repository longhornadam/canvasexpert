# Ferrari index: CanvasExpert Desk / Workbench / Instrument redesign

Status: architecture and implementation sequence approved for specification only.
Implementation is deferred until the user explicitly authorizes a slice.

## Product decision

CanvasExpert is a dense expert console organized by **jobs -> courses -> students**.
It emphasizes raw utility, multi-course scope, professional language, warm/dark
scientific-instrument styling, and 1920px+ desktop use.

- **Desk**: Start, Continue, Attention, Prepared, Receipts, and cross-course state.
- **Workbench**: one resumable job, a persistent Work rail, explicit focused course and
  write targets, and a server-owned operation summary.
- **Instrument**: an expanded view of the same job for grading, comparison, preview,
  or delivery. It never duplicates the job/form.

Creation and pushing are first-class. Detected work does not dominate teacher intent.
Operational labels remain terse: Work, Start, Continue, Attention, Scope, Prepared,
Receipt. Do not add redundant labels such as “Teacher Jobs.”

## Stop-line prerequisite

Before any redesign implementation:

1. Resolve and accept/archive the active `webui-09` and PowerGrader setup handoffs.
2. Reconcile uncommitted changes overlapping `base.html`, PowerGrader setup files,
   `test_webui_template_contracts.py`, and module maps.
3. Preserve unrelated engine refactoring and the handoff archive move.
4. Fetch and compare `dev` with `origin/dev` and `main`; do not merge or clean histories.
5. Establish the baseline in slice 00.

## Durable contracts

- `docs/contracts/work-registry-contract.md`
- `docs/contracts/operation-ledger-contract.md`
- Existing `docs/contracts/feedback-scoring-contract.md`

## Dependency-ordered slices

| Slice | Handoff | Depends on |
|---|---|---|
| 00 | `canvasexpert-redesign-00-baseline-gate.md` | none |
| 01 | `canvasexpert-redesign-01-visual-foundation.md` | 00 |
| 02 | `canvasexpert-redesign-02-shared-context.md` | 01 |
| 03 | `canvasexpert-redesign-03-readiness-strip.md` | 02 |
| 04 | `canvasexpert-redesign-04-powergrader-push-safety.md` | 00 |
| 05a | `canvasexpert-redesign-05a-receipt-store.md` | 04 |
| 05b | `canvasexpert-redesign-05b-curve-storage-relocation.md` | 05a |
| 06a | `canvasexpert-redesign-06a-work-registry.md` | 02, 03, 05a |
| 06b | `canvasexpert-redesign-06b-work-discovery.md` | 06a |
| 07 | `canvasexpert-redesign-07-desk.md` | 06b |
| 08 | `canvasexpert-redesign-08-creation-workbench.md` | 07 |
| 09 | `canvasexpert-redesign-09-creation-instrument.md` | 08 |
| 10 | `canvasexpert-redesign-10-operation-ledger-pilot.md` | 05a, 08 |
| 10r | `canvasexpert-redesign-10r-operation-ledger-acceptance-repair.md` | 10 |
| 11a | `archive/canvasexpert-redesign-11a-quick-operation.md` | 10r |
| 11b1 | `archive/canvasexpert-redesign-11b1-assignment-core-operation.md` | 10r |
| 11b2 | `archive/canvasexpert-redesign-11b2-assignment-dependencies.md` | 11b1 |
| 11b3 | `archive/canvasexpert-redesign-11b3-assignment-autoscore.md` | 11b2 |
| 11b4 | `canvasexpert-redesign-11b4-assignment-differentiation.md` | 11b3, 11r |
| 11c0 | `archive/canvasexpert-redesign-11c0-rubric-path-audit.md` | 10r |
| 11c1 | `archive/canvasexpert-redesign-11c1-rubric-operation.md` | 11c0 |
| 11d (deferred) | `canvasexpert-redesign-11d-quiz-operation.md` | 11r |
| 11r | `archive/canvasexpert-redesign-11r-operation-integration-acceptance-repair.md` | 11a, 11b3, 11c1 |
| 12a | `canvasexpert-redesign-12a-powergrader-workbench.md` | 06a, 10r |
| 12b0 | `canvasexpert-redesign-12b0-feedback-parity-matrix.md` | 12a |
| 12b1 | `canvasexpert-redesign-12b1-feedback-import-lane.md` | 12b0 |
| 12b2 | `canvasexpert-redesign-12b2-feedback-batch-lane.md` | 12b1 |
| 12b3 | `canvasexpert-redesign-12b3-feedback-push-safety.md` | 12b2, 10r |
| 12b4 | `canvasexpert-redesign-12b4-feedback-persona-folders.md` | 12b2 |
| 12b5 | `canvasexpert-redesign-12b5-feedback-parity-acceptance.md` | 12b3, 12b4 |
| 13a | `canvasexpert-redesign-13a-late-policy-operation.md` | 05a, 10r |
| 13b1 | `canvasexpert-redesign-13b1-sweep-operation.md` | 05a, 10r |
| 13b2 | `canvasexpert-redesign-13b2-extension-operation.md` | 05a, 10r |
| 13c | `canvasexpert-redesign-13c-curve-operation.md` | 05b, 10r |
| 13d1 | `canvasexpert-redesign-13d1-roster-group-create.md` | 05a, 10r |
| 13d2 | `canvasexpert-redesign-13d2-roster-membership.md` | 13d1 |
| 13d3 | `canvasexpert-redesign-13d3-roster-workbench.md` | 13d2 |
| 13e | `canvasexpert-redesign-13e-routines-integration.md` | 05a, 06a |
| 14a | `canvasexpert-redesign-14a-gradebook-workbench.md` | 13a, 13b1, 13b2, 13c |
| 14b1 | `canvasexpert-redesign-14b1-settings-system-map.md` | 12a, 13d3, 13e |
| 14b2 | `canvasexpert-redesign-14b2-secondary-surfaces.md` | 14b1 |
| 14c | `canvasexpert-redesign-14c-navigation-legacy-cleanup.md` | 11a, 11b4, 11c1, 11d, 12b5, 14a, 14b1, 14b2 |
| 15 | `canvasexpert-redesign-15-release-acceptance.md` | all prior |

Slices are accepted sequentially. A later handoff being present is not authorization to
start it. Each implementation is one commit by default and remains active until Ferrari
or the user reviews evidence and archives it.

Discovery gates 11c0 and 12b0 are deliberately Ferrari-owned. Before delegating their
dependent Toyota slices, Ferrari must replace any named placeholders or “from the accepted
matrix” ownership references with exact files, symbols, interfaces, and commands learned
from the gate. The dependent draft is not Toyota-ready until that amendment is reviewed.

## Cross-cutting safety rules

Every handoff inherits and repeats the relevant rules:

- Never commit secrets, student data, private local paths, or real course data.
- Focused course and write-target courses are distinct.
- No client-defined arbitrary Canvas writes.
- No general activity record is called a receipt.
- Multi-operation apply is sequential and may be partial.
- AI drafts remain drafts until approval, except the existing explicit scheduled policy.
- Enabled routines run without repeated arming but produce durable evidence.
- Existing routes, deep links, script globals, script load order, theme key, PowerGrader
  sessions, autoscore queue, Feedback scoring contract, and workspace folder names stay
  compatible until their explicit removal slice.

## Shared rendered-app oracle

Use a lifespan-disabled server for read-only browser verification so enabled routines
cannot fire:

```powershell
cd api
py -m uvicorn webui.server:app --host 127.0.0.1 --port 8765 --lifespan off
```

At 1920x1080 and 2560x1440 inspect every affected route, dark and light. Confirm:

- `document.documentElement.scrollWidth === window.innerWidth` unless an explicitly
  documented data table owns horizontal scrolling.
- Required page globals exist and scripts occur once in dependency order.
- Deep links, course focus/targets, keyboard focus, dialogs, and theme initialization work.
- Browser console has zero new CanvasExpert errors or warnings.
- No Canvas write, external AI request, routine execution, or session start occurs during
  read-only verification.

Source tests never substitute for rendered verification.

# CanvasExpert Desk / Workbench / Instrument redesign

Status: **RELEASED.** All 11 operation kinds, the polling status endpoint, and restart
recovery are implemented and verified. The operation ledger is the crash-safe backend
safety layer for content pushes. See the acceptance table below.

## Product decisions (locked 2026-07-12)

1. **Polling, not SSE.** Operation progress is exposed via a polling GET endpoint
   that returns current target/step states from the durable ledger. No event log,
   no reconnection protocol, no asyncio threading. The ledger's checkpointed step
   state is the source of truth.

2. **Browser migration deferred.** The operation ledger is a backend safety layer
   accessible via API. Legacy streaming routes remain active and are not shut down.
   Browser migration to the operation-ledger path is a post-release UX improvement.

3. **Feedback stays on its existing path.** The feedback pipeline already has its
   own safety layer (SAFE/PRIVATE zones, pseudonymization, teacher review before
   push). Operation-ledger integration for feedback is deferred to post-release.

4. **Frontend work is post-release and teacher-outcome driven.** PowerGrader's
   session workbench/responsive grading instrument and Roster's focused Workbench
   lenses are complete and archived. Settings and secondary-surface polish remain
   deferred until selected from actual teacher friction. The backends are complete
   enough to support this work.

5. **Release criteria satisfied.** All registered operation kinds pass their
   focused tests, the full API test suite is green, and the operation ledger
   recovers correctly from a simulated crash. No browser runtime check required.

## Durable contracts

- `docs/contracts/work-registry-contract.md`
- `docs/contracts/operation-ledger-contract.md`
- Existing `docs/contracts/feedback-scoring-contract.md`

## Slice status

### Accepted and archived

| Slice | Description | Status |
|---|---|---|
| 00-10r | Baseline, visual foundation, shared context, readiness, receipts, work registry, desk, workbench, operation-ledger pilot + repair | archived |
| 11a | Quick assignment operation | archived |
| 11b1-11b4 | Assignment operation (core, dependencies, autoscore, differentiation) | archived |
| 11c0-11c1 | Rubric path audit + operation | archived |
| 11d0 | Quiz operation deferral | archived |
| 11d1 | Quiz plan and whole-class operation | archived |
| 11r | Operation integration acceptance repair | archived |
| 13a-13c | Gradebook operations (late policy, sweep, extension, curve) | archived |
| 13d1-13d2 | Roster group-set and membership | archived |
| 13e | Routines integration | archived |
| 14a | Gradebook workbench composition | archived |

### Released

All three remaining slices are implemented and the acceptance criteria are met.

| Slice | Description | Status |
|---|---|---|
| 11d2 | Quiz differentiation adapter — safe group/extra-time resolution, checkpointed override steps, 19 tests | **released** |
| 11d3 | Polling endpoint — `GET /api/operations/{id}/status` returning target/step states, no SSE, no asyncio | **released** |
| 15 | Release acceptance — 658 API tests, 22 recovery tests, 121 engine tests all green, no PII/secrets, `git diff --check` clean | **released** |

The 11d2, 11d3, and 15 execution briefs are archived reference specs. No further
implementation is authorized by them.

### Completed frontend work

| Work | Authority | Status |
|---|---|---|
| PowerGrader session workbench and responsive grading instrument | `docs/handoffs/archive/powergrader-frontend-workbench.md` | **completed** |
| Roster Workbench lenses over one student dataset | `docs/handoffs/archive/roster-frontend-workbench.md` | **completed** |
| Course Expert Quiz operation-ledger browser migration | `docs/handoffs/archive/course-expert-quiz-ledger-migration.md` | **completed** |
| Shared Workbench header visual integration | `docs/handoffs/archive/workbench-header-integration.md` | **completed** |
| Instrument language and drafting-grid restoration | `docs/handoffs/archive/instrument-language-and-drafting-grid.md` | **completed** |
| Workbench readiness/header and Desk control consolidation | `docs/handoffs/archive/workbench-readiness-header-consolidation.md` | **completed** |

### Deferred to post-release

| Slice | Reason |
|---|---|
| 12b0-12b5 | Feedback parity — feedback stays on existing safe path |
| 14b1-14b2 | Settings/secondary surfaces — UI polish |
| 14c | Navigation legacy cleanup — nothing to clean up (browser migration deferred) |

This redesign was completed under the former slice model. Future work follows the
senior-design -> one-executor execution briefs and risk-proportional verification in
`AGENTS.md`; this released index does not authorize new implementation by itself.

## Cross-cutting safety rules

Every implementation inherits these rules:

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

## Rendered verification reference

Use a lifespan-disabled server for read-only browser verification so enabled routines
cannot fire:

```powershell
cd api
py -m uvicorn webui.server:app --host 127.0.0.1 --port 8765 --lifespan off
```

The active execution brief names the affected routes, useful viewports, themes, and
interactions. Do not expand that matrix by ritual. For each named route, confirm:

- `document.documentElement.scrollWidth === window.innerWidth` unless an explicitly
  documented data table owns horizontal scrolling.
- Required page globals exist and scripts occur once in dependency order.
- Deep links, course focus/targets, keyboard focus, dialogs, and theme initialization work.
- Browser console has zero new CanvasExpert errors or warnings.
- No Canvas write, external AI request, routine execution, or session start occurs during
  read-only verification.

Source tests never substitute for rendered verification.

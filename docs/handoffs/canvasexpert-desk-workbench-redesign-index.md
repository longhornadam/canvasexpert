# CanvasExpert Desk / Workbench / Instrument redesign

Status: architecture accepted. Operation ledger is the crash-safe backend safety
layer for content pushes. Browser migration, SSE, and feedback parity are deferred
to post-release. The remaining work is 11d2 (mechanical), 11d3-simplified
(polling endpoint), and 15 (release acceptance).

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

4. **UI workbench slices deferred.** PowerGrader workbench (12a), roster workbench
   (13d3), settings system map (14b1), and secondary surfaces (14b2) are
   post-release polish. The backends are complete and accessible via API.

5. **Release criteria.** Release = all registered operation kinds pass their
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

### Remaining work

| Slice | Track | Description | Depends on |
|---|---|---|---|
| 11d2 | Direct (smaller model) | Quiz differentiation adapter — same pattern as 11b4. Safe group/extra-time resolution, checkpointed override steps. Browser stays legacy. | 11d1, 11b4 |
| 11d3 | Direct (smaller model) | Polling endpoint only — one GET route returning target/step states. No SSE, no event log, no asyncio threading. Browser polling loop optional. | 11d2 |
| 15 | Design (frontier) | Release acceptance — run all focused + full API tests, verify restart recovery, declare done. No browser runtime check. | 11d2, 11d3 |

### Deferred to post-release

| Slice | Reason |
|---|---|
| 12a | PowerGrader workbench — UI polish, backend complete |
| 12b0-12b5 | Feedback parity — feedback stays on existing safe path |
| 13d3 | Roster workbench — UI polish, backend complete |
| 14b1-14b2 | Settings/secondary surfaces — UI polish |
| 14c | Navigation legacy cleanup — nothing to clean up (browser migration deferred) |

Slices are implemented directly (Track 1) or with a brief design note (Track 2).
No handoff documents. The commit message + diff is the record. See AGENTS.md
"Agent workflow: two-track model" for the full policy.

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

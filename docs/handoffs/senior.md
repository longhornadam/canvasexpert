# Unified senior handoff

**Status:** One bounded closure-correction brief is locked in section 3. The one-word pseudonym
cutover implementation is complete, but its GREEN retirement was premature because the required
fixture-hygiene and rendered-browser evidence was not durably satisfied.

**Last consolidated:** 2026-08-12

**Current next pointer:** Section 3 only: close the one-word pseudonym evidence gap without
changing production behavior. Nothing in section 5 authorizes implementation.

## 1. Authority and disposition

This is the only handoff file. It replaces the former `README.md`, the root
`one-word-pseudonym-cutover.md`, both files under `senior level/`, and all three files under
`senior/`. Git history, durable contracts, and route cards remain the record for completed work.

A direct brief occupies section 3 only while it is locked and ready for (or under) execution;
none is currently locked. One implementation executor may execute that section after its
preflight holds. Sections 2, 4, and 5 are senior context only. On a GREEN result, the senior
accepts against section 3, retires that execution section in the same batch, and leaves at most
one newly locked next pointer. Do not turn section 5 into a queue of executor tasks.

## 2. Cross-document resolutions

The consolidation exposed conflicts that are now settled:

1. **One word is the only current pseudonym shape.** The authoritative
   `docs/contracts/pseudonym-contract.md` supersedes every historical two-part, fake-person, or
   hyphenated example in the retired handoffs, including `Student Alpha`, `Sparky McGee`, and
   `Reader-One`. Existing consumers continue to treat the stored value as opaque and exact.
2. **Dead Name Manager routes are deleted, not ported.** The newer cutover brief asked to update
   `POST /api/names/pseudonym`, but the earlier accepted trace proved that route and four sibling
   routes have no production consumers and are superseded by the Students per-row update path.
   Pre-launch clean-break policy won: the cutover deleted the dead routes instead of carrying them
   into schema v3.
3. **Completed initiatives do not remain implementation authority.** Pseudonym-first assessment
   conversations, feature-freeze hardening, file-based AI-chat repair, the first three read-aloud
   batches, and the fixed three-scenario findings are closed. Their current behavior belongs in
   the named contracts and route cards, not copied history here.
4. **Raw voice is not the next batch.** Optional read-aloud raw-audio transmission remains gated
   by an explicit teacher decision to keep and use OpenRouter plus every privacy/capability/cost
   law in `docs/contracts/oral-reading-evidence-contract.md`. Local transcript-first scoring is
   the delivered default.
5. **No compatibility work is justified.** Canvas Expert remains pre-launch with no legacy users
   or records. All future promotions use clean current shapes and one source of truth.

## 3. Direct brief: one-word pseudonym closure correction

**Status:** READY FOR EXECUTION

**Risk:** Low. Tests, read-only browser evidence, and closure documentation only; no production
code, private vault, Canvas data, or live-course interaction.

**Baseline:** Local `dev` at `ea6fa6b`, one clean unpushed commit ahead of `origin/dev` after the
2026-08-12 fetch.

### 3.1 Objective and acceptance criteria

Close the bounded evidence gap found after `ea6fa6b` without reopening the pseudonym design:

1. Replace every multiword pseudonym JSON literal found by the locked hygiene check with a valid
   one-word value from `api/data/pseudonym_words.json`. This includes the ordinary packet/gate
   examples and the structurally fictional conflict file; this correction adds no new rejection
   behavior.
2. Changes are limited to the four named test files and this handoff. No production file changes.
3. The four-file focused gate passes with `pytest-randomly` disabled, the exact hygiene check
   returns zero matches, and `git diff --check` passes.
4. `/roster` is rendered from a lifespan-disabled local server without selecting or refreshing a
   real course. `window.CE_ROSTER`, `table.js`, and `inline_edit.js` load; a valid fictional
   one-word row renders; a stubbed edit captures a `/api/roster/student` JSON patch whose
   `pseudonym` is a string; and the browser records zero CanvasExpert console errors or warnings.
5. The execution result below records the commit hash, changed files, exact command counts,
   hygiene result, browser evidence, zero production/Canvas/private-vault interaction, and the
   accepted documentation deviation from `ea6fa6b`.

### 3.2 Locked decisions, scope, and non-goals

- Use existing registry words; do not invent or extend the vocabulary.
- Test functions remain functions. Do not add tests: only correct invalid fictional examples.
- Authorized test files are exactly:
  - `api/tests/test_scoring_packet_mcp.py`;
  - `api/tests/mcp_server/test_tools.py`;
  - `api/tests/powergrader/test_copilot_packet.py`; and
  - `api/tests/test_vault_conflict_endpoint.py`.
- The prior edit to `docs/reference/workbench-canonical-flow-map.md` is accepted as a necessary
  truth correction for the deleted `/name-manager` route. Record it as the sole deviation from
  the former file allowlist; do not edit that document again.
- Do not amend or rewrite `ea6fa6b`. Make one follow-up executor commit. Do not push; the senior
  reviews, retires this brief, and pushes afterward under the user's explicit authorization.
- Do not rerun the full API suite: it passed at `ea6fa6b`, and this correction changes only
  fictional test values. Do not touch Canvas, credentials, configured courses, the configured
  Identity Vault, production code, or section 5.

### 3.3 Required references and preflight

Read only:

1. `AGENTS.md`;
2. this file, sections 1-3;
3. `docs/reference/project-state.md` sections **Status: pre-launch**, **Userbase**, and **What this
   means for scope**;
4. `docs/contracts/pseudonym-contract.md` in full;
5. `api/webui/README.md` section **Rendered verification (read-only)**; and
6. the four authorized test files plus `api/data/pseudonym_words.json`.

Before writing, confirm branch `dev`, baseline `ea6fa6b` with only this senior-authored handoff
edit dirty, exactly one handoff file, and the 14 known exact hygiene hits across the four
authorized files. Stop if another file matches, any authorized test file has an overlapping edit,
or a production change appears necessary.

### 3.4 Named verification gate

```powershell
py -m pytest api/tests/test_scoring_packet_mcp.py api/tests/mcp_server/test_tools.py api/tests/powergrader/test_copilot_packet.py api/tests/test_vault_conflict_endpoint.py -p no:randomly
```

Exact hygiene check (PowerShell-native so quote handling is stable):

```powershell
$files = Get-ChildItem api/tests,api/dailywriting/fixtures -Recurse -File
$files | Select-String -Pattern '"pseudonym"\s*:\s*"[^" ]+ [^"]+"'
git diff --check
```

Render `/roster` using the lifespan-disabled command in the required Web UI reference. Inject only
fictional in-memory state, stub `window.fetch` before the edit, clear the fictional state, and
stop the server after verification. Do not select a course or send the edit request.

### 3.5 Stop conditions

Return RED before expanding scope if a production file must change, a hygiene hit exists outside
the four authorized files, or the browser check would touch a real course, Canvas, or the
configured vault. Return YELLOW for an unrelated focused-test failure or an unavailable browser
environment. Do not substitute source inspection for browser evidence.

### 3.6 Execution result

- Traffic light: GREEN
- Commit hash: This follow-up executor commit; its exact hash is returned in chat because a commit
  cannot contain its own final hash.
- Changed files: `api/tests/test_scoring_packet_mcp.py`,
  `api/tests/mcp_server/test_tools.py`, `api/tests/powergrader/test_copilot_packet.py`,
  `api/tests/test_vault_conflict_endpoint.py`, and this handoff.
- Focused gate command and result/count: `py -m pytest api/tests/test_scoring_packet_mcp.py
  api/tests/mcp_server/test_tools.py api/tests/powergrader/test_copilot_packet.py
  api/tests/test_vault_conflict_endpoint.py -p no:randomly` -> 176 passed in 5.51s.
- Exact hygiene result: the locked `Get-ChildItem` / `Select-String` command returned 0 matches;
  `git diff --check` passed with no errors.
- Rendered `/roster` evidence and console warning/error count: the lifespan-disabled local route
  returned HTTP 200; `window.CE_ROSTER` existed; `table.js` and `inline_edit.js` each loaded once;
  an in-memory fictional `Quartz` row rendered; a pre-stubbed edit captured POST
  `/api/roster/student` with JSON patch `{"pseudonym":"Mica"}` (string); the fictional row/state
  was then cleared. Browser count: 0 console warnings/errors and 0 page errors.
- Canvas/private-vault interaction: zero. No course was selected or refreshed, every page `fetch`
  was intercepted in-browser before dispatch, the edit request was not sent, and the local server
  was stopped after verification.
- Accepted prior deviation: `ea6fa6b` corrected
  `docs/reference/workbench-canonical-flow-map.md` outside the former allowlist for the deleted
  `/name-manager` route; this execution did not edit it.
- New deviations: none.
- Unresolved decisions: none.

## 4. Closed work retained only for orientation

| Former document | Current disposition |
| --- | --- |
| Pseudonym-first assessment conversations | Batch A is complete. `get_assessment_context` and the read-only grouping proposal remain governed by `docs/reference/dataforge-route-card.md` and `docs/mcp-server.md`. Only first-live-course verification remains. |
| Feature-freeze hardening | Approved hardening, operational logging, synced Library sources, and platform-service layering are complete. MCP soft flags now emit aggregate counts only. C3/C4 remain diagnostic observations, not authorized work. |
| Three-scenario teacher trace | Vault-conflict repair, readiness probing, honest failed-sync status, custom-routine scheduling, Pages `page_id`, and MCP Canvas-write disclosure are fixed. The dead Name Manager routes are deleted (see the one-word pseudonym cutover row below). Other old findings require fresh validation before any promotion. |
| File-based AI-assist trace | Silent zero-import, vendor-neutral naming, real download filenames, unsafe scoring-skill retirement, binary upload guard, aggregate-only Writing Timeline projection, and one output-contract source are complete. ZIP input/return packaging is rejected because M365 Copilot cannot read ZIP attachments. |
| Media-recording read-aloud initiative | Batches A-C plus later hardening are complete under the user-authorized synthetic-only override. Transcript-first local scoring is current. Raw-audio Batch D is optional; Batch E remains field-use gated. |
| One-word pseudonym cutover | Implementation commit `ea6fa6b` delivered the schema-v3 registry cutover, but the post-commit senior audit found fixture-hygiene and rendered-evidence gaps. Section 3 is the sole authorized closure correction; do not promote another batch until it closes. |

Do not re-derive or reimplement closed work from this table. Read the relevant current route card
or contract when a future teacher-visible need reaches that subsystem.

## 5. Deferred senior decisions and verification gates

These are not ordered work items and do not authorize implementation. A future senior selects at
most one after checking current repository truth, writes independent acceptance criteria, and
adds a new section 3 only when that batch is ready for execution.

- **OpenRouter's future:** decide keep, retire, or keep alongside file/MCP lanes. Optional raw-audio
  scoring cannot be promoted before that decision and a fresh provider/privacy verification.
- **First-live-course checks:** after populated classes exist, verify assessment-context coverage
  and freshness; verify real Canvas `MediaComment`/signed-download behavior using teacher-created
  dummy evidence only; and complete one file-based PowerGrader round trip. These are validation
  gates, not current acceptance failures.
- **Teacher-trace remainder:** catalog self-refresh over MCP, learning-objective source identity and
  digest projection, schedule completeness/day-resolution UI, bell-boundary refresh across the
  remaining Panel templates, accommodation-aware `effective_late`, excused/ungraded totals, and a
  local-only pseudonym-to-name reading utility were not closed by the trace. Each must be
  revalidated and promoted separately; none may be inferred current solely from the retired trace.
- **Structural diagnostics:** in-function imports and module-size imbalance remain observations.
  Do not launch a cleanup without an immediate consumer and a bounded seam.
- **AI-chat context sizing:** the 128k batch assumption remains hard-coded. Make it visible or
  configurable only after measuring the actual primary chat lane; do not reintroduce ZIP packaging.
- **Nickname elongation:** repeated-character tolerant matching remains deliberately unbuilt. It
  changes a privacy-load-bearing matcher and requires a concrete recurring miss or teacher request.

Standing rejected directions remain rejected: no regex for phone/email/address in student writing,
no third-party-name matching beyond the roster/nickname boundary, no consolidated teacher-facing
activity dashboard, no second identity/profile/roster store, no raw audio over MCP, and no automatic
posting of media-derived scores.

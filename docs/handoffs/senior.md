# Unified senior handoff

**Status:** Current senior authority. One execution-ready batch is locked below; no other
document under `docs/handoffs/` is current.

**Last consolidated:** 2026-08-12

**Current next pointer:** One-word pseudonym cutover, section 3. Nothing else in this file
authorizes implementation.

**Baseline:** The consolidation was written from local `dev` at `ed22cfd`. A fetch on
2026-08-12 found `origin/dev` at `958f5f6`, one commit ahead only in
`api/default_docs/Calendars/Bell Schedule - Friday.csv`. The executor must begin from fetched
`origin/dev` at `958f5f6` or return for a senior re-lock if `dev` has moved again.

## 1. Authority and disposition

This is the only handoff file. It replaces the former `README.md`, the root
`one-word-pseudonym-cutover.md`, both files under `senior level/`, and all three files under
`senior/`. The tracked documents remain available in Git history at `ed22cfd`; the untracked
one-word brief is preserved and corrected in section 3. Git history, durable contracts, and route
cards remain the record for completed work.

Section 3 is the single direct brief required by `AGENTS.md`. One implementation executor may
execute that section after its preflight holds. Sections 2, 4, and 5 are senior context only. On a
GREEN result, the senior accepts against section 3, retires that execution section in the same
batch, and leaves at most one newly locked next pointer. Do not turn section 5 into a queue of
executor tasks.

## 2. Cross-document resolutions

The consolidation exposed conflicts that are now settled:

1. **One word is the only current pseudonym shape.** The authoritative
   `docs/contracts/pseudonym-contract.md` supersedes every historical two-part, fake-person, or
   hyphenated example in the retired handoffs, including `Student Alpha`, `Sparky McGee`, and
   `Reader-One`. Existing consumers continue to treat the stored value as opaque and exact.
2. **Dead Name Manager routes are deleted, not ported.** The newer cutover brief asked to update
   `POST /api/names/pseudonym`, but the earlier accepted trace proved that route and four sibling
   routes have no production consumers and are superseded by the Students per-row update path.
   Pre-launch clean-break policy wins: section 3 deletes the dead routes instead of carrying them
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

## 3. Direct brief: one-word pseudonym cutover

**Status:** READY FOR EXECUTION

**Risk:** High - private identity mapping and every pseudonymized outbound surface

**Branch:** `dev`

### 3.1 Objective

Deliver the canonical one-word pseudonym contract end to end. A fresh roster sync assigns and
shows one unique mineral, weather, or ocean word per student. Students editing and regeneration,
the scrubber, MCP roster writes, and downstream pseudonym consumers use that same string.

The current implementation is known wrong: it still constructs first/last fake-person names, the
configured pre-launch vault contains only two-word entries, and focused tests encode the retired
shape. This is a clean replacement; it does not preserve the retired contract or mutate the
configured private vault.

### 3.2 Acceptance criteria

1. `docs/contracts/pseudonym-contract.md` holds in full. There is one categorized registry at
   `api/data/pseudonym_words.json`, with at least 256 unique valid words and no animal,
   fictional-character, human-name, sequential-ID, or out-of-category entry.
2. `fake_first_names.txt` and `fake_last_names.txt` are deleted. Current schemas, fixtures,
   outputs, and accepted APIs contain no `pseudo_first` or `pseudo_last` field and no first/last
   pseudonym shape. The only permitted source reference to those keys is an explicit fail-closed
   validator/test for rejecting a non-v3 document.
3. A new schema-v3 vault assigns one registry word, persists it, returns it stably on later reads,
   avoids supplied roster tokens, preserves case-insensitive uniqueness, and fails closed on
   invalid registry data or exhaustion. Manual set and regenerate obey the same allowlist and
   collision law; regenerate returns a different word.
4. A present non-v3 or structurally retired vault is rejected before any save. There is no
   automatic migration, dual read, compatibility mapping, startup reset, or configured-vault
   mutation.
5. A fresh mirror-backed or fictional Canvas roster load through `GET /api/roster` upserts the new
   schema and returns only `pseudonym` for the pseudonym value. Every returned pseudonym is one
   registry word.
6. Students renders that exact value in one input. An edit sends
   `{"pseudonym":"Quartz"}` as a string; invalid, multiword, out-of-registry, and colliding
   values are refused without altering the vault. Regenerate produces and displays a different
   valid one-word value.
7. `POST /api/roster/student` and the MCP preview/apply path accept the same one-string contract,
   report collision/validation failures without a partial write, and preserve the current safe
   pseudonym-rename order. The dead `/api/names/roster`, `/api/names/nickname`,
   `/api/names/pseudonym`, `/api/names/pseudonym/regenerate`, and `/api/names/collisions` routes
   are deleted rather than updated. The live `/api/names/protected`, `/api/names/scrub-test`,
   `/api/names/who-is-who`, `/api/names/backup-vault`, and `/api/names/vault-conflict` routes stay.
8. The scrub replacement law maps a student's full real name, each real-name token, and each
   nickname to the same full one-word pseudonym. Canvas/SIS ID placeholder behavior is unchanged.
   No partial pseudonym component remains in a SAFE artifact.
9. PowerGrader, DataForge, Daily Writing, mirror/MCP reads, reverse lookup, exports, and stored
   pseudonym references continue to treat the value as opaque and exact. Their examples and
   fixtures use valid one-word registry entries; no subsystem adds its own pool.
10. The named focused gate, full API integration gate, hygiene scans, and rendered Students check
    pass with no undeclared deviation. No real names, IDs, mappings, or configured-vault values
    appear in test output or the execution report.

### 3.3 Explicit non-goals

- Do not touch Canvas, live course data, credentials, settings, mirror documents, or the
  configured private Identity Vault.
- Do not implement a legacy-vault migration, backward-compatible reader, dual schema, reset
  button, one-time startup job, or retirement banner.
- Do not change pseudonym stability, reverse lookup, rename propagation, outbound review, safety
  scanning, PowerGrader review, or Canvas-write policy except for the locked value shape.
- Do not add animals, fictional characters, human-style names, colors, plants, celestial objects,
  or a pluggable vocabulary system.
- Do not change `engine/`, CanvasMirror storage formats, or any Canvas transport.
- Do not preserve or replace the dead Name Manager endpoints with aliases, redirects, or new
  compatibility routes.

### 3.4 Locked design decisions

- Registry: one JSON object with exactly `mineral`, `weather`, and `ocean` arrays.
- Token: title-case ASCII letters only; one token; no hyphens, digits, spaces, or generated
  suffixes.
- Capacity: at least 256 case-insensitively unique words. Exhaustion is an error.
- Storage: root `schema_version: 3`; entry field `pseudonym` only. Category is derived from the
  registry and is not duplicated into each vault entry.
- Selection: random from currently available allowlisted words; stored assignment provides
  stability. Never derive a pseudonym deterministically from a Canvas or SIS ID.
- Collision avoidance: exclude every used vault pseudonym and every supplied roster-name token
  under case-folded comparison.
- Manual UI/MCP value: one string already present in the registry. The registry is not a
  suggestion list for arbitrary teacher text.
- Scrub substitution: all name and nickname matches resolve to the same complete pseudonym.
- Clean break: incompatible private state fails closed. Moving aside the current developer vault
  is a later recoverable user action, never executor authority.
- Dead-route resolution: delete the five retired Name Manager endpoints and their route entries;
  do not spend implementation or test surface adapting them to schema v3.
- Test style: functions, not classes. `pytest-randomly` stays disabled in named gates.

### 3.5 Scope and insertion points

Production changes are limited to:

- `api/feedback_vault.py` - registry validation, schema-v3 load/save, assignment, set,
  regenerate, entries, and reverse index;
- `api/data/pseudonym_words.json` - the sole reviewed vocabulary;
- deletion of `api/data/fake_first_names.txt` and `api/data/fake_last_names.txt`;
- `api/feedback_scrub.py::build_replacement_map` - one complete replacement value;
- `api/webui/routes/roster.py::roster_get` - response shape only;
- `api/webui/routes/roster_updates.py::update_student` - one-string validation/apply while
  preserving rename ordering and transaction behavior;
- `api/webui/static/roster/inline_edit.js` - capture, send, and display one string;
- `api/webui/static/roster/table.js` only if placeholder or markup needs a shape correction;
- `api/mcp_server/tools.py::_validate_mcp_roster_patch` and `api/webui/roster_mcp.py` only as
  required to enforce the identical string contract;
- `api/webui/routes/names.py` - delete the five dead endpoints while preserving the five live
  safety/conflict endpoints named in criterion 7;
- `api/webui/routes/pages.py` only to delete `/name-manager` if preflight confirms it has no
  production link or caller;
- fictional fixtures under `api/dailywriting/fixtures/` and `api/tests/` for mechanical
  schema/value updates; and
- documentation truth updates limited to `docs/contracts/pseudonym-contract.md`,
  `docs/contracts/feedback-scoring-contract.md`, `docs/reference/roster-module-map.md`,
  `docs/mcp-server.md`, and pseudonym safety wording in `api/webui/README.md`.

`api/roster_service.py`, `api/pseudonym_rename.py`, `api/feedback_artifacts.py`,
`api/dataforge/identity.py`, and `api/mcp_server/pseudonym.py` are expected consumers to inspect at
their pseudonym symbols, not presumed edit targets. If compliance requires a production change
there, record why in this brief before editing. Any other production owner is a RED scope
expansion.

Tests may change only where they directly encode the registry/vault/scrub/route/MCP contract, the
dead route registry, or the one fictional vertical example. Do not rewrite unrelated assertions.

### 3.6 Required references

The executor reads only:

1. `AGENTS.md`;
2. this file, sections 1-3 only;
3. `docs/reference/project-state.md` - **Status: pre-launch**, **Userbase**, and
   **What this means for scope**;
4. `docs/contracts/pseudonym-contract.md` in full;
5. `docs/reference/roster-module-map.md` - **Entry points and owners**,
   **Privacy and write boundaries**, and **Test routing**;
6. `docs/contracts/feedback-scoring-contract.md` - the opening **Privacy invariant**,
   **Direction 1 - Bundle (app -> LLM)**, and **Direction 2 - Results (LLM -> app)**;
7. `api/webui/README.md` - **Roster module routing** and the PowerGrader safety wording at the end
   of its workflow description; and
8. `docs/mcp-server.md` - opening safety bullets before **Tools**, roster/submission/gradebook rows
   in **Tools**, and pseudonym-filter paragraphs under **Token-lean results**.

Do not read retired handoffs or the CanvasMirror vision spine.

### 3.7 Preflight before writing

1. Confirm `docs/handoffs/` contains only this file.
2. Confirm branch `dev`; fetch and compare `origin/dev` and `origin/main`. The locked execution
   baseline is `origin/dev` at `958f5f6`. If either remote has moved, stop for a senior re-lock.
3. Preserve unrelated dirty files. At consolidation time they are `Open Canvas Expert.bat`,
   `Repair.bat`, and `api/default_docs/AI Authoring/START HERE - CanvasAgent.txt`. The untracked
   `docs/contracts/pseudonym-contract.md` is intended authority for this batch. Stop if any other
   scoped file has an overlapping uncommitted edit.
4. Confirm current implementation assumptions with:

   ```powershell
   rg -n "pseudo_first|pseudo_last|fake_first_names|fake_last_names|set_pseudonym" api
   rg -n "pseudonym" api/webui/static/roster/inline_edit.js api/webui/routes/roster_updates.py api/mcp_server/tools.py
   ```

5. Confirm the five dead Name Manager routes still have no production callers. Keep the five live
   routes named in criterion 7. Delete `/name-manager` only if it is also unlinked. If a real
   production consumer exists, stop RED rather than porting or deleting around it.
6. Confirm the configured Identity Vault is outside the repository. Do not open, print, move,
   save, or test against it. All vault tests use `tmp_path` or fictional in-memory data.
7. Stop RED if the retired first/last generator is no longer the active source of truth, a named
   mutation seam is absent, or current repo truth contradicts a locked criterion.

### 3.8 Implementation sequence

1. Add and validate the canonical registry; replace the vault schema and assignment law.
2. Convert the scrubber and current Roster/MCP mutation contracts to one string.
3. Delete the five dead Name Manager routes, their route registrations/tests, and the unlinked
   redirect if confirmed; do not build a v3 version of any retired route.
4. Convert Students browser state and markup behavior.
5. Mechanically update affected fictional fixtures/examples and the narrow durable docs.
6. Add the pre-authored law/contract/example tests, run the focused gate, perform the rendered
   route check, then run the full API integration gate once.

Do not pause after a partial backend conversion. This slice is the whole vertical contract.

### 3.9 Required tests by taxonomy

**Law**

- Registry: exact categories, at least 256 entries, title-case ASCII single tokens,
  case-folded uniqueness, and no empty/out-of-contract structure.
- Vault: every assign/set/regenerate result is an available registry word, globally unique,
  stable after persistence, roster-token-safe, and never synthesized on exhaustion.
- Scrub: full name, component tokens, and nicknames all resolve to the same complete pseudonym;
  ID placeholders remain unchanged.

**Contract**

- Parametrize the current Roster route/MCP pseudonym patch boundary over accepted string and
  rejected blank, multiword, non-string, out-of-registry, and colliding values. Assert no partial
  write.
- Parametrize serialized vault entries and roster rows from their defining field lists so retired
  component fields cannot return unnoticed.
- Update the route registry from its defining list to remove the five dead Name Manager routes;
  do not add five one-off negative route tests.

**Example**

- One fictional fresh-roster load through `/api/roster`, followed by one Students-style manual
  rename and one regeneration, documents the intended happy path.

Do not add duplicate consumer examples or test classes.

### 3.10 Verification gates

Focused slice gate:

```powershell
py -m pytest api/tests/test_feedback_vault.py api/tests/test_feedback_scrub.py api/tests/test_feedback_pipeline.py api/tests/test_pseudonym_rename.py api/tests/test_roster_routes.py api/tests/test_roster_mcp_write.py api/tests/mcp_server/test_tools.py api/tests/test_route_contract.py api/tests/dataforge api/tests/dailywriting -p no:randomly
```

Hygiene checks:

```powershell
rg -n "pseudo_first|pseudo_last|fake_first_names|fake_last_names" api --glob '!api/tests/**'
rg -n '"pseudonym"\s*:\s*"[^" ]+ [^"]+"' api/tests api/dailywriting/fixtures
rg -n "/api/names/(roster|nickname|pseudonym|collisions)|/name-manager" api --glob '!api/tests/**'
```

The first command may hit only the explicit non-v3 rejection check. The second may hit only a
deliberate negative-test input whose assertion makes multiword rejection explicit. The third must
return no production caller or route; it does not match the five live Name Manager safety/conflict
routes.

Rendered Students check:

- Load `/roster` without selecting or refreshing a real course.
- Confirm `window.CE_ROSTER`, `table.js`, and `inline_edit.js` load with zero new console errors.
- In page memory only, inject one complete fictional student row using a valid registry word,
  render it through `CE_ROSTER.setFilteredStudents(...)` and `CE_ROSTER.renderTable()`, and stub
  `window.fetch` before dispatching an edit. Confirm the input is one word and the captured
  `/api/roster/student` form contains a JSON patch whose `pseudonym` is a string.
- Clear the fictional DOM state. Do not select a configured course or send a real request.

Because this is a cross-cutting privacy change, run one integration checkpoint after the focused
gate and browser check:

```powershell
py -m pytest api/tests -p no:randomly
```

Do not run `engine/tests` unless an unexpected engine coupling appears; that is a RED scope
contradiction, not routine verification.

### 3.11 Stop conditions

Return RED before expanding work if:

- a production pseudonym owner outside the authorized scope must change;
- preserving current behavior would require migration, dual-read, or multiple vocabularies;
- rename propagation cannot remain atomic and correctly ordered with a one-string value;
- the registry cannot supply at least 256 plainly in-category words without ambiguity;
- a supposedly dead Name Manager route has a current production consumer;
- any test or browser verification would require real student data or the configured vault;
- an unrelated regression appears; or
- a public contract beyond pseudonym shape must change.

Return YELLOW if the browser check or full API gate is unavailable for an environmental reason
after the focused gate passes. Do not substitute source inspection for browser evidence.

### 3.12 Execution result

- Traffic light:
- Commit hash (if any):
- Changed files:
- Focused gate command and result/count:
- Hygiene scan result:
- Rendered `/roster` evidence and console-error count:
- Full API gate command and result/count:
- Deviations:
- Unresolved decisions:

## 4. Closed work retained only for orientation

| Former document | Current disposition |
| --- | --- |
| Pseudonym-first assessment conversations | Batch A is complete. `get_assessment_context` and the read-only grouping proposal remain governed by `docs/reference/dataforge-route-card.md` and `docs/mcp-server.md`. Only first-live-course verification remains. |
| Feature-freeze hardening | Approved hardening, operational logging, synced Library sources, and platform-service layering are complete. MCP soft flags now emit aggregate counts only. C3/C4 remain diagnostic observations, not authorized work. |
| Three-scenario teacher trace | Vault-conflict repair, readiness probing, honest failed-sync status, custom-routine scheduling, Pages `page_id`, and MCP Canvas-write disclosure are fixed. The dead Name Manager route decision is folded into section 3. Other old findings require fresh validation before any promotion. |
| File-based AI-assist trace | Silent zero-import, vendor-neutral naming, real download filenames, unsafe scoring-skill retirement, binary upload guard, aggregate-only Writing Timeline projection, and one output-contract source are complete. ZIP input/return packaging is rejected because M365 Copilot cannot read ZIP attachments. |
| Media-recording read-aloud initiative | Batches A-C plus later hardening are complete under the user-authorized synthetic-only override. Transcript-first local scoring is current. Raw-audio Batch D is optional; Batch E remains field-use gated. |

Do not re-derive or reimplement closed work from this table. Read the relevant current route card
or contract when a future teacher-visible need reaches that subsystem.

## 5. Deferred senior decisions and verification gates

These are not ordered work items and do not authorize implementation. A future senior selects at
most one after checking current repository truth, writes independent acceptance criteria, and
replaces section 3 only after the current cutover is closed.

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

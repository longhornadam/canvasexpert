# Unified senior handoff

**Status:** No direct brief is currently locked for execution. The one-word pseudonym cutover and
its bounded closure correction closed GREEN on 2026-08-12 (outcome recorded in section 4); no
other document under `docs/handoffs/` is current.

**Last consolidated:** 2026-08-12

**Current next pointer:** None. A future senior selects at most one item from section 5, writes
independent acceptance criteria, and adds a new section 3. Nothing in this file currently
authorizes implementation.

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

## 3. Direct brief

None currently locked. The one-word pseudonym cutover and its closure correction closed GREEN on
2026-08-12; their durable execution evidence is recorded in commits `ea6fa6b` and `c5eb65c`.
A future senior writes a new section 3 only when the next batch is ready for execution.

## 4. Closed work retained only for orientation

| Former document | Current disposition |
| --- | --- |
| Pseudonym-first assessment conversations | Batch A is complete. `get_assessment_context` and the read-only grouping proposal remain governed by `docs/reference/dataforge-route-card.md` and `docs/mcp-server.md`. Only first-live-course verification remains. |
| Feature-freeze hardening | Approved hardening, operational logging, synced Library sources, and platform-service layering are complete. MCP soft flags now emit aggregate counts only. C3/C4 remain diagnostic observations, not authorized work. |
| Three-scenario teacher trace | Vault-conflict repair, readiness probing, honest failed-sync status, custom-routine scheduling, Pages `page_id`, and MCP Canvas-write disclosure are fixed. The dead Name Manager routes are deleted (see the one-word pseudonym cutover row below). Other old findings require fresh validation before any promotion. |
| File-based AI-assist trace | Silent zero-import, vendor-neutral naming, real download filenames, unsafe scoring-skill retirement, binary upload guard, aggregate-only Writing Timeline projection, and one output-contract source are complete. ZIP input/return packaging is rejected because M365 Copilot cannot read ZIP attachments. |
| Media-recording read-aloud initiative | Batches A-C plus later hardening are complete under the user-authorized synthetic-only override. Transcript-first local scoring is current. Raw-audio Batch D is optional; Batch E remains field-use gated. |
| One-word pseudonym cutover | Complete and GREEN on 2026-08-12 in `ea6fa6b` plus closure correction `c5eb65c`. `docs/contracts/pseudonym-contract.md` is authoritative; `api/data/pseudonym_words.json` holds the 351-word mineral/weather/ocean registry; the Identity Vault is schema v3; Roster, MCP, and the scrubber all use the single-string contract. The five dead `/api/names/*` routes and `/name-manager` are deleted. The required focused correction gate passed 176 tests; exact fixture hygiene returned zero matches; rendered `/roster` verification captured the one-string edit contract with zero browser warnings/errors and zero Canvas or configured-vault interaction. The workbench flow-map truth correction is accepted as the sole former-scope deviation. |

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

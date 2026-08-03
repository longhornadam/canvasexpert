# Pseudonym-first assessment conversations initiative

**Status:** Senior context; no active direct execution brief

**Last senior review:** 2026-08-03

**Next batch pointer:** Batch A - pseudonym-first assessment context over MCP

This document is persistent senior context. It does not authorize implementation directly.
The senior promotes Batch A into the single direct brief in `docs/handoffs/` after locking
the exact baseline and files against the then-current repository.

## 1. Teacher outcome

The teacher talks with an AI assistant about students by using CanvasExpert pseudonyms.
The assistant must be able to answer a question such as:

> "What should I focus on with `Student Alpha` in this course, given the assessment history?"

without asking the teacher to manually compare the Assessments screen, Students screen,
gradebook, and standards profile.

The assistant may combine current course facts with longitudinal assessment evidence, but it
must say what each source actually means. Assessment history imported from Eduphoria is a
local longitudinal artifact; it is not automatically attributable to the current Canvas
course merely because the pseudonym is present in the current roster.

## 2. Why this initiative exists

CanvasExpert already has the important identity boundary:

- `get_roster(course_id)` returns current roster facts by pseudonym.
- `get_submissions(course_id, ...)` and `get_gradebook_snapshot(course_id)` return
  pseudonymized course facts from the local mirror.
- `get_writing_history(pseudonym, ...)` is already explicitly pseudonym-first.
- `get_standards_profile()` returns the published DataForge profile keyed by pseudonym.

The gap is the assistant-facing join. The DataForge profile is deliberately not course-scoped,
and the assessment grouping proposal currently lives behind the Students UI. The assistant can
make separate calls and attempt the join itself, but CanvasExpert does not provide a bounded,
privacy-gated assessment context or a read-only grouping proposal over MCP.

The UI is therefore not missing. The conversational data surface is incomplete.

## 3. Locked product decisions

### 3.1 Pseudonym is the conversation key

The pseudonym is the only student identifier exposed to the assistant. The assistant-facing
projection must never include Canvas user IDs, SIS IDs, section IDs, submission IDs, vault
paths, or identity-vault mappings. The teacher is responsible for knowing which real student a
pseudonym represents; CanvasExpert never helps re-identify one.

Pseudonym matching is exact after trim and case-folding. Do not add fuzzy matching, name
expansion, or a second identity namespace.

### 3.2 Current-course scope is the roster intersection

`course_id` is required for assessment context. The current local roster is the denominator.
Assessment rows are included only when their pseudonym is present in that current roster.
Return explicit coverage counts for:

- current roster students with matching assessment history;
- current roster students with no matching assessment history;
- requested pseudonyms that are not in the current roster; and
- assessment-profile students not in the current roster, counted but not disclosed as rows.

Do not claim that an assessment was taken for the current course unless the source artifact
actually carries that course relationship. The response must label the assessment source as
local longitudinal history and identify its generated date/grain.

### 3.3 Freshness is fail-closed

The current roster mirror must be current before student data is returned. A missing, stale,
malformed, or internally inconsistent roster returns a structured attention result with no
student rows and tells the assistant to use `refresh_mirror` before retrying.

The DataForge profile is local published state, not a live Canvas read. Its generated date and
profile availability are returned as source metadata; an old but valid profile is not silently
represented as current course state.

### 3.4 Narrow reads are the default

The tool accepts an optional pseudonym filter. A single-student conversation should not require
returning the whole class or the whole assessment profile. Results must have deterministic
limits and a bounded token shape. If a requested set exceeds the limit, return a clear limit
error rather than truncating students without saying so.

### 3.5 MCP remains read-only with respect to Canvas

The assistant may inspect a grouping proposal, but it may not apply Canvas group membership
through this initiative. The teacher reviews and applies the proposal in the existing Students
UI and existing digest-protected bulk transport. No new Canvas mutation owner or MCP Canvas
write is permitted.

### 3.6 The app reports; it does not judge

Assessment percentages, standards, attempts, and weak-standard flags are observable source
facts. The tool must not label a student as capable, incapable, lazy, dishonest, or in need of
a particular placement beyond the explicit grouping method and its inputs. The assistant may
help the teacher interpret the evidence, but the data contract must not encode an integrity
judgment.

## 4. Batch A surface

Batch A adds one read-only MCP context surface and one read-only proposal projection. Both use
the existing local services; neither creates a parallel assessment store or identity system.

### 4.1 `get_assessment_context(course_id, pseudonyms="")`

The exact public name may change only in the promoted brief, but the contract must provide:

- current-course source and roster freshness metadata;
- DataForge profile generated date, grain, and explicit `local_longitudinal_history` scope;
- coverage counts described in section 3.2;
- one bounded row per requested/current-roster pseudonym, including assessment count, latest
  assessment date/percentage, weak-standard codes, and the per-standard evidence needed for
  teacher discussion;
- no Canvas IDs, SIS IDs, raw names, vault data, private paths, or raw workbook contents;
- stable empty states for unavailable profile, no matching students, and students with no
  assessment history.

The service should join by the pseudonym projection at the boundary. It may use local
`canvas_id` joins internally where the existing DataForge history/profile code requires them,
but those fields must be gone before the MCP result is returned.

Do not duplicate the full gradebook in this first context payload. The assistant can call the
existing course-scoped gradebook/submission tools when the teacher asks for current work. If a
later measured use case proves that a compact current-course summary belongs in this tool, it
requires a separate senior decision and token budget.

### 4.2 `get_assessment_grouping_proposal(...)`

Expose the existing Students-page proposal as a read-only, pseudonym-safe projection. Inputs
must identify the current course, assessment snapshot, grouping method/cutoffs, explicit No Data
group, and selected Canvas group set by a teacher-safe label. The server may resolve that label
to an internal category ID, but raw IDs must not be required from or returned to the assistant.

The response must include:

- proposal source and coverage status;
- the method and cutoffs used;
- group names, counts, and pseudonym membership;
- explicit No Data placement;
- exact roster-coverage result and any blocking error;
- a proposal digest or equivalent review identity so the teacher can recognize the UI proposal.

The projection must reuse `api.dataforge.canvas_join` and `api.dataforge.grouping` rather than
reimplementing tier rules in the MCP wrapper. The UI and MCP projections must agree on the
same synthetic fixtures.

## 5. Data and ownership boundaries

The implementation must preserve these owners:

| Concern | Owner | Rule |
| --- | --- | --- |
| Current roster freshness and course membership | CanvasMirror/read service | Mirror-only; no live fallback in the context tool |
| Assessment history and standards aggregation | `api/dataforge/history_store.py`, `profile_export.py` | Preserve longitudinal semantics and source labels |
| SIS/Canvas identity joins | `api/dataforge/canvas_join.py`, Identity Vault | Internal only; never in MCP output |
| Grouping rules | `api/dataforge/grouping.py` | One source of tier/coverage truth |
| MCP projection and privacy gate | `api/mcp_server/tools.py` and `server.py` | Bounded, pseudonym-only result |
| Teacher review and Canvas apply | Students UI and existing `/api/roster/bulk` path | No new mutation transport |
| Product instructions | `docs/mcp-server.md`, Appendix G of `START HERE - CanvasAgent.txt` | Teach the assistant the source limits and call order |

No code may read the private Identity Vault and then pass through a raw vault entry, Canvas ID,
SIS ID, or private setting. All returned student data goes through the existing pseudonym and
outbound safety gates.

## 6. Assistant call behavior

The product guide must teach this sequence:

1. Establish or confirm the current course.
2. If the teacher names pseudonyms, request only those pseudonyms.
3. Call `get_assessment_context` for assessment evidence and coverage.
4. Call existing gradebook/submission/writing tools only when the question needs current work
   or writing evidence.
5. If the teacher asks about tier placement, call the read-only grouping proposal and report
   the method, counts, No Data placement, and coverage result.
6. State whether evidence is current-course mirror data or local longitudinal assessment data.
7. Direct the teacher to the Students UI for any Canvas group change; never imply that the
   assistant applied it.

The assistant must not infer a real name from a pseudonym, merge students because two labels
look similar, or treat a missing assessment row as a statement about ability.

## 7. Acceptance criteria for Batch A

All criteria are executable with synthetic data. A real course is not required and its absence
is not a YELLOW or RED result.

1. A synthetic current roster and synthetic DataForge profile can be joined by pseudonym for a
   single requested student and for a bounded current-roster request.
2. The response reports matched, no-assessment, not-in-roster, and unscoped-history counts
   without exposing identifiers or private paths.
3. Stale/missing roster state withholds all student rows and returns the documented refresh
   instruction.
4. Missing or malformed published profile state is distinct from a valid student with no
   assessment history.
5. A pseudonym rename is reflected through the existing VaultIdentity/history behavior without
   splitting the assessment record or exposing the old label as a second student.
6. The MCP grouping proposal matches the Students UI proposal for synthetic snapshots,
   rosters, group sets, No Data placement, and all supported tiering methods.
7. The proposal contains no Canvas IDs, SIS IDs, submission IDs, private notes, or vault data,
   and it never performs a Canvas write.
8. Tool schema, server registration, `docs/mcp-server.md`, product guide Appendix G, and the
   relevant wrapper tests agree on the same names, arguments, result limits, and privacy rules.
9. Focused synthetic tests cover the happy path, no-match path, stale mirror path, malformed
   profile path, output privacy, token/row bounds, rename continuity, and proposal parity.
10. The named offline gate passes. Live-course coverage, live mirror refresh, and teacher
    first-use review remain deferred until populated classes are available on or after
    2026-08-18; they are not acceptance failures for this batch.

## 8. Required verification

The promoted direct brief must name exact tests and symbols, at minimum:

- `api/mcp_server/tools.py` and `api/mcp_server/server.py` for the new tool;
- `api/dataforge/canvas_join.py`, `grouping.py`, `history_store.py`, and `profile_export.py`;
- `api/tests/mcp_server/test_tools.py` and `test_standards_profile.py`;
- `api/tests/dataforge/test_canvas_join.py`, `test_grouping.py`, and
  `test_history_store.py`;
- `api/tests/webui/routes/test_roster_assessment_groups.py` for proposal parity;
- `docs/mcp-server.md` Tools and Token-lean results sections;
- Appendix G of `api/default_docs/AI Authoring/START HERE - CanvasAgent.txt`;
- `docs/reference/dataforge-route-card.md`, especially One source and one identity boundary,
  MCP read, Grouping and write boundary, and Off-season verification.

Run focused tests first, then the full API suite only if the changed MCP projection crosses
shared privacy or routing code. No live Canvas calls, browser sign-in, real roster, real
assessment export, or external Learning Commons integration belongs in the acceptance gate.

## 9. Explicit non-goals

- No MCP tool that applies Canvas groups or writes grades.
- No automatic teacher/course inference from a pseudonym.
- No course ID added to the published DataForge artifact merely to make the join convenient.
- No second profile, roster, or identity store.
- No raw Eduphoria workbook or full assessment export sent to the assistant.
- No automatic standards remediation plan or AI-generated placement judgment.
- No Learning Commons connector in this batch. Its standards knowledge may inform a later
  product decision, but it is not required to expose CanvasExpert's own student evidence.
- No live-course validation before classes populate; synthetic coverage is the complete current
  acceptance gate.

## 10. Stop and senior-review conditions

Stop and return for senior review if:

- the assistant-facing result requires a Canvas/SIS identifier to be useful;
- the course join cannot distinguish current-roster membership from longitudinal history;
- the published profile cannot be safely filtered or bounded without exposing raw history;
- UI and MCP grouping proposals diverge on synthetic fixtures;
- the design adds a Canvas mutation owner or bypasses the existing review/apply path;
- a stale mirror would have to be accepted to answer a teacher question;
- a new durable contract or identity namespace is required;
- someone proposes treating the lack of a live course as a failed acceptance condition.

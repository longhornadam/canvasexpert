# Direct execution brief: bounded assessment context over MCP

**Status:** Retired — GREEN; accepted 2026-08-03

**Executor:** Luna

**Senior objective:** Add one read-only MCP tool, `get_assessment_context`, so a
teacher can ask about one or a bounded set of current-roster pseudonyms using
local longitudinal DataForge assessment evidence without manually joining the
Students, Assessments, and grade surfaces.

## Required context

Read `AGENTS.md`, `docs/reference/project-state.md`, and only these sections of
`docs/handoffs/senior level/pseudonym-first-assessment-conversations-initiative.md`:

- §1 Teacher outcome
- §2 Why this initiative exists
- §3.1–§3.4 Pseudonym key, roster intersection, freshness, and narrow reads
- §3.6 App reports; it does not judge
- §4.1 `get_assessment_context`
- §5 Data and ownership boundaries
- §6 Assistant call behavior
- §7 acceptance criteria 1–5 and 8–10
- §8 Required verification
- §9 Explicit non-goals
- §10 Stop and senior-review conditions

## Locked decisions

- Public MCP name: `get_assessment_context`.
- Public arguments: `course_id: str`, `pseudonyms: str = ""`.
- `pseudonyms` is a comma-separated filter. Each token is trimmed and
  case-folded for matching; output uses the current canonical pseudonym. Empty
  means the current roster, subject to the row limit. Duplicate filter tokens
  count once.
- Set `MAX_ASSESSMENT_CONTEXT_STUDENTS = 25`. If the requested set or the
  unfiltered current roster exceeds that limit, return a structured limit error;
  never silently truncate students.
- Bound per-student standards evidence to 32 standard entries and each
  `assessed_in` list to 8 labels. If the selected result cannot fit those
  bounds, return a structured limit error rather than silently dropping
  evidence.
- Use the compact `{columns, rows}` table shape for student rows. The columns
  are exactly: `pseudonym`, `assessment_count`, `latest_assessment_date`,
  `latest_percentage`, `weak_standard_codes`, `standards`. `standards` contains
  only the bounded per-standard evidence required by the initiative.
- Return source metadata identifying current roster data as local mirror data
  and assessment data as `scope: "local_longitudinal_history"`, including the
  published profile's `generated`, `grain`, and `snapshots_used` values.
- Return explicit coverage counts for current-roster students with history,
  current-roster students without history, requested pseudonyms not in the
  current roster, and published-profile students not in the current roster.
  Profile-only students are counted but never returned as rows.
- Exact case-folded pseudonym collisions in the current roster or published
  profile are malformed state and must be withheld, not merged.
- A missing, stale, malformed, or inconsistent current roster returns no student
  rows and a structured attention result with `action: "refresh_mirror"`.
  It must not make a live Canvas call.
- Missing, malformed, unsupported, or unsafe published profile state is a
  distinct structured error from a valid current-roster student with no
  assessment history.
- The assessment context is observational only. Do not add capability,
  placement, integrity, remediation, or other judgment labels.
- Do not implement the grouping proposal in this brief. Do not change Canvas
  writes, the Students UI, DataForge grouping rules, or the published profile
  format.

## Authorized scope and insertion points

- `api/mcp_server/tools.py`: add the bounded profile loader/projection and the
  `get_assessment_context` implementation. Reuse the existing course gate,
  mirror freshness seam, pseudonym projection, Identity Vault boundary, and
  outbound safety gate. If the existing standards-profile loader is extracted,
  preserve `get_standards_profile` behavior and its current public shape.
- `api/mcp_server/server.py`: add the MCP wrapper with the locked signature and
  compact serialization.
- `api/tests/mcp_server/test_tools.py` and
  `api/tests/mcp_server/test_standards_profile.py`: add focused synthetic
  coverage for the new implementation and preserved profile behavior.
- `docs/mcp-server.md`: update the tool count/schema version, Tools table, and
  Token-lean results guidance for the new tool.
- `api/default_docs/AI Authoring/START HERE - CanvasAgent.txt`: update Appendix
  G with the exact call sequence, source labels, coverage limits, and
  refresh/no-judgment rules.

Do not modify the user's intentional deletions under `docs/handoffs/`.

## Acceptance criteria

1. Synthetic current mirror roster and synthetic published profile produce the
   correct single-student and bounded current-roster joins by pseudonym.
2. The result contains all four required coverage counts and never exposes
   Canvas IDs, SIS IDs, raw names, vault mappings, private paths, or workbook
   contents.
3. Stale, missing, malformed, or internally inconsistent roster state returns
   no student rows, includes `action: "refresh_mirror"`, and makes zero live
   Canvas calls.
4. Missing/malformed/unsupported/unsafe profile state is distinct from a valid
   profile with no matching history for a current-roster student.
5. Filter matching is exact after trim and case-folding; fuzzy or name-based
   matching is absent. Requested non-roster pseudonyms are counted only.
6. Student and standards limits are deterministic and return explicit limit
   errors rather than truncating students or evidence silently.
7. The result is observational and labels longitudinal source scope and profile
   metadata without making course-attribution claims.
8. Existing `get_standards_profile` tests and behavior remain green.
9. Tool registration, wrapper tests, MCP docs, Appendix G, and result schema
   agree on the same name, arguments, limits, and privacy rules.
10. Run only synthetic/offline tests. Do not use a real workspace, real roster,
    live Canvas, browser sign-in, external AI, or external assessment export.

## Named verification gate

```powershell
py -m pytest api/tests/mcp_server/test_tools.py api/tests/mcp_server/test_standards_profile.py -p no:randomly
```

Run the focused DataForge tests only if the implementation changes one of the
existing DataForge seams; otherwise do not broaden the gate. Report the exact
test command and counts.

## Stop conditions

Stop and return YELLOW/RED without guessing if the current mirror or profile
shape does not support the locked projection, a privacy-safe result requires a
new identity namespace, a live Canvas fallback appears necessary, the profile
format must change, or another subsystem/public contract must change outside
this scope.

## Execution result

Traffic light: GREEN

Commit hash: none; no commit was created.

Implemented the complete bounded `get_assessment_context` slice with synthetic/offline
coverage. The result uses the current local mirror roster as its denominator, joins the
published learning-standard profile by exact case-folded pseudonym, returns the locked
compact columns and four coverage counts, enforces the 25/32/8 limits without truncation,
and routes successful payloads through the existing pseudonym and outbound safety gates.
Stale/missing/malformed/inconsistent roster state returns no rows with
`attention.action = "refresh_mirror"`; missing/malformed/unsupported/unsafe profile
states are distinct structured errors. `get_standards_profile` behavior remains green.

Targeted senior repair completed: profile validation now rejects NaN/Infinity,
percentages/means/latest values outside 0..100, duplicate weak-standard codes, and
weak-standard lists larger than the 32-entry evidence bound. Roster validation now
rejects malformed raw student values, non-dict sections, non-list projected output,
and non-dict projected rows before they can be used.

Changed files:

- `api/mcp_server/tools.py`
- `api/mcp_server/server.py`
- `api/mcp_server/contract.py`
- `api/mcp_server/tool_schema_v27.json`
- `api/tests/mcp_server/test_tools.py`
- `api/tests/mcp_server/test_standards_profile.py`
- `api/tests/test_beta075_mcp.py`
- `docs/mcp-server.md`
- `api/default_docs/AI Authoring/START HERE - CanvasAgent.txt`
- this brief's execution result

Verification:

- `py -m pytest api/tests/mcp_server/test_tools.py api/tests/mcp_server/test_standards_profile.py -p no:randomly` — 122 passed.
- `py -m pytest api/tests/test_beta075_mcp.py -p no:randomly` — 7 passed.
- `git diff --check` — passed.

Intentional user deletions under `docs/handoffs/` were preserved. No grouping proposal,
Canvas write, live Canvas call, real workspace, browser sign-in, external AI, or real
assessment data was used.

Deviations: the public MCP registry gained its required versioned schema snapshot (`v27`)
and the existing schema-law test was updated from 43 to 44 tools; no product scope was
expanded.

Unresolved decisions: none.

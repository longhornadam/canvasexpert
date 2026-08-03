# Direct execution brief: pseudonym-safe assessment grouping proposal over MCP

**Status:** Retired — GREEN; accepted 2026-08-03

**Executor:** Luna

**Senior objective:** Add one read-only MCP tool,
`get_assessment_grouping_proposal`, that exposes the existing Students-page
assessment grouping proposal as a bounded pseudonym-only projection. The teacher
can inspect the proposal conversationally, but the teacher reviews and applies
any Canvas group change in the existing Students UI.

## Required context

Read `AGENTS.md`, `docs/reference/project-state.md`, and only these sections of
`docs/handoffs/senior level/pseudonym-first-assessment-conversations-initiative.md`:

- §1 Teacher outcome
- §2 Why this initiative exists
- §3.1 Pseudonym is the conversation key
- §3.2 Current-course scope is the roster intersection
- §3.3 Freshness is fail-closed
- §3.5 MCP remains read-only with respect to Canvas
- §3.6 The app reports; it does not judge
- §4.2 `get_assessment_grouping_proposal`
- §5 Data and ownership boundaries
- §6 Assistant call behavior
- §7 acceptance criteria 6–10
- §8 Required verification
- §9 Explicit non-goals
- §10 Stop and senior-review conditions

## Locked decisions

- Public MCP name: `get_assessment_grouping_proposal`.
- Public arguments: `course_id: str`, `snapshot_id: str`,
  `method: str = "overall_pct"`, `cutoffs: str = ""`,
  `no_data_group: str = ""`, `group_set_label: str = ""`.
- `snapshot_id` is the exact trimmed local history snapshot identifier. The
  selected snapshot is read offline from DataForge history.
- `group_set_label` is the teacher-facing Canvas group-category label, matched
  after trim and case-folding. It is the only group-set selector exposed to the
  assistant. Missing or duplicate labels are structured errors; raw category
  and group IDs are never accepted from or returned to the assistant.
- Preserve the existing grouping method/cutoff semantics by calling
  `api.dataforge.grouping.build_grouping_proposal`. Do not reimplement tier
  rules, quartiles, STAAR bands, No Data behavior, or proposal digest logic in
  the MCP wrapper.
- Reuse `api.dataforge.canvas_join.build_coverage_report` for the internal
  roster/history coverage join. Internal Canvas/SIS IDs and names may be used
  only inside the local service boundary and must be removed before the MCP
  result is safety-gated or returned.
- The safe proposal includes source metadata, method, cutoffs, the selected
  teacher-safe group-set label, No Data placement, exact coverage counts/status,
  the existing `proposal_digest`, group names/counts/pseudonym membership, and
  one placement row per current-roster student with pseudonym, score, status,
  and group. It contains no display names, Canvas IDs, SIS IDs, submission IDs,
  category IDs, group IDs, vault data, private paths, or raw workbook data.
- Return the existing private proposal digest as a non-sensitive review
  identity; do not expose the private proposal that was hashed.
- Require a Current course, a current local roster mirror, and a current local
  group mirror. Missing/stale/malformed state returns no proposal rows and no
  live Canvas fallback.
- Run the final safe payload through the existing pseudonym/outbound safety
  gates before returning it. The result reports source facts and grouping
  inputs; it never labels ability, integrity, capability, remediation, or
  placement beyond the explicitly selected method and its resulting group.
- This slice adds no Canvas write, no MCP apply tool, no new identity namespace,
  no new grouping algorithm, and no change to the Students UI or `/api/roster/bulk`.

## Authorized scope and insertion points

- `api/mcp_server/tools.py`: add the offline grouping-source loader, safe
  projection, and `get_assessment_grouping_proposal`. Reuse the existing course
  gate, mirror read/freshness seams, `VaultIdentity`, DataForge path/history
  services, `canvas_join`, `grouping`, and outbound safety gate.
- `api/mcp_server/server.py`: add the compact MCP wrapper with the locked
  signature.
- `api/mcp_server/contract.py`, the next versioned
  `api/mcp_server/tool_schema_v*.json`, and
  `api/tests/test_beta075_mcp.py`: advance the public schema snapshot and its
  law test for the one additional read tool.
- `api/tests/mcp_server/test_tools.py`: synthetic happy path, missing/stale
  sources, label resolution, all supported methods, no-data placement, privacy,
  and parity assertions.
- `api/tests/mcp_server/test_standards_profile.py` only if the shared profile or
  safety helper changes; otherwise preserve it and run it as part of the gate.
- `api/tests/webui/routes/test_roster_assessment_groups.py`: run the existing
  Students proposal tests and add only a synthetic parity fixture/assertion if
  the shared seam requires it.
- `docs/mcp-server.md`: update schema version/count, Tools table, and the
  grouping/read-only sections.
- `api/default_docs/AI Authoring/START HERE - CanvasAgent.txt`: update Appendix
  G with the proposal call, method/cutoff/No Data reporting, digest/review
  boundary, and Students-UI-only apply instruction.

Do not modify the user's intentional deletions under `docs/handoffs/`.

## Acceptance criteria

1. A synthetic current roster, synthetic current group mirror, synthetic
   identity mapping, and synthetic DataForge snapshot produce a proposal for
   `overall_pct`, `staar_bands`, and `quartiles` using the existing grouping
   engine.
2. The MCP projection matches the Students UI proposal on method, cutoffs,
   No Data placement, roster/matched/no-data counts, tier names/counts,
   pseudonym membership, and `proposal_digest` for shared synthetic fixtures.
3. Group-set label selection is exact after trim/case-folding and rejects
   missing or duplicate labels without accepting raw IDs.
4. Missing, stale, malformed, or internally inconsistent roster/group mirrors,
   missing snapshots, invalid methods/cutoffs, invalid group sets, and missing
   identity state return structured blocking errors with no proposal rows.
5. The result contains no Canvas IDs, SIS IDs, display names, submission IDs,
   category/group IDs, private notes, vault values, private paths, or raw
   assessment exports; the outbound safety gate is green on the returned safe
   projection.
6. The tool never calls Canvas and never invokes `/api/roster/bulk`, applies a
   group, writes a group, or implies that a Canvas change was applied.
7. Tool registration, versioned schema, wrapper tests, MCP docs, Appendix G,
   and the current Students route contract agree on the same public behavior.
8. Run only synthetic/offline tests. No real workspace, real roster, live
   Canvas, browser sign-in, external AI, or real assessment data is permitted.

## Named verification gate

```powershell
py -m pytest api/tests/mcp_server/test_tools.py api/tests/mcp_server/test_standards_profile.py api/tests/webui/routes/test_roster_assessment_groups.py api/tests/test_beta075_mcp.py -p no:randomly
```

Run the focused DataForge tests if the implementation changes either pure
DataForge seam; otherwise do not broaden the gate. Report exact commands and
counts, plus `git diff --check`.

## Stop conditions

Stop and return YELLOW/RED without guessing if parity requires changing the
Students UI's grouping rules, a safe result cannot omit raw IDs/names, a live
Canvas call or write path appears necessary, group-set labels are not unique
enough to resolve safely, a new identity namespace is proposed, or any public
contract outside this scope must change.

## Execution result

Traffic light: GREEN

Commit hash: none; no commit was created.

Implemented the complete read-only `get_assessment_grouping_proposal` slice.
The MCP tool requires a Current course, current local roster/group mirrors, an
exact trimmed local history snapshot ID, and a unique teacher-facing group-set
label matched after trim/case-folding. It reuses `canvas_join.build_coverage_report`
and `grouping.build_grouping_proposal`, returns the existing private
`proposal_digest`, and projects groups/placements to pseudonyms, scores, status,
counts, and group names only. It has no Canvas client, `/api/roster/bulk`, apply,
or write path. Missing/stale/malformed/ambiguous sources and invalid inputs
return structured errors with no proposal rows. The result is bounded to 25
placements and 20,000 serialized characters, then passes the existing outbound
safety gate before placement tabulation.

Changed files for this slice:

- `api/mcp_server/tools.py`
- `api/mcp_server/server.py`
- `api/mcp_server/contract.py`
- `api/mcp_server/tool_schema_v28.json`
- `api/tests/mcp_server/test_tools.py`
- `api/tests/test_beta075_mcp.py`
- `docs/mcp-server.md`
- `api/default_docs/AI Authoring/START HERE - CanvasAgent.txt`
- this brief's execution result

Verification:

- `py -m pytest api/tests/mcp_server/test_tools.py api/tests/mcp_server/test_standards_profile.py api/tests/webui/routes/test_roster_assessment_groups.py api/tests/test_beta075_mcp.py -p no:randomly` — 140 passed.
- `git diff --check` — passed.

Synthetic/offline only. No real workspace, live Canvas, browser sign-in,
external AI, real roster, or real assessment data was used. Intentional
deletions under `docs/handoffs/` and accepted Slice 1 changes were preserved.

Deviations: advanced the public schema from v27 to v28 for the additional tool;
the safe group projection uses `group_name` rather than a `name` key because the
shared outbound safety law blocks identity-bearing `name` keys. No UI grouping
rule or public write contract changed.

Unresolved decisions: none.

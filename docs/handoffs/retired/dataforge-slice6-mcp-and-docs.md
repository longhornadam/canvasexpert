# DataForge Slice 6 — MCP and documentation integration

## Status

Retired GREEN. The senior accepted Slices 1–5 before execution; this final
planned DataForge merge slice is now accepted GREEN.

## Objective

Expose the published, pseudonymized DataForge standards profile through one
read-only local MCP tool and fold the teacher-facing DataForge workflow into the
durable MCP, route-card, and product-guide documentation.

## Required context

- `AGENTS.md`
- `docs/reference/project-state.md`
- `docs/handoffs/senior level/dataforge-merge-initiative.md`, sections 5.1, 6, 7, 9, and 11
- `docs/mcp-server.md`
- `api/mcp_server/contract.py`
- `api/mcp_server/server.py`
- `api/mcp_server/tools.py`
- `api/dataforge/paths.py`
- `api/dataforge/profile_export.py`
- `api/feedback_safety.py`
- `api/feedback_vault.py`
- `api/default_docs/AI Authoring/START HERE - CanvasAgent.txt`

## Locked decisions

- The tool is named `get_standards_profile` and reads only the published local
  `For AI/DataForge/standards-profile.json` artifact.
- The tool is read-only, has no `course_id`, performs no Canvas request, and does
  not create or migrate identity records.
- The artifact remains pseudonymized, not anonymous. Run the existing feedback
  safety scan before returning it; block a non-green payload without exposing the
  offending value or private filesystem path.
- Missing or malformed artifacts return a structured, actionable error rather
  than a traceback. Do not add a dependency or a second profile format.
- The MCP schema/version documentation, route card, and canonical product guide
  must describe the same behavior and the review-first grouping workflow.
- All verification uses synthetic profiles and temporary workspaces. No test may
  require an active or real Canvas course.

## In scope

- Implement the MCP tool and its server registration/export.
- Update the MCP contract/schema snapshot and `docs/mcp-server.md`.
- Add the durable DataForge route card under `docs/reference/`.
- Update the canonical `START HERE - CanvasAgent.txt` guide with the DataForge
  assessment/profile/grouping path and privacy wording.
- Add focused tests for successful, missing, malformed, and safety-blocked profile
  reads, plus the product-guide/tool-contract assertions required by the existing
  MCP test style.

## Explicit non-goals

- No Canvas transport, course discovery, live-course fixture, or Canvas mutation.
- No profile generation changes, new identity provider, new storage, or new
  persistence format.
- No changes to grouping semantics or the existing roster bulk-apply transport.
- No broad MCP refactor and no unrelated documentation cleanup.

## Acceptance criteria

1. `get_standards_profile` returns the published profile for a valid synthetic
   artifact after the existing safety scan passes.
2. Missing, malformed, wrong-format, and safety-blocked artifacts produce stable
   structured errors with no raw path, ID, name, or offending value in the result.
3. The tool is registered in the MCP server/schema without a Canvas call, a
   `course_id` parameter, or a new dependency; existing MCP tools remain green.
4. `get_product_guide` exposes the updated canonical guide and the guide names
   Assessments/profile import, coverage, review-first grouping, Identity Vault,
   and the pseudonymized-not-anonymous boundary.
5. Durable docs state one DataForge profile source, offline/local operation, the
   teacher review step before grouping apply, and the absence of automatic Canvas
   writes.
6. The named gate passes:

   ```powershell
   py -m pytest api/tests/mcp_server api/tests/dataforge -p no:randomly
   ```

   and the full API suite passes afterward. Rendered checks are not required for
   this docs/MCP-only slice; the Assessments and roster routes were rendered and
   accepted GREEN in Slice 5 and are unchanged in behavior here.

## Stop conditions

- Stop RED if the existing MCP registration/schema mechanism cannot add the tool
  without changing an unrelated public contract, or if the profile artifact does
  not have the locked format/source.
- Stop RED if a safety scan cannot guarantee that blocked payloads do not expose
  the offending private value.
- Stop YELLOW only for an unavailable named gate or a bounded documentation
  decision that requires senior direction.

## Execution result

Traffic light: GREEN.

Commit hash: none; the worktree contains the user's existing uncommitted DataForge
merge work and this slice was kept in that worktree.

Changed files: added `get_standards_profile` and the v26 MCP schema snapshot;
updated MCP wiring, contract tests, the canonical CanvasAgent guide, and
`docs/mcp-server.md`; added `docs/reference/dataforge-route-card.md` and
`docs/guides/dataforge-assessments.md`; added synthetic profile/safety tests.

Verification:

- `py -m pytest api/tests/mcp_server api/tests/dataforge -p no:randomly` — 257 passed.
- `py -m pytest api/tests` — 2083 passed.
- MCP live registry/schema parity and canonical guide appendix routing passed.
- No active or real Canvas course was used or required; profile, malformed,
  safety-block, and documentation checks use synthetic/offline state.

Deviations: none. Unresolved decisions: none.

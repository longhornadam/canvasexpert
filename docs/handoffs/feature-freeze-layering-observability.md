# Direct execution brief: approved layering, diagnostics, and library-source batch

**Status:** Retired — GREEN  
**Owner:** senior / Luna executor  
**Risk:** high  
**Target branch:** `dev`

## Objective

Implement the senior's approved follow-through from the feature-freeze initiative:

- defer the OpenRouter decision;
- log an aggregate count for MCP soft safety flags without changing the MCP schema or
  returning flagged names;
- make quiz, assignment, page, and rubric pickers read only from their synced Library
  folders;
- add operational logging at the highest-value mirror-refresh and operation-ledger write
  boundaries;
- promote C1 platform layering and C2 private-import cleanup.

The app must retain its existing behavior and safety boundaries. This batch changes module
ownership and diagnostics, not teacher-facing workflow semantics or Canvas contracts.

## Required context

Read `AGENTS.md`, `docs/reference/project-state.md`, and only these sections of
`docs/handoffs/senior level/feature-freeze-hardening-initiative.md`: §2.3, §3 A5,
§4 B1, §5 C1-C2, §6 D1, §7, §8, and §10.

## Locked decisions

- OpenRouter remains unchanged; its future is deferred.
- A5 is log-only. The MCP gate may emit an aggregate `count` for non-empty soft flags,
  using the existing allowlisted operational-log fields. It must not emit names, paths,
  payload text, or a schema notice. Soft flags remain non-blocking.
- D1.4 applies the synced-Library-only rule to `Quizzes`, `Assignments`, `Pages`, and
  `Rubrics`. Bundled `api/qf_materials` examples are not picker sources. An unconfigured
  workspace yields an empty picker, not a repository fallback.
- B1 is limited to the highest-value boundaries: mirror refresh outcomes and operation-ledger
  write/apply outcomes. Use existing event/outcome vocabulary and allowlisted keys; do not
  add operational-log fields.
- C1 creates `api/platform_services/` as the owner of `workspace`, `config`, and `canvas_client`.
  Update callers directly and remove the old `api.webui` ownership; do not add compatibility
  re-export shims because the project is pre-launch and has no legacy state to preserve.
- C2 promotes the eight documented cross-package private-import seams to public names and
  updates all callers/tests. C3 and C4 remain diagnostic only and receive no implementation.

## Authorized scope

- `api/platform_services/` (new package containing the moved platform modules)
- the removal of the old `api/webui` platform owners as part of the clean move
- all production and test import sites that must follow the C1/C2 ownership changes
- `api/feedback_safety.py`, `api/mcp_server/pseudonym.py`, `api/operational_log.py`, and
  their focused tests for the A5 counter
- `api/runtime_paths.py`, picker consumers, and focused tests for D1.4
- the existing mirror-refresh and operation-ledger write/apply owners plus focused tests for B1
- `docs/handoffs/senior level/feature-freeze-hardening-initiative.md` status/pointer/open-item
  corrections only
- this brief's `Execution result` only

Do not remove OpenRouter, change MCP schemas, alter Canvas write semantics, implement C3/C4,
or touch unrelated work.

## Acceptance criteria

1. Production and test code imports platform services from `api.platform_services`; no live import
   depends on the removed `api.webui` ownership, and the moved modules do not import the
   FastAPI web package merely to load.
2. The eight C2 private imports are replaced by public owning-module names, with no private
   cross-package import left at those seams.
3. An MCP soft-flag result remains `{ok: true, ...payload}` and produces only an aggregate
   operational record; no name, path, or payload text is logged.
4. All four picker kinds use only their current Library folder and return no bundled examples
   when the workspace is unconfigured.
5. Highest-value mirror refresh and operation-ledger write/apply outcomes emit validated,
   privacy-minimized records without changing control flow or write behavior.
6. Existing focused behavior remains green, import cycles are absent, and the packaging/import
   smoke check succeeds.
7. The feature-freeze senior handoff no longer points to deleted briefs or lists completed D4
   work as an unresolved decision; its next pointer names the deferred C decision and the
   remaining A5/D1.4/B1/OpenRouter work accurately.

## Named verification gate

```powershell
py -m pytest api/tests/test_feedback_safety.py api/tests/test_beta075_imports.py api/tests/test_beta075_runtime.py api/tests/test_workspace_pin.py api/tests/webui/test_workspace.py api/tests/webui/test_canvas_client.py api/tests/test_mirror_reads_helper.py api/tests/mirror/test_sync.py api/tests/test_operation_routes.py api/tests/test_push_routes.py -p no:randomly
```

Then run the full API suite because C1 crosses the application import graph:

```powershell
py -m pytest api/tests -q -p no:randomly
```

Also run `python -m compileall -q api` and a clean import smoke check for the moved platform
modules. Report exact commands and counts.

## Stop conditions

Stop RED if a platform move requires a public route/schema change, an import cycle cannot be
resolved locally, a packaged import fails, or a log record would contain student data. Stop
YELLOW if the focused gate passes but the full suite or packaging check is unavailable.

## Execution result

Traffic light: GREEN

Commit hash: recorded in the implementation commit that includes this brief.

Implemented the approved batch. Platform ownership moved from `api.webui` to the new
`api.platform_services` package, all production/test/tool importers were migrated, and the
eight C2 private seams now use public owning-module names. The first package name (`api/platform`)
was rejected during entrypoint smoke because it shadowed Python's standard-library `platform`;
the final `api/platform_services` name avoids that collision. MCP soft flags remain non-blocking
and now emit only an aggregate `count`; all four material pickers use synced Library folders;
mirror refresh and operation-ledger write/apply outcomes emit allowlisted operational records.

Changed files: platform move and import graph, C2 owning modules/callers/tests, A5/D1.4/B1
owners and focused tests, Canvas transport ownership contract, architecture references,
senior initiative pointer, this brief, and retirement of the prior Home Calendar brief.

Verification:

- Named gate: 144 passed.
- Full API suite: 2,198 passed, 1 pre-existing failure in
  `api/tests/test_presentation_contracts.py::test_migrated_feature_css_consumes_shared_visual_tokens`
  for unchanged `api/webui/static/pages/calendar.css`; the same failure reproduced at baseline
  `7ceb136`.
- `py -m compileall -q api`: passed.
- Platform/server/MCP import smoke and `api/diagnose_newquizzes.py --help`: passed.
- `engine/tests/unit/test_text_utils.py` plus affected tool tests: 20 passed.

Deviations: `api/platform` became `api/platform_services` after the standard-library shadowing
hazard was found in the CLI entrypoint smoke test. No OpenRouter removal, MCP schema change,
Canvas write change, C3/C4 implementation, or compatibility shim was added.

Unresolved decisions: OpenRouter's future remains deferred; C3/C4 remain diagnostic-only.

# Slice A — get_modules MCP read tool

Status: **ACTIVE — ready for the executor**

Part of the author-and-stage feature (docs/reference/author-and-stage-overview.md). This is
Slice A: the smallest, fully independent piece. It lets any MCP-capable assistant see a
course's module structure so it can place authored content in the right module. No other
slice depends on this one, and this one depends on nothing.

## Objective

Add a read-only `get_modules(course_id, include_items=False)` MCP tool that serves the
local course catalog's module structure, and bump the tool schema to v5. No Canvas fetch,
no student data, no write path.

## Assistant-visible outcome

An assistant can call `get_modules(course_id)` and receive the course's modules as a
compact `{columns, rows}` table (id, name, position, published, item_count). With
`include_items=true`, each module also carries its items as a nested `{columns, rows}`
table (id, type, title, position). This is enough for the assistant to name a target
module when it later stages content for the teacher to push.

## Locked decisions

1. Read-only and non-PII. Modules and module items are structural (module names, item
   titles like "Unit 3 Quiz"), the same class of data already exposed by
   `get_course_assignments`. So `get_modules` skips the identity vault and the outbound
   safety gate, exactly as `get_course_assignments` does. It still applies the standard
   Current-course gate (`_course_gate_check` against `config.active_courses()`).
2. Local catalog only, never a live Canvas fetch. Read through
   `read_service.catalog_modules(course_id)`. There is no live fallback in this tool.
3. Staleness is labeled, not refused. Modules are not refreshed on the sync heartbeat
   (only on demand or marked stale after an apply), so unlike the student-data tools this
   tool returns the records it has and labels freshness (`source`, `synced_at`, and the
   catalog `state`) rather than refusing. If the catalog is genuinely absent, return a
   structured `{"ok": false, "error": ...}` naming the missing catalog, consistent with
   `get_course_assignments`. Rationale: structural data carries far lower risk than student
   data, and an assistant choosing a module name needs the shape, not a freshness guarantee.
4. Token-lean by default. Default `include_items=False` returns the module list only
   (names plus counts), the common need for placement. `include_items=True` opts into the
   nested item detail. This mirrors the existing `full_descriptions` / `include_text`
   conventions.
5. Concision is a requirement, not a preference. The tool description follows the surface's
   standard: a functional line or two, no restatement of the shared rules that already live
   in the server instruction block. Use exactly:

       """A course's modules from the local catalog as a {columns, rows} table
       (id, name, position, published, item_count). include_items=true adds each
       module's items (id, type, title, position). No student data."""

## Scope

Expected owners:

- `api/mcp_server/tools.py` — new `get_modules` implementation returning a
  `{"ok": ...}` dict, tabulated with the existing `_tabulate` helper; module-item columns
  as a module-scoped constant.
- `api/mcp_server/server.py` — new `@mcp.tool()` wrapper with the concise docstring above.
- `api/mcp_server/tool_schema_v5.json` — new frozen contract: the seven current tools plus
  `get_modules`. `api/mcp_server/contract.py` — `TOOL_SCHEMA_VERSION = 5` and
  `_SUPPORTED_SCHEMA_VERSIONS = (1, 2, 3, 4, 5)`. Leave v1-v4 untouched.
- `api/tests/test_mcp_server_tools.py` — coverage for `get_modules`. `api/tests/` contract
  test — update to v5.
- `docs/mcp-server.md` — add the `get_modules` row to the tool table and bump the stated
  schema version.
- Do not modify Roster, Seating, CanvasMirror, Connections, the operation ledger, or any
  student-data tool.

## Required context

Read only:

1. AGENTS.md
2. This brief in full, and docs/reference/author-and-stage-overview.md
3. `api/mcp_server/tools.py` (the tool pattern, `_tabulate`, `_course_gate_check`, and how
   `get_course_assignments` handles a missing local catalog without a vault or gate)
4. `api/mcp_server/server.py` (wrapper pattern, `_compact`, the instruction block)
5. `api/course_catalog.py` module shape (`_normalize_module_item`) and
   `api/mirror/read_service.py::catalog_modules` (envelope: `state`, `records`,
   `last_success_at`)
6. `api/mcp_server/contract.py` and an existing `tool_schema_v*.json` for the frozen-contract
   format

## Preflight — stop if false

- `read_service.catalog_modules(course_id)` returns modules with `{id, name, position,
  items:[{id, type, title, position, content_id}]}` and a freshness envelope, with no
  Canvas call.
- A published/`item_count` value is derivable from the catalog record without a new fetch
  (if `published` is not stored, omit that column rather than fetching it).
- The contract test compares the live registry to the frozen schema for the current
  version, so adding a tool requires the v5 fixture to stay green.

## Acceptance criteria

1. `get_modules(course_id)` returns `{"ok": true, ...}` with a `{columns, rows}` module
   table and freshness labels (`source`, `synced_at`), no vault or safety-gate invocation.
2. `include_items=true` adds each module's items as a nested `{columns, rows}` table;
   default omits them.
3. A non-active course is rejected by the course gate with a structured error; an absent
   local catalog returns a structured error naming the missing catalog.
4. Stale-but-present catalog data is returned with a staleness label, not refused.
5. Schema is v5: `tool_schema_v5.json` lists eight tools, `TOOL_SCHEMA_VERSION == 5`, v1-v4
   unchanged, and the contract test passes.
6. The tool description is the exact concise string in Locked decision 5. No shared-rule
   boilerplate repeated from the instruction block.
7. docs/mcp-server.md lists `get_modules` and states schema v5.

## Verification gate

Run from repository root:

    py -m pytest api/tests/test_mcp_server_tools.py api/tests/test_beta075_mcp.py

Confirm the live contract matches the v5 fixture and all `get_modules` cases pass. No live
Canvas call, no student data, no network binding.

## Explicit non-goals

- No live Canvas fetch, no fallback path, and no on-demand catalog refresh from this tool
  (the teacher's existing refresh owns that).
- No student data, no vault, no safety gate, no pseudonymization.
- No write path of any kind. No change to any other tool, the instruction block's shared
  rules, or the operation ledger.
- No module authoring, reordering, or placement action; this slice only reads.

## Stop conditions

- Module data cannot be read from the local catalog without a Canvas call.
- Exposing module item titles would require the identity vault (i.e. they are not
  structural after all).
- The v5 contract bump would force a change to a frozen prior-version schema.

## Execution result

Done. `get_modules(course_id, include_items=False)` added in `tools.py` (course-gated,
catalog-only, no vault or safety gate; returns a `{columns, rows}` module table with
`source`/`synced_at`/`state` labels; stale-but-present returns labeled records, absent
catalog returns a structured error; `include_items` nests each module's items;
`published` column emitted only when the catalog record carries it). Wrapper added in
`server.py` with the exact concise docstring. Schema bumped to v5 (`tool_schema_v5.json`,
`contract.py`); v1-v4 untouched. Tests added in `test_mcp_server_tools.py`; contract test
in `test_beta075_mcp.py` updated to v5/8 tools with a v4-immutability check.
Verification gate green (55 passed). Implemented by a Sonnet subagent, verified by the
senior agent.

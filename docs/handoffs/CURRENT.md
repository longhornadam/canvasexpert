# Route MCP roster and submission helpers through typed local scopes

> **DEEPSEEK EXECUTION AUTHORITY.** Read `AGENTS.md`, this file, and only the references
> routed below. Do not read `NEXT_BATCH.md`, `HANDOFF_TEMPLATE.md`, or `archive/`.

Status: **READY**

Risk: **high** - MCP returns pseudonymized private student information outside the app process;
wire allowlists, safety scanning, course gates, and vault behavior must remain exact.

Depends on: commit `ae69f26` (accepted 04 routine typed-read SDK)

## Teacher-visible result

MCP tools retain the same compact payloads and privacy gates while their local roster and
assignment-submission acquisition uses the typed read service instead of direct mirror
store/query ownership. Stale state still falls back live.

## Acceptance criteria

- [ ] `_mirror_roster_doc` (rename allowed) uses `read_service.private_roster` with the configured
      serve-age bound and preserves the existing monkeypatch/cache guard.
- [ ] `_mirror_submission_bundle` reads typed roster, assignments, and submissions once each,
      requires all three current, filters the requested assignment locally, and uses the minimum
      required `last_success_at` as the unchanged `synced_at` value.
- [ ] Current local roster/submission tools make zero Canvas calls; any missing/stale/corrupt
      required scope falls back through the existing live/vault path as one coherent bundle.
- [ ] Tool names, JSON schemas, columns, truncation, course gate, pseudonym mapping, vault
      transaction/conflict behavior, outbound scan, and structured errors remain unchanged.
- [ ] `get_gradebook_snapshot` continues to use shared `gradebook_snapshot.load_snapshot`; do not
      duplicate or rewrite that use case in MCP.
- [ ] No `mirror_store`/`mirror_queries` import remains in MCP tools if caller proof shows none.
- [ ] The named acceptance gate passes.

## Explicit non-goals

- Tool/schema version changes, new response fields (including generation), comment payloads,
new caching, derived views, writes, tunnel/client configuration, or gradebook snapshot refactor.

## Locked decisions

- Preserve every module-level monkeypatch seam (`_course_*`, `_assignment*`, `_fetch_sections`)
  and `_cache_safe` behavior. Patched tests remain on live fakes and never cross-call cache data.
- Typed envelopes are internal only. MCP output remains `source` plus `synced_at`; generation is
  neither emitted nor cached in this slice.
- Continue pseudonymizing/gating dict rows before tabulation and trimming text before the gate.
- Remove imports/helpers only when the focused tests prove their last caller migrated.

## Scope

- `api/mcp_server/tools.py`
- `api/tests/test_mcp_server_tools.py`
- `api/tests/test_beta075_mcp.py`
- `docs/mcp-server.md`: local-read/source description only

## Read only these references

- `AGENTS.md`; this promoted brief
- `docs/mcp-server.md`: introduction, Tools, and Token-lean results
- `docs/reference/canvasmirror-1.0beta-information-spine.md`: §11.9 and Former Program 8's MCP
  bullet only
- `api/mirror/read_service.py`: private roster/assignment/submission readers
- exact files under Scope

Do not read archived handoffs, MCP client setup sections, unrelated privacy modules, or the
whole vision document.

## Preflight - stop if these facts are false

```powershell
rg -n "mirror_queries|mirror_store|def _mirror_roster_doc|def _mirror_submission_bundle|def _load_snapshot" api/mcp_server/tools.py
rg -n "def get_roster|def get_submissions|def get_gradebook_snapshot|pseudonym.gate|_tabulate" api/mcp_server/tools.py
rg -n "cache_safe|zero|mirror|scan_payload|columns" api/tests/test_mcp_server_tools.py
```

- MCP still owns two direct mirror compatibility helpers and the output/privacy seams are tested.
- Shared gradebook snapshot already owns its local-first behavior.

## Named acceptance gate

```powershell
py -m pytest api/tests/test_mcp_server_tools.py api/tests/test_beta075_mcp.py -q
```

- Add typed zero-live and stale-required-scope fallback assertions without weakening existing PII
  sweep tests. No broad suite or live MCP client invocation.

## Stop conditions

- **RED:** typed migration requires changing an outbound allowlist, safety scan, vault behavior,
  or tool schema.
- **YELLOW:** an established monkeypatch seam cannot be preserved without a compatibility helper;
  retain it and report the exact test/caller.

## Execution result

Record traffic light, changed files, focused command/count, privacy assertions, deviations,
unresolved decisions, and commit hash if created.

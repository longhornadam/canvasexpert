# Execution brief: retire dead roster tier-scheme HTTP endpoints

Status: **ready for implementation**

Risk: **low**

Executor: **external VS Code agent**

## Outcome

Canvas Expert exposes only the current Roster V3 group-management HTTP surface. The
unused V2 `GET` and `POST /api/roster/tier-scheme` endpoints and their endpoint-only
tests are removed, while PowerGrader continues reading the existing private,
synced tier-scheme configuration exactly as it does today.

This is a small, evidence-backed retirement batch from the canonical Workbench audit.
It trims a dead standalone API surface without changing teacher workflows, stored data,
or PowerGrader's tier-map behavior.

## Locked decisions

- Delete `GET /api/roster/tier-scheme` and `POST /api/roster/tier-scheme`. They have
  no browser, template, routine, or CLI caller in the current repository. This
  local-only app has no supported external HTTP-client contract for these endpoints.
- Retain all tier-scheme configuration and PowerGrader behavior. In particular, do
  **not** modify or delete `config.get_roster_tier_scheme`,
  `config.set_roster_tier_scheme`, `config.roster_tier_by_id`,
  `roster_tier_schemes` in synced settings, or PowerGrader callers of the tier map.
- Do not migrate tier-scheme data to Canvas groups in this batch. That is a separate
  product/behavior decision.
- This is a route-surface deletion, not a test-count exercise. Delete only tests whose
  sole observable behavior is the removed HTTP endpoint. Keep configuration-level
  regression evidence.
- `/api/tier-tags` is an active Settings feature and is explicitly out of scope.

## Scope

- In `api/webui/routes/roster.py`, remove the V2 tier-scheme route documentation and
  the two endpoint handlers `get_tier_scheme` and `save_tier_scheme`.
- In `api/tests/test_roster_routes.py`, remove only the five endpoint-specific
  `test_tier_scheme_*` tests for the deleted HTTP routes.
- In `api/tests/test_route_contract.py`, remove the two
  `/api/roster/tier-scheme` GET/POST entries from `EXPECTED`.
- Update `docs/reference/roster-module-map.md` so `roster.py` no longer claims to own
  tier-scheme route flow; it remains the owner of Roster V3 route orchestration.
- Update `docs/reference/workbench-canonical-flow-map.md`: mark this batch completed,
  record the retained configuration/PowerGrader boundary, and leave the Quiz streaming
  investigation gate unchanged.
- Archive the completed audit brief
  `docs/handoffs/workbench-canonical-flow-audit.md` under `docs/handoffs/archive/`
  as part of this closure batch. Do not edit its recorded execution result.

## Out of scope

- Do not edit `api/webui/config/roster.py`, `api/webui/config/_io.py`,
  `api/webui/config/__init__.py`, `roster_helpers.py`, any PowerGrader file, or any
  persisted `roster_tier_schemes` data.
- Do not remove V2 data-migration helpers merely because they have no current caller.
- Do not change Roster V3 Canvas group operations, gradebook extra-time behavior,
  Settings tier tags, routes beyond the two named endpoints, tests beyond the named
  endpoint-only tests, or any teacher-facing navigation.
- Do not call Canvas, OpenRouter, routines, or inspect private workspace artifacts.
- Do not run the full API suite for this narrow, non-shared route deletion.

## Reference pattern and routing

- Canonical-flow evidence and audit result:
  `docs/reference/workbench-canonical-flow-map.md`
- Roster ownership map: `docs/reference/roster-module-map.md`
- Endpoint owner: `api/webui/routes/roster.py::get_tier_scheme`,
  `api/webui/routes/roster.py::save_tier_scheme`
- Retained PowerGrader configuration seam:
  `api/webui/config/roster.py::roster_tier_by_id`
- Endpoint test owner: `api/tests/test_roster_routes.py::test_tier_scheme_*`
- HTTP-surface contract: `api/tests/test_route_contract.py::EXPECTED`
- Read project-local `TOOLS.md` before broad inspection. Use `rg` to confirm that no
  route declaration or endpoint-only test reference remains after deletion.

## Implementation requirements

1. Remove the two HTTP handlers and their stale V2 route documentation. Clean imports
   only when they become unused; do not reorganize adjacent Roster code.

2. Remove the exact five route tests and the two route-contract entries. Preserve
   `test_roster_config.py` unchanged, including its tier-scheme tests: they protect the
   live configuration consumed by PowerGrader.

3. Correct the two current-reference maps to distinguish the retired HTTP surface from
   retained tier-scheme data. The Workbench map must not call this a product decision
   after this batch; it must state that only endpoint wrappers were removed.

4. Self-audit with a repository search. It is acceptable for the term `tier_scheme`
   and `roster_tier_schemes` to remain in configuration, PowerGrader, tests, and
   historical handoffs. It is not acceptable for a live route decorator, handler, or
   `EXPECTED` entry for `/api/roster/tier-scheme` to remain.

5. Move the audit brief to the archive only after recording this batch's result. The
   audit map is a durable reference and must remain in `docs/reference/`.

## Verification

```powershell
py -m pytest api/tests/test_roster_routes.py api/tests/test_route_contract.py
rg -n '"/tier-scheme"|/api/roster/tier-scheme|def get_tier_scheme|def save_tier_scheme' api docs/reference --glob '!docs/handoffs/archive/**'
git diff --check
```

The `rg` command should return no live route/handler/contract references. It may return
the completed-reference explanation in `workbench-canonical-flow-map.md` only if that
text clearly says the endpoints were removed; it must not describe them as active.

No rendered browser check is required: there are no browser/template callers and no
browser assets change. Do not substitute a full-suite pass count for this focused
evidence.

## Stop conditions

Stop with RED rather than guessing if:

- A live browser, template, CLI, routine, or supported local client calls either
  `/api/roster/tier-scheme` endpoint.
- Removing the endpoint requires changing PowerGrader's `roster_tier_by_id` behavior,
  tier-scheme persisted data, or a Canvas group/write path.
- Route removal exposes a mismatch in Roster V3 ownership that requires a new public
  contract or data migration.
- The focused tests reveal an unrelated regression outside this endpoint boundary.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them
to the senior. Do not leave the only copy of execution state or evidence in chat.

### Execution result

- Traffic light: **GREEN**
- Commit hash: uncommitted
- Files changed:
  - `api/webui/routes/roster.py` — removed `import json`, docstring route listing, both `get_tier_scheme`/`save_tier_scheme` handlers, and the historical removal paragraph from the module docstring
  - `api/tests/test_roster_routes.py` — removed 5 endpoint-only test functions (`test_tier_scheme_*`)
  - `api/tests/test_route_contract.py` — removed 2 `EXPECTED` entries for `/api/roster/tier-scheme`
  - `docs/reference/roster-module-map.md` — replaced stale "group scheme/tier scheme route flow" with "group-set preference and group-label route flow"; removed historical removal paragraph (rationale lives in workbench-canonical-flow-map.md)
  - `docs/reference/workbench-canonical-flow-map.md` — replaced "needs product decision" batch with "Completed retirements" section; renumbered streaming batch to Batch 1
- Files moved:
  - `docs/handoffs/workbench-canonical-flow-audit.md` → `docs/handoffs/archive/workbench-canonical-flow-audit.md`
- Verification commands and pass/fail/skip counts:
  - `py -m pytest api/tests/test_roster_routes.py api/tests/test_route_contract.py` — **33 passed** in 1.18s
  - `rg -n '"/tier-scheme"|/api/roster/tier-scheme|def get_tier_scheme|def save_tier_scheme' api docs/reference --glob '!docs/handoffs/archive/**'` — returned only documentation references explaining the removal (3 matches: workbench-canonical-flow-map.md (past-tense), roster-module-map.md (past-tense), roster.py docstring). Zero live route decorators, handler functions, or contract entries.
  - `git diff --check` — clean
- Caller-search result: No browser, template, CLI, or routine callers of the removed endpoints were found in the current repository. The live `config.roster_tier_by_id()` callers in PowerGrader remain unchanged.
- Deviations from the brief: None.
- Remaining blocker or decision: None.

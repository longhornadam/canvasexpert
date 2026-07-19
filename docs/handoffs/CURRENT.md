# Remove the last endpoint-shaped fallback from Work typed reads

> **DEEPSEEK EXECUTION AUTHORITY.** Read `AGENTS.md`, this file, and only the references
> routed below. Do not read `NEXT_BATCH.md`, `HANDOFF_TEMPLATE.md`, or `archive/`.

Status: **READY**

Risk: **low** - internal Work discovery acquisition only; no response, persistence,
privacy, or Canvas-write behavior changes.

Depends on: the existing uncommitted 1.0beta-07a Work typed-read worktree based on
`1b3a2c1`; preserve every unrelated/user change exactly.

## Teacher-visible result

Home and Work findings remain byte-for-byte compatible, but the new typed Work context no
longer re-enters URL-regex mirror ownership when a typed scope needs its bounded live fallback.

## Acceptance criteria

- [ ] `WorkCourseReads` consults each named typed scope once and calls a pure live helper on
      non-current state; `_mirror_shape`/`_mirror_rows` are never reached by that fallback.
- [ ] `call_canvas_get_all` retains its existing compatibility behavior and tests, delegating
      only its final live call/error translation to the same pure helper.
- [ ] Current local reads remain zero-live-call; stale/missing/corrupt reads preserve deadline,
      timeout, structured-error, shared-cache, rich-comment, and live-only group behavior.
- [ ] No provider order, finding shape, registry/cache persistence, or privacy behavior changes.
- [ ] The named acceptance gate below passes.

The executor reports evidence; it does not redefine, narrow, or self-accept these criteria.

## Explicit non-goals

- Comment freshness policy, report provenance, Routines, MCP, derived views, or mutation
  reconciliation.
- Removing the compatibility matcher; Batch 8 may retire it only after caller proof.
- Editing any already-modified provider/discovery file except where an import must follow the
  helper rename; prefer no changes outside the two authorized files below.

## Locked decisions

- Extract the deadline/callback/timeout/error-normalization portion of
  `call_canvas_get_all` into `_call_live_get_all(canvas_get_all, path, params, deadline)`.
- `WorkCourseReads.assignments`, `.students`, `.submissions`, and `.live_call` invoke
  `_call_live_get_all` for live work. `call_canvas_get_all` keeps endpoint matching, then
  invokes `_call_live_get_all` only after no current compatibility read was available.
- Preserve exact live endpoints/params and the separate comment-bearing request. Do not make a
  local read authorize a write or persist any returned row.

## Scope

- `api/work_registry/providers/__init__.py`
- `api/tests/test_work_providers_mirror.py`
- `api/tests/test_work_discovery.py` only if the pure-helper proof belongs at that seam

## Read only these references

- `AGENTS.md`
- this brief
- `docs/contracts/work-registry-contract.md`: “Persistence boundary” and “Detected findings”
- the three files under Scope

Do not read: archived handoffs, unrelated module maps, or the whole 1.0beta spine.

## Preflight - stop if these facts are false

```powershell
git status --short
rg -n "class WorkCourseReads|def call_canvas_get_all|_mirror_shape|_mirror_rows" api/work_registry/providers/__init__.py
rg -n "call_canvas_get_all|WorkCourseReads|zero_live|falls_back" api/tests/test_work_providers_mirror.py api/tests/test_work_discovery.py
```

- The worktree still contains the reported 07a files and no unknown overlapping edit.
- `WorkCourseReads` still calls `call_canvas_get_all` from its typed fallback methods.
- The endpoint-matching compatibility seam still has an explicit regression test.

If any fact is false, return RED without implementation changes.

## Named acceptance gate

```powershell
py -m pytest api/tests/test_work_providers_mirror.py api/tests/test_work_discovery.py api/tests/test_work_registry.py api/tests/test_desk_routes.py -q
```

- Add one test that makes `_mirror_shape` raise if a `WorkCourseReads` live fallback touches it,
  while proving the live callback still runs and returns the expected rows.
- Existing compatibility and aggregate/privacy assertions must remain green.
- The 07a report records `1101 passed, 1 skipped`; do not rerun the broad suite.

## Stop conditions

- **RED:** preserving compatibility requires changing provider output, registry persistence, or
  the typed read-service contract.
- **YELLOW:** an existing test requires endpoint matching from `WorkCourseReads`; report the
  exact caller instead of preserving the architectural loop silently.

## Execution result

Record traffic light, changed files, command/counts, deviations, unresolved decisions, and
commit hash if one is created. Do not modify `NEXT_BATCH.md` or archive/commit other worktree
files in this repair.

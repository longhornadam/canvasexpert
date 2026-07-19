# Give built-in and custom Routines a supported typed read interface

> **DEEPSEEK EXECUTION AUTHORITY.** Read `AGENTS.md`, this file, and only the references
> routed below. Do not read `NEXT_BATCH.md`, `HANDOFF_TEMPLATE.md`, or `archive/`.

Status: **READY**

Risk: **medium** - background reads may inspect private rows, but final mutation computation,
Canvas sends, receipts, and routine scheduling remain live and unchanged.

Depends on: commit `5bc929c` (accepted 03 report provenance and atomicity)

## Teacher-visible result

Read-only grading-debt/download discovery and newly authored custom read-only Routines reuse
current local assignments/roster/submissions with honest source/freshness, falling back live
when unavailable. Existing writing Routines retain their live decision boundary.

## Acceptance criteria

- [ ] New `api/routine_reads.py::read_scope(scope, course_id, *, live_reader,
      max_age_hours=None)` supports only `assignments|roster|submissions` and returns exact keys
      `ok, records, error, source, synced_at, generation`.
- [ ] A current typed scope makes zero live calls; missing/stale/corrupt state uses the injected
      live reader with the existing endpoint/params and labels `source=canvas` without freshness
      or generation claims.
- [ ] Built-in `grading_debt` and download assignment listing use `read_scope`; Student Reports
      remains on its accepted report service. Sweep, curve, PowerGrader, and all apply paths are
      byte-for-byte untouched.
- [ ] Custom SDK injects `canvas_read`; existing `canvas_get`, `canvas_get_all`, and
      `canvas_send` remain compatibility/live tools. The shipped example and AUTHORING guide use
      `canvas_read` for ordinary assignment/submission reporting.
- [ ] No private rows/source envelopes enter routine receipts, logs, fixtures, or configuration.
- [ ] The named acceptance gate passes.

## Explicit non-goals

- Removing `api/webui/mirror_reads.py` (Gradebook still has a caller), changing custom routine
  decorator/schema, declaring mutation scopes, or changing write-routine behavior.

## Locked decisions

- Use one explicit mapping in `api/routine_reads.py`; reject unknown scope with a structured
  error and never accept arbitrary URLs.
- The helper owns no Canvas import and no persistence. Callers inject `_canvas_get_all`; tests
  inject fakes. Default age is `mirror_queries._serve_max_age_hours()` when omitted.
- Built-ins may ignore source metadata but must not serialize it. Custom authors receive the
  full result dict so freshness is available without a second read.
- Keep all live endpoint params exactly as `mirror_reads.py` currently defines them.

## Scope

- `api/routine_reads.py` (new)
- `api/webui/routes/routines_builtin.py`
- `api/webui/routes/routines_custom.py`
- `api/custom_routines/AUTHORING.md`
- `api/custom_routines/_example_missing_work.py`
- `api/tests/test_routine_reads.py` (new)
- `api/tests/test_routine_receipts.py` only if a no-private-receipt assertion belongs there

## Read only these references

- `AGENTS.md`; this promoted brief
- `api/custom_routines/AUTHORING.md`
- `docs/reference/canvasmirror-1.0beta-information-spine.md`: §11.8 and Former Program 8's
  Routine bullets only
- `api/webui/mirror_reads.py`; exact files under Scope

Do not read archived handoffs, unrelated route modules, or the whole vision document.

## Preflight - stop if these facts are false

```powershell
rg -n "assignments_or_live|submissions_or_live|def _run_routine_grading_debt|def _run_routine_download" api/webui/routes/routines_builtin.py
rg -n "def _routine_sdk|canvas_get_all|canvas_send" api/webui/routes/routines_custom.py
rg -n "canvas_get_all" api/custom_routines/AUTHORING.md api/custom_routines/_example_missing_work.py
```

- Only grading debt/download listing are authorized compatibility-reader migrations.
- Custom SDK still injects raw live reads/writes and has no supported typed reader.

## Named acceptance gate

```powershell
py -m pytest api/tests/test_routine_reads.py api/tests/test_routine_receipts.py api/tests/test_route_contract.py -q
```

- Cover three zero-live scopes, three fallback shapes, unknown-scope rejection, metadata labels,
  and proof that writing routine owners/imports are unchanged. No broad suite.

## Stop conditions

- **RED:** the migration requires changing sweep/curve/PowerGrader computation or receipt shape.
- **YELLOW:** a custom compatibility test requires a different public result shape; preserve raw
  APIs and report the exact expectation.

## Execution result

Record traffic light, changed files, focused command/count, deviations, unresolved decisions,
and commit hash if created.

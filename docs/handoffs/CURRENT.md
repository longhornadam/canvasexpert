# Make Home discovery honor bounded comment freshness

> **DEEPSEEK EXECUTION AUTHORITY.** Read `AGENTS.md`, this file, and only the references
> routed below. Do not read `NEXT_BATCH.md`, `HANDOFF_TEMPLATE.md`, or `archive/`.

Status: **READY**

Risk: **medium** - private comments are transiently reduced into aggregate Home findings;
registry persistence and Canvas writes remain untouched.

Depends on: commit `6103fca` (accepted 01 comment-freshness foundation)

## Teacher-visible result

Home comment-follow-up findings use local comments only while their dedicated freshness scope
is current. Older/missing comment state triggers the existing bounded live request, so a recent
comment-free submission delta can no longer hide a student reply.

## Acceptance criteria

- [ ] `WorkCourseReads.submissions(include_comments=False)` uses `PRIVATE_SUBMISSIONS`; the
      `True` path uses `PRIVATE_SUBMISSION_COMMENTS`, both with the configured serve-age bound.
- [ ] Fresh comment state produces zero live calls; stale/missing/corrupt comment state makes
      exactly one rich live submission call containing `submission_comments`.
- [ ] Plain submissions may reuse a rich result, but a plain live result is never reused as a
      rich result; calling plain then rich performs the required rich acquisition.
- [ ] Grading-debt/Home comment reductions and provider order remain aggregate-only and
      unchanged; late-work can keep the plain scope.
- [ ] Deadline, timeout, last-good discovery-cache, and structured-error behavior remain intact.
- [ ] The named acceptance gate passes.

## Explicit non-goals

- Report generation/provenance, comment scheduler cadence, write-triggered invalidation,
Routines, MCP, registry schema, or any new derived view.

## Locked decisions

- Use `mirror_queries._serve_max_age_hours()` as the beta comment bound; do not add a setting.
- Keep separate plain and rich submission caches inside `WorkCourseReads`. A rich result may
  seed the plain cache; never do the reverse.
- Live fallback remains the existing course submissions endpoint and is transient only. Do not
  persist comments, identities, or source envelopes into Work Registry/discovery cache/logs.
- No provider signature or finding-vocabulary changes are allowed.

## Scope

- `api/work_registry/providers/__init__.py`
- `api/tests/test_work_providers_mirror.py`
- `api/tests/test_work_discovery.py` only for an aggregate/provider-order assertion

## Read only these references

- `AGENTS.md`; this promoted brief
- `docs/contracts/work-registry-contract.md`: "Persistence boundary" and "Detected findings"
- `docs/reference/workbench-canonical-flow-map.md`: Home row and safety boundary
- `api/mirror/read_service.py`: the two private submission scope constants/readers
- the exact files under Scope

Do not read archived handoffs, unrelated providers, or the whole 1.0beta spine.

## Preflight - stop if these facts are false

```powershell
rg -n "class WorkCourseReads|def submissions|include_comments|_submissions_cache" api/work_registry/providers/__init__.py
rg -n "PRIVATE_SUBMISSION_COMMENTS|def private_submission_comments" api/mirror/read_service.py
rg -n "reads.submissions" api/work_registry/providers -g "*.py"
```

- 07a's pure live helper is present and Home/grading debt request rich comments explicitly.
- The dedicated comment scope exists and returns the same normalized row shape.

## Named acceptance gate

```powershell
py -m pytest api/tests/test_work_providers_mirror.py api/tests/test_work_discovery.py api/tests/test_work_registry.py api/tests/test_desk_routes.py -q
```

- Add zero-live, stale-rich-fallback, corrupt-rich-fallback, and plain-then-rich cache tests.
- No full suite or rendered route check unless a route/template unexpectedly changes (stop RED).

## Stop conditions

- **RED:** the dedicated scope cannot preserve the existing aggregate finding shape/privacy.
- **YELLOW:** the provider order makes a plain live result precede the rich request in production;
  preserve correctness with separate caches and report the exact order.

## Execution result

Record traffic light, changed files, focused command/count, deviations, unresolved decisions,
and commit hash if created.

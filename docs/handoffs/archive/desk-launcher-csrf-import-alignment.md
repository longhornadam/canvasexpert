# Execution brief: Restore Desk scan under the real launcher

Status: **ready for implementation**

Risk: **high**

Executor: **Terra**

## Outcome

Make Desk's **Scan active courses** action work when Canvas Expert is started through
the shipped `api/qf_ui.py` launcher. Preserve the existing local-only CSRF, loopback,
and same-origin protections while ensuring the token rendered by Desk is validated by
the same guard-module instance used by the scan route.

This also repairs the identical launcher-only rejection on operation-ledger mutation
routes, whose guard must remain intact because reviewed operations can write to Canvas.

## Locked decisions

- The confirmed cause is Python package aliasing: `api/qf_ui.py` imports
  `webui.server`, while `api/webui/routes/work.py` and
  `api/webui/routes/operations.py` import the guard as
  `api.webui.local_request_guard`. That loads two modules and creates two random CSRF
  tokens. Desk renders the `webui.*` token and the routes validate against the
  `api.webui.*` token.
- Fix both route modules by using package-relative imports that resolve under either
  supported import root. Do not change the launcher, manipulate `sys.path`, alias
  entries in `sys.modules`, make the token deterministic, move it to persistence, or
  weaken any validation in `local_request_guard.py`.
- Add a true launcher-package integration regression: exercise the app imported as
  `webui.server`, extract the server-rendered token from `/`, and use it for a guarded
  `POST /api/work/scan`. The test must fail on the current absolute import and pass on
  the relative import.
- Keep the regression hermetic: stub the scan result and workspace boundary. It must
  not read Canvas, persist into the user's workspace, expose credentials, or contain
  course/student data.
- Do not broaden Desk scanning behavior or alter its existing aggregate discovery
  providers, timeouts, cache, course selection, messages, or API response shape.
- Preserve the existing staged/uncommitted work exactly. Leave this fix uncommitted
  and do not reset, unstage, or restage unrelated paths.

## Senior live-verification addendum: keep the bounded scan useful

The CSRF fix passed live launcher verification: Desk's POST reached Canvas and the
button stayed in its real scanning state instead of failing immediately with 403.
That run exposed a second bounded issue before this user outcome could be accepted:
the one active course ended stale with `course_timeout` and zero findings.

Aggregate-only timing isolated the cause without printing course/student data:

- assignments: 444 rows in 12.72 seconds;
- submissions with comments: 753 rows in 9.33 seconds;
- roster-warning provider by itself: 1.97 seconds, zero findings.

`grading_debt` and `late_work` currently request the same assignments and submissions
paths sequentially. The grading-debt request is the richer submissions projection
because it includes comments; late-work needs only fields already present in that
successful response. Repeating both paginated reads deterministically exhausts the
30-second course budget.

Locked follow-up decisions:

- In `api/work_registry/discovery.py`, give one `_scan_course` execution a narrowly
  scoped, in-memory read-through wrapper for exactly that course's assignments path
  and students/submissions path. Continue running the existing providers in their
  current order so grading-debt fills the submissions cache with the richer response
  before late-work reuses it.
- Cache only successful `(list, None)` results. Do not cache errors; a later provider
  may retry. Do not persist raw Canvas data, copy it into findings, or widen any public
  response. All other Canvas paths and parameters continue directly to the existing
  client.
- Do not raise `SCAN_TIMEOUT_SECONDS` or request timeouts, parallelize providers,
  change provider outputs, alter discovery-cache schema, or add generic cache
  infrastructure. This is one concrete per-course duplicate-read elimination.
- The wrapper must preserve the injected callback seam and deadline behavior used by
  current provider tests. Providers remain independently callable outside discovery.
- Add a regression in `api/tests/test_work_discovery.py` that exercises the real
  grading-debt and late-work providers through `_scan_course`, proves both kinds can be
  produced, and proves the shared assignments and submissions paths are each fetched
  only once. Keep all fixture data fictional and PII-free.

Follow-up scope is limited to `api/work_registry/discovery.py`,
`api/tests/test_work_discovery.py`, and this handoff. Add this command to verification:

```powershell
py -m pytest api/tests/test_work_discovery.py api/tests/test_work_routes.py api/tests/test_operation_routes.py
```

After the executor returns, the senior will restart the real launcher and run Desk
Scan once more. Acceptance requires the single course to finish within the existing
budget without `course_timeout`; a legitimate provider-level Canvas error may return
the existing partial result, but the duplicate-read timeout may not.

## Scope

- `api/webui/routes/work.py`: resolve `require_local_mutation` through the route
  package's own parent package.
- `api/webui/routes/operations.py`: make the same guard import alignment so the real
  launcher has one CSRF token for every guarded operation route.
- `api/tests/test_work_routes.py` or one narrowly named adjacent test module: add the
  launcher-path integration regression without relying on source-text assertions.
- This handoff's `Execution result` section.

## Out of scope

- Changes to `api/qf_ui.py`, `api/webui/local_request_guard.py`, Canvas clients,
  discovery providers, Work Registry storage, operation-ledger behavior, templates,
  JavaScript, CSS, or public API contracts.
- A live Canvas write, operation prepare/review/apply/retry, AI request, credential
  change, or persistence migration.
- General cleanup of other absolute `api.*` imports. Only the two imports that create
  the duplicated process-local CSRF guard are authorized.
- Changes to or staging-state manipulation of the unrelated dirty integration batch.

## Reference pattern and routing

- Real launcher/import root: `api/qf_ui.py::from webui.server import app`
- Token render: `api/webui/routes/pages.py::dashboard` and
  `api/webui/templates/base.html`
- Guard implementation: `api/webui/local_request_guard.py`
- Affected guarded routes: `api/webui/routes/work.py` and
  `api/webui/routes/operations.py`
- Existing route safety tests: `api/tests/test_work_routes.py` and
  `api/tests/test_operation_routes.py`
- Read project-local `TOOLS.md` before using broad manual inspection.

## Implementation requirements

1. Replace only the two alias-producing absolute guard imports with imports relative
   to `api/webui/routes/`, so both `webui.*` and `api.webui.*` application imports
   obtain their matching single guard instance.
2. Add a hermetic route-level regression that starts from the `webui.server` import
   path used by `qf_ui.py`, obtains the rendered CSRF value rather than importing it
   independently, and proves the guarded Desk scan returns a successful stub result.
   Isolate the launcher-path import if necessary so the ordinary test suite's
   `api.webui.*` imports cannot mask the aliasing bug.
3. In that regression, assert a wrong CSRF token is still rejected with 403 before
   the valid rendered-token request succeeds. Do not duplicate the full guard matrix
   already covered by existing tests.
4. Keep the test worktree-independent and free of developer-specific paths, live
   settings, credentials, Canvas calls, and persisted user data.
5. Self-review the final diff specifically for guard weakening, import aliasing, and
   unintended changes to staged files.

## Verification

```powershell
py -m pytest api/tests/test_work_routes.py api/tests/test_operation_routes.py
py -m pytest api/tests/test_desk_routes.py api/tests/test_webui_template_contracts.py api/tests/test_route_contract.py
git diff --check HEAD
```

After the focused tests pass, restart the local app through `api/qf_ui.py` so it loads
the changed Python modules. Render `/`, confirm zero new browser-console errors, and
invoke **Scan active courses** once. The scan may perform read-only Canvas requests and
update the local Work Registry cache, as explicitly requested by the user; it must not
perform a Canvas write. Confirm the UI no longer reports the generic 403-driven
`Scan unavailable` result. Record whether the successful result is full or partial and
only aggregate counts/error codes—no course IDs, names beyond the user-provided course,
student data, grades, or submission content.

Do not exercise operation prepare, review, apply, or retry in live rendered
verification. Their existing stubbed route tests are the required safety evidence.

## Stop conditions

Stop with RED rather than guessing if:

- The launcher no longer imports `webui.server`, the affected routes are not loaded
  beneath that package, or package-relative imports do not unify the guard instance.
- Passing the launcher-path regression requires changing the launcher, global import
  path, CSRF implementation, public API, or guard validation semantics.
- The real Desk scan reaches a new credential, FERPA, or Canvas-write boundary.
- An unrelated worktree change blocks the scoped files or would need to be overwritten,
  unstaged, or reformatted.

## Return report

Before handback, replace the placeholders below in this file as well as reporting them
to the senior. Do not leave the only copy of execution state or test evidence in chat.

### Execution result

- Traffic light: **GREEN** — implementation and senior live acceptance are complete.
- Commit: changes are uncommitted; the existing staged integration batch was not
  reset, unstaged, restaged, or committed.
- Files changed:
  - `api/webui/routes/work.py`
  - `api/webui/routes/operations.py`
  - `api/work_registry/discovery.py`
  - `api/tests/test_work_discovery.py`
  - `api/tests/test_work_routes.py`
  - `docs/handoffs/desk-launcher-csrf-import-alignment.md`
- Verification:
  - `py -m pytest api/tests/test_work_discovery.py api/tests/test_work_routes.py api/tests/test_operation_routes.py`
    - **33 passed, 0 failed, 0 skipped**
  - `py -m pytest api/tests/test_desk_routes.py api/tests/test_webui_template_contracts.py api/tests/test_route_contract.py`
    - **21 passed, 0 failed, 0 skipped**
  - `git diff --check HEAD`
    - **passed**; Git emitted only line-ending conversion warnings for the five
      unstaged implementation files.
- Rendered routes checked: the senior restarted the shipped `api/qf_ui.py` launcher,
  reloaded `/`, and invoked **Scan active courses** in the rendered Desk. The request
  passed the CSRF guard, completed within the unchanged 30-second discovery budget,
  returned the button to enabled state, and produced zero new browser-console errors.
  The aggregate cache result was 1 course scanned, 0 findings, 0 stale courses, and no
  error codes. No Canvas write, AI call, routine, or operation-ledger mutation ran.
- Deviations: none. The launcher regression is isolated in a fresh Python subprocess,
  renders the CSRF token from `/`, rejects a wrong token with 403, stubs discovery and
  persistence, and accepts the rendered token for `POST /api/work/scan`. The follow-up
  regression exercises the real grading-debt and late-work providers through
  `_scan_course`, produces both finding kinds, and proves the shared assignments and
  richer submissions reads each execute once. Only successful `(list, None)` responses
  are held in that one course scan's in-memory closure; errors, other callback result
  shapes, and unrelated requests pass through.
- Remaining blocker or decision: none.

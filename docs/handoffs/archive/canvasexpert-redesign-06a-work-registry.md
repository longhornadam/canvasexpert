# Toyota handoff 06a: durable work registry and source adapters

## Prerequisite and objective

`docs/contracts/work-registry-contract.md` is accepted for this slice. Implement the
contract's PII-minimized registry, suppression records, local source adapters, and
guarded mutation routes. No Canvas scan, UI, or live write occurs in this slice.

The registry is an index, never a replacement for PowerGrader sessions, the autoscore
queue, Canvas, Forge files, or PRIVATE receipt details.

## Exact files and interfaces

- New `api/work_registry/models.py`
  - Define the contract enums and strict validators:
    `validate_registry_document`, `validate_job`, `validate_suppressions`, and
    `validate_source_ref`.
  - Expose `stable_fingerprint(kind, source_ref, course_ids, assignment_id)` and
    `material_version(job_facts)`; both return lowercase SHA-256 hex strings and
    never accept student IDs, names, grades, comments, or submission content.
  - Reject unknown versions, statuses, origins, source types, absolute URLs, absolute
    paths, non-string Canvas IDs, and a focused course outside `course_ids`.
- New `api/work_registry/storage.py`
  - Resolve `<workspace>/_system/workbench/` through `webui.workspace.workspace_root()`.
  - Expose `read_registry()`, `write_registry(document)`, `read_suppressions()`,
    `write_suppressions(document)`, and `quarantine_dir()`.
  - Use a module `threading.RLock`, same-directory temp files, flush/fsync,
    `os.replace`, and timestamped quarantine. If no workspace is configured, reads
    return empty versioned documents and writes return a fixed
    `workspace_not_configured` error without creating repo files.
- New `api/work_registry/suppressions.py`
  - Expose `ignore(job)`, `snooze(job, until)`, `clear_for_material_change(job)`,
    and `is_suppressed(job, now=None)`. Suppression identity is exactly
    `(fingerprint, material_version)`.
- New `api/work_registry/adapters.py`
  - Expose `collect_local_jobs()` and `collect_start_sources()`.
  - Adapters may read only existing local authorities: PowerGrader session summaries,
    autoscore queue, receipt projections, routine status projection, and workspace
    Forge file listings. They must never load student/session payloads, call Canvas,
    or copy authority data into the registry.
- New `api/webui/local_request_guard.py`
  - Expose `csrf_token()` and `require_local_mutation(request)`.
  - Generate one process-random token at import; never persist it.
  - Require header `X-CanvasExpert-CSRF`, a literal loopback Host (`127.0.0.1` or
    `::1`, with the request port), and when `Origin` is present require exact
    scheme/host/port match. Reject missing/wrong token, non-loopback Host, malformed
    Origin, or foreign Origin with HTTP 403 before any private record lookup.
- New `api/webui/routes/work.py`
  - Register the routes below and keep responses JSON, PII-free, and local-only.
- `api/webui/server.py`
  - Register the work router once; preserve all existing router order and behavior.
- `api/powergrader/session_store.py` only if a PII-free summary field or safe relative
  resume URL is needed. Do not expose session payloads.
- `api/webui/routes/routines.py` only if a pure, PII-free routine status projection is
  needed by the adapter. Do not run a routine from a GET or adapter call.
- New `api/tests/test_work_registry.py`, `api/tests/test_work_routes.py`; update
  `api/tests/test_route_contract.py` only for these routes.

## Source projection rules

All adapter output uses generic titles when a source label might contain identity:

- PowerGrader session summaries become `grade.powergrader` jobs with
  `source_ref.type=powergrader_session`, resume URL
  `/powergrader/session/{safe_session_id}`, and only course/assignment IDs and
  aggregate counts. `posted == total > 0` is `completed`; approved work not posted
  is `attention`; all other nonterminal sessions are `in_progress`.
- Autoscore queue entries become `grade.powergrader.scheduled` jobs with
  `source_ref.type=autoscore_job`. `needs_attention`, `failed`, and
  `partial_auto_pushed` are `attention`; `auto_pushed` is `completed`; scheduled or
  session-ready work is `in_progress`. Use `/powergrader/session/{session_id}` only
  when the existing queue field contains a safe session ID; otherwise use `/powergrader`.
- Receipt summaries become `operation_receipt` system jobs. `applied` and `no_effect`
  are `completed`; `partial`, `failed`, and `blocked` are `attention`. The detail URL
  is `/api/receipts/{opaque_receipt_id}`; never hydrate PRIVATE detail here.
- Routine status projection may create `routine_state` system jobs only from local
  enabled/due/last-summary state. A due enabled routine is `attention`; disabled or
  not-due state is omitted from Continue/Attention.
- `collect_start_sources()` may return only workspace-relative Forge files and generic
  start metadata. Repository fallback examples are not copied into the registry.

Every projected job must contain the exact public index shape in the accepted contract.
`title` must be generic or passed through a deterministic protected-name sanitizer;
when uncertain use `PowerGrader work`, `Scheduled work`, `Operation receipt`, or a
generic kind/count label. No response, disk document, log, or exception may contain
student names, Canvas user IDs, submission content, grades, comments, monitored notes,
or absolute paths.

## Routes and state transitions

- `GET /api/work?section=continue|attention|all`: read local state and adapters only;
  never scan Canvas. Apply suppressions and return
  `{"ok":true,"jobs":[...],"start_sources":[...]}`. Unknown section returns 400.
- `POST /api/work/{job_id}/ignore`: JSON body exactly
  `{"material_version":"..."}`. Guard first, then require an exact current
  fingerprint/material-version match; persist an ignored suppression and return the
  updated PII-free projection.
- `POST /api/work/{job_id}/snooze`: JSON body exactly
  `{"material_version":"...","until":"ISO-8601"}`. `until` must be a valid
  future timestamp; stale/unknown jobs fail closed with 409 and no write.
- `POST /api/work/{job_id}/complete`: JSON body exactly
  `{"material_version":"..."}`. Guard first; only `origin=intentional` jobs may
  transition to `completed`. Detected/system jobs return 409 and remain unchanged.

No mutation route accepts a client-supplied Canvas method, endpoint, payload, title,
course list, or arbitrary registry record. No route starts a session or routine.

## Required tests

Test strict schema validation, empty/round-trip storage, atomic replace, concurrency,
quarantine, no-workspace behavior, adapter authority boundaries, stable fingerprints,
material-version changes, generic redaction, safe relative resume URLs, suppression
resurfacing, stale/unknown fail-closed behavior, every guard rejection, valid same-origin
mutation, absence of Canvas calls, and absence of PII/absolute paths in disk/API/logs.

```powershell
py -m pytest api/tests/test_work_registry.py api/tests/test_work_routes.py api/tests/test_powergrader_scheduled_autoscore.py api/tests/test_workspace.py api/tests/test_route_contract.py
git diff --check
```

One commit. Report the hash, schema/storage/concurrency/quarantine results, adapter
source matrix, PII deny-list evidence, guard rejection matrix, route-contract result,
and confirmation of zero Canvas calls. Do not archive this handoff.

## Forbidden changes / escalation

- Do not add `POST /api/work/scan` (that is 06b).
- Do not add Desk markup, Workbench markup, or expose the CSRF token in templates
  (that is 07).
- Do not add `/api/operations` or any Operation Ledger mutation (that is 10).
- Stop if any adapter needs private payload copying, identity persistence, a Canvas
  call, a changed existing public route, or a new unresolved status/source type.

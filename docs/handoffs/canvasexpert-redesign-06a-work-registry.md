# Toyota handoff 06a: durable work registry and source adapters

## Objective

Implement the Work Registry Contract, suppressions, and adapters for existing local
authorities. No Canvas scan, UI, or live write occurs in this slice.

## Files

- New `api/work_registry/{__init__,models,storage,suppressions,adapters}.py`
- New `api/webui/local_request_guard.py` owning a process-random CSRF token and strict
  same-origin plus loopback Host/Origin validation
- New `api/webui/routes/work.py`
- `api/webui/server.py`
- `api/powergrader/session_store.py` only to extend PII-free summaries if necessary
- `api/webui/routes/routines.py` only for a pure status projection if necessary
- New `api/tests/test_work_registry.py`
- New `api/tests/test_work_routes.py`
- `api/tests/test_route_contract.py`

## Sources and API

Adapters project without copying authority:

- `session_store.list_session_summaries()` -> Continue/Attention + resume URLs.
- `autoscore_queue.load_queue()` -> scheduled/needs-attention/partial/failed.
- receipt summaries -> completed/failed operation and routine entries.
- workspace Forge libraries -> Start sources, not invented drafts.

Routes in this slice:

- `GET /api/work?section=continue|attention|all`
- `POST /api/work/{job_id}/ignore`
- `POST /api/work/{job_id}/snooze`
- `POST /api/work/{job_id}/complete` for intentional jobs only

Ignore/snooze follows fingerprint+material-version. Unknown/stale jobs fail closed.
No response contains student identity or submission content. All POST routes run the
local mutation guard before record lookup. Missing/wrong token, non-loopback Host, or
foreign Origin returns 403. Tests inject the process token; slice 07 exposes it only in
Workbench markup. Never persist it or describe the app as authenticated.

## Verification

Test schema validation, empty/round-trip, atomic replace, concurrency, quarantine, adapter
authority, stable fingerprints, resurfacing, redaction, safe relative resume URLs,
absence of Canvas calls, every guard rejection, and valid same-origin mutation.

```powershell
py -m pytest api/tests/test_work_registry.py api/tests/test_work_routes.py api/tests/test_powergrader_scheduled_autoscore.py api/tests/test_workspace.py api/tests/test_route_contract.py
git diff --check
```

Stop if an adapter needs to copy PRIVATE session/student payloads into the registry.

## Required implementer reply

One commit; report hash/files, schema/storage/concurrency/quarantine results, PII deny-list
evidence, route contract result, and confirmation of zero Canvas calls.

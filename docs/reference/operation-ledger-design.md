# Operation Ledger — accepted design

Status: implemented historical design reference. The contract in
`docs/contracts/operation-ledger-contract.md` remains canonical; this document records the
storage schema, state machine, adapter interface, claim/lease/recovery rules, and PageForge
pilot decisions used by the implementation. New changes require a current execution brief
under `AGENTS.md`, not authority inferred from this document.

## 1. Storage layout

All operation-ledger records are PRIVATE and machine-affine, stored under
`%LOCALAPPDATA%\CanvasExpert\workbench\private\` (the existing `paths.private_root()`).

### Files

| File | Contents | Format |
|---|---|---|
| `operations.v1.json` | All operations and their targets | Single JSON document, atomic-replaced |
| `claims.v1.json` | Active and expired claim records | Single JSON document, atomic-replaced |
| `receipts.v1.json` | Immutable receipts (existing, unchanged) | Single JSON document, atomic-replaced |

Batches are embedded inside the operation record (see §2.3). There is no separate
batches file — a batch is a frozen review snapshot stored on the operation.

### paths.py additions

```python
def operations_file() -> Path:
    return private_root() / "operations.v1.json"

def claims_file() -> Path:
    return private_root() / "claims.v1.json"
```

### Atomicity

All writes use the existing `storage.atomic_write_json()` (temp-file + fsync + atomic
replace) under `storage.storage_lock()` (process-wide RLock). Corrupt documents are
quarantined via `storage._quarantine()`.

## 2. Data models

### 2.1 Operation

```json
{
  "version": 1,
  "operation_id": "op-<token>",
  "kind": "content.page",
  "source_job_id": "job-<hash>" | null,
  "status": "working",
  "source_ref": { "type": "workspace_relative", "value": "<path>" },
  "source_digest": "<sha256>",
  "normalized_payload": { ... kind-specific private payload ... },
  "review": null,
  "targets": [ { ... target records ... } ],
  "created_at": "<iso>",
  "updated_at": "<iso>"
}
```

**Operation status enum** (ordered lifecycle):

```
working → prepared → reviewed → applying → applied | partial | failed | attention
```

- `working` — created, not yet validated/frozen
- `prepared` — server-validated, source digest stored, targets verified
- `reviewed` — batch frozen, review digest stored, ready to apply
- `applying` — at least one target is claimed or in-flight
- `applied` — all targets applied
- `partial` — some targets applied, some failed/blocked/sent_unknown
- `failed` — all targets failed
- `attention` — at least one target is `sent_unknown` or `blocked` and needs human review

Transitions are forward-only except `attention → applying` (retry) and
`applying → attention` (uncertain outcome). No status may skip `prepared` or `reviewed`.

### 2.2 Target

```json
{
  "target_key": "<deterministic>",
  "idempotency_key": "<deterministic>",
  "course_id": "<private>",
  "state": "pending",
  "attempt_id": null,
  "payload_digest": null,
  "claim_owner": null,
  "claim_acquired_at": null,
  "claim_lease_expires_at": null,
  "baseline": null,
  "returned_object_id": null,
  "returned_object_url": null,
  "steps": [ { ... step records ... } ],
  "error_code": null,
  "private_diagnostic": null,
  "updated_at": "<iso>"
}
```

**Target state enum**:

```
pending → claimed → sent_unknown → applied | failed | blocked | skipped
```

- `pending` — not yet attempted
- `claimed` — write-ahead persisted, Canvas call in flight or about to be
- `sent_unknown` — Canvas call returned uncertain (timeout, disconnect, crash window,
  unparseable response); needs recovery; automatic resend is forbidden
- `applied` — Canvas confirmed success; returned IDs persisted
- `failed` — Canvas returned an unambiguous rejection (4xx with clear error)
- `blocked` — adapter detected drift or ambiguous foreign content; needs human review
- `skipped` — idempotency check proved the effect already exists (by exact ID, never
  by title); no Canvas call made

### 2.3 Batch (embedded review snapshot)

```json
{
  "batch_id": "batch-<token>",
  "review_digest": "<sha256 over frozen reviews>",
  "frozen_reviews": [ { ... per-target frozen summary ... } ],
  "created_at": "<iso>"
}
```

Stored as `operation.review` (null until reviewed). The `review_digest` covers the
ordered list of frozen reviews; apply requires both `batch_id` and `review_digest`
to match the stored values.

### 2.4 Step (for multi-step targets like PageForge page+module)

```json
{
  "step_key": "create_page" | "attach_module",
  "state": "pending" | "claimed" | "sent_unknown" | "applied" | "failed" | "blocked" | "skipped",
  "attempt_id": null,
  "returned_object_id": null,
  "error_code": null,
  "private_diagnostic": null,
  "updated_at": "<iso>"
}
```

Steps execute sequentially within a target. A target is `applied` only when all
required steps are `applied` or `skipped`. If an earlier step is `sent_unknown` or
`blocked`, later steps stay `pending` and the target is not `applied`.

### 2.5 Claim record (claims.v1.json)

```json
{
  "version": 1,
  "claims": [
    {
      "claim_id": "<target_key>:<attempt_id>",
      "target_key": "<deterministic>",
      "operation_id": "op-<token>",
      "attempt_id": "<uuid>",
      "owner_pid": <int>,
      "owner_started_at": "<iso>",
      "acquired_at": "<iso>",
      "lease_expires_at": "<iso>",
      "payload_digest": "<sha256>",
      "state": "claimed" | "released" | "expired"
    }
  ]
}
```

## 3. Adapter interface

Every registered kind implements this Protocol. The registry maps kind strings to
adapter instances.

```python
class OperationAdapter(Protocol):
    kind: str                          # e.g. "content.page"

    def build_payload(self, prepare_request: dict) -> dict:
        """Parse/validate the browser-submitted prepare request.
        Returns the normalized private payload. Raises ValueError on invalid input.
        Never trusts browser-supplied Canvas paths, endpoints, or method names."""

    def source_digest(self, payload: dict) -> str:
        """Deterministic SHA-256 over the normalized payload (not including targets)."""

    def verify_targets(self, payload: dict, targets: list[dict]) -> list[dict]:
        """Verify each target against active/available courses.
        Returns the verified target list with target_key and idempotency_key set.
        Raises ValueError if any target is invalid."""

    def target_key(self, payload: dict, course_id: str) -> str:
        """Deterministic target key for a course (e.g. sha256 of kind+digest+course_id)."""

    def idempotency_key(self, payload: dict, course_id: str) -> str:
        """Deterministic idempotency key (e.g. sha256 of source_digest+course_id+normalized_title)."""

    def freeze_review(self, payload: dict, target: dict, baseline: dict) -> dict:
        """Capture the frozen review summary for a target.
        Includes per-course effects, module-item implications, and baseline snapshot.
        Must be JSON-serializable and deterministic for digest computation."""

    def check_drift(self, payload: dict, target: dict, baseline: dict) -> bool:
        """Return True if Canvas/local state has drifted since review.
        Drift invalidates review and blocks apply."""

    def capture_baseline(self, payload: dict, target: dict) -> dict:
        """Read current Canvas/local state for drift detection.
        Called at review time and again at apply time."""

    def execute(self, payload: dict, target: dict, baseline: dict, claim: dict,
                context) -> dict:
        """Perform the Canvas call(s) for one target.
        Returns {state, returned_object_id, returned_object_url, error_code, private_diagnostic, steps}.
        May perform multiple sequential steps (e.g. create_page then attach_module).
        Must be idempotent: if the effect already exists (proven by exact ID), return skipped."""

    def reconcile(self, payload: dict, target: dict, baseline: dict) -> dict:
        """On restart, prove whether a sent_unknown target was applied or not.
        Returns {state, returned_object_id, ...} or {state: "sent_unknown"} if unprovable.
        Same-title matching is never proof. Only exact ID or kind-specific postcondition."""

    def retry_selector(self, operation: dict) -> list[dict]:
        """Return only the targets that are unresolved (sent_unknown, failed, blocked).
        Applied/skipped targets are never retried."""

    def reversal_descriptor(self, payload: dict, target: dict) -> dict:
        """Describe whether/how this target can be reversed.
        {supported: bool, method: str | null, snapshot: dict | null}.
        If no separately validated API path exists, supported is false."""
```

## 4. Claim / lease / recovery rules

### 4.1 Claim acquisition

Before any Canvas call, the executor:

1. Generates a new `attempt_id` (UUID4).
2. Computes `payload_digest` = SHA-256 over the normalized outbound payload.
3. Acquires the claim under the claims interprocess lock: writes to
   `claims.v1.json` with `state: "claimed"`,
   `owner_pid`, `owner_started_at` (process start time), `acquired_at`, and
   `lease_expires_at` = `acquired_at + 5 minutes`.
4. Persists the target as `claimed` with `attempt_id`, `payload_digest`, and
   additive `apply_baseline` to `operations.v1.json`. The review-time `baseline`
   remains immutable.
5. **Flushes both writes (fsync + atomic replace) before making the Canvas call.**

Before each individual Canvas mutation, the adapter calls the executor-owned execution
context to persist the named step as `claimed` with `outbound_started_at`. A successful
response and every returned object ID are checkpointed and flushed before the next Canvas
call. The context verifies the current claim before every checkpoint so a superseded
worker cannot overwrite recovered state.

### 4.2 Lease expiry

- Lease duration: **5 minutes** (sufficient for a single Canvas POST + module item POST).
- On restart, any claim with `lease_expires_at < now` is marked `expired` and the
  target is reconciled via `adapter.reconcile()`.
- A claim with `lease_expires_at >= now` remains active regardless of PID. PID inequality
  is not evidence that a process died.
- Expiry permits reconciliation, never blind takeover or resend. An expired but
  unreconciled claim still blocks a new claim.
- Claims and operations read-modify-write transactions use one shared adjacent OS-locked
  ledger lock file in addition to the in-process lock. The shared lock makes claim
  validation plus target checkpointing one fenced transaction; separate per-document
  locks are forbidden. Atomic JSON replacement alone is not a cross-process mutex.

### 4.3 Recovery on restart

For every target in `claimed` or `sent_unknown` state:

1. Skip an unexpired active claim. If its lease expired, atomically mark it `expired`.
2. Call `adapter.reconcile(payload, target, baseline)`.
3. If reconcile proves `applied`: persist returned IDs, set target `applied`.
4. Reset to `pending` only when no mutation step has an outbound marker. Absence after a
   possibly-sent create is not proof of absence and remains `sent_unknown`.
5. If reconcile cannot prove either: target stays `sent_unknown` (Attention).

### 4.4 Retry

Retry creates a **new attempt** for unresolved targets only. The executor:

1. Calls `adapter.retry_selector(operation)` to get unresolved targets.
2. For each, runs the normal claim → write-ahead → execute → persist loop.
3. Applied targets from the original attempt are never resent.

## 5. PageForge pilot adapter

### 5.1 Kind

`content.page`

### 5.2 Prepare

Input: `{path, published, module_name?}` (same as the existing immediate push payload).

The adapter:
1. Calls `pf.parse_file(path)` → `(data, problems)`. If problems, raise ValueError.
2. Normalizes the payload: `{title, body, published, module_name, source_path}`.
3. Computes `source_digest` = SHA-256 over `{title, body, published, module_name}`.
4. Verifies targets against `config.active_courses()`.
5. Sets `target_key` = SHA-256(`content.page` + source_digest + course_id).
6. Sets `idempotency_key` = SHA-256(source_digest + course_id + normalized_title).

### 5.3 Review

For each target, `freeze_review` captures:
- Course name (PRIVATE)
- Page title
- Whether the page will be published
- Module name (if any)
- Baseline: current page with the same title in this course (if any), by exact title match
  only for baseline display — **never** for idempotency proof

`check_drift` at apply time: re-checks whether a page with the same title exists and
whether its body/published state matches the baseline. If the baseline page was deleted
or modified, drift is detected and review is invalidated.

### 5.4 Execute (two steps)

**Step 1: create_page**

1. Check for existing page by exact returned ID (if this is a retry and we have a
   `returned_object_id` from a previous attempt). If found, skip.
2. POST `/api/v1/courses/{cid}/pages` with `{wiki_page: {title, body, published}}`.
3. On success: persist `returned_object_id` = `resp.url` (Canvas page URL slug),
   `returned_object_url` = `resp.html_url`.
4. On timeout/disconnect/unparseable: return `sent_unknown`.
5. On 4xx: return `failed` with error code.

**Step 2: attach_module** (only if `module_name` is set and step 1 is applied/skipped)

1. If we have a `returned_object_id` from step 1, use it.
2. Find or create the module (`_find_or_create_module_id`).
3. POST module item with `{type: "Page", page_url: returned_object_id}`.
4. On success: mark step `applied`.
5. On timeout/disconnect: step is `sent_unknown`, target is `sent_unknown` (Attention).

### 5.5 Reconcile

For a `sent_unknown` target:

1. If we have a `returned_object_id` (page URL slug from a previous attempt):
   - GET `/api/v1/courses/{cid}/pages/{slug}` — if 200, page exists, target is `applied`.
   - If 404, page was not created, target is `pending` (eligible for retry).
2. If no `returned_object_id`:
   - GET `/api/v1/courses/{cid}/pages?per_page=100&search_term={title}`.
   - If an exact title match exists AND its body matches the source body hash, it *might*
     be ours — but **same-title matching is never proof**. Target stays `sent_unknown`.
   - If no exact title match, the page was likely not created. Target is `pending`.
3. If the Canvas call itself fails (timeout, 5xx), target stays `sent_unknown`.

### 5.6 Reversal

```python
def reversal_descriptor(self, payload, target):
    return {"supported": False, "method": None, "snapshot": None}
```

Page deletion is possible via `DELETE /api/v1/courses/{cid}/pages/{slug}`, but the
contract requires a "separately validated API path." Since we have not validated the
delete path in this slice, reversal is **unsupported**. The UI states this truthfully.

## 6. Route layer

### 6.1 New routes (all require `require_local_mutation`)

| Route | Method | Body | Returns |
|---|---|---|---|
| `/api/operations` | GET | — | `{ok, operations: [PII-minimized summaries]}` |
| `/api/operations/{kind}/prepare` | POST | kind-specific prepare request | `{ok, operation_id, review_summary}` |
| `/api/operation-batches/review` | POST | `{operation_ids: [...]}` | `{ok, batch_id, review_digest, frozen_reviews}` |
| `/api/operation-batches/{batch_id}/apply` | POST | `{review_digest}` | `{ok, operation_id, status, target_results}` |
| `/api/operations/{operation_id}/retry` | POST | — | `{ok, operation_id, status, target_results}` |

### 6.2 PII minimization

`GET /api/operations` returns only:
```json
{
  "operation_id": "op-...",
  "kind": "content.page",
  "status": "prepared",
  "target_count": 3,
  "created_at": "...",
  "updated_at": "..."
}
```

No course IDs, no payload, no target details. Private detail requires opening the
operation by ID (future route, not in this slice).

### 6.3 Server registration

`api/webui/routes/operations.py` exports `router`. `server.py` adds:
```python
from .routes.operations import router as _operations_router
app.include_router(_operations_router)
```

## 7. UI changes

### 7.1 Page panel (course_expert.html)

Add a "Prepare publication" button next to the existing "Push page…" button:

```html
<div class="actions">
  <button id="btn-pf-validate">Validate</button>
  <button id="btn-pf-prepare" class="secondary">Prepare publication</button>
  <button id="btn-pf-push" class="primary">Push page…</button>
</div>
```

The existing immediate push button stays — legacy `/api/content/push` remains for
compatibility. Both paths coexist.

### 7.2 page.js

New `btn-pf-prepare` handler:
1. Validates the file (same as existing validate).
2. POSTs to `/api/operations/content.page/prepare` with `{path, published, module_name}`.
3. Shows the prepared operation in the Summary panel (right rail).
4. "Review & Apply" button opens `CE_WRITE_REVIEW.confirm` with frozen review details.
5. On confirm, POSTs to `/api/operation-batches/{batch_id}/apply` with `{review_digest}`.

### 7.3 Summary panel

The Summary panel in `course_expert.html` (currently "Canvas unchanged.") gains:
- A list of prepared operations (from `GET /api/operations`).
- Each shows kind, status, target count.
- "Review & Apply" button for `reviewed` operations.
- "Retry" button for `attention` operations.

### 7.4 Review dialog

Reuse the existing `CE_WRITE_REVIEW.confirm`. The frozen review provides:
- `title`: "Review page publication"
- `action`: "Publish <title> to <N> course(s)"
- `targets`: list of course names
- `details`: page title, published state, module name
- `warnings`: "This will create a new page in each target course."
- `confirmText`: "Apply to Canvas"
- `cancelText`: "Cancel" (receives initial focus, per contract)

## 8. Test matrix

### 8.1 `test_operation_ledger.py` — schema, atomicity, concurrency

| Test | What it proves |
|---|---|
| Operation round-trip | Create → read → update preserves all fields |
| Target state transitions | Only valid transitions are accepted |
| Invalid kind rejected | Unknown kind raises ValueError |
| Concurrent claim acquisition | Two threads cannot claim the same target |
| Atomic failure preserves previous | If write fails, previous document is intact |
| Corrupt operations file quarantined | Bad JSON → quarantine, empty document |
| Lease expiry detection | Expired claims are detected on restart |
| Stale claim recovery | Dead-process claim is expired and reconciled |

### 8.2 `test_page_operation.py` — PageForge adapter

| Test | What it proves |
|---|---|
| Prepare with valid file | Operation created, source digest stored |
| Prepare with invalid file | ValueError raised |
| Prepare with unknown kind | 404 or 400 returned |
| Review freezes per-target summaries | Batch ID + digest returned |
| Apply creates pages | Mock Canvas POST called per target |
| Apply with drift | Review invalidated, apply blocked |
| Partial failure | Some targets applied, some failed |
| Timeout → sent_unknown | Canvas timeout → target is sent_unknown, no resend |
| Retry only unresolved | Applied targets not resent |
| Idempotent skip | If returned_object_id exists, page GET confirms, skip |
| Same-title is not proof | Reconcile with no returned ID stays sent_unknown |
| Module attachment after page | Step 2 only runs after step 1 is applied |
| Retry resumes module attachment | Uses recorded page ID, does not create second page |
| Reversal is unsupported | Descriptor returns supported: false |
| Receipt written per attempt | One receipt per apply, with target results |
| PII minimization | GET /api/operations has no course IDs or payload |
| Every mutation-guard rejection | Missing CSRF, bad origin, bad host → 403 |

### 8.3 Route contract

`test_route_contract.py` EXPECTED gains:
```python
('/api/operations', ('GET',)),
('/api/operations/{kind}/prepare', ('POST',)),
('/api/operation-batches/review', ('POST',)),
('/api/operation-batches/{batch_id}/apply', ('POST',)),
('/api/operations/{operation_id}/retry', ('POST',)),
```

## 9. Forbidden behavior

- Do not accept browser-supplied Canvas paths, endpoints, or method names.
- Do not use same-title or approximate-content matching as idempotency proof.
- Do not automatically resend a `sent_unknown` target.
- Do not retry an `applied` target.
- Do not persist operations, batches, or claims in the synced workspace or repo.
- Do not expose course IDs, student data, or payload in `GET /api/operations`.
- Do not skip the write-ahead flush before the Canvas call.
- Do not claim reversal is supported without a separately validated API path.
- Do not change the existing immediate `/api/content/push` route.
- Do not change the existing receipt store schema or behavior.

## 10. File ownership and load order

| File | Owner | New/Modified |
|---|---|---|
| `api/operation_ledger/models.py` | slice 10 | new |
| `api/operation_ledger/operations.py` | slice 10 | new |
| `api/operation_ledger/batches.py` | slice 10 | new |
| `api/operation_ledger/registry.py` | slice 10 | new |
| `api/operation_ledger/executor.py` | slice 10 | new |
| `api/operation_ledger/claims.py` | slice 10 | new |
| `api/operation_ledger/recovery.py` | slice 10 | new |
| `api/operation_ledger/adapters/__init__.py` | slice 10 | new |
| `api/operation_ledger/adapters/page.py` | slice 10 | new |
| `api/operation_ledger/paths.py` | slice 10 | modified (add operations_file, claims_file) |
| `api/operation_ledger/storage.py` | slice 10 | modified (add operations/claims read/write helpers) |
| `api/operation_ledger/__init__.py` | slice 10 | modified (re-export new modules) |
| `api/webui/routes/operations.py` | slice 10 | new |
| `api/webui/server.py` | slice 10 | modified (register operations router) |
| `api/webui/templates/course_expert.html` | slice 10 | modified (add Prepare button) |
| `api/webui/static/push/page.js` | slice 10 | modified (add prepare flow) |
| `api/tests/test_route_contract.py` | slice 10 | modified (add 5 routes) |
| `api/tests/test_operation_ledger.py` | slice 10 | new |
| `api/tests/test_page_operation.py` | slice 10 | new |
| `api/tests/test_webui_template_contracts.py` | slice 10 | modified (add operation panel contract) |

**Load order**: `paths.py` → `storage.py` → `models.py` → `claims.py` → `operations.py` →
`batches.py` → `registry.py` → `adapters/page.py` → `executor.py` → `recovery.py` →
`routes/operations.py` → `server.py` registration.

## 11. Verification strategy

```powershell
node --check api/webui/static/push/page.js
py -m pytest api/tests/test_operation_ledger.py api/tests/test_page_operation.py api/tests/test_push_service.py api/tests/test_route_contract.py api/tests/test_webui_template_contracts.py
git diff --check
```

Rendered verification (lifespan off, fake Canvas):
- Prepare a page operation → appears in Summary panel
- Review → frozen dialog with Cancel focus
- Apply → pages created (mock Canvas), receipt written
- Cancel → no Canvas call, no receipt
- Drift → review invalidated, apply blocked
- Partial failure → some targets applied, receipt shows partial
- Timeout → sent_unknown, Attention, no auto-resend
- Retry → only unresolved targets retried

No live Canvas call. No AI request. No routine execution.

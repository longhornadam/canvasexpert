"""Operation-ledger routes — prepare, review, apply, retry, list.

All mutation routes require ``require_local_mutation`` (CSRF + loopback +
same-origin). The browser never chooses Canvas paths, endpoints, or method
names — the adapter owns all Canvas interaction.
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.webui.local_request_guard import require_local_mutation

from api.operation_ledger import (
    batches, executor, models, operations, registry,
)
from api.operation_ledger.adapters import PageAdapter

# Ensure the adapter is registered (idempotent — __init__ also registers)
if not registry.is_registered(PageAdapter.kind):
    registry.register(PageAdapter())


router = APIRouter(tags=["operations"])


@router.get("/api/operations")
def list_operations_route():
    """PII-minimized list of all operations. No course IDs or payload."""
    return {"ok": True, "operations": operations.list_operations_pii_minimized()}


@router.post("/api/operations/{kind}/prepare")
def prepare_operation(kind: str, request: Request):
    """Prepare an operation for later review and apply.

    Body: kind-specific prepare request (e.g. ``{path, published, module_name?}``
    for ``content.page``).
    """
    require_local_mutation(request)

    try:
        adapter = registry.get_adapter(kind)
    except ValueError:
        return JSONResponse(
            status_code=404,
            content={"ok": False, "error": f"unknown operation kind: {kind}"},
        )

    import json
    try:
        body = json.loads(request._body.decode("utf-8")) if request._body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "invalid JSON body"},
        )

    # Build payload (validates source)
    try:
        payload = adapter.build_payload(body)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": str(exc)},
        )

    source_digest = adapter.source_digest(payload)

    # Verify targets — use active courses as the target list
    from api.webui import config
    targets_in = [{"course_id": str(c["id"])} for c in config.active_courses()]
    try:
        targets = adapter.verify_targets(payload, targets_in)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": str(exc)},
        )

    # Build target records with baselines
    target_records = []
    for t in targets:
        baseline = adapter.capture_baseline(payload, t)
        target_records.append(models.new_target(
            target_key=t["target_key"],
            idempotency_key=t["idempotency_key"],
            course_id=t["course_id"],
            baseline=baseline,
        ))

    operation_id = models.new_operation_id()
    source_ref = {"type": "workspace_relative", "value": payload.get("source_path", "")}
    op = models.new_operation(
        operation_id=operation_id,
        kind=kind,
        source_ref=source_ref,
        source_digest=source_digest,
        normalized_payload=payload,
        targets=target_records,
    )

    operations.create_operation(op)

    # Build review summary for the response
    review_summary = _build_review_summary(adapter, payload, target_records)

    return {
        "ok": True,
        "operation_id": operation_id,
        "review_summary": review_summary,
    }


@router.post("/api/operation-batches/review")
def review_batch(request: Request):
    """Freeze a review snapshot for a set of operations.

    Body: ``{operation_ids: ["op-...", ...]}``.
    Returns ``{ok, batch_id, review_digest, frozen_reviews}``.
    """
    require_local_mutation(request)

    import json
    try:
        body = json.loads(request._body.decode("utf-8")) if request._body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "invalid JSON body"},
        )

    op_ids = body.get("operation_ids")
    if not isinstance(op_ids, list) or not op_ids:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "operation_ids must be a non-empty list"},
        )

    frozen_by_op = {}
    for op_id in op_ids:
        op = operations.get_operation(op_id)
        if op is None:
            return JSONResponse(
                status_code=404,
                content={"ok": False, "error": f"operation {op_id} not found"},
            )
        adapter = registry.get_adapter(op["kind"])
        payload = op["normalized_payload"]
        frozen = []
        for target in op.get("targets", []):
            baseline = target.get("baseline", {})
            frozen.append(adapter.freeze_review(payload, target, baseline))
        frozen_by_op[op_id] = frozen

    batch = batches.freeze_batch(op_ids, frozen_by_op)

    # Persist the batch on each operation
    for op_id in op_ids:
        operations.set_operation_review(op_id, batch)

    return {
        "ok": True,
        "batch_id": batch["batch_id"],
        "review_digest": batch["review_digest"],
        "frozen_reviews": batch["frozen_reviews"],
    }


@router.post("/api/operation-batches/{batch_id}/apply")
def apply_batch(batch_id: str, request: Request):
    """Apply a reviewed batch to Canvas.

    Body: ``{review_digest: "..."}``.
    """
    require_local_mutation(request)

    import json
    try:
        body = json.loads(request._body.decode("utf-8")) if request._body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "invalid JSON body"},
        )

    review_digest = body.get("review_digest")
    if not review_digest:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "review_digest is required"},
        )

    # Find the operation that has this batch_id
    all_ops = operations.list_operations()
    target_op = None
    for op in all_ops:
        review = op.get("review")
        if review and review.get("batch_id") == batch_id:
            target_op = op
            break

    if target_op is None:
        return JSONResponse(
            status_code=404,
            content={"ok": False, "error": f"batch {batch_id} not found"},
        )

    try:
        result = executor.apply_operation(
            target_op["operation_id"], batch_id, review_digest)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": str(exc)},
        )

    return result


@router.post("/api/operations/{operation_id}/retry")
def retry_operation(operation_id: str, request: Request):
    """Retry only unresolved targets in an operation."""
    require_local_mutation(request)

    try:
        result = executor.retry_operation(operation_id)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": str(exc)},
        )

    return result


# ── Helpers ─────────────────────────────────────────────────────────────

def _build_review_summary(adapter, payload: dict, targets: list[dict]) -> dict:
    """Build a PII-minimized review summary for the prepare response."""
    frozen = []
    for target in targets:
        baseline = target.get("baseline", {})
        frozen.append(adapter.freeze_review(payload, target, baseline))

    return {
        "kind": adapter.kind,
        "target_count": len(targets),
        "frozen_reviews": frozen,
        "reversal_supported": False,
    }

"""Assistant-facing SIS grade-bridge use case.

This is the shared non-HTTP boundary used by MCP.  Live Canvas behavior stays
inside the ledger adapter; this module creates one frozen operation and shapes
only aggregate, student-free results.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone

from api.operation_ledger import batches, executor, models, operations, receipts, registry
from api.operation_ledger.adapters.sis_grade_bridge import KIND
from api.platform_services import config


def _current_course(course_id: str) -> bool:
    wanted = str(course_id or "").strip()
    return bool(wanted) and wanted in {
        str(course.get("id") or "").strip()
        for course in config.active_courses()
    }


def list_sis_grade_bridges(course_id: str) -> dict:
    course_key = str(course_id or "").strip()
    if not course_key:
        return {"ok": False, "error": "course_id is required"}
    saved_ids = {
        str(course.get("id") or "").strip()
        for course in [*(config.saved_courses() or []), *(config.active_courses() or [])]
        if str(course.get("id") or "").strip()
    }
    if course_key not in saved_ids:
        return {
            "ok": False,
            "error": (
                f"Unknown course_id '{course_key}'; call list_courses and use a "
                "returned course_id."
            ),
        }
    if not _current_course(course_key):
        return {"ok": False, "error": "course is not in Current courses"}
    try:
        records = config.list_sis_grade_bridges(course_key)
    except Exception:
        return {"ok": False, "error": "bridge registrations could not be read"}
    return {
        "ok": True,
        "course_id": course_key,
        "bridges": [
            {
                "family_title": record.get("family_title"),
                "source_count": len(record.get("source_assignment_ids") or []),
                "bridge_assignment_id": record.get("bridge_assignment_id"),
                "registered": True,
            }
            for record in records
        ],
    }


def preview_sis_grade_bridge(course_id: str, family_title: str) -> dict:
    course_key = str(course_id or "").strip()
    title = str(family_title or "").strip()
    if not course_key or not title:
        return {"ok": False, "error": "course_id and family_title are required"}
    if not _current_course(course_key):
        return {"ok": False, "error": "course is not in Current courses"}

    adapter = registry.get_adapter(KIND)
    try:
        registration = config.get_sis_grade_bridge(course_key, title)
        payload = adapter.build_payload({
            "course_id": course_key,
            "family_title": title,
            "registration": registration,
        })
        provisional = adapter.verify_targets(
            payload, [{"course_id": course_key}]
        )[0]
        baseline = adapter.capture_baseline(payload, provisional)
        if baseline.get("blocking_error"):
            return {
                "ok": False,
                "error": baseline["blocking_error"],
                "blocking": True,
            }
        payload = adapter.freeze_payload(payload, baseline)
        target = adapter.verify_targets(
            payload, [{"course_id": course_key}]
        )[0]
        # Re-read once against the frozen identity so the persisted baseline is
        # already the exact state that apply will drift-check.
        baseline = adapter.capture_baseline(payload, target)
        if baseline.get("blocking_error"):
            return {
                "ok": False,
                "error": baseline["blocking_error"],
                "blocking": True,
            }

        target_record = models.new_target(
            target_key=target["target_key"],
            idempotency_key=target["idempotency_key"],
            course_id=target["course_id"],
            baseline=baseline,
            steps=adapter.initial_steps(payload, baseline),
        )
        operation_id = models.new_operation_id()
        operation = models.new_operation(
            operation_id=operation_id,
            kind=KIND,
            source_ref={"type": "sis_grade_bridge"},
            source_digest=adapter.source_digest(payload),
            normalized_payload=payload,
            targets=[target_record],
        )
        operations.create_operation(operation)
        frozen = adapter.freeze_review(payload, target_record, baseline)
        batch = batches.freeze_batch(
            [operation_id], {operation_id: [frozen]}
        )
        operations.set_operation_review(operation_id, batch)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "blocking": True}
    except Exception:
        return {"ok": False, "error": "bridge preview could not be prepared"}

    return {
        "ok": True,
        "operation_id": operation_id,
        "batch_id": batch["batch_id"],
        "review_digest": batch["review_digest"],
        "preview": frozen,
    }


def apply_sis_grade_bridge(
    operation_id: str, batch_id: str, review_digest: str
) -> dict:
    operation_key = str(operation_id or "").strip()
    batch_key = str(batch_id or "").strip()
    digest = str(review_digest or "").strip()
    if not operation_key or not batch_key or not digest:
        return {
            "ok": False,
            "error": "operation_id, batch_id, and review_digest are required",
        }
    operation = operations.get_operation(operation_key)
    if operation is None or operation.get("kind") != KIND:
        return {"ok": False, "error": "bridge operation was not found"}
    try:
        result = executor.apply_operation(operation_key, batch_key, digest)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:
        return {"ok": False, "error": "bridge apply could not complete"}

    return _result_projection(operation_key, result, operation)


def confirm_sis_grade_bridge_passback(
    operation_id: str, observed_last_sync_at: str,
) -> dict:
    operation_key = str(operation_id or "").strip()
    observed_text = str(observed_last_sync_at or "").strip()
    if not operation_key or not observed_text:
        return {
            "ok": False,
            "error": "operation_id and observed_last_sync_at are required",
        }

    observed = _aware_datetime(observed_text)
    if observed is None:
        return {"ok": False, "error": "observed_last_sync_at must be timezone-aware ISO 8601"}

    operation = operations.get_operation(operation_key)
    error = _confirmation_error(operation, observed)
    if error:
        return {"ok": False, "error": error}

    adapter = registry.get_adapter(KIND)
    target = operation["targets"][0]
    fresh = adapter.capture_baseline(operation["normalized_payload"], target)
    if (
        fresh.get("blocking_error")
        or fresh.get("validation_digest")
        != (target.get("baseline") or {}).get("validation_digest")
    ):
        return {"ok": False, "error": "bridge operation state has drifted"}

    observed_canonical = observed.isoformat()

    def confirm(candidate: dict) -> dict:
        candidate_error = _confirmation_error(candidate, observed)
        if candidate_error:
            raise ValueError(candidate_error)
        candidate_target = candidate["targets"][0]
        step = next(
            row for row in candidate_target["steps"]
            if row.get("step_key") == "post_grades"
        )
        step.update({
            "state": "applied",
            "error_code": None,
            "private_diagnostic": None,
            "passback_state": "confirmed",
            "external_evidence": {
                "kind": "teacher_observed_canvas_grade_sync_last_sync",
                "observed_last_sync_at": observed_canonical,
            },
            "updated_at": models.now_iso(),
        })
        return candidate

    try:
        operations.update_operation(operation_key, confirm)
        result = executor.retry_operation(operation_key)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:
        return {"ok": False, "error": "bridge passback confirmation could not complete"}

    projected = _result_projection(operation_key, result, operation)
    projected["passback_evidence"] = {
        "kind": "teacher_observed_canvas_grade_sync_last_sync",
        "observed_last_sync_at": observed_canonical,
    }
    return projected


def _confirmation_error(operation: dict | None, observed: datetime) -> str | None:
    if operation is None or operation.get("kind") != KIND:
        return "bridge operation was not found"
    if operation.get("status") != "attention":
        return "bridge operation is not awaiting passback confirmation"
    targets = operation.get("targets") or []
    if len(targets) != 1:
        return "bridge operation is not structurally confirmable"
    target = targets[0]
    if target.get("state") not in {"blocked", "sent_unknown"}:
        return "bridge target is not awaiting passback confirmation"
    steps = target.get("steps") or []
    post_steps = [row for row in steps if row.get("step_key") == "post_grades"]
    register_steps = [row for row in steps if row.get("step_key") == "register_bridge"]
    if len(post_steps) != 1 or len(register_steps) != 1:
        return "bridge operation is not structurally confirmable"
    post_step = post_steps[0]
    register_step = register_steps[0]
    other_incomplete = [
        row for row in steps
        if row.get("step_key") not in {"post_grades", "register_bridge"}
        and row.get("state") != "applied"
    ]
    if other_incomplete or register_step.get("state") != "pending":
        return "passback is not the sole incomplete outbound effect"
    diagnostic = str(post_step.get("private_diagnostic") or "")
    ambiguous = (
        post_step.get("state") == "sent_unknown"
        or (
            post_step.get("state") == "blocked"
            and diagnostic.startswith("HTTP 5")
        )
    )
    if not ambiguous or post_step.get("external_evidence"):
        return "passback outcome is not eligible for evidence confirmation"
    marker = _aware_datetime(str(post_step.get("outbound_started_at") or ""))
    if marker is None:
        return "passback outbound marker is missing or invalid"
    if observed < marker:
        return "observed Last Sync predates the passback request"
    if not target.get("returned_object_id"):
        return "bridge assignment checkpoint is missing"
    return None


def _aware_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _result_projection(operation_key: str, result: dict, fallback: dict) -> dict:
    stored = operations.get_operation(operation_key) or fallback
    target = (stored.get("targets") or [{}])[0]
    baseline = target.get("baseline") or {}
    step_rows = [
        {
            "step_key": step.get("step_key"),
            "state": step.get("state"),
            "error_code": step.get("error_code"),
        }
        for step in (target.get("steps") or [])
    ]
    passback_step = next(
        (step for step in target.get("steps", [])
         if step.get("step_key") == "post_grades"),
        {},
    )
    receipt_id = None
    for receipt in receipts.list_receipts():
        if receipt.get("subject_id") == operation_key:
            receipt_id = receipt.get("receipt_id")
            break
    return {
        "ok": bool(result.get("ok")),
        "operation_id": operation_key,
        "status": result.get("status"),
        "counts": copy.deepcopy(baseline.get("counts") or {}),
        "warnings": copy.deepcopy(baseline.get("warnings") or []),
        "bridge_assignment_id": target.get("returned_object_id"),
        "bridge_url": target.get("returned_object_url"),
        "passback": (
            "accepted" if passback_step.get("state") == "applied"
            else "uncertain" if passback_step.get("state") == "sent_unknown"
            else "not_accepted"
        ),
        "steps": step_rows,
        "receipt_id": receipt_id,
    }


__all__ = [
    "list_sis_grade_bridges",
    "preview_sis_grade_bridge",
    "apply_sis_grade_bridge",
    "confirm_sis_grade_bridge_passback",
]

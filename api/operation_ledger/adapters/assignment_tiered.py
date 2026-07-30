"""Tiered assignment execution and reconciliation helpers."""

from __future__ import annotations

from .. import models
from .adapter_support import build_result, ensure_step, find_step
from .module_placement import attach_assignment_type_module_item
from api.webui import canvas_client


def execute(
    payload: dict,
    target: dict,
    baseline: dict,
    context,
    *,
    ordered_steps,
    resolve_assignment_groups,
    group_resolution_error,
    find_assignment_group,
    autoscore_queue_factory,
    autoscore_settings,
    autoscore_push_policy,
    schedule_autoscore,
    active_course_name,
    as_bool,
    read_modules,
) -> dict:
    course_id = target["course_id"]
    tiers = payload["tiers"]
    steps = ordered_steps(target)
    try:
        resolved = resolve_assignment_groups(course_id, tiers)
    except group_resolution_error:
        return build_result("failed", steps=steps, error_code="group_resolution_failed")
    if resolved["safe"] != baseline.get("group_snapshot"):
        return build_result("failed", steps=steps, error_code="group_membership_drift")

    safe_by_index = {row["index"]: row for row in resolved["safe"]["tiers"]}
    transient_ids = resolved["student_ids_by_group"]

    for index, tier in enumerate(tiers):
        assignment_key = f"create_tier_assignment:{index}"
        override_key = f"create_tier_override:{index}"
        assignment_step = ensure_step(steps, assignment_key)
        assignment_id = assignment_step.get("returned_object_id")
        assignment_url = assignment_step.get("returned_object_url")

        if assignment_id:
            existing, error = canvas_client._canvas_get(
                f"/api/v1/courses/{course_id}/assignments/{assignment_id}"
            )
            if error or not existing:
                return build_result("sent_unknown", steps=steps, error_code="assignment_exact_id_unverified")
            assignment_step["state"] = "skipped"
            assignment_url = existing.get("html_url") or assignment_url
        elif assignment_step.get("outbound_started_at"):
            return build_result("sent_unknown", steps=steps, error_code="assignment_creation_unresolved")
        else:
            assignment_data = _assignment_data(payload, tier["description"], course_id, find_assignment_group)
            assignment_data["only_visible_to_overrides"] = True
            request = {"assignment": assignment_data}
            path = f"/api/v1/courses/{course_id}/assignments"
            marked = context.before_send(
                assignment_key,
                models.sha256_dict({"method": "POST", "path": path, "payload": request}),
            )
            _replace_local_step(steps, marked)
            response, error = canvas_client._canvas_send("POST", path, request)
            if error:
                state = "sent_unknown" if _is_uncertain(error) else _tier_failure_state(steps)
                marked["state"] = state if state == "sent_unknown" else "failed"
                marked["error_code"] = "timeout_or_disconnect" if state == "sent_unknown" else "canvas_rejected"
                marked["private_diagnostic"] = type(error).__name__
                marked = context.checkpoint_step(marked)
                _replace_local_step(steps, marked)
                return build_result(state, steps=steps, error_code=marked["error_code"])
            assignment_id = str(response.get("id")) if isinstance(response, dict) and response.get("id") is not None else None
            assignment_url = response.get("html_url") if isinstance(response, dict) else None
            if not assignment_id:
                marked["state"] = "sent_unknown"
                marked["error_code"] = "unparseable_response"
                marked["private_diagnostic"] = "missing assignment id"
                marked = context.checkpoint_step(marked)
                _replace_local_step(steps, marked)
                return build_result("sent_unknown", steps=steps, error_code="unparseable_response")
            marked["state"] = "applied"
            marked = context.checkpoint_step(
                marked,
                returned_object_id=assignment_id,
                returned_object_url=assignment_url,
            )
            _replace_local_step(steps, marked)

        override_step = ensure_step(steps, override_key)
        override_id = override_step.get("returned_object_id")
        if override_id:
            existing, error = canvas_client._canvas_get(
                f"/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides/{override_id}"
            )
            if error or not existing:
                return build_result("sent_unknown", steps=steps, error_code="override_exact_id_unverified")
            override_step["state"] = "skipped"
        elif override_step.get("outbound_started_at"):
            return build_result("sent_unknown", steps=steps, error_code="override_creation_unresolved")
        else:
            safe_tier = safe_by_index[index]
            override_request = {
                "assignment_override": {
                    "title": f"{tier['label']} assignment access",
                    "student_ids": transient_ids[safe_tier["group_id"]],
                }
            }
            for key in ("due_at", "unlock_at", "lock_at"):
                if payload.get(key):
                    override_request["assignment_override"][key] = payload[key]
            path = f"/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides"
            marked = context.before_send(
                override_key,
                models.sha256_dict(
                    {
                        "method": "POST",
                        "path": path,
                        "membership_digest": safe_tier["membership_digest"],
                    }
                ),
            )
            _replace_local_step(steps, marked)
            response, error = canvas_client._canvas_send("POST", path, override_request)
            if error:
                state = "sent_unknown" if _is_uncertain(error) else "partial"
                marked["state"] = state if state == "sent_unknown" else "failed"
                marked["error_code"] = "timeout_or_disconnect" if state == "sent_unknown" else "override_rejected"
                marked["private_diagnostic"] = type(error).__name__
                marked = context.checkpoint_step(marked)
                _replace_local_step(steps, marked)
                return build_result(state, steps=steps, error_code=marked["error_code"])
            override_id = str(response.get("id")) if isinstance(response, dict) and response.get("id") is not None else None
            if not override_id:
                marked["state"] = "sent_unknown"
                marked["error_code"] = "unparseable_response"
                marked["private_diagnostic"] = "missing override id"
                marked = context.checkpoint_step(marked)
                _replace_local_step(steps, marked)
                return build_result("sent_unknown", steps=steps, error_code="unparseable_response")
            marked["state"] = "applied"
            marked = context.checkpoint_step(marked, returned_object_id=override_id)
            _replace_local_step(steps, marked)

        if payload.get("module_name"):
            result = attach_assignment_type_module_item(
                course_id=course_id,
                content_id=assignment_id,
                title=payload["name"],
                module_name=payload["module_name"],
                steps=steps,
                context=context,
                attach_step_key=f"attach_module:{index}",
                returned_object_id=assignment_id,
                deterministic_failure_state="failed",
                read_modules=read_modules,
            )
            if result.get("state") != "applied":
                if result.get("state") == "failed":
                    result["state"] = "partial"
                return result

        if payload.get("autoscore_schedule"):
            result = _schedule_tier_autoscore(
                payload,
                course_id,
                assignment_id,
                index,
                steps,
                context,
                autoscore_queue_factory=autoscore_queue_factory,
                autoscore_settings=autoscore_settings,
                autoscore_push_policy=autoscore_push_policy,
                schedule_autoscore=schedule_autoscore,
                active_course_name=active_course_name,
                as_bool=as_bool,
            )
            if result is not None:
                return result

    return build_result("applied", steps=steps, returned_object_id=None, returned_object_url=None)


def reconcile(payload: dict, target: dict, *, ordered_steps, autoscore_queue_factory) -> dict:
    course_id = target["course_id"]
    stored_steps = ordered_steps(target)
    projected = []
    module_step = find_step(stored_steps, "create_module")
    module_id = module_step.get("returned_object_id")

    if payload.get("module_name") and module_id:
        module, error = canvas_client._canvas_get(f"/api/v1/courses/{course_id}/modules/{module_id}")
        if error or not module or str(module.get("id")) != str(module_id):
            return _tier_reconcile_result("sent_unknown", projected)
        projected.append(_applied_safe_step(module_step))

    for index, _tier in enumerate(payload.get("tiers") or []):
        assignment_step = find_step(stored_steps, f"create_tier_assignment:{index}")
        assignment_id = assignment_step.get("returned_object_id")
        if not assignment_id:
            return _tier_reconcile_unfinished(assignment_step, projected)
        assignment, error = canvas_client._canvas_get(
            f"/api/v1/courses/{course_id}/assignments/{assignment_id}"
        )
        if error or not assignment or str(assignment.get("id")) != str(assignment_id):
            return _tier_reconcile_result("sent_unknown", projected)
        projected.append(_applied_safe_step(assignment_step, returned_object_url=assignment.get("html_url")))

        override_step = find_step(stored_steps, f"create_tier_override:{index}")
        override_id = override_step.get("returned_object_id")
        if not override_id:
            return _tier_reconcile_unfinished(override_step, projected)
        override, error = canvas_client._canvas_get(
            f"/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides/{override_id}"
        )
        if error or not override or str(override.get("id")) != str(override_id):
            return _tier_reconcile_result("sent_unknown", projected)
        projected.append(_applied_safe_step(override_step))

        if payload.get("module_name"):
            attach_step = find_step(stored_steps, f"attach_module:{index}")
            item_id = attach_step.get("returned_object_id")
            step_module_id = attach_step.get("module_id") or module_id
            if not item_id or not step_module_id:
                return _tier_reconcile_unfinished(attach_step, projected)
            item, error = canvas_client._canvas_get(
                f"/api/v1/courses/{course_id}/modules/{step_module_id}/items/{item_id}"
            )
            if (
                error
                or not item
                or str(item.get("id")) != str(item_id)
                or str(item.get("type", "")).casefold() != "assignment"
                or str(item.get("content_id")) != str(assignment_id)
            ):
                return _tier_reconcile_result("sent_unknown", projected)
            projected.append(_applied_safe_step(attach_step))

        if payload.get("autoscore_schedule"):
            schedule_step = find_step(stored_steps, f"schedule_autoscore:{index}")
            expected_job_id = autoscore_queue_factory().make_job_id(course_id, assignment_id)
            if not schedule_step.get("returned_object_id"):
                return _tier_reconcile_unfinished(schedule_step, projected)
            if str(schedule_step.get("returned_object_id")) != str(expected_job_id):
                return _tier_reconcile_result("sent_unknown", projected)
            try:
                jobs = (autoscore_queue_factory().load_queue() or {}).get("jobs", [])
            except Exception:
                return _tier_reconcile_result("sent_unknown", projected)
            job = next((row for row in jobs if str(row.get("job_id")) == str(expected_job_id)), None)
            if not job or str(job.get("course_id")) != str(course_id) or str(job.get("assignment_id")) != str(assignment_id):
                return _tier_reconcile_result("sent_unknown", projected)
            projected.append(_applied_safe_step(schedule_step))

    return _tier_reconcile_result("applied", projected)


def _tier_reconcile_unfinished(step: dict, projected: list[dict]) -> dict:
    state = "sent_unknown" if step.get("outbound_started_at") else "pending"
    return _tier_reconcile_result(state, projected)


def _tier_reconcile_result(state: str, steps: list[dict]) -> dict:
    return {
        "state": state,
        "returned_object_id": None,
        "returned_object_url": None,
        "steps": steps,
    }


def _applied_safe_step(step: dict, returned_object_url=None) -> dict:
    return {
        "step_key": step.get("step_key"),
        "state": "applied",
        "returned_object_id": step.get("returned_object_id"),
        "returned_object_url": returned_object_url or step.get("returned_object_url"),
        "error_code": None,
    }


def _assignment_data(payload: dict, description: str, course_id: str, find_assignment_group) -> dict:
    data = {
        "name": payload.get("name", "Untitled assignment"),
        "submission_types": payload.get("submission_types", ["online_text_entry"]),
    }
    if description:
        data["description"] = description
    if payload.get("points") is not None:
        data["points_possible"] = float(payload["points"])
    for key in ("allowed_extensions", "external_tool_tag_attributes"):
        if payload.get(key):
            data[key] = payload[key]
    for key in ("due_at", "unlock_at", "lock_at"):
        if payload.get(key):
            data[key] = payload[key]
    if payload.get("post_to_sis"):
        data["post_to_sis"] = True
    if payload.get("published"):
        data["published"] = True
    assignment_group_name = payload.get("assignment_group_name")
    if assignment_group_name:
        group_id = find_assignment_group(course_id, assignment_group_name)
        if group_id is not None:
            data["assignment_group_id"] = group_id
    return data


def _tier_failure_state(steps: list[dict]) -> str:
    return "partial" if any(
        step.get("state") in ("applied", "skipped") and step.get("returned_object_id")
        for step in steps
    ) else "failed"


def _schedule_tier_autoscore(
    payload,
    course_id,
    assignment_id,
    index,
    steps,
    context,
    *,
    autoscore_queue_factory,
    autoscore_settings,
    autoscore_push_policy,
    schedule_autoscore,
    active_course_name,
    as_bool,
):
    queue = autoscore_queue_factory()
    settings = autoscore_settings(payload)
    policy = autoscore_push_policy(payload)
    job_id = queue.make_job_id(course_id, assignment_id)
    key = f"schedule_autoscore:{index}"
    step = ensure_step(steps, key)
    if step.get("returned_object_id") == job_id and step.get("state") in ("applied", "skipped"):
        step["state"] = "skipped"
        return None
    marked = context.before_send(
        key,
        models.sha256_dict(
            {
                "assignment_id": assignment_id,
                "due_at": payload.get("due_at"),
                "settings": settings,
                "auto_push": as_bool(payload.get("autoscore_auto_push")),
                "push_policy": policy,
            }
        ),
    )
    _replace_local_step(steps, marked)
    try:
        job = schedule_autoscore(
            course_id=course_id,
            course_name=active_course_name(course_id),
            assignment_id=assignment_id,
            assignment_name=payload["name"],
            payload=payload,
            settings=settings,
            push_policy=policy,
            queue=queue,
        )
        if str(job.get("job_id") or job_id) != job_id:
            raise ValueError("unexpected queue job ID")
        marked["state"] = "applied"
        marked = context.checkpoint_step(marked, returned_object_id=job_id)
        _replace_local_step(steps, marked)
        return None
    except Exception as exc:
        marked["state"] = "failed"
        marked["error_code"] = "autoscore_queue_failed"
        marked["private_diagnostic"] = type(exc).__name__
        marked = context.checkpoint_step(marked)
        _replace_local_step(steps, marked)
        return build_result("partial", steps=steps, error_code="autoscore_queue_failed")


def _replace_local_step(steps: list[dict], step: dict) -> None:
    for index, existing in enumerate(steps):
        if existing.get("step_key") == step.get("step_key"):
            steps[index] = step
            return
    steps.append(step)


def _is_uncertain(error: str) -> bool:
    lower = str(error or "").lower()
    return any(
        term in lower
        for term in (
            "timeout",
            "timed out",
            "connection",
            "network",
            "unparseable",
            "no response",
            "read timed out",
        )
    )
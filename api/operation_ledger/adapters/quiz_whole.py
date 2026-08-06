"""Whole-class quiz execution and reconciliation helpers."""

from __future__ import annotations

from .adapter_support import as_list, build_result, find_step, has_outbound_marker, module_id_from_steps, normalize, prepend_step
from . import quiz_steps
from api.platform_services import canvas_client, config


def execute(payload: dict, target: dict, context, *, ordered_steps) -> dict:
    course_id = target["course_id"]
    plan = payload.get("plan", {})
    title = plan.get("title", "Untitled quiz")
    steps = ordered_steps(target)
    quiz_id, quiz_url, result = quiz_steps.ensure_quiz(
        course_id=course_id,
        step_key="create_quiz:0",
        quiz_payload=plan.get("quiz_payload", {}),
        steps=steps,
        context=context,
        current_quiz_id=target.get("returned_object_id"),
        current_quiz_url=target.get("returned_object_url"),
        failure_state="failed",
    )
    if result is not None:
        return result

    for item in plan.get("items", []):
        result = quiz_steps.ensure_item(
            course_id=course_id,
            quiz_id=quiz_id,
            quiz_url=quiz_url,
            step_key=f"create_item:0:{item.get('index', 0)}",
            item_payload=item.get("payload", {}),
            steps=steps,
            context=context,
            failure_state="failed",
        )
        if result is not None:
            return result

    assignment_settings = plan.get("assignment_settings", {})
    if assignment_settings:
        result = quiz_steps.patch_assignment(
            course_id=course_id,
            quiz_id=quiz_id,
            quiz_url=quiz_url,
            step_key="patch_assignment:0",
            assignment_settings=assignment_settings,
            steps=steps,
            context=context,
            failure_state="failed",
        )
        if result is not None:
            return result

    module_name = (plan.get("module", {}) or {}).get("module_name")
    if module_name and quiz_id:
        result = quiz_steps.attach_module(
            course_id=course_id,
            quiz_id=quiz_id,
            title=title,
            module_name=module_name,
            steps=steps,
            context=context,
            attach_step_key="attach_module:0",
            failure_state="failed",
        )
        if result.get("state") != "applied":
            return result

    return build_result("applied", steps=steps, returned_object_id=quiz_id, returned_object_url=quiz_url)


def reconcile(payload: dict, target: dict, *, ordered_steps) -> dict:
    course_id = target["course_id"]
    plan = payload.get("plan", {})
    title = plan.get("title", "")
    steps = ordered_steps(target)
    quiz_step = prepend_step(steps, "create_quiz:0")
    quiz_id = target.get("returned_object_id") or quiz_step.get("returned_object_id")
    has_marker = has_outbound_marker(steps)

    if not quiz_id:
        assignments, error = canvas_client.canvas_get(
            f"/api/v1/courses/{course_id}/assignments",
            params={"per_page": 100, "search_term": title},
        )
        if error:
            return {"state": "sent_unknown"}
        if any(normalize(assignment.get("name")) == normalize(title) for assignment in as_list(assignments)):
            return {"state": "sent_unknown"}
        return {"state": "sent_unknown" if has_marker else "pending"}

    quiz, error = canvas_client.canvas_get(f"/api/quiz/v1/courses/{course_id}/quizzes/{quiz_id}")
    if error:
        if "404" in str(error) and not quiz_step.get("outbound_started_at"):
            return {"state": "pending"}
        return {"state": "sent_unknown"}
    if not quiz:
        return {"state": "sent_unknown"}

    result = {
        "state": "applied",
        "returned_object_id": quiz_id,
        "returned_object_url": f"{config.get_canvas_base()}/courses/{course_id}/assignments/{quiz_id}",
    }
    for item in plan.get("items", []):
        item_step = find_step(steps, f"create_item:0:{item.get('index', 0)}")
        item_id = item_step.get("returned_object_id")
        if not item_id:
            return {"state": "sent_unknown" if has_marker else "pending", "returned_object_id": quiz_id}
        verify, verify_error = canvas_client.canvas_get(
            f"/api/quiz/v1/courses/{course_id}/quizzes/{quiz_id}/items/{item_id}"
        )
        if verify_error or not verify:
            return {"state": "sent_unknown", "returned_object_id": quiz_id}

    module_name = (plan.get("module", {}) or {}).get("module_name")
    if not module_name:
        return result
    create_module_step = find_step(steps, "create_module")
    attach_step = find_step(steps, "attach_module:0")
    module_id = module_id_from_steps(create_module_step, attach_step)
    if not module_id:
        return {"state": "sent_unknown" if has_marker else "pending", "returned_object_id": quiz_id}
    item_id = attach_step.get("returned_object_id")
    if item_id:
        item, item_error = canvas_client.canvas_get(f"/api/v1/courses/{course_id}/modules/{module_id}/items/{item_id}")
        if not item_error and item:
            if str(item.get("type", "")).lower() == "assignment" and str(item.get("content_id")) == str(quiz_id):
                result["module_item_id"] = item_id
                return result
    items_list, item_error = canvas_client.canvas_get_all(
        f"/api/v1/courses/{course_id}/modules/{module_id}/items",
        {"per_page": 100},
    )
    if item_error:
        return {"state": "sent_unknown", "returned_object_id": quiz_id}
    matches = [
        item for item in (items_list or [])
        if str(item.get("type", "")).lower() == "assignment" and str(item.get("content_id")) == str(quiz_id)
    ]
    if len(matches) == 1 and matches[0].get("id") is not None:
        result["module_item_id"] = str(matches[0]["id"])
        return result
    if attach_step.get("outbound_started_at") or has_marker:
        return {"state": "sent_unknown", "returned_object_id": quiz_id}
    return {"state": "pending", "returned_object_id": quiz_id}
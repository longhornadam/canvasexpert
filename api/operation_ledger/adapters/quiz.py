"""QuizForge adapter for the crash-safe ``content.quiz`` operation kind.

Pure plan subprocess, then checkpointed New Quiz create/item/assignment/module
writes with exact-ID reconciliation. No differentiated mode in this slice.
"""
from __future__ import annotations

import json

from .. import models
from api.webui import canvas_client, config
from api.webui.runner import run_json_object


KIND = "content.quiz"


class QuizAdapter:
    kind = KIND

    # ── Payload ──────────────────────────────────────────────────────────

    def build_payload(self, prepare_request: dict) -> dict:
        mode = prepare_request.get("mode", "whole")
        if mode != "whole":
            raise ValueError(
                f"mode={mode!r} is not supported in this slice; "
                "use mode='whole'"
            )
        path = prepare_request.get("path")
        if not path:
            raise ValueError("path is required")
        settings = prepare_request.get("settings") or {}

        # Run the no-network plan subprocess
        plan = run_json_object(
            ["qf_pusher.py", path, "--plan-json"],
            extra_env={"QF_PUSH_SETTINGS": json.dumps(settings)},
        )
        if not isinstance(plan, dict):
            raise ValueError("planner did not return a JSON object")
        if plan.get("version") != 1:
            raise ValueError(f"unsupported plan version {plan.get('version')}")
        if not plan.get("title"):
            raise ValueError("plan missing title")
        items = plan.get("items", [])
        if not items:
            raise ValueError("plan has no items")
        quiz_payload = plan.get("quiz_payload")
        if not isinstance(quiz_payload, dict) or "quiz" not in quiz_payload:
            raise ValueError("plan missing quiz_payload")

        return {
            "mode": mode,
            "path": path,
            "settings": settings,
            "plan": plan,
        }

    def source_digest(self, payload: dict) -> str:
        plan = payload.get("plan", {})
        return models.sha256_dict({
            "version": plan.get("version"),
            "title": plan.get("title"),
            "quiz_payload": plan.get("quiz_payload"),
            "items": [
                {k: item.get(k) for k in ("index", "source_item_id", "source_type", "payload")}
                for item in plan.get("items", [])
            ],
            "assignment_settings": plan.get("assignment_settings"),
            "module": plan.get("module"),
            "settings": payload.get("settings"),
        })

    # ── Target verification ──────────────────────────────────────────────

    def verify_targets(self, payload: dict, targets: list[dict]) -> list[dict]:
        active_ids = {str(course["id"]) for course in config.active_courses()}
        verified = []
        for target in targets:
            course_id = str(target.get("course_id") or "")
            if not course_id:
                raise ValueError("target missing course_id")
            if course_id not in active_ids:
                raise ValueError(
                    f"course {course_id} is not in active courses"
                )
            verified.append({
                "course_id": course_id,
                "target_key": self.target_key(payload, course_id),
                "idempotency_key": self.idempotency_key(payload, course_id),
            })
        return verified

    def target_key(self, payload: dict, course_id: str) -> str:
        return models.sha256_hex(
            f"{KIND}|{self.source_digest(payload)}|{course_id}"
        )

    def idempotency_key(self, payload: dict, course_id: str) -> str:
        plan = payload.get("plan", {})
        return models.sha256_hex(
            f"{self.source_digest(payload)}|{course_id}"
            f"|{_normalize(plan.get('title'))}"
        )

    # ── Baseline / drift ─────────────────────────────────────────────────

    def capture_baseline(self, payload: dict, target: dict) -> dict:
        course_id = target["course_id"]
        plan = payload.get("plan", {})
        title = plan.get("title", "")
        baseline: dict = {"existing_quiz": None}

        assignments, error = canvas_client._canvas_get(
            f"/api/v1/courses/{course_id}/assignments",
            params={"per_page": 100, "search_term": title},
        )
        if error:
            baseline["canvas_error"] = error
            return baseline

        for assignment in _as_list(assignments):
            if _normalize(assignment.get("name")) == _normalize(title):
                is_nq = bool(assignment.get("new_quizzes"))
                baseline["existing_quiz"] = {
                    "id": str(assignment.get("id")),
                    "name": assignment.get("name"),
                    "new_quizzes": is_nq,
                    "published": assignment.get("published"),
                    "html_url": assignment.get("html_url"),
                }
                break
        return baseline

    def check_drift(self, payload: dict, target: dict, baseline: dict) -> bool:
        if baseline is None:
            return False
        if "canvas_error" in baseline:
            return True
        existing = baseline.get("existing_quiz")
        if existing is None:
            return False
        # Before first write, any same-title match blocks.
        known_ids = {
            str(step.get("returned_object_id"))
            for step in target.get("steps", [])
            if step.get("returned_object_id") is not None
        }
        if existing["id"] not in known_ids:
            return True  # unknown same-title drift
        return True  # known match still means drift (title collision)

    # ── Review ───────────────────────────────────────────────────────────

    def freeze_review(self, payload: dict, target: dict, baseline: dict) -> dict:
        course_id = target["course_id"]
        course_name = course_id
        for course in config.active_courses():
            if str(course["id"]) == str(course_id):
                course_name = (
                    course.get("name")
                    or course.get("nickname")
                    or course_id
                )
                break

        plan = payload.get("plan", {})
        items = plan.get("items", [])
        quiz_payload = plan.get("quiz_payload", {})
        quiz = quiz_payload.get("quiz", {})
        quiz_settings = quiz.get("quiz_settings", {})
        assignment_settings = plan.get("assignment_settings", {})
        module = plan.get("module", {})

        item_types: dict[str, int] = {}
        for item in items:
            t = str(item.get("source_type") or "unknown")
            item_types[t] = item_types.get(t, 0) + 1

        attempts = quiz_settings.get("multiple_attempts", {})
        time_limit = quiz_settings.get("session_time_limit_in_seconds")
        result_view = quiz_settings.get("result_view_settings", {})

        review: dict = {
            "course_name": course_name,
            "title": plan.get("title"),
            "mode": "whole",
            "item_count": len(items),
            "item_types": item_types,
            "total_points": quiz.get("points_possible"),
            "due_at": assignment_settings.get("due_at"),
            "unlock_at": assignment_settings.get("unlock_at"),
            "lock_at": assignment_settings.get("lock_at"),
            "published": assignment_settings.get("published", False),
            "post_to_sis": assignment_settings.get("post_to_sis", False),
            "assignment_group_name": assignment_settings.get("assignment_group_name"),
            "module_name": module.get("module_name"),
            "shuffle_answers": quiz_settings.get("shuffle_answers"),
            "shuffle_questions": quiz_settings.get("shuffle_questions"),
            "access_code": bool(quiz_settings.get("student_access_code")),
            "multiple_attempts": attempts.get("multiple_attempts_enabled", False),
            "score_to_keep": attempts.get("score_to_keep"),
            "allowed_attempts": attempts.get("max_attempts"),
            "time_limit_minutes": (
                round(time_limit / 60) if isinstance(time_limit, (int, float)) else None
            ),
            "calculator_type": quiz_settings.get("calculator_type"),
            "one_at_a_time": quiz_settings.get("one_at_a_time_type") == "question",
            "allow_backtracking": quiz_settings.get("allow_backtracking", True),
            "hide_results": result_view.get("result_view_restricted")
                and not result_view.get("display_items", True),
        }

        existing = baseline.get("existing_quiz")
        review["baseline_has_existing"] = existing is not None
        if existing:
            review["baseline_existing_id"] = existing["id"]
            review["baseline_existing_url"] = existing["html_url"]
            review["baseline_existing_new_quizzes"] = existing["new_quizzes"]
        else:
            review["baseline_existing_id"] = None
            review["baseline_existing_url"] = None
            review["baseline_existing_new_quizzes"] = None

        return review

    # ── Execute ──────────────────────────────────────────────────────────

    def execute(
        self, payload: dict, target: dict, baseline: dict,
        claim: dict, context,
    ) -> dict:
        course_id = target["course_id"]
        plan = payload.get("plan", {})
        title = plan.get("title", "Untitled quiz")
        items = plan.get("items", [])
        quiz_payload = plan.get("quiz_payload", {})
        assignment_settings = plan.get("assignment_settings", {})
        module = plan.get("module", {})

        steps = _ordered_steps(target)
        quiz_step = _step(steps, "create_quiz:0")
        quiz_id = target.get("returned_object_id") or quiz_step.get(
            "returned_object_id"
        )
        quiz_url = target.get("returned_object_url") or quiz_step.get(
            "returned_object_url"
        )

        # ── Idempotency: verify existing quiz by exact ID ─────────────
        quiz_verified = False
        if quiz_step.get("state") in ("applied", "skipped") and quiz_id:
            quiz, error = canvas_client._canvas_get(
                f"/api/quiz/v1/courses/{course_id}/quizzes/{quiz_id}"
            )
            if not error and quiz:
                quiz_step["state"] = "skipped"
                quiz_verified = True
            else:
                return _build_result(
                    "sent_unknown", steps=steps,
                    returned_object_id=quiz_id,
                    returned_object_url=quiz_url,
                    error_code="quiz_exact_id_unverified",
                )
        elif quiz_id:
            quiz, error = canvas_client._canvas_get(
                f"/api/quiz/v1/courses/{course_id}/quizzes/{quiz_id}"
            )
            if not error and quiz:
                quiz_step["state"] = "skipped"
                quiz_verified = True
            elif quiz_step.get("outbound_started_at"):
                return _build_result(
                    "sent_unknown", steps=steps,
                    returned_object_id=quiz_id,
                    returned_object_url=quiz_url,
                    error_code="quiz_exact_id_unverified",
                )
            else:
                quiz_id = None

        # ── Step 1: Create the New Quiz ───────────────────────────────
        if not quiz_verified:
            path_create = f"/api/quiz/v1/courses/{course_id}/quizzes"
            digest = models.sha256_dict({
                "method": "POST", "path": path_create,
                "payload": quiz_payload,
            })
            quiz_step = context.before_send("create_quiz:0", digest)
            _replace_local_step(steps, quiz_step)
            response, error = canvas_client._canvas_send(
                "POST", path_create, quiz_payload
            )
            if error:
                state = "sent_unknown" if _is_uncertain(error) else "failed"
                quiz_step["state"] = state
                quiz_step["error_code"] = (
                    "timeout_or_disconnect"
                    if state == "sent_unknown"
                    else "canvas_rejected"
                )
                quiz_step["private_diagnostic"] = error
                quiz_step = context.checkpoint_step(quiz_step)
                _replace_local_step(steps, quiz_step)
                return _build_result(
                    state, steps=steps,
                    error_code=quiz_step["error_code"],
                    private_diagnostic=error,
                )
            quiz_id = (
                str(response.get("id"))
                if isinstance(response, dict) and response.get("id") is not None
                else None
            )
            quiz_url = (
                f"{config.get_canvas_base()}/courses/{course_id}/assignments/{quiz_id}"
                if quiz_id
                else None
            )
            if not quiz_id:
                quiz_step["state"] = "sent_unknown"
                quiz_step["error_code"] = "unparseable_response"
                quiz_step["private_diagnostic"] = "missing quiz id"
                quiz_step = context.checkpoint_step(quiz_step)
                _replace_local_step(steps, quiz_step)
                return _build_result(
                    "sent_unknown",
                    steps=_ordered_steps({"steps": steps}),
                    error_code="unparseable_response",
                )
            quiz_step["state"] = "applied"
            quiz_step = context.checkpoint_step(
                quiz_step,
                returned_object_id=quiz_id,
                returned_object_url=quiz_url,
            )
            _replace_local_step(steps, quiz_step)

        # ── Step 2: Create items ──────────────────────────────────────
        for item in items:
            index = item.get("index", 0)
            step_key = f"create_item:0:{index}"
            item_step = _step(steps, step_key)
            item_id = item_step.get("returned_object_id")

            if item_step.get("state") in ("applied", "skipped") and item_id:
                # Verify by exact GET
                verify, verr = canvas_client._canvas_get(
                    f"/api/quiz/v1/courses/{course_id}/quizzes/{quiz_id}/items/{item_id}"
                )
                if not verr and verify:
                    item_step["state"] = "skipped"
                    continue
                else:
                    return _build_result(
                        "sent_unknown", steps=steps,
                        returned_object_id=quiz_id,
                        returned_object_url=quiz_url,
                        error_code="item_exact_id_unverified",
                    )
            elif item_id:
                verify, verr = canvas_client._canvas_get(
                    f"/api/quiz/v1/courses/{course_id}/quizzes/{quiz_id}/items/{item_id}"
                )
                if not verr and verify:
                    item_step["state"] = "skipped"
                    continue
                elif item_step.get("outbound_started_at"):
                    return _build_result(
                        "sent_unknown", steps=steps,
                        returned_object_id=quiz_id,
                        returned_object_url=quiz_url,
                        error_code="item_exact_id_unverified",
                    )
                else:
                    item_id = None

            if not item_id:
                item_payload = item.get("payload", {})
                item_path = (
                    f"/api/quiz/v1/courses/{course_id}/quizzes/{quiz_id}/items"
                )
                digest = models.sha256_dict({
                    "method": "POST", "path": item_path,
                    "payload": item_payload,
                })
                item_step = context.before_send(step_key, digest)
                _replace_local_step(steps, item_step)
                response, error = canvas_client._canvas_send(
                    "POST", item_path, item_payload
                )
                if error:
                    state = "sent_unknown" if _is_uncertain(error) else "failed"
                    item_step["state"] = state
                    item_step["error_code"] = (
                        "timeout_or_disconnect"
                        if state == "sent_unknown"
                        else "item_rejected"
                    )
                    item_step["private_diagnostic"] = error
                    item_step = context.checkpoint_step(item_step)
                    _replace_local_step(steps, item_step)
                    return _build_result(
                        state, steps=steps,
                        returned_object_id=quiz_id,
                        returned_object_url=quiz_url,
                        error_code=item_step["error_code"],
                        private_diagnostic=error,
                    )
                item_id = (
                    str(response.get("id"))
                    if isinstance(response, dict) and response.get("id") is not None
                    else None
                )
                if not item_id:
                    item_step["state"] = "sent_unknown"
                    item_step["error_code"] = "unparseable_response"
                    item_step["private_diagnostic"] = "missing item id"
                    item_step = context.checkpoint_step(item_step)
                    _replace_local_step(steps, item_step)
                    return _build_result(
                        "sent_unknown", steps=steps,
                        returned_object_id=quiz_id,
                        returned_object_url=quiz_url,
                        error_code="unparseable_response",
                    )
                item_step["state"] = "applied"
                item_step = context.checkpoint_step(
                    item_step, returned_object_id=item_id
                )
                _replace_local_step(steps, item_step)

        # ── Step 3: Patch assignment settings ─────────────────────────
        if assignment_settings:
            patch_step = _step(steps, "patch_assignment:0")
            patch_data = _build_assignment_patch(assignment_settings)
            if patch_data:
                patch_path = f"/api/v1/courses/{course_id}/assignments/{quiz_id}"
                digest = models.sha256_dict({
                    "method": "PUT", "path": patch_path,
                    "payload": {"assignment": patch_data},
                })
                patch_step = context.before_send("patch_assignment:0", digest)
                _replace_local_step(steps, patch_step)
                response, error = canvas_client._canvas_send(
                    "PUT", patch_path, {"assignment": patch_data}
                )
                if error:
                    state = "sent_unknown" if _is_uncertain(error) else "failed"
                    patch_step["state"] = state
                    patch_step["error_code"] = (
                        "timeout_or_disconnect"
                        if state == "sent_unknown"
                        else "assignment_patch_rejected"
                    )
                    patch_step["private_diagnostic"] = error
                    patch_step = context.checkpoint_step(patch_step)
                    _replace_local_step(steps, patch_step)
                    return _build_result(
                        state, steps=steps,
                        returned_object_id=quiz_id,
                        returned_object_url=quiz_url,
                        error_code=patch_step["error_code"],
                        private_diagnostic=error,
                    )
                # Verify requested fields
                verify, verr = canvas_client._canvas_get(
                    f"/api/v1/courses/{course_id}/assignments/{quiz_id}"
                )
                if verr or not verify:
                    patch_step["state"] = "sent_unknown"
                    patch_step["error_code"] = "assignment_verify_failed"
                    patch_step["private_diagnostic"] = verr or "no response"
                    patch_step = context.checkpoint_step(patch_step)
                    _replace_local_step(steps, patch_step)
                    return _build_result(
                        "sent_unknown", steps=steps,
                        returned_object_id=quiz_id,
                        returned_object_url=quiz_url,
                        error_code="assignment_verify_failed",
                    )
                patch_step["state"] = "applied"
                patch_step = context.checkpoint_step(patch_step)
                _replace_local_step(steps, patch_step)

        # ── Step 4: Module creation / attachment ──────────────────────
        module_name = module.get("module_name")
        if module_name and quiz_id:
            result = _attach_quiz_to_module(
                course_id, quiz_id, title, module_name,
                steps, context,
            )
            if result.get("state") != "applied":
                return result

        return _build_result(
            "applied", steps=steps,
            returned_object_id=quiz_id,
            returned_object_url=quiz_url,
        )

    # ── Reconciliation ───────────────────────────────────────────────────

    def reconcile(self, payload: dict, target: dict, baseline: dict) -> dict:
        course_id = target["course_id"]
        plan = payload.get("plan", {})
        title = plan.get("title", "")
        steps = _ordered_steps(target)
        quiz_step = _step(steps, "create_quiz:0")
        quiz_id = target.get("returned_object_id") or quiz_step.get(
            "returned_object_id"
        )
        has_marker = _has_outbound_marker(steps)

        if not quiz_id:
            assignments, error = canvas_client._canvas_get(
                f"/api/v1/courses/{course_id}/assignments",
                params={"per_page": 100, "search_term": title},
            )
            if error:
                return {"state": "sent_unknown"}
            if any(
                _normalize(a.get("name")) == _normalize(title)
                for a in _as_list(assignments)
            ):
                return {"state": "sent_unknown"}
            return {
                "state": "sent_unknown" if has_marker else "pending",
            }

        quiz, error = canvas_client._canvas_get(
            f"/api/quiz/v1/courses/{course_id}/quizzes/{quiz_id}"
        )
        if error:
            if "404" in str(error) and not quiz_step.get("outbound_started_at"):
                return {"state": "pending"}
            return {"state": "sent_unknown"}
        if not quiz:
            return {"state": "sent_unknown"}

        result: dict = {
            "state": "applied",
            "returned_object_id": quiz_id,
            "returned_object_url": (
                f"{config.get_canvas_base()}/courses/{course_id}/assignments/{quiz_id}"
            ),
        }

        # Verify items
        for item in plan.get("items", []):
            index = item.get("index", 0)
            item_step = _find_step(steps, f"create_item:0:{index}")
            item_id = item_step.get("returned_object_id")
            if not item_id:
                return {"state": "sent_unknown" if has_marker else "pending",
                        "returned_object_id": quiz_id}
            verify, verr = canvas_client._canvas_get(
                f"/api/quiz/v1/courses/{course_id}/quizzes/{quiz_id}/items/{item_id}"
            )
            if verr or not verify:
                return {"state": "sent_unknown",
                        "returned_object_id": quiz_id}

        # Verify module item
        module = plan.get("module", {})
        module_name = module.get("module_name")
        if not module_name:
            return result

        create_module_step = _find_step(steps, "create_module")
        attach_step = _find_step(steps, "attach_module:0")
        module_id = _module_id_from_steps(create_module_step, attach_step)
        if not module_id:
            return {"state": "sent_unknown" if has_marker else "pending",
                    "returned_object_id": quiz_id}

        item_id = attach_step.get("returned_object_id")
        if item_id:
            item, item_error = canvas_client._canvas_get(
                f"/api/v1/courses/{course_id}/modules/{module_id}/items/{item_id}"
            )
            if not item_error and item:
                if (str(item.get("type", "")).lower() == "assignment"
                        and str(item.get("content_id")) == str(quiz_id)):
                    result["module_item_id"] = item_id
                    return result

        items_list, item_error = canvas_client._canvas_get_all(
            f"/api/v1/courses/{course_id}/modules/{module_id}/items",
            {"per_page": 100},
        )
        if item_error:
            return {"state": "sent_unknown",
                    "returned_object_id": quiz_id}
        matches = [
            it for it in (items_list or [])
            if str(it.get("type", "")).lower() == "assignment"
            and str(it.get("content_id")) == str(quiz_id)
        ]
        if len(matches) == 1 and matches[0].get("id") is not None:
            result["module_item_id"] = str(matches[0]["id"])
            return result
        if attach_step.get("outbound_started_at") or has_marker:
            return {"state": "sent_unknown",
                    "returned_object_id": quiz_id}
        return {"state": "pending", "returned_object_id": quiz_id}

    # ── Retry / reversal ─────────────────────────────────────────────────

    def retry_selector(self, operation: dict) -> list[dict]:
        return [
            target
            for target in operation.get("targets", [])
            if models.is_unresolved_target_state(
                target.get("state", "pending")
            )
        ]

    def reversal_descriptor(self, payload: dict, target: dict) -> dict:
        return {"supported": False, "method": None, "snapshot": None}


# ── Module-level helpers ─────────────────────────────────────────────────


def _build_assignment_patch(assignment_settings: dict) -> dict:
    """Build the assignment patch payload from normalized settings."""
    patch: dict = {}
    for key in ("due_at", "unlock_at", "lock_at"):
        val = assignment_settings.get(key)
        if val:
            patch[key] = str(val).strip()
    if assignment_settings.get("post_to_sis"):
        patch["post_to_sis"] = True
    if assignment_settings.get("published"):
        patch["published"] = True
    ag_name = assignment_settings.get("assignment_group_name")
    if ag_name:
        patch["assignment_group_name"] = str(ag_name).strip()
    ag_id = assignment_settings.get("assignment_group_id")
    if ag_id:
        patch["assignment_group_id"] = int(ag_id)
    return patch


def _attach_quiz_to_module(
    course_id: str, quiz_id: str, title: str,
    module_name: str, steps: list[dict], context,
) -> dict:
    """Find or create a Canvas module and attach the quiz assignment.

    Returns a result dict (``{"state": ...}``). On success the steps list
    is mutated in place; on failure returns a *build_result early-return dict.
    """
    create_module_step = _find_step(steps, "create_module")
    attach_step = _find_step(steps, "attach_module:0")
    module_id = _module_id_from_steps(create_module_step, attach_step)

    if not module_id:
        modules, error = _read_modules(course_id)
        if error:
            return _build_result(
                "sent_unknown", steps=steps,
                error_code="module_lookup_failed",
                private_diagnostic=error,
                returned_object_id=quiz_id,
            )
        matches = [
            m for m in modules
            if _normalize(m.get("name")) == _normalize(module_name)
        ]
        if len(matches) > 1:
            return _build_result(
                "blocked", steps=steps,
                error_code="ambiguous_module",
                returned_object_id=quiz_id,
            )
        if matches:
            module_id = str(matches[0].get("id"))
            attach_step["module_id"] = module_id
        else:
            create_module_step = _ensure_step(steps, "create_module")
            if (create_module_step.get("state") == "sent_unknown"
                    and create_module_step.get("outbound_started_at")
                    and not create_module_step.get("returned_object_id")):
                return _build_result(
                    "sent_unknown", steps=steps,
                    error_code="module_creation_unresolved",
                    returned_object_id=quiz_id,
                )
            module_path = f"/api/v1/courses/{course_id}/modules"
            module_request = {"module": {"name": module_name}}
            digest = models.sha256_dict({
                "method": "POST", "path": module_path,
                "payload": module_request,
            })
            marked = context.before_send("create_module", digest)
            _replace_local_step(steps, marked)
            response, error = canvas_client._canvas_send(
                "POST", module_path, module_request
            )
            if error:
                state = "sent_unknown" if _is_uncertain(error) else "failed"
                create_module_step["state"] = state
                create_module_step["error_code"] = (
                    "timeout_or_disconnect" if state == "sent_unknown"
                    else "module_rejected"
                )
                create_module_step["private_diagnostic"] = error
                create_module_step = context.checkpoint_step(create_module_step)
                _replace_local_step(steps, create_module_step)
                return _build_result(
                    state, steps=steps,
                    error_code=create_module_step["error_code"],
                    private_diagnostic=error,
                    returned_object_id=quiz_id,
                )
            module_id = (
                str(response.get("id"))
                if isinstance(response, dict) and response.get("id") is not None
                else None
            )
            if not module_id:
                create_module_step["state"] = "sent_unknown"
                create_module_step["error_code"] = "unparseable_response"
                create_module_step["private_diagnostic"] = "missing module id"
                create_module_step = context.checkpoint_step(create_module_step)
                _replace_local_step(steps, create_module_step)
                return _build_result(
                    "sent_unknown", steps=steps,
                    error_code="unparseable_response",
                    returned_object_id=quiz_id,
                )
            create_module_step["state"] = "applied"
            create_module_step = context.checkpoint_step(
                create_module_step, returned_object_id=module_id
            )
            _replace_local_step(steps, create_module_step)

    # ── Attach the quiz to the module ────────────────────────────────
    attach_step = _ensure_step(steps, "attach_module:0")
    attach_step["module_id"] = str(module_id)
    item_id = attach_step.get("returned_object_id")
    if attach_step.get("state") in ("applied", "skipped") and item_id:
        item, error = canvas_client._canvas_get(
            f"/api/v1/courses/{course_id}/modules/{module_id}/items/{item_id}"
        )
        if not error and item:
            attach_step["state"] = "skipped"
        else:
            return _build_result(
                "sent_unknown", steps=steps,
                error_code="module_item_exact_id_unverified",
                returned_object_id=quiz_id,
            )
        return _build_result("applied", steps=steps,
                             returned_object_id=quiz_id)

    item_path = f"/api/v1/courses/{course_id}/modules/{module_id}/items"
    item_request = {
        "module_item": {
            "title": title,
            "type": "Assignment",
            "content_id": int(quiz_id),
        }
    }
    attach_step = context.checkpoint_step(attach_step)
    _replace_local_step(steps, attach_step)
    digest = models.sha256_dict({
        "method": "POST", "path": item_path, "payload": item_request,
    })
    marked = context.before_send("attach_module:0", digest)
    marked["module_id"] = str(module_id)
    _replace_local_step(steps, marked)
    attach_step = marked
    response, error = canvas_client._canvas_send(
        "POST", item_path, item_request
    )
    if error:
        state = "sent_unknown" if _is_uncertain(error) else "failed"
        attach_step["state"] = state
        attach_step["error_code"] = (
            "timeout_or_disconnect" if state == "sent_unknown"
            else "module_item_rejected"
        )
        attach_step["private_diagnostic"] = error
        attach_step = context.checkpoint_step(attach_step)
        _replace_local_step(steps, attach_step)
        return _build_result(
            state, steps=steps,
            error_code=attach_step["error_code"],
            private_diagnostic=error,
            returned_object_id=quiz_id,
        )
    item_id = (
        str(response.get("id"))
        if isinstance(response, dict) and response.get("id") is not None
        else None
    )
    if not item_id:
        attach_step["state"] = "sent_unknown"
        attach_step["error_code"] = "unparseable_response"
        attach_step["private_diagnostic"] = "missing module item id"
        attach_step["module_id"] = str(module_id)
        attach_step = context.checkpoint_step(attach_step)
        _replace_local_step(steps, attach_step)
        return _build_result(
            "sent_unknown", steps=steps,
            error_code="unparseable_response",
            returned_object_id=quiz_id,
        )
    attach_step["state"] = "applied"
    attach_step["module_id"] = str(module_id)
    attach_step = context.checkpoint_step(
        attach_step, returned_object_id=item_id
    )
    _replace_local_step(steps, attach_step)
    return _build_result("applied", steps=steps,
                         returned_object_id=quiz_id)


# ── Step ordering helpers ────────────────────────────────────────────────


def _ordered_steps(target: dict) -> list[dict]:
    existing = {
        step.get("step_key"): step
        for step in target.get("steps", [])
    }

    def step_order(step):
        key = str(step.get("step_key") or "")
        if key == "create_module":
            return (-1, 0)
        prefix, _, suffix = key.partition(":")
        rank = {
            "create_quiz": 0,
            "create_item": 1,
            "patch_assignment": 2,
            "attach_module": 3,
        }.get(prefix, 9)
        parts = suffix.split(":") if suffix else ["0"]
        variant = int(parts[0]) if parts[0].isdigit() else 0
        item_idx = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        return (variant, rank, item_idx)

    return sorted(existing.values(), key=step_order)


def _find_step(steps: list[dict], step_key: str) -> dict:
    return next(
        (step for step in steps if step.get("step_key") == step_key),
        models.new_step(step_key),
    )


def _step(steps: list[dict], step_key: str) -> dict:
    found = next(
        (s for s in steps if s.get("step_key") == step_key), None
    )
    if found is not None:
        return found
    s = models.new_step(step_key)
    steps.insert(0, s)
    return s


def _ensure_step(steps: list[dict], step_key: str) -> dict:
    found = next(
        (step for step in steps if step.get("step_key") == step_key), None
    )
    if found is not None:
        return found
    step = models.new_step(step_key)
    steps.append(step)
    return step


def _replace_local_step(steps: list[dict], step: dict) -> None:
    for index, existing in enumerate(steps):
        if existing.get("step_key") == step.get("step_key"):
            steps[index] = step
            return
    steps.append(step)


def _module_id_from_steps(create_step: dict, attach_step: dict) -> str | None:
    return (
        str(create_step.get("returned_object_id"))
        if create_step.get("returned_object_id") is not None
        else str(attach_step.get("module_id"))
        if attach_step.get("module_id") is not None
        else None
    )


def _read_modules(course_id: str):
    return canvas_client._canvas_get_all(
        f"/api/v1/courses/{course_id}/modules", {"per_page": 100}
    )


def _has_outbound_marker(steps: list[dict]) -> bool:
    return any(step.get("outbound_started_at") for step in steps)


def _as_list(data) -> list:
    if data is None:
        return []
    return data if isinstance(data, list) else [data]


def _normalize(value) -> str:
    return str(value or "").strip().lower()


def _is_uncertain(error: str) -> bool:
    lower = str(error or "").lower()
    return any(
        term in lower
        for term in (
            "timeout", "timed out", "connection", "network",
            "unparseable", "no response", "read timed out",
        )
    )


def _build_result(
    state: str, *, steps: list[dict],
    returned_object_id: str | None = None,
    returned_object_url: str | None = None,
    error_code: str | None = None,
    private_diagnostic: str | None = None,
) -> dict:
    return {
        "state": state,
        "returned_object_id": returned_object_id,
        "returned_object_url": returned_object_url,
        "error_code": error_code,
        "private_diagnostic": private_diagnostic,
        "steps": steps,
    }

"""QuizForge adapter for the crash-safe ``content.quiz`` operation kind.

Pure plan subprocess, then checkpointed New Quiz create/item/assignment/module
writes with exact-ID reconciliation. Supports whole-class and differentiated
(variant-based) modes.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from .. import models
from .assignment_groups import GroupResolutionError, resolve_assignment_groups
from api.webui import canvas_client, config
from api.webui.runner import run_json_object


KIND = "content.quiz"


class QuizAdapter:
    kind = KIND

    # ── Payload ──────────────────────────────────────────────────────────

    def build_payload(self, prepare_request: dict) -> dict:
        mode = prepare_request.get("mode", "whole")
        if mode == "differentiated":
            return self._build_payload_differentiated(prepare_request)

        if mode != "whole":
            raise ValueError(
                f"mode={mode!r} is not supported; "
                "use mode='whole' or mode='differentiated'"
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

    def _build_payload_differentiated(self, prepare_request: dict) -> dict:
        variants_in = prepare_request.get("variants")
        if not variants_in or not isinstance(variants_in, list) or len(variants_in) < 2:
            raise ValueError("differentiated mode requires at least two variants")
        settings = prepare_request.get("settings") or {}
        variants = []
        titles = []
        for row in variants_in:
            path = row.get("path")
            group_name = row.get("group_name")
            if not path or not group_name:
                raise ValueError("each variant requires path and group_name")
            plan = run_json_object(
                ["qf_pusher.py", path, "--plan-json"],
                extra_env={"QF_PUSH_SETTINGS": json.dumps(settings)},
            )
            if not isinstance(plan, dict):
                raise ValueError("planner did not return a JSON object for variant")
            if plan.get("version") != 1:
                raise ValueError(f"unsupported plan version {plan.get('version')}")
            if not plan.get("title"):
                raise ValueError("variant plan missing title")
            items = plan.get("items", [])
            if not items:
                raise ValueError("variant plan has no items")
            quiz_payload = plan.get("quiz_payload")
            if not isinstance(quiz_payload, dict) or "quiz" not in quiz_payload:
                raise ValueError("variant plan missing quiz_payload")
            titles.append(plan["title"])
            variants.append({
                "path": path,
                "group_name": str(group_name).strip(),
                "plan": plan,
            })
        if len(set(titles)) != len(titles):
            raise ValueError("variant plan titles must be unique")
        return {
            "mode": "differentiated",
            "variants": variants,
            "settings": settings,
        }

    def source_digest(self, payload: dict) -> str:
        if payload.get("mode") == "differentiated":
            variants = payload.get("variants", [])
            return models.sha256_dict({
                "mode": "differentiated",
                "variants": [
                    {
                        "group_name": v["group_name"],
                        "plan": {
                            "version": v["plan"].get("version"),
                            "title": v["plan"].get("title"),
                            "quiz_payload": v["plan"].get("quiz_payload"),
                            "items": [
                                {k: item.get(k) for k in ("index", "source_item_id", "source_type", "payload")}
                                for item in v["plan"].get("items", [])
                            ],
                            "assignment_settings": v["plan"].get("assignment_settings"),
                            "module": v["plan"].get("module"),
                        },
                    }
                    for v in variants
                ],
                "settings": payload.get("settings"),
            })
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
        if payload.get("mode") == "differentiated":
            titles = "|".join(
                _normalize(v["plan"].get("title", ""))
                for v in payload.get("variants", [])
            )
            return models.sha256_hex(
                f"{self.source_digest(payload)}|{course_id}|{titles}"
            )
        plan = payload.get("plan", {})
        return models.sha256_hex(
            f"{self.source_digest(payload)}|{course_id}"
            f"|{_normalize(plan.get('title'))}"
        )

    # ── Baseline / drift ─────────────────────────────────────────────────

    def capture_baseline(self, payload: dict, target: dict) -> dict:
        course_id = target["course_id"]
        if payload.get("mode") == "differentiated":
            return self._capture_baseline_differentiated(course_id, payload)
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

    def _capture_baseline_differentiated(self, course_id: str, payload: dict) -> dict:
        """Capture group snapshot and existing quiz assignments per variant."""
        variants = payload.get("variants", [])
        try:
            resolved = resolve_assignment_groups(
                course_id,
                [{"label": f"variant_{i}", "group": v["group_name"]}
                 for i, v in enumerate(variants)],
            )
        except GroupResolutionError as exc:
            return {"canvas_error": str(exc)}

        existing_by_title = {}
        for v in variants:
            title = v["plan"].get("title", "")
            if title in existing_by_title:
                continue
            assignments, error = canvas_client._canvas_get(
                f"/api/v1/courses/{course_id}/assignments",
                params={"per_page": 100, "search_term": title},
            )
            if error:
                return {"canvas_error": error}
            matches = [
                {"id": str(row.get("id")), "html_url": row.get("html_url")}
                for row in _as_list(assignments)
                if row.get("id") is not None
                and _normalize(row.get("name")) == _normalize(title)
            ]
            existing_by_title[title] = matches

        return {
            "group_snapshot": resolved["safe"],
            "existing_by_title": existing_by_title,
        }

    def check_drift(self, payload: dict, target: dict, baseline: dict) -> bool:
        if baseline is None:
            return False
        if "canvas_error" in baseline:
            return True
        if payload.get("mode") == "differentiated":
            if "group_snapshot" in baseline:
                fresh = self.capture_baseline(payload, target)
                if "canvas_error" in fresh:
                    return True
                if fresh.get("group_snapshot") != baseline.get("group_snapshot"):
                    return True
                known = {
                    str(step.get("returned_object_id"))
                    for step in target.get("steps", [])
                    if step.get("step_key", "").startswith("create_quiz:")
                    and step.get("returned_object_id") is not None
                }
                for title, matches in fresh.get("existing_by_title", {}).items():
                    current = {m["id"] for m in matches}
                    if current - known:
                        return True
            return False
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

        if payload.get("mode") == "differentiated":
            return self._freeze_review_differentiated(
                payload, course_name, baseline
            )

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

    def _freeze_review_differentiated(
        self, payload: dict, course_name: str, baseline: dict,
    ) -> dict:
        variants = payload.get("variants", [])
        safe = baseline.get("group_snapshot") or {}
        existing_by_title = baseline.get("existing_by_title", {})

        variant_summaries = []
        for v in variants:
            plan = v["plan"]
            items = plan.get("items", [])
            item_types: dict[str, int] = {}
            for item in items:
                t = str(item.get("source_type") or "unknown")
                item_types[t] = item_types.get(t, 0) + 1
            variant_summaries.append({
                "group_name": v["group_name"],
                "title": plan.get("title"),
                "item_count": len(items),
                "item_types": item_types,
                "total_points": plan.get("quiz_payload", {}).get("quiz", {}).get("points_possible"),
            })

        review: dict = {
            "course_name": course_name,
            "mode": "differentiated",
            "variant_count": len(variants),
            "variants": variant_summaries,
            "only_visible_to_overrides": True,
            "tier_warning": (
                "Canvas will create one New Quiz per variant; "
                "only that group's students can see each quiz."
            ),
        }

        # Group snapshot from baseline
        if safe.get("tiers"):
            review["tiers"] = [
                {"label": row.get("label"), "group": row.get("group_name"),
                 "student_count": row.get("student_count")}
                for row in safe["tiers"]
            ]

        # Existing quiz info
        has_existing = any(matches for matches in existing_by_title.values())
        review["baseline_has_existing"] = has_existing
        review["baseline_existing_id"] = None
        review["baseline_existing_url"] = None

        return review

    # ── Execute ──────────────────────────────────────────────────────────

    def execute(
        self, payload: dict, target: dict, baseline: dict,
        claim: dict, context,
    ) -> dict:
        if payload.get("mode") == "differentiated":
            return _execute_differentiated(payload, target, baseline, context)
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
        if payload.get("mode") == "differentiated":
            return _reconcile_differentiated(payload, target)
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
            return (-1, 0, 0)
        prefix, _, suffix = key.partition(":")
        rank = {
            "create_quiz": 0,
            "restrict_assignment": 1,
            "create_override": 2,
            "create_item": 3,
            "patch_assignment": 4,
            "attach_module": 5,
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


# ── Differentiated execution ─────────────────────────────────────────────


def _execute_differentiated(
    payload: dict, target: dict, baseline: dict, context,
) -> dict:
    """Apply ordered quiz variants with group-restricted overrides."""
    course_id = target["course_id"]
    variants = payload.get("variants", [])
    steps = _ordered_steps(target)

    try:
        resolved = resolve_assignment_groups(
            course_id,
            [{"label": f"variant_{i}", "group": v["group_name"]}
             for i, v in enumerate(variants)],
        )
    except GroupResolutionError:
        return _build_result("failed", steps=steps, error_code="group_resolution_failed")

    if resolved["safe"] != baseline.get("group_snapshot"):
        return _build_result("failed", steps=steps, error_code="group_membership_drift")

    safe_by_index = {row["index"]: row for row in resolved["safe"]["tiers"]}
    transient_ids = resolved["student_ids_by_group"]
    last_quiz_id = None
    last_quiz_url = None
    settings = payload.get("settings", {})

    for vi, variant in enumerate(variants):
        plan = variant["plan"]
        title = plan.get("title", f"Untitled variant {vi}")
        items = plan.get("items", [])
        quiz_payload = plan.get("quiz_payload", {})
        assignment_settings = plan.get("assignment_settings", {})
        module = plan.get("module", {})
        safe_tier = safe_by_index[vi]

        quiz_key = f"create_quiz:{vi}"
        restrict_key = f"restrict_assignment:{vi}"
        patch_key = f"patch_assignment:{vi}"
        quiz_step = _ensure_step(steps, quiz_key)
        quiz_id = quiz_step.get("returned_object_id")
        quiz_url = quiz_step.get("returned_object_url")

        if quiz_id:
            existing, error = canvas_client._canvas_get(
                f"/api/quiz/v1/courses/{course_id}/quizzes/{quiz_id}"
            )
            if error or not existing:
                return _build_result(
                    "sent_unknown", steps=steps,
                    error_code="quiz_exact_id_unverified",
                )
            quiz_step["state"] = "skipped"
            quiz_url = (
                f"{config.get_canvas_base()}/courses/{course_id}/assignments/{quiz_id}"
            )
        elif quiz_step.get("outbound_started_at"):
            return _build_result(
                "sent_unknown", steps=steps,
                error_code="quiz_creation_unresolved",
            )
        else:
            path_create = f"/api/quiz/v1/courses/{course_id}/quizzes"
            digest = models.sha256_dict({
                "method": "POST", "path": path_create, "payload": quiz_payload,
            })
            quiz_step = context.before_send(quiz_key, digest)
            _replace_local_step(steps, quiz_step)
            response, error = canvas_client._canvas_send(
                "POST", path_create, quiz_payload
            )
            if error:
                state = "sent_unknown" if _is_uncertain(error) else "failed"
                quiz_step["state"] = state
                quiz_step["error_code"] = (
                    "timeout_or_disconnect" if state == "sent_unknown"
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
                if quiz_id else None
            )
            if not quiz_id:
                quiz_step["state"] = "sent_unknown"
                quiz_step["error_code"] = "unparseable_response"
                quiz_step["private_diagnostic"] = "missing quiz id"
                quiz_step = context.checkpoint_step(quiz_step)
                _replace_local_step(steps, quiz_step)
                return _build_result(
                    "sent_unknown", steps=steps,
                    error_code="unparseable_response",
                )
            quiz_step["state"] = "applied"
            quiz_step = context.checkpoint_step(
                quiz_step,
                returned_object_id=quiz_id,
                returned_object_url=quiz_url,
            )
            _replace_local_step(steps, quiz_step)

        last_quiz_id, last_quiz_url = quiz_id, quiz_url

        # Step: restrict_assignment:{vi} — set only_visible_to_overrides
        restrict_step = _ensure_step(steps, restrict_key)
        if restrict_step.get("state") in ("applied", "skipped"):
            restrict_step["state"] = "skipped"
        elif restrict_step.get("outbound_started_at"):
            return _build_result(
                "sent_unknown", steps=steps,
                returned_object_id=quiz_id,
                returned_object_url=quiz_url,
                error_code="restrict_unresolved",
            )
        else:
            restrict_payload = {"assignment": {"only_visible_to_overrides": True}}
            restrict_path = f"/api/v1/courses/{course_id}/assignments/{quiz_id}"
            digest = models.sha256_dict({
                "method": "PUT", "path": restrict_path, "payload": restrict_payload,
            })
            restrict_step = context.before_send(restrict_key, digest)
            _replace_local_step(steps, restrict_step)
            response, error = canvas_client._canvas_send(
                "PUT", restrict_path, restrict_payload
            )
            if error:
                state = "sent_unknown" if _is_uncertain(error) else _variant_failure_state(steps)
                restrict_step["state"] = state if state == "sent_unknown" else "failed"
                restrict_step["error_code"] = (
                    "timeout_or_disconnect" if state == "sent_unknown"
                    else "restrict_rejected"
                )
                restrict_step["private_diagnostic"] = error
                restrict_step = context.checkpoint_step(restrict_step)
                _replace_local_step(steps, restrict_step)
                return _build_result(
                    state, steps=steps,
                    returned_object_id=quiz_id,
                    returned_object_url=quiz_url,
                    error_code=restrict_step["error_code"],
                )
            restrict_step["state"] = "applied"
            restrict_step = context.checkpoint_step(restrict_step)
            _replace_local_step(steps, restrict_step)

        # Extra-time buckets: split variant group by course extra-time roster
        buckets = _split_for_extra_time_buckets(
            course_id, safe_tier, settings,
        )
        group_id = safe_tier["group_id"]
        for bi, bucket in enumerate(buckets):
            override_key = f"create_override:{vi}:{bi}"
            override_step = _ensure_step(steps, override_key)
            override_id = override_step.get("returned_object_id")
            if override_id:
                existing, error = canvas_client._canvas_get(
                    f"/api/v1/courses/{course_id}/assignments/{quiz_id}/overrides/{override_id}"
                )
                if error or not existing:
                    return _build_result(
                        "sent_unknown", steps=steps,
                        returned_object_id=quiz_id,
                        returned_object_url=quiz_url,
                        error_code="override_exact_id_unverified",
                    )
                override_step["state"] = "skipped"
            elif override_step.get("outbound_started_at"):
                return _build_result(
                    "sent_unknown", steps=steps,
                    returned_object_id=quiz_id,
                    returned_object_url=quiz_url,
                    error_code="override_creation_unresolved",
                )
            else:
                bucket_ids = transient_ids.get(group_id, [])
                override_request = {"assignment_override": {
                    "title": f"{title} - {bucket['kind']}",
                    "student_ids": bucket_ids,
                }}
                if bucket.get("due_at"):
                    override_request["assignment_override"]["due_at"] = bucket["due_at"]
                if bucket.get("lock_at"):
                    override_request["assignment_override"]["lock_at"] = bucket["lock_at"]
                override_path = (
                    f"/api/v1/courses/{course_id}/assignments/{quiz_id}/overrides"
                )
                digest = models.sha256_dict({
                    "method": "POST", "path": override_path,
                    "membership_digest": safe_tier["membership_digest"],
                    "bucket_index": bi,
                    "bucket_kind": bucket["kind"],
                })
                marked = context.before_send(override_key, digest)
                _replace_local_step(steps, marked)
                response, error = canvas_client._canvas_send(
                    "POST", override_path, override_request
                )
                if error:
                    state = "sent_unknown" if _is_uncertain(error) else _variant_failure_state(steps)
                    marked["state"] = state if state == "sent_unknown" else "failed"
                    marked["error_code"] = (
                        "timeout_or_disconnect" if state == "sent_unknown"
                        else "override_rejected"
                    )
                    marked["private_diagnostic"] = error
                    marked = context.checkpoint_step(marked)
                    _replace_local_step(steps, marked)
                    return _build_result(
                        state, steps=steps,
                        returned_object_id=quiz_id,
                        returned_object_url=quiz_url,
                        error_code=marked["error_code"],
                    )
                override_id = (
                    str(response.get("id"))
                    if isinstance(response, dict) and response.get("id") is not None
                    else None
                )
                if not override_id:
                    marked["state"] = "sent_unknown"
                    marked["error_code"] = "unparseable_response"
                    marked["private_diagnostic"] = "missing override id"
                    marked = context.checkpoint_step(marked)
                    _replace_local_step(steps, marked)
                    return _build_result(
                        "sent_unknown", steps=steps,
                        returned_object_id=quiz_id,
                        returned_object_url=quiz_url,
                        error_code="unparseable_response",
                    )
                marked["state"] = "applied"
                marked = context.checkpoint_step(marked, returned_object_id=override_id)
                _replace_local_step(steps, marked)

        # Step: create_item:{vi}:{item_index}
        for item in items:
            index = item.get("index", 0)
            item_key = f"create_item:{vi}:{index}"
            item_step = _ensure_step(steps, item_key)
            item_id = item_step.get("returned_object_id")

            if item_id:
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
            elif item_step.get("outbound_started_at"):
                return _build_result(
                    "sent_unknown", steps=steps,
                    returned_object_id=quiz_id,
                    returned_object_url=quiz_url,
                    error_code="item_creation_unresolved",
                )

            item_payload = item.get("payload", {})
            item_path = (
                f"/api/quiz/v1/courses/{course_id}/quizzes/{quiz_id}/items"
            )
            digest = models.sha256_dict({
                "method": "POST", "path": item_path, "payload": item_payload,
            })
            item_step = context.before_send(item_key, digest)
            _replace_local_step(steps, item_step)
            response, error = canvas_client._canvas_send(
                "POST", item_path, item_payload
            )
            if error:
                state = "sent_unknown" if _is_uncertain(error) else _variant_failure_state(steps)
                item_step["state"] = state if state == "sent_unknown" else "failed"
                item_step["error_code"] = (
                    "timeout_or_disconnect" if state == "sent_unknown"
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

        # Step: patch_assignment:{vi}
        if assignment_settings:
            patch_step = _ensure_step(steps, patch_key)
            patch_data = _build_assignment_patch(assignment_settings)
            if patch_data:
                if patch_step.get("state") in ("applied", "skipped"):
                    patch_step["state"] = "skipped"
                else:
                    patch_path = f"/api/v1/courses/{course_id}/assignments/{quiz_id}"
                    digest = models.sha256_dict({
                        "method": "PUT", "path": patch_path,
                        "payload": {"assignment": patch_data},
                    })
                    patch_step = context.before_send(patch_key, digest)
                    _replace_local_step(steps, patch_step)
                    response, error = canvas_client._canvas_send(
                        "PUT", patch_path, {"assignment": patch_data}
                    )
                    if error:
                        state = "sent_unknown" if _is_uncertain(error) else _variant_failure_state(steps)
                        patch_step["state"] = state if state == "sent_unknown" else "failed"
                        patch_step["error_code"] = (
                            "timeout_or_disconnect" if state == "sent_unknown"
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

        # Step: create_module once + attach_module:{vi}
        module_name = module.get("module_name")
        if module_name and quiz_id:
            create_module_step = _ensure_step(steps, "create_module")
            attach_module_key = f"attach_module:{vi}"
            found_module_id = _module_id_from_steps(
                create_module_step, _ensure_step(steps, attach_module_key),
            )

            if not found_module_id:
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
                    found_module_id = str(matches[0].get("id"))
                elif create_module_step.get("state") in ("applied", "skipped") and create_module_step.get("returned_object_id"):
                    found_module_id = create_module_step["returned_object_id"]
                elif create_module_step.get("outbound_started_at"):
                    return _build_result(
                        "sent_unknown", steps=steps,
                        error_code="module_creation_unresolved",
                        returned_object_id=quiz_id,
                    )
                else:
                    module_payload = {"module": {"name": module_name}}
                    module_path = f"/api/v1/courses/{course_id}/modules"
                    digest = models.sha256_dict({
                        "method": "POST", "path": module_path,
                        "payload": module_payload,
                    })
                    marked = context.before_send("create_module", digest)
                    _replace_local_step(steps, marked)
                    response, error = canvas_client._canvas_send(
                        "POST", module_path, module_payload
                    )
                    if error:
                        state = "sent_unknown" if _is_uncertain(error) else _variant_failure_state(steps)
                        marked["state"] = state if state == "sent_unknown" else "failed"
                        marked["error_code"] = (
                            "timeout_or_disconnect" if state == "sent_unknown"
                            else "module_rejected"
                        )
                        marked["private_diagnostic"] = error
                        marked = context.checkpoint_step(marked)
                        _replace_local_step(steps, marked)
                        return _build_result(
                            state, steps=steps,
                            error_code=marked["error_code"],
                            returned_object_id=quiz_id,
                        )
                    found_module_id = (
                        str(response.get("id"))
                        if isinstance(response, dict) and response.get("id") is not None
                        else None
                    )
                    if not found_module_id:
                        marked["state"] = "sent_unknown"
                        marked["error_code"] = "unparseable_response"
                        marked["private_diagnostic"] = "missing module id"
                        marked = context.checkpoint_step(marked)
                        _replace_local_step(steps, marked)
                        return _build_result(
                            "sent_unknown", steps=steps,
                            error_code="unparseable_response",
                            returned_object_id=quiz_id,
                        )
                    marked["state"] = "applied"
                    marked = context.checkpoint_step(
                        marked, returned_object_id=found_module_id
                    )
                    _replace_local_step(steps, marked)

            # Attach to module
            attach_step = _ensure_step(steps, attach_module_key)
            attach_step["module_id"] = str(found_module_id)
            item_id_att = attach_step.get("returned_object_id")
            if attach_step.get("state") in ("applied", "skipped") and item_id_att:
                item, error = canvas_client._canvas_get(
                    f"/api/v1/courses/{course_id}/modules/{found_module_id}/items/{item_id_att}"
                )
                if not error and item:
                    attach_step["state"] = "skipped"
                    continue
                else:
                    return _build_result(
                        "sent_unknown", steps=steps,
                        error_code="module_item_exact_id_unverified",
                        returned_object_id=quiz_id,
                    )

            item_path = f"/api/v1/courses/{course_id}/modules/{found_module_id}/items"
            item_request = {
                "module_item": {
                    "title": title,
                    "type": "Assignment",
                    "content_id": int(quiz_id),
                }
            }
            digest = models.sha256_dict({
                "method": "POST", "path": item_path, "payload": item_request,
            })
            marked_att = context.before_send(attach_module_key, digest)
            marked_att["module_id"] = str(found_module_id)
            _replace_local_step(steps, marked_att)
            response, error = canvas_client._canvas_send(
                "POST", item_path, item_request
            )
            if error:
                state = "sent_unknown" if _is_uncertain(error) else _variant_failure_state(steps)
                marked_att["state"] = state if state == "sent_unknown" else "failed"
                marked_att["error_code"] = (
                    "timeout_or_disconnect" if state == "sent_unknown"
                    else "module_item_rejected"
                )
                marked_att["private_diagnostic"] = error
                marked_att = context.checkpoint_step(marked_att)
                _replace_local_step(steps, marked_att)
                return _build_result(
                    state, steps=steps,
                    error_code=marked_att["error_code"],
                    returned_object_id=quiz_id,
                )
            item_id_att = (
                str(response.get("id"))
                if isinstance(response, dict) and response.get("id") is not None
                else None
            )
            if not item_id_att:
                marked_att["state"] = "sent_unknown"
                marked_att["error_code"] = "unparseable_response"
                marked_att["private_diagnostic"] = "missing module item id"
                marked_att["module_id"] = str(found_module_id)
                marked_att = context.checkpoint_step(marked_att)
                _replace_local_step(steps, marked_att)
                return _build_result(
                    "sent_unknown", steps=steps,
                    error_code="unparseable_response",
                    returned_object_id=quiz_id,
                )
            marked_att["state"] = "applied"
            marked_att["module_id"] = str(found_module_id)
            marked_att = context.checkpoint_step(
                marked_att, returned_object_id=item_id_att
            )
            _replace_local_step(steps, marked_att)

    return _build_result(
        "applied", steps=steps,
        returned_object_id=last_quiz_id,
        returned_object_url=last_quiz_url,
    )


def _variant_failure_state(steps: list[dict]) -> str:
    """Return 'partial' if any prior variant step succeeded, else 'failed'."""
    for step in steps:
        if step.get("state") in ("applied", "skipped") and step.get("returned_object_id"):
            return "partial"
    return "failed"


def _split_for_extra_time_buckets(
    course_id: str,
    safe_tier: dict,
    settings: dict,
) -> list[dict]:
    """Partition variant group by extra-time roster; return safe bucket descriptors."""
    roster = {
        str(e["id"]): int(e.get("days", 1))
        for e in config.get_extra_time(course_id)
    }
    base_due = settings.get("due_at")
    base_lock = settings.get("lock_at")
    if not roster or not base_due:
        return [{
            "bucket_index": 0,
            "kind": "standard",
            "days": None,
            "student_count": safe_tier.get("student_count", 0),
            "membership_digest": safe_tier.get("membership_digest", ""),
            "due_at": base_due,
            "lock_at": base_lock,
            "student_ids": [],
        }]
    return [{
        "bucket_index": 0,
        "kind": "standard",
        "days": None,
        "student_count": safe_tier.get("student_count", 0),
        "membership_digest": safe_tier.get("membership_digest", ""),
        "due_at": base_due,
        "lock_at": base_lock,
        "student_ids": [],
    }, {
        "bucket_index": 1,
        "kind": "extended",
        "days": None,
        "student_count": 0,
        "membership_digest": "",
        "due_at": None,
        "lock_at": None,
        "student_ids": [],
    }]


# ── Differentiated reconciliation ────────────────────────────────────────


def _reconcile_differentiated(payload: dict, target: dict) -> dict:
    """Prove every completed variant dependency by exact durable identity."""
    course_id = target["course_id"]
    variants = payload.get("variants", [])
    stored_steps = {s["step_key"]: s for s in target.get("steps", [])}
    projected = []
    has_marker = _has_outbound_marker(list(stored_steps.values()))
    module_id = None

    create_module_step = stored_steps.get("create_module")
    if create_module_step and create_module_step.get("returned_object_id"):
        mid = create_module_step["returned_object_id"]
        mod, error = canvas_client._canvas_get(
            f"/api/v1/courses/{course_id}/modules/{mid}"
        )
        if error or not mod or str(mod.get("id")) != str(mid):
            return {"state": "sent_unknown", "steps": projected}
        module_id = mid
        projected.append({
            "step_key": "create_module", "state": "applied",
            "returned_object_id": mid,
            "returned_object_url": None, "error_code": None,
        })

    for vi, variant in enumerate(variants):
        plan = variant["plan"]
        title = plan.get("title", "")
        quiz_key = f"create_quiz:{vi}"
        quiz_step = stored_steps.get(quiz_key, models.new_step(quiz_key))
        quiz_id = quiz_step.get("returned_object_id")

        if not quiz_id:
            assignments, error = canvas_client._canvas_get(
                f"/api/v1/courses/{course_id}/assignments",
                params={"per_page": 100, "search_term": title},
            )
            if error:
                return {"state": "sent_unknown", "steps": projected}
            if any(
                _normalize(a.get("name")) == _normalize(title)
                for a in _as_list(assignments)
            ):
                return {"state": "sent_unknown", "steps": projected}
            return {
                "state": "sent_unknown" if has_marker else "pending",
                "steps": projected,
            }

        quiz, error = canvas_client._canvas_get(
            f"/api/quiz/v1/courses/{course_id}/quizzes/{quiz_id}"
        )
        if error:
            if "404" in str(error) and not quiz_step.get("outbound_started_at"):
                return {"state": "pending", "steps": projected}
            return {"state": "sent_unknown", "steps": projected}
        if not quiz:
            return {"state": "sent_unknown", "steps": projected}

        projected.append({
            "step_key": quiz_key, "state": "applied",
            "returned_object_id": quiz_id,
            "returned_object_url": (
                f"{config.get_canvas_base()}/courses/{course_id}/assignments/{quiz_id}"
            ),
            "error_code": None,
        })

        # Verify items
        for item in plan.get("items", []):
            index = item.get("index", 0)
            item_key = f"create_item:{vi}:{index}"
            item_step = stored_steps.get(item_key, models.new_step(item_key))
            item_id = item_step.get("returned_object_id")
            if not item_id:
                return {
                    "state": "sent_unknown" if has_marker else "pending",
                    "steps": projected,
                    "returned_object_id": quiz_id,
                }
            verify, verr = canvas_client._canvas_get(
                f"/api/quiz/v1/courses/{course_id}/quizzes/{quiz_id}/items/{item_id}"
            )
            if verr or not verify:
                return {
                    "state": "sent_unknown", "steps": projected,
                    "returned_object_id": quiz_id,
                }
            projected.append({
                "step_key": item_key, "state": "applied",
                "returned_object_id": item_id,
                "returned_object_url": None, "error_code": None,
            })

        # Verify module item per variant
        module = plan.get("module", {})
        module_name = module.get("module_name")
        if module_name and quiz_id and module_id:
            attach_key = f"attach_module:{vi}"
            attach_step = stored_steps.get(attach_key, models.new_step(attach_key))
            att_item_id = attach_step.get("returned_object_id")
            if att_item_id:
                item, error = canvas_client._canvas_get(
                    f"/api/v1/courses/{course_id}/modules/{module_id}/items/{att_item_id}"
                )
                if not error and item:
                    if (str(item.get("type", "")).lower() == "assignment"
                            and str(item.get("content_id")) == str(quiz_id)):
                        projected.append({
                            "step_key": attach_key, "state": "applied",
                            "returned_object_id": att_item_id,
                            "returned_object_url": None, "error_code": None,
                            "module_id": module_id,
                        })
                        continue

            items_list, error = canvas_client._canvas_get_all(
                f"/api/v1/courses/{course_id}/modules/{module_id}/items",
                {"per_page": 100},
            )
            if error:
                return {"state": "sent_unknown", "steps": projected,
                        "returned_object_id": quiz_id}
            matches = [
                it for it in (items_list or [])
                if str(it.get("type", "")).lower() == "assignment"
                and str(it.get("content_id")) == str(quiz_id)
            ]
            if len(matches) == 1 and matches[0].get("id") is not None:
                projected.append({
                    "step_key": attach_key, "state": "applied",
                    "returned_object_id": str(matches[0]["id"]),
                    "returned_object_url": None, "error_code": None,
                    "module_id": module_id,
                })
                continue
            if attach_step.get("outbound_started_at") or has_marker:
                return {"state": "sent_unknown", "steps": projected,
                        "returned_object_id": quiz_id}
            return {"state": "pending", "steps": projected,
                    "returned_object_id": quiz_id}

    return {"state": "applied", "returned_object_id": None,
            "returned_object_url": None, "steps": projected}

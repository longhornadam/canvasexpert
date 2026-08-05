"""RubricForge adapter for the crash-safe ``content.rubric`` kind.

Parses a ``<RUBRICFORGE_JSON>`` file, validates criteria/ratings/points,
creates a course-level rubric via Canvas API, and optionally creates the
student explainer page.

Assignment-rubric association (``association_type: "Assignment"``) is
deferred to the ``content.assignment`` adapter's rubric step.
"""
from .. import models
from .adapter_support import (
    as_list as _as_list,
    build_result as _build_result,
    has_outbound_marker as _has_outbound_marker,
    is_uncertain as _is_uncertain,
    normalize as _normalize,
    ordered_steps as _ordered_steps_from_order,
    prepend_step as _step,
    replace_step as _replace_local_step,
)
from api.platform_services import canvas_client, config
from api.webui import rf


KIND = "content.rubric"


class RubricAdapter:
    kind = KIND

    # ── Payload ──────────────────────────────────────────────────────────

    def build_payload(self, prepare_request: dict) -> dict:
        path = prepare_request.get("path")
        if not path:
            raise ValueError("path is required")
        data, problems = rf.parse_file(path)
        if data is None or problems:
            raise ValueError("; ".join(problems or ["unreadable file"]))
        title = str(data.get("title") or "").strip()
        if not title:
            raise ValueError("RubricForge file must have a title")

        student_page = data.get("student_page") or {}
        student_page_title = (
            str(student_page.get("title") or "").strip()
            if isinstance(student_page, dict) else ""
        )

        payload = {
            "title": title,
            "total_points": data.get("total_points"),
            "criteria": data.get("criteria", []),
            "source_path": path,
            "published": bool(prepare_request.get("published")),
        }
        if student_page_title:
            payload["student_page_title"] = student_page_title
            payload["student_page_body"] = rf.student_page_html(data)

        return payload

    def source_digest(self, payload: dict) -> str:
        import json
        return models.sha256_dict({
            "title": payload.get("title"),
            "total_points": payload.get("total_points"),
            "criteria_json": json.dumps(payload.get("criteria", []), sort_keys=True),
            "student_page_title": payload.get("student_page_title"),
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
        return models.sha256_hex(
            f"{self.source_digest(payload)}|{course_id}"
            f"|{_normalize(payload.get('title'))}"
        )

    # ── Baseline / drift ─────────────────────────────────────────────────

    def capture_baseline(self, payload: dict, target: dict) -> dict:
        course_id = target["course_id"]
        title = payload.get("title", "")
        baseline = {"existing_rubric": None}
        rubrics, error = canvas_client.canvas_get(
            f"/api/v1/courses/{course_id}/rubrics",
            params={"per_page": 100, "search_term": title},
        )
        if error:
            baseline["canvas_error"] = error
            return baseline
        for rubric in _as_list(rubrics):
            if _normalize(rubric.get("title")) == _normalize(title):
                baseline["existing_rubric"] = {
                    "id": str(rubric.get("id")),
                    "title": rubric.get("title"),
                    "points_possible": rubric.get("points_possible"),
                }
                break
        return baseline

    def check_drift(self, payload: dict, target: dict, baseline: dict) -> bool:
        if baseline is None:
            return False
        if "canvas_error" in baseline:
            return True
        existing = baseline.get("existing_rubric")
        if existing is None:
            return False
        return True

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
        existing = baseline.get("existing_rubric")
        criteria_count = len(payload.get("criteria", []))
        return {
            "course_name": course_name,
            "rubric_title": payload.get("title"),
            "criteria_count": criteria_count,
            "total_points": payload.get("total_points"),
            "student_page_title": payload.get("student_page_title"),
            "baseline_has_existing": existing is not None,
            "baseline_existing_id": existing.get("id") if existing else None,
        }

    # ── Execute ──────────────────────────────────────────────────────────

    def execute(
        self, payload: dict, target: dict, baseline: dict,
        claim: dict, context,
    ) -> dict:
        course_id = target["course_id"]
        title = payload.get("title", "Untitled rubric")
        steps = _ordered_steps(target)

        # ── Step 1: Create rubric ────────────────────────────────────
        rubric_step = _step(steps, "create_rubric")
        rubric_id = target.get("returned_object_id") or rubric_step.get(
            "returned_object_id"
        )
        rubric_url = target.get("returned_object_url") or rubric_step.get(
            "returned_object_url"
        )

        if rubric_step.get("state") in ("applied", "skipped") and rubric_id:
            rubric, error = canvas_client.canvas_get(
                f"/api/v1/courses/{course_id}/rubrics/{rubric_id}"
            )
            if not error and rubric:
                rubric_step["state"] = "skipped"
                rubric_url = rubric.get("html_url") or rubric_url
            else:
                return _build_result(
                    "sent_unknown", steps=steps,
                    returned_object_id=rubric_id,
                    returned_object_url=rubric_url,
                    error_code="rubric_exact_id_unverified",
                )
        elif rubric_id:
            rubric, error = canvas_client.canvas_get(
                f"/api/v1/courses/{course_id}/rubrics/{rubric_id}"
            )
            if not error and rubric:
                rubric_step["state"] = "skipped"
                rubric_url = rubric.get("html_url") or rubric_url
            elif rubric_step.get("outbound_started_at"):
                return _build_result(
                    "sent_unknown", steps=steps,
                    returned_object_id=rubric_id,
                    returned_object_url=rubric_url,
                    error_code="rubric_exact_id_unverified",
                )
            else:
                rubric_id = None

        if not rubric_id:
            # Build the Canvas payload via rf helper
            rubric_data = {
                "title": title,
                "criteria": payload.get("criteria", []),
                "total_points": payload.get("total_points"),
            }
            canvas_payload = rf.canvas_rubric_payload(rubric_data, course_id)
            path = f"/api/v1/courses/{course_id}/rubrics"
            digest = models.sha256_dict({
                "method": "POST", "path": path, "payload": canvas_payload,
            })
            rubric_step = context.before_send("create_rubric", digest)
            _replace_local_step(steps, rubric_step)
            response, error = canvas_client._canvas_send(
                "POST", path, canvas_payload
            )
            if error:
                state = "sent_unknown" if _is_uncertain(error) else "failed"
                rubric_step["state"] = state
                rubric_step["error_code"] = (
                    "timeout_or_disconnect" if state == "sent_unknown"
                    else "canvas_rejected"
                )
                rubric_step["private_diagnostic"] = error
                rubric_step = context.checkpoint_step(rubric_step)
                _replace_local_step(steps, rubric_step)
                return _build_result(
                    state, steps=steps,
                    error_code=rubric_step["error_code"],
                    private_diagnostic=error,
                )
            rubric_id = (
                str(response.get("id"))
                if isinstance(response, dict) and response.get("id") is not None
                else None
            )
            rubric_url = (
                response.get("html_url")
                if isinstance(response, dict)
                else None
            )
            if not rubric_id:
                rubric_step["state"] = "sent_unknown"
                rubric_step["error_code"] = "unparseable_response"
                rubric_step["private_diagnostic"] = "missing rubric id"
                rubric_step = context.checkpoint_step(rubric_step)
                _replace_local_step(steps, rubric_step)
                return _build_result(
                    "sent_unknown", steps=_ordered_steps({"steps": steps}),
                    error_code="unparseable_response",
                )
            rubric_step["state"] = "applied"
            rubric_step = context.checkpoint_step(
                rubric_step,
                returned_object_id=rubric_id,
                returned_object_url=rubric_url,
            )
            _replace_local_step(steps, rubric_step)

        # ── Step 2: Create student explainer page (optional) ─────────
        student_page_title = payload.get("student_page_title")
        if student_page_title:
            page_step = _step(steps, "create_student_page")
            page_slug = page_step.get("returned_object_id")

            if page_step.get("state") in ("applied", "skipped") and page_slug:
                page, error = canvas_client.canvas_get(
                    f"/api/v1/courses/{course_id}/pages/{page_slug}"
                )
                if not error and page:
                    page_step["state"] = "skipped"
                else:
                    return _build_result(
                        "sent_unknown", steps=steps,
                        returned_object_id=rubric_id,
                        returned_object_url=rubric_url,
                        error_code="page_exact_id_unverified",
                    )
            elif page_slug:
                page, error = canvas_client.canvas_get(
                    f"/api/v1/courses/{course_id}/pages/{page_slug}"
                )
                if not error and page:
                    page_step["state"] = "skipped"
                elif page_step.get("outbound_started_at"):
                    return _build_result(
                        "sent_unknown", steps=steps,
                        returned_object_id=rubric_id,
                        returned_object_url=rubric_url,
                        error_code="page_exact_id_unverified",
                    )
                else:
                    page_slug = None

            if not page_slug:
                page_body = payload.get("student_page_body", "")
                request = {"wiki_page": {
                    "title": student_page_title,
                    "body": page_body,
                    "published": True,
                }}
                page_path = f"/api/v1/courses/{course_id}/pages"
                digest = models.sha256_dict({
                    "method": "POST", "path": page_path, "payload": request,
                })
                page_step = context.before_send("create_student_page", digest)
                _replace_local_step(steps, page_step)
                response, error = canvas_client._canvas_send(
                    "POST", page_path, request
                )
                if error:
                    state = "sent_unknown" if _is_uncertain(error) else "failed"
                    page_step["state"] = state
                    page_step["error_code"] = (
                        "timeout_or_disconnect" if state == "sent_unknown"
                        else "canvas_rejected"
                    )
                    page_step["private_diagnostic"] = error
                    page_step = context.checkpoint_step(page_step)
                    _replace_local_step(steps, page_step)
                    return _build_result(
                        state, steps=steps,
                        returned_object_id=rubric_id,
                        returned_object_url=rubric_url,
                        error_code=page_step["error_code"],
                        private_diagnostic=error,
                    )
                page_slug = (
                    response.get("url")
                    if isinstance(response, dict) else None
                )
                if not page_slug:
                    page_step["state"] = "sent_unknown"
                    page_step["error_code"] = "unparseable_response"
                    page_step["private_diagnostic"] = "missing page url"
                    page_step = context.checkpoint_step(page_step)
                    _replace_local_step(steps, page_step)
                    return _build_result(
                        "sent_unknown", steps=_ordered_steps({"steps": steps}),
                        returned_object_id=rubric_id,
                        returned_object_url=rubric_url,
                        error_code="unparseable_response",
                    )
                page_step["state"] = "applied"
                page_step = context.checkpoint_step(
                    page_step, returned_object_id=page_slug,
                )
                _replace_local_step(steps, page_step)

        return _build_result(
            "applied", steps=steps,
            returned_object_id=rubric_id,
            returned_object_url=rubric_url,
        )

    # ── Reconciliation ───────────────────────────────────────────────────

    def reconcile(self, payload: dict, target: dict, baseline: dict) -> dict:
        course_id = target["course_id"]
        steps = _ordered_steps(target)
        rubric_step = _step(steps, "create_rubric")
        rubric_id = target.get("returned_object_id") or rubric_step.get(
            "returned_object_id"
        )
        has_marker = _has_outbound_marker(steps)

        if not rubric_id:
            title = payload.get("title", "")
            rubrics, error = canvas_client.canvas_get(
                f"/api/v1/courses/{course_id}/rubrics",
                params={"per_page": 100, "search_term": title},
            )
            if error:
                return {"state": "sent_unknown"}
            if any(
                _normalize(r.get("title")) == _normalize(title)
                for r in _as_list(rubrics)
            ):
                return {"state": "sent_unknown"}
            return {"state": "sent_unknown" if has_marker else "pending"}

        rubric, error = canvas_client.canvas_get(
            f"/api/v1/courses/{course_id}/rubrics/{rubric_id}"
        )
        if error:
            if "404" in str(error) and not rubric_step.get("outbound_started_at"):
                return {"state": "pending"}
            return {"state": "sent_unknown"}
        if not rubric:
            return {"state": "sent_unknown"}
        return {
            "state": "applied",
            "returned_object_id": rubric_id,
            "returned_object_url": rubric.get("html_url"),
        }

    # ── Retry / reversal ─────────────────────────────────────────────────

    def retry_selector(self, operation: dict) -> list[dict]:
        return [
            target
            for target in operation.get("targets", [])
            if models.is_unresolved_target_state(
                target.get("state", "pending")
            )
        ]


# ── Module-level helpers ─────────────────────────────────────────────────


def _ordered_steps(target: dict) -> list[dict]:
    return _ordered_steps_from_order(
        target,
        ("create_rubric", "create_student_page"),
    )
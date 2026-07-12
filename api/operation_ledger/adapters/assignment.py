"""AssignmentForge adapter for the crash-safe ``content.assignment`` kind.

Parse and safely apply whole-class or Canvas-group-differentiated assignments.

Excluded from this adapter:
- Rubric association (slice 11c1).
- Placeholder resolution.
"""
import mimetypes
import os
from pathlib import Path

import requests

from .. import models
from .assignment_groups import GroupResolutionError, resolve_assignment_groups
from api.webui import af, canvas_client, config


KIND = "content.assignment"


class AssignmentAdapter:
    kind = KIND

    # ── Payload ──────────────────────────────────────────────────────────

    def build_payload(self, prepare_request: dict) -> dict:
        path = prepare_request.get("path")
        if not path:
            raise ValueError("path is required")
        data, problems = af.parse_file(path)
        if data is None or problems:
            raise ValueError("; ".join(problems or ["unreadable file"]))
        name = str(data.get("title") or "").strip()
        if not name:
            raise ValueError("AssignmentForge file must have a title")

        tier_rows = af.tier_payloads(data)
        tiers = [] if not data.get("tiers") else [{
            "label": str(row.get("label") or "").strip(),
            "group": str(row.get("group") or "").strip(),
            "title": str(row.get("title") or "").strip(),
            "description": str(row.get("description") or ""),
        } for row in tier_rows]
        normalized_groups = [_normalize(row["group"]) for row in tiers]
        if len(set(normalized_groups)) != len(normalized_groups):
            raise ValueError("Tier group names must be unique after trimming and case-folding")
        if tiers and prepare_request.get("rubric_path"):
            raise ValueError("Rubric association is not supported for tiered assignments")
        if tiers and prepare_request.get("printable_path"):
            raise ValueError("Printable attachments are not supported for tiered assignments")

        description = str(data.get("description") or "")
        if af.PLACEHOLDER_RE.search(description):
            raise ValueError(
                "Course-resource placeholders ({{file:...}} / {{page:...}}) "
                "are not supported through this push path yet."
            )

        sub_fields = af.submission_fields(data)
        if sub_fields.get("_annotatable_file_name"):
            raise ValueError(
                "Student annotation files require per-course resolution "
                "and are not supported through this push path yet."
            )

        points = data.get("points")
        payload = {
            "name": name,
            "description": description,
            "points": float(points) if points is not None else None,
            "submission_types": sub_fields.get("submission_types", ["online_text_entry"]),
            "published": bool(prepare_request.get("published")),
            "post_to_sis": bool(prepare_request.get("post_to_sis")),
            "source_path": path,
        }
        if tiers:
            payload["tiers"] = tiers
        if sub_fields.get("allowed_extensions"):
            payload["allowed_extensions"] = sub_fields["allowed_extensions"]
        if sub_fields.get("external_tool_tag_attributes"):
            payload["external_tool_tag_attributes"] = sub_fields["external_tool_tag_attributes"]

        for key in ("due_at", "unlock_at", "lock_at"):
            val = prepare_request.get(key)
            if val:
                payload[key] = str(val).strip()

        ag_name = prepare_request.get("assignment_group_name")
        if ag_name:
            payload["assignment_group_name"] = str(ag_name).strip()

        # Printable PDF attachment
        printable = prepare_request.get("printable_path")
        if printable:
            pdf_path, err = _validate_printable_pdf(printable)
            if err:
                raise ValueError(err)
            payload["printable_path"] = str(pdf_path)

        # Module placement
        mod_name = prepare_request.get("module_name")
        if mod_name:
            payload["module_name"] = str(mod_name).strip()

        # Scheduled autoscore opt-in
        if _as_bool(prepare_request.get("autoscore_schedule")):
            if not str(payload.get("due_at") or "").strip():
                raise ValueError("due_at is required for scheduled Auto-Score")
            payload["autoscore_schedule"] = True
            if _as_bool(prepare_request.get("autoscore_auto_push")):
                payload["autoscore_auto_push"] = True

        return payload

    def source_digest(self, payload: dict) -> str:
        keys = {
            "name": payload.get("name"),
            "description": payload.get("description"),
            "points": payload.get("points"),
            "submission_types": payload.get("submission_types"),
            "published": payload.get("published"),
            "post_to_sis": payload.get("post_to_sis"),
            "due_at": payload.get("due_at"),
            "unlock_at": payload.get("unlock_at"),
            "lock_at": payload.get("lock_at"),
            "assignment_group_name": payload.get("assignment_group_name"),
            "printable_path": payload.get("printable_path"),
            "module_name": payload.get("module_name"),
            "autoscore_schedule": payload.get("autoscore_schedule"),
            "autoscore_auto_push": payload.get("autoscore_auto_push"),
            "tiers": payload.get("tiers"),
        }
        return models.sha256_dict(keys)

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
            f"|{_normalize(payload.get('name'))}"
        )

    # ── Baseline / drift ─────────────────────────────────────────────────

    def capture_baseline(self, payload: dict, target: dict) -> dict:
        course_id = target["course_id"]
        name = payload.get("name", "")
        if payload.get("tiers"):
            try:
                groups = resolve_assignment_groups(course_id, payload["tiers"])
            except GroupResolutionError as exc:
                return {"canvas_error": str(exc)}
            assignments, error = canvas_client._canvas_get_all(
                f"/api/v1/courses/{course_id}/assignments",
                {"per_page": 100, "search_term": name},
            )
            if error:
                return {"canvas_error": "Canvas assignments could not be read."}
            matches = [
                {"id": str(row.get("id")), "html_url": row.get("html_url")}
                for row in (assignments or [])
                if row.get("id") is not None
                and _normalize(row.get("name")) == _normalize(name)
            ]
            return {"group_snapshot": groups["safe"], "existing_assignments": matches}

        baseline = {"existing_assignment": None}
        assignments, error = canvas_client._canvas_get(
            f"/api/v1/courses/{course_id}/assignments",
            params={"per_page": 100, "search_term": name},
        )
        if error:
            baseline["canvas_error"] = error
            return baseline
        for assignment in _as_list(assignments):
            if _normalize(assignment.get("name")) == _normalize(name):
                baseline["existing_assignment"] = {
                    "id": str(assignment.get("id")),
                    "name": assignment.get("name"),
                    "points_possible": assignment.get("points_possible"),
                    "published": assignment.get("published"),
                    "html_url": assignment.get("html_url"),
                }
                break
        return baseline

    def check_drift(self, payload: dict, target: dict, baseline: dict) -> bool:
        if payload.get("tiers"):
            if baseline is None or "canvas_error" in baseline:
                return True
            fresh = self.capture_baseline(payload, target)
            if "canvas_error" in fresh:
                return True
            if fresh.get("group_snapshot") != baseline.get("group_snapshot"):
                return True
            known = {
                str(step.get("returned_object_id"))
                for step in target.get("steps", [])
                if str(step.get("step_key", "")).startswith("create_tier_assignment:")
                and step.get("returned_object_id") is not None
            }
            current = {row["id"] for row in fresh.get("existing_assignments", [])}
            return bool(current - known)
        if baseline is None:
            return False
        if "canvas_error" in baseline:
            return True
        existing = baseline.get("existing_assignment")
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
        existing = baseline.get("existing_assignment")
        sub = payload.get("submission_types", [])
        dependencies = []
        if payload.get("printable_path"):
            dependencies.append({
                "type": "printable",
                "path": str(payload["printable_path"]),
            })
        if payload.get("module_name"):
            dependencies.append({
                "type": "module",
                "name": payload["module_name"],
            })
        autoscore = {}
        if payload.get("autoscore_schedule"):
            autoscore["scheduled"] = True
            autoscore["auto_push"] = bool(payload.get("autoscore_auto_push"))
        review = {
            "course_name": course_name,
            "assignment_name": payload.get("name"),
            "points": payload.get("points"),
            "description_preview": (payload.get("description") or "")[:120],
            "submission_types": sub,
            "published": payload.get("published"),
            "post_to_sis": payload.get("post_to_sis"),
            "due_at": payload.get("due_at"),
            "baseline_has_existing": existing is not None,
            "baseline_existing_id": existing.get("id") if existing else None,
            "baseline_existing_url": existing.get("html_url") if existing else None,
            "dependencies": dependencies,
            "autoscore": autoscore,
        }
        if payload.get("tiers"):
            safe = baseline.get("group_snapshot") or {}
            review.update({
                "tiered": True,
                "tier_count": len(payload["tiers"]),
                "tiers": [{
                    "label": row.get("label"),
                    "group": row.get("group_name"),
                    "student_count": row.get("student_count"),
                } for row in safe.get("tiers", [])],
                "only_visible_to_overrides": True,
                "tier_warning": (
                    "Canvas will create one assignment/gradebook column per tier; "
                    "only that group's students can see each assignment."
                ),
            })
            review["baseline_has_existing"] = bool(baseline.get("existing_assignments"))
            review["baseline_existing_id"] = None
            review["baseline_existing_url"] = None
        return review

    # ── Execute ──────────────────────────────────────────────────────────

    def execute(
        self, payload: dict, target: dict, baseline: dict,
        claim: dict, context,
    ) -> dict:
        if payload.get("tiers"):
            return _execute_tiered(payload, target, baseline, context)
        course_id = target["course_id"]
        name = payload.get("name", "Untitled assignment")
        steps = _ordered_steps(target)
        step = _step(steps, "create_assignment")
        assignment_id = target.get("returned_object_id") or step.get(
            "returned_object_id"
        )
        assignment_url = target.get("returned_object_url") or step.get(
            "returned_object_url"
        )

        # ── Idempotency: if already applied, verify by ID ──────────────
        assignment_verified = False
        if step.get("state") in ("applied", "skipped") and assignment_id:
            assignment, error = canvas_client._canvas_get(
                f"/api/v1/courses/{course_id}/assignments/{assignment_id}"
            )
            if not error and assignment:
                step["state"] = "skipped"
                assignment_url = (
                    assignment.get("html_url") or assignment_url
                )
                assignment_verified = True
            else:
                return _build_result(
                    "sent_unknown", steps=steps,
                    returned_object_id=assignment_id,
                    returned_object_url=assignment_url,
                    error_code="assignment_exact_id_unverified",
                )
        elif assignment_id:
            assignment, error = canvas_client._canvas_get(
                f"/api/v1/courses/{course_id}/assignments/{assignment_id}"
            )
            if not error and assignment:
                step["state"] = "skipped"
                assignment_url = (
                    assignment.get("html_url") or assignment_url
                )
                assignment_verified = True
            elif step.get("outbound_started_at"):
                return _build_result(
                    "sent_unknown", steps=steps,
                    returned_object_id=assignment_id,
                    returned_object_url=assignment_url,
                    error_code="assignment_exact_id_unverified",
                )
            else:
                assignment_id = None

        # ── Create the assignment (skip if already verified) ─────────
        if not assignment_verified:
            # Upload printable PDF before building the description
            printable_path = payload.get("printable_path")
            description = payload.get("description")
            if printable_path:
                uploaded, upload_err = _upload_course_file(course_id, printable_path)
                if upload_err:
                    return _build_result(
                        "failed", steps=steps,
                        error_code="printable_upload_failed",
                        private_diagnostic=upload_err,
                    )
                file_link = _file_link_html(uploaded)
                description = "\n".join(p for p in (description, file_link) if p)

            assignment_data = {
                "name": name,
                "submission_types": payload.get("submission_types", ["online_text_entry"]),
            }
            if description:
                assignment_data["description"] = description
            pts = payload.get("points")
            if pts is not None:
                assignment_data["points_possible"] = float(pts)
            exts = payload.get("allowed_extensions")
            if exts:
                assignment_data["allowed_extensions"] = exts
            ext_tool = payload.get("external_tool_tag_attributes")
            if ext_tool:
                assignment_data["external_tool_tag_attributes"] = ext_tool
            for key in ("due_at", "unlock_at", "lock_at"):
                val = payload.get(key)
                if val:
                    assignment_data[key] = val
            if payload.get("post_to_sis"):
                assignment_data["post_to_sis"] = True
            if payload.get("published"):
                assignment_data["published"] = True
            ag_name = payload.get("assignment_group_name")
            if ag_name:
                ag_id = _find_assignment_group(course_id, ag_name)
                if ag_id is not None:
                    assignment_data["assignment_group_id"] = ag_id

            request = {"assignment": assignment_data}
            path_create = f"/api/v1/courses/{course_id}/assignments"
            digest = models.sha256_dict({
                "method": "POST", "path": path_create, "payload": request,
            })
            step = context.before_send("create_assignment", digest)
            _replace_local_step(steps, step)
            response, error = canvas_client._canvas_send(
                "POST", path_create, request
            )
            if error:
                state = "sent_unknown" if _is_uncertain(error) else "failed"
                step["state"] = state
                step["error_code"] = (
                    "timeout_or_disconnect"
                    if state == "sent_unknown"
                    else "canvas_rejected"
                )
                step["private_diagnostic"] = error
                step = context.checkpoint_step(step)
                _replace_local_step(steps, step)
                return _build_result(
                    state, steps=steps,
                    error_code=step["error_code"],
                    private_diagnostic=error,
                )
            assignment_id = (
                str(response.get("id"))
                if isinstance(response, dict) and response.get("id") is not None
                else None
            )
            assignment_url = (
                response.get("html_url")
                if isinstance(response, dict)
                else None
            )
            if not assignment_id:
                step["state"] = "sent_unknown"
                step["error_code"] = "unparseable_response"
                step["private_diagnostic"] = "missing assignment id"
                step = context.checkpoint_step(step)
                _replace_local_step(steps, step)
                return _build_result(
                    "sent_unknown",
                    steps=_ordered_steps({"steps": steps}),
                    error_code="unparseable_response",
                )
            step["state"] = "applied"
            step = context.checkpoint_step(
                step,
                returned_object_id=assignment_id,
                returned_object_url=assignment_url,
            )
            _replace_local_step(steps, step)

        # ── Module attachment (post-create) ───────────────────────────
        module_name = payload.get("module_name")
        if module_name and assignment_id:
            result = _attach_to_module(
                course_id, assignment_id, name, module_name,
                steps, context,
            )
            if result.get("state") != "applied":
                return result

        # ── Scheduled autoscore (local queue write, post-creation) ────
        if payload.get("autoscore_schedule") and assignment_id:
            _aq = _autoscore_queue()
            settings = _autoscore_settings(payload)
            policy = _autoscore_push_policy(payload)
            job_id = _aq.make_job_id(course_id, assignment_id)
            schedule_digest = models.sha256_dict({
                "assignment_id": assignment_id,
                "due_at": payload.get("due_at"),
                "settings": settings,
                "auto_push": _as_bool(payload.get("autoscore_auto_push")),
                "push_policy": policy,
            })
            schedule_step = context.before_send(
                "schedule_autoscore", schedule_digest
            )
            _replace_local_step(steps, schedule_step)
            try:
                job = _schedule_autoscore(
                    course_id=course_id,
                    course_name=_active_course_name(course_id),
                    assignment_id=assignment_id,
                    assignment_name=name,
                    payload=payload,
                    settings=settings,
                    push_policy=policy,
                    queue=_aq,
                )
                returned_job_id = str(job.get("job_id") or job_id)
                if returned_job_id != job_id:
                    raise ValueError("autoscore queue returned an unexpected job ID")
                schedule_step["state"] = "applied"
                schedule_step = context.checkpoint_step(
                    schedule_step, returned_object_id=job_id
                )
                _replace_local_step(steps, schedule_step)
            except Exception as exc:
                schedule_step["state"] = "failed"
                schedule_step["error_code"] = "autoscore_queue_failed"
                schedule_step["private_diagnostic"] = type(exc).__name__
                schedule_step = context.checkpoint_step(schedule_step)
                _replace_local_step(steps, schedule_step)
                return _build_result(
                    "partial",
                    steps=steps,
                    returned_object_id=assignment_id,
                    returned_object_url=assignment_url,
                    error_code="autoscore_queue_failed",
                    private_diagnostic=type(exc).__name__,
                )

        return _build_result(
            "applied", steps=steps,
            returned_object_id=assignment_id,
            returned_object_url=assignment_url,
        )

    # ── Reconciliation ───────────────────────────────────────────────────

    def reconcile(self, payload: dict, target: dict, baseline: dict) -> dict:
        if payload.get("tiers"):
            return _reconcile_tiered(payload, target)
        course_id = target["course_id"]
        steps = _ordered_steps(target)
        step = _step(steps, "create_assignment")
        assignment_id = target.get("returned_object_id") or step.get(
            "returned_object_id"
        )
        has_marker = _has_outbound_marker(steps)

        if not assignment_id:
            name = payload.get("name", "")
            assignments, error = canvas_client._canvas_get(
                f"/api/v1/courses/{course_id}/assignments",
                params={"per_page": 100, "search_term": name},
            )
            if error:
                return {"state": "sent_unknown"}
            if any(
                _normalize(a.get("name")) == _normalize(name)
                for a in _as_list(assignments)
            ):
                return {"state": "sent_unknown"}
            return {
                "state": "sent_unknown" if has_marker else "pending",
            }

        assignment, error = canvas_client._canvas_get(
            f"/api/v1/courses/{course_id}/assignments/{assignment_id}"
        )
        if error:
            if "404" in str(error) and not step.get("outbound_started_at"):
                return {"state": "pending"}
            return {"state": "sent_unknown"}
        if not assignment:
            return {"state": "sent_unknown"}

        result = {
            "state": "applied",
            "returned_object_id": assignment_id,
            "returned_object_url": assignment.get("html_url"),
        }

        # Verify module item exists when module_name is set
        module_name = payload.get("module_name")
        if not module_name:
            return result

        create_module_step = _find_step(steps, "create_module")
        attach_step = _find_step(steps, "attach_module")
        module_id = _module_id_from_steps(create_module_step, attach_step)
        if not module_id:
            return {"state": "sent_unknown" if has_marker else "pending",
                    "returned_object_id": assignment_id,
                    "returned_object_url": assignment.get("html_url")}

        item_id = attach_step.get("returned_object_id")
        if item_id:
            item, item_error = canvas_client._canvas_get(
                f"/api/v1/courses/{course_id}/modules/{module_id}/items/{item_id}")
            if not item_error and item:
                if (str(item.get("type", "")).lower() == "assignment"
                        and str(item.get("content_id")) == str(assignment_id)):
                    result["module_item_id"] = item_id
                    return result

        items, item_error = canvas_client._canvas_get_all(
            f"/api/v1/courses/{course_id}/modules/{module_id}/items",
            {"per_page": 100},
        )
        if item_error:
            return {"state": "sent_unknown", "returned_object_id": assignment_id}
        matches = [item for item in (items or [])
                   if str(item.get("type", "")).lower() == "assignment"
                   and str(item.get("content_id")) == str(assignment_id)]
        if len(matches) == 1 and matches[0].get("id") is not None:
            result["module_item_id"] = str(matches[0]["id"])
            return result
        if attach_step.get("outbound_started_at") or has_marker:
            return {"state": "sent_unknown", "returned_object_id": assignment_id}
        return {"state": "pending", "returned_object_id": assignment_id}

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


def _find_assignment_group(course_id: str, name: str) -> int | None:
    """Resolve an assignment group name to its Canvas numeric ID, or None."""
    data, err = canvas_client._canvas_get_all(
        f"/api/v1/courses/{course_id}/assignment_groups",
        {"per_page": 100},
    )
    if err:
        return None
    for group in data or []:
        if _normalize(group.get("name")) == _normalize(name):
            gid = group.get("id")
            return int(gid) if gid is not None else None
    return None


def _reconcile_tiered(payload: dict, target: dict) -> dict:
    """Prove every completed tier dependency by exact durable identity."""
    course_id = target["course_id"]
    stored_steps = _ordered_steps(target)
    projected = []
    module_step = _find_step(stored_steps, "create_module")
    module_id = module_step.get("returned_object_id")

    if payload.get("module_name") and module_id:
        module, error = canvas_client._canvas_get(
            f"/api/v1/courses/{course_id}/modules/{module_id}"
        )
        if error or not module or str(module.get("id")) != str(module_id):
            return _tier_reconcile_result("sent_unknown", projected)
        projected.append(_applied_safe_step(module_step))

    for index, _tier in enumerate(payload.get("tiers") or []):
        assignment_step = _find_step(stored_steps, f"create_tier_assignment:{index}")
        assignment_id = assignment_step.get("returned_object_id")
        if not assignment_id:
            return _tier_reconcile_unfinished(assignment_step, projected)
        assignment, error = canvas_client._canvas_get(
            f"/api/v1/courses/{course_id}/assignments/{assignment_id}"
        )
        if (error or not assignment
                or str(assignment.get("id")) != str(assignment_id)):
            return _tier_reconcile_result("sent_unknown", projected)
        projected.append(_applied_safe_step(
            assignment_step, returned_object_url=assignment.get("html_url")
        ))

        override_step = _find_step(stored_steps, f"create_tier_override:{index}")
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
            attach_step = _find_step(stored_steps, f"attach_module:{index}")
            item_id = attach_step.get("returned_object_id")
            step_module_id = attach_step.get("module_id") or module_id
            if not item_id or not step_module_id:
                return _tier_reconcile_unfinished(attach_step, projected)
            item, error = canvas_client._canvas_get(
                f"/api/v1/courses/{course_id}/modules/{step_module_id}/items/{item_id}"
            )
            if (error or not item
                    or str(item.get("id")) != str(item_id)
                    or str(item.get("type", "")).casefold() != "assignment"
                    or str(item.get("content_id")) != str(assignment_id)):
                return _tier_reconcile_result("sent_unknown", projected)
            projected.append(_applied_safe_step(attach_step))

        if payload.get("autoscore_schedule"):
            schedule_step = _find_step(stored_steps, f"schedule_autoscore:{index}")
            expected_job_id = _autoscore_queue().make_job_id(course_id, assignment_id)
            if not schedule_step.get("returned_object_id"):
                return _tier_reconcile_unfinished(schedule_step, projected)
            if str(schedule_step.get("returned_object_id")) != str(expected_job_id):
                return _tier_reconcile_result("sent_unknown", projected)
            try:
                jobs = (_autoscore_queue().load_queue() or {}).get("jobs", [])
            except Exception:
                return _tier_reconcile_result("sent_unknown", projected)
            job = next(
                (row for row in jobs if str(row.get("job_id")) == str(expected_job_id)),
                None,
            )
            if (not job or str(job.get("course_id")) != str(course_id)
                    or str(job.get("assignment_id")) != str(assignment_id)):
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


def _execute_tiered(payload: dict, target: dict, baseline: dict, context) -> dict:
    """Apply ordered tier assignment/override steps without persisting roster IDs."""
    course_id = target["course_id"]
    tiers = payload["tiers"]
    steps = _ordered_steps(target)
    try:
        resolved = resolve_assignment_groups(course_id, tiers)
    except GroupResolutionError:
        return _build_result("failed", steps=steps, error_code="group_resolution_failed")
    if resolved["safe"] != baseline.get("group_snapshot"):
        return _build_result("failed", steps=steps, error_code="group_membership_drift")

    safe_by_index = {row["index"]: row for row in resolved["safe"]["tiers"]}
    transient_ids = resolved["student_ids_by_group"]
    last_assignment_id = None
    last_assignment_url = None

    for index, tier in enumerate(tiers):
        assignment_key = f"create_tier_assignment:{index}"
        override_key = f"create_tier_override:{index}"
        assignment_step = _ensure_step(steps, assignment_key)
        assignment_id = assignment_step.get("returned_object_id")
        assignment_url = assignment_step.get("returned_object_url")

        if assignment_id:
            existing, error = canvas_client._canvas_get(
                f"/api/v1/courses/{course_id}/assignments/{assignment_id}"
            )
            if error or not existing:
                return _build_result(
                    "sent_unknown", steps=steps,
                    error_code="assignment_exact_id_unverified",
                )
            assignment_step["state"] = "skipped"
            assignment_url = existing.get("html_url") or assignment_url
        elif assignment_step.get("outbound_started_at"):
            return _build_result(
                "sent_unknown", steps=steps,
                error_code="assignment_creation_unresolved",
            )
        else:
            assignment_data = _assignment_data(payload, tier["description"], course_id)
            assignment_data["only_visible_to_overrides"] = True
            request = {"assignment": assignment_data}
            path = f"/api/v1/courses/{course_id}/assignments"
            marked = context.before_send(assignment_key, models.sha256_dict({
                "method": "POST", "path": path, "payload": request,
            }))
            _replace_local_step(steps, marked)
            response, error = canvas_client._canvas_send("POST", path, request)
            if error:
                state = "sent_unknown" if _is_uncertain(error) else _tier_failure_state(steps)
                marked["state"] = state if state == "sent_unknown" else "failed"
                marked["error_code"] = "timeout_or_disconnect" if state == "sent_unknown" else "canvas_rejected"
                marked["private_diagnostic"] = type(error).__name__
                marked = context.checkpoint_step(marked)
                _replace_local_step(steps, marked)
                return _build_result(state, steps=steps, error_code=marked["error_code"])
            assignment_id = str(response.get("id")) if isinstance(response, dict) and response.get("id") is not None else None
            assignment_url = response.get("html_url") if isinstance(response, dict) else None
            if not assignment_id:
                marked["state"] = "sent_unknown"
                marked["error_code"] = "unparseable_response"
                marked["private_diagnostic"] = "missing assignment id"
                marked = context.checkpoint_step(marked)
                _replace_local_step(steps, marked)
                return _build_result("sent_unknown", steps=steps, error_code="unparseable_response")
            marked["state"] = "applied"
            marked = context.checkpoint_step(
                marked, returned_object_id=assignment_id,
                returned_object_url=assignment_url,
            )
            _replace_local_step(steps, marked)

        last_assignment_id, last_assignment_url = assignment_id, assignment_url
        override_step = _ensure_step(steps, override_key)
        override_id = override_step.get("returned_object_id")
        if override_id:
            existing, error = canvas_client._canvas_get(
                f"/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides/{override_id}"
            )
            if error or not existing:
                return _build_result("sent_unknown", steps=steps, error_code="override_exact_id_unverified")
            override_step["state"] = "skipped"
        elif override_step.get("outbound_started_at"):
            return _build_result("sent_unknown", steps=steps, error_code="override_creation_unresolved")
        else:
            safe_tier = safe_by_index[index]
            override_request = {"assignment_override": {
                "title": f"{tier['label']} assignment access",
                "student_ids": transient_ids[safe_tier["group_id"]],
            }}
            for key in ("due_at", "unlock_at", "lock_at"):
                if payload.get(key):
                    override_request["assignment_override"][key] = payload[key]
            path = f"/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides"
            # Persist only the accepted safe membership digest, never the request body.
            marked = context.before_send(override_key, models.sha256_dict({
                "method": "POST", "path": path,
                "membership_digest": safe_tier["membership_digest"],
            }))
            _replace_local_step(steps, marked)
            response, error = canvas_client._canvas_send("POST", path, override_request)
            if error:
                state = "sent_unknown" if _is_uncertain(error) else "partial"
                marked["state"] = state if state == "sent_unknown" else "failed"
                marked["error_code"] = "timeout_or_disconnect" if state == "sent_unknown" else "override_rejected"
                marked["private_diagnostic"] = type(error).__name__
                marked = context.checkpoint_step(marked)
                _replace_local_step(steps, marked)
                return _build_result(state, steps=steps, error_code=marked["error_code"])
            override_id = str(response.get("id")) if isinstance(response, dict) and response.get("id") is not None else None
            if not override_id:
                marked["state"] = "sent_unknown"
                marked["error_code"] = "unparseable_response"
                marked["private_diagnostic"] = "missing override id"
                marked = context.checkpoint_step(marked)
                _replace_local_step(steps, marked)
                return _build_result("sent_unknown", steps=steps, error_code="unparseable_response")
            marked["state"] = "applied"
            marked = context.checkpoint_step(marked, returned_object_id=override_id)
            _replace_local_step(steps, marked)

        if payload.get("module_name"):
            result = _attach_to_module(
                course_id, assignment_id, payload["name"], payload["module_name"],
                steps, context, attach_step_key=f"attach_module:{index}",
            )
            if result.get("state") != "applied":
                if result.get("state") == "failed":
                    result["state"] = "partial"
                return result

        if payload.get("autoscore_schedule"):
            result = _schedule_tier_autoscore(
                payload, course_id, assignment_id, index, steps, context
            )
            if result is not None:
                return result

    return _build_result(
        "applied", steps=steps,
        returned_object_id=None, returned_object_url=None,
    )


def _assignment_data(payload: dict, description: str, course_id: str) -> dict:
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
        group_id = _find_assignment_group(course_id, assignment_group_name)
        if group_id is not None:
            data["assignment_group_id"] = group_id
    return data


def _tier_failure_state(steps: list[dict]) -> str:
    return "partial" if any(
        step.get("state") in ("applied", "skipped")
        and step.get("returned_object_id")
        for step in steps
    ) else "failed"


def _schedule_tier_autoscore(payload, course_id, assignment_id, index, steps, context):
    queue = _autoscore_queue()
    settings = _autoscore_settings(payload)
    policy = _autoscore_push_policy(payload)
    job_id = queue.make_job_id(course_id, assignment_id)
    key = f"schedule_autoscore:{index}"
    step = _ensure_step(steps, key)
    if step.get("returned_object_id") == job_id and step.get("state") in ("applied", "skipped"):
        step["state"] = "skipped"
        return None
    marked = context.before_send(key, models.sha256_dict({
        "assignment_id": assignment_id, "due_at": payload.get("due_at"),
        "settings": settings, "auto_push": _as_bool(payload.get("autoscore_auto_push")),
        "push_policy": policy,
    }))
    _replace_local_step(steps, marked)
    try:
        job = _schedule_autoscore(
            course_id=course_id, course_name=_active_course_name(course_id),
            assignment_id=assignment_id, assignment_name=payload["name"],
            payload=payload, settings=settings, push_policy=policy, queue=queue,
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
        return _build_result("partial", steps=steps, error_code="autoscore_queue_failed")


def _validate_printable_pdf(pdf_path: str) -> tuple:
    """Validate a printable PDF path. Returns (Path, None) or (None, error)."""
    if not pdf_path:
        return None, "printable_path is required"
    candidate = os.path.realpath(pdf_path)
    if not os.path.isfile(candidate):
        return None, "printable PDF not found"
    if Path(candidate).suffix.lower() != ".pdf":
        return None, "printable attachment must be a PDF"

    for root in _allowed_printable_roots():
        try:
            if os.path.commonpath([candidate, root]) == root:
                return Path(candidate), None
        except ValueError:
            continue
    return None, "printable PDF is outside Canvas Expert export folders"


def _allowed_printable_roots():
    """Return directory roots where printable PDFs are allowed."""
    from api.webui.deps import _exports_dir
    roots = []
    try:
        roots.append(os.path.realpath(_exports_dir()))
    except Exception:
        pass
    try:
        from api.webui import config as _cfg
        ws = _cfg.get_workspace_path()
        if ws:
            roots.append(os.path.realpath(ws))
    except Exception:
        pass
    return roots


def _upload_course_file(course_id: str, pdf_path: Path):
    """Upload a PDF to a Canvas course. Returns (file_json, None) or (None, error)."""
    pdf, err = _validate_printable_pdf(str(pdf_path))
    if err:
        return None, err
    filename = pdf.name
    content_type = mimetypes.guess_type(filename)[0] or "application/pdf"
    init_payload = {
        "name": filename,
        "size": pdf.stat().st_size,
        "content_type": content_type,
        "parent_folder_path": "Canvas Expert Printables",
        "on_duplicate": "rename",
    }
    init, err = canvas_client._canvas_send(
        "POST", f"/api/v1/courses/{course_id}/files", init_payload
    )
    if err:
        return None, err
    upload_url = (init or {}).get("upload_url")
    upload_params = (init or {}).get("upload_params") or {}
    if not upload_url:
        return None, "Canvas did not return a file upload URL"
    try:
        with pdf.open("rb") as fh:
            response = requests.post(
                upload_url,
                data=upload_params,
                files={"file": (filename, fh, content_type)},
                timeout=60,
            )
    except requests.RequestException as exc:
        return None, str(exc)
    if response.status_code not in (200, 201):
        return None, (
            f"Canvas file upload failed: HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )
    try:
        return response.json(), None
    except ValueError:
        return None, "Canvas file upload returned a non-JSON response"


def _file_link_html(uploaded_file: dict) -> str:
    """Build an HTML link for an uploaded Canvas file."""
    import html as _html
    label = _html.escape(
        uploaded_file.get("display_name")
        or uploaded_file.get("filename")
        or "Printable PDF"
    )
    url = uploaded_file.get("url") or uploaded_file.get("html_url") or ""
    if not url and uploaded_file.get("id"):
        url = f"/files/{uploaded_file['id']}/download?download_frd=1"
    if not url:
        return f"<p><strong>{label}</strong> uploaded to course files.</p>"
    return f'<p><a href="{_html.escape(str(url), quote=True)}">{label}</a></p>'


def _attach_to_module(
    course_id: str, assignment_id: str, name: str,
    module_name: str, steps: list[dict], context,
    *, attach_step_key: str = "attach_module",
) -> dict:
    """Find or create a Canvas module and attach the assignment.

    Returns a result dict (``{"state": ...}``).  On success the steps list
    is mutated in place; on failure returns a *build_result early-return dict.
    """
    create_module_step = _find_step(steps, "create_module")
    attach_step = _find_step(steps, attach_step_key)
    module_id = _module_id_from_steps(create_module_step, attach_step)

    if not module_id:
        modules, error = _read_modules(course_id)
        if error:
            return _build_result(
                "sent_unknown", steps=steps,
                error_code="module_lookup_failed",
                private_diagnostic=error,
                returned_object_id=assignment_id,
            )
        matches = [
            m for m in modules
            if _normalize(m.get("name")) == _normalize(module_name)
        ]
        if len(matches) > 1:
            return _build_result(
                "blocked", steps=steps,
                error_code="ambiguous_module",
                returned_object_id=assignment_id,
            )
        if matches:
            module_id = str(matches[0].get("id"))
            attach_step = _ensure_step(steps, attach_step_key)
            attach_step["module_id"] = module_id
        else:
            create_module_step = _ensure_step(steps, "create_module")
            if (create_module_step.get("state") == "sent_unknown"
                    and create_module_step.get("outbound_started_at")
                    and not create_module_step.get("returned_object_id")):
                return _build_result(
                    "sent_unknown", steps=steps,
                    error_code="module_creation_unresolved",
                    returned_object_id=assignment_id,
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
                    returned_object_id=assignment_id,
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
                    returned_object_id=assignment_id,
                )
            create_module_step["state"] = "applied"
            create_module_step = context.checkpoint_step(
                create_module_step, returned_object_id=module_id
            )
            _replace_local_step(steps, create_module_step)

    # ── Attach the assignment to the module ──────────────────────────
    attach_step = _ensure_step(steps, attach_step_key)
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
                returned_object_id=assignment_id,
            )
        return _build_result("applied", steps=steps,
                             returned_object_id=assignment_id)

    item_path = f"/api/v1/courses/{course_id}/modules/{module_id}/items"
    item_request = {
        "module_item": {
            "title": name,
            "type": "Assignment",
            "content_id": int(assignment_id),
        }
    }
    attach_step = context.checkpoint_step(attach_step)
    _replace_local_step(steps, attach_step)
    digest = models.sha256_dict({
        "method": "POST", "path": item_path, "payload": item_request,
    })
    marked = context.before_send(attach_step_key, digest)
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
            returned_object_id=assignment_id,
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
            returned_object_id=assignment_id,
        )
    attach_step["state"] = "applied"
    attach_step["module_id"] = str(module_id)
    attach_step = context.checkpoint_step(
        attach_step, returned_object_id=item_id
    )
    _replace_local_step(steps, attach_step)
    return _build_result("applied", steps=steps,
                         returned_object_id=assignment_id)


def _ordered_steps(target: dict) -> list[dict]:
    existing = {
        step.get("step_key"): step
        for step in target.get("steps", [])
    }
    if any(":" in str(key) for key in existing):
        def tier_order(step):
            key = str(step.get("step_key") or "")
            if key == "create_module":
                return (-1, 0)
            prefix, _, suffix = key.partition(":")
            rank = {
                "create_tier_assignment": 0,
                "create_tier_override": 1,
                "attach_module": 2,
                "schedule_autoscore": 3,
            }.get(prefix, 9)
            return (int(suffix) if suffix.isdigit() else 999999, rank)
        return sorted(existing.values(), key=tier_order)
    order = (
        "create_assignment", "create_module", "attach_module",
        "schedule_autoscore",
    )
    return [existing[key] for key in order if key in existing]


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


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _autoscore_settings(payload: dict) -> dict:
    return {
        "mode": "assisted",
        "model_id": str(payload.get("autoscore_model_id") or "").strip()
        or config.get_openrouter_model(),
        "persona_id": str(payload.get("autoscore_persona_id") or "sage").strip() or "sage",
        "response_kind": str(payload.get("autoscore_response_kind") or "scr").strip() or "scr",
        "rubric_name": str(payload.get("autoscore_rubric_name") or "").strip(),
        "watch_late": True if payload.get("autoscore_watch_late") is None
        else _as_bool(payload.get("autoscore_watch_late")),
    }


def _autoscore_push_policy(payload: dict) -> dict:
    auto_push = _as_bool(payload.get("autoscore_auto_push"))
    return {
        "enabled": auto_push,
        "allow_grade_push": True,
        "allow_comment_push": True,
        "policy_version": "2.0",
    }


def _schedule_autoscore(
    *,
    course_id: str,
    course_name: str,
    assignment_id: str,
    assignment_name: str,
    payload: dict,
    settings: dict,
    push_policy: dict,
    queue,
) -> dict:
    """Schedule a PowerGrader autoscore job for this assignment.

    This is a local queue write only — no Canvas API call.
    """
    due_at = str(payload.get("due_at") or "").strip()
    if not due_at:
        raise ValueError("due_at is required for scheduled Auto-Score")
    return queue.upsert_job(
        course_id=course_id,
        course_name=course_name,
        assignment_id=assignment_id,
        assignment_name=assignment_name,
        due_at=due_at,
        source="push",
        settings=settings,
        assignment={
            "name": assignment_name,
            "due_at": due_at,
            "submission_types": payload.get("submission_types", []),
            "allowed_extensions": payload.get("allowed_extensions", []),
        },
        auto_push=_as_bool(payload.get("autoscore_auto_push")),
        push_policy=push_policy,
    )


def _active_course_name(course_id: str) -> str:
    for course in config.active_courses():
        if str(course.get("id")) == str(course_id):
            return str(
                course.get("name") or course.get("nickname") or course_id
            )
    return str(course_id)


def _autoscore_queue():
    """Lazy queue import so adapter tests can replace the local-write boundary."""
    from api.powergrader import autoscore_queue
    return autoscore_queue

"""Crash-safe SIS grade-bridge operation adapter.

All family discovery, private roster/submission reads, Canvas mutations, exact
postcondition checks, retry decisions, and reconciliation for
``gradebook.sis_bridge`` live here.  Assistant-facing projections are owned by
``api.sis_grade_bridge`` and never expose this adapter's private baselines.
"""

from __future__ import annotations

import copy
import math
from typing import Any

from api import operational_log
from api.platform_services import canvas_client, config

from .. import models
from . import adapter_support


KIND = "gradebook.sis_bridge"
_DESCRIPTION = (
    "<p><strong>This is not your quiz.</strong> This assignment is only used to "
    "sync your grade. Open your Canvas Dashboard or To Do list and complete the "
    "version whose title includes your color tag (Red, Blue, or Silver).</p>"
)
_PREVIOUS_DESCRIPTION = (
    "No submission is required here. Your grade is copied from the version "
    "of this assignment that was assigned to you."
)
_SCORE_TOLERANCE = 1e-6


class _BridgeReadError(RuntimeError):
    pass


class _BridgeInvariantError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


class SisGradeBridgeAdapter:
    kind = KIND

    def build_payload(self, prepare_request: dict) -> dict:
        if not isinstance(prepare_request, dict):
            raise ValueError("prepare request must be an object")
        course_id = _required_text(prepare_request.get("course_id"), "course_id")
        family_title = _required_text(
            prepare_request.get("family_title"), "family_title"
        )
        registration = prepare_request.get("registration")
        payload = {
            "course_id": course_id,
            "family_title": family_title,
            "registered": bool(registration),
            "source_assignment_ids": [],
            "source_titles": [],
            "bridge_assignment_id": None,
            "registered_bridge_digest": None,
        }
        if registration:
            if not isinstance(registration, dict):
                raise ValueError("registration must be an object")
            if str(registration.get("family_title") or "").strip() != family_title:
                raise ValueError("registered family title does not match request")
            payload.update({
                "source_assignment_ids": [
                    _required_text(value, "source_assignment_id")
                    for value in (registration.get("source_assignment_ids") or [])
                ],
                "source_titles": [
                    _required_text(value, "source_title")
                    for value in (registration.get("source_titles") or [])
                ],
                "bridge_assignment_id": _required_text(
                    registration.get("bridge_assignment_id"),
                    "bridge_assignment_id",
                ),
                "registered_bridge_digest": _required_text(
                    registration.get("bridge_state_digest"),
                    "bridge_state_digest",
                ),
            })
            if len(payload["source_assignment_ids"]) < 2:
                raise ValueError("registered bridge has fewer than two sources")
            if len(payload["source_assignment_ids"]) != len(payload["source_titles"]):
                raise ValueError("registered source IDs and titles do not align")
        return payload

    def freeze_payload(self, payload: dict, baseline: dict) -> dict:
        """Freeze discovery results into the operation's private payload."""
        if baseline.get("blocking_error"):
            raise ValueError(str(baseline["blocking_error"]))
        frozen = copy.deepcopy(payload)
        frozen.update({
            "source_assignment_ids": list(baseline["source_assignment_ids"]),
            "source_titles": list(baseline["source_titles"]),
            "points_possible": baseline["points_possible"],
            "assignment_group_id": baseline["assignment_group_id"],
            "due_at": baseline["due_at"],
        })
        return frozen

    def source_digest(self, payload: dict) -> str:
        return models.sha256_dict({
            "course_id": payload.get("course_id"),
            "family_title": payload.get("family_title"),
            "registered": bool(payload.get("registered")),
            "source_assignment_ids": payload.get("source_assignment_ids") or [],
            "source_titles": payload.get("source_titles") or [],
            "bridge_assignment_id": payload.get("bridge_assignment_id"),
            "registered_bridge_digest": payload.get("registered_bridge_digest"),
            "points_possible": payload.get("points_possible"),
            "assignment_group_id": payload.get("assignment_group_id"),
            "due_at": payload.get("due_at"),
        })

    def verify_targets(self, payload: dict, targets: list[dict]) -> list[dict]:
        active_ids = {str(course.get("id") or "").strip()
                      for course in config.active_courses()}
        verified = []
        for target in targets:
            course_id = str(target.get("course_id") or "").strip()
            if not course_id or course_id != payload.get("course_id"):
                raise ValueError("target course does not match bridge request")
            if course_id not in active_ids:
                raise ValueError("course is not in Current courses")
            verified.append({
                "course_id": course_id,
                "target_key": self.target_key(payload, course_id),
                "idempotency_key": self.idempotency_key(payload, course_id),
            })
        if len(verified) != 1:
            raise ValueError("a bridge operation requires exactly one course target")
        return verified

    def target_key(self, payload: dict, course_id: str) -> str:
        return models.sha256_hex(
            f"{KIND}|{course_id}|{payload.get('family_title', '')}"
        )

    def idempotency_key(self, payload: dict, course_id: str) -> str:
        return models.sha256_hex(
            f"{course_id}|{self.source_digest(payload)}"
        )

    def capture_baseline(self, payload: dict, target: dict) -> dict:
        try:
            return self._capture_baseline(payload, target)
        except _BridgeInvariantError as exc:
            return {
                "blocking_error": exc.code,
                "private_diagnostic": exc.detail or exc.code,
            }
        except _BridgeReadError as exc:
            return {
                "blocking_error": "canvas_read_failed",
                "private_diagnostic": str(exc),
            }

    def _capture_baseline(self, payload: dict, target: dict) -> dict:
        course_id = target["course_id"]
        assignments = _get_all(
            f"/api/v1/courses/{course_id}/assignments",
            {"per_page": 100},
        )
        known_bridge_id = _bridge_id(
            payload, target, copy.deepcopy(target.get("steps") or [])
        )
        source_rows, bridge_row = _resolve_family_assignments(
            payload, assignments, known_bridge_id=known_bridge_id
        )
        _validate_source_identity(payload, source_rows)

        bridge_state = None
        if payload.get("registered"):
            bridge_id = str(payload.get("bridge_assignment_id") or "")
            if bridge_row is None or str(bridge_row.get("id")) != bridge_id:
                raise _BridgeInvariantError("registered_bridge_missing_or_renamed")
            bridge_state = _read_bridge_state(course_id, bridge_id, bridge_row)
            if _bridge_digest(bridge_state) != payload.get("registered_bridge_digest"):
                raise _BridgeInvariantError("registered_bridge_drift")
        elif bridge_row is not None:
            if not known_bridge_id or str(bridge_row.get("id")) != known_bridge_id:
                raise _BridgeInvariantError("bridge_title_collision")
            bridge_state = _read_bridge_state(course_id, known_bridge_id, bridge_row)
            if not _operation_bridge_state_is_valid(payload, target, bridge_state):
                raise _BridgeInvariantError("operation_bridge_drift")

        active_users = _get_all(
            f"/api/v1/courses/{course_id}/users",
            {
                "enrollment_type[]": "student",
                "enrollment_state[]": "active",
                "per_page": 100,
            },
        )
        active_ids = {str(row.get("id")) for row in active_users
                      if row.get("id") is not None}

        source_states = []
        source_memberships: list[list[str]] = []
        effective_due_dates: list[str | None] = []
        for source in source_rows:
            _validate_source_shape(source)
            source_id = str(source["id"])
            overrides = _get_all(
                f"/api/v1/courses/{course_id}/assignments/{source_id}/overrides",
                {"per_page": 100},
            )
            members, due_dates = _explicit_override_members(source, overrides)
            source_memberships.append(sorted(members))
            effective_due_dates.extend(due_dates)
            source_states.append(_source_state(source, overrides))

        _validate_common_source_shape(source_rows, effective_due_dates)
        memberships_by_student: dict[str, list[int]] = {}
        all_members = set()
        for source_index, members in enumerate(source_memberships):
            for user_id in members:
                all_members.add(user_id)
                if user_id in active_ids:
                    memberships_by_student.setdefault(user_id, []).append(source_index)
        overlaps = {uid: indexes for uid, indexes in memberships_by_student.items()
                    if len(indexes) > 1}
        if overlaps:
            raise _BridgeInvariantError(
                "overlapping_active_memberships",
                f"active_overlap_count={len(overlaps)}",
            )

        grade_entries = []
        pending_review = 0
        unsubmitted = 0
        skipped_other = 0
        submission_counts = 0
        for source_index, source in enumerate(source_rows):
            source_id = str(source["id"])
            submissions = _get_all(
                f"/api/v1/courses/{course_id}/assignments/{source_id}/submissions",
                {"per_page": 100},
            )
            by_user: dict[str, dict] = {}
            for submission in submissions:
                user_id = str(submission.get("user_id") or "")
                if not user_id:
                    continue
                if user_id in by_user:
                    raise _BridgeInvariantError("duplicate_submission_row")
                by_user[user_id] = submission

            for user_id in source_memberships[source_index]:
                if user_id not in active_ids:
                    continue
                submission_counts += 1
                submission = by_user.get(user_id)
                if not submission:
                    unsubmitted += 1
                    continue
                workflow_state = str(submission.get("workflow_state") or "")
                if workflow_state == "pending_review":
                    pending_review += 1
                    continue
                if workflow_state == "unsubmitted":
                    unsubmitted += 1
                    continue
                if bool(submission.get("excused")):
                    grade_entries.append({
                        "source_index": source_index,
                        "source_assignment_id": source_id,
                        "user_id": user_id,
                        "excused": True,
                        "score": None,
                        "late_policy_status": _late_status(submission),
                    })
                    continue
                score = submission.get("score")
                if workflow_state == "graded" and _is_number(score):
                    grade_entries.append({
                        "source_index": source_index,
                        "source_assignment_id": source_id,
                        "user_id": user_id,
                        "excused": False,
                        "score": float(score),
                        "late_policy_status": _late_status(submission),
                    })
                else:
                    skipped_other += 1

        grade_entries.sort(key=lambda row: (row["source_index"], row["user_id"]))
        assigned_active = len(memberships_by_student)
        uncovered_active = len(active_ids - set(memberships_by_student))
        inactive_assignees = len(all_members - active_ids)
        counts = {
            "active_students": len(active_ids),
            "assigned_active": assigned_active,
            "uncovered_active": uncovered_active,
            "overlapping_active": 0,
            "inactive_assignees": inactive_assignees,
            "eligible_final": len(grade_entries),
            "eligible_numeric": sum(not row["excused"] for row in grade_entries),
            "eligible_excused": sum(bool(row["excused"]) for row in grade_entries),
            "pending_review": pending_review,
            "unsubmitted": unsubmitted,
            "skipped_other": skipped_other,
        }
        if submission_counts != assigned_active:
            raise _BridgeInvariantError("membership_count_inconsistent")

        warnings = [
            {"code": code, "count": counts[count_key]}
            for code, count_key in (
                ("active_students_uncovered", "uncovered_active"),
                ("pending_review_skipped", "pending_review"),
                ("unsubmitted_skipped", "unsubmitted"),
                ("inactive_assignees_ignored", "inactive_assignees"),
                ("other_nonfinal_skipped", "skipped_other"),
            )
            if counts[count_key]
        ]

        first = source_rows[0]
        baseline = {
            "source_assignment_ids": [str(row["id"]) for row in source_rows],
            "source_titles": [str(row.get("name") or "") for row in source_rows],
            "source_states": source_states,
            "source_memberships": source_memberships,
            "active_student_ids": sorted(active_ids),
            "grade_entries": grade_entries,
            "points_possible": _normalized_number(first.get("points_possible")),
            "assignment_group_id": str(first.get("assignment_group_id")),
            "due_at": effective_due_dates[0],
            "bridge_state": bridge_state,
            "counts": counts,
            "warnings": warnings,
        }
        baseline["validation_digest"] = models.sha256_dict({
            "source_assignment_ids": baseline["source_assignment_ids"],
            "source_titles": baseline["source_titles"],
            "source_states": [
                {
                    key: value for key, value in state.items()
                    if key not in {"omit_from_final_grade", "post_to_sis"}
                }
                for state in source_states
            ],
            "source_memberships": source_memberships,
            "active_student_ids": baseline["active_student_ids"],
            "grade_entries": grade_entries,
            "points_possible": baseline["points_possible"],
            "assignment_group_id": baseline["assignment_group_id"],
            "due_at": baseline["due_at"],
            "counts": counts,
        })
        baseline["baseline_digest"] = models.sha256_dict(baseline)
        return baseline

    def check_drift(self, payload: dict, target: dict, baseline: dict) -> bool:
        fresh = self.capture_baseline(payload, target)
        if fresh.get("blocking_error"):
            return True
        return fresh.get("validation_digest") != baseline.get("validation_digest")

    def freeze_review(self, payload: dict, target: dict, baseline: dict) -> dict:
        if baseline.get("blocking_error"):
            raise ValueError(str(baseline["blocking_error"]))
        return {
            "course_id": target["course_id"],
            "family_title": payload["family_title"],
            "source_count": len(baseline.get("source_assignment_ids") or []),
            "bridge_exists": bool(payload.get("registered")),
            "points_possible": baseline.get("points_possible"),
            "common_assignment_group": True,
            "common_due_date": True,
            "no_active_overlap": True,
            "counts": copy.deepcopy(baseline.get("counts") or {}),
            "warnings": copy.deepcopy(baseline.get("warnings") or []),
        }

    def initial_steps(self, payload: dict, baseline: dict) -> list[dict]:
        keys = []
        if not payload.get("registered"):
            keys.append("create_bridge")
        keys.append("publish_bridge")
        keys.extend(
            f"copy_grade:{index}"
            for index, _entry in enumerate(baseline.get("grade_entries") or [])
        )
        keys.extend(
            f"exclude_source:{index}"
            for index, _source in enumerate(baseline.get("source_assignment_ids") or [])
        )
        keys.extend(("activate_bridge", "post_grades", "register_bridge"))
        return [models.new_step(key) for key in keys]

    def execute(
        self, payload: dict, target: dict, baseline: dict,
        claim: dict, context,
    ) -> dict:
        if baseline.get("blocking_error"):
            return adapter_support.build_result(
                "blocked",
                steps=copy.deepcopy(target.get("steps") or []),
                error_code=str(baseline["blocking_error"]),
                private_diagnostic=baseline.get("private_diagnostic"),
            )

        course_id = target["course_id"]
        steps = copy.deepcopy(target.get("steps") or [])
        grade_entries = baseline.get("grade_entries") or []
        source_ids = baseline.get("source_assignment_ids") or []

        # Keep the active reviewed operation resumable when the safe publish
        # checkpoint was inserted ahead of grade writes. Step keys and effects
        # are unchanged; only their canonical execution/reporting order moves.
        canonical_keys = []
        if not payload.get("registered"):
            canonical_keys.append("create_bridge")
        canonical_keys.append("publish_bridge")
        canonical_keys.extend(
            f"copy_grade:{index}" for index, _entry in enumerate(grade_entries)
        )
        canonical_keys.extend(
            f"exclude_source:{index}" for index, _source in enumerate(source_ids)
        )
        canonical_keys.extend(("activate_bridge", "post_grades", "register_bridge"))
        canonical_order = {key: index for index, key in enumerate(canonical_keys)}
        steps.sort(key=lambda step: canonical_order.get(
            str(step.get("step_key") or ""), len(canonical_order)
        ))

        # A retry may enter with one or more ambiguous steps. Reconcile those
        # exact effects before deciding whether any call is safe to repeat.
        for step in steps:
            if step.get("state") != "sent_unknown":
                continue
            verdict = self._reconcile_step(
                payload, target, baseline, step, steps,
            )
            if verdict != "applied":
                return adapter_support.build_result(
                    "sent_unknown", steps=steps,
                    returned_object_id=_bridge_id(payload, target, steps),
                    error_code=step.get("error_code") or "ambiguous_canvas_outcome",
                )
            step["state"] = "applied"
            step["error_code"] = None
            step = context.checkpoint_step(
                step,
                returned_object_id=step.get("returned_object_id"),
                returned_object_url=step.get("returned_object_url"),
            )
            adapter_support.replace_step(steps, step)

        if not payload.get("registered"):
            step = adapter_support.find_step(steps, "create_bridge")
            if step.get("state") != "applied":
                request = {"assignment": _expected_bridge(payload, phase="created")}
                path = f"/api/v1/courses/{course_id}/assignments"
                context.before_send(
                    "create_bridge",
                    _request_digest("POST", path, request),
                )
                response, error = canvas_client._canvas_send("POST", path, request)
                if error:
                    return self._stop_after_error(
                        context, steps, step, error,
                        uncertain_code="bridge_create_uncertain",
                        rejection_code="bridge_create_rejected",
                    )
                bridge_id = str((response or {}).get("id") or "")
                if not bridge_id:
                    return self._stop_after_error(
                        context, steps, step, "missing create response id",
                        uncertain_code="bridge_create_uncertain",
                        force_uncertain=True,
                    )
                step["returned_object_id"] = bridge_id
                step["returned_object_url"] = (response or {}).get("html_url")
                step["state"] = "claimed"
                step = context.checkpoint_step(
                    step,
                    returned_object_id=bridge_id,
                    returned_object_url=step.get("returned_object_url"),
                )
                adapter_support.replace_step(steps, step)
                verified, assignment = _verify_bridge_phase(
                    course_id, bridge_id, payload, "created"
                )
                if not verified:
                    return self._stop_after_error(
                        context, steps, step, "create postcondition unavailable",
                        uncertain_code="bridge_create_unverified",
                        force_uncertain=True,
                    )
                step["state"] = "applied"
                step["returned_object_url"] = assignment.get("html_url")
                step = context.checkpoint_step(
                    step,
                    returned_object_id=bridge_id,
                    returned_object_url=assignment.get("html_url"),
                )
                adapter_support.replace_step(steps, step)

        bridge_id = _bridge_id(payload, target, steps)
        if not bridge_id:
            return adapter_support.build_result(
                "sent_unknown", steps=steps,
                error_code="bridge_id_unavailable",
            )

        # Canvas rejects grade writes to an unpublished assignment. Publish the
        # bridge first while it is still omitted from final-grade calculation
        # and SIS-disabled, then verify that exact safe state before any grade.
        stopped = self._apply_assignment_phase(
            payload=payload,
            context=context,
            steps=steps,
            course_id=course_id,
            bridge_id=bridge_id,
            step_key="publish_bridge",
            assignment_id=bridge_id,
            object_kind="bridge",
            phase="published",
        )
        if stopped:
            return stopped

        grade_writes = 0
        for index, entry in enumerate(grade_entries):
            step_key = f"copy_grade:{index}"
            step = adapter_support.find_step(steps, step_key)
            if step.get("state") == "applied":
                continue
            request = {"submission": _grade_request(entry)}
            path = (
                f"/api/v1/courses/{course_id}/assignments/{bridge_id}/"
                f"submissions/{entry['user_id']}"
            )
            context.before_send(step_key, _request_digest("PUT", path, request))
            _response, error = canvas_client._canvas_send("PUT", path, request)
            if error:
                return self._stop_after_error(
                    context, steps, step, error,
                    uncertain_code="grade_write_uncertain",
                    rejection_code="grade_write_rejected",
                    returned_object_id=bridge_id,
                )
            submission, read_error = canvas_client.canvas_get(path)
            if read_error or not _grade_matches(submission or {}, entry):
                return self._stop_after_error(
                    context, steps, step, read_error or "grade postcondition mismatch",
                    uncertain_code="grade_write_unverified",
                    force_uncertain=True,
                    returned_object_id=bridge_id,
                )
            step["state"] = "applied"
            step["error_code"] = None
            step = context.checkpoint_step(step)
            adapter_support.replace_step(steps, step)
            grade_writes += 1

        if grade_writes:
            try:
                from api.webui import mirror_service
                mirror_service.notify_course_changed(course_id)
            except Exception as exc:
                operational_log.emit(
                    "mirror.notify_course_changed", "failed",
                    error_class=type(exc),
                )

        phase_steps = (
            *(
                (f"exclude_source:{index}", source_id, "source", "excluded")
                for index, source_id in enumerate(source_ids)
            ),
            ("activate_bridge", bridge_id, "bridge", "activated"),
        )
        for step_key, assignment_id, object_kind, phase in phase_steps:
            stopped = self._apply_assignment_phase(
                payload=payload,
                context=context,
                steps=steps,
                course_id=course_id,
                bridge_id=bridge_id,
                step_key=step_key,
                assignment_id=assignment_id,
                object_kind=object_kind,
                phase=phase,
            )
            if stopped:
                return stopped

        stopped = self._update_bridge_description_if_needed(
            payload=payload,
            context=context,
            steps=steps,
            course_id=course_id,
            bridge_id=bridge_id,
        )
        if stopped:
            return stopped

        step = adapter_support.find_step(steps, "post_grades")
        if step.get("state") != "applied":
            path = f"/api/v1/courses/{course_id}/post_grades"
            request = {"assignments": [int(bridge_id)]}
            context.before_send(
                "post_grades", _request_digest("POST", path, request)
            )
            _response, error = canvas_client._canvas_send("POST", path, request)
            if error:
                return self._stop_after_error(
                    context, steps, step, error,
                    uncertain_code="passback_uncertain",
                    rejection_code="passback_rejected",
                    returned_object_id=bridge_id,
                )
            step["state"] = "applied"
            step["passback_state"] = "accepted"
            step = context.checkpoint_step(step)
            adapter_support.replace_step(steps, step)

        step = adapter_support.find_step(steps, "register_bridge")
        if step.get("state") != "applied":
            final_assignment, read_error = _get_assignment(course_id, bridge_id)
            if read_error or final_assignment is None:
                return self._stop_after_error(
                    context, steps, step, read_error or "bridge read failed",
                    uncertain_code="bridge_registration_blocked",
                    rejection_code="bridge_registration_blocked",
                    returned_object_id=bridge_id,
                )
            final_state = _read_bridge_state(
                course_id, bridge_id, final_assignment
            )
            final_digest = _bridge_digest(final_state)
            registration = {
                "family_title": payload["family_title"],
                "source_assignment_ids": list(source_ids),
                "source_titles": list(baseline.get("source_titles") or []),
                "bridge_assignment_id": bridge_id,
                "bridge_state_digest": final_digest,
            }
            try:
                config.save_sis_grade_bridge(course_id, registration)
                saved = config.get_sis_grade_bridge(
                    course_id, payload["family_title"]
                )
            except Exception as exc:
                step["state"] = "blocked"
                step["error_code"] = "bridge_registration_failed"
                step["private_diagnostic"] = type(exc).__name__
                step = context.checkpoint_step(step)
                adapter_support.replace_step(steps, step)
                return adapter_support.build_result(
                    "blocked", steps=steps,
                    returned_object_id=bridge_id,
                    returned_object_url=final_assignment.get("html_url"),
                    error_code="bridge_registration_failed",
                    private_diagnostic=type(exc).__name__,
                )
            if saved != registration:
                step["state"] = "blocked"
                step["error_code"] = "bridge_registration_unverified"
                step = context.checkpoint_step(step)
                adapter_support.replace_step(steps, step)
                return adapter_support.build_result(
                    "blocked", steps=steps,
                    returned_object_id=bridge_id,
                    returned_object_url=final_assignment.get("html_url"),
                    error_code="bridge_registration_unverified",
                )
            step["state"] = "applied"
            step["bridge_state_digest"] = final_digest
            step = context.checkpoint_step(step)
            adapter_support.replace_step(steps, step)

        final_assignment, _error = _get_assignment(course_id, bridge_id)
        return adapter_support.build_result(
            "applied", steps=steps,
            returned_object_id=bridge_id,
            returned_object_url=(final_assignment or {}).get("html_url"),
        )

    def _update_bridge_description_if_needed(
        self, *, payload: dict, context, steps: list[dict], course_id: str,
        bridge_id: str,
    ) -> dict | None:
        assignment, read_error = _get_assignment(course_id, bridge_id)
        if read_error or assignment is None:
            return self._stop_after_error(
                context, steps, models.new_step("update_bridge_description"),
                read_error or "bridge read failed",
                uncertain_code="bridge_description_unverified",
                force_uncertain=True,
                returned_object_id=bridge_id,
            )
        if assignment.get("description") == _DESCRIPTION:
            return None

        step = adapter_support.find_step(steps, "update_bridge_description")
        if not any(
            item.get("step_key") == "update_bridge_description" for item in steps
        ):
            insert_at = next(
                (index for index, item in enumerate(steps)
                 if item.get("step_key") == "post_grades"),
                len(steps),
            )
            steps.insert(insert_at, step)
        return self._apply_assignment_phase(
            payload=payload,
            context=context,
            steps=steps,
            course_id=course_id,
            bridge_id=bridge_id,
            step_key="update_bridge_description",
            assignment_id=bridge_id,
            object_kind="bridge_description",
            phase="activated",
        )

    def _apply_assignment_phase(
        self, *, payload: dict, context, steps: list[dict], course_id: str,
        bridge_id: str, step_key: str, assignment_id: str,
        object_kind: str, phase: str,
    ) -> dict | None:
        step = adapter_support.find_step(steps, step_key)
        if step.get("state") == "applied":
            return None
        if object_kind == "bridge":
            expected = _expected_bridge(payload, phase=phase)
            verified, assignment = _verify_bridge_phase(
                course_id, assignment_id, payload, phase
            )
        elif object_kind == "bridge_description":
            expected = {"description": _DESCRIPTION}
            assignment, read_error = _get_assignment(course_id, assignment_id)
            verified = not read_error and _fields_match(assignment or {}, expected)
        else:
            expected = {"omit_from_final_grade": True, "post_to_sis": False}
            assignment, read_error = _get_assignment(course_id, assignment_id)
            verified = not read_error and _fields_match(assignment or {}, expected)
        if not verified:
            request = {"assignment": expected}
            path = f"/api/v1/courses/{course_id}/assignments/{assignment_id}"
            context.before_send(step_key, _request_digest("PUT", path, request))
            _response, error = canvas_client._canvas_send("PUT", path, request)
            if error:
                return self._stop_after_error(
                    context, steps, step, error,
                    uncertain_code=f"{phase}_uncertain",
                    rejection_code=f"{phase}_rejected",
                    returned_object_id=bridge_id,
                )
            if object_kind in {"bridge", "bridge_description"}:
                verified, assignment = _verify_bridge_phase(
                    course_id, assignment_id, payload, phase
                )
            else:
                assignment, read_error = _get_assignment(course_id, assignment_id)
                verified = not read_error and _fields_match(assignment or {}, expected)
        if not verified:
            return self._stop_after_error(
                context, steps, step, "assignment postcondition unavailable",
                uncertain_code=f"{phase}_unverified",
                force_uncertain=True,
                returned_object_id=bridge_id,
            )
        step["state"] = "applied"
        step["error_code"] = None
        if object_kind in {"bridge", "bridge_description"} and assignment:
            step["returned_object_url"] = assignment.get("html_url")
        step = context.checkpoint_step(
            step,
            returned_object_id=(
                bridge_id
                if object_kind in {"bridge", "bridge_description"}
                else None
            ),
            returned_object_url=step.get("returned_object_url"),
        )
        adapter_support.replace_step(steps, step)
        return None

    def _stop_after_error(
        self, context, steps: list[dict], step: dict, error: str,
        *, uncertain_code: str, rejection_code: str | None = None,
        force_uncertain: bool = False, returned_object_id: str | None = None,
    ) -> dict:
        uncertain = force_uncertain or adapter_support.is_uncertain(error)
        step["state"] = "sent_unknown" if uncertain else "blocked"
        step["error_code"] = uncertain_code if uncertain else rejection_code
        step["private_diagnostic"] = str(error)
        step = context.checkpoint_step(
            step,
            returned_object_id=step.get("returned_object_id"),
            returned_object_url=step.get("returned_object_url"),
        )
        adapter_support.replace_step(steps, step)
        return adapter_support.build_result(
            step["state"], steps=steps,
            returned_object_id=returned_object_id or step.get("returned_object_id"),
            returned_object_url=step.get("returned_object_url"),
            error_code=step.get("error_code"),
            private_diagnostic=str(error),
        )

    def _reconcile_step(
        self, payload: dict, target: dict, baseline: dict,
        step: dict, steps: list[dict],
    ) -> str:
        course_id = target["course_id"]
        key = str(step.get("step_key") or "")
        bridge_id = _bridge_id(payload, target, steps)
        if key == "create_bridge":
            if not step.get("returned_object_id"):
                return "sent_unknown"
            verified, _assignment = _verify_bridge_phase(
                course_id, str(step["returned_object_id"]), payload, "created"
            )
            return "applied" if verified else "sent_unknown"
        if key.startswith("copy_grade:"):
            if not bridge_id:
                return "sent_unknown"
            try:
                index = int(key.split(":", 1)[1])
                entry = baseline["grade_entries"][index]
            except (ValueError, IndexError, KeyError):
                return "sent_unknown"
            path = (
                f"/api/v1/courses/{course_id}/assignments/{bridge_id}/"
                f"submissions/{entry['user_id']}"
            )
            submission, error = canvas_client.canvas_get(path)
            return "applied" if not error and _grade_matches(submission or {}, entry) else "sent_unknown"
        if key == "publish_bridge" and bridge_id:
            verified, _assignment = _verify_bridge_phase(
                course_id, bridge_id, payload, "published"
            )
            return "applied" if verified else "sent_unknown"
        if key.startswith("exclude_source:"):
            try:
                index = int(key.split(":", 1)[1])
                source_id = baseline["source_assignment_ids"][index]
            except (ValueError, IndexError, KeyError):
                return "sent_unknown"
            assignment, error = _get_assignment(course_id, source_id)
            return (
                "applied"
                if not error and _fields_match(
                    assignment or {},
                    {"omit_from_final_grade": True, "post_to_sis": False},
                )
                else "sent_unknown"
            )
        if key == "activate_bridge" and bridge_id:
            verified, _assignment = _verify_bridge_phase(
                course_id, bridge_id, payload, "activated"
            )
            return "applied" if verified else "sent_unknown"
        if key == "update_bridge_description" and bridge_id:
            verified, _assignment = _verify_bridge_phase(
                course_id, bridge_id, payload, "activated"
            )
            return "applied" if verified else "sent_unknown"
        if key == "post_grades":
            # Canvas exposes no SIS readback proof. An ambiguous accepted/not-
            # accepted request can never be resent by inference.
            return "sent_unknown"
        if key == "register_bridge" and bridge_id:
            saved = config.get_sis_grade_bridge(
                course_id, payload["family_title"]
            )
            return (
                "applied"
                if saved and str(saved.get("bridge_assignment_id")) == bridge_id
                else "sent_unknown"
            )
        return "sent_unknown"

    def reconcile(self, payload: dict, target: dict, baseline: dict) -> dict:
        steps = copy.deepcopy(target.get("steps") or [])
        if not adapter_support.has_outbound_marker(steps):
            return {"state": "pending"}
        for step in steps:
            if step.get("state") == "applied":
                continue
            if step.get("state") != "sent_unknown":
                return {"state": "sent_unknown", "steps": steps}
            if self._reconcile_step(payload, target, baseline, step, steps) != "applied":
                return {"state": "sent_unknown", "steps": steps}
            step["state"] = "applied"
            step["error_code"] = None
        return {
            "state": "applied",
            "steps": steps,
            "returned_object_id": _bridge_id(payload, target, steps),
        }

    def retry_selector(self, operation: dict) -> list[dict]:
        return [
            target for target in operation.get("targets", [])
            if models.is_unresolved_target_state(target.get("state", "pending"))
        ]


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _get_all(path: str, params: dict | None = None) -> list[dict]:
    rows, error, complete = canvas_client.canvas_get_all_complete(path, params or {})
    if error or not complete or not isinstance(rows, list):
        raise _BridgeReadError(str(error or "incomplete Canvas collection"))
    return rows


def _get_assignment(course_id: str, assignment_id: str) -> tuple[dict | None, str | None]:
    assignment, error = canvas_client.canvas_get(
        f"/api/v1/courses/{course_id}/assignments/{assignment_id}"
    )
    if error or not isinstance(assignment, dict):
        return None, str(error or "invalid assignment response")
    return assignment, None


def _resolve_family_assignments(
    payload: dict, assignments: list[dict], *, known_bridge_id: str | None = None
):
    course_id = payload["course_id"]
    family_title = payload["family_title"]
    prefix = f"{family_title} - "
    exact_sources = [
        row for row in assignments
        if str(row.get("name") or "").startswith(prefix)
        and str(row.get("name") or "")[len(prefix):].strip()
    ]
    exact_sources.sort(
        key=lambda row: (
            str(row.get("name") or "").strip().casefold(),
            str(row.get("id") or ""),
        )
    )
    bridge_matches = [row for row in assignments
                      if str(row.get("name") or "") == family_title]
    if len(bridge_matches) > 1:
        raise _BridgeInvariantError("duplicate_bridge_title")

    for row in exact_sources + bridge_matches:
        if str(row.get("course_id") or "") != course_id:
            raise _BridgeInvariantError("assignment_outside_selected_course")

    if payload.get("registered"):
        by_id = {str(row.get("id")): row for row in assignments}
        frozen_sources = []
        for source_id in payload.get("source_assignment_ids") or []:
            row = by_id.get(str(source_id))
            if row is None:
                raise _BridgeInvariantError("registered_source_missing")
            frozen_sources.append(row)
        bridge = by_id.get(str(payload.get("bridge_assignment_id") or ""))
        return frozen_sources, bridge

    normalized_titles = [
        str(row.get("name") or "").strip().casefold()
        for row in exact_sources
    ]
    if len(set(normalized_titles)) != len(normalized_titles):
        raise _BridgeInvariantError("duplicate_normalized_source_title")

    frozen_ids = [str(value) for value in payload.get("source_assignment_ids") or []]
    if frozen_ids:
        discovered_ids = [str(row.get("id")) for row in exact_sources]
        if discovered_ids != frozen_ids:
            raise _BridgeInvariantError("source_discovery_drift")
    if len(exact_sources) < 2:
        raise _BridgeInvariantError("fewer_than_two_sources")
    bridge = bridge_matches[0] if bridge_matches else None
    if bridge is not None and known_bridge_id:
        if str(bridge.get("id")) != str(known_bridge_id):
            raise _BridgeInvariantError("bridge_title_collision")
    return exact_sources, bridge


def _validate_source_identity(payload: dict, source_rows: list[dict]) -> None:
    frozen_ids = [str(value) for value in payload.get("source_assignment_ids") or []]
    frozen_titles = [str(value) for value in payload.get("source_titles") or []]
    if frozen_ids and [str(row.get("id")) for row in source_rows] != frozen_ids:
        raise _BridgeInvariantError("source_id_drift")
    if frozen_titles and [str(row.get("name") or "") for row in source_rows] != frozen_titles:
        raise _BridgeInvariantError("source_title_drift")


def _validate_source_shape(source: dict) -> None:
    if source.get("published") is not True:
        raise _BridgeInvariantError("source_not_published")
    if source.get("grading_type") != "points":
        raise _BridgeInvariantError("source_not_point_graded")
    if source.get("only_visible_to_overrides") is not True:
        raise _BridgeInvariantError("source_not_override_only")
    if not _is_number(source.get("points_possible")):
        raise _BridgeInvariantError("source_points_invalid")


def _explicit_override_members(source: dict, overrides: list[dict]):
    if not overrides:
        raise _BridgeInvariantError("source_missing_student_overrides")
    members: set[str] = set()
    due_dates: list[str | None] = []
    for override in overrides:
        student_ids = override.get("student_ids")
        if not isinstance(student_ids, list) or not student_ids:
            raise _BridgeInvariantError("source_has_nonstudent_override")
        if override.get("group_id") is not None or override.get("course_section_id") is not None:
            raise _BridgeInvariantError("source_has_nonstudent_override")
        effective_due = override.get("due_at") or source.get("due_at")
        due_dates.append(str(effective_due) if effective_due is not None else None)
        for student_id in student_ids:
            text = str(student_id or "").strip()
            if not text:
                raise _BridgeInvariantError("source_override_student_id_invalid")
            if text in members:
                raise _BridgeInvariantError("duplicate_source_membership")
            members.add(text)
    return members, due_dates


def _validate_common_source_shape(
    source_rows: list[dict], effective_due_dates: list[str | None]
) -> None:
    points = [_normalized_number(row.get("points_possible")) for row in source_rows]
    if any(not _numbers_equal(points[0], value) for value in points[1:]):
        raise _BridgeInvariantError("mixed_points_possible")
    groups = [str(row.get("assignment_group_id")) for row in source_rows]
    if len(set(groups)) != 1:
        raise _BridgeInvariantError("mixed_assignment_groups")
    if (not effective_due_dates or effective_due_dates[0] is None
            or len(set(effective_due_dates)) != 1):
        raise _BridgeInvariantError("mixed_effective_due_dates")


def _source_state(source: dict, overrides: list[dict]) -> dict:
    return {
        "id": str(source.get("id")),
        "course_id": str(source.get("course_id")),
        "name": str(source.get("name") or ""),
        "published": source.get("published") is True,
        "grading_type": source.get("grading_type"),
        "points_possible": _normalized_number(source.get("points_possible")),
        "assignment_group_id": str(source.get("assignment_group_id")),
        "due_at": source.get("due_at"),
        "only_visible_to_overrides": source.get("only_visible_to_overrides") is True,
        "omit_from_final_grade": source.get("omit_from_final_grade") is True,
        "post_to_sis": source.get("post_to_sis") is True,
        "overrides": [
            {
                "id": str(row.get("id") or ""),
                "student_ids": sorted(str(value) for value in (row.get("student_ids") or [])),
                "due_at": row.get("due_at"),
            }
            for row in sorted(overrides, key=lambda item: str(item.get("id") or ""))
        ],
    }


def _read_bridge_state(course_id: str, bridge_id: str, assignment: dict | None = None) -> dict:
    if assignment is None:
        assignment, error = _get_assignment(course_id, bridge_id)
        if error:
            raise _BridgeReadError(error)
    overrides = _get_all(
        f"/api/v1/courses/{course_id}/assignments/{bridge_id}/overrides",
        {"per_page": 100},
    )
    return {
        "id": str((assignment or {}).get("id")),
        "course_id": str((assignment or {}).get("course_id")),
        "name": str((assignment or {}).get("name") or ""),
        "description": str((assignment or {}).get("description") or ""),
        "points_possible": _normalized_number((assignment or {}).get("points_possible")),
        "assignment_group_id": str((assignment or {}).get("assignment_group_id")),
        "due_at": (assignment or {}).get("due_at"),
        "grading_type": (assignment or {}).get("grading_type"),
        "submission_types": sorted((assignment or {}).get("submission_types") or []),
        "published": (assignment or {}).get("published") is True,
        "only_visible_to_overrides": (assignment or {}).get("only_visible_to_overrides") is True,
        "omit_from_final_grade": (assignment or {}).get("omit_from_final_grade") is True,
        "post_to_sis": (assignment or {}).get("post_to_sis") is True,
        "overrides": copy.deepcopy(overrides),
    }


def _bridge_digest(state: dict) -> str:
    return models.sha256_dict(state)


def _expected_bridge(payload: dict, *, phase: str) -> dict:
    expected = {
        "name": payload["family_title"],
        "description": _DESCRIPTION,
        "points_possible": payload["points_possible"],
        "assignment_group_id": payload["assignment_group_id"],
        "due_at": payload["due_at"],
        "grading_type": "points",
        "submission_types": ["none"],
        "only_visible_to_overrides": False,
        "published": phase != "created",
        "omit_from_final_grade": phase != "activated",
        "post_to_sis": phase == "activated",
    }
    return expected


def _verify_bridge_phase(
    course_id: str, bridge_id: str, payload: dict, phase: str
) -> tuple[bool, dict | None]:
    assignment, error = _get_assignment(course_id, bridge_id)
    if error or assignment is None:
        return False, None
    if str(assignment.get("course_id") or "") != str(course_id):
        return False, assignment
    if not _fields_match(assignment, _expected_bridge(payload, phase=phase)):
        return False, assignment
    try:
        overrides = _get_all(
            f"/api/v1/courses/{course_id}/assignments/{bridge_id}/overrides",
            {"per_page": 100},
        )
    except _BridgeReadError:
        return False, assignment
    return not overrides, assignment


def _operation_bridge_state_is_valid(
    payload: dict, target: dict, bridge_state: dict
) -> bool:
    if bridge_state.get("overrides"):
        return False
    assignment = dict(bridge_state)
    steps = {step.get("step_key"): step for step in target.get("steps", [])}
    possible_phases = {"created"}
    publish_state = (steps.get("publish_bridge") or {}).get("state")
    activate_state = (steps.get("activate_bridge") or {}).get("state")
    if publish_state in {"applied", "sent_unknown"}:
        possible_phases.add("published")
    if activate_state in {"applied", "sent_unknown"}:
        possible_phases.add("activated")
    if any(
        _fields_match(assignment, _expected_bridge(payload, phase=phase))
        for phase in possible_phases
    ):
        return True

    # The first in-flight bridge used the original neutral description. Allow
    # only that exact app-authored value, and only after a definite passback
    # rejection, so the same reviewed operation can checkpoint the requested
    # student-facing correction before its controlled retry.
    passback = steps.get("post_grades") or {}
    if (
        assignment.get("description") in {
            _PREVIOUS_DESCRIPTION,
            f"<p>{_PREVIOUS_DESCRIPTION}</p>",
        }
        and activate_state == "applied"
        and passback.get("state") == "blocked"
        and passback.get("error_code") == "passback_rejected"
    ):
        assignment["description"] = _DESCRIPTION
        return _fields_match(
            assignment, _expected_bridge(payload, phase="activated")
        )
    return False


def _fields_match(actual: dict, expected: dict) -> bool:
    for key, value in expected.items():
        current = actual.get(key)
        if key == "points_possible":
            if not _numbers_equal(current, value):
                return False
        elif key == "assignment_group_id":
            if str(current) != str(value):
                return False
        elif key == "submission_types":
            if sorted(current or []) != sorted(value or []):
                return False
        elif current != value:
            return False
    return True


def _grade_request(entry: dict) -> dict:
    request = {"excuse": True} if entry.get("excused") else {
        "posted_grade": str(entry.get("score"))
    }
    if entry.get("late_policy_status"):
        request["late_policy_status"] = entry["late_policy_status"]
    return request


def _grade_matches(submission: dict, entry: dict) -> bool:
    if entry.get("excused"):
        if submission.get("excused") is not True:
            return False
    elif not _numbers_equal(submission.get("score"), entry.get("score")):
        return False
    expected_status = entry.get("late_policy_status")
    if expected_status and submission.get("late_policy_status") != expected_status:
        return False
    return True


def _late_status(submission: dict) -> str | None:
    value = str(submission.get("late_policy_status") or "").strip()
    return value or None


def _bridge_id(payload: dict, target: dict, steps: list[dict]) -> str | None:
    if payload.get("bridge_assignment_id"):
        return str(payload["bridge_assignment_id"])
    create_step = next(
        (step for step in steps if step.get("step_key") == "create_bridge"),
        None,
    )
    value = (create_step or {}).get("returned_object_id") or target.get("returned_object_id")
    return str(value) if value is not None else None


def _request_digest(method: str, path: str, payload: dict) -> str:
    return models.sha256_dict({"method": method, "path": path, "payload": payload})


def _is_number(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _normalized_number(value: Any) -> int | float:
    number = float(value)
    return int(number) if number.is_integer() else number


def _numbers_equal(left: Any, right: Any) -> bool:
    if not _is_number(left) or not _is_number(right):
        return False
    return math.isclose(
        float(left), float(right), rel_tol=0.0, abs_tol=_SCORE_TOLERANCE
    )


__all__ = ["KIND", "SisGradeBridgeAdapter"]

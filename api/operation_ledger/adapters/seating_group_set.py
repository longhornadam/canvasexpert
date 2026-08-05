"""Create-only Canvas group-set export for a finalized local Seating mode."""

from __future__ import annotations

from api import seating_grouping, seating_state
from api.platform_services import canvas_client, config
from api.webui.routes import roster_canvas

from .. import models
from .adapter_support import (
    build_result as _build_result,
    is_uncertain as _is_uncertain,
    replace_step as _replace_step,
)


KIND = "seating.group_set_create"
_NAME_MAX_LENGTH = 100


def _normalize_name(value: object) -> str:
    return str(value or "").strip().casefold()


def _response_id(value: object) -> str | None:
    if not isinstance(value, dict) or value.get("id") is None:
        return None
    result = str(value["id"])
    return result or None


def _ordered_steps(target: dict, payload: dict) -> list[dict]:
    keys = ["create_category"]
    for group_index, group in enumerate(payload["groups"]):
        keys.append(f"create_group_{group_index}")
        for member_index, _student_id in enumerate(group["student_ids"]):
            keys.append(f"add_member_{group_index}_{member_index}")
    existing = {step.get("step_key"): step for step in target.get("steps", [])}
    return [existing[key] for key in keys if key in existing]


def _step(steps: list[dict], key: str) -> dict:
    found = next((step for step in steps if step.get("step_key") == key), None)
    if found is not None:
        return found
    step = models.new_step(key)
    steps.append(step)
    return step


class SeatingGroupSetAdapter:
    """Ledger adapter that only creates a new category and its new descendants."""

    kind = KIND

    def build_payload(self, prepare_request: dict) -> dict:
        if set(prepare_request) != {"course_id", "mode_id", "group_set_name"}:
            raise ValueError("Seating export requires exactly course_id, mode_id, and group_set_name.")
        course_id = str(prepare_request.get("course_id") or "").strip()
        mode_id = str(prepare_request.get("mode_id") or "").strip()
        group_set_name = str(prepare_request.get("group_set_name") or "").strip()
        if not course_id or not mode_id:
            raise ValueError("course_id and mode_id are required.")
        if (not group_set_name or len(group_set_name) > _NAME_MAX_LENGTH
                or any(ord(character) < 32 for character in group_set_name)):
            raise ValueError("new Canvas group-set name must be 1 to 100 characters.")
        state = seating_state.normalize_state(config.get_seating_course_state(course_id))
        mode = next((item for item in state["modes"] if item["id"] == mode_id), None)
        if mode is None:
            raise ValueError("Seating mode not found.")
        layout = next((item for item in state["layouts"] if item["id"] == mode["layout_id"]), None)
        if layout is None:
            raise ValueError("Seating mode layout not found.")
        plan, plan_error = seating_grouping.finalized_group_plan(
            layout, mode["strategy"], mode["assignment"]
        )
        if plan_error:
            raise ValueError(plan_error)
        groups = [{"student_ids": list(group["student_ids"])} for group in plan["groups"]]
        assigned = [student_id for group in groups for student_id in group["student_ids"]]
        if len(assigned) != len(set(assigned)):
            raise ValueError("saved Seating group plan has a duplicate member.")
        return {
            "course_id": course_id,
            "mode_id": mode_id,
            "group_set_name": group_set_name,
            "group_size": plan["group_size"],
            "groups": groups,
            "member_count": plan["member_count"],
            "partial_group_count": plan["partial_group_count"],
        }

    def source_digest(self, payload: dict) -> str:
        return models.sha256_dict({
            "course_id": payload["course_id"],
            "mode_id": payload["mode_id"],
            "group_set_name": payload["group_set_name"],
            "groups": payload["groups"],
        })

    def verify_targets(self, payload: dict, targets: list[dict]) -> list[dict]:
        active_ids = {str(course["id"]) for course in config.active_courses()}
        course_id = payload["course_id"]
        if course_id not in active_ids:
            raise ValueError("course is not in active courses.")
        verified = []
        for target in targets:
            target_course_id = str(target.get("course_id") or "")
            if target_course_id != course_id:
                raise ValueError("Seating export target does not match its saved course.")
            baseline = self.capture_baseline(payload, {"course_id": course_id})
            if baseline.get("canvas_error"):
                raise ValueError(
                    "Canvas group-set names could not be checked. Resolve access before preparing this write."
                )
            if baseline.get("name_collision"):
                raise ValueError("A Canvas group set with that name already exists. Choose a new name.")
            verified.append({
                "course_id": course_id,
                "target_key": self.target_key(payload, course_id),
                "idempotency_key": self.idempotency_key(payload, course_id),
            })
        return verified

    def target_key(self, payload: dict, course_id: str) -> str:
        return models.sha256_hex(f"{KIND}|{self.source_digest(payload)}|{course_id}")

    def idempotency_key(self, payload: dict, course_id: str) -> str:
        return models.sha256_hex(
            f"{course_id}|{payload['mode_id']}|{_normalize_name(payload['group_set_name'])}|{self.source_digest(payload)}"
        )

    def capture_baseline(self, payload: dict, target: dict) -> dict:
        categories, error = roster_canvas.list_canvas_group_categories(
            target["course_id"], canvas_get_all=canvas_client.canvas_get_all,
        )
        if error:
            return {"canvas_error": str(error)}
        projection = sorted(
            (item["id"], _normalize_name(item["name"]))
            for item in categories or []
        )
        return {
            "category_names_digest": models.sha256_dict(projection),
            "name_collision": any(
                _normalize_name(item["name"]) == _normalize_name(payload["group_set_name"])
                for item in categories or []
            ),
        }

    def check_drift(self, payload: dict, target: dict, baseline: dict) -> bool:
        if not isinstance(baseline, dict) or baseline.get("canvas_error"):
            return True
        current = self.capture_baseline(payload, target)
        if current.get("canvas_error"):
            return True
        return bool(current.get("name_collision") or current != baseline)

    def freeze_review(self, payload: dict, target: dict, baseline: dict) -> dict:
        course_id = target["course_id"]
        course_name = course_id
        for course in config.active_courses():
            if str(course["id"]) == course_id:
                course_name = course.get("name") or course.get("nickname") or course_id
                break
        return {
            "course_name": course_name,
            "new_group_set_name": payload["group_set_name"],
            "group_count": len(payload["groups"]),
            "member_count": payload["member_count"],
            "partial_group_count": payload["partial_group_count"],
            "baseline_name_collision": bool(baseline.get("name_collision")),
            "new_set_only": True,
        }

    def execute(self, payload: dict, target: dict, baseline: dict, claim: dict, context) -> dict:
        course_id = target["course_id"]
        steps = _ordered_steps(target, payload)
        category_step = _step(steps, "create_category")
        category_id = category_step.get("returned_object_id") or target.get("returned_object_id")
        if category_id is not None:
            category_id = str(category_id)
        try:
            if category_id:
                if not self._category_matches(course_id, category_id, payload["group_set_name"]):
                    return _build_result("sent_unknown", steps=steps,
                                         returned_object_id=category_id,
                                         error_code="new_category_exact_id_unverified")
                category_step["state"] = "skipped"
            elif category_step.get("outbound_started_at"):
                # A timeout before the returned category ID can never be retried by name:
                # matching it could target a category another actor created.
                return _build_result("sent_unknown", steps=steps,
                                     error_code="new_category_creation_unresolved")
            else:
                # Check the same strict no-collision baseline immediately before first send.
                if self.check_drift(payload, target, target.get("baseline", baseline)):
                    return _build_result("blocked", steps=steps, error_code="category_name_drift")
                path = f"/api/v1/courses/{course_id}/group_categories"
                request = {"name": payload["group_set_name"]}
                digest = models.sha256_dict({"method": "POST", "path": path, "payload": request})
                category_step = context.before_send("create_category", digest)
                _replace_step(steps, category_step)
                response, error = roster_canvas.create_canvas_group_category(
                    course_id, payload["group_set_name"], canvas_send=canvas_client._canvas_send,
                )
                if error:
                    state = "sent_unknown" if _is_uncertain(error) else "failed"
                    category_step["state"] = state
                    category_step["error_code"] = "timeout_or_disconnect" if state == "sent_unknown" else "category_rejected"
                    category_step["private_diagnostic"] = str(error)
                    category_step = context.checkpoint_step(category_step)
                    _replace_step(steps, category_step)
                    return _build_result(state, steps=steps, error_code=category_step["error_code"],
                                         private_diagnostic=str(error))
                category_id = _response_id(response)
                if not category_id:
                    category_step["state"] = "sent_unknown"
                    category_step["error_code"] = "unparseable_response"
                    category_step["private_diagnostic"] = "missing group category id"
                    category_step = context.checkpoint_step(category_step)
                    _replace_step(steps, category_step)
                    return _build_result("sent_unknown", steps=steps, error_code="unparseable_response")
                category_step["state"] = "applied"
                category_step = context.checkpoint_step(category_step, returned_object_id=category_id)
                _replace_step(steps, category_step)

            for group_index, group in enumerate(payload["groups"]):
                result = self._create_group_and_members(
                    course_id, category_id, payload, group_index, group, steps, context,
                )
                if result is not None:
                    result["returned_object_id"] = category_id
                    return result
            return _build_result("applied", steps=steps, returned_object_id=category_id)
        finally:
            if category_id:
                self._reconcile_new_category(course_id, category_id, payload["group_set_name"])

    def _create_group_and_members(self, course_id: str, category_id: str, payload: dict,
                                  group_index: int, group: dict, steps: list[dict], context) -> dict | None:
        step_key = f"create_group_{group_index}"
        group_step = _step(steps, step_key)
        group_id = group_step.get("returned_object_id")
        group_name = f"Group {group_index + 1}"
        if group_id:
            group_id = str(group_id)
            if not self._group_matches(category_id, group_id, group_name):
                return _build_result("sent_unknown", steps=steps,
                                     error_code="new_group_exact_id_unverified")
            group_step["state"] = "skipped"
        elif group_step.get("state") == "sent_unknown" or group_step.get("outbound_started_at"):
            return _build_result("sent_unknown", steps=steps,
                                 error_code="new_group_creation_unresolved")
        else:
            path = f"/api/v1/group_categories/{category_id}/groups"
            request = {"name": group_name}
            digest = models.sha256_dict({"method": "POST", "path": path, "payload": request})
            group_step = context.before_send(step_key, digest)
            _replace_step(steps, group_step)
            response, error = roster_canvas.create_canvas_group(
                category_id, group_name, canvas_send=canvas_client._canvas_send,
            )
            if error:
                state = "sent_unknown" if _is_uncertain(error) else "partial"
                group_step["state"] = state
                group_step["error_code"] = "timeout_or_disconnect" if state == "sent_unknown" else "group_rejected"
                group_step["private_diagnostic"] = str(error)
                group_step = context.checkpoint_step(group_step)
                _replace_step(steps, group_step)
                return _build_result(state, steps=steps, error_code=group_step["error_code"],
                                     private_diagnostic=str(error))
            group_id = _response_id(response)
            if not group_id:
                group_step["state"] = "sent_unknown"
                group_step["error_code"] = "unparseable_response"
                group_step["private_diagnostic"] = "missing group id"
                group_step = context.checkpoint_step(group_step)
                _replace_step(steps, group_step)
                return _build_result("sent_unknown", steps=steps, error_code="unparseable_response")
            group_step["state"] = "applied"
            group_step = context.checkpoint_step(group_step, returned_object_id=group_id)
            _replace_step(steps, group_step)

        for member_index, student_id in enumerate(group["student_ids"]):
            member_key = f"add_member_{group_index}_{member_index}"
            member_step = _step(steps, member_key)
            membership_id = member_step.get("returned_object_id")
            if membership_id:
                if not self._membership_matches(group_id, str(membership_id), student_id):
                    return _build_result("sent_unknown", steps=steps,
                                         error_code="new_membership_exact_id_unverified")
                member_step["state"] = "skipped"
                continue
            if member_step.get("state") == "sent_unknown" or member_step.get("outbound_started_at"):
                return _build_result("sent_unknown", steps=steps,
                                     error_code="new_membership_creation_unresolved")
            path = f"/api/v1/groups/{group_id}/memberships"
            request = {"user_id": student_id}
            digest = models.sha256_dict({"method": "POST", "path": path, "payload": request})
            member_step = context.before_send(member_key, digest)
            _replace_step(steps, member_step)
            response, error = roster_canvas.create_canvas_group_membership(
                group_id, student_id, canvas_send=canvas_client._canvas_send,
            )
            if error:
                state = "sent_unknown" if _is_uncertain(error) else "partial"
                member_step["state"] = state
                member_step["error_code"] = "timeout_or_disconnect" if state == "sent_unknown" else "membership_rejected"
                member_step["private_diagnostic"] = str(error)
                member_step = context.checkpoint_step(member_step)
                _replace_step(steps, member_step)
                return _build_result(state, steps=steps, error_code=member_step["error_code"],
                                     private_diagnostic=str(error))
            membership_id = _response_id(response)
            if not membership_id:
                member_step["state"] = "sent_unknown"
                member_step["error_code"] = "unparseable_response"
                member_step["private_diagnostic"] = "missing membership id"
                member_step = context.checkpoint_step(member_step)
                _replace_step(steps, member_step)
                return _build_result("sent_unknown", steps=steps, error_code="unparseable_response")
            member_step["state"] = "applied"
            member_step = context.checkpoint_step(member_step, returned_object_id=membership_id)
            _replace_step(steps, member_step)
        return None

    def reconcile(self, payload: dict, target: dict, baseline: dict) -> dict:
        steps = _ordered_steps(target, payload)
        category_step = _step(steps, "create_category")
        category_id = category_step.get("returned_object_id") or target.get("returned_object_id")
        if not category_id:
            return {"state": "sent_unknown" if category_step.get("outbound_started_at") else "pending"}
        category_id = str(category_id)
        if not self._category_matches(target["course_id"], category_id, payload["group_set_name"]):
            return {"state": "sent_unknown", "returned_object_id": category_id}
        for group_index, group in enumerate(payload["groups"]):
            group_step = _step(steps, f"create_group_{group_index}")
            group_id = group_step.get("returned_object_id")
            if not group_id or not self._group_matches(category_id, str(group_id), f"Group {group_index + 1}"):
                return {"state": "sent_unknown", "returned_object_id": category_id}
            for member_index, student_id in enumerate(group["student_ids"]):
                member_step = _step(steps, f"add_member_{group_index}_{member_index}")
                membership_id = member_step.get("returned_object_id")
                if not membership_id or not self._membership_matches(str(group_id), str(membership_id), student_id):
                    return {"state": "sent_unknown", "returned_object_id": category_id}
        self._reconcile_new_category(target["course_id"], category_id, payload["group_set_name"])
        return {"state": "applied", "returned_object_id": category_id, "steps": steps}

    def retry_selector(self, operation: dict) -> list[dict]:
        return [target for target in operation.get("targets", [])
                if models.is_unresolved_target_state(target.get("state", "pending"))]

    @staticmethod
    def _category_matches(course_id: str, category_id: str, name: str) -> bool:
        categories, error = roster_canvas.list_canvas_group_categories(
            course_id, canvas_get_all=canvas_client.canvas_get_all,
        )
        return not error and any(
            item["id"] == str(category_id) and _normalize_name(item["name"]) == _normalize_name(name)
            for item in categories or []
        )

    @staticmethod
    def _group_matches(category_id: str, group_id: str, name: str) -> bool:
        groups, error = canvas_client.canvas_get_all(
            f"/api/v1/group_categories/{category_id}/groups", {"per_page": 100},
        )
        return not error and any(
            str(item.get("id")) == str(group_id) and _normalize_name(item.get("name")) == _normalize_name(name)
            for item in groups or [] if isinstance(item, dict)
        )

    @staticmethod
    def _membership_matches(group_id: str, membership_id: str, student_id: str) -> bool:
        memberships, error = canvas_client.canvas_get_all(
            f"/api/v1/groups/{group_id}/memberships", {"per_page": 200},
        )
        return not error and any(
            str(item.get("id")) == str(membership_id) and str(item.get("user_id")) == str(student_id)
            for item in memberships or [] if isinstance(item, dict)
        )

    @staticmethod
    def _reconcile_new_category(course_id: str, category_id: str, category_name: str) -> None:
        try:
            from api.webui.routes import roster as roster_routes
            roster_routes._reconcile_group_category(course_id, category_id, category_name)
        except Exception:
            # The Canvas write outcome is authoritative; the existing Roster seam falls
            # back to staleness when reconciliation cannot refresh its private mirror.
            return

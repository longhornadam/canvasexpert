"""Due-date extension operation adapter for the crash-safe ``gradebook.extension`` kind.

Per-student due-date extensions via Canvas assignment overrides.  Inspects
existing overrides to avoid conflicts: creates new student-specific overrides,
updates exclusive ones, and blocks shared/ambiguous overrides.
"""
from .. import models
from api.webui import canvas_client, config
from api.webui.schooldays import _parse_iso_local, _add_school_days


KIND = "gradebook.extension"


class ExtensionAdapter:
    kind = KIND

    # ── Payload ──────────────────────────────────────────────────────────

    def build_payload(self, prepare_request: dict) -> dict:
        assignment_id = str(prepare_request.get("assignment_id") or "").strip()
        if not assignment_id:
            raise ValueError("assignment_id is required")
        student_ids = prepare_request.get("student_ids", [])
        if isinstance(student_ids, str):
            import json
            try:
                student_ids = json.loads(student_ids)
            except (json.JSONDecodeError, TypeError):
                student_ids = [student_ids]
        if not isinstance(student_ids, list) or not student_ids:
            raise ValueError("at least one student_id is required")
        days = int(prepare_request.get("days", 1))
        if days < 1:
            raise ValueError("days must be >= 1")
        payload = {
            "assignment_id": assignment_id,
            "student_ids": [str(s).strip() for s in student_ids],
            "days": days,
            "skip_weekends": bool(prepare_request.get("skip_weekends", True)),
        }
        holidays = prepare_request.get("holidays", [])
        if isinstance(holidays, list):
            payload["holidays"] = [str(h).strip() for h in holidays if str(h).strip()]
        elif isinstance(holidays, str):
            import json
            try:
                payload["holidays"] = json.loads(holidays)
            except (json.JSONDecodeError, TypeError):
                payload["holidays"] = []
        return payload

    def source_digest(self, payload: dict) -> str:
        return models.sha256_dict({
            "assignment_id": payload.get("assignment_id"),
            "student_ids": sorted(payload.get("student_ids", [])),
            "days": payload.get("days"),
            "skip_weekends": payload.get("skip_weekends"),
            "holidays": sorted(payload.get("holidays", [])),
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
                raise ValueError(f"course {course_id} is not in active courses")
            verified.append({
                "course_id": course_id,
                "target_key": self.target_key(payload, course_id),
                "idempotency_key": self.idempotency_key(payload, course_id),
            })
        return verified

    def target_key(self, payload: dict, course_id: str) -> str:
        return models.sha256_hex(f"{KIND}|{self.source_digest(payload)}|{course_id}")

    def idempotency_key(self, payload: dict, course_id: str) -> str:
        return models.sha256_hex(f"{self.source_digest(payload)}|{course_id}")

    # ── Baseline / drift ─────────────────────────────────────────────────

    def capture_baseline(self, payload: dict, target: dict) -> dict:
        course_id = target["course_id"]
        assignment_id = payload.get("assignment_id", "")
        baseline = {"existing_overrides": [], "assignment": None}

        # Fetch the assignment
        a, err = canvas_client._canvas_get(
            f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
        if err:
            baseline["canvas_error"] = err
            return baseline
        baseline["assignment"] = a

        # Fetch existing overrides
        overrides, err = canvas_client._canvas_get(
            f"/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides",
            {"per_page": 100})
        if err and "404" not in str(err):
            baseline["canvas_error"] = err
            return baseline
        baseline["existing_overrides"] = _as_list(overrides) if not err else []
        return baseline

    def check_drift(self, payload: dict, target: dict, baseline: dict) -> bool:
        if baseline is None:
            return False
        if "canvas_error" in baseline:
            return True
        # Re-fetch assignment to check due_at hasn't changed
        course_id = target["course_id"]
        assignment_id = payload.get("assignment_id", "")
        a, err = canvas_client._canvas_get(
            f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
        if err:
            return True
        stored = baseline.get("assignment") or {}
        if a.get("due_at") != stored.get("due_at"):
            return True
        return False

    # ── Review ───────────────────────────────────────────────────────────

    def freeze_review(self, payload: dict, target: dict, baseline: dict) -> dict:
        course_id = target["course_id"]
        course_name = course_id
        for course in config.active_courses():
            if str(course["id"]) == str(course_id):
                course_name = course.get("name") or course.get("nickname") or course_id
                break
        a = baseline.get("assignment") or {}
        existing = baseline.get("existing_overrides", [])
        return {
            "course_name": course_name,
            "assignment_name": a.get("name", payload.get("assignment_id")),
            "student_count": len(payload.get("student_ids", [])),
            "days": payload.get("days"),
            "existing_override_count": len(existing),
            "baseline_due_at": a.get("due_at"),
        }

    # ── Execute ──────────────────────────────────────────────────────────

    def execute(self, payload: dict, target: dict, baseline: dict,
                claim: dict, context) -> dict:
        course_id = target["course_id"]
        assignment_id = payload.get("assignment_id", "")
        student_ids = payload.get("student_ids", [])
        days = payload.get("days", 1)
        skip_we = payload.get("skip_weekends", True)
        hols = set(payload.get("holidays", []))
        try:
            hols.update(
                config.get_combined_calendar_for_range().get("no_count_dates") or [])
        except Exception:
            pass

        steps = _ordered_steps(target)
        step = _step(steps, "apply_extension")

        # Fetch assignment for due date
        a, err = canvas_client._canvas_get(
            f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
        if err:
            step["state"] = "failed"
            step["error_code"] = "assignment_fetch_failed"
            step["private_diagnostic"] = err
            step = context.checkpoint_step(step)
            _replace_local_step(steps, step)
            return _build_result("failed", steps=steps, error_code="assignment_fetch_failed")

        due = _parse_iso_local(a.get("due_at"))
        if not due:
            step["state"] = "blocked"
            step["error_code"] = "no_due_date"
            step = context.checkpoint_step(step)
            _replace_local_step(steps, step)
            return _build_result("blocked", steps=steps, error_code="no_due_date")

        # Fetch existing overrides to detect conflicts
        existing_ovs, err = canvas_client._canvas_get(
            f"/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides",
            {"per_page": 100})
        if err and "404" not in str(err):
            step["state"] = "failed"
            step["error_code"] = "override_fetch_failed"
            step["private_diagnostic"] = err
            step = context.checkpoint_step(step)
            _replace_local_step(steps, step)
            return _build_result("failed", steps=steps, error_code="override_fetch_failed")

        existing_ovs = _as_list(existing_ovs) if not err else []

        # For each student, find their existing override
        results = []
        all_applied = True
        for sid in student_ids:
            candidate = _find_student_override(existing_ovs, sid)
            new_due = _add_school_days(due, days, skip_we, hols)

            if candidate is None:
                # Create new student-specific override
                ov_payload = {
                    "assignment_override": {
                        "student_ids": [int(sid)],
                        "title": f"Extra time (+{days} school day{'s' if days != 1 else ''})",
                        "due_at": new_due.isoformat(),
                    }
                }
                ov_path = f"/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides"
                digest = models.sha256_dict({
                    "method": "POST", "path": ov_path, "payload": ov_payload,
                })
                context.before_send(f"create_override_{sid}", digest)
                resp, err = canvas_client._canvas_send("POST", ov_path, ov_payload)
                if err:
                    state = "sent_unknown" if _is_uncertain(err) else "failed"
                    results.append({"student_id": sid, "state": state, "error": err})
                    if state == "failed":
                        all_applied = False
                else:
                    results.append({"student_id": sid, "state": "applied",
                                    "override_id": str(resp.get("id")) if resp else None})

            elif candidate.get("state") == "ambiguous":
                results.append({"student_id": sid, "state": "blocked",
                                "error_code": "ambiguous_override"})
                all_applied = False

            else:
                # Update existing exclusive override
                ov_id = candidate["id"]
                ov_payload = {
                    "assignment_override": {
                        "student_ids": [int(sid)],
                        "due_at": new_due.isoformat(),
                    }
                }
                ov_path = f"/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides/{ov_id}"
                digest = models.sha256_dict({
                    "method": "PUT", "path": ov_path, "payload": ov_payload,
                })
                context.before_send(f"update_override_{sid}", digest)
                resp, err = canvas_client._canvas_send("PUT", ov_path, ov_payload)
                if err:
                    state = "sent_unknown" if _is_uncertain(err) else "failed"
                    results.append({"student_id": sid, "state": state, "error": err})
                    if state == "failed":
                        all_applied = False
                else:
                    results.append({"student_id": sid, "state": "applied",
                                    "override_id": str(resp.get("id")) if resp else None})

        step["state"] = "applied" if all_applied else "partial"
        step["results"] = results
        step = context.checkpoint_step(step)
        _replace_local_step(steps, step)
        return _build_result(step["state"], steps=steps)

    # ── Reconciliation ───────────────────────────────────────────────────

    def reconcile(self, payload: dict, target: dict, baseline: dict) -> dict:
        course_id = target["course_id"]
        assignment_id = payload.get("assignment_id", "")
        steps = _ordered_steps(target)
        step = _step(steps, "apply_extension")
        has_marker = _has_outbound_marker(steps)

        if not has_marker and not step.get("outbound_started_at"):
            return {"state": "pending"}

        # Verify at least one override exists for our students
        overrides, err = canvas_client._canvas_get(
            f"/api/v1/courses/{course_id}/assignments/{assignment_id}/overrides",
            {"per_page": 100})
        if err:
            return {"state": "sent_unknown"}
        ovs = _as_list(overrides)
        target_ids = set(payload.get("student_ids", []))
        for ov in ovs:
            ov_students = [str(s) for s in (ov.get("student_ids") or [])]
            if any(s in target_ids for s in ov_students):
                return {"state": "applied"}
        return {"state": "sent_unknown" if has_marker else "pending"}

    # ── Retry / reversal ─────────────────────────────────────────────────

    def retry_selector(self, operation: dict) -> list[dict]:
        return [t for t in operation.get("targets", [])
                if models.is_unresolved_target_state(t.get("state", "pending"))]

    def reversal_descriptor(self, payload: dict, target: dict) -> dict:
        baseline = target.get("baseline") or {}
        existing = baseline.get("existing_overrides", [])
        if existing:
            return {"supported": True, "method": "restore_snapshot",
                    "snapshot": {"overrides": existing}}
        return {"supported": False, "method": None, "snapshot": None}


# ── Helpers ──────────────────────────────────────────────────────────────

def _find_student_override(overrides: list, student_id: str) -> dict | None:
    """Find the override for a student, or None if none exists.

    Returns the override dict if exactly one student-specific override exists.
    Returns {'state': 'ambiguous'} if the student is in a shared/section/group
    override or multiple overrides apply.
    """
    matches = []
    for ov in overrides:
        ov_students = [str(s) for s in (ov.get("student_ids") or [])]
        if str(student_id) in ov_students:
            matches.append(ov)
        # Also check section/group overrides
        if ov.get("course_section_id") or ov.get("group_id"):
            matches.append(ov)

    if not matches:
        return None
    if len(matches) > 1:
        return {"state": "ambiguous"}
    m = matches[0]
    # If the match is a section/group override, it's ambiguous
    if m.get("course_section_id") or m.get("group_id"):
        return {"state": "ambiguous"}
    # If the match has more than one student, it's shared
    ov_students = [str(s) for s in (m.get("student_ids") or [])]
    if len(ov_students) > 1:
        return {"state": "ambiguous"}
    return m


def _ordered_steps(target: dict) -> list[dict]:
    existing = {s.get("step_key"): s for s in target.get("steps", [])}
    return [existing[k] for k in ("apply_extension",) if k in existing]


def _step(steps: list[dict], step_key: str) -> dict:
    found = next((s for s in steps if s.get("step_key") == step_key), None)
    if found is not None:
        return found
    s = models.new_step(step_key)
    steps.insert(0, s)
    return s


def _replace_local_step(steps: list[dict], step: dict) -> None:
    for i, existing in enumerate(steps):
        if existing.get("step_key") == step.get("step_key"):
            steps[i] = step
            return
    steps.append(step)


def _has_outbound_marker(steps: list[dict]) -> bool:
    return any(s.get("outbound_started_at") for s in steps)


def _as_list(data) -> list:
    if data is None:
        return []
    return data if isinstance(data, list) else [data]


def _is_uncertain(error: str) -> bool:
    lower = str(error or "").lower()
    return any(t in lower for t in (
        "timeout", "timed out", "connection", "network",
        "unparseable", "no response", "read timed out"))


def _build_result(state: str, *, steps: list[dict],
                  returned_object_id: str | None = None,
                  returned_object_url: str | None = None,
                  error_code: str | None = None,
                  private_diagnostic: str | None = None) -> dict:
    return {"state": state, "returned_object_id": returned_object_id,
            "returned_object_url": returned_object_url,
            "error_code": error_code, "private_diagnostic": private_diagnostic,
            "steps": steps}
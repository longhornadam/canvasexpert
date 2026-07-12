"""Late-sweep operation adapter for the crash-safe ``gradebook.sweep`` kind.

Server-authoritative late-work sweep: recomputes school-day lateness from
current Canvas state, applies per-student ``seconds_late_override`` via
Canvas Submissions API, and returns per-student results.
"""
from .. import models
from api.webui import canvas_client, config
from api.webui.schooldays import (
    _parse_iso_local, _school_days_late_detail,
)


KIND = "gradebook.sweep"


class SweepAdapter:
    kind = KIND

    # ── Payload ──────────────────────────────────────────────────────────

    def build_payload(self, prepare_request: dict) -> dict:
        settings = {
            "skip_weekends": bool(prepare_request.get("skip_weekends", True)),
            "honor_extra_time": bool(prepare_request.get("honor_extra_time", True)),
        }
        holidays = prepare_request.get("holidays", [])
        if isinstance(holidays, list):
            settings["holidays"] = [
                str(h).strip() for h in holidays if str(h).strip()
            ]
        date_from = prepare_request.get("date_from")
        if date_from:
            settings["date_from"] = str(date_from).strip()
        date_to = prepare_request.get("date_to")
        if date_to:
            settings["date_to"] = str(date_to).strip()
        return {"settings": settings}

    def source_digest(self, payload: dict) -> str:
        return models.sha256_dict(payload.get("settings", {}))

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
        )

    # ── Baseline / drift ─────────────────────────────────────────────────

    def capture_baseline(self, payload: dict, target: dict) -> dict:
        """Compute the sweep preview from current Canvas state."""
        course_id = target["course_id"]
        settings = payload.get("settings", {})
        entries, skipped, error = _compute_sweep(course_id, settings)
        if error:
            return {"canvas_error": error}
        return {
            "entries": entries,
            "skipped": skipped,
            "entry_count": len(entries),
        }

    def check_drift(self, payload: dict, target: dict, baseline: dict) -> bool:
        if baseline is None:
            return False
        if "canvas_error" in baseline:
            return True
        course_id = target.get("course_id")
        if not course_id:
            return False
        # Re-compute and compare entry count — if batch counts differ,
        # the Canvas state has changed
        settings = payload.get("settings", {})
        fresh, _, error = _compute_sweep(course_id, settings)
        if error:
            return True
        stored_count = baseline.get("entry_count", 0)
        if len(fresh) != stored_count:
            return True
        # Check per-student digest consistency
        stored_ids = {
            (e.get("user_id"), e.get("assignment_id"))
            for e in baseline.get("entries", [])
        }
        fresh_ids = {
            (e.get("user_id"), e.get("assignment_id"))
            for e in fresh
        }
        return stored_ids != fresh_ids

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
        entries = baseline.get("entries", [])
        return {
            "course_name": course_name,
            "settings": payload.get("settings", {}),
            "entry_count": len(entries),
            "entry_preview": [
                {
                    "student_name": e.get("student_name"),
                    "assignment_name": e.get("assignment_name"),
                    "school_days": e.get("school_days"),
                    "seconds_override": e.get("seconds_override"),
                }
                for e in entries[:50]
            ],
            "skipped_count": len(baseline.get("skipped", [])),
        }

    # ── Execute ──────────────────────────────────────────────────────────

    def execute(
        self, payload: dict, target: dict, baseline: dict,
        claim: dict, context,
    ) -> dict:
        course_id = target["course_id"]
        settings = payload.get("settings", {})
        steps = _ordered_steps(target)
        step = _step(steps, "apply_sweep")

        # Re-compute from current Canvas state (server-authoritative)
        entries, skipped, error = _compute_sweep(course_id, settings)
        if error:
            step["state"] = "failed"
            step["error_code"] = "sweep_computation_failed"
            step["private_diagnostic"] = error
            step = context.checkpoint_step(step)
            _replace_local_step(steps, step)
            return _build_result(
                "failed", steps=steps,
                error_code="sweep_computation_failed",
                private_diagnostic=error,
            )

        if not entries:
            step["state"] = "applied"
            step = context.checkpoint_step(step)
            _replace_local_step(steps, step)
            return _build_result("applied", steps=steps)

        # Apply per-student overrides
        results = []
        all_applied = True
        for entry in entries:
            uid = entry.get("user_id")
            aid = entry.get("assignment_id")
            seconds = entry.get("seconds_override", 0)
            path = (
                f"/api/v1/courses/{course_id}/assignments/"
                f"{aid}/submissions/{uid}"
            )
            request = {
                "submission": {
                    "late_policy_status": "late",
                    "seconds_late_override": seconds,
                }
            }
            digest = models.sha256_dict({
                "method": "PUT", "path": path, "payload": request,
            })
            context.before_send(f"apply_{uid}_{aid}", digest)

            response, err = canvas_client._canvas_send("PUT", path, request)
            if err:
                state = "sent_unknown" if _is_uncertain(err) else "failed"
                results.append({
                    "user_id": uid, "assignment_id": aid,
                    "state": state, "error": err,
                })
                if state == "failed":
                    all_applied = False
            else:
                results.append({
                    "user_id": uid, "assignment_id": aid,
                    "state": "applied",
                })

        step["state"] = "applied" if all_applied else "partial"
        step["results_count"] = len(results)
        step = context.checkpoint_step(step)
        _replace_local_step(steps, step)

        state = "applied" if all_applied else "partial"
        return _build_result(state, steps=steps)

    # ── Reconciliation ───────────────────────────────────────────────────

    def reconcile(self, payload: dict, target: dict, baseline: dict) -> dict:
        course_id = target["course_id"]
        steps = _ordered_steps(target)
        step = _step(steps, "apply_sweep")
        has_marker = _has_outbound_marker(steps)

        if not has_marker and not step.get("outbound_started_at"):
            return {"state": "pending"}

        # Verify at least one submission was modified
        settings = payload.get("settings", {})
        entries, _, error = _compute_sweep(course_id, settings)
        if error:
            return {"state": "sent_unknown"}
        if not entries:
            return {"state": "applied"}
        # Check a sample entry to verify override was applied
        sample = entries[0]
        path = (
            f"/api/v1/courses/{course_id}/assignments/"
            f"{sample['assignment_id']}/submissions/{sample['user_id']}"
        )
        sub, err = canvas_client._canvas_get(path)
        if err:
            return {"state": "sent_unknown"}
        if not sub:
            return {"state": "sent_unknown"}
        if sub.get("seconds_late_override") == sample.get("seconds_override"):
            return {"state": "applied"}
        return {"state": "sent_unknown"}

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


def _compute_sweep(course_id: str, settings: dict):
    """Compute late-work sweep entries from current Canvas state.

    Returns (entries, skipped, error).  Follows the same logic as
    gradebook_service._sweep_compute but with correct unpacking of
    _school_days_late_detail (which returns 2 values, not 4).
    """
    skip_we = settings.get("skip_weekends", True)
    hols = set(settings.get("holidays", []))

    # Merge calendar holidays
    try:
        hols.update(
            config.get_combined_calendar_for_range().get("no_count_dates") or []
        )
    except Exception:
        pass

    assignments, err = canvas_client._canvas_get_all(
        f"/api/v1/courses/{course_id}/assignments", {"per_page": 100})
    if err:
        return [], [], err

    subs, err = canvas_client._canvas_get_all(
        f"/api/v1/courses/{course_id}/students/submissions",
        {"student_ids[]": "all", "per_page": 100}, timeout=60)
    if err:
        return [], [], err

    students, err = canvas_client._canvas_get_all(
        f"/api/v1/courses/{course_id}/users",
        {"enrollment_type[]": "student", "per_page": 100})
    if err:
        return [], [], err

    name_by_id = {str(s["id"]): (s.get("sortable_name") or s.get("name", ""))
                  for s in students}
    amap = {a["id"]: a for a in assignments if a.get("published", True)}

    entries, skipped = [], []
    for sub in subs:
        if sub.get("excused") or not sub.get("submitted_at"):
            continue
        aid = sub.get("assignment_id")
        a = amap.get(aid)
        if not a:
            continue
        uid = sub.get("user_id")
        if sub.get("workflow_state", "") != "late":
            continue

        due = _parse_iso_local(a.get("due_at"))
        subd = _parse_iso_local(sub.get("submitted_at"))
        if not due or not subd:
            continue

        school_days, excluded = _school_days_late_detail(
            due, subd, skip_we, hols)
        if excluded:
            skipped.append({
                "student_name": name_by_id.get(str(uid), uid),
                "assignment_name": a.get("name", aid),
                "reason": "; ".join(excluded),
            })
            continue

        entries.append({
            "user_id": uid,
            "student_name": name_by_id.get(str(uid), uid),
            "assignment_id": aid,
            "assignment_name": a.get("name", aid),
            "school_days": school_days,
            "seconds_override": school_days * 86400,
        })

    return entries, skipped, None


def _ordered_steps(target: dict) -> list[dict]:
    existing = {
        step.get("step_key"): step
        for step in target.get("steps", [])
    }
    return [existing[key] for key in ("apply_sweep",) if key in existing]


def _step(steps: list[dict], step_key: str) -> dict:
    found = next(
        (s for s in steps if s.get("step_key") == step_key), None
    )
    if found is not None:
        return found
    s = models.new_step(step_key)
    steps.insert(0, s)
    return s


def _replace_local_step(steps: list[dict], step: dict) -> None:
    for index, existing in enumerate(steps):
        if existing.get("step_key") == step.get("step_key"):
            steps[index] = step
            return
    steps.append(step)


def _has_outbound_marker(steps: list[dict]) -> bool:
    return any(step.get("outbound_started_at") for step in steps)


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
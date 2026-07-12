"""Late-policy adapter for the crash-safe ``gradebook.late_policy`` kind.

Single-course, single-step: capture current Canvas policy, validate normalized
settings, apply via PATCH or POST, and return receipt with before/after state.
Reversal is ``restore_snapshot`` when the full prior policy was captured.
"""
from .. import models
from api.webui import canvas_client, config


KIND = "gradebook.late_policy"

# Canvas late-policy field names
_BOOLEAN_FIELDS = (
    "late_submission_deduction_enabled",
    "late_submission_minimum_percent_enabled",
    "missing_submission_deduction_enabled",
)
_NUMERIC_FIELDS = (
    "late_submission_deduction",
    "late_submission_minimum_percent",
    "missing_submission_deduction",
)
_INTERVAL_FIELDS = ("late_submission_interval",)
_ALL_FIELDS = _BOOLEAN_FIELDS + _NUMERIC_FIELDS + _INTERVAL_FIELDS

_VALID_INTERVALS = ("day", "hour")


class LatePolicyAdapter:
    kind = KIND

    # ── Payload ──────────────────────────────────────────────────────────

    def build_payload(self, prepare_request: dict) -> dict:
        settings = {}
        raw = prepare_request.get("policy", prepare_request)
        for field in _BOOLEAN_FIELDS:
            val = raw.get(field)
            if val is not None:
                settings[field] = bool(val)
        for field in _NUMERIC_FIELDS:
            val = raw.get(field)
            if val is not None:
                try:
                    parsed = float(val)
                except (TypeError, ValueError):
                    raise ValueError(f"{field} must be a number")
                if parsed < 0 or parsed > 100:
                    raise ValueError(f"{field} must be between 0 and 100")
                settings[field] = parsed
        for field in _INTERVAL_FIELDS:
            val = raw.get(field)
            if val is not None:
                val = str(val).strip().lower()
                if val not in _VALID_INTERVALS:
                    raise ValueError(
                        f"{field} must be one of {_VALID_INTERVALS}"
                    )
                settings[field] = val
        if not settings:
            raise ValueError("at least one policy setting is required")
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
        course_id = target["course_id"]
        baseline = {"policy": None, "snapshot_complete": False}
        data, error = canvas_client._canvas_get(
            f"/api/v1/courses/{course_id}/late_policy"
        )
        if error and "404" in str(error):
            # No policy exists — baseline is empty
            return baseline
        if error:
            baseline["canvas_error"] = error
            return baseline
        policy = data.get("late_policy") if isinstance(data, dict) else None
        if policy is None:
            return baseline
        snapshot = {}
        all_present = True
        for field in _ALL_FIELDS:
            if field in policy:
                snapshot[field] = policy[field]
            else:
                all_present = False
        baseline["policy"] = snapshot
        baseline["snapshot_complete"] = all_present
        return baseline

    def check_drift(self, payload: dict, target: dict, baseline: dict) -> bool:
        if baseline is None:
            return False
        if "canvas_error" in baseline:
            return True
        # Drift is detected when Canvas already equals the target — that's
        # idempotent, not drifted. Drift means the policy changed *away* from
        # the reviewed baseline.
        return False

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
        return {
            "course_name": course_name,
            "settings": payload.get("settings", {}),
            "baseline_policy": baseline.get("policy"),
            "baseline_snapshot_complete": baseline.get("snapshot_complete", False),
        }

    # ── Execute ──────────────────────────────────────────────────────────

    def execute(
        self, payload: dict, target: dict, baseline: dict,
        claim: dict, context,
    ) -> dict:
        course_id = target["course_id"]
        settings = payload.get("settings", {})
        steps = _ordered_steps(target)
        step = _step(steps, "apply_policy")

        # Idempotency: if already applied, verify current state matches
        if step.get("state") in ("applied", "skipped"):
            current, error = canvas_client._canvas_get(
                f"/api/v1/courses/{course_id}/late_policy"
            )
            if not error and current:
                step["state"] = "skipped"
                return _build_result(
                    "applied", steps=steps,
                )

        # Determine method: PATCH if policy exists, POST if new
        method = "POST"
        existing = baseline.get("policy")
        if existing:
            method = "PATCH"

        request = {"late_policy": settings}
        path = f"/api/v1/courses/{course_id}/late_policy"
        digest = models.sha256_dict({
            "method": method, "path": path, "payload": request,
        })
        step = context.before_send("apply_policy", digest)
        _replace_local_step(steps, step)
        response, error = canvas_client._canvas_send(method, path, request)
        if error:
            state = "sent_unknown" if _is_uncertain(error) else "failed"
            step["state"] = state
            step["error_code"] = (
                "timeout_or_disconnect" if state == "sent_unknown"
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
        step["state"] = "applied"
        step = context.checkpoint_step(step)
        _replace_local_step(steps, step)
        return _build_result(
            "applied", steps=steps,
        )

    # ── Reconciliation ───────────────────────────────────────────────────

    def reconcile(self, payload: dict, target: dict, baseline: dict) -> dict:
        course_id = target["course_id"]
        steps = _ordered_steps(target)
        step = _step(steps, "apply_policy")
        has_marker = _has_outbound_marker(steps)

        data, error = canvas_client._canvas_get(
            f"/api/v1/courses/{course_id}/late_policy"
        )
        if error:
            if "404" in str(error) and not step.get("outbound_started_at"):
                return {"state": "pending"}
            return {"state": "sent_unknown"}
        policy = data.get("late_policy") if isinstance(data, dict) else None
        if policy is None:
            if has_marker:
                return {"state": "sent_unknown"}
            return {"state": "pending"}

        # Verify the applied settings match
        settings = payload.get("settings", {})
        for field, value in settings.items():
            current = policy.get(field)
            if field in _NUMERIC_FIELDS:
                if abs(float(current or 0) - float(value)) > 0.01:
                    return {"state": "sent_unknown"}
            elif field in _BOOLEAN_FIELDS:
                if bool(current) != bool(value):
                    return {"state": "sent_unknown"}
            else:
                if str(current or "").strip().lower() != str(value or "").strip().lower():
                    return {"state": "sent_unknown"}
        return {"state": "applied"}

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
        baseline = target.get("baseline") or {}
        if baseline.get("snapshot_complete") and baseline.get("policy"):
            return {
                "supported": True,
                "method": "restore_snapshot",
                "snapshot": baseline["policy"],
            }
        return {"supported": False, "method": None, "snapshot": None}


# ── Module-level helpers ─────────────────────────────────────────────────


def _ordered_steps(target: dict) -> list[dict]:
    existing = {
        step.get("step_key"): step
        for step in target.get("steps", [])
    }
    order = ("apply_policy",)
    return [existing[key] for key in order if key in existing]


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
"""Curve operation adapter for the crash-safe ``gradebook.curve`` kind.

Applies a curve model to one assignment and creates a canonical receipt.
Revert is a separate reviewed operation that restores original scores only
when current scores still match the applied snapshot (drift check).
"""
import json
import uuid as _uuid
from datetime import datetime

from .. import models
from api.webui import canvas_client, config
from api.webui.routes.gradebook_common import _assignment, _assignment_submissions, _course_students


KIND = "gradebook.curve"


class CurveAdapter:
    kind = KIND

    # ── Payload ──────────────────────────────────────────────────────────

    def build_payload(self, prepare_request: dict) -> dict:
        assignment_id = str(prepare_request.get("assignment_id") or "").strip()
        if not assignment_id:
            raise ValueError("assignment_id is required")
        curve_type = str(prepare_request.get("curve_type") or "").strip()
        if not curve_type:
            raise ValueError("curve_type is required")
        settings_raw = prepare_request.get("settings", {})
        if isinstance(settings_raw, str):
            try:
                settings_raw = json.loads(settings_raw)
            except (json.JSONDecodeError, TypeError):
                settings_raw = {}
        return {
            "assignment_id": assignment_id,
            "curve_type": curve_type,
            "settings": dict(settings_raw),
        }

    def source_digest(self, payload: dict) -> str:
        return models.sha256_dict({
            "assignment_id": payload.get("assignment_id"),
            "curve_type": payload.get("curve_type"),
            "settings": payload.get("settings", {}),
        })

    def verify_targets(self, payload: dict, targets: list[dict]) -> list[dict]:
        active_ids = {str(c["id"]) for c in config.active_courses()}
        verified = []
        for target in targets:
            cid = str(target.get("course_id") or "")
            if not cid:
                raise ValueError("target missing course_id")
            if cid not in active_ids:
                raise ValueError(f"course {cid} is not in active courses")
            verified.append({
                "course_id": cid,
                "target_key": self.target_key(payload, cid),
                "idempotency_key": self.idempotency_key(payload, cid),
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
        baseline = {"scored_students": [], "assignment": None}

        a, err = _assignment(course_id, assignment_id)
        if err:
            baseline["canvas_error"] = err
            return baseline
        baseline["assignment"] = a

        students, err = _course_students(course_id)
        if err:
            baseline["canvas_error"] = err
            return baseline
        name_by_id = {str(s["id"]): (s.get("sortable_name") or s.get("name", ""))
                      for s in students}

        subs, err = _assignment_submissions(course_id, assignment_id)
        if err:
            baseline["canvas_error"] = err
            return baseline

        scored = [{"user_id": str(sub["user_id"]),
                   "student_name": name_by_id.get(str(sub["user_id"]), f"user {sub['user_id']}"),
                   "score": sub.get("score")}
                  for sub in (subs or []) if sub.get("workflow_state") == "graded"]
        baseline["scored_students"] = scored
        return baseline

    def check_drift(self, payload: dict, target: dict, baseline: dict) -> bool:
        if baseline is None:
            return False
        if "canvas_error" in baseline:
            return True
        # Re-fetch submissions and compare scores
        course_id = target["course_id"]
        assignment_id = payload.get("assignment_id", "")
        subs, err = _assignment_submissions(course_id, assignment_id)
        if err:
            return True
        stored = {s["user_id"]: s.get("score") for s in baseline.get("scored_students", [])}
        for sub in (subs or []):
            uid = str(sub["user_id"])
            if uid in stored and sub.get("score") != stored[uid]:
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
        pts = a.get("points_possible") or 0
        scored = baseline.get("scored_students", [])
        scores = [s.get("score") or 0 for s in scored]
        from api.webui.gradebook_service import _apply_curve_model as _acm
        preview = _acm(scored, payload.get("curve_type"),
                                      payload.get("settings", {}), pts)
        return {
            "course_name": course_name,
            "assignment_name": a.get("name", payload.get("assignment_id")),
            "points_possible": pts,
            "curve_type": payload.get("curve_type"),
            "student_count": len(scored),
            "original_avg": round(sum(scores) / len(scores), 1) if scores else None,
            "preview_count": len(preview),
        }

    # ── Execute ──────────────────────────────────────────────────────────

    def execute(self, payload: dict, target: dict, baseline: dict,
                claim: dict, context) -> dict:
        course_id = target["course_id"]
        assignment_id = payload.get("assignment_id", "")
        curve_type = payload.get("curve_type", "")
        settings = payload.get("settings", {})
        steps = _ordered_steps(target)
        step = _step(steps, "apply_curve")

        a = baseline.get("assignment") or {}
        pts = a.get("points_possible") or 0
        scored = baseline.get("scored_students", [])

        # Re-apply curve model server-side
        from api.webui.gradebook_service import _apply_curve_model as _acm
        results = _acm(scored, curve_type, settings, pts)

        if not results:
            step["state"] = "applied"
            step = context.checkpoint_step(step)
            _replace_local_step(steps, step)
            return _build_result("applied", steps=steps)

        # Check drift against current scores
        current_subs, _ = _assignment_submissions(course_id, assignment_id)
        current_by_uid = {str(sub["user_id"]): sub.get("score")
                          for sub in (current_subs or [])}

        drifted = []
        for r in results:
            uid = str(r["user_id"])
            current = current_by_uid.get(uid)
            stored = next((s.get("score") for s in scored if str(s["user_id"]) == uid), None)
            if current is not None and stored is not None and abs(float(current) - float(stored)) > 0.01:
                drifted.append(uid)

        if drifted:
            step["state"] = "blocked"
            step["error_code"] = "drift_detected"
            step["private_diagnostic"] = f"{len(drified)} student scores changed since preview"
            step = context.checkpoint_step(step)
            _replace_local_step(steps, step)
            return _build_result("blocked", steps=steps, error_code="drift_detected")

        # Apply grades
        push_results = []
        all_ok = True
        for r in results:
            uid = str(r["user_id"])
            curved = r["curved_score"]
            path = f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/{uid}"
            request = {"submission": {"posted_grade": str(curved)}}
            digest = models.sha256_dict({"method": "PUT", "path": path, "payload": request})
            context.before_send(f"curve_{uid}", digest)
            resp, err = canvas_client._canvas_send("PUT", path, request)
            if err:
                state = "sent_unknown" if _is_uncertain(err) else "failed"
                push_results.append({"user_id": uid, "state": state, "error": err})
                if state == "failed":
                    all_ok = False
            else:
                push_results.append({"user_id": uid, "state": "applied"})

        # Create curve event record
        event_id = f"curve_{_uuid.uuid4().hex[:8]}"
        event_students = [{
            "user_id": r["user_id"],
            "student_name": r.get("student_name", r["user_id"]),
            "original_score": r["original_score"],
            "curved_score": r["curved_score"],
            "score_at_apply_time": current_by_uid.get(str(r["user_id"])),
            "changed": r.get("changed", True),
        } for r in results]

        from api.webui.gradebook_service import _load_curve_events as _lce
        events = _lce()
        events.append({
            "id": event_id, "course_id": str(course_id),
            "assignment_id": str(assignment_id),
            "assignment_name": a.get("name", assignment_id),
            "curve_type": curve_type, "curve_settings": settings,
            "applied_at": datetime.now().isoformat(timespec="seconds"),
            "reverted": False, "students": event_students,
        })
        from api.webui.gradebook_service import _save_curve_events as _sce
        _sce(events)

        step["state"] = "applied" if all_ok else "partial"
        step["event_id"] = event_id
        step = context.checkpoint_step(step)
        _replace_local_step(steps, step)
        return _build_result(step["state"], steps=steps)

    # ── Reconciliation ───────────────────────────────────────────────────

    def reconcile(self, payload: dict, target: dict, baseline: dict) -> dict:
        course_id = target["course_id"]
        assignment_id = payload.get("assignment_id", "")
        steps = _ordered_steps(target)
        step = _step(steps, "apply_curve")
        has_marker = _has_outbound_marker(steps)
        if not has_marker and not step.get("outbound_started_at"):
            return {"state": "pending"}
        # Verify at least one submission was updated
        subs, err = _assignment_submissions(course_id, assignment_id)
        if err:
            return {"state": "sent_unknown"}
        scored = baseline.get("scored_students", [])
        if not scored:
            return {"state": "applied"}
        sample = scored[0]
        sub = next((s for s in (subs or []) if str(s.get("user_id")) == str(sample["user_id"])), None)
        if sub and sub.get("score") != sample.get("score"):
            return {"state": "applied"}
        if has_marker:
            return {"state": "sent_unknown"}
        return {"state": "pending"}

    # ── Retry / reversal ─────────────────────────────────────────────────

    def retry_selector(self, operation: dict) -> list[dict]:
        return [t for t in operation.get("targets", [])
                if models.is_unresolved_target_state(t.get("state", "pending"))]

    def reversal_descriptor(self, payload: dict, target: dict) -> dict:
        baseline = target.get("baseline") or {}
        scored = baseline.get("scored_students", [])
        if scored:
            return {"supported": True, "method": "restore_originals",
                    "snapshot": {"students": scored}}
        return {"supported": False, "method": None, "snapshot": None}


# ── Helpers ──────────────────────────────────────────────────────────────

def _ordered_steps(target: dict) -> list[dict]:
    existing = {s.get("step_key"): s for s in target.get("steps", [])}
    return [existing[k] for k in ("apply_curve",) if k in existing]

def _step(steps: list[dict], step_key: str) -> dict:
    found = next((s for s in steps if s.get("step_key") == step_key), None)
    if found: return found
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
    if data is None: return []
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
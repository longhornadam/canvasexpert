"""Roster group membership adapter for ``roster.membership``.

Adds or removes students from Canvas groups with idempotency.
"""
from .. import models
from api.webui import canvas_client, config


KIND = "roster.membership"


class MembershipAdapter:
    kind = KIND

    def build_payload(self, prepare_request: dict) -> dict:
        group_id = str(prepare_request.get("group_id") or "").strip()
        if not group_id:
            raise ValueError("group_id is required")
        student_ids = prepare_request.get("student_ids", [])
        if isinstance(student_ids, str):
            import json
            try:
                student_ids = json.loads(student_ids)
            except (json.JSONDecodeError, TypeError):
                student_ids = [student_ids]
        action = str(prepare_request.get("action") or "add").strip().lower()
        if action not in ("add", "remove"):
            raise ValueError("action must be 'add' or 'remove'")
        return {
            "group_id": group_id,
            "student_ids": [str(s).strip() for s in (student_ids or [])],
            "action": action,
        }

    def source_digest(self, payload: dict) -> str:
        return models.sha256_dict({
            "group_id": payload.get("group_id"),
            "student_ids": sorted(payload.get("student_ids", [])),
            "action": payload.get("action"),
        })

    def verify_targets(self, payload, targets):
        active_ids = {str(c["id"]) for c in config.active_courses()}
        verified = []
        for target in targets:
            cid = str(target.get("course_id") or "")
            if not cid:
                raise ValueError("target missing course_id")
            if cid not in active_ids:
                raise ValueError(f"course {cid} not in active courses")
            verified.append({"course_id": cid, "target_key": self.target_key(payload, cid),
                             "idempotency_key": self.idempotency_key(payload, cid)})
        return verified

    def target_key(self, payload, course_id):
        return models.sha256_hex(f"{KIND}|{self.source_digest(payload)}|{course_id}")

    def idempotency_key(self, payload, course_id):
        return models.sha256_hex(f"{self.source_digest(payload)}|{course_id}")

    def capture_baseline(self, payload, target):
        group_id = payload.get("group_id", "")
        members, err = canvas_client._canvas_get(
            f"/api/v1/groups/{group_id}/memberships", {"per_page": 100})
        if err:
            return {"canvas_error": err}
        return {"existing_memberships": _as_list(members)}

    def check_drift(self, payload, target, baseline):
        if baseline is None: return False
        if "canvas_error" in baseline: return True
        existing = {str(m.get("user_id")) for m in baseline.get("existing_memberships", [])}
        target_ids = set(payload.get("student_ids", []))
        action = payload.get("action", "add")
        if action == "add":
            already_present = target_ids & existing
            return set(payload.get("student_ids", [])) == already_present
        else:
            already_absent = target_ids - existing
            return already_absent == set(payload.get("student_ids", []))
        return False

    def freeze_review(self, payload, target, baseline):
        course_id = target["course_id"]
        course_name = course_id
        for course in config.active_courses():
            if str(course["id"]) == str(course_id):
                course_name = course.get("name") or course.get("nickname") or course_id
                break
        return {"course_name": course_name, "group_id": payload.get("group_id"),
                "student_count": len(payload.get("student_ids", [])),
                "action": payload.get("action")}

    def execute(self, payload, target, baseline, claim, context):
        group_id = payload.get("group_id", "")
        student_ids = payload.get("student_ids", [])
        action = payload.get("action", "add")
        steps = _ordered_steps(target)
        step = _step(steps, "apply_membership")
        results = []
        all_ok = True
        for sid in student_ids:
            if action == "add":
                path = f"/api/v1/groups/{group_id}/memberships"
                req = {"user_id": int(sid)}
                digest = models.sha256_dict({"method": "POST", "path": path, "payload": req})
                context.before_send(f"add_{sid}", digest)
                resp, err = canvas_client._canvas_send("POST", path, req)
            else:
                path = f"/api/v1/groups/{group_id}/memberships/{sid}"
                digest = models.sha256_dict({"method": "DELETE", "path": path})
                context.before_send(f"remove_{sid}", digest)
                resp, err = canvas_client._canvas_send("DELETE", path, {})
            if err:
                state = "sent_unknown" if _is_uncertain(err) else "failed"
                results.append({"student_id": sid, "state": state, "error": err})
                if state == "failed":
                    all_ok = False
            else:
                results.append({"student_id": sid, "state": "applied"})
        step["state"] = "applied" if all_ok else "partial"
        step["results"] = results
        step = context.checkpoint_step(step)
        _replace_local_step(steps, step)
        return _build_result(step["state"], steps=steps)

    def reconcile(self, payload, target, baseline):
        group_id = payload.get("group_id", "")
        steps = _ordered_steps(target)
        has_marker = _has_outbound_marker(steps)
        if not has_marker:
            return {"state": "pending"}
        members, err = canvas_client._canvas_get(
            f"/api/v1/groups/{group_id}/memberships", {"per_page": 100})
        if err:
            return {"state": "sent_unknown"}
        existing = {str(m.get("user_id")) for m in _as_list(members)}
        target_ids = set(payload.get("student_ids", []))
        action = payload.get("action", "add")
        if action == "add":
            if target_ids & existing:
                return {"state": "applied"}
        else:
            if not (target_ids & existing):
                return {"state": "applied"}
        return {"state": "sent_unknown"}

    def retry_selector(self, operation):
        return [t for t in operation.get("targets", [])
                if models.is_unresolved_target_state(t.get("state", "pending"))]

    def reversal_descriptor(self, payload, target):
        return {"supported": False, "method": None, "snapshot": None}


def _ordered_steps(target):
    existing = {s.get("step_key"): s for s in target.get("steps", [])}
    return [existing[k] for k in ("apply_membership",) if k in existing]

def _step(steps, key):
    found = next((s for s in steps if s.get("step_key") == key), None)
    if found: return found
    s = models.new_step(key)
    steps.insert(0, s)
    return s

def _replace_local_step(steps, step):
    for i, s in enumerate(steps):
        if s.get("step_key") == step.get("step_key"):
            steps[i] = step
            return
    steps.append(step)

def _has_outbound_marker(steps):
    return any(s.get("outbound_started_at") for s in steps)

def _as_list(data):
    if data is None: return []
    return data if isinstance(data, list) else [data]

def _is_uncertain(error):
    lower = str(error or "").lower()
    return any(t in lower for t in ("timeout","timed out","connection","network","unparseable","no response","read timed out"))

def _build_result(state, *, steps, **kw):
    return {"state": state, "steps": steps, **kw}
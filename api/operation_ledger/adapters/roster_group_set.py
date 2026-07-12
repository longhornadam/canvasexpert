"""Roster group-set/group creation adapter for ``roster.group_set``.

Creates Canvas group categories and optionally seeds groups inside them.
"""
from .. import models
from api.webui import canvas_client, config


KIND = "roster.group_set"


class GroupSetAdapter:
    kind = KIND

    def build_payload(self, prepare_request: dict) -> dict:
        name = str(prepare_request.get("name") or "").strip()
        if not name:
            raise ValueError("group set name is required")
        group_names = prepare_request.get("group_names", [])
        if isinstance(group_names, str):
            import json
            try:
                group_names = json.loads(group_names)
            except (json.JSONDecodeError, TypeError):
                group_names = [group_names]
        if not isinstance(group_names, list) or not group_names:
            raise ValueError("at least one group name is required")
        return {
            "name": name,
            "group_names": [str(g).strip() for g in group_names if str(g).strip()],
        }

    def source_digest(self, payload: dict) -> str:
        return models.sha256_dict({
            "name": payload.get("name"),
            "group_names": sorted(payload.get("group_names", [])),
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

    def capture_baseline(self, payload: dict, target: dict) -> dict:
        course_id = target["course_id"]
        cats, err = canvas_client._canvas_get_all(
            f"/api/v1/courses/{course_id}/group_categories", {"per_page": 100})
        if err:
            return {"canvas_error": err}
        name = payload.get("name", "")
        existing = [c for c in (cats or []) if str(c.get("name", "")).strip().lower() == name.lower()]
        return {"existing_categories": [{
            "id": str(c["id"]), "name": c.get("name")
        } for c in existing]}

    def check_drift(self, payload: dict, target: dict, baseline: dict) -> bool:
        if baseline is None:
            return False
        if "canvas_error" in baseline:
            return True
        existing = baseline.get("existing_categories", [])
        # Drift if a category with this name already exists
        return len(existing) > 0

    def freeze_review(self, payload: dict, target: dict, baseline: dict) -> dict:
        course_id = target["course_id"]
        course_name = course_id
        for course in config.active_courses():
            if str(course["id"]) == str(course_id):
                course_name = course.get("name") or course.get("nickname") or course_id
                break
        return {
            "course_name": course_name,
            "group_set_name": payload.get("name"),
            "group_names": payload.get("group_names", []),
            "group_count": len(payload.get("group_names", [])),
        }

    def execute(self, payload: dict, target: dict, baseline: dict,
                claim: dict, context) -> dict:
        course_id = target["course_id"]
        name = payload.get("name", "")
        group_names = payload.get("group_names", [])
        steps = _ordered_steps(target)
        cat_step = _step(steps, "create_category")
        name_step = _step(steps, "create_groups")

        # Create the group category
        path = f"/api/v1/courses/{course_id}/group_categories"
        req = {"name": name}
        digest = models.sha256_dict({"method": "POST", "path": path, "payload": req})
        cat_step = context.before_send("create_category", digest)
        _replace_local_step(steps, cat_step)
        resp, err = canvas_client._canvas_send("POST", path, req)
        if err:
            state = "sent_unknown" if _is_uncertain(err) else "failed"
            cat_step["state"] = state
            cat_step["error_code"] = "canvas_rejected" if state == "failed" else "timeout_or_disconnect"
            cat_step["private_diagnostic"] = err
            cat_step = context.checkpoint_step(cat_step)
            _replace_local_step(steps, cat_step)
            return _build_result(state, steps=steps, error_code=cat_step["error_code"])
        cat_id = str(resp.get("id")) if isinstance(resp, dict) else None
        if not cat_id:
            cat_step["state"] = "sent_unknown"
            cat_step["error_code"] = "unparseable_response"
            cat_step = context.checkpoint_step(cat_step)
            _replace_local_step(steps, cat_step)
            return _build_result("sent_unknown", steps=steps, error_code="unparseable_response")
        cat_step["state"] = "applied"
        cat_step = context.checkpoint_step(cat_step, returned_object_id=cat_id)
        _replace_local_step(steps, cat_step)

        # Create each group
        created = []
        all_ok = True
        for gname in group_names:
            gpath = f"/api/v1/group_categories/{cat_id}/groups"
            greq = {"name": gname}
            gdigest = models.sha256_dict({"method": "POST", "path": gpath, "payload": greq})
            context.before_send(f"create_group_{gname}", gdigest)
            gresp, gerr = canvas_client._canvas_send("POST", gpath, greq)
            if gerr:
                state = "sent_unknown" if _is_uncertain(gerr) else "failed"
                created.append({"name": gname, "state": state, "error": gerr})
                if state == "failed":
                    all_ok = False
            else:
                gid = str(gresp.get("id")) if isinstance(gresp, dict) else None
                created.append({"name": gname, "state": "applied", "id": gid})
        name_step["state"] = "applied" if all_ok else "partial"
        name_step["created_groups"] = created
        name_step = context.checkpoint_step(name_step)
        _replace_local_step(steps, name_step)
        return _build_result("applied" if all_ok else "partial", steps=steps,
                             returned_object_id=cat_id)

    def reconcile(self, payload: dict, target: dict, baseline: dict) -> dict:
        course_id = target["course_id"]
        name = payload.get("name", "")
        cats, err = canvas_client._canvas_get_all(
            f"/api/v1/courses/{course_id}/group_categories", {"per_page": 100})
        if err:
            return {"state": "sent_unknown"}
        if any(str(c.get("name", "")).strip().lower() == name.lower() for c in (cats or [])):
            return {"state": "applied"}
        steps = _ordered_steps(target)
        return {"state": "sent_unknown" if _has_outbound_marker(steps) else "pending"}

    def retry_selector(self, operation: dict) -> list[dict]:
        return [t for t in operation.get("targets", [])
                if models.is_unresolved_target_state(t.get("state", "pending"))]

    def reversal_descriptor(self, payload: dict, target: dict) -> dict:
        return {"supported": False, "method": None, "snapshot": None}


def _ordered_steps(target: dict) -> list[dict]:
    existing = {s.get("step_key"): s for s in target.get("steps", [])}
    return [existing[k] for k in ("create_category", "create_groups") if k in existing]

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

def _is_uncertain(error):
    lower = str(error or "").lower()
    return any(t in lower for t in ("timeout","timed out","connection","network","unparseable","no response","read timed out"))

def _build_result(state, *, steps, **kw):
    return {"state": state, "steps": steps, **kw}
"""Gradebook late-policy routes."""
import json

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from ..canvas_client import _canvas_get, _canvas_send

router = APIRouter(tags=["gradebook"])


@router.get("/api/late-policy")
def get_late_policy(course_id: str):
    data, err = _canvas_get(f"/api/v1/courses/{course_id}/late_policy")
    if err and "404" in err:
        return JSONResponse({"ok": True, "policy": None})
    if err:
        return JSONResponse({"ok": False, "error": err})
    return JSONResponse({"ok": True, "policy": data.get("late_policy")})


@router.post("/api/late-policy/apply")
def apply_late_policy(courses: str = Form(...), policy: str = Form(...)):
    """Create or update the Canvas late policy in every target course."""
    try:
        targets = json.loads(courses)
        p = json.loads(policy)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})
    if not targets:
        return JSONResponse({"ok": False, "error": "no courses selected"})

    results = []
    for t in targets:
        cid = str(t.get("id", ""))
        cname = t.get("name", f"course {cid}")
        existing, gerr = _canvas_get(f"/api/v1/courses/{cid}/late_policy")
        if gerr and "404" not in gerr:
            results.append({"course_name": cname, "ok": False, "error": gerr})
            continue
        method = "PATCH" if (existing and not gerr) else "POST"
        _, err = _canvas_send(method, f"/api/v1/courses/{cid}/late_policy",
                              {"late_policy": p})
        results.append({"course_name": cname, "ok": not err, "error": err,
                        "title": f"late policy {'updated' if method == 'PATCH' else 'created'}"})
    return JSONResponse({"ok": all(r["ok"] for r in results), "results": results})

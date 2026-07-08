"""Push and validation routes for Canvas Expert.

One APIRouter for file validation, physical quiz output, content push, and
streaming push output.
"""
import json
import os

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from ..canvas_client import _canvas_get
from ..deps import _exports_dir, _workspace_folder
from ..push_service import _CONTENT_PUSHERS
from .push_streaming import register_streaming_routes
from .push_validation import register_validation_routes

router = APIRouter(tags=["push"])
register_validation_routes(
    router,
    exports_dir_func=lambda: _exports_dir(),
    workspace_folder_func=lambda name: _workspace_folder(name),
)
register_streaming_routes(router)


# --------------------------------------------------------------------------
# Route handlers
# --------------------------------------------------------------------------


@router.get("/api/modules")
def get_modules(course_id: str):
    """Canvas Modules list for a course."""
    data, err = _canvas_get(f"/api/v1/courses/{course_id}/modules", {"per_page": 100})
    if err:
        return JSONResponse({"ok": False, "error": err})
    modules = [{"id": str(m["id"]), "name": m["name"]}
               for m in (data or []) if "id" in m]
    return JSONResponse({"ok": True, "modules": modules})


@router.get("/api/assignment-groups")
def get_assignment_groups(course_id: str):
    """Grading categories (Canvas assignment groups) for a course."""
    data, err = _canvas_get(f"/api/v1/courses/{course_id}/assignment_groups")
    if err:
        return JSONResponse({"ok": False, "error": err})
    groups = [{"id": str(g["id"]), "name": g["name"]}
              for g in (data or []) if "id" in g]
    return JSONResponse({"ok": True, "groups": groups})


@router.post("/api/content/push")
def api_content_push(kind: str = Form(...), courses: str = Form(...), payload: str = Form(...)):
    """Create an assignment / page in every target course."""
    fn = _CONTENT_PUSHERS.get(kind)
    if not fn:
        return JSONResponse({"ok": False, "error": f"unknown kind '{kind}'"})
    try:
        targets = json.loads(courses)
        p = json.loads(payload)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"bad request: {e}"})
    if not targets:
        return JSONResponse({"ok": False, "error": "no courses selected"})

    results = []
    for t in targets:
        cid = str(t.get("id", ""))
        cname = t.get("name", f"course {cid}")
        notes = []
        course_payload = dict(p)
        course_payload["course_name"] = cname
        result = fn(cid, course_payload, notes)
        if hasattr(result, "ok"):
            ok = result.ok
            title = result.title
            url = result.url
            error = result.error
            assignment_id = getattr(result, "assignment_id", None)
        else:
            ok, title, url, error = result
            assignment_id = None
        results.append({"course_id": cid, "course_name": cname, "ok": ok,
                        "title": title, "url": url, "assignment_id": assignment_id,
                        "error": error, "notes": notes})
    return JSONResponse({"ok": all(r["ok"] for r in results), "results": results})

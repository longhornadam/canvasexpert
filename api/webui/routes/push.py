"""Push and validation routes for Canvas Expert.

One APIRouter for file validation, physical quiz output, and dry-run preview.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..canvas_client import _canvas_get
from ..deps import _exports_dir, _workspace_folder
from .push_validation import register_validation_routes

router = APIRouter(tags=["push"])
register_validation_routes(
    router,
    exports_dir_func=lambda: _exports_dir(),
    workspace_folder_func=lambda name: _workspace_folder(name),
)


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

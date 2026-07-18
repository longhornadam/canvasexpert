"""Push and validation routes for Canvas Expert.

One APIRouter for file validation, physical quiz output, and dry-run preview.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api import course_catalog
from api import runtime_paths
from ..canvas_client import _canvas_get
from .push_validation import register_validation_routes

router = APIRouter(tags=["push"])
register_validation_routes(
    router,
    exports_dir_func=runtime_paths.exports_dir,
    workspace_folder_func=runtime_paths.workspace_folder,
)


# --------------------------------------------------------------------------
# Route handlers
# --------------------------------------------------------------------------


@router.get("/api/modules")
def get_modules(course_id: str):
    """Canvas Modules list for a course."""
    read_result = course_catalog.read_catalog(course_id)
    catalog = read_result.get("catalog") if isinstance(read_result, dict) else None
    module_scope = catalog.get("modules") if isinstance(catalog, dict) else None
    records = module_scope.get("records") if isinstance(module_scope, dict) else None
    if (
        isinstance(module_scope, dict)
        and module_scope.get("state") == "current"
        and isinstance(records, list)
        and all(
            isinstance(module, dict)
            and isinstance(module.get("id"), str)
            and module["id"]
            and isinstance(module.get("name"), str)
            for module in records
        )
    ):
        modules = [{"id": module["id"], "name": module["name"]} for module in records]
        return JSONResponse({"ok": True, "modules": modules})
    data, err = _canvas_get(f"/api/v1/courses/{course_id}/modules", {"per_page": 100})
    if err:
        return JSONResponse({"ok": False, "error": err})
    modules = [{"id": str(m["id"]), "name": m["name"]}
               for m in (data or []) if "id" in m]
    return JSONResponse({"ok": True, "modules": modules})


@router.get("/api/assignment-groups")
def get_assignment_groups(course_id: str):
    """Grading categories (Canvas assignment groups) for a course."""
    read_result = course_catalog.read_catalog(course_id)
    catalog = read_result.get("catalog") if isinstance(read_result, dict) else None
    group_scope = catalog.get("assignment_groups") if isinstance(catalog, dict) and catalog.get("version") == course_catalog.CATALOG_VERSION else None
    records = group_scope.get("records") if isinstance(group_scope, dict) else None
    if (
        isinstance(group_scope, dict)
        and group_scope.get("state") == "current"
        and isinstance(records, list)
        and all(
            isinstance(group, dict)
            and set(group) == course_catalog.ASSIGNMENT_GROUP_KEYS
            and isinstance(group.get("id"), str)
            and group["id"]
            and isinstance(group.get("name"), str)
            and isinstance(group.get("position"), int)
            and not isinstance(group.get("group_weight"), bool)
            and isinstance(group.get("group_weight"), (int, float))
            for group in records
        )
    ):
        return JSONResponse({"ok": True, "groups": [{"id": group["id"], "name": group["name"]} for group in records]})
    data, err = _canvas_get(f"/api/v1/courses/{course_id}/assignment_groups")
    if err:
        return JSONResponse({"ok": False, "error": err})
    groups = [{"id": str(g["id"]), "name": g["name"]}
              for g in (data or []) if "id" in g]
    return JSONResponse({"ok": True, "groups": groups})

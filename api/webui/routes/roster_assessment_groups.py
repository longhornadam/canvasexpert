"""Read-only assessment grouping proposals for the Students page.

Preview uses only the local mirror and offline DataForge history.  Applying a
proposal remains the browser's existing ``/api/roster/bulk`` flow; this module
does not own a Canvas client or a new mutation transport.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Query
from fastapi.responses import JSONResponse

from api.dataforge import grouping, history_store, paths as dataforge_paths
from api.dataforge import canvas_join
from api.dataforge.identity import IdentityMigrationError, VaultIdentity
from api.mirror import store as mirror_store


router = APIRouter(prefix="/api/roster/assessment-groups", tags=["roster"])

# Re-exported so the route body and the tests name one class. Defined here rather
# than at the foot of the module so the ``except`` clause below cannot outrun it.
GroupingValidationError = grouping.GroupingValidationError


def _public_groups(document: dict | None) -> list[dict]:
    if not isinstance(document, dict):
        return []
    out = []
    for category in document.get("categories", []):
        if not isinstance(category, dict):
            continue
        out.append({
            "category_id": str(category.get("category_id") or ""),
            "category_name": str(category.get("category_name") or ""),
            "groups": [
                {
                    "id": str(group.get("id") or ""),
                    "name": str(group.get("name") or ""),
                }
                for group in category.get("groups", [])
                if isinstance(group, dict)
            ],
        })
    return out


def _snapshot_options(paths) -> list[dict]:
    options = []
    for snapshot in history_store.list_snapshots(paths):
        if not isinstance(snapshot, dict) or not str(snapshot.get("id") or "").strip():
            continue
        options.append({
            "id": str(snapshot["id"]),
            "label": str(snapshot.get("label") or snapshot["id"]),
            "date": str(snapshot.get("date") or ""),
            "student_count": len(snapshot.get("students") or []),
        })
    return options


def _error(message: str, status_code: int = 400):
    return JSONResponse({"ok": False, "error": message}, status_code=status_code)


@router.get("/sources")
def sources(course_id: str = Query("")):
    """Return local history and current mirror group-set choices."""
    if not course_id:
        return _error("course_id required.")
    roster_document = mirror_store.read_roster(course_id)
    groups_document = mirror_store.read_groups(course_id)
    if not isinstance(roster_document, dict) or roster_document.get("state") != "current":
        return _error("A current local roster mirror is required for assessment grouping.", 409)
    if not isinstance(groups_document, dict) or groups_document.get("state") != "current":
        return _error("A current local group mirror is required for assessment grouping.", 409)
    try:
        paths = dataforge_paths.get_paths()
        snapshots = _snapshot_options(paths)
    except (OSError, RuntimeError):
        snapshots = []
    return JSONResponse({
        "ok": True,
        "snapshots": snapshots,
        "groups": _public_groups(groups_document),
    })


def _selected_snapshot(paths, snapshot_id: str) -> dict | None:
    for snapshot in history_store.list_snapshots(paths):
        if isinstance(snapshot, dict) and str(snapshot.get("id") or "") == snapshot_id:
            return snapshot
    return None


@router.post("/preview")
def preview(
    course_id: str = Form(...),
    snapshot_id: str = Form(...),
    method: str = Form("overall_pct"),
    cutoffs: str = Form(""),
    no_data_group: str = Form(""),
    category_id: str = Form(""),
):
    """Build a complete proposal without any live Canvas access."""
    if not course_id:
        return _error("course_id required.")
    roster_document = mirror_store.read_roster(course_id)
    groups_document = mirror_store.read_groups(course_id)
    if not isinstance(roster_document, dict) or roster_document.get("state") != "current":
        return _error("A current local roster mirror is required for assessment grouping.", 409)
    if not isinstance(groups_document, dict) or groups_document.get("state") != "current":
        return _error("A current local group mirror is required for assessment grouping.", 409)

    try:
        paths = dataforge_paths.get_paths()
        snapshot = _selected_snapshot(paths, snapshot_id)
        if snapshot is None:
            return _error("Choose an available assessment snapshot.")
        category = next(
            (item for item in groups_document.get("categories", [])
             if str(item.get("category_id") or "") == str(category_id)),
            None,
        )
        if category is None:
            return _error("Choose a Canvas group set.")
        identity = VaultIdentity.from_paths(paths)
        linked_students = identity.linked_students()
        profile_students = {
            str(student.get("n")): {"latest_pct": student.get("pct")}
            for student in snapshot.get("students", [])
            if isinstance(student, dict) and str(student.get("n") or "").strip()
        }
        report = canvas_join.build_coverage_report(
            profile_students,
            linked_students,
            list((roster_document.get("students") or {}).values()),
        )
        proposal = grouping.build_grouping_proposal(
            snapshot,
            report,
            list((roster_document.get("students") or {}).values()),
            category,
            method=method,
            # Passed through as the raw form value: grouping._cutoffs parses the
            # JSON itself and reports a bad value as a validation error, so the
            # teacher gets "Cutoffs must be valid JSON" as a 400 rather than a
            # decoder message as a 409.
            cutoffs=cutoffs or None,
            no_data_group=no_data_group,
        )
    except IdentityMigrationError:
        return _error("The local assessment identity map is unavailable.", 409)
    except GroupingValidationError as exc:
        return _error(str(exc))
    except (OSError, RuntimeError, ValueError) as exc:
        return _error(str(exc) or "Assessment grouping preview is unavailable.", 409)
    return JSONResponse({"ok": True, "proposal": proposal})

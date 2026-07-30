"""One narrow, in-memory assignment-collection acquisition seam."""

from __future__ import annotations

from typing import Callable


ASSIGNMENTS_PATH = "/api/v1/courses/{course_id}/assignments"

CanvasGetAllComplete = Callable[[str, dict], tuple[object, str | None, bool]]
AssignmentCollectionReceipt = tuple[object, str | None, bool]


def acquire_assignment_collection(
    course_id: str,
    canvas_get_all_complete: CanvasGetAllComplete,
) -> AssignmentCollectionReceipt:
    """Fetch the complete collection without normalizing or persisting its rows."""
    return canvas_get_all_complete(
        ASSIGNMENTS_PATH.format(course_id=course_id), {"per_page": 100})

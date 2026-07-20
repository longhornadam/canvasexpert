"""PII-minimizing Canvas group resolver for tiered assignments."""
from __future__ import annotations

import hashlib

from api.webui import canvas_client, config


class GroupResolutionError(ValueError):
    """A safe, teacher-actionable group resolution failure."""


def resolve_assignment_groups(
    course_id: str,
    tiers: list[dict],
    *,
    canvas_get_all=None,
    selected_category_id=None,
) -> dict:
    """Return a durable safe snapshot and transient group-to-student IDs."""
    get_all = canvas_get_all or canvas_client._canvas_get_all
    category_id = (
        selected_category_id
        if selected_category_id is not None
        else config.get_selected_group_category_id(course_id)
    )
    if not category_id:
        raise GroupResolutionError(
            "Select a Canvas group set for this course in Roster before preparing tiers."
        )
    category_id = str(category_id)

    groups, error = get_all(
        f"/api/v1/group_categories/{category_id}/groups", {"per_page": 100}
    )
    if error and _permission_blocked(error):
        groups, error = get_all(
            f"/api/v1/courses/{course_id}/groups", {"per_page": 100}
        )
        if not error:
            groups = [
                group for group in (groups or [])
                if str(group.get("group_category_id")) == category_id
            ]
    if error:
        raise GroupResolutionError("Canvas groups could not be read for the selected group set.")

    resolved = []
    for index, tier in enumerate(tiers):
        authored_name = str(tier.get("group") or "").strip()
        matches = [
            group for group in (groups or [])
            if _normalize(group.get("name")) == _normalize(authored_name)
        ]
        if not matches:
            raise GroupResolutionError(f"Tier group {authored_name!r} was not found in the selected group set.")
        if len(matches) != 1:
            raise GroupResolutionError(f"Tier group {authored_name!r} is ambiguous in the selected group set.")
        group_id = matches[0].get("id")
        if group_id is None:
            raise GroupResolutionError(f"Tier group {authored_name!r} has no Canvas ID.")
        resolved.append((index, tier, str(group_id)))

    memberships_by_group = {}
    seen_students = set()
    for _, tier, group_id in resolved:
        memberships, error = get_all(
            f"/api/v1/groups/{group_id}/memberships",
            {"filter_states[]": "accepted", "per_page": 100},
        )
        if error:
            raise GroupResolutionError("Canvas group memberships could not be read.")
        student_ids = sorted({
            str(row.get("user_id")) for row in (memberships or [])
            if row.get("user_id") is not None
            and str(row.get("workflow_state") or "accepted").casefold() == "accepted"
        })
        if not student_ids:
            raise GroupResolutionError(f"Tier group {tier.get('group')!r} has no accepted members.")
        overlap = seen_students.intersection(student_ids)
        if overlap:
            raise GroupResolutionError("Referenced tier groups contain overlapping memberships.")
        seen_students.update(student_ids)
        memberships_by_group[group_id] = student_ids

    enrollments, error = get_all(
        f"/api/v1/courses/{course_id}/enrollments",
        {"type[]": "StudentEnrollment", "state[]": "active", "per_page": 100},
    )
    if error:
        raise GroupResolutionError("Canvas active student enrollments could not be read.")
    roster_ids = sorted({
        str(row.get("user_id")) for row in (enrollments or [])
        if row.get("user_id") is not None
        and str(row.get("enrollment_state") or "active").casefold() == "active"
    })
    if seen_students != set(roster_ids):
        raise GroupResolutionError(
            "Referenced tier groups must cover the active student roster exactly."
        )

    safe_tiers = []
    for index, tier, group_id in resolved:
        ids = memberships_by_group[group_id]
        safe_tiers.append({
            "index": index,
            "label": str(tier.get("label") or "").strip(),
            "group_name": str(tier.get("group") or "").strip(),
            "group_id": group_id,
            "student_count": len(ids),
            "membership_digest": _ids_digest(ids),
        })
    return {
        "safe": {
            "selected_category_id": category_id,
            "roster_count": len(roster_ids),
            "roster_digest": _ids_digest(roster_ids),
            "tiers": safe_tiers,
        },
        "student_ids_by_group": memberships_by_group,
    }


def _ids_digest(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()


def _normalize(value) -> str:
    return str(value or "").strip().casefold()


def _permission_blocked(error) -> bool:
    value = str(error or "").casefold()
    return any(token in value for token in ("http 401", "http 403", "forbidden", "permission"))

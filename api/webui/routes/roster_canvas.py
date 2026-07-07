"""Canvas-specific roster helpers with injected dependencies."""

from __future__ import annotations

from collections.abc import Callable

import requests

from .roster_helpers import _user_id_set_from_canvas_groups


def fetch_sections(course_id: str, *, canvas_get_all: Callable[..., tuple[list[dict] | None, str | None]]) -> dict:
    """Return {section_id: section_name} for a course."""
    sections, err = canvas_get_all(
        f"/api/v1/courses/{course_id}/sections", {"per_page": 100})
    if err or not sections:
        return {}
    return {str(s["id"]): s.get("name", f"Section {s['id']}") for s in sections}


def create_canvas_group(
    category_id: str,
    name: str,
    *,
    canvas_send: Callable[..., tuple[dict | None, str | None]],
) -> tuple[dict | None, str | None]:
    return canvas_send(
        "POST",
        f"/api/v1/group_categories/{category_id}/groups",
        {"name": name},
    )


def canvas_add_group_membership(
    group_id: str,
    user_id: str,
    *,
    canvas_send: Callable[..., tuple[dict | None, str | None]],
) -> tuple[bool, str | None]:
    """Add a user to a Canvas group."""
    try:
        r = canvas_send(
            "POST",
            f"/api/v1/groups/{group_id}/memberships",
            {"user_id": user_id},
        )
        if r[1]:
            return False, r[1]
        return True, None
    except Exception as e:  # pragma: no cover - defensive Canvas transport wrapper
        return False, str(e)


def canvas_remove_group_membership(
    group_id: str,
    membership_id: str,
    *,
    canvas_send: Callable[..., tuple[dict | None, str | None]],
) -> tuple[bool, str | None]:
    """Remove a user from a Canvas group by membership ID."""
    try:
        r = canvas_send(
            "DELETE",
            f"/api/v1/groups/{group_id}/memberships/{membership_id}",
            {},
        )
        if r[1]:
            return False, r[1]
        return True, None
    except Exception as e:  # pragma: no cover - defensive Canvas transport wrapper
        return False, str(e)


def get_group_memberships(
    course_id: str,
    group_id: str,
    *,
    canvas_headers: Callable[[], tuple[dict | None, str | None]],
) -> tuple[list[dict], str | None]:
    """Get all memberships for a Canvas group."""
    hdrs, base = canvas_headers()
    if not hdrs:
        return [], "No Canvas token saved"
    try:
        r = requests.get(
            f"{base}/api/v1/groups/{group_id}/memberships",
            headers=hdrs,
            params={"per_page": 200},
            timeout=20,
        )
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}: {r.text[:200]}"
        return r.json() or [], None
    except Exception as e:
        return [], str(e)


def validate_canvas_group_target(
    course_id: str,
    category_id: str,
    target_group_id: str | None,
    *,
    load_group_categories: Callable[[str], tuple[list[dict], str | None, str]],
) -> tuple[list[dict], dict | None, str | None]:
    """Validate a Canvas group category and optional target group for a course."""
    categories, group_err, _ = load_group_categories(course_id)
    if group_err:
        return categories, None, group_err

    category = next((c for c in categories if c.get("category_id") == str(category_id)), None)
    if not category:
        return categories, None, f"Invalid category_id '{category_id}'."

    if target_group_id:
        group_ids = {str(g.get("id")) for g in category.get("groups", [])}
        if str(target_group_id) not in group_ids:
            return categories, category, f"Invalid group_id '{target_group_id}' for category {category_id}."

    return categories, category, None


def update_student_canvas_group(
    course_id: str,
    user_id: str,
    category_id: str,
    target_group_id: str | None,
    *,
    categories: list[dict] | None = None,
    validate_canvas_group_target: Callable[
        [str, str, str | None], tuple[list[dict], dict | None, str | None]
    ],
    canvas_add_group_membership: Callable[[str, str], tuple[bool, str | None]],
    canvas_remove_group_membership: Callable[[str, str], tuple[bool, str | None]],
) -> tuple[bool, str | None]:
    """Update a student's Canvas group membership."""
    if categories is None:
        categories, _, err = validate_canvas_group_target(course_id, category_id, target_group_id)
        if err:
            return False, err
    else:
        category = next((c for c in categories if c.get("category_id") == str(category_id)), None)
        if not category:
            return False, f"Invalid category_id '{category_id}'."
        if target_group_id:
            group_ids = {str(g.get("id")) for g in category.get("groups", [])}
            if str(target_group_id) not in group_ids:
                return False, f"Invalid group_id '{target_group_id}' for category {category_id}."

    user_groups = _user_id_set_from_canvas_groups(categories).get(str(user_id), [])
    groups_in_category = [g for g in user_groups if g.get("category_id") == str(category_id)]

    for g in groups_in_category:
        gid = g.get("group_id")
        mem_id = g.get("membership_id")
        if mem_id:
            ok, err = canvas_remove_group_membership(str(gid), str(mem_id))
            if not ok:
                return False, f"Failed to remove from group {gid}: {err}"

    if target_group_id:
        ok, err = canvas_add_group_membership(str(target_group_id), str(user_id))
        if not ok:
            return False, f"Failed to add to group {target_group_id}: {err}"

    return True, None

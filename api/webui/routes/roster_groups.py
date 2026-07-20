"""Roster group-set and group-label helpers."""

from __future__ import annotations

import json
from collections.abc import Callable

from .roster_helpers import _parse_group_names


def save_group_set_preference(
    course_id: str,
    category_id: str,
    *,
    set_selected_group_category_id: Callable[[str, str | None], None],
) -> dict:
    """Persist the selected Canvas group category for a course."""
    set_selected_group_category_id(course_id, category_id or None)
    return {"ok": True}


def create_group_set(
    course_id: str,
    name: str,
    group_names: str,
    *,
    canvas_send: Callable[[str, str, dict], tuple[dict | None, str | None]],
    create_canvas_group: Callable[[str, str], tuple[dict | None, str | None]],
    set_selected_group_category_id: Callable[[str, str | None], None],
    invalidate_groups: Callable[[str, str, str | None], None],
) -> dict:
    """Create a Canvas group category and optionally seed groups inside it."""
    set_name = (name or "").strip()
    if not set_name:
        return {"ok": False, "error": "Group set name required."}

    names, parse_err = _parse_group_names(group_names)
    if parse_err:
        return {"ok": False, "error": parse_err}

    category, err = canvas_send(
        "POST",
        f"/api/v1/courses/{course_id}/group_categories",
        {"name": set_name},
    )
    if err:
        return {"ok": False, "error": err}

    category_id = str(category.get("id", "") if isinstance(category, dict) else "")
    if not category_id:
        return {"ok": False, "error": "Canvas did not return a group set id."}

    category_name = category.get("name")

    created_groups = []
    for group_name in names:
        group, group_err = create_canvas_group(category_id, group_name)
        if group_err:
            # Unconditional (unlike create_groups's equivalent guard): the
            # category-creation POST above already succeeded unconditionally
            # before this loop started, so a real new category exists in
            # Canvas here regardless of whether zero, some, or all seed
            # groups also succeeded. It must always be reconciled — even a
            # brand-new category with zero groups is real state that must
            # not stay invisible to the mirror.
            invalidate_groups(course_id, category_id, category_name)
            return {
                "ok": False,
                "error": f"Created group set, but failed to create '{group_name}': {group_err}",
                "group_category": category,
                "created_groups": created_groups,
            }
        created_groups.append(group)

    # Reconcile once after the category and every seed group exist in
    # Canvas — not right after category creation, which would merge in a
    # category with zero groups and never get corrected until an unrelated
    # future write touched the same category.
    invalidate_groups(course_id, category_id, category_name)

    set_selected_group_category_id(course_id, category_id)
    return {
        "ok": True,
        "group_category": category,
        "created_groups": created_groups,
    }


def create_groups(
    course_id: str,
    category_id: str,
    group_names: str,
    *,
    validate_canvas_group_target: Callable[
        [str, str, str | None], tuple[list[dict], dict | None, str | None]
    ],
    create_canvas_group: Callable[[str, str], tuple[dict | None, str | None]],
    invalidate_groups: Callable[[str, str], None],
) -> dict:
    """Create Canvas groups inside an existing group category."""
    names, parse_err = _parse_group_names(group_names)
    if parse_err:
        return {"ok": False, "error": parse_err}
    if not names:
        return {"ok": False, "error": "At least one group name required."}

    categories, _, validation_err = validate_canvas_group_target(course_id, category_id, None)
    if validation_err:
        return {"ok": False, "error": validation_err}

    category = next((c for c in categories if c.get("category_id") == str(category_id)), None)
    existing = {
        str(g.get("name", "")).strip().lower()
        for g in (category or {}).get("groups", [])
    }
    for group_name in names:
        if group_name.lower() in existing:
            return {"ok": False, "error": f"Group '{group_name}' already exists."}

    created_groups = []
    for group_name in names:
        group, group_err = create_canvas_group(str(category_id), group_name)
        if group_err:
            # Reconcile whatever was created before the failure — a partial
            # creation must still be reflected, matching today's behavior
            # where each success invalidated immediately.
            if created_groups:
                invalidate_groups(course_id, str(category_id))
            return {
                "ok": False,
                "error": f"Failed to create '{group_name}': {group_err}",
                "created_groups": created_groups,
            }
        created_groups.append(group)

    # Reconcile once after all requested groups are created, not once per
    # group — the whole point of targeted reconciliation is to avoid wasted
    # Canvas traffic for a multi-group creation.
    invalidate_groups(course_id, str(category_id))

    return {"ok": True, "created_groups": created_groups}


def get_group_labels(
    course_id: str,
    *,
    get_roster_group_scheme: Callable[[str], dict],
) -> dict:
    """Return the saved group labels for a course."""
    return {"ok": True, "group_labels": get_roster_group_scheme(course_id).get("group_labels", {})}


def save_group_labels(
    course_id: str,
    labels: str,
    *,
    set_group_labels: Callable[[str, dict], None],
) -> dict:
    """Validate and persist group labels for a course."""
    try:
        parsed = json.loads(labels)
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"Invalid labels JSON: {e}"}
    if not isinstance(parsed, dict):
        return {"ok": False, "error": "labels must be an object."}

    clean = {}
    for group_id, label_info in parsed.items():
        if not isinstance(label_info, dict):
            continue
        teacher_label = str(label_info.get("teacher_label", "") or "").strip()
        meaning = str(label_info.get("meaning", "") or "").strip()
        if teacher_label or meaning:
            clean[str(group_id)] = {"teacher_label": teacher_label, "meaning": meaning}

    set_group_labels(course_id, clean)
    return {"ok": True, "group_labels": clean}

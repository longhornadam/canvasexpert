"""Aggregate roster-warning discovery with no roster-route mutation."""

from __future__ import annotations

from collections import Counter
import os

try:
    import feedback_scrub
except ModuleNotFoundError:  # package-root test/import context
    from api import feedback_scrub
from api.webui import config
from api.webui import workspace
try:
    import feedback_vault
except ModuleNotFoundError:  # package-root test/import context
    from api import feedback_vault
from api.webui.routes.roster_helpers import _compute_warnings

from . import call_canvas_get_all, check_deadline, finding, text


_WARNING_CODES = {
    "missing_pseudonym",
    "extra_time_without_days",
    "group_unset",
    "multiple_groups_in_selected_set",
    "nickname_collision",
    "protected_name_collision",
}


def _groups_from_categories(categories: list[dict]) -> list[dict]:
    groups = []
    for category in categories:
        category_id = text(category.get("id") or category.get("category_id"))
        category_name = text(category.get("name") or category.get("category_name"))
        raw_groups = category.get("groups")
        if not isinstance(raw_groups, list):
            raw_groups = []
        groups.append({
            "category_id": category_id,
            "category_name": category_name,
            "groups": raw_groups,
        })
    return groups


def _fetch_groups(course_id: str, *, deadline, canvas_get_all) -> list[dict]:
    """Read Canvas groups, using the same permission-tolerant shape as Roster."""
    categories = call_canvas_get_all(
        canvas_get_all,
        f"/api/v1/courses/{course_id}/group_categories",
        {"per_page": 50},
        deadline,
    )
    if categories:
        result = []
        for category in categories:
            category_id = text(category.get("id")) if isinstance(category, dict) else ""
            if not category_id:
                continue
            groups = call_canvas_get_all(
                canvas_get_all,
                f"/api/v1/group_categories/{category_id}/groups",
                {"per_page": 100},
                deadline,
            )
            normalized = []
            for group in groups:
                if not isinstance(group, dict):
                    continue
                group_id = text(group.get("id"))
                if not group_id:
                    continue
                memberships = call_canvas_get_all(
                    canvas_get_all,
                    f"/api/v1/groups/{group_id}/memberships",
                    {"per_page": 200},
                    deadline,
                )
                normalized.append({
                    "id": group_id,
                    "name": text(group.get("name")),
                    "memberships": memberships,
                    "student_ids": [
                        item.get("user_id") for item in memberships
                        if isinstance(item, dict) and item.get("user_id") is not None
                    ],
                })
            result.append({
                "category_id": category_id,
                "category_name": text(category.get("name")),
                "groups": normalized,
            })
        return result
    groups = call_canvas_get_all(
        canvas_get_all,
        f"/api/v1/courses/{course_id}/groups",
        {"per_page": 100},
        deadline,
    )
    buckets: dict[str, list[dict]] = {}
    for group in groups:
        if not isinstance(group, dict):
            continue
        category_id = text(group.get("group_category_id")) or "0"
        buckets.setdefault(category_id, []).append(group)
    result = []
    for category_id, raw_groups in sorted(buckets.items()):
        normalized = []
        for group in raw_groups:
            group_id = text(group.get("id"))
            if not group_id:
                continue
            memberships = call_canvas_get_all(
                canvas_get_all,
                f"/api/v1/groups/{group_id}/memberships",
                {"per_page": 200},
                deadline,
            )
            normalized.append({
                "id": group_id,
                "name": text(group.get("name")),
                "memberships": memberships,
                "student_ids": [
                    item.get("user_id") for item in memberships
                    if isinstance(item, dict) and item.get("user_id") is not None
                ],
            })
        result.append({
            "category_id": category_id,
            "category_name": "Group set",
            "groups": normalized,
        })
    return result


def _group_map(categories: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for category in categories:
        category_id = text(category.get("category_id"))
        for group in category.get("groups") or []:
            group_id = text(group.get("id"))
            if not group_id:
                continue
            for user_id in group.get("student_ids") or []:
                result.setdefault(str(user_id), []).append({
                    "category_id": category_id,
                    "category_name": text(category.get("category_name")),
                    "group_id": group_id,
                    "group_name": text(group.get("name")),
                })
    return result


def _vault_context() -> tuple[dict, set[str], dict]:
    try:
        private_root = workspace.feedback_folder("_vault")
        vault_entries = feedback_vault.Vault(os.path.join(private_root, "vault.json")).entries() if private_root else []
    except Exception:
        vault_entries = []
    by_id = {text(item.get("canvas_id")): item for item in vault_entries if isinstance(item, dict)}
    try:
        protected = {text(value).casefold() for value in config.active_protected_names()}
    except Exception:
        protected = set()
    try:
        collisions = feedback_scrub.find_collisions(vault_entries, protected)
    except Exception:
        collisions = {"literary": [], "dup_first": [], "common_word": []}
    return by_id, protected, collisions


def scan_course(course_id: str, *, now, deadline, canvas_get_all) -> list[dict]:
    check_deadline(deadline)
    users = call_canvas_get_all(
        canvas_get_all,
        f"/api/v1/courses/{course_id}/users",
        {"enrollment_type[]": "student", "include[]": "enrollments", "per_page": 100},
        deadline,
    )
    categories = _fetch_groups(course_id, deadline=deadline, canvas_get_all=canvas_get_all)
    group_map = _group_map(categories)
    selected_category = None
    try:
        selected_category = text(config.get_roster_group_scheme(course_id).get("selected_group_category_id"))
    except Exception:
        selected_category = ""
    if not selected_category and categories:
        selected_category = text(categories[0].get("category_id"))
    extra_time = {
        text(item.get("id")): {
            "enabled": True,
            "days": item.get("days", 0),
        }
        for item in config.get_extra_time(course_id)
        if isinstance(item, dict) and text(item.get("id"))
    }
    vault_by_id, protected, collisions = _vault_context()
    counts = Counter()
    for user in users:
        if not isinstance(user, dict) or user.get("id") is None:
            continue
        user_id = str(user.get("id"))
        groups = group_map.get(user_id, [])
        selected_groups = [item for item in groups if item.get("category_id") == selected_category]
        selected_group = selected_groups[0] if selected_groups else None
        student = {
            "id": user_id,
            "extra_time": extra_time.get(user_id, {"enabled": False, "days": 0}),
            "canvas_group": selected_group,
            "canvas_groups": groups,
        }
        warnings = _compute_warnings(
            student,
            vault_by_id,
            protected,
            collisions,
            selected_category_id=selected_category or None,
        )
        counts.update(code for code in warnings if code in _WARNING_CODES)
    output = []
    for warning_code in sorted(counts):
        amount = counts[warning_code]
        output.append(finding(
            kind="roster.warning",
            course_id=str(course_id),
            counts={"total": amount, "pending": amount, "affected": amount},
            now=now,
            title="Roster warning",
            resumable_url=f"/roster?course_id={course_id}",
            source_suffix=warning_code,
        ))
    return output


__all__ = ["scan_course"]

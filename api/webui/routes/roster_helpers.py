"""Pure roster normalization helpers."""

from __future__ import annotations

import json
import re as _re

from api.platform_services import config


def _enrollment_section_ids(users: list[dict]) -> dict:
    """Return {user_id_str: [section_id_str, ...]} from enrollments."""
    result = {}
    for u in (users or []):
        uid = str(u["id"])
        secs = set()
        for enrollment in (u.get("enrollments") or []):
            sec_id = enrollment.get("course_section_id")
            if sec_id:
                secs.add(str(sec_id))
        if secs:
            result[uid] = sorted(secs)
    return result


def _resolve_tier_display(course_id: str, tier_id: str | None,
                           tier_scheme: list[dict] | None = None) -> dict:
    """Return {tier_id, tier_label, tier_alias, tier_display} for a student."""
    tid = tier_id or ""
    if tier_scheme is None:
        tier_scheme = config.get_roster_tier_scheme(course_id)
    label = ""
    alias = ""
    for t in tier_scheme:
        if t["id"] == tid:
            label = t.get("teacher_label", "")
            alias = t.get("alias", "")
            break
    display = f"{label} / {alias}" if label and alias else (label or alias or "")
    return {
        "tier_id": tid,
        "tier_label": label,
        "tier_alias": alias,
        "tier_display": display,
    }


def _compute_warnings(student: dict, vault_entries_by_id: dict,
                      protected_names: set[str], collisions: dict,
                      selected_category_id: str | None = None,
                      roster_change: dict | None = None) -> list[str]:
    """Return warning string codes for one student row.

    ``roster_change`` is this student's entry (if any) from
    ``api.roster_context.diff_roster_baseline`` against the teacher's last
    acknowledged roster -- ``{"is_new": True}`` or
    ``{"changed_section": <detail>}``. A departed student has no live row to
    attach a warning to, so that code is reported by the caller directly.
    """
    warnings: list[str] = []
    cid = student["id"]

    vault_entry = vault_entries_by_id.get(cid, {})
    pseudo = vault_entry.get("pseudonym", "")
    if not pseudo or pseudo.startswith("S0"):
        warnings.append("missing_pseudonym")

    et = student.get("extra_time", {})
    if et.get("enabled") and not (et.get("days") and int(et.get("days", 0)) > 0):
        warnings.append("extra_time_without_days")

    canvas_group = student.get("canvas_group") or {}
    if selected_category_id and not canvas_group.get("group_id"):
        warnings.append("group_unset")

    canvas_groups = student.get("canvas_groups", [])
    if selected_category_id:
        groups_in_selected = [g for g in canvas_groups if g.get("category_id") == selected_category_id]
        if len(groups_in_selected) > 1:
            warnings.append("multiple_groups_in_selected_set")

    nicknames = vault_entry.get("nicknames", [])
    for nn in nicknames:
        if nn.lower() in protected_names:
            warnings.append("protected_name_collision")
            break

    if vault_entry:
        if collisions.get("literary"):
            for lit in collisions["literary"]:
                if vault_entry.get("real_name", "").lower() in lit.lower():
                    warnings.append("protected_name_collision")
                    break
        for bucket in ("dup_first", "common_word"):
            for item in collisions.get(bucket, []):
                if vault_entry.get("real_name", "").lower() in item.lower():
                    warnings.append("nickname_collision")
                    break

    if roster_change:
        if roster_change.get("is_new"):
            warnings.append("student_added")
        if roster_change.get("changed_section"):
            warnings.append("student_changed_section")

    return list(dict.fromkeys(warnings))


def _as_int(value, field_name: str) -> tuple[int | None, str | None]:
    """Best-effort int parsing for form JSON values."""
    try:
        return int(value), None
    except (TypeError, ValueError):
        return None, f"{field_name} must be an integer."


def _value_name(value: dict | None, user_id: str) -> str:
    """Return a per-user display name from a bulk value payload."""
    if not isinstance(value, dict):
        return ""
    names = value.get("names")
    if isinstance(names, dict):
        return str(names.get(str(user_id), "") or "")
    return str(value.get("name", "") or "")


def _parse_group_names(raw: str) -> tuple[list[str], str | None]:
    """Parse a JSON array or newline/comma separated group-name list."""
    raw = (raw or "").strip()
    if not raw:
        return [], None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = [part.strip() for part in _re.split(r"[\r\n,]+", raw)]
    if not isinstance(parsed, list):
        return [], "group_names must be a list or separated text."

    names: list[str] = []
    seen: set[str] = set()
    for item in parsed:
        name = str(item or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            return [], f"Duplicate group name '{name}'."
        seen.add(key)
        names.append(name)
    return names, None


def _user_id_set_from_canvas_groups(categories: list[dict]) -> dict:
    """Return {user_id_str: [group_info, ...]} from categories.

    Each group_info includes: category_id, category_name, group_id, group_name,
    and optionally membership_id (from Canvas membership response).
    """
    result: dict[str, list[dict]] = {}
    for cat in categories:
        cat_id = cat.get("category_id", "")
        cat_name = cat.get("category_name", "")
        for grp in cat.get("groups", []):
            gid = grp.get("id", "")
            gname = grp.get("name", "")
            memberships = grp.get("memberships", [])
            for sid in grp.get("student_ids", []):
                sid_str = str(sid)
                result.setdefault(sid_str, []).append({
                    "category_id": cat_id,
                    "category_name": cat_name,
                    "group_id": gid,
                    "group_name": gname,
                    "membership_id": None,
                })
            for mem in memberships:
                mem_user_id = str(mem.get("user_id", ""))
                if mem_user_id:
                    for gi in result.get(mem_user_id, []):
                        if gi["group_id"] == gid:
                            gi["membership_id"] = mem.get("id")
    return result


def _compute_canvas_group_display(course_id: str, group_id: str | None, group_name: str | None) -> dict:
    """Compute Canvas group display info for a student row."""
    if not group_id or not group_name:
        return {
            "category_id": None,
            "category_name": None,
            "group_id": None,
            "group_name": None,
            "teacher_label": None,
            "display": None,
        }
    group_label = config.get_group_label(course_id, group_id)
    teacher_label = group_label.get("teacher_label") if group_label else None
    display = config.compute_group_display(teacher_label, group_name)
    return {
        "category_id": None,
        "category_name": None,
        "group_id": group_id,
        "group_name": group_name,
        "teacher_label": teacher_label,
        "display": display,
    }


def _annotate_group_labels(course_id: str, categories: list[dict]) -> None:
    """Attach teacher labels/display text to Canvas group objects in-place."""
    for cat in categories:
        for group in cat.get("groups", []):
            group_id = str(group.get("id", ""))
            group_name = group.get("name", "")
            saved = config.get_group_label(course_id, group_id) or {}
            teacher_label = saved.get("teacher_label") or config.default_group_label(group_name)
            meaning = saved.get("meaning", "")
            if teacher_label:
                group["teacher_label"] = teacher_label
                group["display"] = config.compute_group_display(teacher_label, group_name)
            else:
                group["teacher_label"] = None
                group["display"] = group_name
            if meaning:
                group["meaning"] = meaning

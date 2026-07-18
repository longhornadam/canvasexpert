"""Roster student and bulk update helpers with injected route dependencies."""

from __future__ import annotations

import json
from collections.abc import Callable


def update_student(
    course_id: str,
    user_id: str,
    patch: str,
    *,
    vault_factory: Callable[[], object],
    get_extra_time: Callable[[str], list[dict]],
    set_extra_time: Callable[[str, list[dict]], None],
    set_monitored_student: Callable[..., None],
    remove_monitored_student: Callable[[str], None],
    as_int: Callable[[object, str], tuple[int | None, str | None]],
    validate_canvas_group_target: Callable[
        [str, str, str | None], tuple[list[dict], dict | None, str | None]
    ],
    update_student_canvas_group: Callable[
        [str, str, str, str | None, list[dict] | None], tuple[bool, str | None]
    ],
    invalidate_groups: Callable[[str], None],
    allowed_keys: set[str],
    obsolete_keys: set[str],
) -> dict:
    """Validate and apply one student's roster update."""
    if not course_id or not user_id:
        return {"ok": False, "error": "course_id and user_id required."}

    try:
        data = json.loads(patch)
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"Invalid patch JSON: {e}"}
    if not isinstance(data, dict):
        return {"ok": False, "error": "patch must be a JSON object."}

    obsolete = set(data.keys()) & obsolete_keys
    if obsolete:
        return {
            "ok": False,
            "error": (
                "Local tier/group assignment is obsolete; update canvas_group instead. "
                f"Rejected keys: {sorted(obsolete)}"
            ),
        }

    unknown = set(data.keys()) - allowed_keys
    if unknown:
        return {"ok": False, "error": f"Unknown patch keys: {sorted(unknown)}"}

    vault = vault_factory()

    with vault.transaction():
        if "nicknames" in data:
            nns = data["nicknames"]
            if not isinstance(nns, list):
                return {"ok": False, "error": "nicknames must be a list."}
            vault.set_nicknames(user_id, nns)

        if "pseudonym" in data:
            p = data["pseudonym"]
            if not isinstance(p, dict) or "first" not in p or "last" not in p:
                return {"ok": False, "error": "pseudonym must be {first, last}."}
            vault.set_pseudonym(user_id, p["first"], p["last"])

        if data.get("regenerate_pseudonym"):
            vault.regenerate_pseudonym(user_id)

    if "extra_time" in data:
        et = data["extra_time"]
        if not isinstance(et, dict):
            return {"ok": False, "error": "extra_time must be an object."}
        et_list = get_extra_time(course_id)
        et_list = [e for e in et_list if e.get("id") != user_id]
        if et.get("enabled"):
            days, err = as_int(et.get("days", 0), "extra_time.days")
            if err:
                return {"ok": False, "error": err}
            et_list.append({
                "id": user_id,
                "name": et.get("name", ""),
                "days": days,
            })
        set_extra_time(course_id, et_list)

    if "monitored" in data:
        m = data["monitored"]
        if not isinstance(m, dict):
            return {"ok": False, "error": "monitored must be an object."}
        if m.get("enabled"):
            set_monitored_student(
                user_id,
                name=m.get("name", ""),
                note=m.get("note", ""),
            )
        else:
            remove_monitored_student(user_id)

    if "canvas_group" in data:
        cg = data["canvas_group"]
        if not isinstance(cg, dict):
            return {"ok": False, "error": "canvas_group must be an object."}

        category_id = cg.get("category_id")
        group_id = cg.get("group_id")
        if not category_id:
            return {"ok": False, "error": "canvas_group.category_id required."}

        target_group_id = None if not group_id else str(group_id)
        categories, _, validation_err = validate_canvas_group_target(
            course_id, category_id, target_group_id
        )
        if validation_err:
            return {"ok": False, "error": validation_err}

        ok, err = update_student_canvas_group(
            course_id, user_id, category_id, target_group_id, categories
        )
        if not ok:
            return {"ok": False, "error": err}
        invalidate_groups(course_id)

    return {"ok": True}


def update_bulk(
    course_id: str,
    user_ids: str,
    action: str,
    value: str,
    *,
    get_extra_time: Callable[[str], list[dict]],
    set_extra_time: Callable[[str, list[dict]], None],
    set_monitored_student: Callable[..., None],
    remove_monitored_student: Callable[[str], None],
    as_int: Callable[[object, str], tuple[int | None, str | None]],
    value_name: Callable[[dict | None, str], str],
    validate_canvas_group_target: Callable[
        [str, str, str | None], tuple[list[dict], dict | None, str | None]
    ],
    update_student_canvas_group: Callable[
        [str, str, str, str | None, list[dict] | None], tuple[bool, str | None]
    ],
    invalidate_groups: Callable[[str], None],
) -> dict:
    """Apply a bulk roster action."""
    if not course_id or not user_ids or not action:
        return {"ok": False, "error": "course_id, user_ids, and action required."}

    try:
        ids = json.loads(user_ids)
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"Invalid user_ids JSON: {e}"}

    if not isinstance(ids, list) or not ids:
        return {"ok": False, "error": "user_ids must be a non-empty list."}

    try:
        val = json.loads(value) if (value or "").strip() else None
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"Invalid value JSON: {e}"}

    updated = 0
    failed = 0
    errors: list[str] = []
    group_membership_changed = False

    if action == "set_extra_time":
        if not isinstance(val, dict):
            return {"ok": False, "error": "set_extra_time requires value object."}
        days, err = as_int(val.get("days", 0), "days")
        if err:
            return {"ok": False, "error": err}
        et_list = get_extra_time(course_id)
        existing_ids = {str(e["id"]) for e in et_list}
        for uid in ids:
            uid_str = str(uid)
            if uid_str not in existing_ids:
                et_list.append({"id": uid_str, "name": value_name(val, uid_str), "days": days})
            else:
                for e in et_list:
                    if str(e["id"]) == uid_str:
                        e["days"] = days
                        name = value_name(val, uid_str)
                        if name:
                            e["name"] = name
            updated += 1
        set_extra_time(course_id, et_list)

    elif action == "clear_extra_time":
        et_list = get_extra_time(course_id)
        id_set = {str(uid) for uid in ids}
        et_list = [e for e in et_list if str(e.get("id", "")) not in id_set]
        set_extra_time(course_id, et_list)
        updated = len(ids)

    elif action == "set_canvas_group":
        if not isinstance(val, dict):
            return {"ok": False, "error": "set_canvas_group requires value object."}
        category_id = val.get("category_id")
        group_id = val.get("group_id")
        if not category_id:
            return {"ok": False, "error": "set_canvas_group requires category_id."}
        categories, _, validation_err = validate_canvas_group_target(
            course_id, category_id, str(group_id) if group_id else None
        )
        if validation_err:
            return {"ok": False, "error": validation_err}
        for uid in ids:
            ok, err = update_student_canvas_group(
                course_id, str(uid), category_id, str(group_id) if group_id else None, categories
            )
            if ok:
                updated += 1
                group_membership_changed = True
            else:
                failed += 1
                errors.append(f"User {uid}: {err}")

    elif action == "clear_canvas_group":
        if not isinstance(val, dict):
            return {"ok": False, "error": "clear_canvas_group requires value object."}
        category_id = val.get("category_id")
        if not category_id:
            return {"ok": False, "error": "clear_canvas_group requires category_id."}
        categories, _, validation_err = validate_canvas_group_target(course_id, category_id, None)
        if validation_err:
            return {"ok": False, "error": validation_err}
        for uid in ids:
            ok, err = update_student_canvas_group(course_id, str(uid), category_id, None, categories)
            if ok:
                updated += 1
                group_membership_changed = True
            else:
                failed += 1
                errors.append(f"User {uid}: {err}")

    elif action in ("set_tier", "clear_tier", "set_planned_group", "clear_planned_group"):
        return {
            "ok": False,
            "error": f"'{action}' is obsolete in V3; use set_canvas_group or clear_canvas_group.",
        }

    elif action in ("set_monitored", "clear_monitored"):
        is_set = action == "set_monitored"
        for uid in ids:
            uid_str = str(uid)
            if is_set:
                set_monitored_student(uid_str, name=value_name(val, uid_str) or uid_str, note="")
            else:
                remove_monitored_student(uid_str)
            updated += 1

    else:
        return {"ok": False, "error": f"Unknown action '{action}'."}

    if group_membership_changed:
        invalidate_groups(course_id)

    result = {"ok": True, "updated": updated}
    if failed > 0:
        result["failed"] = failed
        result["errors"] = errors[:5]
        if updated > 0:
            result["message"] = f"Updated {updated}; failed {failed}."
        else:
            result["ok"] = False
            result["error"] = f"All {failed} updates failed: " + "; ".join(errors[:3])

    return result

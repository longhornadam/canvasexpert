"""Roster Console API — unified student-level settings surface.

Prefix: /api/roster

Routes:
    GET  /api/roster          — full roster merge (students + vault + settings + groups)
    POST /api/roster/student  — update one student's settings
    POST /api/roster/bulk     — bulk action on many students
    GET  /api/roster/tier-scheme  — get course tier scheme
    POST /api/roster/tier-scheme  — save course tier scheme

V3: Canvas groups are the source of truth for tier/group assignment.
Does NOT write local tier_id.
"""
import json
import re as _re

from fastapi import APIRouter, Form, Query
from fastapi.responses import JSONResponse

import feedback_scrub
from .. import config
from ..canvas_client import _canvas_get_all, _canvas_send
from .courses import load_group_categories
from .names import _fetch_students, _upsert_roster, _vault

router = APIRouter(prefix="/api/roster", tags=["roster"])

# V3: Canvas group-backed keys only
ALLOWED_STUDENT_PATCH_KEYS = {
    "nicknames", "pseudonym", "regenerate_pseudonym",
    "extra_time", "monitored", "canvas_group",
}

# Legacy keys that are rejected with clear errors
OBSOLETE_PATCH_KEYS = {"tier_id", "tier", "planned_group"}

WARNING_CODES = (
    "missing_pseudonym", "extra_time_without_days",
    "group_unset", "multiple_groups_in_selected_set",
    "nickname_collision", "protected_name_collision",
)


def _fetch_sections(course_id: str) -> dict:
    """Return {section_id: section_name} for a course."""
    sections, err = _canvas_get_all(
        f"/api/v1/courses/{course_id}/sections", {"per_page": 100})
    if err or not sections:
        return {}
    return {str(s["id"]): s.get("name", f"Section {s['id']}") for s in sections}


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
    if tier_id:
        tid = tier_id
    else:
        tid = ""
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
                       selected_category_id: str | None = None) -> list[str]:
    """Return warning string codes for one student row."""
    warnings: list[str] = []
    cid = student["id"]

    vault_entry = vault_entries_by_id.get(cid, {})
    pseudo = vault_entry.get("pseudonym", "")
    if not pseudo or pseudo.startswith("S0"):
        warnings.append("missing_pseudonym")

    et = student.get("extra_time", {})
    if et.get("enabled") and not (et.get("days") and int(et.get("days", 0)) > 0):
        warnings.append("extra_time_without_days")

    # V3: Check for group_unset or multiple_groups_in_selected_set
    canvas_group = student.get("canvas_group", {})
    if selected_category_id and not canvas_group.get("group_id"):
        warnings.append("group_unset")

    # Check if student is in multiple groups in the selected set
    canvas_groups = student.get("canvas_groups", [])
    if selected_category_id:
        groups_in_selected = [g for g in canvas_groups if g.get("category_id") == selected_category_id]
        if len(groups_in_selected) > 1:
            warnings.append("multiple_groups_in_selected_set")

    # Nickname collisions
    nicknames = vault_entry.get("nicknames", [])
    for nn in nicknames:
        if nn.lower() in protected_names:
            warnings.append("protected_name_collision")
            break

    # Check current-course vault entries for duplicate/common/protected collisions.
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


# --------------------------------------------------------------------------
# Canvas Group Membership Helpers (V3)
# --------------------------------------------------------------------------

def canvas_add_group_membership(group_id: str, user_id: str) -> tuple[bool, str | None]:
    """Add a user to a Canvas group.

    Returns (success, error_message).
    Canvas endpoint: POST /api/v1/groups/{group_id}/memberships
    """
    try:
        r = _canvas_send(
            "POST",
            f"/api/v1/groups/{group_id}/memberships",
            {"user_id": user_id},
        )
        if r[1]:
            return False, r[1]
        return True, None
    except Exception as e:
        return False, str(e)


def canvas_remove_group_membership(group_id: str, membership_id: str) -> tuple[bool, str | None]:
    """Remove a user from a Canvas group by membership ID.

    Returns (success, error_message).
    Canvas endpoint: DELETE /api/v1/groups/{group_id}/memberships/{membership_id}
    """
    try:
        r = _canvas_send(
            "DELETE",
            f"/api/v1/groups/{group_id}/memberships/{membership_id}",
            {},
        )
        if r[1]:
            return False, r[1]
        return True, None
    except Exception as e:
        return False, str(e)


def _get_group_memberships(course_id: str, group_id: str) -> tuple[list[dict], str | None]:
    """Get all memberships for a Canvas group."""
    hdrs, base = _canvas_get_all.__wrapped__.__self__._canvas_headers() if hasattr(_canvas_get_all, '__wrapped__') else (None, None)
    import requests
    from ..canvas_client import _canvas_headers
    hdrs, base = _canvas_headers()
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


def _update_student_canvas_group(course_id: str, user_id: str, category_id: str, target_group_id: str | None) -> tuple[bool, str | None]:
    """Update a student's Canvas group membership.

    1. Remove from all groups in the category.
    2. Add to target group if specified.
    Returns (success, error_message).
    """
    # Get all groups in the category
    categories, _, _ = load_group_categories(course_id)
    category = next((c for c in categories if c.get("category_id") == str(category_id)), None)
    if not category:
        return False, f"Group category {category_id} not found"

    # Get current memberships for this user in this category
    user_groups = _user_id_set_from_canvas_groups(categories).get(str(user_id), [])
    groups_in_category = [g for g in user_groups if g.get("category_id") == str(category_id)]

    # Remove from all groups in the category
    for g in groups_in_category:
        gid = g.get("group_id")
        mem_id = g.get("membership_id")
        if mem_id:
            ok, err = canvas_remove_group_membership(gid, mem_id)
            if not ok:
                return False, f"Failed to remove from group {gid}: {err}"

    # Add to target group if specified
    if target_group_id:
        ok, err = canvas_add_group_membership(str(target_group_id), str(user_id))
        if not ok:
            return False, f"Failed to add to group {target_group_id}: {err}"

    return True, None


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
            # Include membership_id if present (for Canvas writes)
            memberships = grp.get("memberships", [])
            for sid in grp.get("student_ids", []):
                sid_str = str(sid)
                result.setdefault(sid_str, []).append({
                    "category_id": cat_id,
                    "category_name": cat_name,
                    "group_id": gid,
                    "group_name": gname,
                    "membership_id": None,  # Will be populated if Canvas returns it
                })
            # Also index by membership if available
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
        "category_id": None,  # Will be filled by caller
        "category_name": None,
        "group_id": group_id,
        "group_name": group_name,
        "teacher_label": teacher_label,
        "display": display,
    }


@router.get("")
def roster_get(course_id: str = Query("")):
    """Full roster merge for one course (V3: Canvas groups are source of truth).

    1. Fetch students from Canvas + upsert into vault.
    2. Fetch sections and groups.
    3. Merge vault entries, extra-time, monitored, and Canvas group assignments.
    4. Return unified rows with counts, warnings, and group scheme.
    """
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})

    vault = _vault()
    users, err = _fetch_students(course_id)
    if err:
        return JSONResponse({"ok": False, "error": f"Canvas fetch failed: {err}"})

    _upsert_roster(vault, users)

    # Sections
    section_map = _fetch_sections(course_id)
    enrollment_secs = _enrollment_section_ids(users)

    # Groups (V3: now used for tier/group assignment)
    categories, group_err, group_msg = load_group_categories(course_id)
    user_groups = _user_id_set_from_canvas_groups(categories)

    # Determine selected group category
    group_scheme = config.get_roster_group_scheme(course_id)
    selected_category_id = group_scheme.get("selected_group_category_id")

    # If no saved preference, try to find a likely differentiation group set
    if not selected_category_id and categories:
        likely_names = ("tier", "differentiation", "diff", "level", "groups")
        for cat in categories:
            cat_name = cat.get("category_name", "").lower()
            if any(name in cat_name for name in likely_names):
                selected_category_id = cat.get("category_id")
                break
        if not selected_category_id and categories:
            selected_category_id = categories[0].get("category_id")

    # Extra time
    extra_time_list = config.get_extra_time(course_id)
    extra_time_by_id: dict[str, dict] = {}
    for et in extra_time_list:
        extra_time_by_id[et.get("id", "")] = {"enabled": True, "days": et.get("days", 0)}

    # Monitored
    monitored = config.get_monitored_students()

    # Protected names for collision check
    protected_names = {p.lower() for p in config.active_protected_names()}

    # Build vault lookup by canvas_id
    vault_entries_list = vault.entries()
    vault_by_id: dict[str, dict] = {}
    for ve in vault_entries_list:
        vault_by_id[ve["canvas_id"]] = ve
    course_ids = {str(u["id"]) for u in (users or [])}
    course_vault_entries = [ve for ve in vault_entries_list
                            if str(ve.get("canvas_id", "")) in course_ids]
    collisions = feedback_scrub.find_collisions(course_vault_entries, protected_names)

    # Build rows
    students_out = []
    name_order_map = {}
    for u in (users or []):
        uid = str(u["id"])
        sortable = u.get("sortable_name") or u.get("name", "")
        display = u.get("name") or sortable
        short = u.get("short_name") or ""

        # Vault entry
        ve = vault_by_id.get(uid, {})

        # Sections
        sec_ids = enrollment_secs.get(uid, [])
        sections = [{"id": sid, "name": section_map.get(sid, f"Section {sid}")}
                    for sid in sec_ids]

        # Extra time
        et = extra_time_by_id.get(uid, {"enabled": False, "days": 0})

        # Monitored
        mon = monitored.get(uid, {})
        monitored_flag = bool(mon)
        monitored_note = mon.get("note", "") if mon else ""

        # Canvas groups (V3: source of truth)
        canvas_groups = user_groups.get(uid, [])

        # Find the student's group in the selected category
        canvas_group_info = None
        if selected_category_id:
            for g in canvas_groups:
                if g.get("category_id") == str(selected_category_id):
                    canvas_group_info = g
                    break

        # Build canvas_group field for the row
        canvas_group = None
        if canvas_group_info:
            canvas_group = {
                "category_id": canvas_group_info.get("category_id"),
                "category_name": canvas_group_info.get("category_name"),
                "group_id": canvas_group_info.get("group_id"),
                "group_name": canvas_group_info.get("group_name"),
                "teacher_label": config.get_group_label(course_id, canvas_group_info.get("group_id", {})).get("teacher_label") if config.get_group_label(course_id, canvas_group_info.get("group_id", {})) else None,
                "display": None,
            }
            if canvas_group_info.get("group_id"):
                label = config.get_group_label(course_id, canvas_group_info["group_id"])
                teacher_label = label.get("teacher_label") if label else None
                canvas_group["teacher_label"] = teacher_label
                canvas_group["display"] = config.compute_group_display(
                    teacher_label, canvas_group_info.get("group_name", ""))

        # Nicknames from vault
        nicknames = ve.get("nicknames", [])

        row = {
            "id": uid,
            "canvas_id": uid,
            "name": sortable,
            "display_name": display,
            "short_name": short,
            "sections": sections,
            "nicknames": nicknames,
            "pseudonym": ve.get("pseudonym", ""),
            "pseudo_first": ve.get("pseudo_first", ""),
            "pseudo_last": ve.get("pseudo_last", ""),
            "extra_time": et,
            "monitored": {"enabled": monitored_flag, "note": monitored_note},
            "canvas_groups": canvas_groups,
            "canvas_group": canvas_group,
            "warnings": [],
        }
        row["warnings"] = _compute_warnings(
            row, vault_by_id, protected_names, collisions, selected_category_id)
        students_out.append(row)
        name_order_map[uid] = (sortable or display).lower()

    students_out.sort(key=lambda s: name_order_map.get(s["id"], s["name"].lower()))

    # Counts
    total = len(students_out)
    extra_time_count = sum(1 for s in students_out if s["extra_time"]["enabled"])
    monitored_count = sum(1 for s in students_out if s["monitored"]["enabled"])
    group_unset_count = sum(1 for s in students_out if not s.get("canvas_group", {}).get("group_id"))
    warning_count = sum(1 for s in students_out if s["warnings"])

    note = ""
    if group_err:
        note = f"Groups: {group_err}"
    elif group_msg:
        note = group_msg

    # Check for legacy tier assignments
    legacy_tier_count = 0
    raw_roster_settings = config.get_roster_student_settings(course_id)
    for uid, local in raw_roster_settings.items():
        if local.get("tier_id") or local.get("tier") or local.get("planned_group"):
            legacy_tier_count += 1

    return JSONResponse({
        "ok": True,
        "students": students_out,
        "groups": categories,
        "selected_group_category_id": selected_category_id,
        "group_label_scheme": group_scheme.get("group_labels", {}),
        "counts": {
            "total": total,
            "extra_time": extra_time_count,
            "monitored": monitored_count,
            "group_unset": group_unset_count,
            "warnings": warning_count,
        },
        "note": note or None,
        "legacy_tier_count": legacy_tier_count if legacy_tier_count > 0 else None,
    })


@router.post("/student")
def roster_student_update(
    course_id: str = Form(...),
    user_id: str = Form(...),
    patch: str = Form(...),
):
    """Update one student's roster settings (V3: Canvas groups are source of truth).

    Accepted patch fields: nicknames, pseudonym, regenerate_pseudonym,
    extra_time, monitored, canvas_group.

    Obsolete fields (rejected with clear error): tier_id, tier, planned_group.
    """
    if not course_id or not user_id:
        return JSONResponse({"ok": False, "error": "course_id and user_id required."})

    try:
        data = json.loads(patch)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"Invalid patch JSON: {e}"})
    if not isinstance(data, dict):
        return JSONResponse({"ok": False, "error": "patch must be a JSON object."})

    # Reject obsolete keys
    obsolete = set(data.keys()) & OBSOLETE_PATCH_KEYS
    if obsolete:
        return JSONResponse({
            "ok": False,
            "error": f"Local tier/group assignment is obsolete; update canvas_group instead. "
                     f"Rejected keys: {sorted(obsolete)}"
        })

    # Validate keys
    unknown = set(data.keys()) - ALLOWED_STUDENT_PATCH_KEYS
    if unknown:
        return JSONResponse({"ok": False, "error": f"Unknown patch keys: {sorted(unknown)}"})

    vault = _vault()

    # --- Nicknames ---
    if "nicknames" in data:
        nns = data["nicknames"]
        if not isinstance(nns, list):
            return JSONResponse({"ok": False, "error": "nicknames must be a list."})
        vault.set_nicknames(user_id, nns)
        vault.save()

    # --- Pseudonym ---
    if "pseudonym" in data:
        p = data["pseudonym"]
        if not isinstance(p, dict) or "first" not in p or "last" not in p:
            return JSONResponse({"ok": False, "error": "pseudonym must be {first, last}."})
        vault.set_pseudonym(user_id, p["first"], p["last"])
        vault.save()

    if data.get("regenerate_pseudonym"):
        vault.regenerate_pseudonym(user_id)
        vault.save()

    # --- Extra time ---
    if "extra_time" in data:
        et = data["extra_time"]
        if not isinstance(et, dict):
            return JSONResponse({"ok": False, "error": "extra_time must be an object."})
        et_list = config.get_extra_time(course_id)
        et_list = [e for e in et_list if e.get("id") != user_id]
        if et.get("enabled"):
            days, err = _as_int(et.get("days", 0), "extra_time.days")
            if err:
                return JSONResponse({"ok": False, "error": err})
            et_list.append({
                "id": user_id,
                "name": et.get("name", ""),
                "days": days,
            })
        config.set_extra_time(course_id, et_list)

    # --- Monitored ---
    if "monitored" in data:
        m = data["monitored"]
        if not isinstance(m, dict):
            return JSONResponse({"ok": False, "error": "monitored must be an object."})
        if m.get("enabled"):
            config.set_monitored_student(
                user_id,
                name=m.get("name", ""),
                note=m.get("note", ""),
            )
        else:
            config.remove_monitored_student(user_id)

    # --- Canvas Group (V3: writes to Canvas) ---
    if "canvas_group" in data:
        cg = data["canvas_group"]
        if not isinstance(cg, dict):
            return JSONResponse({"ok": False, "error": "canvas_group must be an object."})

        category_id = cg.get("category_id")
        group_id = cg.get("group_id")  # None or empty string means clear

        if not category_id:
            return JSONResponse({"ok": False, "error": "canvas_group.category_id required."})

        # Validate category exists
        categories, _, _ = load_group_categories(course_id)
        if not any(c.get("category_id") == str(category_id) for c in categories):
            return JSONResponse({"ok": False, "error": f"Invalid category_id '{category_id}'."})

        # If clearing or setting a group, update Canvas
        target_group_id = None if not group_id else str(group_id)

        # Validate group belongs to category if specified
        if target_group_id:
            category = next((c for c in categories if c.get("category_id") == str(category_id)), None)
            if category:
                group_ids = [g.get("id") for g in category.get("groups", [])]
                if target_group_id not in group_ids:
                    return JSONResponse({"ok": False, "error": f"Invalid group_id '{group_id}' for category {category_id}."})

        ok, err = _update_student_canvas_group(course_id, user_id, category_id, target_group_id)
        if not ok:
            return JSONResponse({"ok": False, "error": err})

    return JSONResponse({"ok": True})


@router.post("/bulk")
def roster_bulk_update(
    course_id: str = Form(...),
    user_ids: str = Form(...),
    action: str = Form(...),
    value: str = Form(""),
):
    """Bulk action on many students (V3: Canvas groups are source of truth).

    V3 supported actions: set_extra_time, clear_extra_time, set_canvas_group,
    clear_canvas_group, set_monitored, clear_monitored.

    Legacy actions (rejected): set_tier, clear_tier, set_planned_group, clear_planned_group.
    """
    if not course_id or not user_ids or not action:
        return JSONResponse({"ok": False, "error": "course_id, user_ids, and action required."})

    try:
        ids = json.loads(user_ids)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"Invalid user_ids JSON: {e}"})

    if not isinstance(ids, list) or not ids:
        return JSONResponse({"ok": False, "error": "user_ids must be a non-empty list."})

    try:
        val = json.loads(value) if value.strip() else None
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"Invalid value JSON: {e}"})

    updated = 0
    failed = 0
    errors = []

    if action == "set_extra_time":
        if not isinstance(val, dict):
            return JSONResponse({"ok": False, "error": "set_extra_time requires value object."})
        days, err = _as_int(val.get("days", 0), "days")
        if err:
            return JSONResponse({"ok": False, "error": err})
        et_list = config.get_extra_time(course_id)
        existing_ids = {str(e["id"]) for e in et_list}
        for uid in ids:
            uid_str = str(uid)
            if uid_str not in existing_ids:
                et_list.append({"id": uid_str, "name": _value_name(val, uid_str), "days": days})
            else:
                for e in et_list:
                    if str(e["id"]) == uid_str:
                        e["days"] = days
                        name = _value_name(val, uid_str)
                        if name:
                            e["name"] = name
            updated += 1
        config.set_extra_time(course_id, et_list)

    elif action == "clear_extra_time":
        et_list = config.get_extra_time(course_id)
        id_set = {str(uid) for uid in ids}
        et_list = [e for e in et_list if str(e.get("id", "")) not in id_set]
        config.set_extra_time(course_id, et_list)
        updated = len(ids)

    elif action == "set_canvas_group":
        if not isinstance(val, dict):
            return JSONResponse({"ok": False, "error": "set_canvas_group requires value object."})
        category_id = val.get("category_id")
        group_id = val.get("group_id")
        if not category_id:
            return JSONResponse({"ok": False, "error": "set_canvas_group requires category_id."})
        for uid in ids:
            ok, err = _update_student_canvas_group(course_id, str(uid), category_id, str(group_id) if group_id else None)
            if ok:
                updated += 1
            else:
                failed += 1
                errors.append(f"User {uid}: {err}")

    elif action == "clear_canvas_group":
        if not isinstance(val, dict):
            return JSONResponse({"ok": False, "error": "clear_canvas_group requires value object."})
        category_id = val.get("category_id")
        if not category_id:
            return JSONResponse({"ok": False, "error": "clear_canvas_group requires category_id."})
        for uid in ids:
            ok, err = _update_student_canvas_group(course_id, str(uid), category_id, None)
            if ok:
                updated += 1
            else:
                failed += 1
                errors.append(f"User {uid}: {err}")

    elif action in ("set_tier", "clear_tier", "set_planned_group", "clear_planned_group"):
        return JSONResponse({
            "ok": False,
            "error": f"'{action}' is obsolete in V3; use set_canvas_group or clear_canvas_group."
        })

    elif action in ("set_monitored", "clear_monitored"):
        is_set = action == "set_monitored"
        for uid in ids:
            uid_str = str(uid)
            if is_set:
                config.set_monitored_student(uid_str, name=_value_name(val, uid_str) or uid_str, note="")
            else:
                config.remove_monitored_student(uid_str)
            updated += 1

    else:
        return JSONResponse({"ok": False, "error": f"Unknown action '{action}'."})

    # Build response
    result = {"ok": True, "updated": updated}
    if failed > 0:
        result["failed"] = failed
        result["errors"] = errors[:5]  # Limit error details
        if updated > 0:
            result["message"] = f"Updated {updated}; failed {failed}."
        else:
            result["ok"] = False
            result["error"] = f"All {failed} updates failed: " + "; ".join(errors[:3])

    return JSONResponse(result)


# --------------------------------------------------------------------------
# Tier-scheme endpoints (kept for backward compatibility)
# --------------------------------------------------------------------------


@router.get("/tier-scheme")
def get_tier_scheme(course_id: str = Query("")):
    """Get the tier scheme for a course (V2 compatibility)."""
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})
    scheme = config.get_roster_tier_scheme(course_id)
    return JSONResponse({"ok": True, "tier_scheme": scheme})


@router.post("/tier-scheme")
def save_tier_scheme(course_id: str = Form(...), scheme: str = Form(...)):
    """Save a tier scheme for a course."""
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})
    try:
        parsed = json.loads(scheme)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"Invalid scheme JSON: {e}"})
    try:
        config.set_roster_tier_scheme(course_id, parsed)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)})
    return JSONResponse({"ok": True, "tier_scheme": config.get_roster_tier_scheme(course_id)})


# --------------------------------------------------------------------------
# V3: Group set preference and group labels
# --------------------------------------------------------------------------


@router.post("/group-set-preference")
def save_group_set_preference(
    course_id: str = Form(...),
    category_id: str = Form(""),
):
    """Save the preferred group set for a course."""
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})
    config.set_selected_group_category_id(course_id, category_id or None)
    return JSONResponse({"ok": True})


@router.get("/group-labels")
def get_group_labels(course_id: str = Query("")):
    """Get group labels for a course."""
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})
    return JSONResponse({"ok": True, "group_labels": config.get_roster_group_scheme(course_id).get("group_labels", {})})


@router.post("/group-labels")
def save_group_labels(
    course_id: str = Form(...),
    labels: str = Form(...),
):
    """Save group labels for a course."""
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})
    try:
        parsed = json.loads(labels)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"Invalid labels JSON: {e}"})
    if not isinstance(parsed, dict):
        return JSONResponse({"ok": False, "error": "labels must be an object."})
    # Save each label individually
    for group_id, label_info in parsed.items():
        teacher_label = label_info.get("teacher_label", "") if isinstance(label_info, dict) else ""
        meaning = label_info.get("meaning", "") if isinstance(label_info, dict) else ""
        config.set_group_label(course_id, group_id, teacher_label, meaning)
    return JSONResponse({"ok": True, "group_labels": parsed})

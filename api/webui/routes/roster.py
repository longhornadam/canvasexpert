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

from fastapi import APIRouter, Form, Query
from fastapi.responses import JSONResponse

import feedback_scrub
from .. import config
from ..canvas_client import _canvas_get_all, _canvas_headers, _canvas_send
from .courses import load_group_categories
from .names import _fetch_students, _upsert_roster, _vault
from . import roster_canvas
from .roster_helpers import (
    _annotate_group_labels,
    _as_int,
    _compute_canvas_group_display,
    _compute_warnings,
    _enrollment_section_ids,
    _parse_group_names,
    _resolve_tier_display,
    _user_id_set_from_canvas_groups,
    _value_name,
)

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
    return roster_canvas.fetch_sections(course_id, canvas_get_all=_canvas_get_all)


def _create_canvas_group(category_id: str, name: str) -> tuple[dict | None, str | None]:
    return roster_canvas.create_canvas_group(category_id, name, canvas_send=_canvas_send)


# --------------------------------------------------------------------------
# Canvas Group Membership Helpers (V3)
# --------------------------------------------------------------------------

def canvas_add_group_membership(group_id: str, user_id: str) -> tuple[bool, str | None]:
    return roster_canvas.canvas_add_group_membership(
        group_id, user_id, canvas_send=_canvas_send)


def canvas_remove_group_membership(group_id: str, membership_id: str) -> tuple[bool, str | None]:
    return roster_canvas.canvas_remove_group_membership(
        group_id, membership_id, canvas_send=_canvas_send)


def _get_group_memberships(course_id: str, group_id: str) -> tuple[list[dict], str | None]:
    return roster_canvas.get_group_memberships(
        course_id, group_id, canvas_headers=_canvas_headers)


def _validate_canvas_group_target(
    course_id: str,
    category_id: str,
    target_group_id: str | None,
) -> tuple[list[dict], dict | None, str | None]:
    return roster_canvas.validate_canvas_group_target(
        course_id,
        category_id,
        target_group_id,
        load_group_categories=load_group_categories,
    )


def _update_student_canvas_group(
    course_id: str,
    user_id: str,
    category_id: str,
    target_group_id: str | None,
    categories: list[dict] | None = None,
) -> tuple[bool, str | None]:
    return roster_canvas.update_student_canvas_group(
        course_id,
        user_id,
        category_id,
        target_group_id,
        categories=categories,
        validate_canvas_group_target=_validate_canvas_group_target,
        canvas_add_group_membership=canvas_add_group_membership,
        canvas_remove_group_membership=canvas_remove_group_membership,
    )


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
    _annotate_group_labels(course_id, categories)
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
            canvas_group = _compute_canvas_group_display(
                course_id,
                canvas_group_info.get("group_id"),
                canvas_group_info.get("group_name"),
            )
            canvas_group["category_id"] = canvas_group_info.get("category_id")
            canvas_group["category_name"] = canvas_group_info.get("category_name")

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
    group_unset_count = sum(
        1 for s in students_out
        if selected_category_id and not (s.get("canvas_group") or {}).get("group_id")
    )
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

        # If clearing or setting a group, update Canvas
        target_group_id = None if not group_id else str(group_id)

        categories, _, validation_err = _validate_canvas_group_target(course_id, category_id, target_group_id)
        if validation_err:
            return JSONResponse({"ok": False, "error": validation_err})

        ok, err = _update_student_canvas_group(course_id, user_id, category_id, target_group_id, categories)
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
        categories, _, validation_err = _validate_canvas_group_target(
            course_id, category_id, str(group_id) if group_id else None)
        if validation_err:
            return JSONResponse({"ok": False, "error": validation_err})
        for uid in ids:
            ok, err = _update_student_canvas_group(
                course_id, str(uid), category_id, str(group_id) if group_id else None, categories)
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
        categories, _, validation_err = _validate_canvas_group_target(course_id, category_id, None)
        if validation_err:
            return JSONResponse({"ok": False, "error": validation_err})
        for uid in ids:
            ok, err = _update_student_canvas_group(course_id, str(uid), category_id, None, categories)
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


@router.post("/group-set")
def create_group_set(
    course_id: str = Form(...),
    name: str = Form(...),
    group_names: str = Form("[]"),
):
    """Create a Canvas group set, then optionally create groups inside it."""
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})
    set_name = (name or "").strip()
    if not set_name:
        return JSONResponse({"ok": False, "error": "Group set name required."})
    names, parse_err = _parse_group_names(group_names)
    if parse_err:
        return JSONResponse({"ok": False, "error": parse_err})

    category, err = _canvas_send(
        "POST",
        f"/api/v1/courses/{course_id}/group_categories",
        {"name": set_name},
    )
    if err:
        return JSONResponse({"ok": False, "error": err})
    category_id = str(category.get("id", "") if isinstance(category, dict) else "")
    if not category_id:
        return JSONResponse({"ok": False, "error": "Canvas did not return a group set id."})

    created_groups = []
    for group_name in names:
        group, group_err = _create_canvas_group(category_id, group_name)
        if group_err:
            return JSONResponse({
                "ok": False,
                "error": f"Created group set, but failed to create '{group_name}': {group_err}",
                "group_category": category,
                "created_groups": created_groups,
            })
        created_groups.append(group)

    config.set_selected_group_category_id(course_id, category_id)
    return JSONResponse({
        "ok": True,
        "group_category": category,
        "created_groups": created_groups,
    })


@router.post("/groups")
def create_groups(
    course_id: str = Form(...),
    category_id: str = Form(...),
    group_names: str = Form(...),
):
    """Create Canvas groups in an existing group set."""
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})
    if not category_id:
        return JSONResponse({"ok": False, "error": "group set required."})
    names, parse_err = _parse_group_names(group_names)
    if parse_err:
        return JSONResponse({"ok": False, "error": parse_err})
    if not names:
        return JSONResponse({"ok": False, "error": "At least one group name required."})

    categories, _, validation_err = _validate_canvas_group_target(course_id, category_id, None)
    if validation_err:
        return JSONResponse({"ok": False, "error": validation_err})
    category = next((c for c in categories if c.get("category_id") == str(category_id)), None)
    existing = {str(g.get("name", "")).strip().lower()
                for g in (category or {}).get("groups", [])}
    for group_name in names:
        if group_name.lower() in existing:
            return JSONResponse({"ok": False, "error": f"Group '{group_name}' already exists."})

    created_groups = []
    for group_name in names:
        group, group_err = _create_canvas_group(str(category_id), group_name)
        if group_err:
            return JSONResponse({
                "ok": False,
                "error": f"Failed to create '{group_name}': {group_err}",
                "created_groups": created_groups,
            })
        created_groups.append(group)

    return JSONResponse({"ok": True, "created_groups": created_groups})


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
    clean = {}
    for group_id, label_info in parsed.items():
        if not isinstance(label_info, dict):
            continue
        teacher_label = str(label_info.get("teacher_label", "") or "").strip()
        meaning = str(label_info.get("meaning", "") or "").strip()
        if teacher_label or meaning:
            clean[str(group_id)] = {"teacher_label": teacher_label, "meaning": meaning}
    config.set_group_labels(course_id, clean)
    return JSONResponse({"ok": True, "group_labels": clean})

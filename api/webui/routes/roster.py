"""Roster Console API — unified student-level settings surface.

Prefix: /api/roster

Routes:
    GET  /api/roster          — full roster merge (students + vault + settings + groups)
    POST /api/roster/student  — update one student's settings
    POST /api/roster/bulk     — bulk action on many students
    GET  /api/roster/tier-scheme  — get course tier scheme
    POST /api/roster/tier-scheme  — save course tier scheme

Depends on the existing vault, extra-time, monitored-student, and group helpers.
Does NOT write Canvas groups in V2.
"""
import json
import re as _re

from fastapi import APIRouter, Form, Query
from fastapi.responses import JSONResponse

import feedback_scrub
from .. import config
from ..canvas_client import _canvas_get_all
from .courses import load_group_categories
from .names import _fetch_students, _upsert_roster, _vault

router = APIRouter(prefix="/api/roster", tags=["roster"])

ALLOWED_STUDENT_PATCH_KEYS = {
    "nicknames", "pseudonym", "regenerate_pseudonym",
    "extra_time", "monitored", "tier_id", "tier", "planned_group",
}

WARNING_CODES = (
    "missing_pseudonym", "extra_time_without_days",
    "tier_unset", "nickname_collision", "protected_name_collision",
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
                       protected_names: set[str], collisions: dict) -> list[str]:
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

    if not student.get("tier_id"):
        warnings.append("tier_unset")

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


def _user_id_set_from_canvas_groups(categories: list[dict]) -> dict:
    """Return {user_id_str: [group_info, ...]} from categories."""
    result: dict[str, list[dict]] = {}
    for cat in categories:
        cat_id = cat.get("category_id", "")
        cat_name = cat.get("category_name", "")
        for grp in cat.get("groups", []):
            gid = grp.get("id", "")
            gname = grp.get("name", "")
            for sid in grp.get("student_ids", []):
                sid_str = str(sid)
                result.setdefault(sid_str, []).append({
                    "category_id": cat_id,
                    "category_name": cat_name,
                    "group_id": gid,
                    "group_name": gname,
                })
    return result


def _migrate_and_clean_settings(course_id: str, roster_settings: dict) -> dict:
    """Migrate legacy V1 tier/planned_group to V2 tier_id. Returns cleaned settings dict."""
    result = {}
    for uid, local in roster_settings.items():
        entry = {}
        tier_id = local.get("tier_id")
        if tier_id:
            entry["tier_id"] = tier_id
        else:
            legacy_tier = local.get("tier", "")
            if legacy_tier:
                migrated = config.migrate_legacy_tier(course_id, uid, legacy_tier, roster_settings)
                if migrated:
                    entry["tier_id"] = migrated
            # Remove legacy fields from output
        # Preserve only V2 keys
        if "tier_id" in entry or not local.get("tier"):
            pass  # clean
        result[uid] = entry
    return result


@router.get("")
def roster_get(course_id: str = Query("")):
    """Full roster merge for one course.

    1. Fetch students from Canvas + upsert into vault.
    2. Fetch sections and groups.
    3. Merge vault entries, extra-time, monitored, and local settings.
    4. Return unified rows with counts, warnings, and tier_scheme.
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

    # Groups (read-only in V2)
    categories, group_err, group_msg = load_group_categories(course_id)
    user_groups = _user_id_set_from_canvas_groups(categories)

    # Extra time
    extra_time_list = config.get_extra_time(course_id)
    extra_time_by_id: dict[str, dict] = {}
    for et in extra_time_list:
        extra_time_by_id[et.get("id", "")] = {"enabled": True, "days": et.get("days", 0)}

    # Monitored
    monitored = config.get_monitored_students()

    # Local roster settings — migrate legacy tier/planned_group
    raw_roster_settings = config.get_roster_student_settings(course_id)
    roster_settings = _migrate_and_clean_settings(course_id, raw_roster_settings)

    # Tier scheme
    tier_scheme = config.get_roster_tier_scheme(course_id)

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

        # Local settings (V2)
        local = roster_settings.get(uid, {})

        # Canvas groups (read-only in V2)
        canvas_groups = user_groups.get(uid, [])

        # Nicknames from vault
        nicknames = ve.get("nicknames", [])

        # Tier display
        tier_id = local.get("tier_id", "")
        tier_info = _resolve_tier_display(course_id, tier_id, tier_scheme)

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
            "warnings": [],
            **tier_info,
        }
        row["warnings"] = _compute_warnings(
            row, vault_by_id, protected_names, collisions)
        students_out.append(row)
        name_order_map[uid] = (sortable or display).lower()

    students_out.sort(key=lambda s: name_order_map.get(s["id"], s["name"].lower()))

    # Counts
    total = len(students_out)
    extra_time_count = sum(1 for s in students_out if s["extra_time"]["enabled"])
    monitored_count = sum(1 for s in students_out if s["monitored"]["enabled"])
    tier_unset_count = sum(1 for s in students_out if not s.get("tier_id"))
    warning_count = sum(1 for s in students_out if s["warnings"])

    note = ""
    if group_err:
        note = f"Groups: {group_err}"
    elif group_msg:
        note = group_msg

    return JSONResponse({
        "ok": True,
        "students": students_out,
        "groups": categories,
        "tier_scheme": tier_scheme,
        "counts": {
            "total": total,
            "extra_time": extra_time_count,
            "monitored": monitored_count,
            "tier_unset": tier_unset_count,
            "warnings": warning_count,
        },
        "note": note or None,
    })


@router.post("/student")
def roster_student_update(
    course_id: str = Form(...),
    user_id: str = Form(...),
    patch: str = Form(...),
):
    """Update one student's roster settings.

    V2 accepted patch fields: nicknames, pseudonym, regenerate_pseudonym,
    extra_time, monitored, tier_id.
    Legacy: tier (maps to tier_id), planned_group (ignored/no-op).
    """
    if not course_id or not user_id:
        return JSONResponse({"ok": False, "error": "course_id and user_id required."})

    try:
        data = json.loads(patch)
    except json.JSONDecodeError as e:
        return JSONResponse({"ok": False, "error": f"Invalid patch JSON: {e}"})
    if not isinstance(data, dict):
        return JSONResponse({"ok": False, "error": "patch must be a JSON object."})

    # Validate keys
    unknown = set(data.keys()) - ALLOWED_STUDENT_PATCH_KEYS
    if unknown:
        return JSONResponse({"ok": False, "error": f"Unknown patch keys: {sorted(unknown)}"})

    vault = _vault()
    tier_scheme = config.get_roster_tier_scheme(course_id)
    active_tiers = {t["id"] for t in tier_scheme if t.get("active", True)}

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

    # --- Tier (V2: tier_id) ---
    tier_id_val = data.get("tier_id")
    if tier_id_val is not None:
        if tier_id_val and tier_id_val not in active_tiers:
            return JSONResponse(
                {"ok": False,
                 "error": f"Invalid tier_id '{tier_id_val}'. Valid: {sorted(active_tiers)}"})
        patch_data = {"tier_id": tier_id_val if tier_id_val else None}
        # Clean up legacy V1 fields
        config.update_roster_student_settings(course_id, user_id, patch_data)
        # Also remove legacy fields
        config.update_roster_student_settings(course_id, user_id, {"tier": None})
        config.update_roster_student_settings(course_id, user_id, {"planned_group": None})

    # --- Legacy tier (V1 compat — map to tier_id) ---
    if "tier" in data and "tier_id" not in data:
        legacy_tier = data["tier"]
        if legacy_tier:
            migrated = config.migrate_legacy_tier(course_id, user_id, legacy_tier)
            if migrated and migrated in active_tiers:
                config.update_roster_student_settings(course_id, user_id, {"tier_id": migrated})
            else:
                config.update_roster_student_settings(course_id, user_id, {"tier_id": migrated})
            config.update_roster_student_settings(course_id, user_id, {"tier": None})
        else:
            config.update_roster_student_settings(course_id, user_id, {"tier_id": None})
            config.update_roster_student_settings(course_id, user_id, {"tier": None})

    # --- Legacy planned_group (V2: no-op / cleanup) ---
    if "planned_group" in data:
        # Silently clean up — remove planned_group from storage
        config.update_roster_student_settings(course_id, user_id, {"planned_group": None})

    return JSONResponse({"ok": True})


@router.post("/bulk")
def roster_bulk_update(
    course_id: str = Form(...),
    user_ids: str = Form(...),
    action: str = Form(...),
    value: str = Form(""),
):
    """Bulk action on many students.

    V2 supported actions: set_extra_time, clear_extra_time, set_tier, clear_tier,
    set_monitored, clear_monitored.
    Legacy: set/clear_planned_group accepted but no-op (cleanup only).
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

    elif action == "set_tier":
        tier_id = str(val) if isinstance(val, str) else (val.get("tier_id", "") if isinstance(val, dict) else "")
        if not tier_id and isinstance(val, dict) and val.get("tier"):
            # Legacy: map tier label
            tier_label = val["tier"]
            for uid in ids:
                migrated = config.migrate_legacy_tier(course_id, uid, tier_label)
                if migrated:
                    config.update_roster_student_settings(course_id, uid, {"tier_id": migrated})
                    config.update_roster_student_settings(course_id, uid, {"tier": None})
                    config.update_roster_student_settings(course_id, uid, {"planned_group": None})
                updated += 1
        else:
            active_tiers = config.active_tier_ids(course_id)
            if tier_id and tier_id not in active_tiers:
                return JSONResponse(
                    {"ok": False,
                     "error": f"Invalid tier_id '{tier_id}'. Valid: {sorted(active_tiers)}"})
            for uid in ids:
                config.update_roster_student_settings(course_id, uid, {"tier_id": tier_id or None})
                config.update_roster_student_settings(course_id, uid, {"tier": None})
                config.update_roster_student_settings(course_id, uid, {"planned_group": None})
                updated += 1

    elif action == "clear_tier":
        for uid in ids:
            config.update_roster_student_settings(course_id, uid, {"tier_id": None})
            config.update_roster_student_settings(course_id, uid, {"tier": None})
            updated += 1

    elif action in ("set_planned_group", "clear_planned_group"):
        # V2: no-op, silently clean up
        for uid in ids:
            config.update_roster_student_settings(course_id, uid, {"planned_group": None})
            updated += 1

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

    # Rebuild minimal local counts
    extra_time_list = config.get_extra_time(course_id)
    et_count = len(extra_time_list)
    monitored_dict = config.get_monitored_students()
    mon_count = len(monitored_dict)
    roster_settings = config.get_roster_student_settings(course_id)
    tier_unset = sum(1 for v in roster_settings.values() if not v.get("tier_id"))

    return JSONResponse({
        "ok": True,
        "updated": updated,
        "counts": {
            "extra_time": et_count,
            "monitored": mon_count,
            "tier_unset": tier_unset,
        },
    })


# --------------------------------------------------------------------------
# Tier-scheme endpoints
# --------------------------------------------------------------------------


@router.get("/tier-scheme")
def get_tier_scheme(course_id: str = Query("")):
    """Get the tier scheme for a course."""
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

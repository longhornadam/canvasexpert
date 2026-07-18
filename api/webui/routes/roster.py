"""Roster Console API — unified student-level settings surface.

Prefix: /api/roster

Routes:
    GET  /api/roster          — full roster merge (students + vault + settings + groups)
    POST /api/roster/student  — update one student's settings
    POST /api/roster/bulk     — bulk action on many students

V3: Canvas groups are the source of truth for tier/group assignment.
Does NOT write local tier_id.
"""
from fastapi import APIRouter, Form, Query
from fastapi.responses import JSONResponse

from api import feedback_scrub
from api import roster_service
from api.mirror import store as mirror_store
from .. import config
from ..canvas_client import _canvas_get_all, _canvas_headers, _canvas_send
from .courses import load_group_categories
from .names import _vault
from . import roster_groups
from . import roster_canvas
from . import roster_updates
from .roster_helpers import (
    _annotate_group_labels,
    _as_int,
    _compute_canvas_group_display,
    _compute_warnings,
    _enrollment_section_ids,
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
    return roster_service.fetch_sections(course_id, canvas_get_all=_canvas_get_all)


_fetch_students = roster_service.fetch_students
_upsert_roster = roster_service.upsert_roster


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

    roster_document = mirror_store.read_roster(course_id)
    if roster_document is not None and roster_document.get("state") == "current":
        users = list(roster_document["students"].values())
        section_map = roster_document["sections"]
    else:
        users, err = _fetch_students(course_id)
        if err:
            return JSONResponse({"ok": False, "error": f"Canvas fetch failed: {err}"})
        section_map = _fetch_sections(course_id)

    vault = _vault()
    with vault.transaction():
        _upsert_roster(vault, users)
        vault_entries_list = vault.entries()

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
    return JSONResponse(roster_updates.update_student(
        course_id,
        user_id,
        patch,
        vault_factory=_vault,
        get_extra_time=config.get_extra_time,
        set_extra_time=config.set_extra_time,
        set_monitored_student=config.set_monitored_student,
        remove_monitored_student=config.remove_monitored_student,
        as_int=_as_int,
        validate_canvas_group_target=_validate_canvas_group_target,
        update_student_canvas_group=_update_student_canvas_group,
        allowed_keys=ALLOWED_STUDENT_PATCH_KEYS,
        obsolete_keys=OBSOLETE_PATCH_KEYS,
    ))


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
    return JSONResponse(roster_updates.update_bulk(
        course_id,
        user_ids,
        action,
        value,
        get_extra_time=config.get_extra_time,
        set_extra_time=config.set_extra_time,
        set_monitored_student=config.set_monitored_student,
        remove_monitored_student=config.remove_monitored_student,
        as_int=_as_int,
        value_name=_value_name,
        validate_canvas_group_target=_validate_canvas_group_target,
        update_student_canvas_group=_update_student_canvas_group,
    ))


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
    return JSONResponse(roster_groups.save_group_set_preference(
        course_id,
        category_id,
        set_selected_group_category_id=config.set_selected_group_category_id,
    ))


@router.post("/group-set")
def create_group_set(
    course_id: str = Form(...),
    name: str = Form(...),
    group_names: str = Form("[]"),
):
    """Create a Canvas group set, then optionally create groups inside it."""
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})
    return JSONResponse(roster_groups.create_group_set(
        course_id,
        name,
        group_names,
        canvas_send=_canvas_send,
        create_canvas_group=_create_canvas_group,
        set_selected_group_category_id=config.set_selected_group_category_id,
    ))


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
    return JSONResponse(roster_groups.create_groups(
        course_id,
        category_id,
        group_names,
        validate_canvas_group_target=_validate_canvas_group_target,
        create_canvas_group=_create_canvas_group,
    ))


@router.get("/group-labels")
def get_group_labels(course_id: str = Query("")):
    """Get group labels for a course."""
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})
    return JSONResponse(roster_groups.get_group_labels(
        course_id,
        get_roster_group_scheme=config.get_roster_group_scheme,
    ))


@router.post("/group-labels")
def save_group_labels(
    course_id: str = Form(...),
    labels: str = Form(...),
):
    """Save group labels for a course."""
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})
    return JSONResponse(roster_groups.save_group_labels(
        course_id,
        labels,
        set_group_labels=config.set_group_labels,
    ))

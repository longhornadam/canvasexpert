"""Roster Console configuration — student settings, tier scheme, group scheme.

Uses lazy module-reference so monkeypatches to config._io propagate correctly.
"""
import re

from . import _io as _io_mod


# --------------------------------------------------------------------------
# Roster student settings
# --------------------------------------------------------------------------

def get_roster_student_settings(course_id: str) -> dict:
    return _io_mod._synced_state().get("roster_student_settings", {}).get(str(course_id), {})


def set_roster_student_settings(course_id: str, settings: dict):
    state = _io_mod._synced_state()
    all_settings = state.setdefault("roster_student_settings", {})
    all_settings[str(course_id)] = settings
    _io_mod._save_synced_key("roster_student_settings", all_settings)


def update_roster_student_settings(course_id: str, user_id: str, patch: dict):
    state = _io_mod._synced_state()
    all_settings = state.setdefault("roster_student_settings", {})
    course_settings = all_settings.setdefault(str(course_id), {})
    student = course_settings.setdefault(str(user_id), {})
    for k, v in patch.items():
        if v is None:
            student.pop(k, None)
        else:
            student[k] = v
    _io_mod._save_synced_key("roster_student_settings", all_settings)


# --------------------------------------------------------------------------
# Tier scheme
# --------------------------------------------------------------------------

ROSTER_DEFAULT_TIER_SCHEME = [
    {"id": "support", "teacher_label": "Support", "meaning": "below-level",
     "alias": "Blue", "order": 10, "active": True},
    {"id": "core", "teacher_label": "Core", "meaning": "on-level",
     "alias": "Red", "order": 20, "active": True},
    {"id": "extend", "teacher_label": "Extend", "meaning": "advanced",
     "alias": "White", "order": 30, "active": True},
]


def _validate_tier_scheme(scheme: list[dict]) -> str | None:
    if not isinstance(scheme, list) or not scheme:
        return "Scheme must be a non-empty list."
    seen_ids: set[str] = set()
    for i, t in enumerate(scheme):
        if not isinstance(t, dict):
            return f"Item {i} is not an object."
        tid = t.get("id", "")
        if not tid or not isinstance(tid, str):
            return f"Item {i}: missing or invalid 'id'."
        if tid in seen_ids:
            return f"Duplicate tier id '{tid}'."
        seen_ids.add(tid)
        label = t.get("teacher_label", "")
        if not label or not isinstance(label, str):
            return f"Tier '{tid}': missing 'teacher_label'."
        alias = t.get("alias", "")
        if not alias or not isinstance(alias, str):
            return f"Tier '{tid}': missing or blank 'alias'."
    return None


def _normalize_tier_scheme(scheme: list[dict]) -> list[dict]:
    out = []
    for i, t in enumerate(scheme):
        out.append({
            "id": str(t.get("id", "")),
            "teacher_label": str(t.get("teacher_label", "")),
            "meaning": str(t.get("meaning", "")),
            "alias": str(t.get("alias", "")),
            "order": t.get("order", (i + 1) * 10),
            "active": t.get("active", True),
        })
    return out


def get_roster_tier_scheme(course_id: str) -> list[dict]:
    schemes = _io_mod._synced_state().get("roster_tier_schemes", {})
    saved = schemes.get(str(course_id))
    if saved:
        return _normalize_tier_scheme(saved)
    return list(ROSTER_DEFAULT_TIER_SCHEME)


def set_roster_tier_scheme(course_id: str, scheme: list[dict]):
    err = _validate_tier_scheme(scheme)
    if err:
        raise ValueError(err)
    norm = _normalize_tier_scheme(scheme)
    state = _io_mod._synced_state()
    schemes = state.setdefault("roster_tier_schemes", {})
    schemes[str(course_id)] = norm
    _io_mod._save_synced_key("roster_tier_schemes", schemes)


def roster_tier_by_id(course_id: str) -> dict:
    scheme = get_roster_tier_scheme(course_id)
    return {t["id"]: t for t in scheme}


def active_tier_ids(course_id: str) -> set[str]:
    return {t["id"] for t in get_roster_tier_scheme(course_id) if t.get("active", True)}


def migrate_legacy_tier(course_id: str, user_id: str, tier_val: str, roster_settings: dict | None = None) -> str | None:
    if not tier_val:
        return None
    scheme = get_roster_tier_scheme(course_id)
    tier_lower = tier_val.strip().lower()
    for t in scheme:
        if t.get("teacher_label", "").lower() == tier_lower:
            return t["id"]
    slug = re.sub(r'[^a-z0-9]+', '_', tier_lower).strip('_') or f"tier_{len(scheme)}"
    new_tier = {
        "id": slug,
        "teacher_label": tier_val.strip(),
        "meaning": "",
        "alias": tier_val.strip(),
        "order": 1000,
        "active": True,
    }
    scheme.append(new_tier)
    set_roster_tier_scheme(course_id, scheme)
    return slug


# --------------------------------------------------------------------------
# Group scheme
# --------------------------------------------------------------------------

DEFAULT_GROUP_LABELS = {
    "blue": "Support",
    "red": "Core",
    "white": "Extend",
}


def get_roster_group_scheme(course_id: str) -> dict:
    schemes = _io_mod._synced_state().get("roster_group_schemes", {})
    return schemes.get(str(course_id), {})


def set_roster_group_scheme(course_id: str, scheme: dict):
    state = _io_mod._synced_state()
    schemes = state.setdefault("roster_group_schemes", {})
    schemes[str(course_id)] = scheme
    _io_mod._save_synced_key("roster_group_schemes", schemes)


def get_selected_group_category_id(course_id: str) -> str | None:
    scheme = get_roster_group_scheme(course_id)
    return scheme.get("selected_group_category_id")


def set_selected_group_category_id(course_id: str, category_id: str | None):
    scheme = get_roster_group_scheme(course_id)
    scheme["selected_group_category_id"] = category_id
    set_roster_group_scheme(course_id, scheme)


def get_group_label(course_id: str, group_id: str) -> dict | None:
    scheme = get_roster_group_scheme(course_id)
    return scheme.get("group_labels", {}).get(str(group_id))


def set_group_label(course_id: str, group_id: str, teacher_label: str, meaning: str = ""):
    scheme = get_roster_group_scheme(course_id)
    labels = scheme.setdefault("group_labels", {})
    labels[str(group_id)] = {"teacher_label": teacher_label, "meaning": meaning}
    set_roster_group_scheme(course_id, scheme)


def set_group_labels(course_id: str, labels: dict):
    scheme = get_roster_group_scheme(course_id)
    scheme["group_labels"] = labels
    set_roster_group_scheme(course_id, scheme)


def compute_group_display(teacher_label: str | None, group_name: str) -> str:
    if teacher_label and teacher_label != group_name:
        return f"{teacher_label} / {group_name}"
    return group_name


def default_group_label(group_name: str) -> str | None:
    return DEFAULT_GROUP_LABELS.get(group_name.lower())
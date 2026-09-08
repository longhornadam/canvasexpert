"""Roster-change reporting and the one-click section-change migration.

Canvas rosters drift for weeks while Skyward syncs in and counselors move
students between sections. ``api.roster_context.diff_roster_baseline`` finds
who is new, who has left, and who changed section from ids and section ids
alone -- that is all the Work Registry provider needs, so it lives in the
shared, config-free ``roster_context`` module. This module adds the
human-facing side: exactly which locally-held store still references a given
student (settings, extra time, monitored status, score values, relationship
pairs, seat), keyed by course + student or by course + section -- and, for
an unambiguous single-section swap, actually moves the section-keyed pieces.
"""
from __future__ import annotations

from collections.abc import Callable

from api import roster_context


def _has_local_settings(entry: dict | None) -> bool:
    """True when a roster_student_settings row holds more than empty defaults."""
    if not isinstance(entry, dict):
        return False
    profile = entry.get("classroom_profile")
    if isinstance(profile, dict) and (profile.get("birthday") or profile.get("celebrations")):
        return True
    return False


def _section_label(section_id: str, section_names: dict) -> dict:
    return {"section_id": section_id, "section_name": section_names.get(section_id) or f"Section {section_id}"}


def _score_holdings(score_matrix: dict, student_id: str, section_ids, section_names: dict) -> list[dict]:
    """Sections holding a score for student_id, restricted to section_ids when given."""
    values_by_section = (score_matrix or {}).get("values_by_section", {})
    result = []
    for section_id, students in values_by_section.items():
        if section_ids is not None and section_id not in section_ids:
            continue
        scores = (students or {}).get(student_id)
        if scores:
            result.append({**_section_label(section_id, section_names), "columns": sorted(scores)})
    return sorted(result, key=lambda item: item["section_id"])


def _relationship_holdings(relationships: dict, student_id: str, section_ids, section_names: dict,
                           name_by_id: dict) -> list[dict]:
    """Pairs referencing student_id, restricted to section_ids when given."""
    by_section = (relationships or {}).get("by_section", {})
    result = []
    for section_id, items in by_section.items():
        if section_ids is not None and section_id not in section_ids:
            continue
        for item in items or []:
            if item.get("student_a") != student_id and item.get("student_b") != student_id:
                continue
            partner_id = item["student_b"] if item["student_a"] == student_id else item["student_a"]
            result.append({
                **_section_label(section_id, section_names),
                "partner_id": partner_id,
                "partner_name": name_by_id.get(partner_id, partner_id),
                "type": item.get("type"),
            })
    return sorted(result, key=lambda item: (item["section_id"], item["partner_id"]))


def departed_detail(
    student_id: str,
    *,
    display_name: str,
    roster_student_settings: dict,
    extra_time_by_id: dict,
    monitored: dict,
    score_matrix: dict,
    relationships: dict,
    section_names: dict,
    name_by_id: dict,
) -> dict:
    """Exactly which local store still holds data for a student no longer on this roster."""
    extra_time = extra_time_by_id.get(student_id)
    return {
        "student_id": student_id,
        "display_name": display_name,
        "settings": _has_local_settings(roster_student_settings.get(student_id)),
        "extra_time_days": extra_time.get("days") if extra_time else None,
        "monitored": student_id in monitored,
        "score_values": _score_holdings(score_matrix, student_id, None, section_names),
        "relationship_pairs": _relationship_holdings(relationships, student_id, None, section_names, name_by_id),
    }


def changed_section_detail(
    change: dict,
    *,
    score_matrix: dict,
    relationships: dict,
    section_names: dict,
    name_by_id: dict,
) -> dict:
    """What is stranded under a student's old section id(s), and whether a migrate action applies."""
    student_id = change["student_id"]
    old_ids = set(change["old_section_ids"])
    return {
        **change,
        "old_section_names": [section_names.get(sid) or f"Section {sid}" for sid in change["old_section_ids"]],
        "new_section_names": [section_names.get(sid) or f"Section {sid}" for sid in change["new_section_ids"]],
        "score_values": _score_holdings(score_matrix, student_id, old_ids, section_names),
        "relationship_pairs": _relationship_holdings(relationships, student_id, old_ids, section_names, name_by_id),
        # Only a clean one-section-to-another swap is unambiguous enough to
        # move automatically -- see roster_context.diff_roster_baseline.
        "can_migrate": change["clean_swap"],
    }


def migrate_student_section(
    course_id: str,
    student_id: str,
    diff: dict,
    *,
    get_roster_score_matrix: Callable[[str], dict],
    set_roster_score_matrix: Callable[[str, dict], None],
    get_roster_relationships: Callable[[str], dict],
    set_roster_relationships: Callable[[str, dict], None],
    get_roster_baseline: Callable[[str], dict],
    set_roster_baseline: Callable[[str, dict], None],
) -> tuple[dict | None, str | None]:
    """Move one student's stranded section-keyed local data to their new section.

    ``diff`` must be a fresh ``api.roster_context.diff_roster_baseline``
    result for this course, computed by the caller from the current baseline
    and the live roster. The old/new section pair always comes from that
    diff, never from client input -- the only trustworthy answer to "is this
    really a clean swap" is a fresh comparison, not whatever a request claims.
    """
    change = next(
        (item for item in diff.get("changed_section", []) if item["student_id"] == student_id),
        None,
    )
    if change is None or not change["clean_swap"]:
        return None, "This student does not have a single, unambiguous section change to bring over."

    old_section_id = change["old_section_ids"][0]
    new_section_id = change["new_section_ids"][0]

    # Score matrix: fill in only the columns the new section does not
    # already have a value for. The old section's numbers are still real
    # data the teacher entered, and a value already on record for the new
    # section (rare, but possible with a brief cross-listing) is never
    # overwritten.
    matrix = roster_context._normalize_score_matrix(get_roster_score_matrix(course_id))
    values_by_section = matrix["values_by_section"]
    old_values = values_by_section.get(old_section_id, {}).pop(student_id, None)
    moved_columns: list[str] = []
    if old_values:
        new_section_values = values_by_section.setdefault(new_section_id, {})
        existing = dict(new_section_values.get(student_id, {}))
        for column_id, value in old_values.items():
            if column_id not in existing:
                existing[column_id] = value
                moved_columns.append(column_id)
        new_section_values[student_id] = existing
        if not values_by_section.get(old_section_id):
            values_by_section.pop(old_section_id, None)
        set_roster_score_matrix(course_id, matrix)

    # Relationships: a pair only ever moves as a whole, and only when both
    # sides made the identical move -- a keep-apart or preferred pair is
    # meaningless if just one student changed section. Anything else stays
    # in the old section and comes back reported as broken, so the teacher
    # notices instead of the pair silently vanishing.
    relationships = roster_context.normalize_relationships(get_roster_relationships(course_id))
    by_section = {section_id: list(items) for section_id, items in relationships["by_section"].items()}
    old_items = by_section.get(old_section_id, [])
    comigrating_partners = {
        other["student_id"] for other in diff.get("changed_section", [])
        if other["clean_swap"]
        and other["old_section_ids"] == [old_section_id]
        and other["new_section_ids"] == [new_section_id]
    }
    remaining: list[dict] = []
    moved_pairs: list[dict] = []
    broken_pairs: list[dict] = []
    for item in old_items:
        if item["student_a"] != student_id and item["student_b"] != student_id:
            remaining.append(item)
            continue
        partner_id = item["student_b"] if item["student_a"] == student_id else item["student_a"]
        if partner_id in comigrating_partners:
            new_section_items = by_section.setdefault(new_section_id, [])
            already_there = any(
                other["student_a"] == item["student_a"] and other["student_b"] == item["student_b"]
                for other in new_section_items
            )
            if not already_there:
                new_section_items.append(item)
            moved_pairs.append(item)
        else:
            remaining.append(item)
            broken_pairs.append({**item, "partner_id": partner_id})
    if old_items:
        if remaining:
            by_section[old_section_id] = remaining
        else:
            by_section.pop(old_section_id, None)
    if moved_pairs:
        set_roster_relationships(course_id, {"by_section": by_section})

    # This student's own section-change warning is now resolved locally;
    # advance just their baseline entry so it clears without acknowledging
    # the whole roster, which would also silently clear any other student's
    # still-open added/departed/changed-section warning.
    baseline = roster_context.normalize_roster_baseline(get_roster_baseline(course_id))
    baseline["students"][student_id] = list(change["new_section_ids"])
    set_roster_baseline(course_id, baseline)

    return {
        "student_id": student_id,
        "old_section_id": old_section_id,
        "new_section_id": new_section_id,
        "moved_score_columns": moved_columns,
        "moved_relationship_pairs": [
            {"student_a": pair["student_a"], "student_b": pair["student_b"], "type": pair["type"]}
            for pair in moved_pairs
        ],
        "broken_relationship_pairs": broken_pairs,
    }, None

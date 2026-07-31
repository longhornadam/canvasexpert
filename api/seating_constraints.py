"""Pure, generic-ID constraint evaluation and proposal helpers for Seating."""

from __future__ import annotations

import random
import re

from api import roster_context, seating_state


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")
_CONTEXT_FIELDS = {"section_id", "students", "relationships"}
_STUDENT_FIELDS = {"id", "front_row", "near_teacher"}
_RELATIONSHIP_FIELDS = {"type", "students"}


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(_ID_RE.fullmatch(value))


def validate_context(value: object) -> tuple[dict | None, str | None]:
    """Validate the minimal, no-display-data Roster projection for one section."""
    if not isinstance(value, dict) or set(value) != _CONTEXT_FIELDS:
        return None, "seating context has an invalid shape."
    section_id = value.get("section_id")
    students_value = value.get("students")
    relationships_value = value.get("relationships")
    if not _valid_id(section_id) or not isinstance(students_value, list) or not isinstance(relationships_value, list):
        return None, "seating context requires a valid section, students, and relationships."
    students: list[dict] = []
    student_ids: set[str] = set()
    for index, student in enumerate(students_value):
        if not isinstance(student, dict) or set(student) != _STUDENT_FIELDS:
            return None, f"student {index} has an invalid shape."
        student_id = student.get("id")
        if not _valid_id(student_id) or student_id in student_ids:
            return None, f"student {index} has an invalid id."
        front_row = student.get("front_row")
        near_teacher = student.get("near_teacher")
        if front_row not in roster_context.SEATING_CONTEXT_SUPPORTS or near_teacher not in roster_context.SEATING_CONTEXT_SUPPORTS:
            return None, f"student {index} has an invalid support level."
        student_ids.add(student_id)
        students.append({"id": student_id, "front_row": front_row, "near_teacher": near_teacher})
    relationships: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    for index, relationship in enumerate(relationships_value):
        if not isinstance(relationship, dict) or set(relationship) != _RELATIONSHIP_FIELDS:
            return None, f"relationship {index} has an invalid shape."
        relation_type = relationship.get("type")
        pair = relationship.get("students")
        if relation_type not in roster_context.RELATIONSHIP_TYPES or not isinstance(pair, list) or len(pair) != 2:
            return None, f"relationship {index} is invalid."
        first, second = pair
        if not _valid_id(first) or not _valid_id(second) or first == second or first not in student_ids or second not in student_ids:
            return None, f"relationship {index} has an invalid student."
        canonical = tuple(sorted((first, second)))
        if canonical in seen_pairs:
            return None, f"relationship {index} duplicates a pair."
        seen_pairs.add(canonical)
        relationships.append({"type": relation_type, "students": list(canonical)})
    return {
        "section_id": section_id,
        "students": sorted(students, key=lambda student: student["id"]),
        "relationships": sorted(relationships, key=lambda item: (item["students"], item["type"])),
    }, None


def _validated_layout(value: object) -> tuple[dict | None, str | None]:
    state, error = seating_state.validate_state({"layouts": [value], "modes": []})
    if error:
        return None, "layout is invalid."
    return state["layouts"][0], None


def validate_assignment(layout_value: object, context_value: object, assignment: object) -> tuple[dict | None, str | None]:
    """Validate a generic-ID proposal or lock map against one layout/context."""
    layout, layout_error = _validated_layout(layout_value)
    if layout_error:
        return None, layout_error
    context, context_error = validate_context(context_value)
    if context_error:
        return None, context_error
    if not isinstance(assignment, dict):
        return None, "assignment must be an object."
    valid_seat_ids = {seat["id"] for seat in layout["seats"]}
    valid_student_ids = {student["id"] for student in context["students"]}
    normalized: dict[str, str] = {}
    assigned_students: set[str] = set()
    for seat_id_value, student_id in assignment.items():
        if not _valid_id(seat_id_value) or seat_id_value not in valid_seat_ids:
            return None, "assignment has an unknown seat."
        if not _valid_id(student_id) or student_id not in valid_student_ids:
            return None, "assignment has a student outside this section."
        if student_id in assigned_students:
            return None, "assignment assigns a student more than once."
        normalized[seat_id_value] = student_id
        assigned_students.add(student_id)
    return normalized, None


def _seat_by_id(layout: dict) -> dict[str, dict]:
    return {seat["id"]: seat for seat in layout["seats"]}


def _are_adjacent(seats: dict[str, dict], first: str, second: str) -> bool:
    one, two = seats.get(first), seats.get(second)
    if one is None or two is None:
        return False
    return abs(one["row"] - two["row"]) + abs(one["column"] - two["column"]) == 1


def evaluate(layout_value: object, context_value: object, assignment_value: object) -> tuple[dict | None, str | None]:
    """Evaluate locked grid semantics with no names, notes, or reasons."""
    layout, layout_error = _validated_layout(layout_value)
    if layout_error:
        return None, layout_error
    context, context_error = validate_context(context_value)
    if context_error:
        return None, context_error
    assignment, assignment_error = validate_assignment(layout, context, assignment_value)
    if assignment_error:
        return None, assignment_error

    seats = _seat_by_id(layout)
    student_seats = {student_id: seat_id_value for seat_id_value, student_id in assignment.items()}
    marked_near_teacher = set(layout["near_teacher_seat_ids"])
    required_violations: list[dict] = []
    unmet_preferences: list[dict] = []
    for student in context["students"]:
        student_id = student["id"]
        seat_id_value = student_seats.get(student_id)
        seat = seats.get(seat_id_value) if seat_id_value else None
        if student["front_row"] == "required" and (seat is None or seat["row"] != 1):
            required_violations.append({"kind": "front_row_required", "student_id": student_id})
        elif student["front_row"] == "preferred" and (seat is None or seat["row"] != 1):
            unmet_preferences.append({"kind": "front_row_preferred", "student_id": student_id})
        if student["near_teacher"] == "required" and (seat is None or seat_id_value not in marked_near_teacher):
            required_violations.append({"kind": "near_teacher_required", "student_id": student_id})
        elif student["near_teacher"] == "preferred" and (seat is None or seat_id_value not in marked_near_teacher):
            unmet_preferences.append({"kind": "near_teacher_preferred", "student_id": student_id})

    for relationship in context["relationships"]:
        first, second = relationship["students"]
        first_seat, second_seat = student_seats.get(first), student_seats.get(second)
        adjacent = bool(first_seat and second_seat and _are_adjacent(seats, first_seat, second_seat))
        if relationship["type"] == "keep_apart" and adjacent:
            required_violations.append({"kind": "keep_apart", "students": [first, second]})
        elif relationship["type"] == "preferred_pair" and not adjacent:
            unmet_preferences.append({"kind": "preferred_pair", "students": [first, second]})

    required_violations.sort(key=lambda item: (item["kind"], item.get("student_id", ""), item.get("students", [])))
    unmet_preferences.sort(key=lambda item: (item["kind"], item.get("student_id", ""), item.get("students", [])))
    return {
        "required_ok": not required_violations,
        "required_violations": required_violations,
        "unmet_preferences": unmet_preferences,
    }, None


def validate_locks(layout: dict, context: dict, proposal: dict, locks_value: object) -> tuple[dict | None, str | None]:
    locks, error = validate_assignment(layout, context, locks_value)
    if error:
        return None, error
    for seat_id_value, student_id in locks.items():
        if proposal and proposal.get(seat_id_value) != student_id:
            return None, "lock does not match the proposed seat assignment."
    return locks, None


def _relationship_index(context: dict) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    keep_apart: dict[str, set[str]] = {}
    preferred: dict[str, set[str]] = {}
    for relationship in context["relationships"]:
        first, second = relationship["students"]
        target = keep_apart if relationship["type"] == "keep_apart" else preferred
        target.setdefault(first, set()).add(second)
        target.setdefault(second, set()).add(first)
    return keep_apart, preferred


def generate(layout_value: object, context_value: object, locks_value: object = None) -> tuple[dict | None, dict | None, str | None]:
    """Create one in-memory proposal, preserving valid explicit locks."""
    layout, layout_error = _validated_layout(layout_value)
    if layout_error:
        return None, None, layout_error
    context, context_error = validate_context(context_value)
    if context_error:
        return None, None, context_error
    locks, locks_error = validate_locks(layout, context, {}, locks_value or {})
    if locks_error:
        return None, None, locks_error

    seats = _seat_by_id(layout)
    assignment = dict(locks)
    assigned_students = set(assignment.values())
    available_seats = [seat for seat in layout["seats"] if seat["id"] not in assignment]
    random.shuffle(available_seats)
    keep_apart, preferred_pairs = _relationship_index(context)
    near_teacher_seats = set(layout["near_teacher_seat_ids"])

    remaining = [student for student in context["students"] if student["id"] not in assigned_students]
    random.shuffle(remaining)
    remaining.sort(key=lambda student: -(
        (student["front_row"] == "required") + (student["near_teacher"] == "required")
    ))

    def score(student: dict, seat: dict) -> int:
        student_id = student["id"]
        value = 0
        if student["front_row"] == "required":
            value += 1000 if seat["row"] == 1 else -1000
        elif student["front_row"] == "preferred" and seat["row"] == 1:
            value += 30
        if student["near_teacher"] == "required":
            value += 1000 if seat["id"] in near_teacher_seats else -1000
        elif student["near_teacher"] == "preferred" and seat["id"] in near_teacher_seats:
            value += 30
        for assigned_seat_id, assigned_student_id in assignment.items():
            adjacent = _are_adjacent(seats, seat["id"], assigned_seat_id)
            if assigned_student_id in keep_apart.get(student_id, set()) and adjacent:
                value -= 5000
            if assigned_student_id in preferred_pairs.get(student_id, set()) and adjacent:
                value += 40
        return value

    for student in remaining:
        if not available_seats:
            break
        best = max(available_seats, key=lambda seat: score(student, seat))
        assignment[best["id"]] = student["id"]
        available_seats.remove(best)
    results, results_error = evaluate(layout, context, assignment)
    if results_error:
        return None, None, results_error
    return assignment, results, None


def reroll(layout_value: object, context_value: object, proposal_value: object,
           locks_value: object, reroll_seat_ids: object) -> tuple[dict | None, dict | None, str | None]:
    """Reshuffle only selected, unlocked proposal seats; all other seats stay fixed."""
    layout, layout_error = _validated_layout(layout_value)
    if layout_error:
        return None, None, layout_error
    context, context_error = validate_context(context_value)
    if context_error:
        return None, None, context_error
    proposal, proposal_error = validate_assignment(layout, context, proposal_value)
    if proposal_error:
        return None, None, proposal_error
    locks, locks_error = validate_locks(layout, context, proposal, locks_value)
    if locks_error:
        return None, None, locks_error
    if not isinstance(reroll_seat_ids, list) or not reroll_seat_ids:
        return None, None, "select one or more unlocked proposal seats to reroll."
    valid_seats = {seat["id"] for seat in layout["seats"]}
    selected: set[str] = set()
    for seat_id_value in reroll_seat_ids:
        if not _valid_id(seat_id_value) or seat_id_value not in valid_seats or seat_id_value in selected:
            return None, None, "reroll selection has an invalid seat."
        if seat_id_value in locks:
            return None, None, "locked seats cannot be rerolled."
        selected.add(seat_id_value)
    fixed = {seat_id_value: student_id for seat_id_value, student_id in proposal.items()
             if seat_id_value not in selected}
    return generate(layout, context, fixed)

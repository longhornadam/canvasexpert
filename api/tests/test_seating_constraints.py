"""Generic-ID tests for local Seating constraint evaluation and proposals."""

from api import seating_constraints


def _layout():
    return {
        "id": "layout-a", "name": "Room", "rows": 2, "columns": 2,
        "seats": [
            {"id": "seat-1-1", "row": 1, "column": 1, "label": "1-1"},
            {"id": "seat-1-2", "row": 1, "column": 2, "label": "1-2"},
            {"id": "seat-2-1", "row": 2, "column": 1, "label": "2-1"},
            {"id": "seat-2-2", "row": 2, "column": 2, "label": "2-2"},
        ],
        "near_teacher_seat_ids": ["seat-1-2"],
    }


def _context():
    return {
        "section_id": "section-a",
        "students": [
            {"id": "student-a", "front_row": "required", "near_teacher": "none"},
            {"id": "student-b", "front_row": "none", "near_teacher": "required"},
            {"id": "student-c", "front_row": "preferred", "near_teacher": "none"},
            {"id": "student-d", "front_row": "none", "near_teacher": "preferred"},
        ],
        "relationships": [
            {"type": "keep_apart", "students": ["student-a", "student-b"]},
            {"type": "preferred_pair", "students": ["student-c", "student-d"]},
        ],
    }


def test_evaluate_reports_required_violations_separately_from_preferences():
    results, error = seating_constraints.evaluate(_layout(), _context(), {
        "seat-2-1": "student-a", "seat-2-2": "student-b",
    })

    assert error is None
    assert results["required_ok"] is False
    assert results["required_violations"] == [
        {"kind": "front_row_required", "student_id": "student-a"},
        {"kind": "keep_apart", "students": ["student-a", "student-b"]},
        {"kind": "near_teacher_required", "student_id": "student-b"},
    ]
    assert results["unmet_preferences"] == [
        {"kind": "front_row_preferred", "student_id": "student-c"},
        {"kind": "near_teacher_preferred", "student_id": "student-d"},
        {"kind": "preferred_pair", "students": ["student-c", "student-d"]},
    ]
    assert "reason" not in str(results)


def test_generation_preserves_valid_locks_and_reports_generic_results():
    proposal, results, error = seating_constraints.generate(
        _layout(), _context(), {"seat-1-1": "student-a"}
    )

    assert error is None
    assert proposal["seat-1-1"] == "student-a"
    assert len(set(proposal)) == len(proposal)
    assert len(set(proposal.values())) == len(proposal)
    assert set(proposal).issubset({seat["id"] for seat in _layout()["seats"]})
    assert set(proposal.values()).issubset({student["id"] for student in _context()["students"]})
    assert set(results) == {"required_ok", "required_violations", "unmet_preferences"}


def test_reroll_keeps_unselected_and_locked_positions_fixed():
    proposal = {
        "seat-1-1": "student-a", "seat-1-2": "student-b",
        "seat-2-1": "student-c", "seat-2-2": "student-d",
    }
    rerolled, results, error = seating_constraints.reroll(
        _layout(), _context(), proposal,
        {"seat-1-1": "student-a"}, ["seat-2-1", "seat-2-2"],
    )

    assert error is None
    assert rerolled["seat-1-1"] == "student-a"
    assert rerolled["seat-1-2"] == "student-b"
    assert set(results) == {"required_ok", "required_violations", "unmet_preferences"}


def test_context_and_assignment_reject_foreign_or_malformed_inputs():
    malformed_context = {**_context(), "relationships": [{
        "type": "keep_apart", "students": ["student-a", "student-z"],
    }]}
    assert seating_constraints.validate_context(malformed_context)[0] is None
    assert seating_constraints.validate_assignment(_layout(), _context(), {
        "seat-1-1": "student-z",
    })[0] is None
    assert seating_constraints.validate_assignment(_layout(), _context(), {
        "seat-9-9": "student-a",
    })[0] is None

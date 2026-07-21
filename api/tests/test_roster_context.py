"""Pure shared Roster context validation tests."""

from api import roster_context


def test_shared_normalizers_keep_existing_seating_and_score_shapes():
    assert roster_context.normalize_seating_context(None) == {
        "front_row": "none", "near_teacher": "none", "private_note": "", "ai_context_note": "",
    }
    assert roster_context._normalize_score_matrix({
        "columns": [{"id": "score-a", "label": "Writing"}],
        "values_by_section": {"section-a": {"student-a": {"score-a": 3}}},
    }) == {
        "columns": [{"id": "score-a", "label": "Writing"}],
        "values_by_section": {"section-a": {"student-a": {"score-a": 3}}},
    }


def test_relationships_canonicalize_pair_and_reject_duplicates_atomically():
    saved, error = roster_context.replace_section_relationships(
        {"by_section": {}}, "section-a", [{
            "student_a": "student-b", "student_b": "student-a",
            "type": "keep_apart", "reason": "private",
        }]
    )
    assert error is None
    assert saved == {"by_section": {"section-a": [{
        "student_a": "student-a", "student_b": "student-b",
        "type": "keep_apart", "reason": "private",
    }]}}

    unchanged, error = roster_context.replace_section_relationships(saved, "section-a", [
        {"student_a": "student-a", "student_b": "student-b", "type": "keep_apart", "reason": ""},
        {"student_a": "student-b", "student_b": "student-a", "type": "preferred_pair", "reason": ""},
    ])
    assert unchanged is None
    assert "duplicates" in error

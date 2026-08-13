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


# --------------------------------------------------------------------------
# Roster-change baseline: normalize, build, diff
# --------------------------------------------------------------------------


def test_normalize_roster_baseline_rejects_malformed_shapes_to_empty():
    assert roster_context.normalize_roster_baseline(None) == {"acknowledged_at": "", "students": {}}
    assert roster_context.normalize_roster_baseline({"students": {}}) == {"acknowledged_at": "", "students": {}}
    assert roster_context.normalize_roster_baseline({
        "acknowledged_at": "2026-08-01T00:00:00",
        "students": "not-a-dict",
    }) == {"acknowledged_at": "", "students": {}}


def test_normalize_roster_baseline_drops_invalid_ids_and_sorts_sections():
    normalized = roster_context.normalize_roster_baseline({
        "acknowledged_at": "2026-08-01T00:00:00",
        "students": {
            "101": ["44", "12"],
            "bad id": ["1"],
            "102": "not-a-list",
            "103": ["44", "bad section"],
        },
    })
    assert normalized == {
        "acknowledged_at": "2026-08-01T00:00:00",
        "students": {"101": ["12", "44"], "103": ["44"]},
    }


def test_build_roster_baseline_snapshots_current_sections():
    baseline = roster_context.build_roster_baseline(
        {"101": ["44"], "102": []}, acknowledged_at="2026-08-01T00:00:00")
    assert baseline == {
        "acknowledged_at": "2026-08-01T00:00:00",
        "students": {"101": ["44"], "102": []},
    }


def test_diff_roster_baseline_is_empty_when_never_acknowledged():
    diff = roster_context.diff_roster_baseline(
        {"acknowledged_at": "", "students": {}}, {"101", "102"}, {"101": ["44"]})
    assert diff == {"baseline_set": False, "added": [], "departed": [], "changed_section": []}

    # A missing/malformed baseline normalizes to the same unset shape.
    assert roster_context.diff_roster_baseline(None, {"101"}, {}) == {
        "baseline_set": False, "added": [], "departed": [], "changed_section": [],
    }


def test_diff_roster_baseline_finds_added_and_departed():
    baseline = roster_context.build_roster_baseline(
        {"101": ["44"], "102": ["44"]}, acknowledged_at="2026-08-01T00:00:00")
    diff = roster_context.diff_roster_baseline(
        baseline, {"101", "103"}, {"101": ["44"], "103": ["55"]})
    assert diff["baseline_set"] is True
    assert diff["added"] == ["103"]
    assert diff["departed"] == ["102"]
    assert diff["changed_section"] == []


def test_diff_roster_baseline_reports_clean_swap_and_ambiguous_changes():
    baseline = roster_context.build_roster_baseline(
        {"101": ["44"], "102": ["44"], "103": ["44"]}, acknowledged_at="2026-08-01T00:00:00")
    diff = roster_context.diff_roster_baseline(baseline, {"101", "102", "103"}, {
        "101": ["55"],          # clean one-for-one swap
        "102": ["44", "55"],    # gained a section without losing the old one
        "103": ["44"],          # unchanged
    })
    changed_by_id = {item["student_id"]: item for item in diff["changed_section"]}
    assert set(changed_by_id) == {"101", "102"}
    assert changed_by_id["101"] == {
        "student_id": "101", "old_section_ids": ["44"], "new_section_ids": ["55"], "clean_swap": True,
    }
    assert changed_by_id["102"]["clean_swap"] is False
    assert changed_by_id["102"]["old_section_ids"] == []
    assert changed_by_id["102"]["new_section_ids"] == ["55"]
    assert diff["added"] == []
    assert diff["departed"] == []


def test_diff_roster_baseline_ignores_students_missing_from_current_sections():
    baseline = roster_context.build_roster_baseline(
        {"101": []}, acknowledged_at="2026-08-01T00:00:00")
    diff = roster_context.diff_roster_baseline(baseline, {"101"}, {})
    assert diff == {"baseline_set": True, "added": [], "departed": [], "changed_section": []}

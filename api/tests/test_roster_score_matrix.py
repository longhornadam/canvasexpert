"""Focused tests for local, current-only Roster score-matrix normalization."""

from api.webui.routes import roster as roster_routes


def test_column_rename_retains_values_and_removal_prunes_every_section():
    matrix = {
        "columns": [
            {"id": "score-writing", "label": "Writing"},
            {"id": "score-reading", "label": "Reading"},
        ],
        "values_by_section": {
            "section-a": {"student-a": {"score-writing": 3, "score-reading": 4}},
            "section-b": {"student-b": {"score-writing": 5, "score-reading": 6}},
        },
    }

    renamed, error = roster_routes._apply_score_matrix_patch(matrix, {
        "columns": [
            {"id": "score-writing", "label": "Draft writing"},
            {"id": "score-reading", "label": "Reading"},
        ],
    })
    removed, error_after_removal = roster_routes._apply_score_matrix_patch(renamed, {
        "columns": [{"id": "score-reading", "label": "Reading"}],
    })

    assert error is None
    assert renamed["values_by_section"]["section-a"]["student-a"]["score-writing"] == 3
    assert error_after_removal is None
    assert removed == {
        "columns": [{"id": "score-reading", "label": "Reading"}],
        "values_by_section": {
            "section-a": {"student-a": {"score-reading": 4}},
            "section-b": {"student-b": {"score-reading": 6}},
        },
    }


def test_bulk_values_preserve_other_sections_and_sparse_clears():
    matrix = {
        "columns": [{"id": "score-current", "label": "Current score"}],
        "values_by_section": {"section-b": {"student-b": {"score-current": 8}}},
    }

    saved, error = roster_routes._apply_score_matrix_patch(matrix, {
        "section_id": "section-a",
        "values": {
            "student-a": {"score-current": 0},
            "student-c": {"score-current": 12.5},
        },
    })
    cleared, clear_error = roster_routes._apply_score_matrix_patch(saved, {
        "section_id": "section-a",
        "values": {"student-a": {"score-current": None}},
    })

    assert error is None
    assert saved["values_by_section"]["section-a"]["student-a"]["score-current"] == 0
    assert saved["values_by_section"]["section-b"]["student-b"]["score-current"] == 8
    assert clear_error is None
    assert "student-a" not in cleared["values_by_section"]["section-a"]
    assert cleared["values_by_section"]["section-a"]["student-c"]["score-current"] == 12.5


def test_malformed_matrix_and_nonfinite_values_are_rejected_without_candidate():
    matrix = {
        "columns": [{"id": "score-current", "label": "Current score"}],
        "values_by_section": {},
    }

    malformed, malformed_error = roster_routes._apply_score_matrix_patch(matrix, {
        "columns": [{"id": "score-current", "label": ""}],
    })
    nonfinite, nonfinite_error = roster_routes._apply_score_matrix_patch(matrix, {
        "section_id": "section-a",
        "values": {"student-a": {"score-current": float("inf")}},
    })

    assert malformed is None
    assert "blank" in malformed_error.lower()
    assert nonfinite is None
    assert "finite" in nonfinite_error.lower()

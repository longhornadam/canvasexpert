from api.dataforge.canvas_join import build_coverage_report


def test_coverage_uses_only_local_id_to_sis_id_and_distinguishes_join_states():
    report = build_coverage_report(
        {
            "Student_A": {"latest_pct": 82.0},
            "Student_B": {"latest_pct": 61.0},
            "Student_C": {"latest_pct": 44.0},
            "Student_D": {"latest_pct": 91.0},
        },
        {
            "Student_A": "SIS-1",
            "Student_B": "SIS-missing",
            "Student_C": "SIS-duplicate",
        },
        [
            {"id": "canvas-1", "name": "Synthetic One", "sis_user_id": "SIS-1"},
            {"id": "canvas-2", "name": "Synthetic Two", "sis_user_id": "SIS-duplicate"},
            {"id": "canvas-3", "name": "Synthetic Three", "sis_user_id": "SIS-duplicate"},
            {"id": "canvas-4", "name": "Synthetic Four", "sis_user_id": "SIS-roster-only"},
            {"id": "canvas-5", "name": "Name Does Not Matter", "sis_user_id": "SIS-name-only"},
        ],
    )

    rows = {row["pseudonym"]: row for row in report["rows"]}
    assert rows["Student_A"]["status"] == "matched"
    assert rows["Student_A"]["canvas_id"] == "canvas-1"
    assert rows["Student_B"]["status"] == "not_in_roster"
    assert rows["Student_C"]["status"] == "ambiguous_roster"
    assert rows["Student_D"]["status"] == "missing_local_id"
    assert report["profile_student_count"] == 4
    assert report["linked_student_count"] == 3
    assert report["matched_count"] == 1
    assert report["missing_local_id_count"] == 1
    assert report["not_in_roster_count"] == 1
    assert report["ambiguous_roster_count"] == 1
    assert report["roster_student_count"] == 5
    assert report["roster_only_count"] == 2
    assert report["coverage_percent"] == 25.0


def test_coverage_empty_profile_is_explicit_and_does_not_fallback_to_names():
    report = build_coverage_report(
        {"Student_A": {"latest_pct": 70.0}},
        {"Student_A": ""},
        [{"id": "canvas-1", "name": "Student_A", "sis_user_id": "SIS-1"}],
    )

    assert report["matched_count"] == 0
    assert report["missing_local_id_count"] == 1
    assert report["rows"][0]["status"] == "missing_local_id"
    assert report["rows"][0]["canvas_id"] == ""

"""Pure academic Seating grouping tests with synthetic IDs and finite values only."""

from api import seating_grouping


def _layout(rows=2, columns=4):
    return {
        "id": "layout-a", "name": "Room", "rows": rows, "columns": columns,
        "seats": [
            {"id": f"seat-{row}-{column}", "row": row, "column": column, "label": f"{row}-{column}"}
            for row in range(1, rows + 1) for column in range(1, columns + 1)
        ],
        "near_teacher_seat_ids": [],
    }


def _context(ids, relationships=None, required_front=False):
    return {
        "section_id": "section-a",
        "students": [{
            "id": student_id,
            "front_row": "required" if required_front and student_id == ids[0] else "none",
            "near_teacher": "none",
        } for student_id in ids],
        "relationships": relationships or [],
    }


def _academic(scores=None, column="score-a", mentors=None):
    return {"score_column_id": column, "scores": scores or {}, "mentor_ready": mentors or []}


def test_seat_clusters_are_deterministic_edge_connected_and_allow_a_partial_final_cluster():
    layout = _layout(rows=3, columns=4)
    first, error = seating_grouping.seat_clusters(layout, 3)
    second, second_error = seating_grouping.seat_clusters(layout, 3)

    assert error is None and second_error is None
    assert first == second
    assert first[0] == ["seat-1-1", "seat-1-2", "seat-1-3"]
    assert all(1 <= len(cluster) <= 3 for cluster in first)


def test_buddy_pairs_prefer_relationships_and_random_trios_report_a_partial_group():
    ids = ["student-a", "student-b", "student-c", "student-d", "student-e"]
    buddy_context = _context(ids[:4], [{"type": "preferred_pair", "students": ["student-a", "student-b"]}])
    assignment, results, grouping, error = seating_grouping.generate(
        _layout(), buddy_context, "buddy_pairs", _academic(column=""), {}
    )

    assert error is None and results["required_ok"] is True
    assert assignment and {"student-a", "student-b"} in [set(group["student_ids"]) for group in grouping["groups"]]
    assert grouping["groups"][0]["kind"] == "buddy_pair"

    _, _, trios, error = seating_grouping.generate(
        _layout(rows=2, columns=3), _context(ids), "random_trios", _academic(column=""), {}
    )
    assert error is None
    assert sorted(len(group["student_ids"]) for group in trios["groups"]) == [2, 3]
    assert {"kind": "partial_groups", "group_size": 3, "count": 1} in trios["notices"]


def test_mixed_and_uniform_fours_keep_generic_groups_and_report_missing_scores():
    ids = [f"student-{letter}" for letter in "abcdefgh"]
    scores = {student_id: index + 1 for index, student_id in enumerate(ids)}
    mixed_assignment, _, mixed, error = seating_grouping.generate(
        _layout(), _context(ids), "mixed_fours", _academic(scores), {}
    )
    uniform_assignment, _, uniform, uniform_error = seating_grouping.generate(
        _layout(), _context(ids), "uniform_fours", _academic(scores), {}
    )

    assert error is None and uniform_error is None
    assert mixed_assignment and uniform_assignment
    mixed_values = {scores[student_id] for student_id in mixed["groups"][0]["student_ids"]}
    uniform_values = {scores[student_id] for student_id in uniform["groups"][0]["student_ids"]}
    assert mixed_values == {1, 2, 7, 8}
    assert uniform_values == {1, 2, 3, 4}
    assert all("score" not in group and "name" not in group for group in mixed["groups"])

    _, _, with_missing, missing_error = seating_grouping.generate(
        _layout(), _context(ids), "mixed_fours", _academic({student_id: score for student_id, score in scores.items() if score != 8}), {}
    )
    assert missing_error is None
    assert {"kind": "unscored", "count": 1} in with_missing["notices"]


def test_mentor_pairs_require_an_explicit_temporary_candidate_and_preserve_locks():
    ids = ["student-a", "student-b", "student-c", "student-d"]
    scores = {"student-a": 10, "student-b": 2, "student-c": 7}
    assignment, _, grouping, error = seating_grouping.generate(
        _layout(rows=2, columns=2), _context(ids), "mentor_pairs", _academic(scores, mentors=["student-a"]),
        {"seat-1-1": "student-a"},
    )
    _, _, no_candidate, no_candidate_error = seating_grouping.generate(
        _layout(rows=2, columns=2), _context(ids), "mentor_pairs", _academic(scores), {},
    )

    assert error is None and no_candidate_error is None
    assert assignment["seat-1-1"] == "student-a"
    assert {"student-a", "student-b"} in [
        set(group["student_ids"]) for group in grouping["groups"] if group["kind"] == "mentor_pair"
    ]
    assert not [group for group in no_candidate["groups"] if group["kind"] == "mentor_pair"]

    _, required_results, _, required_error = seating_grouping.generate(
        _layout(rows=2, columns=2), _context(ids, required_front=True), "testing", _academic(column=""),
        {"seat-2-1": "student-a"},
    )
    assert required_error is None
    assert required_results["required_ok"] is False


def test_academic_projection_rejects_foreign_scores_and_never_accepts_mentor_data_for_other_strategies():
    context = _context(["student-a", "student-b"])
    invalid_score, score_error = seating_grouping.validate_academic_context(
        _academic({"student-z": 4}), context, "mixed_fours"
    )
    invalid_mentor, mentor_error = seating_grouping.validate_academic_context(
        _academic({"student-a": 4}, mentors=["student-a"]), context, "uniform_fours"
    )

    assert invalid_score is None and "invalid score" in score_error
    assert invalid_mentor is None and "only mentor pairs" in mentor_error

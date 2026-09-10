"""Direct gradebook aggregation laws, using synthetic records."""
from api.gradebook_snapshot import build_snapshot


def test_snapshot_counts_only_roster_work_and_sums_student_ungraded():
    students = [{"id": i, "name": f"Learner {i}"} for i in range(1, 7)]
    assignments = [{"id": 10, "points_possible": 10},
                   {"id": 11, "published": False}]
    subs = [
        {"user_id": 1, "workflow_state": "submitted", "submitted_at": "2026-09-01"},
        {"user_id": 2, "workflow_state": "pending_review", "submitted_at": "2026-09-01"},
        {"user_id": 3, "workflow_state": "graded", "score": 8},
        {"user_id": 4, "workflow_state": "graded", "score": 6},
        {"user_id": 5, "workflow_state": "submitted", "submitted_at": "2026-09-01",
         "excused": True, "missing": True, "late": True},
        {"user_id": 99, "workflow_state": "graded", "score": 0,
         "submitted_at": "2026-09-01", "missing": True, "late": True},
        {"user_id": 100, "workflow_state": "submitted", "submitted_at": "2026-09-01"},
    ]
    subs = [{"assignment_id": 10, **sub} for sub in subs]
    subs.append({"assignment_id": 11, "user_id": 6, "workflow_state": "submitted",
                 "submitted_at": "2026-09-01", "missing": True, "late": True})

    result = build_snapshot(students, assignments, subs)

    assert result["total_ungraded"] == sum(s["ungraded"] for s in result["students"]) == 2
    assert result["total_missing"] == 0
    assert result["class_avg"] == 70
    assignment, = result["assignments"]
    assert (assignment["submitted"], assignment["graded"], assignment["avg_pct"]) == (2, 2, 70)
    assert (assignment["missing"], assignment["late"]) == (0, 0)

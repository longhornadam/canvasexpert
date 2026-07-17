"""Synthetic CanvasMirror v2 New Quiz coverage; no live identifiers or data."""
from __future__ import annotations

import json
import os

from api.mirror import new_quizzes
from api.powergrader import assignment_refresh, canvas_fetch, new_quiz_fetch
from api.webui import config, workspace


COURSE = "course-synthetic"
ASSIGNMENT = "quiz-synthetic"
NOW = "2026-07-16T12:00:00Z"


def _assignment():
    return {
        "id": ASSIGNMENT, "name": "Fictional Quiz", "description": "Explain.",
        "points_possible": 10, "published": True,
        "is_quiz_lti_assignment": True, "submission_types": ["external_tool"],
    }


def _items():
    return [{
        "id": "outer-essay", "points_possible": 10,
        "entry": {"id": "essay-1", "interaction_type_slug": "essay",
                   "item_body": "<p>Explain the fictional result.</p>"},
    }]


def _attempt(attempt, answer, *, result_id="", evidence=None, submitted=None):
    return {
        "user_id": "student-synthetic", "user": {"name": "Fictional Student"},
        "workflow_state": "submitted", "submission_type": "external_tool",
        "submitted_at": submitted or f"2026-07-{attempt:02d}T10:00:00Z",
        "body": answer, "new_quiz_attempt": attempt,
        "new_quiz_reported_at": submitted or f"2026-07-{attempt:02d}T10:00:00Z",
        "new_quiz_items": [{"item_id": "essay-1", "type": "essay",
                             "prompt": "Prompt", "raw_html_answer": answer,
                             "possible": 10, "earned_score": attempt,
                             "status": "NotGraded", "files": []}],
        "attachments": evidence or [],
        "new_quiz_result_identity": ({"quiz_session_id": f"session-{attempt}",
                                       "result_id": result_id} if result_id else {}),
        "assignment": _assignment(),
    }


def test_snapshot_retains_attempts_identity_and_relative_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    evidence_path = tmp_path / "Courses" / "answer.txt"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("synthetic", encoding="utf-8")
    latest = _attempt(2, "latest", result_id="result-2", evidence=[{
        "filename": "answer.txt", "item_id": "essay-1", "evidence_id": "file-2",
        "local_path": str(evidence_path), "download_status": "downloaded",
        "extraction_status": "validated", "url": "https://signed.invalid/file",
    }])
    older = _attempt(1, "older", result_id="result-1")

    result = new_quizzes.write_response_snapshot(
        COURSE, ASSIGNMENT, assignment=_assignment(), items=_items(),
        normalized_attempts=[older, latest], latest=[latest], root=str(tmp_path),
        attempted_at=NOW,
    )
    assert result == {"ok": True, "state": "current", "students": 1, "attempts": 2}
    student = new_quizzes.read_student(COURSE, ASSIGNMENT, "student-synthetic", root=str(tmp_path))
    assert [entry["attempt"] for entry in student["attempts"]] == [1, 2]
    assert student["current"]["attempt"] == 2
    assert student["current"]["result_identity"]["result_id"] == "result-2"
    assert student["current"]["evidence"][0]["relative_path"] == os.path.relpath(evidence_path, tmp_path)
    raw = json.dumps(student)
    assert "signed.invalid" not in raw and "url" not in raw

    snapshot, error = new_quizzes.read_fresh_snapshot(
        COURSE, ASSIGNMENT, root=str(tmp_path), max_age_hours=6, now=NOW,
    )
    assert error is None and snapshot["source"] == "mirror"
    assert snapshot["students"][0]["new_quiz_attempt"] == 2


def test_duplicate_or_stale_snapshots_fail_closed(tmp_path):
    duplicate = _attempt(1, "one", result_id="result-1")
    duplicate_again = _attempt(1, "one-again", result_id="result-1b")
    result = new_quizzes.write_response_snapshot(
        COURSE, ASSIGNMENT, assignment=_assignment(), items=_items(),
        normalized_attempts=[duplicate, duplicate_again], latest=[duplicate],
        root=str(tmp_path), attempted_at=NOW,
    )
    assert result["state"] == "incomplete"
    snapshot, error = new_quizzes.read_fresh_snapshot(
        COURSE, ASSIGNMENT, root=str(tmp_path), max_age_hours=6, now=NOW,
    )
    assert snapshot is None and error == "incomplete"

    current = _attempt(1, "current", result_id="result-current")
    new_quizzes.write_response_snapshot(
        COURSE, ASSIGNMENT, assignment=_assignment(), items=_items(),
        normalized_attempts=[current], latest=[current], root=str(tmp_path),
        attempted_at="2026-07-01T12:00:00Z",
    )
    snapshot, error = new_quizzes.read_fresh_snapshot(
        COURSE, ASSIGNMENT, root=str(tmp_path), max_age_hours=6, now=NOW,
    )
    assert snapshot is None and error == "stale"


def test_corrupt_v2_files_are_absent_and_identical_refresh_is_idempotent(tmp_path):
    os.makedirs(os.path.dirname(new_quizzes.quiz_path(COURSE, ASSIGNMENT, str(tmp_path))), exist_ok=True)
    with open(new_quizzes.quiz_path(COURSE, ASSIGNMENT, str(tmp_path)), "w", encoding="utf-8") as handle:
        handle.write("not-json")
    assert new_quizzes.read_quiz(COURSE, ASSIGNMENT, root=str(tmp_path)) is None

    row = _attempt(1, "same", result_id="result-same")
    kwargs = {
        "assignment": _assignment(), "items": _items(),
        "normalized_attempts": [row], "latest": [row],
        "root": str(tmp_path), "attempted_at": NOW,
    }
    new_quizzes.write_response_snapshot(COURSE, ASSIGNMENT, **kwargs)
    first = (tmp_path / "_System" / "Canvas Mirror" / COURSE / "new_quizzes" /
             ASSIGNMENT / "students" / "student-synthetic.v2.json").read_text(encoding="utf-8")
    new_quizzes.write_response_snapshot(COURSE, ASSIGNMENT, **kwargs)
    second = (tmp_path / "_System" / "Canvas Mirror" / COURSE / "new_quizzes" /
              ASSIGNMENT / "students" / "student-synthetic.v2.json").read_text(encoding="utf-8")
    assert first == second


def test_stale_or_incomplete_cache_falls_back_to_focused_consumer(monkeypatch, tmp_path):
    monkeypatch.setattr(assignment_refresh.workspace, "workspace_root", lambda: str(tmp_path))
    monkeypatch.setattr(assignment_refresh.workspace, "read_assignment_evidence_manifest", lambda *args: None)
    monkeypatch.setattr(assignment_refresh.workspace, "assignment_evidence_conflicts", lambda *args: [])
    monkeypatch.setattr(assignment_refresh.workspace, "write_assignment_evidence_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr(config, "course_display_name", lambda _course_id: "Fictional Course")
    monkeypatch.setattr(config, "mirror_serve_max_age_hours", lambda: 6.0)
    calls = []

    def focused(course_id, assignment_id, **kwargs):
        calls.append(kwargs)
        return ([{"user_id": "student-synthetic", "submission_type": "online_text_entry"}],
                {"id": assignment_id, "name": "Fictional Assignment", "is_quiz_lti_assignment": False}, None)

    monkeypatch.setattr(assignment_refresh.canvas_fetch, "fetch_submissions", focused)
    for state in ("stale", "incomplete"):
        monkeypatch.setattr(assignment_refresh.new_quizzes, "read_fresh_snapshot", lambda *args, _state=state, **kwargs: (None, _state))
        assignment_refresh.refresh_assignment(COURSE, ASSIGNMENT, session_id=f"session-{state}")
        assert "cached_new_quiz" not in calls[-1]


def test_metadata_sync_is_separate_and_prunes_only_after_complete_pass(tmp_path):
    calls = []

    def canvas(path, params=None, timeout=30):
        calls.append(path)
        if path.endswith(f"/quizzes/{ASSIGNMENT}"):
            return ([{"id": ASSIGNMENT, "title": "Fictional Quiz", "points_possible": 10}], None)
        if path.endswith("/items"):
            return (_items(), None)
        raise AssertionError(path)

    result = new_quizzes.sync_metadata(
        COURSE, [_assignment()], canvas_get_all=canvas, root=str(tmp_path), now=NOW,
    )
    assert result["ok"] is True and result["quizzes"] == 1
    quiz = new_quizzes.read_quiz(COURSE, ASSIGNMENT, root=str(tmp_path))
    assert quiz["quiz"]["title"] == "Fictional Quiz"
    assert quiz["items"]["essay-1"]["points_possible"] == 10
    assert calls == [
        f"/api/quiz/v1/courses/{COURSE}/quizzes/{ASSIGNMENT}",
        f"/api/quiz/v1/courses/{COURSE}/quizzes/{ASSIGNMENT}/items",
    ]


def test_malformed_item_join_and_unmatched_attempt_are_explicit(tmp_path):
    malformed = _attempt(1, "answer")
    malformed["new_quiz_items"][0]["item_id"] = "item-not-in-catalog"
    unmatched = _attempt(2, "unmatched")
    unmatched["user_id"] = "student-unmatched"
    unmatched["new_quiz_join_state"] = "unmatched"
    unmatched["new_quiz_join_error"] = "student_submission_missing"
    result = new_quizzes.write_response_snapshot(
        COURSE, ASSIGNMENT, assignment=_assignment(), items=_items(),
        normalized_attempts=[malformed, unmatched], latest=[malformed],
        root=str(tmp_path), attempted_at=NOW,
    )
    assert result["state"] == "incomplete"
    student = new_quizzes.read_student(COURSE, ASSIGNMENT, "student-synthetic", root=str(tmp_path))
    assert student["attempts"][0]["join_state"] == "incomplete"
    unmatched_doc = new_quizzes.read_student(COURSE, ASSIGNMENT, "student-unmatched", root=str(tmp_path))
    assert unmatched_doc["attempts"][0]["join_error"] == "student_submission_missing"


def test_cached_new_quiz_path_skips_core_and_report_reads(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    monkeypatch.setattr(new_quiz_fetch, "_canvas_headers", lambda: ({"Authorization": "synthetic"}, "https://canvas.invalid"))
    monkeypatch.setattr(canvas_fetch, "_canvas_get_all", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("core read")))
    monkeypatch.setattr(canvas_fetch, "_canvas_get", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("assignment read")))

    cached = {
        "source": "mirror", "assignment": _assignment(),
        "students": [_attempt(2, "cached", result_id="result-cached")],
    }
    subs, assignment, error = canvas_fetch.fetch_submissions(
        COURSE, ASSIGNMENT, session_id="session-synthetic", cached_new_quiz=cached,
        new_quiz_files=False,
    )
    assert error is None and assignment["is_quiz_lti_assignment"] is True
    assert subs[0]["new_quiz_attempt"] == 2
    assert subs[0]["body"] == "cached"

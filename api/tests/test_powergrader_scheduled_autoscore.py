from __future__ import annotations

from api.webui.routes import routines


def _queue_job(**overrides):
    job = {
        "job_id": "course-1_assign-1",
        "course_id": "course-1",
        "course_name": "Period 1",
        "assignment_id": "assign-1",
        "assignment_name": "Essay 1",
        "status": "scheduled",
        "eligibility": "eligible",
        "reason": "text entry gives PowerGrader readable response text",
        "due_at": "2026-06-28T23:59:00-05:00",
        "delay_hours": 6,
        "scheduled_at": "2026-06-29T05:59:00-05:00",
        "auto_push": False,
        "push_policy": {
            "enabled": False,
            "allow_grade_push": True,
            "allow_comment_push": True,
            "policy_version": 1,
        },
        "assignment": {
            "name": "Essay 1",
            "submission_types": ["online_text_entry"],
            "allowed_extensions": [],
        },
        "settings": {
            "model_id": "model-a",
            "persona_id": "sage",
            "response_kind": "scr",
            "rubric_name": "",
            "watch_late": False,
        },
        "session_id": "",
        "last_error": "",
    }
    job.update(overrides)
    return job


def test_scheduled_autoscore_reschedules_when_due_date_moves_later(monkeypatch):
    queue = {"version": 1, "jobs": [_queue_job()]}
    job = queue["jobs"][0]

    monkeypatch.setattr(routines.autoscore_queue, "load_queue", lambda: queue)
    monkeypatch.setattr(routines.autoscore_queue, "due_jobs", lambda q, now=None: q["jobs"])
    monkeypatch.setattr(routines.autoscore_queue, "save_queue", lambda q: None)
    monkeypatch.setattr(routines.canvas_fetch, "fetch_submissions", lambda course_id, assignment_id: ([], {
        "name": "Essay 1",
        "submission_types": ["online_text_entry"],
        "due_at": "2026-07-02T23:59:00-05:00",
    }, None))
    monkeypatch.setattr(routines, "_canvas_send", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("scheduled autoscore must not write grades/comments")))
    monkeypatch.setattr(routines.ai_workflow, "run_ai_workflow", lambda **kwargs: (_ for _ in ()).throw(AssertionError("rescheduled jobs must not create a session")))
    monkeypatch.setattr(routines.session_store, "save_session", lambda session: (_ for _ in ()).throw(AssertionError("rescheduled jobs must not save a session")))

    result = routines._run_routine_powergrader_scheduled_autoscore({"max_jobs": 10})

    assert result["ok"] is True
    assert any("rescheduled" in line for line in result["lines"])
    assert job["scheduled_at"] == "2026-07-03T05:59:00-05:00"
    assert job["status"] == "scheduled"
    assert job["reason"] == "text entry gives PowerGrader readable response text"


def test_scheduled_autoscore_creates_draft_session_without_canvas_writeback(monkeypatch):
    queue = {"version": 1, "jobs": [_queue_job()]}
    job = queue["jobs"][0]
    saved_sessions = []
    ai_calls = []

    monkeypatch.setattr(routines.config, "has_openrouter_key", lambda: True)
    monkeypatch.setattr(routines.config, "get_openrouter_model", lambda: "model-a")
    monkeypatch.setattr(routines.config, "get_roster_student_settings", lambda course_id: {})
    monkeypatch.setattr(routines.config, "roster_tier_by_id", lambda course_id: {})
    monkeypatch.setattr(routines.config, "get_monitored_students", lambda: {})
    monkeypatch.setattr(routines.config, "get_extra_time", lambda course_id: [])
    monkeypatch.setattr(routines.autoscore_queue, "load_queue", lambda: queue)
    monkeypatch.setattr(routines.autoscore_queue, "due_jobs", lambda q, now=None: q["jobs"])
    monkeypatch.setattr(routines.autoscore_queue, "save_queue", lambda q: None)
    monkeypatch.setattr(routines.canvas_fetch, "fetch_submissions", lambda course_id, assignment_id: ([
        {
            "user_id": "1",
            "submission_type": "online_text_entry",
            "workflow_state": "submitted",
            "user": {"name": "Student One", "sortable_name": "Student One"},
        }
    ], {
        "name": "Essay 1",
        "description": "<p>Explain the text.</p>",
        "submission_types": ["online_text_entry"],
        "due_at": "2026-06-28T23:59:00-05:00",
        "points_possible": 10,
    }, None))
    monkeypatch.setattr(routines.canvas_fetch, "enrich_with_code_files", lambda subs: None)
    monkeypatch.setattr(routines, "_canvas_send", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("scheduled autoscore must not write grades/comments")))
    monkeypatch.setattr(routines.autopush_executor, "run_autopush_for_session", lambda **kwargs: (_ for _ in ()).throw(AssertionError("draft-only autoscore must not invoke autopush executor")))

    def fake_run_ai_workflow(**kwargs):
        ai_calls.append(kwargs)
        return {
            "ok": True,
            "error": "",
            "status_code": 200,
            "privacy_steps": [],
            "privacy_artifacts": {},
            "ai_by_uid": {"1": {"score": 9, "feedback": "Strong work."}},
            "packet_zip": None,
            "budget": None,
            "debug_path": None,
            "copilot_packet": None,
            "source_context": {"materials": []},
        }

    monkeypatch.setattr(routines.ai_workflow, "run_ai_workflow", fake_run_ai_workflow)
    monkeypatch.setattr(routines.session_store, "save_session", lambda session: saved_sessions.append(session.copy()))

    result = routines._run_routine_powergrader_scheduled_autoscore({"max_jobs": 10})

    assert result["ok"] is True
    assert any("created PowerGrader draft session" in line for line in result["lines"])
    assert ai_calls[0]["assignment_name"] == "Essay 1"
    assert saved_sessions[0]["mode"] == "assisted"
    assert saved_sessions[0]["students"][0]["user_id"] == "1"
    assert saved_sessions[0]["late_watch"]["enabled"] is False
    assert saved_sessions[0]["late_watch"]["initial_missing_user_ids"] == []
    assert saved_sessions[0]["late_watch"]["known_user_ids"] == ["1"]
    assert saved_sessions[0]["late_watch"]["source_context"] == {"materials": []}
    assert job["status"] == "session_ready"
    assert job["session_id"]
    assert job["last_error"] == ""
    assert job["auto_push"] is False


def test_scheduled_autoscore_runs_autopush_when_enabled(monkeypatch):
    queue = {"version": 1, "jobs": [_queue_job(auto_push=True, push_policy={
        "enabled": True,
        "allow_grade_push": True,
        "allow_comment_push": True,
        "policy_version": 1,
    })]}
    job = queue["jobs"][0]
    saved_sessions = []
    executor_calls = []

    monkeypatch.setattr(routines.config, "has_openrouter_key", lambda: True)
    monkeypatch.setattr(routines.config, "get_openrouter_model", lambda: "model-a")
    monkeypatch.setattr(routines.config, "get_roster_student_settings", lambda course_id: {})
    monkeypatch.setattr(routines.config, "roster_tier_by_id", lambda course_id: {})
    monkeypatch.setattr(routines.config, "get_monitored_students", lambda: {})
    monkeypatch.setattr(routines.config, "get_extra_time", lambda course_id: [])
    monkeypatch.setattr(routines.autoscore_queue, "load_queue", lambda: queue)
    monkeypatch.setattr(routines.autoscore_queue, "due_jobs", lambda q, now=None: q["jobs"])
    monkeypatch.setattr(routines.autoscore_queue, "save_queue", lambda q: None)
    monkeypatch.setattr(routines.canvas_fetch, "fetch_submissions", lambda course_id, assignment_id: ([
        {
            "user_id": "1",
            "submission_type": "online_text_entry",
            "workflow_state": "submitted",
            "score": 7,
            "submission_comments": [{"comment": "Existing note"}],
            "user": {"name": "Student One", "sortable_name": "Student One"},
        }
    ], {
        "name": "Essay 1",
        "description": "<p>Explain the text.</p>",
        "submission_types": ["online_text_entry"],
        "due_at": "2026-06-28T23:59:00-05:00",
        "points_possible": 10,
    }, None))
    monkeypatch.setattr(routines.canvas_fetch, "enrich_with_code_files", lambda subs: None)
    monkeypatch.setattr(routines, "_canvas_send", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("scheduled autoscore must not write grades/comments directly")))

    def fake_run_autopush_for_session(**kwargs):
        executor_calls.append(kwargs)
        session = kwargs["session"]
        session["students"][0]["posted"] = True
        session["students"][0]["autopush_idempotency_key"] = "pg-autopush:v1:course-1:assign-1:1:1:7:abc"
        session["students"][0]["autopush_receipt_id"] = "receipt-1"
        return {
            "ok": True,
            "pushed": 1,
            "needs_review": 0,
            "blocked": 0,
            "errors": [],
            "student_results": [{
                "user_id": "1",
                "decision": "auto_push_allowed",
                "reason": "",
                "receipt_id": "receipt-1",
                "idempotency_key": "pg-autopush:v1:course-1:assign-1:1:1:7:abc",
            }],
            "receipts": [{"receipt_id": "receipt-1"}],
        }

    monkeypatch.setattr(routines.autopush_executor, "run_autopush_for_session", fake_run_autopush_for_session)
    monkeypatch.setattr(routines.ai_workflow, "run_ai_workflow", lambda **kwargs: {
        "ok": True,
        "error": "",
        "status_code": 200,
        "privacy_steps": [],
        "privacy_artifacts": {},
        "ai_by_uid": {"1": {"score": 7, "feedback": "Strong work."}},
        "packet_zip": None,
        "budget": None,
        "debug_path": None,
        "copilot_packet": None,
        "source_context": {"materials": []},
    })
    monkeypatch.setattr(routines.session_store, "save_session", lambda session: saved_sessions.append(session.copy()))

    result = routines._run_routine_powergrader_scheduled_autoscore({"max_jobs": 10})

    assert result["ok"] is True
    assert executor_calls
    assert executor_calls[0]["receipt_dir"].endswith("\\_private\\autopush_receipts\\course-1_assign-1")
    assert executor_calls[0]["canvas_states_by_user"]["1"]["existing_score"] == 7
    assert job["status"] == "auto_pushed"
    assert job["push_summary"]["pushed"] == 1
    assert job["student_decisions"][0]["decision"] == "auto_push_allowed"
    assert saved_sessions[-1]["students"][0]["posted"] is True


def test_scheduled_autoscore_runs_autopush_for_existing_session(monkeypatch):
    existing_session = {
        "session_id": "existing-session",
        "course_id": "course-1",
        "assignment_id": "assign-1",
        "students": [{
            "user_id": "1",
            "body": "Answer",
            "ai_score": 7,
            "ai_feedback": "Good work.",
            "posted": False,
        }],
        "late_watch": {"source_context": {}},
    }
    queue = {"version": 1, "jobs": [_queue_job(
        status="session_ready",
        session_id="existing-session",
        auto_push=True,
        push_policy={
            "enabled": True,
            "allow_grade_push": True,
            "allow_comment_push": True,
            "policy_version": 1,
        },
    )]}
    job = queue["jobs"][0]
    save_calls = []
    executor_calls = []

    monkeypatch.setattr(routines.config, "has_openrouter_key", lambda: True)
    monkeypatch.setattr(routines.autoscore_queue, "load_queue", lambda: queue)
    monkeypatch.setattr(routines.autoscore_queue, "save_queue", lambda q: save_calls.append([j.copy() for j in q["jobs"]]))
    monkeypatch.setattr(routines.canvas_fetch, "fetch_submissions", lambda course_id, assignment_id: ([{
        "user_id": "1",
        "submission_type": "online_text_entry",
        "workflow_state": "submitted",
    }], {
        "name": "Essay 1",
        "description": "<p>Explain the text.</p>",
        "submission_types": ["online_text_entry"],
        "due_at": "2026-06-28T23:59:00-05:00",
        "points_possible": 10,
    }, None))
    monkeypatch.setattr(routines.canvas_fetch, "enrich_with_code_files", lambda subs: None)
    monkeypatch.setattr(routines.session_store, "load_session", lambda session_id: existing_session if session_id == "existing-session" else None)
    monkeypatch.setattr(routines.session_store, "save_session", lambda session: None)
    monkeypatch.setattr(routines.ai_workflow, "run_ai_workflow", lambda **kwargs: (_ for _ in ()).throw(AssertionError("existing sessions should not be rescored")))

    def fake_run_autopush_for_session(**kwargs):
        executor_calls.append(kwargs)
        kwargs["session"]["students"][0]["posted"] = True
        kwargs["session"]["students"][0]["autopush_idempotency_key"] = "key"
        return {
            "ok": True,
            "pushed": 1,
            "needs_review": 0,
            "blocked": 0,
            "errors": [],
            "student_results": [{
                "user_id": "1",
                "decision": "auto_push_allowed",
                "reason": "",
                "receipt_id": "receipt-1",
                "idempotency_key": "key",
            }],
            "receipts": [{"receipt_id": "receipt-1"}],
        }

    monkeypatch.setattr(routines.autopush_executor, "run_autopush_for_session", fake_run_autopush_for_session)

    result = routines._run_routine_powergrader_scheduled_autoscore({"max_jobs": 10})

    assert result["ok"] is True
    assert executor_calls
    assert job["status"] == "auto_pushed"
    assert job["push_summary"]["pushed"] == 1
    assert len(save_calls) >= 2
    assert save_calls[0][0]["claimed_by"]


def test_scheduled_autoscore_marks_missing_assignment_as_failed(monkeypatch):
    queue = {"version": 1, "jobs": [_queue_job()]}
    job = queue["jobs"][0]

    monkeypatch.setattr(routines.autoscore_queue, "load_queue", lambda: queue)
    monkeypatch.setattr(routines.autoscore_queue, "due_jobs", lambda q, now=None: q["jobs"])
    monkeypatch.setattr(routines.autoscore_queue, "save_queue", lambda q: None)
    monkeypatch.setattr(routines.canvas_fetch, "fetch_submissions", lambda course_id, assignment_id: (None, None, "404 Not Found"))
    monkeypatch.setattr(routines, "_canvas_send", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("scheduled autoscore must not write grades/comments")))
    monkeypatch.setattr(routines.ai_workflow, "run_ai_workflow", lambda **kwargs: (_ for _ in ()).throw(AssertionError("failed jobs must not create a session")))
    monkeypatch.setattr(routines.session_store, "save_session", lambda session: (_ for _ in ()).throw(AssertionError("failed jobs must not save a session")))

    result = routines._run_routine_powergrader_scheduled_autoscore({"max_jobs": 10})

    assert result["ok"] is False
    assert any("no longer available" in line for line in result["lines"])
    assert job["status"] == "failed"
    assert job["reason"] == "Canvas assignment is no longer available."
    assert job["last_error"] == "Canvas assignment is no longer available."

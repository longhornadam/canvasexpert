import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.powergrader import late_catchup, session_actions
from api.webui.routes import powergrader


def _response_json(response):
    return json.loads(response.body)


def _make_session_state(session):
    state = copy.deepcopy(session)

    def load_session(session_id):
        return copy.deepcopy(state)

    def save_session(saved):
        state.clear()
        state.update(copy.deepcopy(saved))

    return state, load_session, save_session


def _base_late_watch():
    return {
        "enabled": True,
        "supported": True,
        "reason": "",
        "initial_missing_user_ids": ["2"],
        "known_user_ids": ["1"],
        "scored_user_ids": [],
        "last_checked": None,
        "last_scored": None,
        "last_summary": "",
        "source_context": {"sentinel": "keep-me"},
        "response_kind": "scr",
    }


def _assist_session():
    return {
        "session_id": "sid",
        "course_id": "course-1",
        "assignment_id": "assignment-1",
        "assignment_name": "Essay",
        "assignment_description": "Explain the text.",
        "points_possible": 10,
        "mode": "assisted",
        "mode_label": "Auto-Score With API",
        "rubric_name": "Rubric A",
        "persona_id": "sage",
        "model_id": "model-a",
        "response_kind": "scr",
        "privacy_steps": [],
        "privacy_artifacts": {},
        "copilot_packet": None,
        "late_watch": _base_late_watch(),
        "students": [
            {
                "user_id": "1",
                "real_name": "Existing Student",
                "status": "pending",
                "posted": False,
                "ai_score": None,
                "ai_feedback": None,
            }
        ],
        "push_log": [],
    }


def _late_submission_rows():
    return [
        {
            "user_id": "1",
            "submission_type": "online_text_entry",
            "workflow_state": "submitted",
            "submitted_at": "2026-09-10T16:00:00Z",
            "cached_due_date": "2026-09-10T23:59:00Z",
            "user": {"name": "Existing Student", "sortable_name": "Existing Student"},
            "assignment": {"id": "assignment-1", "name": "Essay", "due_at": "2026-09-10T23:59:00Z"},
        },
        {
            "user_id": "2",
            "submission_type": "online_text_entry",
            "workflow_state": "submitted",
            "submitted_at": "2026-09-11T15:20:00Z",
            "cached_due_date": "2026-09-10T23:59:00Z",
            "user": {"name": "Late Student", "sortable_name": "Late Student"},
            "assignment": {"id": "assignment-1", "name": "Essay", "due_at": "2026-09-10T23:59:00Z"},
        },
        {
            "user_id": "3",
            "submission_type": None,
            "workflow_state": "unsubmitted",
            "submitted_at": None,
            "cached_due_date": "2026-09-10T23:59:00Z",
            "user": {"name": "Still Missing", "sortable_name": "Still Missing"},
            "assignment": {"id": "assignment-1", "name": "Essay", "due_at": "2026-09-10T23:59:00Z"},
        },
    ]


def _patch_late_score_env(monkeypatch):
    monkeypatch.setattr(powergrader.config, "get_roster_student_settings", lambda course_id: {})
    monkeypatch.setattr(powergrader.config, "roster_tier_by_id", lambda course_id: {})
    monkeypatch.setattr(powergrader.config, "get_monitored_students", lambda: {})
    monkeypatch.setattr(powergrader.config, "get_extra_time", lambda course_id: [])
    monkeypatch.setattr(powergrader.config, "get_sweep_settings", lambda: {"skip_weekends": True, "holidays": []})
    monkeypatch.setattr(powergrader.config, "get_combined_calendar_for_range", lambda: {"no_count_dates": []})
    monkeypatch.setattr(powergrader.config, "get_openrouter_model", lambda: "model-a")
    monkeypatch.setattr(powergrader.config, "has_openrouter_key", lambda: True)


def test_find_new_submissions_filters_unsubmitted_and_existing_students():
    session = {
        "students": [{"user_id": "1"}],
        "late_watch": {"initial_missing_user_ids": ["2", "3"]},
    }
    submissions = [
        {"user_id": "1", "submission_type": "online_text_entry", "workflow_state": "submitted"},
        {"user_id": "2", "submission_type": "online_text_entry", "workflow_state": "submitted"},
        {"user_id": "3", "submission_type": None, "workflow_state": "unsubmitted"},
    ]

    found = late_catchup.find_new_submissions(session, submissions)

    assert [row["user_id"] for row in found] == ["2"]


def test_initial_missing_user_ids_records_unsubmitted_rows():
    submissions = [
        {"user_id": 1, "submission_type": "online_text_entry", "workflow_state": "submitted"},
        {"user_id": "2", "submission_type": None, "workflow_state": "unsubmitted"},
        {"user_id": "3", "submission_type": "", "workflow_state": "unsubmitted"},
    ]

    assert late_catchup.initial_missing_user_ids(submissions) == ["2", "3"]


def test_late_preview_does_not_call_ai(monkeypatch):
    state, load_session, save_session = _make_session_state(_assist_session())

    monkeypatch.setattr(powergrader, "_load_session", load_session)
    monkeypatch.setattr(powergrader, "_save_session", save_session)
    monkeypatch.setattr(powergrader.canvas_fetch, "fetch_submissions", lambda course_id, assignment_id: (_late_submission_rows(), {"name": "Essay"}, None))
    monkeypatch.setattr(powergrader.ai_workflow, "run_ai_workflow", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("AI workflow should not run")))

    response = powergrader.pg_late_preview("sid")
    data = _response_json(response)

    assert data["ok"] is True
    assert data["new_count"] == 1
    assert data["students"][0]["user_id"] == "2"
    assert state["late_watch"]["last_checked"]
    assert state["late_watch"]["last_summary"] == "1 new late submission(s) found."


def test_late_score_appends_new_students_once(monkeypatch):
    state, load_session, save_session = _make_session_state(_assist_session())
    ai_calls = []

    _patch_late_score_env(monkeypatch)
    monkeypatch.setattr(powergrader, "_load_session", load_session)
    monkeypatch.setattr(powergrader, "_save_session", save_session)
    monkeypatch.setattr(powergrader.canvas_fetch, "fetch_submissions", lambda course_id, assignment_id: (_late_submission_rows(), {"name": "Essay", "description": "Explain the text.", "due_at": "2026-09-10T23:59:00Z"}, None))
    monkeypatch.setattr(powergrader.canvas_fetch, "ingest_ordinary_attachments", lambda subs, **kwargs: subs)

    def fake_run_ai_workflow(**kwargs):
        ai_calls.append(kwargs)
        return {
            "ok": True,
            "error": "",
            "status_code": 200,
            "privacy_steps": [],
            "privacy_artifacts": {},
            "ai_by_uid": {
                "2": {"score": 4, "feedback": "Strong revision."},
            },
            "packet_zip": None,
            "budget": None,
            "debug_path": None,
            "copilot_packet": None,
            "source_context": {"sentinel": "keep-me"},
        }

    monkeypatch.setattr(powergrader.ai_workflow, "run_ai_workflow", fake_run_ai_workflow)

    first = _response_json(powergrader.pg_late_score("sid"))
    second = _response_json(powergrader.pg_late_score("sid"))

    assert first["ok"] is True
    assert first["appended"] == 1
    assert first["ai_scored"] == 1
    assert second["ok"] is True
    assert second["appended"] == 0
    assert len(state["students"]) == 2
    assert state["students"][1]["user_id"] == "2"
    assert state["students"][1]["late_catchup"]["batch_id"].startswith("late-")
    assert state["students"][1]["late_catchup"]["seconds_late_override"] == 86400
    assert len(ai_calls) == 1


def test_late_score_reuses_stored_source_context(monkeypatch):
    state, load_session, save_session = _make_session_state(_assist_session())
    _patch_late_score_env(monkeypatch)

    monkeypatch.setattr(powergrader, "_load_session", load_session)
    monkeypatch.setattr(powergrader, "_save_session", save_session)
    monkeypatch.setattr(powergrader.canvas_fetch, "fetch_submissions", lambda course_id, assignment_id: (_late_submission_rows(), {"name": "Essay", "description": "Explain the text.", "due_at": "2026-09-10T23:59:00Z"}, None))
    monkeypatch.setattr(powergrader.canvas_fetch, "ingest_ordinary_attachments", lambda subs, **kwargs: subs)

    def fake_run_ai_workflow(**kwargs):
        assert kwargs["source_context_override"]["sentinel"] == "keep-me"
        assert "Late Catch-Up" in kwargs["artifact_assignment_name"]
        return {
            "ok": True,
            "error": "",
            "status_code": 200,
            "privacy_steps": [],
            "privacy_artifacts": {},
            "ai_by_uid": {"2": {"score": 5, "feedback": "Nice."}},
            "packet_zip": None,
            "budget": None,
            "debug_path": None,
            "copilot_packet": None,
            "source_context": {"sentinel": "keep-me"},
        }

    monkeypatch.setattr(powergrader.ai_workflow, "run_ai_workflow", fake_run_ai_workflow)

    response = powergrader.pg_late_score("sid")
    data = _response_json(response)

    assert data["ok"] is True
    assert data["appended"] == 1


def test_push_grades_includes_late_override_for_late_catchup_student():
    session = {
        "session_id": "sid",
        "course_id": "course-1",
        "assignment_id": "assignment-1",
        "students": [
            {
                "user_id": "2",
                "real_name": "Late Student",
                "teacher_score": 8,
                "teacher_feedback": "Nice work.",
                "status": "approved",
                "posted": False,
                "late_catchup": {
                    "is_late_catchup": True,
                    "school_days_late": 1,
                    "seconds_late_override": 86400,
                },
            }
        ],
        "push_log": [],
    }
    saved = {}
    payloads = []

    def load_session(session_id):
        return copy.deepcopy(saved or session)

    def save_session(saved_session):
        saved.clear()
        saved.update(copy.deepcopy(saved_session))

    def canvas_send(method, url, payload):
        payloads.append(payload)
        return None, None

    def canvas_get(path, params=None, timeout=0):
        return ({
            "submission": {"score": 2, "grade": "2", "graded_at": None, "updated_at": "2026-01-01T00:00:00Z"},
            "submission_comments": [],
        }, None)

    review, _ = session_actions.review_push(
        "sid", user_ids="", load_session=load_session,
        save_session=save_session, canvas_get=canvas_get,
    )

    payload, status = session_actions.push_grades(
        "sid",
        user_ids=json.dumps(review["user_ids"]),
        review_token=review["review_token"],
        load_session=load_session,
        save_session=save_session,
        canvas_send=canvas_send,
        canvas_get=canvas_get,
    )

    assert status == 200
    assert payload["ok"] is True
    assert payloads[0]["submission"]["posted_grade"] == "8"
    assert payloads[0]["submission"]["late_policy_status"] == "late"
    assert payloads[0]["submission"]["seconds_late_override"] == 86400
    assert payloads[0]["comment"]["text_comment"] == "Nice work."
    assert saved["students"][0]["posted"] is True


def test_late_routes_reject_non_assisted_session(monkeypatch):
    session = {
        "session_id": "sid",
        "mode": "fast",
        "students": [],
    }
    state, load_session, save_session = _make_session_state(session)

    monkeypatch.setattr(powergrader, "_load_session", load_session)
    monkeypatch.setattr(powergrader, "_save_session", save_session)

    for route in (powergrader.pg_late_preview, powergrader.pg_late_score):
        data = _response_json(route("sid"))
        assert data == {
            "ok": False,
            "error": "Late catch-up requires Auto-Score With API or AI Chat mode.",
        }
    assert state["mode"] == "fast"


def test_late_score_does_not_append_on_ai_error(monkeypatch):
    session = _assist_session()
    state, load_session, save_session = _make_session_state(session)
    _patch_late_score_env(monkeypatch)

    monkeypatch.setattr(powergrader, "_load_session", load_session)
    monkeypatch.setattr(powergrader, "_save_session", save_session)
    monkeypatch.setattr(powergrader.canvas_fetch, "fetch_submissions", lambda course_id, assignment_id: (_late_submission_rows(), {"name": "Essay", "description": "Explain the text.", "due_at": "2026-09-10T23:59:00Z"}, None))
    monkeypatch.setattr(powergrader.canvas_fetch, "ingest_ordinary_attachments", lambda subs, **kwargs: subs)
    monkeypatch.setattr(powergrader.ai_workflow, "run_ai_workflow", lambda **kwargs: {
        "ok": False,
        "error": "OpenRouter model error",
        "status_code": 200,
        "privacy_steps": [{"id": "llm_send", "status": "failed"}],
        "privacy_artifacts": {},
        "ai_by_uid": {},
        "packet_zip": None,
        "budget": None,
        "debug_path": None,
        "copilot_packet": None,
        "source_context": {"sentinel": "keep-me"},
    })

    response = powergrader.pg_late_score("sid")
    data = _response_json(response)

    assert data["ok"] is False
    assert "OpenRouter model error" in data["error"]
    assert len(state["students"]) == 1
    assert "late_catchup_log" not in state

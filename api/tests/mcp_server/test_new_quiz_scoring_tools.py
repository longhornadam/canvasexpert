"""Tests for the New Quiz item-finalization write pair: preview_new_quiz_scores
and apply_new_quiz_scores.

Both tools are thin loops over the existing, already-tested finalization lane
(api.powergrader.session_actions.review_new_quiz_finalization / finalize_new_quiz
/ converge_new_quiz_after_finalize -- see docs/handoffs/newquiz-chat-scoring.md
D4). Only the Canvas-touching preflight/apply callables
(tools._new_quiz_preflight / tools._new_quiz_apply) are stubbed; the real
session_actions machinery runs against an in-memory session dict, the same
pattern api/tests/test_powergrader_new_quizzes.py already uses for
review_new_quiz_finalization/finalize_new_quiz directly. No network, no
Canvas call, no real course, no student data (fixture names/ids below are
synthetic placeholders, matching api/tests/test_beta075_mcp.py's own
"Learner One" / "900001" convention).
"""
from __future__ import annotations

import json

import pytest

from api.mcp_server import server, tools
from api.powergrader import new_quiz_grader, session_actions


def _session(*, session_id="sess-nq", course_id="111", assignment_id="700010",
             students=None, supported=True):
    return {
        "session_id": session_id,
        "course_id": course_id,
        "assignment_id": assignment_id,
        "new_quiz_item_finalization_supported": supported,
        "students": students if students is not None else [],
    }


def _student(user_id, *, real_name="Learner One", item_results=None,
             speedgrader_required=False, new_quiz_finalized=False):
    return {
        "user_id": user_id,
        "real_name": real_name,
        "speedgrader_required": speedgrader_required,
        "new_quiz_finalized": new_quiz_finalized,
        "ai_item_results": item_results if item_results is not None else [],
    }


def _bind_session_store(monkeypatch, sessions: dict):
    monkeypatch.setattr("api.powergrader.session_store.load_session",
                        lambda sid: sessions.get(sid))
    monkeypatch.setattr("api.powergrader.session_store.save_session",
                        lambda s: sessions.__setitem__(s["session_id"], s))


def _fake_preflight(result_id="result-1", state_digest="a" * 64):
    def preflight(_session, _student, decisions):
        return {
            "result_id": result_id,
            "state_digest": state_digest,
            "decision_digest": session_actions._digest(decisions),
        }
    return preflight


def _fake_apply(calls=None, raises=None):
    def apply_fn(_session, student, _decisions, _pending):
        if calls is not None:
            calls.append(str(student.get("user_id")))
        if raises is not None:
            raise raises
        return {"state_digest": "b" * 64}
    return apply_fn


def _refuse_if_called(*_args, **_kwargs):
    raise AssertionError("must not touch Canvas")


def _setup(monkeypatch, _set_active_courses, session, preflight=None, apply_fn=None):
    _set_active_courses(["111"])
    sessions = {session["session_id"]: session}
    _bind_session_store(monkeypatch, sessions)
    monkeypatch.setattr(tools, "_new_quiz_preflight", preflight or _fake_preflight())
    monkeypatch.setattr(tools, "_new_quiz_apply", apply_fn or _refuse_if_called)
    monkeypatch.setattr(tools, "_new_quiz_notify_write_through", lambda *_a, **_kw: None)
    return sessions


# --- example: preview then apply, end to end --------------------------------

def test_preview_then_apply_finalizes_one_student_end_to_end(
    monkeypatch, _use_vault, _set_active_courses,
):
    student = _student("900001", item_results=[
        {"item_id": "essay-1", "score": 4.0, "feedback": "Nice work."},
    ])
    session = _session(students=[student])
    apply_calls = []
    notified = []
    sessions = _setup(monkeypatch, _set_active_courses, session,
                      apply_fn=_fake_apply(calls=apply_calls))
    monkeypatch.setattr(tools, "_new_quiz_notify_write_through",
                        lambda sess, pushed: notified.append((sess.get("course_id"), pushed)))

    preview = tools.preview_new_quiz_scores("sess-nq")
    assert preview["ok"] is True
    assert preview["counts"] == {
        "students": 1, "items": 1, "ready": 1, "refused": 0, "already_finalized": 0,
    }
    assert preview["warnings"] == []
    operation_id, review_digest = preview["operation_id"], preview["review_digest"]
    assert operation_id.startswith("sess-nq::")

    result = tools.apply_new_quiz_scores(operation_id, review_digest)

    assert result["ok"] is True
    assert result["counts"] == {"finalized": 1, "already_applied": 0, "failed": 0}
    assert len(result["results"]) == 1
    assert result["results"][0]["status"] == "finalized"
    assert apply_calls == ["900001"]
    assert notified == [("111", ["900001"])]
    assert sessions["sess-nq"]["students"][0]["new_quiz_finalized"] is True


def test_preview_only_includes_students_with_a_staged_score(
    monkeypatch, _use_vault, _set_active_courses,
):
    scored = _student("900001", item_results=[{"item_id": "essay-1", "score": 4.0, "feedback": "TA note"}])
    unscored = _student("900002", item_results=[{"item_id": "essay-1", "score": None, "feedback": ""}])
    session = _session(students=[scored, unscored])
    _setup(monkeypatch, _set_active_courses, session)

    preview = tools.preview_new_quiz_scores("sess-nq")

    assert preview["ok"] is True
    assert preview["counts"]["students"] == 1


# --- laws: no student identity ----------------------------------------------

def test_preview_never_projects_a_real_name_or_canvas_id(monkeypatch, _use_vault, _set_active_courses):
    student = _student("900123", real_name="Learner One", item_results=[
        {"item_id": "essay-1", "score": 4.0, "feedback": "Nice work."},
    ])
    session = _session(students=[student])
    _setup(monkeypatch, _set_active_courses, session)

    result = tools.preview_new_quiz_scores("sess-nq")

    assert result["ok"] is True
    dumped = json.dumps(result)
    assert "Learner One" not in dumped
    assert "900123" not in dumped


def test_apply_results_never_project_a_real_name_or_canvas_id(monkeypatch, _use_vault, _set_active_courses):
    student = _student("900123", real_name="Learner One", item_results=[
        {"item_id": "essay-1", "score": 4.0, "feedback": "Nice work."},
    ])
    session = _session(students=[student])
    _setup(monkeypatch, _set_active_courses, session, apply_fn=_fake_apply())

    preview = tools.preview_new_quiz_scores("sess-nq")
    result = tools.apply_new_quiz_scores(preview["operation_id"], preview["review_digest"])

    assert result["ok"] is True
    dumped = json.dumps(result)
    assert "Learner One" not in dumped
    assert "900123" not in dumped


# --- laws: apply's opaque-coordinate refusals -------------------------------

def test_apply_refuses_an_operation_id_it_did_not_mint(monkeypatch, _use_vault, _set_active_courses):
    session = _session(students=[])
    _setup(monkeypatch, _set_active_courses, session)

    forged_same_session = tools.apply_new_quiz_scores("sess-nq::forged-suffix", "any-digest")
    malformed = tools.apply_new_quiz_scores("not-a-real-operation-id", "any-digest")

    assert forged_same_session == {
        "ok": False, "error": "Operation not found. Run preview_new_quiz_scores again.",
    }
    assert malformed == {
        "ok": False, "error": "Operation not found. Run preview_new_quiz_scores again.",
    }


def test_apply_refuses_a_mismatched_review_digest_without_touching_canvas(
    monkeypatch, _use_vault, _set_active_courses,
):
    student = _student("900001", item_results=[{"item_id": "essay-1", "score": 4.0, "feedback": "TA note"}])
    session = _session(students=[student])
    _setup(monkeypatch, _set_active_courses, session)  # apply stays poisoned to _refuse_if_called

    preview = tools.preview_new_quiz_scores("sess-nq")
    result = tools.apply_new_quiz_scores(preview["operation_id"], "wrong-digest")

    assert result == {
        "ok": False, "error": "review_digest does not match. Run preview_new_quiz_scores again.",
    }


def test_apply_refuses_an_expired_review_token_cleanly(monkeypatch, _use_vault, _set_active_courses):
    student = _student("900001", item_results=[{"item_id": "essay-1", "score": 4.0, "feedback": "TA note"}])
    session = _session(students=[student])
    sessions = _setup(monkeypatch, _set_active_courses, session)  # apply stays poisoned

    preview = tools.preview_new_quiz_scores("sess-nq")
    operation_id = preview["operation_id"]
    stash = sessions["sess-nq"]["new_quiz_scoring_operations"][operation_id]
    stash["students"]["900001"]["pending"]["expires_at"] = "2000-01-01T00:00:00+00:00"

    result = tools.apply_new_quiz_scores(operation_id, preview["review_digest"])

    assert result["ok"] is False
    assert result["counts"] == {"finalized": 0, "already_applied": 0, "failed": 1}
    assert result["results"][0]["status"] == "failed"
    assert result["results"][0]["code"] == "review_expired"


# --- law: idempotency --------------------------------------------------------

def test_apply_twice_with_the_same_coordinates_writes_once(monkeypatch, _use_vault, _set_active_courses):
    student = _student("900001", item_results=[{"item_id": "essay-1", "score": 4.0, "feedback": "TA note"}])
    session = _session(students=[student])
    apply_calls = []
    _setup(monkeypatch, _set_active_courses, session, apply_fn=_fake_apply(calls=apply_calls))

    preview = tools.preview_new_quiz_scores("sess-nq")
    operation_id, review_digest = preview["operation_id"], preview["review_digest"]

    first = tools.apply_new_quiz_scores(operation_id, review_digest)
    second = tools.apply_new_quiz_scores(operation_id, review_digest)

    assert first["results"][0]["status"] == "finalized"
    assert second["results"][0]["status"] == "already_applied"
    assert second["ok"] is True
    assert apply_calls == ["900001"]  # the Canvas-touching callable ran exactly once


# --- law: an unverified/rejected write is never retried through replay -----

def test_apply_never_retries_an_unverified_write_through_the_same_operation(
    monkeypatch, _use_vault, _set_active_courses,
):
    student = _student("900001", item_results=[{"item_id": "essay-1", "score": 4.0, "feedback": "TA note"}])
    session = _session(students=[student])
    apply_calls = []
    _setup(monkeypatch, _set_active_courses, session,
          apply_fn=_fake_apply(calls=apply_calls, raises=new_quiz_grader.GraderError("write_unknown")))

    preview = tools.preview_new_quiz_scores("sess-nq")
    operation_id, review_digest = preview["operation_id"], preview["review_digest"]

    first = tools.apply_new_quiz_scores(operation_id, review_digest)
    assert first["results"][0]["status"] == "failed"
    assert first["results"][0]["code"] == "write_unknown"
    assert apply_calls == ["900001"]

    # A second replay of the same coordinates must not attempt the write
    # again -- finalize_new_quiz's own rule (never retry an unverified write
    # through the same frozen token), which our stash must not defeat by
    # re-freezing the same token on every call.
    second = tools.apply_new_quiz_scores(operation_id, review_digest)
    assert apply_calls == ["900001"]
    assert second["counts"] == {"finalized": 0, "already_applied": 0, "failed": 0}
    assert second["results"] == []


# --- contract: aggregate counts over a mixed batch --------------------------

def test_preview_counts_ready_refused_and_already_finalized_students(
    monkeypatch, _use_vault, _set_active_courses,
):
    ready = _student("900001", item_results=[{"item_id": "essay-1", "score": 4.0, "feedback": "TA note"}])
    refused = _student("900002", item_results=[{"item_id": "essay-1", "score": 3.0, "feedback": "TA note"}],
                       speedgrader_required=True)
    finalized_again = _student(
        "900003", item_results=[{"item_id": "essay-2", "score": 5.0, "feedback": "TA note"}],
        new_quiz_finalized=True,
    )
    session = _session(students=[ready, refused, finalized_again])
    _setup(monkeypatch, _set_active_courses, session)

    result = tools.preview_new_quiz_scores("sess-nq")

    assert result["ok"] is True
    assert result["counts"] == {
        "students": 3, "items": 2, "ready": 2, "refused": 1, "already_finalized": 1,
    }
    assert result["refused_reasons"] == {"speedgrader_required": 1}
    assert len(result["warnings"]) == 1
    assert result["warnings"][0]["code"] == "speedgrader_required"


# --- contract: clean refusals with no Canvas call ---------------------------

@pytest.mark.parametrize("build_session,expected_error", [
    (lambda: None, "Session not found."),
    (lambda: _session(students=[_student("900001", item_results=[
        {"item_id": "essay-1", "score": 4.0, "feedback": "TA note"}])], supported=False),
     "This session does not support New Quiz item finalization."),
    (lambda: _session(students=[_student("900001")]),
     "No staged item scores are ready to preview. Stage scores first with stage_scores."),
])
def test_preview_refuses_cleanly_without_a_canvas_call(
    monkeypatch, _use_vault, _set_active_courses, build_session, expected_error,
):
    _set_active_courses(["111"])
    session = build_session()
    sessions = {"sess-nq": session} if session else {}
    _bind_session_store(monkeypatch, sessions)
    monkeypatch.setattr(tools, "_new_quiz_preflight", _refuse_if_called)

    result = tools.preview_new_quiz_scores("sess-nq")

    assert result == {"ok": False, "error": expected_error}


def test_preview_refuses_a_non_current_course(monkeypatch, _use_vault, _set_active_courses):
    _set_active_courses(["222"])  # "111" is not Current
    session = _session(students=[_student("900001", item_results=[
        {"item_id": "essay-1", "score": 4.0, "feedback": "TA note"}])])
    _bind_session_store(monkeypatch, {"sess-nq": session})
    monkeypatch.setattr(tools, "_new_quiz_preflight", _refuse_if_called)

    result = tools.preview_new_quiz_scores("sess-nq")

    assert result["ok"] is False
    assert "not a Current course" in result["error"]


# --- server wiring ------------------------------------------------------------

def test_new_quiz_scoring_tools_are_registered_and_wrap_compactly(monkeypatch):
    monkeypatch.setattr(tools, "preview_new_quiz_scores",
                        lambda session_id: {"ok": True, "session_id_seen": session_id})
    monkeypatch.setattr(tools, "apply_new_quiz_scores",
                        lambda operation_id, review_digest: {
                            "ok": True, "operation_id_seen": operation_id, "digest_seen": review_digest,
                        })

    assert server.preview_new_quiz_scores("sess-nq") == '{"ok":true,"session_id_seen":"sess-nq"}'
    assert server.apply_new_quiz_scores("op-1", "digest-1") == (
        '{"ok":true,"operation_id_seen":"op-1","digest_seen":"digest-1"}'
    )

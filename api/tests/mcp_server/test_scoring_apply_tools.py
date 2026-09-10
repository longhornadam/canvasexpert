"""The MCP boundary for posting assignment scores from chat.

The powergrader layer below speaks Canvas ``user_id``. These tools are where
that stops: pseudonyms in, pseudonyms out, including inside question and error
text. That is the highest-risk seam in this pair, so it is asserted directly
rather than inferred from a happy path.
"""
import json

import pytest

from api.mcp_server import tools


REAL_IDS = ("9001", "9002", "9003")


class _FakeVault:
    """Three students, so a leak has something recognizable to leak."""

    def entries(self):
        return [
            {"canvas_id": "9001", "real_name": "Ada Lovelace", "pseudonym": "Pikachu"},
            {"canvas_id": "9002", "real_name": "Alan Turing", "pseudonym": "Snorlax"},
            {"canvas_id": "9003", "real_name": "Grace Hopper", "pseudonym": "Eevee"},
        ]

    def reverse(self, pseudonym):
        return next((e for e in self.entries() if e["pseudonym"] == pseudonym), None)

    def all_real_identifiers(self):
        """(names, ids), matching the real vault -- this is what the outbound
        safety scan unpacks before anything leaves the machine."""
        return ({"Ada Lovelace", "Alan Turing", "Grace Hopper"}, set(REAL_IDS))


def _session(**overrides):
    session = {
        "session_id": "session-1", "course_id": "course-1", "assignment_id": "assignment-1",
        "canvas_writeback_supported": True,
        "assignment": {"points_possible": 10},
        "students": [
            {"user_id": "9001", "ai_score": 12, "ai_feedback": "Strong."},
            {"user_id": "9002", "ai_score": 6, "ai_feedback": "Clear evidence."},
            {"user_id": "9003"},
        ],
    }
    session.update(overrides)
    return session


@pytest.fixture
def wired(monkeypatch):
    """Course gate open, vault faked, Canvas faked, session in memory."""
    from api.platform_services import canvas_client
    from api.powergrader import session_store

    state = {"session": _session(), "sent": []}

    monkeypatch.setattr(tools, "_course_gate_check", lambda _course_id: None)
    monkeypatch.setattr(tools, "_vault_factory", _FakeVault)
    monkeypatch.setattr(session_store, "load_session", lambda _sid: state["session"])
    monkeypatch.setattr(session_store, "save_session",
                        lambda value: state.__setitem__("session", value))

    class _NullLock:
        def __enter__(self): return self
        def __exit__(self, *exc): return False

    monkeypatch.setattr(session_store, "session_lock", lambda _sid: _NullLock())
    monkeypatch.setattr(canvas_client, "canvas_get", lambda *a, **k: (
        {"score": None, "submission_comments": [], "comments_available": True}, None))
    monkeypatch.setattr(canvas_client, "_canvas_send", lambda *a, **k: (
        state["sent"].append(a) or ({"id": 1}, None)))
    return state


def _blob(result) -> str:
    return json.dumps(result, default=str)


# ── The boundary ────────────────────────────────────────────────────────────


def test_preview_never_emits_a_canvas_user_id(wired):
    """LAW: no user_id crosses the MCP boundary.

    Checked over the whole serialized reply, not just the fields we remembered
    to look at -- question text and error strings are where an id slips through.
    """
    result = tools.preview_assignment_scores("session-1")

    assert result["ok"] is True
    blob = _blob(result)
    for real_id in REAL_IDS:
        assert real_id not in blob, f"user_id {real_id} reached the MCP boundary"
    for real_name in ("Ada Lovelace", "Alan Turing", "Grace Hopper"):
        assert real_name not in blob


def test_apply_never_emits_a_canvas_user_id(wired):
    preview = tools.preview_assignment_scores("session-1")
    result = tools.apply_assignment_scores(
        "session-1", preview["review_digest"],
        {"score_above_possible": "skip_those", "held_not_scored": "proceed"})

    blob = _blob(result)
    for real_id in REAL_IDS:
        assert real_id not in blob, f"user_id {real_id} reached the MCP boundary"


def test_questions_name_students_by_pseudonym(wired):
    result = tools.preview_assignment_scores("session-1")

    above = next(q for q in result["questions"] if q["id"] == "score_above_possible")
    held = next(q for q in result["questions"] if q["id"] == "held_not_scored")
    assert above["students"] == ["Pikachu"]
    assert held["students"] == ["Eevee"]
    assert above["answer_with"] == ["post_anyway", "skip_those"]


# ── Behavior ────────────────────────────────────────────────────────────────


def test_preview_makes_no_canvas_write(wired):
    tools.preview_assignment_scores("session-1")

    assert wired["sent"] == []


def test_apply_refuses_while_a_question_is_unanswered(wired):
    preview = tools.preview_assignment_scores("session-1")

    result = tools.apply_assignment_scores("session-1", preview["review_digest"], {})

    assert result["ok"] is False
    assert result["code"] == "unanswered_questions"
    assert wired["sent"] == []


def test_apply_posts_the_answered_plan(wired):
    """EXAMPLE: preview, answer, apply -- one push for the one clean row."""
    preview = tools.preview_assignment_scores("session-1")

    result = tools.apply_assignment_scores(
        "session-1", preview["review_digest"],
        {"score_above_possible": "skip_those", "held_not_scored": "proceed"})

    assert result["ok"] is True
    assert result["skipped"] == ["Pikachu"]
    assert len(wired["sent"]) == 1


def test_apply_refuses_a_stale_digest(wired):
    preview = tools.preview_assignment_scores("session-1")
    wired["session"]["students"][1]["ai_score"] = 9

    result = tools.apply_assignment_scores(
        "session-1", preview["review_digest"],
        {"score_above_possible": "skip_those", "held_not_scored": "proceed"})

    assert result["ok"] is False and result["code"] == "plan_changed"
    assert wired["sent"] == []


def test_a_new_quiz_session_is_pointed_at_its_own_lane(wired):
    wired["session"]["canvas_writeback_supported"] = False
    wired["session"]["comment_writeback_supported"] = True

    result = tools.preview_assignment_scores("session-1")

    assert result["ok"] is False
    assert "preview_new_quiz_scores" in result["error"]


def test_a_session_with_nothing_staged_is_refused(wired):
    wired["session"]["students"] = [{"user_id": "9003"}]

    result = tools.preview_assignment_scores("session-1")

    assert result["ok"] is False and "No staged scores" in result["error"]

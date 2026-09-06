"""Tests for shared PowerGrader session-action convergence helpers.

Currently covers the post-finalize New Quiz convergence: the function moved
here from the HTTP route (``api.webui.routes.powergrader``) so a future MCP
caller can reach it without duplicating the write-through and cache-
invalidation logic. See docs/handoffs/newquiz-chat-scoring.md decision D5.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.powergrader import session_actions


def test_converge_new_quiz_after_finalize_hits_both_surfaces(monkeypatch):
    """A verified New Quiz finalize converges the gradebook submission (write-
    through refresh) and stale-invalidates the separate New Quiz response cache."""
    from api.mirror import new_quizzes

    notified, invalidated = [], []

    def fake_notify_write_through(session, pushed):
        notified.append(str((session or {}).get("course_id")))

    monkeypatch.setattr(new_quizzes, "invalidate_responses",
                        lambda course_id, assignment_id, **kw:
                        invalidated.append((str(course_id), str(assignment_id))))

    session_actions.converge_new_quiz_after_finalize(
        {"course_id": "55", "assignment_id": "900"}, "u1",
        notify_write_through=fake_notify_write_through,
    )

    assert notified == ["55"]
    assert invalidated == [("55", "900")]

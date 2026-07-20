"""Push context builders for interactive and scheduled PowerGrader auto-push.

Each builder returns a new dictionary, never the caller's mutable object.
The resulting context is used by the shared evaluator and executor for all
auto-push authorization, regardless of origin (scheduled job or interactive
session).
"""
from __future__ import annotations

from copy import deepcopy

from .autopush_policy import POLICY_VERSION


def _mapping(value: dict | None) -> dict:
    return value if isinstance(value, dict) else {}


def _text(value) -> str:
    return str(value or "").strip()


def _policy_for_context(source: dict) -> dict:
    """Extract or build a push policy dict for a context.

    Interactive sessions derive the policy from the session's auto_post block.
    Scheduled jobs carry a stored push_policy; this function stamps the
    effective POLICY_VERSION for evaluation and receipt audit.
    """
    policy = deepcopy(_mapping(source.get("push_policy")))
    policy["policy_version"] = POLICY_VERSION
    return policy


def build_scheduled_push_context(job: dict) -> dict:
    """Build a push context dict from a scheduled auto-score job.

    Returns a new dictionary; never returns or aliases the caller's mutable
    job object.  The context includes course_id, assignment_id, status,
    auto_push, push_policy, and source.  Grade and comment pushes are
    allowed only when the derived policy permits them.
    """
    job_map = _mapping(job)
    push_policy = _policy_for_context(job_map)
    context = {
        "course_id": _text(job_map.get("course_id")),
        "assignment_id": _text(job_map.get("assignment_id")),
        "status": _text(job_map.get("status")),
        "auto_push": bool(job_map.get("auto_push")),
        "push_policy": push_policy,
        "source": "scheduled",
        "source_label": "scheduled job",
        "session_id": _text(job_map.get("session_id")),
        # Allow grade and comment pushes only when the opt-in policy permits
        "grade_push_allowed": bool(push_policy.get("allow_grade_push", True)),
        "comment_push_allowed": bool(push_policy.get("allow_comment_push", True)),
    }
    # Carry over any job-level assignment snapshot for fallback
    if job_map.get("assignment"):
        context["assignment_snapshot"] = deepcopy(job_map["assignment"])
    return context


def build_interactive_push_context(session: dict) -> dict:
    """Build a push context dict from an interactive PowerGrader session.

    Returns a new dictionary; never returns or aliases the caller's mutable
    session object.  Derives auto_push and push_policy from
    session['auto_post'].  Interactive contexts use source 'interactive_session'
    and carry the session_id.

    Ordinary interactive sessions support normal grade AND comment PUTs.
    New Quiz is excluded from auto-post entirely, so the remaining eligible
    modes (assisted, packet) always allow both grade and comment writes.
    """
    session_map = _mapping(session)
    auto_post = _mapping(session_map.get("auto_post"))
    auto_post_enabled = bool(auto_post.get("enabled"))
    push_policy = _policy_for_context({"push_policy": {"policy_version": auto_post.get("policy_version", POLICY_VERSION)}})
    push_policy["enabled"] = auto_post_enabled
    push_policy["allow_grade_push"] = True
    push_policy["allow_comment_push"] = True
    context = {
        "course_id": _text(session_map.get("course_id")),
        "assignment_id": _text(session_map.get("assignment_id")),
        "status": "session_ready" if auto_post_enabled else "disabled",
        "auto_push": auto_post_enabled,
        "push_policy": push_policy,
        "source": "interactive_session",
        "source_label": "interactive session",
        "session_id": _text(session_map.get("session_id")),
        "grade_push_allowed": True,
        "comment_push_allowed": True,
    }
    return context
"""Interactive session auto-push orchestration for PowerGrader.

This module owns the trigger-specific logic for performing an automatic Canvas
post from an interactive PowerGrader session.  It uses the shared push context,
policy evaluator, and executor, but manages the interactive-specific fresh-state
fetch, receipt directory, and session summary/log mutation.
"""
from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timezone

from .autopush_policy import POLICY_VERSION
from .autopush_executor import run_autopush_for_session
from .push_context import build_interactive_push_context
from . import scheduled_autoscore_support as autoscore_support


def _mapping(value: dict | None) -> dict:
    return value if isinstance(value, dict) else {}


def _text(value) -> str:
    return str(value or "").strip()


def _now_iso(now=None) -> str:
    if now is None:
        current = datetime.now(timezone.utc)
    elif isinstance(now, datetime):
        current = now
    else:
        current = datetime.fromisoformat(str(now).replace("Z", "+00:00"))
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.replace(microsecond=0).isoformat()


def interactive_receipt_dir(session: dict) -> str | None:
    """Resolve the receipt directory for an interactive session.

    Returns `<PowerGrader Sessions>/_private/autopush_receipts/session-<safe-session-id>/`.
    """
    session_id = _text((session or {}).get("session_id"))
    if not session_id:
        return None
    try:
        from .session_store import pg_dir, safe_session_id
        root = pg_dir()
        if not root:
            return None
        safe_id = safe_session_id(session_id)
        return os.path.join(root, "_private", "autopush_receipts", f"session-{safe_id}")
    except Exception:
        return None


def fetch_fresh_push_state(
    course_id: str,
    assignment_id: str,
    *,
    canvas_get_all,
    canvas_get,
) -> tuple[dict[str, dict], dict, str]:
    """Fetch a fresh Canvas snapshot for auto-push evaluation.

    Makes a paginated read of students/submissions for one assignment, projects
    rows through the shared state builder, and returns a fresh assignment object.

    Returns (canvas_states_by_user, fresh_assignment, error_string).
    On failure, returns ({}, {}, error) and performs zero writes.
    """
    try:
        subs, err = canvas_get_all(
            f"/api/v1/courses/{course_id}/students/submissions",
            {
                "student_ids[]": ["all"],
                "assignment_ids[]": [assignment_id],
                "include[]": ["assignment", "user", "submission_comments"],
                "per_page": 100,
            },
        )
        if err:
            return {}, {}, err
        if not subs:
            return {}, {}, "No submissions returned from Canvas."

        # Extract assignment from the first included assignment if available
        fresh_assignment = None
        for sub in subs:
            if isinstance(sub, dict):
                included = sub.get("assignment")
                if isinstance(included, dict) and included.get("id"):
                    fresh_assignment = deepcopy(included)
                    break

        # Fallback: focused assignment GET if include[]=assignment is unavailable
        if not fresh_assignment:
            adata, aerr = canvas_get(
                f"/api/v1/courses/{course_id}/assignments/{assignment_id}"
            )
            if aerr:
                return {}, {}, aerr
            fresh_assignment = deepcopy(adata) if adata else None

        if not fresh_assignment:
            return {}, {}, "Could not resolve authoritative assignment metadata."

        canvas_states = autoscore_support.autoscore_canvas_states(subs)
        return canvas_states, fresh_assignment, ""
    except Exception as exc:
        return {}, {}, str(exc)


def _sanitize_reason_counts(reason_counts: dict) -> dict:
    """Return reason counts without student names, response text, or grades."""
    safe = {}
    for key, value in (reason_counts or {}).items():
        if not isinstance(key, str):
            continue
        if not isinstance(value, (int, float)):
            continue
        safe[str(key)] = int(value)
    return safe


def _autopush_result_payload(result: dict, trigger: str, autopush_result: dict | None = None, now=None) -> dict:
    """Wrap a raw result dict into the uniform {summary, log_entry, autopush_result} shape.

    Every return path from run_interactive_autopush must go through this
    function so that route callers can safely access result["summary"] and
    result["log_entry"] even after guard-level or fetch-level early exits.

    When *autopush_result* is provided its numeric fields shadow the initial
    *result* dict (which is a zeroed template for guard/fetch early exits).
    """
    src = autopush_result if isinstance(autopush_result, dict) else result
    summary = {
        "ok": bool(src.get("ok", result.get("ok"))),
        "pushed": int(src.get("pushed") or result.get("pushed") or 0),
        "needs_review": int(src.get("needs_review") or result.get("needs_review") or 0),
        "blocked": int(src.get("blocked") or result.get("blocked") or 0),
        "evaluated": int(src.get("evaluated") or result.get("evaluated") or 0),
        "reason_counts": _sanitize_reason_counts(src.get("reason_counts") or result.get("reason_counts")),
        "errors": [
            {"user_id": e.get("user_id"), "reason": e.get("reason")}
            for e in (src.get("errors") or result.get("errors") or [])
            if isinstance(e, dict)
        ],
        "receipts_written": len(src.get("receipts") or result.get("receipts") or []),
        "skipped_reason": src.get("skipped_reason") or result.get("skipped_reason"),
    }
    timestamp = _now_iso(now)
    log_entry = {
        "ts": timestamp,
        "trigger": trigger,
        "evaluated": summary["evaluated"],
        "pushed": summary["pushed"],
        "needs_review": summary["needs_review"],
        "blocked": summary["blocked"],
        "reason_counts": dict(summary["reason_counts"]),
        "errors": list(summary["errors"]),
    }
    if summary.get("skipped_reason"):
        log_entry["skipped_reason"] = summary["skipped_reason"]
    return {
        "summary": summary,
        "log_entry": log_entry,
        "autopush_result": autopush_result or {},
    }


def run_interactive_autopush(
    *,
    session: dict,
    trigger: str,
    canvas_get_all,
    canvas_get,
    canvas_send,
    only_user_ids: set[str] | None = None,
    now=None,
) -> dict:
    """Run one interactive auto-push trigger against a loaded session.

    Guards require an enabled v2 auto_post block, mode in {'assisted', 'packet'},
    and canvas_writeback_supported is not False.

    Callers must hold the session lock around authoritative load through final save.
    This function does not acquire or release the session lock.

    Returns {"summary": ..., "log_entry": ..., "autopush_result": ...}.
    """
    session_map = _mapping(session)
    auto_post = _mapping(session_map.get("auto_post"))
    result = {
        "ok": False,
        "pushed": 0,
        "needs_review": 0,
        "blocked": 0,
        "evaluated": 0,
        "reason_counts": {},
        "errors": [],
        "student_results": [],
        "receipts": [],
        "skipped_reason": None,
    }

    # --- Guards ---
    if not auto_post.get("enabled"):
        result["skipped_reason"] = "auto_post_disabled"
        return _autopush_result_payload(result, trigger, now=now)
    if auto_post.get("policy_version", 1) < 2:
        result["skipped_reason"] = "auto_post_old_policy"
        return _autopush_result_payload(result, trigger, now=now)

    mode = _text(session_map.get("mode"))
    if mode not in ("assisted", "packet"):
        result["skipped_reason"] = f"mode_{mode}_unsupported"
        return _autopush_result_payload(result, trigger, now=now)

    if session_map.get("canvas_writeback_supported") is False:
        result["skipped_reason"] = "canvas_writeback_not_supported"
        return _autopush_result_payload(result, trigger, now=now)

    # Handle only_user_ids: None = all, empty set = none
    if only_user_ids is not None and len(only_user_ids) == 0:
        result["skipped_reason"] = "no_user_ids_to_evaluate"
        return _autopush_result_payload(result, trigger, now=now)

    # --- Fresh fetch ---
    course_id = _text(session_map.get("course_id"))
    assignment_id = _text(session_map.get("assignment_id"))
    canvas_states, fresh_assignment, fetch_err = fetch_fresh_push_state(
        course_id, assignment_id,
        canvas_get_all=canvas_get_all,
        canvas_get=canvas_get,
    )
    if fetch_err:
        result["skipped_reason"] = f"fresh_fetch_failed:{fetch_err}"
        return _autopush_result_payload(result, trigger, now=now)

    # --- Build push context ---
    push_context = build_interactive_push_context(session_map)

    # --- Receipt preflight ---
    receipt_dir = interactive_receipt_dir(session)

    # --- Build scoped student view ---
    all_students = session_map.get("students") or []
    if only_user_ids is None:
        scoped_students = all_students
    else:
        scoped_students = [st for st in all_students if _text(st.get("user_id")) in only_user_ids]

    # Shallow view: keep references so mutations reach the authoritative session
    scoped_session = {
        "session_id": session_map.get("session_id"),
        "course_id": course_id,
        "assignment_id": assignment_id,
        "students": scoped_students,
    }

    # --- Execute ---
    autopush_result = run_autopush_for_session(
        context=push_context,
        session=scoped_session,
        assignment=fresh_assignment,
        canvas_states_by_user=canvas_states,
        canvas_send=canvas_send,
        receipt_dir=receipt_dir,
        now=now,
    )

    # --- Build summary/log ---
    return _autopush_result_payload(result, trigger, autopush_result=autopush_result, now=now)
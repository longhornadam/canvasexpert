"""PowerGrader session actions — save grade and push grades to Canvas."""

import json
from datetime import datetime


def save_grade(
    session_id: str,
    *,
    user_id: str,
    teacher_score: str,
    teacher_feedback: str,
    status: str,
    load_session,
    save_session,
) -> tuple[dict, int]:
    """Save one student's grade into a session. Returns (payload, status_code)."""
    session = load_session(session_id)
    if not session:
        return {"ok": False, "error": "Session not found."}, 404

    score_val = None
    if teacher_score.strip():
        try:
            score_val = float(teacher_score.strip())
        except ValueError:
            return {"ok": False, "error": "Invalid score value."}, 200

    updated = False
    for st in session["students"]:
        if st["user_id"] == user_id:
            st["teacher_score"] = score_val
            st["teacher_feedback"] = teacher_feedback.strip()
            st["status"] = status if status in ("approved", "skipped", "pending") else "approved"
            updated = True
            break

    if not updated:
        return {"ok": False, "error": "Student not found in session."}, 200

    save_session(session)
    approved = sum(1 for s in session["students"] if s.get("status") == "approved")
    return {"ok": True, "approved": approved}, 200


def push_grades(
    session_id: str,
    *,
    user_ids: str,
    load_session,
    save_session,
    canvas_send,
) -> tuple[dict, int]:
    """Push approved grades to Canvas. Returns (payload, status_code)."""
    session = load_session(session_id)
    if not session:
        return {"ok": False, "error": "Session not found."}, 404

    course_id = session["course_id"]
    assignment_id = session["assignment_id"]

    # Determine which students to push
    if user_ids.strip():
        try:
            target_ids = set(json.loads(user_ids))
        except Exception:
            return {"ok": False, "error": "Invalid user_ids JSON."}, 200
    else:
        # Push all approved, not yet posted
        target_ids = {
            st["user_id"] for st in session["students"]
            if st.get("status") == "approved" and not st.get("posted")
        }

    pushed, errors = 0, []
    for st in session["students"]:
        if st["user_id"] not in target_ids:
            continue
        score = st.get("teacher_score")
        feedback = (st.get("teacher_feedback") or "").strip()
        payload: dict = {}
        if score is not None:
            payload["submission"] = {"posted_grade": str(score)}
        if feedback:
            payload.setdefault("comment", {})["text_comment"] = feedback
        if not payload:
            errors.append(f"{st['real_name']}: nothing to push (no score or feedback).")
            continue

        _, err = canvas_send(
            "PUT",
            f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/{st['user_id']}",
            payload,
        )
        if err:
            errors.append(f"{st['real_name']}: {err}")
        else:
            st["posted"] = True
            st["status"] = "posted"
            pushed += 1

    if pushed or errors:
        session["push_log"].append({
            "ts":     datetime.now().isoformat(timespec="seconds"),
            "pushed": pushed,
            "errors": errors,
        })
        save_session(session)

    return {"ok": not errors, "pushed": pushed, "errors": errors}, 200
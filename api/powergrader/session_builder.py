"""PowerGrader session builder — constructs student list and session dict."""

from datetime import datetime


def build_students(
    *,
    submitted: list[dict],
    ai_by_uid: dict,
    roster_settings: dict,
    tier_map: dict,
    monitored: dict,
    extra_time_map: dict,
) -> list[dict]:
    """Build the sorted student list for a session from Canvas submission data."""
    students = []
    for s in submitted:
        uid = str(s.get("user_id", ""))
        user = s.get("user") or {}
        real_name = user.get("name") or user.get("sortable_name") or uid

        rst = roster_settings.get(uid, {})
        tier_id = rst.get("tier_id") or ""
        tier = tier_map.get(tier_id, {})
        mon = monitored.get(uid)
        extra_days = extra_time_map.get(uid, 0)

        body = s.get("body") or ""
        attachments = [
            {"filename": a.get("filename") or a.get("display_name", ""), "size": a.get("size", 0)}
            for a in (s.get("attachments") or [])
            if a.get("filename") or a.get("display_name")
        ]
        code_files = [
            {"filename": cf.get("filename", ""), "text": cf.get("text", "")}
            for cf in (s.get("code_files") or [])
        ]

        ai = ai_by_uid.get(uid, {})
        students.append({
            "user_id":       uid,
            "real_name":     real_name,
            "body":          body,
            "attachments":   attachments,
            "code_files":    code_files,
            "current_score": s.get("score"),
            "status":        "pending",
            "ai_score":      ai.get("score"),
            "ai_feedback":   ai.get("feedback"),
            "teacher_score": None,
            "teacher_feedback": "",
            "posted":        False,
            "tier_id":       tier_id,
            "tier_label":    tier.get("teacher_label", ""),
            "tier_alias":    tier.get("alias", ""),
            "is_monitored":  bool(mon),
            "monitored_note": (mon or {}).get("note", ""),
            "extra_time_days": extra_days,
            **({"late_catchup": s.get("late_catchup")} if s.get("late_catchup") else {}),
        })

    students.sort(key=lambda x: x["real_name"].lower())
    return students


def build_session(
    *,
    session_id: str,
    course_id: str,
    assignment_id: str,
    assignment_name: str,
    points_possible: float,
    mode: str,
    rubric_name: str,
    persona_id: str,
    selected_model: str,
    assignment_description: str = "",
    response_kind: str = "",
    privacy_steps: list[dict] | None = None,
    privacy_artifacts: dict | None = None,
    students: list[dict] | None = None,
    mode_label: str = "",
    copilot_packet: dict | None = None,
    late_watch: dict | None = None,
) -> dict:
    """Build the session dictionary ready to save."""
    return {
        "session_id":      session_id,
        "course_id":       course_id,
        "assignment_id":   assignment_id,
        "assignment_name": assignment_name,
        "assignment_description": assignment_description,
        "points_possible": points_possible,
        "created":         datetime.now().isoformat(timespec="seconds"),
        "mode":            mode,
        "mode_label":      mode_label,
        "rubric_name":     rubric_name,
        "persona_id":      persona_id,
        "model_id":        selected_model if mode == "assisted" else "",
        "response_kind":   response_kind,
        "privacy_steps":   privacy_steps or [],
        "privacy_artifacts": privacy_artifacts or {},
        "copilot_packet":  copilot_packet,
        "late_watch":      late_watch,
        "students":        students or [],
        "push_log":        [],
    }

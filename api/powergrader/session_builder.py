"""PowerGrader session builder — constructs student list and session dict."""

from datetime import datetime

try:
    from powergrader.student_attachments import eligibility_decision
except ModuleNotFoundError:
    from api.powergrader.student_attachments import eligibility_decision


def _attachment_metadata(attachment: dict) -> dict:
    """Persist review metadata only; never persist a Canvas/signed URL."""
    allowed = (
        "filename", "display_name", "local_path", "declared_size", "actual_size",
        "size", "detected_media_type", "media_type", "download_status",
        "extraction_status", "extracted_text_path", "attempt", "item_id",
        "item_link", "ai_eligible", "local_only", "warnings", "error_code",
        "error_message",
    )
    return {key: attachment.get(key) for key in allowed if key in attachment}


def build_students(
    *,
    submitted: list[dict],
    ai_by_uid: dict,
    roster_settings: dict,
    tier_map: dict,
    monitored: dict,
    extra_time_map: dict,
    ai_failures: dict | None = None,
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
            _attachment_metadata({**a, "filename": a.get("filename") or a.get("display_name", "")})
            for a in (s.get("attachments") or [])
            if a.get("filename") or a.get("display_name")
        ]
        code_files = [
            {"filename": cf.get("filename", ""), "text": cf.get("text", "")}
            for cf in (s.get("code_files") or [])
        ]
        new_quiz_items = []
        for item in (s.get("new_quiz_items") or []):
            new_quiz_items.append({
                key: item.get(key) for key in ("item_id", "type", "prompt", "possible", "earned_score", "files")
                if key in item
            })
        expected_count = s.get("expected_attachment_count")
        if expected_count is None and not attachments:
            expected_count = 0
        eligibility = eligibility_decision(attachments, expected_count=expected_count)

        ai = ai_by_uid.get(uid, {})
        ai_failure = (ai_failures or {}).get(uid)
        students.append({
            "user_id":       uid,
            "real_name":     real_name,
            "body":          body,
            "attachments":   attachments,
            "attachment_expected_count": expected_count,
            "new_quiz_items": new_quiz_items,
            "attachment_eligibility": eligibility,
            "new_quiz_files_error": s.get("new_quiz_files_error"),
            "code_files":    code_files,
            "current_score": s.get("score"),
            "status":        "pending",
            "ai_score":      ai.get("score"),
            "ai_feedback":   ai.get("feedback"),
            **({"ai_scoring_error": ai_failure} if ai_failure else {}),
            "teacher_score": None,
            "teacher_feedback": "",
            "posted":        False,
            "tier_id":       tier_id,
            "tier_label":    tier.get("teacher_label", ""),
            "tier_alias":    tier.get("alias", ""),
            "is_monitored":  bool(mon),
            "monitored_note": (mon or {}).get("note", ""),
            "extra_time_days": extra_days,
            **({"new_quiz_attempt": s.get("new_quiz_attempt"), "canvas_late": bool(s.get("late")),
                "seconds_late": s.get("seconds_late")} if s.get("new_quiz_attempt") is not None else {}),
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
    canvas_writeback_supported: bool = True,
    evidence_manifest: str | None = None,
    evidence_status: str = "unknown",
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
        "canvas_writeback_supported": canvas_writeback_supported,
        "evidence_manifest": evidence_manifest,
        "evidence_status": evidence_status,
        "students":        students or [],
        "push_log":        [],
    }

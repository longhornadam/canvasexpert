"""Pure helper functions for PowerGrader route parsing and responses."""

AI_MODES = {"packet", "assisted"}


def normalize_mode(mode: str) -> str:
    if mode in {"fast", "packet", "assisted"}:
        return mode
    return "fast"


def build_late_watch_state(
    *,
    mode: str,
    watch_late: str,
    has_openrouter_key: bool,
    initial_missing_user_ids: list[str],
    submitted_user_ids: list[str],
    response_kind: str,
) -> dict:
    watch_late_enabled = str(watch_late).lower() in {"1", "true", "yes", "on"}
    late_supported = mode == "assisted" and has_openrouter_key
    late_reason = ""
    if not watch_late_enabled:
        late_reason = "Late catch-up is disabled for this session."
    elif mode != "assisted":
        late_reason = "Late catch-up requires Auto-Score With API."
        watch_late_enabled = False
    elif not late_supported:
        late_reason = "Late catch-up requires Auto-Score With API and a saved OpenRouter key."
        watch_late_enabled = False

    return {
        "enabled": watch_late_enabled,
        "supported": late_supported,
        "reason": late_reason,
        "initial_missing_user_ids": initial_missing_user_ids,
        "known_user_ids": submitted_user_ids,
        "scored_user_ids": [],
        "last_checked": None,
        "last_scored": None,
        "last_summary": "",
        "source_context": {},
        "response_kind": response_kind,
    }


def build_start_error_payload(
    error: str,
    *,
    privacy_steps: list[dict] | None = None,
    budget: dict | None = None,
    debug_path: str | None = None,
) -> dict:
    payload = {
        "ok": False,
        "error": error,
        "privacy_steps": privacy_steps or [],
    }
    if budget:
        payload["budget"] = budget
    if debug_path:
        payload["debug_path"] = debug_path
    return payload


def build_start_success_payload(
    *,
    session_id: str,
    students: list[dict],
    assignment_name: str,
    mode: str,
    mode_label: str,
    ai_by_uid: dict,
    privacy_steps: list[dict],
    privacy_artifacts: dict,
    copilot_packet: dict | None,
) -> dict:
    return {
        "ok": True,
        "session_id": session_id,
        "student_count": len(students),
        "assignment_name": assignment_name,
        "mode": mode,
        "mode_label": mode_label,
        "ai_scored": len(ai_by_uid),
        "privacy_steps": privacy_steps,
        "packet_zip": privacy_artifacts.get("packet_zip"),
        "copilot_batch_count": (copilot_packet or {}).get("batch_count", 0),
        "copilot_packet_folder": (copilot_packet or {}).get("packet_folder"),
    }


def build_late_preview_students(new_subs: list[dict]) -> list[dict]:
    return [
        {
            "user_id": str(sub.get("user_id", "")),
            "name": (sub.get("user") or {}).get("name")
            or (sub.get("user") or {}).get("sortable_name")
            or str(sub.get("user_id", "")),
            "submitted_at": sub.get("submitted_at") or "",
        }
        for sub in new_subs
    ]


def build_late_preview_payload(new_subs: list[dict]) -> dict:
    message = f"{len(new_subs)} new late submission(s) found."
    return {
        "ok": True,
        "new_count": len(new_subs),
        "students": build_late_preview_students(new_subs),
        "message": message,
    }
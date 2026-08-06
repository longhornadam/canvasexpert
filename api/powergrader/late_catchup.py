from __future__ import annotations

"""PowerGrader late catch-up helpers."""

from api.webui import config, workspace
from api.webui.schooldays import _parse_iso_local, _school_days_late_detail


def is_real_submission(sub: dict) -> bool:
    """True when a Canvas row contains actual student work."""
    return bool((sub or {}).get("submission_type")) and (sub or {}).get("workflow_state") != "unsubmitted"


def current_session_user_ids(session: dict) -> set[str]:
    """User IDs already present in session['students']."""
    return {str(st.get("user_id", "")) for st in (session or {}).get("students") or [] if st.get("user_id")}


def find_new_submissions(session: dict, submissions: list[dict]) -> list[dict]:
    """Return actual submissions not already represented in the session."""
    session = session or {}
    seen_ids = current_session_user_ids(session)
    late_watch = session.get("late_watch") or {}
    restrict_to_missing = "initial_missing_user_ids" in late_watch
    missing_ids = {str(uid) for uid in (late_watch.get("initial_missing_user_ids") or []) if str(uid)}

    found: list[dict] = []
    for sub in submissions or []:
        uid = str(sub.get("user_id", ""))
        if not uid or uid in seen_ids:
            continue
        if restrict_to_missing and uid not in missing_ids:
            continue
        if not is_real_submission(sub):
            continue
        found.append(sub)
    return found


def initial_missing_user_ids(submissions: list[dict]) -> list[str]:
    """Return user IDs that were unsubmitted at initial session creation."""
    missing: list[str] = []
    for sub in submissions or []:
        if not is_real_submission(sub):
            uid = str(sub.get("user_id", ""))
            if uid:
                missing.append(uid)
    return missing


def make_late_batch_id(now=None) -> str:
    """Return stable label like late-YYYYMMDD-HHMMSS-ffffff.

    Matches workspace.RUN_STAMP_FORMAT -- this label becomes part of a
    teacher-visible "For AI/" run-folder name (see powergrader_late.py's
    artifact_name), so it uses the same stamp convention as every other
    PowerGrader run folder.
    """
    if now is None:
        return f"late-{workspace.run_stamp()}"
    if hasattr(now, "astimezone"):
        now = now.astimezone()
    return f"late-{now.strftime(workspace.RUN_STAMP_FORMAT)}"


def compute_late_meta(
    *,
    sub: dict,
    assignment: dict,
    course_id: str,
    extra_time_days: int,
    no_count_dates: set[str],
    batch_id: str,
) -> dict:
    """Return late_catchup metadata, including seconds_late_override."""
    due_iso = (sub or {}).get("cached_due_date") or (assignment or {}).get("due_at") or ""
    submitted_iso = (sub or {}).get("submitted_at") or ""
    meta = {
        "is_late_catchup": True,
        "submitted_at": submitted_iso,
        "due_at": due_iso,
        "school_days_late": None,
        "batch_id": batch_id,
    }

    due_dt = _parse_iso_local(due_iso)
    submitted_dt = _parse_iso_local(submitted_iso)
    if not due_dt or not submitted_dt or no_count_dates is None:
        return meta

    raw_days, _excluded = _school_days_late_detail(due_dt, submitted_dt, no_count_dates)
    school_days = max(int(raw_days or 0) - max(int(extra_time_days or 0), 0), 0)
    meta["school_days_late"] = school_days
    meta["seconds_late_override"] = school_days * 86400
    meta["course_id"] = str(course_id)
    return meta


def attach_late_meta(students: list[dict], by_user_id: dict[str, dict]) -> list[dict]:
    """Mutate/return student rows with late_catchup metadata attached."""
    for st in students or []:
        meta = by_user_id.get(str(st.get("user_id", "")))
        if meta:
            st["late_catchup"] = meta
    return students


def update_late_watch_after_preview(session: dict, new_count: int, now_iso: str) -> None:
    """Update last_checked and last_summary."""
    late_watch = (session or {}).setdefault("late_watch", {})
    late_watch["last_checked"] = now_iso
    if new_count:
        late_watch["last_summary"] = f"{new_count} new late submission(s) found."
    else:
        late_watch["last_summary"] = "No new late submissions found."


def update_late_watch_after_score(session: dict, appended_user_ids: list[str], now_iso: str) -> None:
    """Update known/scored IDs, last_scored, last_summary."""
    late_watch = (session or {}).setdefault("late_watch", {})
    known_ids = {str(uid) for uid in late_watch.get("known_user_ids") or [] if str(uid)}
    scored_ids = {str(uid) for uid in late_watch.get("scored_user_ids") or [] if str(uid)}
    for uid in appended_user_ids or []:
        uid = str(uid)
        if not uid:
            continue
        known_ids.add(uid)
        scored_ids.add(uid)
    late_watch["known_user_ids"] = sorted(known_ids)
    late_watch["scored_user_ids"] = sorted(scored_ids)
    late_watch["last_scored"] = now_iso
    late_watch["last_summary"] = (
        f"{len(appended_user_ids or [])} late submission(s) added to review."
        if appended_user_ids else "No late submissions added."
    )


def update_late_watch_after_generate(session: dict, appended_user_ids: list[str], now_iso: str) -> None:
    """Update known/generated IDs, last_generated, last_summary for packet mode."""
    late_watch = (session or {}).setdefault("late_watch", {})
    known_ids = {str(uid) for uid in late_watch.get("known_user_ids") or [] if str(uid)}
    generated_ids = {str(uid) for uid in late_watch.get("generated_user_ids") or [] if str(uid)}
    for uid in appended_user_ids or []:
        uid = str(uid)
        if not uid:
            continue
        known_ids.add(uid)
        generated_ids.add(uid)
    late_watch["known_user_ids"] = sorted(known_ids)
    late_watch["generated_user_ids"] = sorted(generated_ids)
    late_watch["last_generated"] = now_iso
    late_watch["last_summary"] = (
        f"{len(appended_user_ids or [])} late submission(s) processed for AI chat batch."
        if appended_user_ids else "No late submissions processed."
    )


def apply_lateness_to_submission_payload(payload: dict, student: dict) -> dict:
    """If student has late_catchup metadata, add late policy fields under submission."""
    meta = (student or {}).get("late_catchup") or {}
    override = meta.get("seconds_late_override")
    if override is None:
        return payload
    submission = payload.setdefault("submission", {})
    submission["late_policy_status"] = "late"
    submission["seconds_late_override"] = override
    return payload

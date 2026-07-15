"""Private New Quiz Student Analysis CSV fallback sessions.

The CSV is review evidence, never a Canvas result identity. Its bytes are parsed
in memory and discarded; the private session keeps review material, a digest,
and the minimum provenance for a later authoritative binding.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

try:
    from nq_report import constructed_responses, html_to_text, parse_student_analysis
except ModuleNotFoundError:  # pragma: no cover
    from api.nq_report import constructed_responses, html_to_text, parse_student_analysis


class CsvProvenanceError(ValueError):
    """A content-free CSV intake failure."""


def _text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvProvenanceError("The Student Analysis CSV must be UTF-8 encoded.") from exc


def build_csv_students(raw: bytes) -> tuple[list[dict], dict]:
    """Normalize CSV review data without retaining source bytes or a path."""
    if not raw:
        raise CsvProvenanceError("Choose a non-empty Student Analysis CSV.")
    source_students = (parse_student_analysis(_text(raw)).get("students") or [])
    if not source_students:
        raise CsvProvenanceError("The CSV did not contain any usable student rows.")
    students, provenance_rows, seen = [], [], set()
    for source in source_students:
        user_id, attempt = str(source.get("canvas_id") or "").strip(), source.get("attempt")
        if not user_id or user_id in seen or not isinstance(attempt, int) or attempt < 1:
            raise CsvProvenanceError("The CSV has an unusable student identity or attempt value.")
        seen.add(user_id)
        items = source.get("items") or []
        item_ids = [str(item.get("item_id") or "").strip() for item in items]
        if not item_ids or any(not value for value in item_ids) or len(set(item_ids)) != len(item_ids):
            raise CsvProvenanceError("The CSV has missing or duplicate New Quiz item identities.")
        constructed = constructed_responses(source)
        review_items = [{
            "item_id": str(item["item_id"]), "type": str(item.get("type") or ""),
            "prompt": str(item.get("prompt") or ""), "possible": item.get("points_possible_est"),
            "earned_score": item.get("earned_points"), "files": [],
        } for item in constructed]
        body = "\n\n".join(part for part in (
            f"{html_to_text(item.get('prompt') or '')}\n{html_to_text(item.get('response') or '')}".strip()
            for item in constructed) if part)
        native_manual = any(
            "upload" in str(item.get("type") or "").lower().replace("-", "_")
            or str(item.get("type") or "").lower() not in {"essay", ""}
            for item in constructed)
        students.append({
            "user_id": user_id, "real_name": str(source.get("name") or user_id), "body": body,
            "attachments": [], "attachment_expected_count": 0, "new_quiz_items": review_items,
            "attachment_eligibility": {"eligible": True, "reason": ""}, "new_quiz_files_error": None,
            # Unresolved CSV provenance requires SpeedGrader for the whole student.
            "speedgrader_required": True, "csv_native_manual_evidence": native_manual,
            "current_score": source.get("overall_score"), "status": "pending", "ai_score": None,
            "ai_feedback": "", "ai_item_results": [], "teacher_score": None,
            "teacher_feedback": "", "posted": False, "new_quiz_attempt": attempt,
        })
        provenance_rows.append({"user_id": user_id, "attempt": attempt, "item_ids": item_ids})
    students.sort(key=lambda row: row["real_name"].lower())
    return students, {"digest": hashlib.sha256(raw).hexdigest(), "rows": provenance_rows}


def make_csv_session(*, session_id: str, course_id: str, assignment_id: str,
                     assignment_name: str, raw: bytes) -> dict:
    students, provenance = build_csv_students(raw)
    return {
        "session_id": session_id, "course_id": str(course_id), "assignment_id": str(assignment_id),
        "assignment_name": str(assignment_name or assignment_id), "points_possible": None,
        "created": datetime.now().isoformat(timespec="seconds"),
        "mode": "fast", "mode_label": "New Quiz CSV review", "rubric_name": "", "persona_id": "",
        "model_id": "", "response_kind": "", "privacy_steps": [], "privacy_artifacts": {},
        "copilot_packet": None, "late_watch": {"supported": False, "enabled": False,
            "reason": "CSV fallback sessions do not support late catch-up."},
        "canvas_writeback_supported": False, "comment_writeback_supported": False,
        "new_quiz_item_finalization_supported": True, "evidence_manifest": None,
        "evidence_status": "csv_review_only", "students": students, "push_log": [],
        "new_quiz_csv_provenance": {"digest": provenance["digest"], "course_id": str(course_id),
            "assignment_id": str(assignment_id), "rows": provenance["rows"], "status": "unresolved",
            "bindings": {}},
    }

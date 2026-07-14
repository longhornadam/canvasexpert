"""PowerGrader import-results mutation — validate and apply AI results to a session."""

import json
import os
from datetime import datetime

import feedback_pipeline as fp


def import_results_into_session(
    session_id: str,
    results_text: str,
    *,
    batch_id: str = "",
    load_session,
    save_session,
    vault_factory,
) -> tuple[dict, int]:
    """Validate pasted AI results and apply them to the session.

    Returns (payload, status_code).  Status 404 only when session is missing.
    """
    session = load_session(session_id)
    if not session:
        return {"ok": False, "error": "Session not found."}, 404
    if not results_text.strip():
        return {"ok": False, "error": "Paste the AI result JSON first."}, 200

    artifacts = session.get("privacy_artifacts") or {}
    safe_bundle = artifacts.get("safe_bundle") or ""
    if not safe_bundle or not os.path.isfile(safe_bundle):
        return {"ok": False, "error": "Safe AI Packet student response bundle is missing."}, 200

    try:
        parsed = fp.parse_results(results_text)
    except Exception as e:
        return {"ok": False, "error": f"Could not parse JSON: {e}"}, 200
    try:
        with open(safe_bundle, encoding="utf-8") as f:
            bundle = json.load(f)
    except Exception as e:
        return {"ok": False, "error": f"Could not load Safe AI Packet bundle: {e}"}, 200

    batch = None
    expected_keys = set()
    batch_id = (batch_id or "").strip()
    if batch_id:
        for candidate in ((session.get("copilot_packet") or {}).get("batches") or []):
            if candidate.get("batch_id") == batch_id:
                batch = candidate
                break
        if not batch:
            return {"ok": False, "error": f"Copilot batch '{batch_id}' was not found in this session."}, 200
        expected_keys = {
            (row.get("pseudonym"), str(row.get("item_id", "")))
            for row in batch.get("expected_results") or []
        }
        errors = []
        for i, row in enumerate(parsed):
            key = (row.get("pseudonym") if isinstance(row, dict) else None,
                   str(row.get("item_id", "")) if isinstance(row, dict) else "")
            if key not in expected_keys:
                errors.append(f"results[{i}]: {key} belongs to another batch or was not in this batch")
        if errors:
            return {
                "ok": False,
                "error": "Validation failed. These results do not belong to this Copilot batch.",
                "validation": {
                    "ok": False,
                    "errors": errors,
                    "warnings": [],
                    "n": len(parsed),
                },
            }, 200

    vault = vault_factory()
    bundle_for_validation = _bundle_for_batch(bundle, expected_keys) if batch_id else bundle
    verdict = fp.validate_results(parsed, bundle_for_validation, vault)
    if not verdict["ok"]:
        return {
            "ok": False,
            "error": "Validation failed. Fix the JSON and paste again.",
            "validation": verdict,
        }, 200

    rows = fp.reidentify(parsed, vault)
    by_uid = fp.merge_rows_by_uid(rows)
    item_by_uid = fp.item_rows_by_uid(rows)
    updated = 0
    for st in session.get("students") or []:
        row = by_uid.get(str(st.get("user_id") or ""))
        if not row:
            continue
        st["ai_score"] = row.get("score")
        st["ai_feedback"] = row.get("feedback")
        st["ai_item_results"] = item_by_uid.get(str(st.get("user_id") or ""), [])
        updated += 1

    unresolved_count = sum(1 for row in rows if not row.get("resolved"))
    if batch is not None:
        batch["imported_at"] = datetime.now().isoformat(timespec="seconds")
        batch["updated"] = updated
        batch["last_validation"] = verdict
        batch["last_unresolved"] = unresolved_count
        if updated >= len(expected_keys) and not unresolved_count:
            batch["status"] = "imported"
        else:
            batch["status"] = "partial"

    session.setdefault("ai_import_log", []).append({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "batch_id": batch_id,
        "updated": updated,
        "validation": verdict,
    })
    save_session(session)
    payload = {
        "ok": True,
        "updated": updated,
        "validation": verdict,
        "unresolved": unresolved_count,
    }
    if batch_id:
        payload["batch_id"] = batch_id
        payload["batch_status"] = batch.get("status") if batch else ""
    return payload, 200


def _bundle_for_batch(full_bundle: dict, expected_keys: set[tuple[str, str]]) -> dict:
    """Return a SAFE bundle containing only responses expected for one batch."""
    filtered = dict(full_bundle or {})
    students = []
    for student in (full_bundle or {}).get("students") or []:
        responses = []
        pseudonym = student.get("pseudonym")
        for response in student.get("responses") or []:
            key = (pseudonym, str(response.get("item_id", "")))
            if key in expected_keys:
                responses.append(dict(response))
        if responses:
            copy = dict(student)
            copy["responses"] = responses
            students.append(copy)
    filtered["students"] = students
    return filtered

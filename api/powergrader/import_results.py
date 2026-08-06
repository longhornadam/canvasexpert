"""PowerGrader import-results mutation — validate and apply AI results to a session."""

import json
import os
from datetime import datetime
from functools import wraps

from api import feedback_pipeline as fp
from api.powergrader import session_store
from api.webui import workspace


def _session_locked(func):
    @wraps(func)
    def wrapped(session_id, *args, **kwargs):
        with session_store.session_lock(session_id):
            return func(session_id, *args, **kwargs)
    return wrapped


@_session_locked
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

    # 1. Parse results text
    try:
        parsed = fp.parse_results(results_text)
    except Exception as e:
        return {"ok": False, "error": f"Could not parse JSON: {e}"}, 200
    parsed_count = len(parsed) if isinstance(parsed, list) else 0

    # 2. Resolve batch and its expected keys without mutating the session
    batch = None
    expected_keys = set()
    clean_batch_id = (batch_id or "").strip()
    if clean_batch_id:
        for candidate in ((session.get("copilot_packet") or {}).get("batches") or []):
            if candidate.get("batch_id") == clean_batch_id:
                batch = candidate
                break
        if not batch:
            return {"ok": False, "error": f"AI chat batch '{clean_batch_id}' was not found in this session."}, 200
        expected_keys = {
            (row.get("pseudonym"), str(row.get("item_id", "")))
            for row in batch.get("expected_results") or []
        }
        # Fail closed: a batch that expects results but got none must not
        # read as a success just because there is nothing left to reject.
        if not parsed_count and expected_keys:
            return _zero_parse_failure()
        errors = []
        for i, row in enumerate(parsed):
            key = (row.get("pseudonym") if isinstance(row, dict) else None,
                   str(row.get("item_id", "")) if isinstance(row, dict) else "")
            if key not in expected_keys:
                errors.append(f"results[{i}]: {key} belongs to another batch or was not in this batch")
        if errors:
            return {
                "ok": False,
                "error": "Validation failed. These results do not belong to this AI chat batch.",
                "validation": {
                    "ok": False,
                    "errors": errors,
                    "warnings": [],
                    "n": len(parsed),
                },
            }, 200
    elif not parsed_count and _awaiting_ai_suggestions(session):
        # Same fail-closed rule for the whole-session (no batch_id) path: a
        # session with students still waiting on an AI draft must not read
        # as a success when the paste yielded nothing to apply.
        return _zero_parse_failure()

    # 3. Select the SAFE bundle path
    # If a batch explicitly names a safe_bundle path, that path must exist
    # (fail closed).  Fallback to the top-level bundle only when the batch
    # has no safe_bundle key at all.
    if batch:
        batch_path = batch.get("safe_bundle")
        if batch_path:
            if not os.path.isfile(workspace.extended_path(batch_path)):
                return {"ok": False, "error": "Safe AI Packet student response bundle is missing."}, 200
            safe_bundle = batch_path
        else:
            # Batch has no safe_bundle key — fall back to top-level bundle
            artifacts = session.get("privacy_artifacts") or {}
            safe_bundle = artifacts.get("safe_bundle") or ""
    else:
        artifacts = session.get("privacy_artifacts") or {}
        safe_bundle = artifacts.get("safe_bundle") or ""

    if not safe_bundle or not os.path.isfile(workspace.extended_path(safe_bundle)):
        return {"ok": False, "error": "Safe AI Packet student response bundle is missing."}, 200

    # 4. Load the bundle
    try:
        with open(workspace.extended_path(safe_bundle), encoding="utf-8") as f:
            bundle = json.load(f)
    except Exception as e:
        return {"ok": False, "error": f"Could not load Safe AI Packet bundle: {e}"}, 200

    # 5. Validate against bundle
    vault = vault_factory()
    bundle_for_validation = _bundle_for_batch(bundle, expected_keys) if clean_batch_id else bundle
    verdict = fp.validate_results(parsed, bundle_for_validation, vault)
    if not verdict["ok"]:
        return {
            "ok": False,
            "error": "Validation failed. Fix the JSON and paste again.",
            "validation": verdict,
        }, 200

    # 6. Reidentify and merge
    rows = fp.reidentify(parsed, vault)
    by_uid = fp.merge_rows_by_uid(rows)
    item_by_uid = fp.item_rows_by_uid(rows)
    updated_user_ids: set[str] = set()
    for st in session.get("students") or []:
        uid = str(st.get("user_id") or "")
        row = by_uid.get(uid)
        if not row:
            continue
        st["ai_score"] = row.get("score")
        st["ai_feedback"] = row.get("feedback")
        st["writing_process_observations"] = row.get("writing_process_observations", "")
        st["ai_item_results"] = item_by_uid.get(uid, [])
        updated_user_ids.add(uid)
    updated = len(updated_user_ids)

    # 7. Update batch metadata
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

    # 8. Log and save
    session.setdefault("ai_import_log", []).append({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "batch_id": clean_batch_id,
        "updated": updated,
        "validation": verdict,
    })
    save_session(session)
    payload = {
        "ok": True,
        "updated": updated,
        "updated_user_ids": sorted(updated_user_ids),
        "validation": verdict,
        "unresolved": unresolved_count,
        "parsed_count": parsed_count,
    }
    if clean_batch_id:
        payload["batch_id"] = clean_batch_id
        payload["batch_status"] = batch.get("status") if batch else ""
    return payload, 200


def _zero_parse_failure() -> tuple[dict, int]:
    """The paste yielded no usable results against a target that expects some."""
    return {
        "ok": False,
        "error": (
            "Read 0 results from the pasted text. Check that the reply is a "
            "JSON array of result objects, then paste it again."
        ),
        "parsed_count": 0,
    }, 200


def _awaiting_ai_suggestions(session: dict) -> bool:
    """True when at least one session student has no AI draft yet."""
    return any(not st.get("ai_feedback") for st in session.get("students") or [])


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

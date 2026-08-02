"""Scoring packet projection for MCP tool consumption.

Mirrors scoring_packet.py, extracting logic testable without an MCP client.
"""
import json
from datetime import datetime

from api import feedback_contract
from api.webui import source_materials


def _canonical_digest(value: dict) -> str:
    """Canonical SHA-256 hex digest over sorted JSON representation."""
    import hashlib
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _tabulate(rows: list[dict], columns: tuple[str, ...]) -> dict:
    """Convert list of dicts to {columns, rows} table format."""
    return {
        "columns": list(columns),
        "rows": [[row.get(col) for col in columns] for row in rows],
    }


def build_packet(
    session: dict,
    safe_bundle: dict,
    *,
    offset: int = 0,
    limit: int = 10,
    include_context: bool = True,
    include_writing_timeline: bool = False,
    rubric_text: str = "",
    persona: dict | None = None,
) -> dict:
    """Build a scoring packet from a SAFE bundle.

    Returns a dict with:
    - packet_digest: SHA-256 over canonicalized bundle + session_id
    - items: {columns, rows} table of prompts (deduplicated by item_id)
    - students: {columns, rows} table of pseudonym + item_id + response text
    - total: total student count in bundle
    - returned: count of students in this page
    - next_offset: offset for next page (or null if final)
    - held: count of students with held/attachment-only responses
    - held_pseudonyms: list of pseudonym strings for held students
    - included_context: bool (true if contract/rubric were included)
    - estimated_tokens: projected token count for this payload

    Raises PayloadTooLarge if projected payload > 25,000 tokens.
    """
    # Compute digest over canonicalized SAFE bundle + session_id
    digest_source = {
        "bundle": json.loads(json.dumps(safe_bundle)),
        "session_id": str(session.get("session_id") or ""),
    }
    packet_digest = _canonical_digest(digest_source)

    # Load student responses from SAFE bundle
    students = safe_bundle.get("students") or []
    total = len(students)

    # Build items table (deduplicated prompts by item_id)
    items_by_id = {}
    for student in students:
        for response in student.get("responses") or []:
            item_id = str(response.get("item_id") or "")
            if item_id not in items_by_id:
                items_by_id[item_id] = {
                    "item_id": item_id,
                    "prompt": response.get("prompt", ""),
                    "possible": response.get("possible"),
                }

    # Build students table: pseudonym + item_id + response (no media)
    student_rows = []
    held_count = 0
    held_pseudonyms = []

    for student in students:
        pseudonym = student.get("pseudonym", "")
        has_responses = False

        for response in student.get("responses") or []:
            # Skip media-only responses (no "response" field)
            response_text = response.get("response", "").strip()
            if not response_text:
                # Check if this is attachment-only (has media, no text)
                if response.get("media"):
                    if pseudonym not in held_pseudonyms:
                        held_pseudonyms.append(pseudonym)
                    held_count += 1
                continue

            has_responses = True
            item_id = str(response.get("item_id") or "")

            student_rows.append({
                "pseudonym": pseudonym,
                "item_id": item_id,
                "text": response_text,
            })

        # Student with no text responses at all
        if not has_responses and student.get("responses"):
            if pseudonym not in held_pseudonyms:
                held_pseudonyms.append(pseudonym)
            held_count += len(student.get("responses") or [])

    # Apply paging
    paged_students = student_rows[offset : offset + limit]
    returned = len(paged_students)
    has_next = (offset + limit) < len(student_rows)
    next_offset = offset + limit if has_next else None

    # Build context: contract, rubric, shared_context (if include_context)
    context_payload = {}
    if include_context:
        # Build contract text
        contract_text = feedback_contract.build_contract_text(
            ai_ta_name=str((persona or {}).get("name") or "your teaching assistant"),
            rubric_text=rubric_text,
            persona=persona,
        )
        context_payload["contract"] = contract_text

        # Include shared context if present
        shared = safe_bundle.get("shared_context")
        if shared:
            context_payload["shared_context"] = {
                "assignment_description": shared.get("assignment_description", ""),
                "materials": shared.get("materials", []),
            }

    # Estimate token count
    estimated_tokens = source_materials.estimate_text_tokens(
        json.dumps({
            "items": items_by_id,
            "students": paged_students,
            "context": context_payload,
        })
    )

    # Guard against oversized payloads (25k token cap)
    if estimated_tokens > 25_000:
        suggested_limit = max(1, limit - 2)
        raise OverflowError(
            f"Projected payload ({estimated_tokens} tokens) exceeds 25,000 token limit. "
            f"Try limit={suggested_limit} or a narrower offset range."
        )

    # Build result payload
    result = {
        "ok": True,
        "packet_digest": packet_digest,
        "items": _tabulate(sorted(items_by_id.values(), key=lambda x: x["item_id"]),
                           ("item_id", "prompt", "possible")),
        "students": _tabulate(paged_students, ("pseudonym", "item_id", "text")),
        "total": total,
        "returned": returned,
        "included_context": include_context,
        "held": held_count,
        "held_pseudonyms": held_pseudonyms,
        "estimated_tokens": estimated_tokens,
    }

    # Add context if included
    if context_payload:
        result.update(context_payload)

    if next_offset is not None:
        result["next_offset"] = next_offset

    return result

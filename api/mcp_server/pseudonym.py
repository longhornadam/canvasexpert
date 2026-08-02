"""Pseudonymization + outbound safety gate for the MCP server.

Every student-data tool in ``tools.py`` routes its assembled payload through
these helpers before it can reach an MCP client: real Canvas identity (name,
sortable_name, short_name, sis_id, canvas user id, section) never leaves this
module. Nothing here writes files beyond the existing identity vault, and
nothing here is logged.
"""
from __future__ import annotations

import re

from api.roster_service import fetch_students as _fetch_students
from api import feedback_safety, feedback_scrub
from api.nq_report import html_to_text


# A scan_payload() hard violation for a leaked real id embeds the id value
# itself in the message string ("real id '<value>' present at <path>"). Strip
# it before any violation description can reach an MCP client.
_REAL_ID_VIOLATION = re.compile(r"^real id '.*?' present at (.+)$")


def _section_names_for_user(user: dict, section_map: dict) -> list[str]:
    names: list[str] = []
    for enrollment in user.get("enrollments") or []:
        section_id = str(enrollment.get("course_section_id") or "")
        if section_id and section_id in section_map and section_map[section_id] not in names:
            names.append(section_map[section_id])
    return names


def pseudonymize_roster(vault, users: list[dict], section_map: dict) -> list[dict]:
    """``[{pseudonym, section_names}]``, sorted by pseudonym. Assumes ``users``
    have already been upserted into ``vault`` (via ``roster_service``),
    so this only reads pseudonyms — it never assigns new ones."""
    rows = []
    for u in users or []:
        cid = u.get("id")
        if cid is None:
            continue
        rows.append({
            "pseudonym": vault.get_or_assign(cid),
            "section_names": _section_names_for_user(u, section_map),
        })
    rows.sort(key=lambda r: r["pseudonym"])
    return rows


def resolve_pseudonym(vault, users: list[dict], requested: str) -> str | None:
    """Resolve a pseudonym only within the current local roster.

    The returned value is an internal Canvas user id for the caller's mutation
    path; callers must never place it in an MCP payload.  Requiring membership
    in ``users`` prevents an old vault entry from addressing a withdrawn
    student and keeps identity resolution mirror-only.
    """
    if not isinstance(requested, str) or not requested.strip():
        return None
    reverse = getattr(vault, "reverse", None)
    if reverse is None:
        return None
    entry = reverse(requested.strip())
    if not entry:
        return None
    local_id = str(entry.get("canvas_id") or "")
    current_ids = {str(user.get("id")) for user in users or [] if user.get("id") is not None}
    return local_id if local_id and local_id in current_ids else None


def pseudonymize_submission_rows(vault, subs: list[dict]) -> list[dict]:
    """Per-submission rows with the body scrubbed of every roster real name
    and nickname, and the author identified only by pseudonym. Attachments
    are never included — filenames are a common identity leak vector."""
    replacement_map = feedback_scrub.build_replacement_map(vault.entries(), set())
    rows = []
    for sub in subs or []:
        user_id = sub.get("user_id")
        if user_id is None:
            continue
        text = feedback_scrub.scrub_text(html_to_text(sub.get("body") or ""), replacement_map)
        rows.append({
            "pseudonym": vault.get_or_assign(user_id),
            "workflow_state": sub.get("workflow_state", ""),
            "submitted_at": sub.get("submitted_at"),
            "late": bool(sub.get("late")),
            "missing": bool(sub.get("missing")),
            "excused": bool(sub.get("excused")),
            "score": sub.get("score"),
            "grade": sub.get("grade"),
            "text": text,
        })
    return rows


def pseudonymize_gradebook_rows(vault, students: list[dict]) -> list[dict]:
    """Map ``build_snapshot`` student rows (which carry ``user_id``) to
    ``{pseudonym, missing, late, ungraded, pct}``."""
    rows = []
    for s in students or []:
        user_id = s.get("user_id")
        if user_id is None:
            continue
        rows.append({
            "pseudonym": vault.get_or_assign(user_id),
            "missing": s.get("missing", 0),
            "late": s.get("late", 0),
            "ungraded": s.get("ungraded", 0),
            "pct": s.get("pct"),
        })
    return rows


def _sanitize_violation(message: str) -> str:
    """Strip any real identifier value out of a scan_payload() violation
    string before it can reach an MCP client."""
    match = _REAL_ID_VIOLATION.match(message)
    if match:
        return f"real identifier value present at {match.group(1)}"
    return message


def gate(payload: dict, vault) -> dict:
    """Final outbound safety check for every student-data tool. Fail closed:
    any hard violation withholds the payload entirely; only sanitized
    violation descriptions are returned, never the flagged name or id value.
    Soft flags (a roster name appearing inside free text) are dropped
    silently — they do not block and are not surfaced to the MCP client."""
    verdict = feedback_safety.scan_payload(payload, vault)
    if not verdict["green"]:
        return {
            "ok": False,
            "error": "Safety scan blocked this result before it left the machine.",
            "violations": [_sanitize_violation(h) for h in verdict["hard"]],
        }
    return {"ok": True, **payload}

"""Pure, read-only matching between DataForge profile students and a roster."""

from __future__ import annotations

from collections import defaultdict


def _text(value) -> str:
    return str(value or "").strip()


def build_coverage_report(profile_students: dict, linked_students: dict, roster_students: list[dict]) -> dict:
    """Build a private coverage report using only the explicit SIS-ID join.

    ``linked_students`` is the local pseudonym -> Eduphoria Local ID mapping
    supplied by the Identity Vault boundary. Roster records are already validated
    CanvasMirror rows. Names are
    copied only for the local report; this function never persists or publishes
    the result.
    """
    roster_by_sis: dict[str, list[dict]] = defaultdict(list)
    for student in roster_students or []:
        if not isinstance(student, dict):
            continue
        sis_id = _text(student.get("sis_user_id"))
        if sis_id:
            roster_by_sis[sis_id].append(student)

    rows = []
    linked_count = 0
    matched_count = 0
    missing_local_id_count = 0
    not_in_roster_count = 0
    ambiguous_roster_count = 0
    linked_roster_sis_ids = set()

    for pseudonym in sorted(profile_students or {}):
        summary = profile_students.get(pseudonym) or {}
        local_id = _text((linked_students or {}).get(pseudonym))
        row = {
            "pseudonym": pseudonym,
            "local_id": local_id,
            "latest_pct": summary.get("latest_pct"),
            "status": "missing_local_id",
            "canvas_id": "",
            "canvas_name": "",
            "roster_names": [],
        }

        if local_id:
            linked_count += 1
            candidates = roster_by_sis.get(local_id, [])
            linked_roster_sis_ids.add(local_id)
            row["roster_names"] = [
                _text(candidate.get("name") or candidate.get("sortable_name"))
                for candidate in candidates
            ]
            if len(candidates) == 1:
                candidate = candidates[0]
                row.update({
                    "status": "matched",
                    "canvas_id": _text(candidate.get("id")),
                    "canvas_name": _text(candidate.get("name") or candidate.get("sortable_name")),
                })
                matched_count += 1
            elif len(candidates) == 0:
                row["status"] = "not_in_roster"
                not_in_roster_count += 1
            else:
                row["status"] = "ambiguous_roster"
                ambiguous_roster_count += 1
        else:
            missing_local_id_count += 1

        rows.append(row)

    profile_count = len(rows)
    roster_only_count = sum(
        1 for sis_id, students in roster_by_sis.items()
        if sis_id not in linked_roster_sis_ids and students
    )
    return {
        "profile_student_count": profile_count,
        "linked_student_count": linked_count,
        "matched_count": matched_count,
        "missing_local_id_count": missing_local_id_count,
        "not_in_roster_count": not_in_roster_count,
        "ambiguous_roster_count": ambiguous_roster_count,
        "roster_student_count": sum(len(students) for students in roster_by_sis.values()),
        "roster_only_count": roster_only_count,
        "coverage_percent": round((matched_count / profile_count) * 100, 1) if profile_count else 0.0,
        "rows": rows,
    }

"""Assessment-to-Canvas-group proposal construction.

This module is deliberately framework-free and side-effect-free.  It turns one
offline DataForge snapshot plus a read-only mirror coverage join into a complete
placement proposal.  The web layer owns preview/apply; this module owns the
invariants that make a proposal safe to review.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict


GROUP_NAMES = ("Support", "Core", "Accelerate", "Extend")
METHODS = {"overall_pct", "staar_bands", "quartiles"}
DEFAULT_CUTOFFS = {"support": 60.0, "core": 75.0, "accelerate": 90.0}


class GroupingValidationError(ValueError):
    """A proposal cannot be safely previewed or applied."""


def _text(value) -> str:
    return str(value or "").strip()


def _number(value, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise GroupingValidationError(f"{label} must be a number.") from exc
    if not math.isfinite(number):
        raise GroupingValidationError(f"{label} must be a finite number.")
    return number


def _cutoffs(value) -> dict[str, float]:
    if value in (None, ""):
        return dict(DEFAULT_CUTOFFS)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise GroupingValidationError("Cutoffs must be valid JSON.") from exc
    if not isinstance(value, dict):
        raise GroupingValidationError("Cutoffs must be an object.")
    result = {
        key: _number(value.get(key), key.title())
        for key in ("support", "core", "accelerate")
    }
    if not all(0 <= result[key] <= 100 for key in result):
        raise GroupingValidationError("Cutoffs must be between 0 and 100.")
    if not (result["support"] < result["core"] < result["accelerate"]):
        raise GroupingValidationError("Cutoffs must be strictly increasing.")
    return result


def _group_set(groups) -> dict[str, dict]:
    if not isinstance(groups, list):
        raise GroupingValidationError("Select a Canvas group set with four groups.")
    by_name = {}
    for group in groups:
        if not isinstance(group, dict):
            continue
        group_id = _text(group.get("id") or group.get("group_id"))
        name = _text(group.get("name"))
        key = name.casefold()
        if not group_id or not name or key in by_name:
            raise GroupingValidationError(
                "The selected group set must contain each tier exactly once."
            )
        by_name[key] = {"id": group_id, "name": name}
    expected = {name.casefold() for name in GROUP_NAMES}
    if set(by_name) != expected:
        raise GroupingValidationError(
            "The selected group set must contain Support, Core, Accelerate, and Extend."
        )
    return {name: by_name[name.casefold()] for name in GROUP_NAMES}


BAND_KEYS = ("mas", "met", "app")


def _has_band_data(student: dict) -> bool:
    """Whether a snapshot row carries any STAAR band column at all.

    Absent bands and failed bands both read as "not met", so without this check
    a snapshot that has no band columns places every student in Support and then
    fails the empty-tier guard, which reports a distribution problem for what is
    really a wrong-method choice.
    """
    return any(_text(student.get(key)) for key in BAND_KEYS)


def _truthy_band(value) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"y", "yes", "true", "1", "met", "mas", "app"}
    return value is True or value == 1


def _staar_tier(student: dict) -> str:
    if _truthy_band(student.get("mas")):
        return "Extend"
    if _truthy_band(student.get("met")):
        return "Accelerate"
    if _truthy_band(student.get("app")):
        return "Core"
    return "Support"


def _overall_tier(score: float, cutoffs: dict[str, float]) -> str:
    if score < cutoffs["support"]:
        return "Support"
    if score < cutoffs["core"]:
        return "Core"
    if score < cutoffs["accelerate"]:
        return "Accelerate"
    return "Extend"


def _quartile_tiers(scored: list[dict]) -> dict[str, str]:
    if len(scored) < 4:
        raise GroupingValidationError("Quartiles require at least four scored students.")
    ordered = sorted(
        scored,
        key=lambda row: (_number(row["score"], "Score"), row["pseudonym"], row["canvas_id"]),
    )
    out = {}
    for index, row in enumerate(ordered):
        out[row["canvas_id"]] = GROUP_NAMES[min(3, (index * 4) // len(ordered))]
    return out


def _digest(proposal: dict) -> str:
    payload = json.dumps(proposal, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_grouping_proposal(
    snapshot: dict,
    coverage_report: dict,
    roster_students: list[dict],
    group_set: dict,
    *,
    method: str = "overall_pct",
    cutoffs=None,
    no_data_group: str = "",
) -> dict:
    """Return a complete, validated placement proposal.

    ``coverage_report`` is the output of :func:`build_coverage_report`.  Only
    rows with status ``matched`` can receive an assessment score.  Mirror
    roster IDs, rather than the assessment's student list, define the required
    coverage universe.
    """
    method = _text(method).lower()
    if method not in METHODS:
        raise GroupingValidationError("Choose Overall %, STAAR bands, or Quartiles.")
    no_data_group = _text(no_data_group)
    if no_data_group not in GROUP_NAMES:
        raise GroupingValidationError("Choose a required no-data placement tier.")
    cutoff_values = _cutoffs(cutoffs)
    group_map = _group_set(group_set.get("groups") if isinstance(group_set, dict) else None)

    roster_by_id = {}
    for student in roster_students or []:
        if not isinstance(student, dict):
            continue
        canvas_id = _text(student.get("id") or student.get("canvas_id"))
        if not canvas_id:
            continue
        if canvas_id in roster_by_id:
            raise GroupingValidationError("The mirror roster contains a duplicate student.")
        roster_by_id[canvas_id] = student
    if not roster_by_id:
        raise GroupingValidationError("The current mirror roster has no students.")

    snapshot_students = {}
    for student in (snapshot or {}).get("students", []):
        if not isinstance(student, dict):
            continue
        pseudonym = _text(student.get("n") or student.get("pseudonym"))
        if pseudonym:
            snapshot_students[pseudonym] = student

    matched_rows = {}
    for row in (coverage_report or {}).get("rows", []):
        if not isinstance(row, dict) or row.get("status") != "matched":
            continue
        canvas_id = _text(row.get("canvas_id"))
        pseudonym = _text(row.get("pseudonym"))
        if canvas_id and pseudonym and canvas_id in roster_by_id:
            matched_rows[canvas_id] = (pseudonym, row)

    placements = []
    scored = []
    for canvas_id, roster_student in sorted(roster_by_id.items()):
        pseudonym, coverage_row = matched_rows.get(canvas_id, ("", {}))
        assessment = snapshot_students.get(pseudonym, {})
        score = assessment.get("pct") if assessment else None
        try:
            score = _number(score, "Score") if score is not None else None
        except GroupingValidationError:
            score = None
        if score is not None and not 0 <= score <= 100:
            score = None
        placement = {
            "canvas_id": canvas_id,
            "display_name": _text(coverage_row.get("canvas_name")) or _text(
                roster_student.get("name") or roster_student.get("sortable_name")
            ),
            "pseudonym": pseudonym,
            "score": score,
            "status": "matched" if score is not None else "no_data",
            "group": "",
        }
        if score is not None:
            scored.append({**placement, "score": score})
        placements.append(placement)

    if method == "quartiles":
        quartile_groups = _quartile_tiers(scored)
    else:
        quartile_groups = {}

    if (
        method == "staar_bands"
        and scored
        and not any(
            _has_band_data(snapshot_students.get(row["pseudonym"], {})) for row in scored
        )
    ):
        raise GroupingValidationError(
            "This snapshot carries no STAAR performance bands, so every student "
            "would land in Support. Choose Overall % or Quartiles instead."
        )

    for placement in placements:
        if placement["score"] is None:
            placement["group"] = no_data_group
        elif method == "overall_pct":
            placement["group"] = _overall_tier(placement["score"], cutoff_values)
        elif method == "staar_bands":
            pseudonym = placement["pseudonym"]
            placement["group"] = _staar_tier(snapshot_students.get(pseudonym, {}))
        else:
            placement["group"] = quartile_groups[placement["canvas_id"]]

    by_group = defaultdict(list)
    for placement in placements:
        by_group[placement["group"]].append(placement["canvas_id"])
    empty = [name for name in GROUP_NAMES if not by_group[name]]
    if empty:
        raise GroupingValidationError(
            "The proposal would leave these required tiers empty: " + ", ".join(empty) + "."
        )

    tiers = [
        {
            "name": name,
            "group_id": group_map[name]["id"],
            "student_ids": by_group[name],
            "student_count": len(by_group[name]),
        }
        for name in GROUP_NAMES
    ]
    proposal = {
        "snapshot_id": _text((snapshot or {}).get("id")),
        "snapshot_label": _text((snapshot or {}).get("label") or (snapshot or {}).get("id")),
        "method": method,
        "cutoffs": cutoff_values,
        "no_data_group": no_data_group,
        "category_id": _text(group_set.get("category_id")),
        "roster_count": len(roster_by_id),
        "matched_count": len(scored),
        "no_data_count": len(roster_by_id) - len(scored),
        "placements": placements,
        "tiers": tiers,
    }
    proposal["proposal_digest"] = _digest(proposal)
    return proposal

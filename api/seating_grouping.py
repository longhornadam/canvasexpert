"""Pure local academic grouping helpers for temporary Seating proposals."""

from __future__ import annotations

import math
import random
import re

from api import seating_constraints, seating_state


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")
_ACADEMIC_FIELDS = {"score_column_id", "scores", "mentor_ready"}
SCORE_STRATEGIES = {"mixed_fours", "uniform_fours", "mentor_pairs"}
GROUP_SIZES = {
    "buddy_pairs": 2,
    "random_trios": 3,
    "mixed_fours": 4,
    "uniform_fours": 4,
    "mentor_pairs": 2,
}


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(_ID_RE.fullmatch(value))


def _valid_score(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _validated_layout(value: object) -> tuple[dict | None, str | None]:
    state, error = seating_state.validate_state({"layouts": [value], "modes": []})
    if error:
        return None, "layout is invalid."
    return state["layouts"][0], None


def validate_academic_context(value: object, context_value: object,
                              strategy: object) -> tuple[dict | None, str | None]:
    """Validate the minimal score and mentor projection for one local proposal."""
    context, context_error = seating_constraints.validate_context(context_value)
    if context_error:
        return None, context_error
    if strategy not in seating_state.STRATEGIES:
        return None, "strategy is unsupported."
    if not isinstance(value, dict) or set(value) != _ACADEMIC_FIELDS:
        return None, "academic context has an invalid shape."
    score_column_id = value.get("score_column_id")
    scores_value = value.get("scores")
    mentor_ready_value = value.get("mentor_ready")
    if not isinstance(score_column_id, str) or not isinstance(scores_value, dict) or not isinstance(mentor_ready_value, list):
        return None, "academic context has invalid values."
    student_ids = {student["id"] for student in context["students"]}
    scores: dict[str, int | float] = {}
    for student_id, score in scores_value.items():
        if not _valid_id(student_id) or student_id not in student_ids or not _valid_score(score):
            return None, "academic context has an invalid score."
        scores[student_id] = score
    mentor_ready: list[str] = []
    seen_ready: set[str] = set()
    for student_id in mentor_ready_value:
        if not _valid_id(student_id) or student_id not in student_ids or student_id in seen_ready:
            return None, "academic context has an invalid mentor-ready student."
        seen_ready.add(student_id)
        mentor_ready.append(student_id)
    if strategy in SCORE_STRATEGIES:
        if not _valid_id(score_column_id):
            return None, "this strategy requires a current score column."
    elif score_column_id or scores or mentor_ready:
        return None, "this strategy does not use academic score or mentor data."
    if strategy != "mentor_pairs" and mentor_ready:
        return None, "only mentor pairs may include mentor-ready students."
    return {
        "score_column_id": score_column_id,
        "scores": dict(sorted(scores.items())),
        "mentor_ready": sorted(mentor_ready),
    }, None


def seat_clusters(layout_value: object, group_size: object) -> tuple[list[list[str]] | None, str | None]:
    """Return deterministic edge-connected seat clusters with no persisted geometry."""
    layout, error = _validated_layout(layout_value)
    if error:
        return None, error
    if not isinstance(group_size, int) or isinstance(group_size, bool) or group_size not in {2, 3, 4}:
        return None, "group size must be 2, 3, or 4."
    seats = {seat["id"]: seat for seat in layout["seats"]}
    remaining = set(seats)
    clusters: list[list[str]] = []
    order = lambda seat_id_value: (seats[seat_id_value]["row"], seats[seat_id_value]["column"])
    while remaining:
        cluster = [min(remaining, key=order)]
        remaining.remove(cluster[0])
        while len(cluster) < group_size:
            choices = [
                seat_id_value for seat_id_value in remaining
                if any(
                    abs(seats[seat_id_value]["row"] - seats[current]["row"])
                    + abs(seats[seat_id_value]["column"] - seats[current]["column"]) == 1
                    for current in cluster
                )
            ]
            if not choices:
                break
            selected = min(choices, key=order)
            cluster.append(selected)
            remaining.remove(selected)
        clusters.append(cluster)
    return clusters, None


def _chunks(values: list[str], size: int, kind: str) -> list[dict]:
    return [
        {"kind": kind, "student_ids": values[index:index + size]}
        for index in range(0, len(values), size)
    ]


def _group_plan(context: dict, academic: dict, strategy: str) -> tuple[list[dict], int, list[str], int]:
    student_ids = [student["id"] for student in context["students"]]
    if strategy not in GROUP_SIZES:
        return [], 1, [], 0
    size = GROUP_SIZES[strategy]
    scores = academic["scores"]
    unscored = sorted(student_id for student_id in student_ids if student_id not in scores)
    if strategy == "buddy_pairs":
        used: set[str] = set()
        plan: list[dict] = []
        for relationship in context["relationships"]:
            first, second = relationship["students"]
            if relationship["type"] == "preferred_pair" and first not in used and second not in used:
                plan.append({"kind": "buddy_pair", "student_ids": [first, second]})
                used.update((first, second))
        plan.extend(_chunks([student_id for student_id in student_ids if student_id not in used], size, "pair"))
        return plan, size, [], 0
    if strategy == "random_trios":
        shuffled = list(student_ids)
        random.shuffle(shuffled)
        return _chunks(shuffled, size, "trio"), size, [], 0
    if strategy == "mixed_fours":
        ordered = [student_id for _, student_id in sorted((score, student_id) for student_id, score in scores.items())]
        mixed: list[str] = []
        left, right = 0, len(ordered) - 1
        while left <= right:
            mixed.append(ordered[left])
            left += 1
            if left <= right:
                mixed.append(ordered[right])
                right -= 1
        return _chunks(mixed + unscored, size, "mixed_four"), size, unscored, 0
    if strategy == "uniform_fours":
        ordered = [student_id for _, student_id in sorted((score, student_id) for student_id, score in scores.items())]
        return _chunks(ordered + unscored, size, "uniform_four"), size, unscored, 0

    ready = set(academic["mentor_ready"])
    used: set[str] = set()
    plan = []
    mentor_unpaired = 0
    mentors = sorted(ready, key=lambda student_id: (-scores.get(student_id, float("-inf")), student_id))
    for mentor in mentors:
        mentor_score = scores.get(mentor)
        if mentor_score is None:
            mentor_unpaired += 1
            continue
        peers = sorted(
            (score, student_id) for student_id, score in scores.items()
            if student_id not in ready and student_id not in used and score < mentor_score
        )
        if not peers:
            mentor_unpaired += 1
            continue
        peer = peers[0][1]
        plan.append({"kind": "mentor_pair", "student_ids": [mentor, peer]})
        used.update((mentor, peer))
    plan.extend(_chunks([student_id for student_id in student_ids if student_id not in used], size, "pair"))
    return plan, size, unscored, mentor_unpaired


def _place_groups(layout: dict, assignment_value: dict, locks: dict,
                  plan: list[dict], group_size: int) -> tuple[dict, list[dict]]:
    """Move only unlocked students into deterministic nearby seat clusters when feasible."""
    clusters, _ = seat_clusters(layout, group_size)
    assignment = dict(assignment_value)
    positions = {student_id: seat_id_value for seat_id_value, student_id in assignment.items()}
    unused_clusters = list(clusters or [])
    records: list[dict] = []
    for group in plan:
        members = list(group["student_ids"])
        member_set = set(members)
        selected_cluster = None
        for index, cluster in enumerate(unused_clusters):
            cluster_set = set(cluster)
            locked_members_fit = all(
                student_id not in locks.values() or positions.get(student_id) in cluster_set
                for student_id in members
            )
            foreign_lock = any(
                seat_id_value in locks and locks[seat_id_value] not in member_set
                for seat_id_value in cluster
            )
            if locked_members_fit and not foreign_lock:
                selected_cluster = unused_clusters.pop(index)
                break
        if selected_cluster is not None:
            cluster_set = set(selected_cluster)
            open_targets = [
                seat_id_value for seat_id_value in selected_cluster
                if seat_id_value not in locks and assignment.get(seat_id_value) not in member_set
            ]
            for student_id in members:
                current_seat = positions.get(student_id)
                if current_seat is None or current_seat in locks:
                    continue
                if current_seat in cluster_set:
                    continue
                if not open_targets:
                    break
                target_seat = open_targets.pop(0)
                displaced = assignment.get(target_seat)
                assignment[target_seat] = student_id
                positions[student_id] = target_seat
                assignment.pop(current_seat, None)
                if displaced is not None:
                    assignment[current_seat] = displaced
                    positions[displaced] = current_seat
            occupied = [
                seat_id_value for seat_id_value in selected_cluster
                if assignment.get(seat_id_value) in member_set
            ]
            complete = len(members) == group_size and len(occupied) == len(members)
        else:
            occupied = []
            complete = False
        records.append({
            "kind": group["kind"],
            "student_ids": members,
            "seat_ids": occupied,
            "complete": complete,
        })
    return assignment, records


def _notices(groups: list[dict], group_size: int, unscored: list[str], mentor_unpaired: int) -> list[dict]:
    notices: list[dict] = []
    if groups:
        notices.append({"kind": "groups", "group_size": group_size, "count": len(groups)})
    partial_count = sum(1 for group in groups if not group["complete"])
    if partial_count:
        notices.append({"kind": "partial_groups", "group_size": group_size, "count": partial_count})
    if unscored:
        notices.append({"kind": "unscored", "count": len(unscored)})
    if mentor_unpaired:
        notices.append({"kind": "mentor_unpaired", "count": mentor_unpaired})
    return notices


def _grouping_summary(plan: list[dict], group_size: int, unscored: list[str],
                      mentor_unpaired: int, assignment: dict | None = None) -> dict:
    positions = {student_id: seat_id_value for seat_id_value, student_id in (assignment or {}).items()}
    groups = [{
        "kind": group["kind"],
        "student_ids": list(group["student_ids"]),
        "seat_ids": [positions[student_id] for student_id in group["student_ids"] if student_id in positions],
        "complete": len(group["student_ids"]) == group_size,
    } for group in plan]
    return {"groups": groups, "notices": _notices(groups, group_size, unscored, mentor_unpaired)}


def generate(layout_value: object, context_value: object, strategy: object,
             academic_value: object, locks_value: object = None) -> tuple[dict | None, dict | None, dict | None, str | None]:
    """Generate a temporary group-aware local proposal with no score or name output."""
    layout, layout_error = _validated_layout(layout_value)
    if layout_error:
        return None, None, None, layout_error
    context, context_error = seating_constraints.validate_context(context_value)
    if context_error:
        return None, None, None, context_error
    academic, academic_error = validate_academic_context(academic_value, context, strategy)
    if academic_error:
        return None, None, None, academic_error
    locks, locks_error = seating_constraints.validate_locks(layout, context, {}, locks_value or {})
    if locks_error:
        return None, None, None, locks_error
    assignment, results, error = seating_constraints.generate(layout, context, locks)
    if error:
        return None, None, None, error
    plan, group_size, unscored, mentor_unpaired = _group_plan(context, academic, strategy)
    if plan:
        baseline_assignment = assignment
        baseline_results = results
        assignment, groups = _place_groups(layout, baseline_assignment, locks, plan, group_size)
        results, error = seating_constraints.evaluate(layout, context, assignment)
        if error:
            return None, None, None, error
        if (baseline_results["required_ok"] and not results["required_ok"]
                or len(results["required_violations"]) > len(baseline_results["required_violations"])):
            assignment = baseline_assignment
            results = baseline_results
            groups = [{
                "kind": group["kind"], "student_ids": list(group["student_ids"]),
                "seat_ids": [], "complete": False,
            } for group in plan]
        grouping = {"groups": groups, "notices": _notices(groups, group_size, unscored, mentor_unpaired)}
    else:
        grouping = {"groups": [], "notices": []}
    return assignment, results, grouping, None


def reroll(layout_value: object, context_value: object, strategy: object, academic_value: object,
           proposal_value: object, locks_value: object, reroll_seat_ids: object) -> tuple[dict | None, dict | None, dict | None, str | None]:
    """Regenerate only selected unlocked seats; all other proposal positions become fixed."""
    layout, layout_error = _validated_layout(layout_value)
    if layout_error:
        return None, None, None, layout_error
    context, context_error = seating_constraints.validate_context(context_value)
    if context_error:
        return None, None, None, context_error
    proposal, proposal_error = seating_constraints.validate_assignment(layout, context, proposal_value)
    if proposal_error:
        return None, None, None, proposal_error
    locks, locks_error = seating_constraints.validate_locks(layout, context, proposal, locks_value)
    if locks_error:
        return None, None, None, locks_error
    if not isinstance(reroll_seat_ids, list) or not reroll_seat_ids:
        return None, None, None, "select one or more unlocked proposal seats to reroll."
    valid_seat_ids = {seat["id"] for seat in layout["seats"]}
    selected: set[str] = set()
    for seat_id_value in reroll_seat_ids:
        if not _valid_id(seat_id_value) or seat_id_value not in valid_seat_ids or seat_id_value in selected:
            return None, None, None, "reroll selection has an invalid seat."
        if seat_id_value in locks:
            return None, None, None, "locked seats cannot be rerolled."
        selected.add(seat_id_value)
    fixed = {seat_id_value: student_id for seat_id_value, student_id in proposal.items()
             if seat_id_value not in selected}
    return generate(layout, context, strategy, academic_value, fixed)


def evaluate(layout_value: object, context_value: object, strategy: object,
             academic_value: object, proposal_value: object) -> tuple[dict | None, dict | None, str | None]:
    """Evaluate a changed temporary proposal and return generic group notices only."""
    layout, layout_error = _validated_layout(layout_value)
    if layout_error:
        return None, None, layout_error
    context, context_error = seating_constraints.validate_context(context_value)
    if context_error:
        return None, None, context_error
    academic, academic_error = validate_academic_context(academic_value, context, strategy)
    if academic_error:
        return None, None, academic_error
    proposal, proposal_error = seating_constraints.validate_assignment(layout, context, proposal_value)
    if proposal_error:
        return None, None, proposal_error
    results, results_error = seating_constraints.evaluate(layout, context, proposal)
    if results_error:
        return None, None, results_error
    plan, group_size, unscored, mentor_unpaired = _group_plan(context, academic, strategy)
    return results, _grouping_summary(plan, group_size, unscored, mentor_unpaired, proposal), None

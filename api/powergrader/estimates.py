"""Estimate helpers for PowerGrader — student count, bundle estimation, cost labels.
"""

import feedback_pipeline as fp

from webui import source_materials
from powergrader.context import apply_shared_context


def assignment_student_count(assignment: dict) -> tuple[int, str]:
    for key, label in (
        ("needs_grading_count", "Canvas needs_grading_count"),
        ("has_submitted_submissions", "Canvas submitted count"),
    ):
        value = assignment.get(key)
        if isinstance(value, bool):
            continue
        try:
            n = int(value)
        except (TypeError, ValueError):
            continue
        if n > 0:
            return n, label
    return 30, "default estimate"


def estimate_bundle(
    assignment_name: str,
    assignment_description: str,
    source_context: dict,
    student_count: int,
    response_kind: str,
) -> dict:
    response = source_materials.synthetic_student_response(response_kind)
    bundle = {
        "contract_version": fp.CONTRACT_VERSION,
        "quiz_title": assignment_name or "Assignment",
        "source": "powergrader_estimate",
        "review_required": True,
        "students": [
            {
                "pseudonym": f"Student {i + 1}",
                "responses": [{
                    "item_id": "estimate",
                    "prompt": "",
                    "response": response,
                    "possible": 5,
                }],
            }
            for i in range(max(1, int(student_count or 1)))
        ],
    }
    return apply_shared_context(bundle, assignment_description, source_context)


def cost_label(cost) -> str:
    if cost is None:
        return "unavailable"
    try:
        value = float(cost)
    except (TypeError, ValueError):
        return "unavailable"
    if value < 0.01:
        return "<$0.01"
    return f"${value:.2f}"
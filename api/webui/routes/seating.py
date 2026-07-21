"""Local-only API for Seating's physical layouts and manual assignments."""

from __future__ import annotations

import json

from fastapi import APIRouter, Form, Query
from fastapi.responses import JSONResponse

from api import seating_constraints, seating_grouping, seating_state
from .. import config


router = APIRouter(prefix="/api/seating", tags=["seating"])


def _parse_json(value: str, label: str) -> tuple[object | None, str | None]:
    try:
        return json.loads(value), None
    except json.JSONDecodeError as error:
        return None, f"Invalid {label} JSON: {error}"


def _mode_context(course_id: str, mode_id: str, context_value: object) -> tuple[dict | None, dict | None, dict | None, str | None]:
    """Return validated local state, mode, layout, and minimal section context."""
    state, state_error = seating_state.validate_state(
        seating_state.normalize_state(config.get_seating_course_state(course_id))
    )
    if state_error:
        return None, None, None, "Stored Seating state is invalid."
    mode = next((item for item in state["modes"] if item["id"] == mode_id), None)
    if mode is None:
        return None, None, None, "Seating mode not found."
    layout = next((item for item in state["layouts"] if item["id"] == mode["layout_id"]), None)
    if layout is None:
        return None, None, None, "Seating mode layout not found."
    context, context_error = seating_constraints.validate_context(context_value)
    if context_error:
        return None, None, None, context_error
    if context["section_id"] != mode["section_id"]:
        return None, None, None, "Seating context does not match this mode section."
    return state, mode, layout, context


@router.get("")
def seating_get(course_id: str = Query("")):
    """Return one course's local physical Seating state; never reads Canvas."""
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})
    return JSONResponse({
        "ok": True,
        "state": seating_state.normalize_state(config.get_seating_course_state(course_id)),
    })


@router.post("/state")
def seating_state_update(
    course_id: str = Form(...),
    state: str = Form(...),
):
    """Atomically replace a validated local Seating state; never reads Canvas."""
    if not course_id:
        return JSONResponse({"ok": False, "error": "course_id required."})
    try:
        candidate = json.loads(state)
    except json.JSONDecodeError as error:
        return JSONResponse({"ok": False, "error": f"Invalid seating state JSON: {error}"})
    validated, error = seating_state.validate_state(candidate)
    if error:
        return JSONResponse({"ok": False, "error": error})
    config.set_seating_course_state(course_id, validated)
    return JSONResponse({"ok": True, "state": validated})


@router.post("/proposal")
def seating_proposal(
    course_id: str = Form(...),
    mode_id: str = Form(...),
    operation: str = Form(...),
    context: str = Form(...),
    locks: str = Form("{}"),
    proposal: str = Form("{}"),
    reroll_seat_ids: str = Form("[]"),
    source_groups: str = Form("[]"),
    academic: str = Form('{"score_column_id":"","scores":{},"mentor_ready":[]}'),
):
    """Generate, reroll, or evaluate an in-memory local proposal only."""
    if not course_id or not mode_id:
        return JSONResponse({"ok": False, "error": "course_id and mode_id required."})
    context_value, error = _parse_json(context, "seating context")
    if error:
        return JSONResponse({"ok": False, "error": error})
    locks_value, error = _parse_json(locks, "locks")
    if error:
        return JSONResponse({"ok": False, "error": error})
    proposal_value, error = _parse_json(proposal, "proposal")
    if error:
        return JSONResponse({"ok": False, "error": error})
    reroll_value, error = _parse_json(reroll_seat_ids, "reroll seats")
    if error:
        return JSONResponse({"ok": False, "error": error})
    source_groups_value, error = _parse_json(source_groups, "source groups")
    if error:
        return JSONResponse({"ok": False, "error": error})
    academic_value, error = _parse_json(academic, "academic context")
    if error:
        return JSONResponse({"ok": False, "error": error})
    _, mode, layout, context_data = _mode_context(course_id, mode_id, context_value)
    if layout is None:
        return JSONResponse({"ok": False, "error": context_data})

    if operation == "generate":
        generated, results, grouping, error = seating_grouping.generate(
            layout, context_data, mode["strategy"], academic_value, locks_value
        )
    elif operation == "reroll":
        generated, results, grouping, error = seating_grouping.reroll(
            layout, context_data, mode["strategy"], academic_value,
            proposal_value, locks_value, reroll_value,
        )
    elif operation == "evaluate":
        generated, error = seating_constraints.validate_assignment(layout, context_data, proposal_value)
        if error is None:
            _, error = seating_constraints.validate_locks(layout, context_data, generated, locks_value)
        if error is None:
            results, grouping, evaluation_error = seating_grouping.evaluate(
                layout, context_data, mode["strategy"], academic_value, generated
            )
            error = evaluation_error
        else:
            results, grouping = None, None
    elif operation == "import_groups":
        generated, results, grouping, error = seating_grouping.import_group_membership(
            layout, context_data, mode["strategy"], source_groups_value, locks_value,
        )
    elif operation == "group_plan":
        generated, error = seating_constraints.validate_assignment(
            layout, context_data, mode["assignment"]
        )
        if error is None:
            plan, error = seating_grouping.finalized_group_plan(
                layout, mode["strategy"], generated,
            )
        else:
            plan = None
        if error is None:
            results, results_error = seating_constraints.evaluate(layout, context_data, generated)
            if results_error:
                error = results_error
                grouping = None
            else:
                grouping = {"groups": plan["groups"], "notices": []}
                plan = {
                    **plan,
                    "unassigned_count": sum(
                        1 for student in context_data["students"]
                        if student["id"] not in generated.values()
                    ),
                }
        else:
            results, grouping = None, None
    else:
        return JSONResponse({"ok": False, "error": "Unknown Seating proposal operation."})
    if error:
        return JSONResponse({"ok": False, "error": error})
    response = {"ok": True, "proposal": generated, "results": results, "grouping": grouping}
    if operation == "group_plan":
        response["group_plan"] = plan
    return JSONResponse(response)


@router.post("/apply")
def seating_apply(
    course_id: str = Form(...),
    mode_id: str = Form(...),
    context: str = Form(...),
    proposal: str = Form(...),
):
    """Persist one clean proposal as the mode's single current assignment."""
    if not course_id or not mode_id:
        return JSONResponse({"ok": False, "error": "course_id and mode_id required."})
    context_value, error = _parse_json(context, "seating context")
    if error:
        return JSONResponse({"ok": False, "error": error})
    proposal_value, error = _parse_json(proposal, "proposal")
    if error:
        return JSONResponse({"ok": False, "error": error})
    state, mode, layout, context_data = _mode_context(course_id, mode_id, context_value)
    if state is None:
        return JSONResponse({"ok": False, "error": context_data})
    assignment, error = seating_constraints.validate_assignment(layout, context_data, proposal_value)
    if error:
        return JSONResponse({"ok": False, "error": error})
    results, error = seating_constraints.evaluate(layout, context_data, assignment)
    if error:
        return JSONResponse({"ok": False, "error": error})
    if not results["required_ok"]:
        return JSONResponse({"ok": False, "error": "Required Seating conditions are not met.", "results": results})
    updated_modes = [
        {**item, "assignment": assignment} if item["id"] == mode["id"] else item
        for item in state["modes"]
    ]
    updated = {"layouts": state["layouts"], "modes": updated_modes}
    config.set_seating_course_state(course_id, updated)
    return JSONResponse({"ok": True, "state": updated, "results": results})

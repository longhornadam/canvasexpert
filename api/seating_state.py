"""Pure validation and local transformations for private Seating state."""

from __future__ import annotations

import re


GRID_MIN = 1
GRID_MAX = 12
NAME_MAX_LENGTH = 80
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")
_STATE_FIELDS = {"layouts", "modes"}
_LAYOUT_FIELDS = {"id", "name", "rows", "columns", "seats", "near_teacher_seat_ids"}
_LEGACY_LAYOUT_FIELDS = _LAYOUT_FIELDS - {"near_teacher_seat_ids"}
_SEAT_FIELDS = {"id", "row", "column", "label"}
_MODE_FIELDS = {"id", "name", "section_id", "layout_id", "strategy", "assignment"}
STRATEGIES = {
    "manual", "testing", "buddy_pairs", "random_trios", "mixed_fours",
    "uniform_fours", "mentor_pairs",
}


def empty_state() -> dict:
    return {"layouts": [], "modes": []}


def seat_id(row: int, column: int) -> str:
    return f"seat-{row}-{column}"


def seat_label(row: int, column: int) -> str:
    return f"{row}-{column}"


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(_ID_RE.fullmatch(value))


def _valid_grid_size(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and GRID_MIN <= value <= GRID_MAX


def _valid_name(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value.strip()) <= NAME_MAX_LENGTH


def _normalize_layout(value: object) -> dict | None:
    if not isinstance(value, dict) or set(value) not in (_LAYOUT_FIELDS, _LEGACY_LAYOUT_FIELDS):
        return None
    if not _valid_id(value.get("id")) or not _valid_name(value.get("name")):
        return None
    rows, columns = value.get("rows"), value.get("columns")
    if not _valid_grid_size(rows) or not _valid_grid_size(columns):
        return None
    seats = value.get("seats")
    if not isinstance(seats, list):
        seats = []
    normalized_seats: list[dict] = []
    positions: set[tuple[int, int]] = set()
    for seat in seats:
        if not isinstance(seat, dict) or set(seat) != _SEAT_FIELDS:
            continue
        row, column = seat.get("row"), seat.get("column")
        if (not isinstance(row, int) or isinstance(row, bool)
                or not isinstance(column, int) or isinstance(column, bool)
                or not (GRID_MIN <= row <= rows and GRID_MIN <= column <= columns)):
            continue
        if seat.get("id") != seat_id(row, column) or seat.get("label") != seat_label(row, column):
            continue
        position = (row, column)
        if position in positions:
            continue
        positions.add(position)
        normalized_seats.append({"id": seat_id(row, column), "row": row,
                                 "column": column, "label": seat_label(row, column)})
    normalized_seats.sort(key=lambda seat: (seat["row"], seat["column"]))
    raw_near_teacher = value.get("near_teacher_seat_ids", [])
    if not isinstance(raw_near_teacher, list):
        raw_near_teacher = []
    seat_ids = {seat["id"] for seat in normalized_seats}
    marked_ids: set[str] = set()
    for seat_id_value in raw_near_teacher:
        if isinstance(seat_id_value, str) and seat_id_value in seat_ids:
            marked_ids.add(seat_id_value)
    return {"id": value["id"], "name": value["name"].strip(), "rows": rows,
            "columns": columns, "seats": normalized_seats,
            "near_teacher_seat_ids": [
                seat["id"] for seat in normalized_seats if seat["id"] in marked_ids
            ]}


def normalize_state(value: object) -> dict:
    """Safely normalize stored private state, dropping malformed records."""
    if not isinstance(value, dict) or set(value) != _STATE_FIELDS:
        return empty_state()
    layouts_value = value.get("layouts")
    modes_value = value.get("modes")
    if not isinstance(layouts_value, list) or not isinstance(modes_value, list):
        return empty_state()

    layouts: list[dict] = []
    layout_by_id: dict[str, dict] = {}
    for value_layout in layouts_value:
        layout = _normalize_layout(value_layout)
        if layout is None or layout["id"] in layout_by_id:
            continue
        layouts.append(layout)
        layout_by_id[layout["id"]] = layout

    modes: list[dict] = []
    mode_ids: set[str] = set()
    for value_mode in modes_value:
        if not isinstance(value_mode, dict) or set(value_mode) != _MODE_FIELDS:
            continue
        mode_id, layout_id, section_id = (
            value_mode.get("id"), value_mode.get("layout_id"), value_mode.get("section_id")
        )
        if (not _valid_id(mode_id) or mode_id in mode_ids or not _valid_name(value_mode.get("name"))
                or not _valid_id(layout_id) or layout_id not in layout_by_id
                or not _valid_id(section_id)):
            continue
        strategy = value_mode.get("strategy")
        if strategy not in STRATEGIES:
            strategy = "manual"
        assignment_value = value_mode.get("assignment")
        if not isinstance(assignment_value, dict):
            assignment_value = {}
        valid_seats = {seat["id"] for seat in layout_by_id[layout_id]["seats"]}
        assigned_students: set[str] = set()
        assignment: dict[str, str] = {}
        for raw_seat_id, student_id in assignment_value.items():
            if (not _valid_id(raw_seat_id) or raw_seat_id not in valid_seats
                    or not _valid_id(student_id) or student_id in assigned_students):
                continue
            assigned_students.add(student_id)
            assignment[raw_seat_id] = student_id
        modes.append({"id": mode_id, "name": value_mode["name"].strip(),
                      "section_id": section_id, "layout_id": layout_id,
                      "strategy": strategy, "assignment": assignment})
        mode_ids.add(mode_id)
    return {"layouts": layouts, "modes": modes}


def validate_state(value: object) -> tuple[dict | None, str | None]:
    """Strictly validate one complete state replacement before it is stored."""
    if not isinstance(value, dict) or set(value) != _STATE_FIELDS:
        return None, "seating state must contain exactly layouts and modes."
    layouts_value, modes_value = value.get("layouts"), value.get("modes")
    if not isinstance(layouts_value, list) or not isinstance(modes_value, list):
        return None, "seating layouts and modes must be lists."

    layouts: list[dict] = []
    layout_by_id: dict[str, dict] = {}
    for index, layout_value in enumerate(layouts_value):
        if not isinstance(layout_value, dict) or set(layout_value) != _LAYOUT_FIELDS:
            return None, f"layout {index} has an invalid shape."
        layout = _normalize_layout(layout_value)
        if layout is None:
            return None, f"layout {index} is invalid."
        if layout["id"] in layout_by_id:
            return None, f"layout {index} has a duplicate id."
        raw_seats = layout_value["seats"]
        if not isinstance(raw_seats, list) or len(raw_seats) != len(layout["seats"]):
            return None, f"layout {index} has an invalid seat."
        if len({seat["id"] for seat in layout["seats"]}) != len(layout["seats"]):
            return None, f"layout {index} has duplicate seats."
        raw_marks = layout_value["near_teacher_seat_ids"]
        if (not isinstance(raw_marks, list)
                or len(raw_marks) != len(layout["near_teacher_seat_ids"])
                or any(not isinstance(seat_id_value, str) for seat_id_value in raw_marks)):
            return None, f"layout {index} has invalid near-teacher seats."
        layouts.append(layout)
        layout_by_id[layout["id"]] = layout

    modes: list[dict] = []
    mode_ids: set[str] = set()
    for index, mode_value in enumerate(modes_value):
        if not isinstance(mode_value, dict) or set(mode_value) != _MODE_FIELDS:
            return None, f"mode {index} has an invalid shape."
        mode_id, layout_id, section_id = (
            mode_value.get("id"), mode_value.get("layout_id"), mode_value.get("section_id")
        )
        if not _valid_id(mode_id) or mode_id in mode_ids or not _valid_name(mode_value.get("name")):
            return None, f"mode {index} has an invalid id or name."
        if not _valid_id(section_id) or not _valid_id(layout_id) or layout_id not in layout_by_id:
            return None, f"mode {index} must reference a known layout and valid section."
        if mode_value.get("strategy") not in STRATEGIES:
            return None, f"mode {index} has an unsupported strategy."
        assignment_value = mode_value.get("assignment")
        if not isinstance(assignment_value, dict):
            return None, f"mode {index} assignment must be an object."
        valid_seats = {seat["id"] for seat in layout_by_id[layout_id]["seats"]}
        assignment: dict[str, str] = {}
        assigned_students: set[str] = set()
        for raw_seat_id, student_id in assignment_value.items():
            if not _valid_id(raw_seat_id) or raw_seat_id not in valid_seats:
                return None, f"mode {index} assignment has an unknown seat."
            if not _valid_id(student_id):
                return None, f"mode {index} assignment has an invalid student id."
            if student_id in assigned_students:
                return None, f"mode {index} assigns a student more than once."
            assigned_students.add(student_id)
            assignment[raw_seat_id] = student_id
        modes.append({"id": mode_id, "name": mode_value["name"].strip(),
                      "section_id": section_id, "layout_id": layout_id,
                      "strategy": mode_value["strategy"], "assignment": assignment})
        mode_ids.add(mode_id)
    return {"layouts": layouts, "modes": modes}, None


def resize_layout(state: object, layout_id: object, rows: object, columns: object) -> tuple[dict | None, str | None]:
    """Resize one layout and clear only assignments whose seats were dropped."""
    current, error = validate_state(state)
    if error:
        return None, error
    if not _valid_id(layout_id) or not _valid_grid_size(rows) or not _valid_grid_size(columns):
        return None, "layout resize requires a valid layout and grid size."
    replacement = None
    layouts: list[dict] = []
    for layout in current["layouts"]:
        if layout["id"] != layout_id:
            layouts.append(layout)
            continue
        seats = [seat for seat in layout["seats"] if seat["row"] <= rows and seat["column"] <= columns]
        valid_seat_ids = {seat["id"] for seat in seats}
        replacement = {**layout, "rows": rows, "columns": columns, "seats": seats,
                       "near_teacher_seat_ids": [
                           seat_id_value for seat_id_value in layout["near_teacher_seat_ids"]
                           if seat_id_value in valid_seat_ids
                       ]}
        layouts.append(replacement)
    if replacement is None:
        return None, "layout not found."
    valid_seats = {seat["id"] for seat in replacement["seats"]}
    modes = [
        {**mode, "assignment": {seat: student for seat, student in mode["assignment"].items()
                                  if mode["layout_id"] != layout_id or seat in valid_seats}}
        for mode in current["modes"]
    ]
    return {"layouts": layouts, "modes": modes}, None


def toggle_seat(state: object, layout_id: object, row: object, column: object) -> tuple[dict | None, str | None]:
    """Toggle a bounded grid position and clear only its dependent assignment."""
    current, error = validate_state(state)
    if error:
        return None, error
    if (not _valid_id(layout_id) or not isinstance(row, int) or isinstance(row, bool)
            or not isinstance(column, int) or isinstance(column, bool)):
        return None, "seat toggle requires a valid layout and coordinates."
    changed_layout = None
    layouts: list[dict] = []
    removed_seat_id = ""
    for layout in current["layouts"]:
        if layout["id"] != layout_id:
            layouts.append(layout)
            continue
        if not (GRID_MIN <= row <= layout["rows"] and GRID_MIN <= column <= layout["columns"]):
            return None, "seat coordinates are outside this layout."
        target_id = seat_id(row, column)
        existing = [seat for seat in layout["seats"] if seat["id"] != target_id]
        if len(existing) == len(layout["seats"]):
            existing.append({"id": target_id, "row": row, "column": column,
                             "label": seat_label(row, column)})
        else:
            removed_seat_id = target_id
        existing.sort(key=lambda seat: (seat["row"], seat["column"]))
        changed_layout = {**layout, "seats": existing,
                          "near_teacher_seat_ids": [
                              seat_id_value for seat_id_value in layout["near_teacher_seat_ids"]
                              if seat_id_value != removed_seat_id
                          ]}
        layouts.append(changed_layout)
    if changed_layout is None:
        return None, "layout not found."
    modes = [
        {**mode, "assignment": {seat: student for seat, student in mode["assignment"].items()
                                  if not (mode["layout_id"] == layout_id and seat == removed_seat_id)}}
        for mode in current["modes"]
    ]
    return {"layouts": layouts, "modes": modes}, None


def toggle_near_teacher_seat(state: object, layout_id: object, seat_id_value: object) -> tuple[dict | None, str | None]:
    """Toggle a near-teacher mark on one existing seat without changing assignments."""
    current, error = validate_state(state)
    if error:
        return None, error
    if not _valid_id(layout_id) or not _valid_id(seat_id_value):
        return None, "near-teacher toggle requires a valid layout and seat."
    changed = False
    layouts = []
    for layout in current["layouts"]:
        if layout["id"] != layout_id:
            layouts.append(layout)
            continue
        valid_seat_ids = {seat["id"] for seat in layout["seats"]}
        if seat_id_value not in valid_seat_ids:
            return None, "near-teacher seat is not in this layout."
        marks = set(layout["near_teacher_seat_ids"])
        if seat_id_value in marks:
            marks.remove(seat_id_value)
        else:
            marks.add(seat_id_value)
        layouts.append({**layout, "near_teacher_seat_ids": [
            seat["id"] for seat in layout["seats"] if seat["id"] in marks
        ]})
        changed = True
    if not changed:
        return None, "layout not found."
    return {"layouts": layouts, "modes": current["modes"]}, None


def delete_layout(state: object, layout_id: object) -> tuple[dict | None, str | None]:
    """Delete one layout and, deterministically, every mode that references it."""
    current, error = validate_state(state)
    if error:
        return None, error
    if not _valid_id(layout_id):
        return None, "layout id is invalid."
    layouts = [layout for layout in current["layouts"] if layout["id"] != layout_id]
    if len(layouts) == len(current["layouts"]):
        return None, "layout not found."
    return {"layouts": layouts,
            "modes": [mode for mode in current["modes"] if mode["layout_id"] != layout_id]}, None

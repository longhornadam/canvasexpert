"""Pure private Seating state tests using synthetic opaque identifiers only."""

from api import seating_state


def _layout(layout_id="layout-a", rows=2, columns=2, seats=None):
    if seats is None:
        seats = [
            {"id": "seat-1-1", "row": 1, "column": 1, "label": "1-1"},
            {"id": "seat-1-2", "row": 1, "column": 2, "label": "1-2"},
            {"id": "seat-2-1", "row": 2, "column": 1, "label": "2-1"},
        ]
    return {"id": layout_id, "name": "Room", "rows": rows, "columns": columns,
            "seats": seats, "near_teacher_seat_ids": []}


def _mode(mode_id="mode-a", layout_id="layout-a", assignment=None, strategy="manual", section_id="section-a"):
    return {"id": mode_id, "name": "Rows", "section_id": section_id,
            "layout_id": layout_id, "strategy": strategy, "assignment": assignment or {}}


def test_normalize_malformed_state_to_empty_valid_shape():
    assert seating_state.normalize_state(None) == seating_state.empty_state()
    assert seating_state.normalize_state({"layouts": "bad", "modes": []}) == seating_state.empty_state()
    legacy = _layout(seats=[{"id": "wrong", "row": 1, "column": 1, "label": "wrong"}])
    legacy.pop("near_teacher_seat_ids")
    assert seating_state.normalize_state({
        "layouts": [legacy],
        "modes": [],
    }) == {"layouts": [{"id": "layout-a", "name": "Room", "rows": 2, "columns": 2,
                          "seats": [], "near_teacher_seat_ids": []}], "modes": []}


def test_resize_and_toggle_drop_only_dependent_assignments():
    state = {
        "layouts": [_layout(), _layout("layout-b", seats=[
            {"id": "seat-1-1", "row": 1, "column": 1, "label": "1-1"},
        ])],
        "modes": [
            _mode(assignment={"seat-1-1": "student-a", "seat-2-1": "student-b"}),
            _mode("mode-b", "layout-b", {"seat-1-1": "student-c"}),
        ],
    }

    resized, error = seating_state.resize_layout(state, "layout-a", 1, 2)
    assert error is None
    assert resized["modes"][0]["assignment"] == {"seat-1-1": "student-a"}
    assert resized["modes"][1]["assignment"] == {"seat-1-1": "student-c"}

    toggled, error = seating_state.toggle_seat(resized, "layout-a", 1, 1)
    assert error is None
    assert toggled["modes"][0]["assignment"] == {}
    assert toggled["modes"][1]["assignment"] == {"seat-1-1": "student-c"}


def test_assignment_validation_rejects_unknown_or_duplicate_student_atomically():
    valid = {"layouts": [_layout()], "modes": [_mode(assignment={"seat-1-1": "student-a"})]}
    accepted, error = seating_state.validate_state(valid)
    assert error is None
    assert accepted == valid

    unknown = {"layouts": [_layout()], "modes": [_mode(assignment={"seat-9-9": "student-a"})]}
    duplicate = {"layouts": [_layout()], "modes": [_mode(assignment={
        "seat-1-1": "student-a", "seat-1-2": "student-a",
    })]}
    assert seating_state.validate_state(unknown)[0] is None
    assert seating_state.validate_state(duplicate)[0] is None


def test_strategy_enum_normalizes_legacy_modes_and_preserves_current_assignments():
    state = {
        "layouts": [_layout(), _layout("layout-b")],
        "modes": [
            _mode(assignment={"seat-1-1": "student-a"}, strategy="mixed_fours"),
            _mode("mode-b", "layout-b", {"seat-1-2": "student-b"}, "mentor_pairs"),
        ],
    }
    accepted, error = seating_state.validate_state(state)
    assert error is None
    assert accepted["modes"][0]["strategy"] == "mixed_fours"
    assert accepted["modes"][0]["assignment"] == {"seat-1-1": "student-a"}
    assert accepted["modes"][1]["strategy"] == "mentor_pairs"
    assert accepted["modes"][1]["assignment"] == {"seat-1-2": "student-b"}

    legacy = _mode(strategy="unsupported")
    assert seating_state.normalize_state({"layouts": [_layout()], "modes": [legacy]})["modes"][0]["strategy"] == "manual"
    assert seating_state.validate_state({"layouts": [_layout()], "modes": [legacy]})[0] is None


def test_delete_layout_removes_only_dependent_modes():
    state = {
        "layouts": [_layout(), _layout("layout-b", seats=[
            {"id": "seat-1-1", "row": 1, "column": 1, "label": "1-1"},
        ])],
        "modes": [_mode(), _mode("mode-b", "layout-b")],
    }
    result, error = seating_state.delete_layout(state, "layout-a")
    assert error is None
    assert [layout["id"] for layout in result["layouts"]] == ["layout-b"]
    assert [mode["id"] for mode in result["modes"]] == ["mode-b"]


def test_clear_student_from_section_only_touches_that_section_and_student():
    state = {
        "layouts": [_layout(), _layout("layout-b", seats=[
            {"id": "seat-1-1", "row": 1, "column": 1, "label": "1-1"},
        ])],
        "modes": [
            _mode(assignment={"seat-1-1": "student-a", "seat-2-1": "student-b"}, section_id="section-old"),
            _mode("mode-b", "layout-b", {"seat-1-1": "student-a"}, section_id="section-new"),
        ],
    }
    cleared, error = seating_state.clear_student_from_section(state, "section-old", "student-a")
    assert error is None
    # Only student-a's seat in section-old is cleared; student-b keeps their
    # seat, and student-a's seat in the unrelated section-new mode is untouched.
    assert cleared["modes"][0]["assignment"] == {"seat-2-1": "student-b"}
    assert cleared["modes"][1]["assignment"] == {"seat-1-1": "student-a"}

    noop, error = seating_state.clear_student_from_section(cleared, "section-old", "student-a")
    assert error is None
    assert noop == cleared

    rejected, error = seating_state.clear_student_from_section(state, "bad section", "student-a")
    assert rejected is None
    assert "valid section and student id" in error


def test_near_teacher_marks_are_a_unique_current_seat_subset():
    state = {
        "layouts": [_layout(), _layout("layout-b")],
        "modes": [_mode(assignment={"seat-1-1": "student-a"}), _mode("mode-b", "layout-b")],
    }
    marked, error = seating_state.toggle_near_teacher_seat(state, "layout-a", "seat-1-1")
    assert error is None
    assert marked["layouts"][0]["near_teacher_seat_ids"] == ["seat-1-1"]
    assert marked["layouts"][1]["near_teacher_seat_ids"] == []
    assert marked["modes"][0]["assignment"] == {"seat-1-1": "student-a"}

    rejected, error = seating_state.toggle_near_teacher_seat(marked, "layout-a", "seat-9-9")
    assert rejected is None
    assert error == "near-teacher seat is not in this layout."

    removed, error = seating_state.toggle_seat(marked, "layout-a", 1, 1)
    assert error is None
    assert removed["layouts"][0]["near_teacher_seat_ids"] == []
    assert removed["modes"][0]["assignment"] == {}

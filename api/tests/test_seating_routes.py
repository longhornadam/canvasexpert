"""Local-only Seating route tests; no roster or Canvas data is used here."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.webui.server import app
from api.webui.routes import seating as seating_routes


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_seating(monkeypatch):
    records = {}
    monkeypatch.setattr(seating_routes.config, "get_seating_course_state",
                        lambda course_id: records.get(str(course_id), {}))
    monkeypatch.setattr(seating_routes.config, "set_seating_course_state",
                        lambda course_id, state: records.__setitem__(str(course_id), state))
    return records


def _state(assignment=None):
    return {
        "layouts": [{
            "id": "layout-a", "name": "Room", "rows": 2, "columns": 2,
            "seats": [{"id": "seat-1-1", "row": 1, "column": 1, "label": "1-1"}],
            "near_teacher_seat_ids": [],
        }],
        "modes": [{
            "id": "mode-a", "name": "Rows", "section_id": "section-a",
            "layout_id": "layout-a", "strategy": "manual", "assignment": assignment or {},
        }],
    }


def _context(required=False):
    return {
        "section_id": "section-a",
        "students": [{
            "id": "student-a", "front_row": "required" if required else "none",
            "near_teacher": "none",
        }],
        "relationships": [],
    }


def test_seating_get_is_course_scoped_and_normalizes_stored_state(isolated_seating):
    isolated_seating["course-a"] = {"bad": "state"}
    first = client.get("/api/seating?course_id=course-a").json()
    second = client.get("/api/seating?course_id=course-b").json()

    assert first == {"ok": True, "state": {"layouts": [], "modes": []}}
    assert second == {"ok": True, "state": {"layouts": [], "modes": []}}


def test_seating_state_post_round_trips_valid_manual_assignment(isolated_seating):
    state = _state({"seat-1-1": "student-a"})
    saved = client.post("/api/seating/state", data={
        "course_id": "course-a", "state": json.dumps(state),
    }).json()

    assert saved == {"ok": True, "state": state}
    assert isolated_seating["course-a"] == state
    assert client.get("/api/seating?course_id=course-a").json()["state"] == state


@pytest.mark.parametrize("state", [
    _state({"seat-9-9": "student-a"}),
    _state({"seat-1-1": "student-a", "seat-1-2": "student-a"}),
    {"layouts": [], "modes": [{"bad": "shape"}]},
])
def test_seating_state_post_rejects_invalid_data_atomically(isolated_seating, state):
    previous = _state({"seat-1-1": "student-b"})
    isolated_seating["course-a"] = previous

    response = client.post("/api/seating/state", data={
        "course_id": "course-a", "state": json.dumps(state),
    }).json()

    assert response["ok"] is False
    assert isolated_seating["course-a"] == previous


def test_print_builder_has_only_chart_title_seat_labels_and_display_names():
    source = Path("api/webui/static/seating.js").read_text(encoding="utf-8")
    print_function = source[source.index("function renderPrintChart"):source.index("function seatingContext")]
    assert "mode.name" in print_function
    assert "seat.label" in print_function
    assert "namesById" in print_function
    for excluded in ("pseudonym", "canvas_id", "sis", "private_note", "score", "relationship", "support", "assignment-controls"):
        assert excluded not in print_function


def test_frontend_ignores_stale_course_switch_responses_before_state_changes():
    source = Path("api/webui/static/seating.js").read_text(encoding="utf-8")
    post_function = source[source.index("function postState"):source.index("function option")]
    load_function = source[source.index("function loadCourse"):source.index('document.getElementById("seating-create-layout")')]

    assert "var initiatingCourseId = currentCourseId;" in post_function
    assert post_function.count("if (initiatingCourseId !== currentCourseId) return;") == 2
    assert post_function.index("if (initiatingCourseId !== currentCourseId) return;") < post_function.index("state = data.state")
    assert "if (currentCourseId !== courseId) return null;" in load_function
    assert load_function.index("if (currentCourseId !== courseId) return null;") < load_function.index("students = roster.students")
    assert "if (!data || currentCourseId !== courseId) return;" in load_function
    assert load_function.index("if (!data || currentCourseId !== courseId) return;") < load_function.index("state = data.state")


def test_near_teacher_editor_only_renders_existing_current_layout_seats():
    source = Path("api/webui/static/seating.js").read_text(encoding="utf-8")
    editor = source[source.index("function renderLayoutEditor"):source.index("function fillSections")]
    toggle = source[source.index("function toggleNearTeacherSeat"):source.index("function loadCourse")]
    update = source[source.index("function updateLayout"):source.index("function toggleSeat")]

    assert "layout.seats.forEach(function (seat)" in editor
    assert "toggleNearTeacherSeat(seatIdValue)" in editor
    assert "layout.seats.some(function (seat) { return seat.id === targetSeatId; })" in toggle
    assert "near_teacher_seat_ids" in toggle
    assert "updateLayout(Object.assign({}, layout" in toggle
    assert "if (selectedMode() && selectedMode().layout_id === nextLayout.id) clearTransient();" in update
    for excluded in ("students", "displayName", "fetch(", "relationship", "support"):
        assert excluded not in editor + toggle


def test_proposal_and_apply_stay_local_and_apply_only_the_selected_mode(isolated_seating):
    state = _state()
    state["modes"].append({
        "id": "mode-b", "name": "Other", "section_id": "section-a",
        "layout_id": "layout-a", "strategy": "manual", "assignment": {},
    })
    isolated_seating["course-a"] = state
    context = _context()
    proposal = client.post("/api/seating/proposal", data={
        "course_id": "course-a", "mode_id": "mode-a", "operation": "generate",
        "context": json.dumps(context), "locks": "{}", "proposal": "{}", "reroll_seat_ids": "[]",
    }).json()

    assert proposal["ok"] is True
    applied = client.post("/api/seating/apply", data={
        "course_id": "course-a", "mode_id": "mode-a", "context": json.dumps(context),
        "proposal": json.dumps(proposal["proposal"]),
    }).json()

    assert applied["ok"] is True
    assert applied["state"]["modes"][0]["assignment"] == proposal["proposal"]
    assert applied["state"]["modes"][1]["assignment"] == {}


def test_apply_rejects_required_violation_or_foreign_student_atomically(isolated_seating):
    previous = _state()
    isolated_seating["course-a"] = previous
    required = client.post("/api/seating/apply", data={
        "course_id": "course-a", "mode_id": "mode-a", "context": json.dumps(_context(required=True)),
        "proposal": "{}",
    }).json()
    foreign = client.post("/api/seating/apply", data={
        "course_id": "course-a", "mode_id": "mode-a", "context": json.dumps(_context()),
        "proposal": json.dumps({"seat-1-1": "student-z"}),
    }).json()

    assert required["ok"] is False
    assert "results" in required
    assert foreign["ok"] is False
    assert isolated_seating["course-a"] == previous

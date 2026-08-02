from __future__ import annotations

from datetime import datetime

import pytest

from api.webui.routes.panels import resolve_panel_course


@pytest.fixture
def _catalog():
    def catalog(records, *, state="current"):
        return lambda _course_id: {
            "catalog": {
                "course_id": "123",
                "course_name": "ELA 7",
                "version": 1,
                "assignments": {
                    "state": state,
                    "last_success_at": "2026-08-17T08:00:00+00:00",
                    "records": records,
                },
            }
        }

    return catalog


@pytest.fixture
def _assignment():
    def assignment(name, due, *, published=True, points=10):
        return {"id": name, "name": name, "due_at": due,
                "published": published, "points_possible": points}

    return assignment


@pytest.fixture
def _schedule():
    def schedule(blocks, problems=(), state="ready"):
        return lambda _date: {"state": state, "blocks": list(blocks), "problems": list(problems)}

    return schedule


@pytest.fixture
def _teacher():
    def teacher(blocks):
        return lambda: ({"blocks": list(blocks)}, [])

    return teacher


@pytest.fixture
def _active():
    def active(*course_ids):
        return lambda: [{"id": cid} for cid in course_ids]

    return active


@pytest.fixture
def _at():
    return lambda hour, minute: datetime(2026, 8, 17, hour, minute)


@pytest.fixture
def _resolve(request, _schedule, _teacher, _active):
    def resolve(
        block="",
        *,
        now,
        schedule_reader=None,
        teacher_blocks=None,
        active_course_ids=("111", "333"),
        calendar_state="ready",
    ):
        module = request.module
        teacher_blocks = module.DAY if teacher_blocks is None else teacher_blocks
        return resolve_panel_course(
            block,
            now=now,
            schedule_reader=schedule_reader or _schedule(module.DAY),
            teacher_schedule_reader=_teacher(teacher_blocks),
            active_courses_reader=_active(*active_course_ids),
            calendar_state=calendar_state,
        )

    return resolve

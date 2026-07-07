from __future__ import annotations

import json

from api.webui import push_service
from api.webui.routes import push as push_routes


def test_push_assignment_returns_assignment_id(monkeypatch):
    calls = []

    def fake_canvas_send(method, path, payload, timeout=30):
        calls.append((method, path, payload))
        return {
            "id": 12345,
            "name": payload["assignment"]["name"],
            "html_url": "https://canvas.invalid/courses/42/assignments/12345",
        }, None

    monkeypatch.setattr(push_service, "_canvas_send", fake_canvas_send)

    result = push_service._push_assignment("42", {"name": "Essay 1", "submission_types": ["online_text_entry"]}, [])

    assert result.ok is True
    assert result.assignment_id == "12345"
    assert calls[0][1] == "/api/v1/courses/42/assignments"


def test_push_quick_returns_assignment_id(monkeypatch):
    def fake_canvas_send(method, path, payload, timeout=30):
        return {
            "id": 24680,
            "name": payload["assignment"]["name"],
            "html_url": "https://canvas.invalid/courses/42/assignments/24680",
        }, None

    monkeypatch.setattr(push_service, "_canvas_send", fake_canvas_send)

    result = push_service._push_quick("42", {"name": "Exit Ticket", "submission_type": "online_text_entry"}, [])

    assert result.ok is True
    assert result.assignment_id == "24680"


def test_content_pushers_cover_frontend_kinds():
    assert {"af", "pf", "rf", "quick", "printable"}.issubset(
        push_service._CONTENT_PUSHERS
    )


def test_pageforge_content_push_uses_pf_pusher_and_returns_page_url(monkeypatch, tmp_path):
    page_path = tmp_path / "handout.pageforge.json"
    page_path.write_text(
        """
<PAGEFORGE_JSON>
{"version":"1.0-json","type":"PAGE","title":"Handout","body":"<p>Read this.</p>"}
</PAGEFORGE_JSON>
""".strip(),
        encoding="utf-8",
    )
    calls = []

    monkeypatch.setattr(push_service, "_find_or_create_module_id", lambda cid, name, notes: None)

    def fake_canvas_send(method, path, payload, timeout=30):
        calls.append((method, path, payload))
        return {
            "title": payload["wiki_page"]["title"],
            "url": "handout",
            "html_url": "https://canvas.invalid/courses/42/pages/handout",
        }, None

    monkeypatch.setattr(push_service, "_canvas_send", fake_canvas_send)

    response = push_routes.api_content_push(
        kind="pf",
        courses=json.dumps([{ "id": "42", "name": "Period 1" }]),
        payload=json.dumps({
            "path": str(page_path),
            "published": True,
            "module_name": "Unit 1",
        }),
    )
    data = json.loads(response.body)

    assert data["ok"] is True
    assert data["results"][0]["title"] == "Handout"
    assert calls[0][1] == "/api/v1/courses/42/pages"
    assert calls[0][2]["wiki_page"] == {
        "title": "Handout",
        "body": "<p>Read this.</p>",
        "published": True,
    }


def test_pageforge_content_push_fails_closed_on_placeholder(monkeypatch, tmp_path):
    page_path = tmp_path / "placeholder.pageforge.json"
    page_path.write_text(
        """
<PAGEFORGE_JSON>
{"version":"1.0-json","type":"PAGE","title":"Handout","body":"<p>{{file:Handout.pdf}}</p>"}
</PAGEFORGE_JSON>
""".strip(),
        encoding="utf-8",
    )
    calls = []

    def fake_canvas_send(method, path, payload, timeout=30):
        calls.append((method, path, payload))
        return {}, None

    monkeypatch.setattr(push_service, "_canvas_send", fake_canvas_send)

    response = push_routes.api_content_push(
        kind="pf",
        courses=json.dumps([{ "id": "42", "name": "Period 1" }]),
        payload=json.dumps({
            "path": str(page_path),
            "published": True,
            "module_name": "Unit 1",
        }),
    )
    data = json.loads(response.body)

    assert data["ok"] is False
    assert "placeholders" in data["results"][0]["error"].lower()
    assert calls == []


def test_rubricforge_content_push_fails_closed_until_wired(monkeypatch):
    fake_rubric = {
        "version": "1.0-json",
        "type": "RUBRIC",
        "title": "Classroom Rubric",
        "student_page": {"title": "Classroom Rubric Guide"},
        "criteria": [],
        "total_points": 0,
    }
    calls = []

    monkeypatch.setattr(push_service.rf, "parse_file", lambda path: (fake_rubric, []))

    def fake_canvas_send(method, path, payload, timeout=30):
        calls.append((method, path, payload))
        return {}, None

    monkeypatch.setattr(push_service, "_canvas_send", fake_canvas_send)

    response = push_routes.api_content_push(
        kind="rf",
        courses=json.dumps([{ "id": "42", "name": "Period 1" }]),
        payload=json.dumps({"path": "fake.rubricforge.json"}),
    )
    data = json.loads(response.body)

    assert data["ok"] is False
    assert data["results"][0]["title"] == "Classroom Rubric"
    assert "not wired" in data["results"][0]["error"]
    assert calls == []


def test_assignmentforge_content_push_uses_af_pusher_and_returns_assignment_id(monkeypatch):
    fake_assignment = {
        "version": "1.0-json",
        "type": "ASSIGNMENT",
        "title": "Essay 1",
        "description": "<p>Prompt</p>",
        "points": 10,
        "submission": {"types": ["online_text_entry"]},
    }

    monkeypatch.setattr(push_service.af, "parse_file", lambda path: (fake_assignment, []))
    monkeypatch.setattr(push_service.af, "tier_payloads", lambda data: [{"title": data["title"], "description": data["description"], "group": None}])
    monkeypatch.setattr(push_service.af, "submission_fields", lambda data: {"submission_types": ["online_text_entry"]})

    def fake_canvas_send(method, path, payload, timeout=30):
        return {
            "id": 67890,
            "name": payload["assignment"]["name"],
            "html_url": "https://canvas.invalid/courses/42/assignments/67890",
        }, None

    monkeypatch.setattr(push_service, "_canvas_send", fake_canvas_send)

    response = push_routes.api_content_push(
        kind="af",
        courses=json.dumps([{ "id": "42", "name": "Period 1" }]),
        payload=json.dumps({"path": "fake.assignmentforge.json"}),
    )
    data = json.loads(response.body)

    assert data["ok"] is True
    assert data["results"][0]["assignment_id"] == "67890"
    assert data["results"][0]["title"] == "Essay 1"


def test_assignmentforge_content_push_can_schedule_autoscore_job(monkeypatch):
    fake_assignment = {
        "version": "1.0-json",
        "type": "ASSIGNMENT",
        "title": "Essay 1",
        "description": "<p>Prompt</p>",
        "points": 10,
        "submission": {"types": ["online_text_entry"]},
    }
    calls = []

    monkeypatch.setattr(push_service.config, "has_openrouter_key", lambda: True)
    monkeypatch.setattr(push_service.af, "parse_file", lambda path: (fake_assignment, []))
    monkeypatch.setattr(push_service.af, "tier_payloads", lambda data: [{"title": data["title"], "description": data["description"], "group": None}])
    monkeypatch.setattr(push_service.af, "submission_fields", lambda data: {"submission_types": ["online_text_entry"]})

    def fake_canvas_send(method, path, payload, timeout=30):
        return {
            "id": 67890,
            "name": payload["assignment"]["name"],
            "html_url": "https://canvas.invalid/courses/42/assignments/67890",
        }, None

    def fake_upsert_job(**kwargs):
        calls.append(kwargs)
        return {
            "job_id": "42_67890",
            "course_id": kwargs["course_id"],
            "course_name": kwargs["course_name"],
            "assignment_id": kwargs["assignment_id"],
            "assignment_name": kwargs["assignment_name"],
            "status": "scheduled",
            "reason": "text entry gives PowerGrader readable response text",
            "scheduled_at": "2026-09-11T05:59:00-05:00",
        }

    monkeypatch.setattr(push_service, "_canvas_send", fake_canvas_send)
    monkeypatch.setattr(push_service.autoscore_queue, "upsert_job", fake_upsert_job)

    response = push_routes.api_content_push(
        kind="af",
        courses=json.dumps([{ "id": "42", "name": "Period 1" }]),
        payload=json.dumps({
            "path": "fake.assignmentforge.json",
            "due_at": "2026-09-10T23:59:00-05:00",
            "autoscore_schedule": True,
        }),
    )
    data = json.loads(response.body)

    assert data["ok"] is True
    assert data["results"][0]["assignment_id"] == "67890"
    assert any("scheduled PowerGrader Auto-Score" in note for note in data["results"][0]["notes"])
    assert calls[0]["course_name"] == "Period 1"
    assert calls[0]["assignment"]["submission_types"] == ["online_text_entry"]
    assert calls[0]["settings"]["watch_late"] is True
    assert calls[0]["auto_push"] is False
    assert calls[0]["push_policy"]["enabled"] is False


def test_assignmentforge_content_push_can_enable_autopush_job(monkeypatch):
    fake_assignment = {
        "version": "1.0-json",
        "type": "ASSIGNMENT",
        "title": "Essay 1",
        "description": "<p>Prompt</p>",
        "points": 10,
        "submission": {"types": ["online_text_entry"]},
    }
    calls = []

    monkeypatch.setattr(push_service.config, "has_openrouter_key", lambda: True)
    monkeypatch.setattr(push_service.af, "parse_file", lambda path: (fake_assignment, []))
    monkeypatch.setattr(push_service.af, "tier_payloads", lambda data: [{"title": data["title"], "description": data["description"], "group": None}])
    monkeypatch.setattr(push_service.af, "submission_fields", lambda data: {"submission_types": ["online_text_entry"]})

    def fake_canvas_send(method, path, payload, timeout=30):
        return {
            "id": 67890,
            "name": payload["assignment"]["name"],
            "html_url": "https://canvas.invalid/courses/42/assignments/67890",
        }, None

    def fake_upsert_job(**kwargs):
        calls.append(kwargs)
        return {
            "job_id": "42_67890",
            "course_id": kwargs["course_id"],
            "course_name": kwargs["course_name"],
            "assignment_id": kwargs["assignment_id"],
            "assignment_name": kwargs["assignment_name"],
            "status": "scheduled",
            "reason": "text entry gives PowerGrader readable response text",
            "scheduled_at": "2026-09-11T05:59:00-05:00",
            "auto_push": kwargs["auto_push"],
            "push_policy": kwargs["push_policy"],
        }

    monkeypatch.setattr(push_service, "_canvas_send", fake_canvas_send)
    monkeypatch.setattr(push_service.autoscore_queue, "upsert_job", fake_upsert_job)

    response = push_routes.api_content_push(
        kind="af",
        courses=json.dumps([{ "id": "42", "name": "Period 1" }]),
        payload=json.dumps({
            "path": "fake.assignmentforge.json",
            "due_at": "2026-09-10T23:59:00-05:00",
            "autoscore_schedule": True,
            "autoscore_auto_push": True,
        }),
    )
    data = json.loads(response.body)

    assert data["ok"] is True
    assert calls[0]["auto_push"] is True
    assert calls[0]["push_policy"]["enabled"] is True
    assert calls[0]["push_policy"]["allow_grade_push"] is True
    assert calls[0]["push_policy"]["allow_comment_push"] is True


def test_assignmentforge_schedule_is_skipped_without_due_date(monkeypatch):
    fake_assignment = {
        "version": "1.0-json",
        "type": "ASSIGNMENT",
        "title": "Essay 1",
        "description": "<p>Prompt</p>",
        "points": 10,
        "submission": {"types": ["online_text_entry"]},
    }
    calls = []

    monkeypatch.setattr(push_service.config, "has_openrouter_key", lambda: True)
    monkeypatch.setattr(push_service.af, "parse_file", lambda path: (fake_assignment, []))
    monkeypatch.setattr(push_service.af, "tier_payloads", lambda data: [{"title": data["title"], "description": data["description"], "group": None}])
    monkeypatch.setattr(push_service.af, "submission_fields", lambda data: {"submission_types": ["online_text_entry"]})

    def fake_canvas_send(method, path, payload, timeout=30):
        return {
            "id": 67890,
            "name": payload["assignment"]["name"],
            "html_url": "https://canvas.invalid/courses/42/assignments/67890",
        }, None

    def fake_upsert_job(**kwargs):
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(push_service, "_canvas_send", fake_canvas_send)
    monkeypatch.setattr(push_service.autoscore_queue, "upsert_job", fake_upsert_job)

    response = push_routes.api_content_push(
        kind="af",
        courses=json.dumps([{ "id": "42", "name": "Period 1" }]),
        payload=json.dumps({
            "path": "fake.assignmentforge.json",
            "autoscore_schedule": True,
        }),
    )
    data = json.loads(response.body)

    assert data["ok"] is True
    assert calls == []
    assert any("no due date" in note.lower() for note in data["results"][0]["notes"])


def test_assignmentforge_tiers_fail_closed_until_override_wiring_exists(monkeypatch):
    fake_assignment = {
        "version": "1.0-json",
        "type": "ASSIGNMENT",
        "title": "Tiered Essay",
        "description": "<p>Prompt</p>",
        "submission": {"types": ["online_text_entry"]},
        "tiers": [{"label": "Support", "group": "Blue"}],
    }

    monkeypatch.setattr(push_service.af, "parse_file", lambda path: (fake_assignment, []))

    result = push_service._push_assignmentforge("42", {"path": "fake.assignmentforge.json"}, [])

    assert result.ok is False
    assert "group override" in result.error


def test_assignmentforge_rubric_path_fails_closed_until_wired(monkeypatch):
    fake_assignment = {
        "version": "1.0-json",
        "type": "ASSIGNMENT",
        "title": "Essay 1",
        "description": "<p>Prompt</p>",
        "submission": {"types": ["online_text_entry"]},
    }

    monkeypatch.setattr(push_service.af, "parse_file", lambda path: (fake_assignment, []))

    result = push_service._push_assignmentforge(
        "42",
        {"path": "fake.assignmentforge.json", "rubric_path": "rubric.txt"},
        [],
    )

    assert result.ok is False
    assert "rubric attachment" in result.error

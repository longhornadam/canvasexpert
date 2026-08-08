"""Boundary contracts for PowerGrader's local media routes."""
from __future__ import annotations

import json

from api.webui.routes import powergrader


def test_read_aloud_requires_submitted_media_before_passage_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(powergrader.workspace, "workspace_root", lambda: str(tmp_path))
    monkeypatch.setattr(powergrader.assignment_refresh, "refresh_assignment", lambda *args, **kwargs: (
        [{"user_id": "synthetic", "submission_type": "online_text_entry", "workflow_state": "submitted"}],
        {"name": "Synthetic"}, {"status": "current"}))
    response = powergrader.pg_start(
        course_id="course", assignment_id="assignment", mode="fast", watch_late="true", auto_post="false",
        rubric_name="", persona_id="sage", feedback_pattern_id="", model_id="", response_kind="scr",
        source_text="", source_files_json="", source_uploads=None, oral_reading_passage="", oral_reading_enabled="true",
    )
    assert json.loads(response.body)["code"] == "oral_reading_media_required"


def test_read_aloud_requires_a_valid_passage_after_media_is_found(tmp_path, monkeypatch):
    monkeypatch.setattr(powergrader.workspace, "workspace_root", lambda: str(tmp_path))
    monkeypatch.setattr(powergrader.assignment_refresh, "refresh_assignment", lambda *args, **kwargs: (
        [{"user_id": "synthetic", "submission_type": "media_recording", "workflow_state": "submitted", "attachments": []}],
        {"name": "Synthetic"}, {"status": "current"}))
    response = powergrader.pg_start(
        course_id="course", assignment_id="assignment", mode="fast", watch_late="true", auto_post="false",
        rubric_name="", persona_id="sage", feedback_pattern_id="", model_id="", response_kind="scr",
        source_text="", source_files_json="", source_uploads=None, oral_reading_passage="not 123", oral_reading_enabled="true",
    )
    body = json.loads(response.body)
    assert body["code"] == "oral_reading_passage_required" and "English words" in body["error"]


def test_media_start_defaults_to_local_review_without_oral_analysis(tmp_path, monkeypatch):
    attachment = {"media_recording": True, "canonical_path": "synthetic.wav", "canonical_sha256": "hash"}
    submission = {"user_id": "synthetic-user", "user": {"name": "Synthetic User"}, "submission_type": "media_recording",
                  "workflow_state": "submitted", "attachments": [attachment]}
    captured = {}
    monkeypatch.setattr(powergrader.workspace, "workspace_root", lambda: str(tmp_path))
    monkeypatch.setattr(powergrader.assignment_refresh, "refresh_assignment", lambda *args, **kwargs: (
        [submission], {"name": "Synthetic", "points_possible": 10}, {"status": "current"}))
    monkeypatch.setattr(powergrader.ai_workflow, "run_ai_workflow", lambda **kwargs: {
        "ok": True, "privacy_steps": [], "privacy_artifacts": {}, "ai_by_uid": {}, "ai_item_by_uid": {}, "ai_failures": {}, "source_context": {}})
    monkeypatch.setattr(powergrader.config, "course_display_name", lambda _course: "Synthetic")
    monkeypatch.setattr(powergrader.config, "get_openrouter_model", lambda: "synthetic/model")
    monkeypatch.setattr(powergrader.config, "has_openrouter_key", lambda: False)
    monkeypatch.setattr(powergrader.config, "get_roster_student_settings", lambda _course: {})
    monkeypatch.setattr(powergrader.config, "roster_tier_by_id", lambda _course: {})
    monkeypatch.setattr(powergrader.config, "get_monitored_students", lambda: {})
    monkeypatch.setattr(powergrader.config, "get_extra_time", lambda _course: [])
    monkeypatch.setattr(powergrader.session_builder, "build_students", lambda **kwargs: [])
    monkeypatch.setattr(powergrader.start_workflow, "append_privacy_audit_step", lambda **kwargs: ({}, []))
    monkeypatch.setattr(powergrader.start_workflow, "build_start_session", lambda **kwargs: captured.update(kwargs) or {"students": []})
    monkeypatch.setattr(powergrader, "_save_session", lambda _session: None)
    monkeypatch.setattr(powergrader.oral_reading, "model_status", lambda: (_ for _ in ()).throw(AssertionError("status")))
    monkeypatch.setattr(powergrader.oral_reading, "construct_transcriber", lambda: (_ for _ in ()).throw(AssertionError("construction")))

    response = powergrader.pg_start(
        course_id="course", assignment_id="assignment", mode="fast", watch_late="true", auto_post="false",
        rubric_name="", persona_id="sage", feedback_pattern_id="", model_id="", response_kind="scr",
        source_text="", source_files_json="", source_uploads=None, oral_reading_passage="", oral_reading_enabled="false",
    )

    assert json.loads(response.body)["ok"] is True
    assert captured["oral_reading_passage"] == {"enabled": False}
    assert "oral_reading" not in attachment


def test_read_aloud_constructs_once_and_shares_transcriber(tmp_path, monkeypatch):
    attachments = [{"media_recording": True, "canonical_path": "x", "canonical_sha256": "h", "duration_seconds": 1} for _ in range(3)]
    submission = {"user_id": "synthetic", "user": {"name": "Synthetic"}, "submission_type": "media_recording", "workflow_state": "submitted", "attachments": attachments}
    captured, calls = {}, []
    monkeypatch.setattr(powergrader.workspace, "workspace_root", lambda: str(tmp_path))
    monkeypatch.setattr(powergrader.assignment_refresh, "refresh_assignment", lambda *a, **k: ([submission], {"name":"Synthetic", "points_possible":1}, {"status":"current"}))
    monkeypatch.setattr(powergrader.oral_reading, "construct_transcriber", lambda: calls.append("construct") or (lambda _path: ("en", [], "synthetic")))
    monkeypatch.setattr(powergrader.oral_reading, "analyze_recording", lambda record, passage, *, transcribe: calls.append(transcribe) or {"status":"complete"})
    monkeypatch.setattr(powergrader.ai_workflow, "run_ai_workflow", lambda **k: {"ok":True,"privacy_steps":[],"privacy_artifacts":{},"ai_by_uid":{},"ai_item_by_uid":{},"ai_failures":{},"source_context":{}})
    for name, value in [("course_display_name", lambda _: "Synthetic"), ("get_openrouter_model", lambda: "synthetic"), ("has_openrouter_key", lambda: False), ("get_roster_student_settings", lambda _: {}), ("roster_tier_by_id", lambda _: {}), ("get_monitored_students", lambda: {}), ("get_extra_time", lambda _: [])]: monkeypatch.setattr(powergrader.config, name, value)
    monkeypatch.setattr(powergrader.session_builder, "build_students", lambda **k: [])
    monkeypatch.setattr(powergrader.start_workflow, "append_privacy_audit_step", lambda **k: ({}, []))
    monkeypatch.setattr(powergrader.start_workflow, "build_start_session", lambda **k: captured.update(k) or {"students":[]})
    monkeypatch.setattr(powergrader, "_save_session", lambda _: None)
    response = powergrader.pg_start(course_id="c", assignment_id="a", mode="fast", watch_late="true", auto_post="false", rubric_name="", persona_id="sage", feedback_pattern_id="", model_id="", response_kind="scr", source_text="", source_files_json="", source_uploads=None, oral_reading_passage="one two", oral_reading_enabled="true")
    assert json.loads(response.body)["ok"] and calls.count("construct") == 1 and len(calls) == 4 and calls[1] is calls[2] is calls[3]
    assert captured["oral_reading_passage"]["enabled"] is True and captured["oral_reading_passage"]["passage"] == "one two"


def test_read_aloud_construction_failure_is_once_and_isolated(tmp_path, monkeypatch):
    attachments = [{"media_recording": True, "canonical_path": "x", "canonical_sha256": "h", "duration_seconds": 1} for _ in range(3)]
    submission = {"user_id":"synthetic", "user":{"name":"Synthetic"}, "submission_type":"media_recording", "workflow_state":"submitted", "attachments":attachments}
    captured, calls = {}, []
    monkeypatch.setattr(powergrader.workspace, "workspace_root", lambda: str(tmp_path))
    monkeypatch.setattr(powergrader.assignment_refresh, "refresh_assignment", lambda *a, **k: ([submission], {"name":"Synthetic", "points_possible":1}, {"status":"current"}))
    monkeypatch.setattr(powergrader.oral_reading, "construct_transcriber", lambda: calls.append("construct") or (_ for _ in ()).throw(powergrader.oral_reading.LocalTranscriberUnavailable("model_missing", "Local speech model is not installed.")))
    monkeypatch.setattr(powergrader.oral_reading, "analyze_recording", lambda *a, **k: (_ for _ in ()).throw(AssertionError("analyze")))
    monkeypatch.setattr(powergrader.oral_reading, "install_model", lambda: (_ for _ in ()).throw(AssertionError("install")))
    monkeypatch.setattr(powergrader.ai_workflow, "run_ai_workflow", lambda **k: {"ok":True,"privacy_steps":[],"privacy_artifacts":{},"ai_by_uid":{},"ai_item_by_uid":{},"ai_failures":{},"source_context":{}})
    for name, value in [("course_display_name", lambda _: "Synthetic"), ("get_openrouter_model", lambda: "synthetic"), ("has_openrouter_key", lambda: False), ("get_roster_student_settings", lambda _: {}), ("roster_tier_by_id", lambda _: {}), ("get_monitored_students", lambda: {}), ("get_extra_time", lambda _: [])]: monkeypatch.setattr(powergrader.config, name, value)
    monkeypatch.setattr(powergrader.session_builder, "build_students", lambda **k: [])
    monkeypatch.setattr(powergrader.start_workflow, "append_privacy_audit_step", lambda **k: ({}, []))
    monkeypatch.setattr(powergrader.start_workflow, "build_start_session", lambda **k: captured.update(k) or {"students":[]})
    monkeypatch.setattr(powergrader, "_save_session", lambda _: None)
    response = powergrader.pg_start(course_id="c", assignment_id="a", mode="fast", watch_late="true", auto_post="false", rubric_name="", persona_id="sage", feedback_pattern_id="", model_id="", response_kind="scr", source_text="", source_files_json="", source_uploads=None, oral_reading_passage="one two", oral_reading_enabled="true")
    assert json.loads(response.body)["ok"] and calls == ["construct"]
    assert all(item["oral_reading"] == {"status":"unavailable", "error_code":"model_missing", "error_message":"Local speech model is not installed."} for item in attachments)
    assert captured["oral_reading_passage"]["enabled"] is True and captured["oral_reading_passage"]["digest"]

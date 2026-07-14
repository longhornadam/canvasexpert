"""Synthetic New Quiz report coverage; fixture data intentionally contains no PII."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.powergrader import new_quiz_fetch as nq
from api.feedback_artifacts import pseudonymize_submissions
from api.feedback_vault import Vault
from api.powergrader import session_actions
from api.webui.routes.powergrader_helpers import build_late_watch_state


class _Response:
    def __init__(self, status, payload=None, bad_json=False):
        self.status_code, self.payload, self.bad_json = status, payload, bad_json
    def json(self):
        if self.bad_json:
            raise ValueError("synthetic malformed json")
        return self.payload


class _Session:
    def __init__(self, *, posts=(), gets=()):
        self.posts, self.gets = list(posts), list(gets)
        self.post_calls, self.get_calls = 0, 0
    def post(self, *args, **kwargs):
        self.post_calls += 1
        return self.posts.pop(0)
    def get(self, *args, **kwargs):
        self.get_calls += 1
        return self.gets.pop(0)


def test_normalize_uses_nested_entry_id_and_latest_attempt_safe_text(tmp_path):
    core = [{"user_id": "fake-01", "submitted_at": "2026-01-02T00:00:00Z", "score": 4,
             "late": True, "seconds_late": 60, "user": {"name": "Fictional Student"}}]
    rows = [
        {"attempt": 1, "submitted_at": "2026-01-01T00:00:00Z", "student_data": {"id": "fake-01"}, "item_responses": [{"item_id": "nested-essay", "answer": "<p>old</p>"}]},
        {"attempt": 2, "submitted_at": "2026-01-02T00:00:00Z", "student_data": {"id": "fake-01"}, "item_responses": [{"item_id": "nested-essay", "answer": "<p>latest answer</p>"}, {"item_id": "nested-file", "files": [{"filename": "fictional.pdf", "url": "never-fetch"}]}]},
    ]
    items = [{"id": "outer-wrong", "entry": [{"id": "nested-essay", "item_type": "essay", "item_body": "<p>Explain.</p>", "points_possible": 5}, {"id": "nested-file", "item_type": "file_upload", "item_body": "Upload.", "points_possible": 1}]}]
    subs = nq.normalize(core, rows, items)
    assert subs[0]["new_quiz_attempt"] == 2
    assert "latest answer" in subs[0]["new_quiz_items"][0]["raw_html_answer"]
    assert subs[0]["new_quiz_items"][1]["files"] == [{"filename": "fictional.pdf"}]
    vault = Vault(str(tmp_path / "vault.json"))
    bundle = pseudonymize_submissions(subs, vault, "Fictional Quiz")
    responses = bundle["students"][0]["responses"]
    assert [item["response"] for item in responses] == ["latest answer", ""]
    assert "fake-01" not in str(bundle)


def test_normalize_uses_nested_student_analysis_attempt_and_timestamp():
    core = [{"user_id": "fictional-user", "submitted_at": "2026-01-02T00:00:00Z"}]
    rows = [
        {"student_data": {"id": "fictional-user", "attempt": 1, "submitted_at": "2026-01-01T00:00:00Z"}, "item_responses": [{"item_id": "essay", "answer": "older"}]},
        {"student_data": {"id": "fictional-user", "attempt": 2, "submitted_at": "2026-01-02T00:00:00Z"}, "item_responses": [{"item_id": "essay", "answer": "nested latest"}]},
    ]
    items = [{"entry": [{"id": "essay", "item_body": "Prompt", "points_possible": 1}]}]
    normalized = nq.normalize(core, rows, items)
    assert normalized[0]["new_quiz_attempt"] == 2
    assert normalized[0]["new_quiz_reported_at"] == "2026-01-02T00:00:00Z"
    assert normalized[0]["new_quiz_items"][0]["raw_html_answer"] == "nested latest"


def test_timestamp_parser_fails_closed():
    assert nq._parse_time("not-a-date") is None
    assert nq._parse_time("2026-01-01T00:00:00Z") is not None


def test_report_transport_accepts_wrapped_and_bare_progress_with_bounded_409():
    for created in ({"progress": {"url": "https://fake/progress"}}, {"url": "https://fake/progress"}):
        session = _Session(posts=[_Response(201, created)], gets=[
            _Response(409), _Response(200, {"progress": {"workflow_state": "completed", "results": {"url": "https://fake/result"}}}),
            _Response(409), _Response(200, [{"student_data": {"id": "fake"}}]),
        ])
        sleeps = []
        rows, error = nq._create_report(session, "https://base", "course", "quiz", {}, lambda seconds: sleeps.append(seconds))
        assert error is None and rows == [{"student_data": {"id": "fake"}}]
        assert sleeps == [nq.POLL_SECONDS, nq.POLL_SECONDS]


def test_report_transport_errors_are_actionable_and_bounded():
    for status in (401, 403):
        rows, error = nq._create_report(_Session(posts=[_Response(status)]), "https://base", "c", "q", {}, lambda _: None)
        assert rows is None and "active Canvas enrollment" in error
    failed = _Session(posts=[_Response(201, {"url": "progress"})], gets=[_Response(200, {"workflow_state": "failed"})])
    assert nq._create_report(failed, "https://base", "c", "q", {}, lambda _: None)[0] is None
    malformed = _Session(posts=[_Response(201, None, bad_json=True)])
    assert nq._create_report(malformed, "https://base", "c", "q", {}, lambda _: None)[0] is None
    timeout = _Session(posts=[_Response(201, {"url": "progress"})], gets=[_Response(200, {"workflow_state": "queued"})] * nq.POLL_LIMIT)
    assert nq._create_report(timeout, "https://base", "c", "q", {}, lambda _: None)[0] is None
    retries = _Session(gets=[_Response(409)] * (nq.REPORT_409_RETRIES + 1))
    assert nq._get_report(retries, "https://base", "result", {}, lambda _: None)[0] is None
    assert retries.get_calls == nq.REPORT_409_RETRIES + 1


def test_freshness_regenerates_once_then_fails_closed(monkeypatch):
    monkeypatch.setattr(nq, "_canvas_headers", lambda: ({"Authorization": "Bearer synthetic"}, "https://base"))
    core = [{"user_id": "fake", "submitted_at": "2026-01-03T00:00:00Z", "user": {"name": "Fictional"}}]
    item = [{"entry": [{"id": "essay", "item_body": "Prompt", "points_possible": 1}]}]
    stale = [{"student_data": {"id": "fake", "attempt": 1, "submitted_at": "2026-01-01T00:00:00Z"}, "item_responses": [{"item_id": "essay", "answer": "old"}]}]
    session = _Session(posts=[_Response(201, {"url": "p1"}), _Response(201, {"url": "p2"})], gets=[
        _Response(200, item), _Response(200, {"workflow_state": "completed", "results": {"url": "r1"}}), _Response(200, stale),
        _Response(200, {"workflow_state": "completed", "results": {"url": "r2"}}), _Response(200, stale),
    ])
    subs, error = nq.fetch("course", "quiz", core, session=session, sleep=lambda _: None)
    assert subs is None and "still older" in error
    assert session.post_calls == 2


def test_new_quiz_server_gates_block_push_and_late_watch_without_canvas():
    session = {"canvas_writeback_supported": False, "students": []}
    load = lambda _: session
    payload, _ = session_actions.review_push("synthetic", user_ids="[]", load_session=load, save_session=lambda _: None, canvas_get=lambda *_args, **_kwargs: None)
    assert payload["code"] == "canvas_writeback_unsupported"
    payload, _ = session_actions.push_grades("synthetic", user_ids="[]", review_token="x", load_session=load, save_session=lambda _: None, canvas_send=lambda *_args: None, canvas_get=lambda *_args, **_kwargs: None)
    assert payload["code"] == "canvas_writeback_unsupported"
    late = build_late_watch_state(mode="assisted", watch_late="true", has_openrouter_key=True, initial_missing_user_ids=[], submitted_user_ids=[], response_kind="scr", new_quiz_snapshot=True)
    assert late["supported"] is False and "immutable snapshots" in late["reason"]

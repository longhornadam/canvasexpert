"""Tests for the core AssignmentForge operation adapter.

Patterns follow test_quick_assignment_operation.py: private-root redirection,
mock Canvas API, and adapter lifecycle verification.
"""
import json
import os

import pytest

from api.operation_ledger import (
    batches, executor, models, operations, paths, registry,
)
from api.operation_ledger.adapters.assignment import (
    AssignmentAdapter,
    _normalize,
)


def _root(tmp_path, monkeypatch):
    root = tmp_path / "local-private"
    monkeypatch.setattr(paths, "private_root", lambda: root)
    return root


def _fake_courses():
    return [
        {"id": 101, "name": "Algebra 1"},
        {"id": 202, "name": "Biology"},
    ]


SAMPLE_AF_JSON = """<ASSIGNMENTFORGE_JSON>
{
  "version": "1.0-json",
  "type": "ASSIGNMENT",
  "title": "Found Poetry",
  "description": "<h2>Found Poetry</h2><p>Create a poem.</p>",
  "points": 100,
  "submission": {
    "types": ["online_text_entry", "online_upload"],
    "allowed_extensions": ["pdf", "docx"]
  }
}
</ASSIGNMENTFORGE_JSON>"""


def _fakecanvas_get(path, params=None, timeout=20):
    if "assignments/24680" in path:
        return {"id": 24680, "name": "Found Poetry",
                "html_url": "https://c/42/assignments/24680"}, None
    if "assignments" in path and "search_term" in (params or {}):
        search = (params or {}).get("search_term", "").lower()
        if "existing" in search:
            return [{"id": 999, "name": "Existing Quiz",
                     "html_url": "https://c/42/assignments/999",
                     "points_possible": 100, "published": False}], None
        return [], None
    if "assignment_groups" in path:
        return [{"id": 55, "name": "Homework"}], None
    return None, None


def _fake_canvas_send(method, path, payload, timeout=30):
    return {
        "id": 24680,
        "name": payload.get("assignment", {}).get("name", "Untitled"),
        "html_url": "https://canvas.invalid/courses/42/assignments/24680",
    }, None


def _fakecanvas_get_all(path, params=None, timeout=30):
    if "assignment_groups" in path:
        return [{"id": 55, "name": "Homework"}], None
    return [], None


# ── Protocol conformance ─────────────────────────────────────────────────

def test_adapter_is_registered():
    adapter = registry.get_adapter("content.assignment")
    assert adapter is not None
    assert adapter.kind == "content.assignment"


def test_payload_build_from_file(tmp_path, monkeypatch):
    af_file = tmp_path / "poetry.assignmentforge.json"
    af_file.write_text(SAMPLE_AF_JSON, encoding="utf-8")
    adapter = AssignmentAdapter()
    payload = adapter.build_payload({"path": str(af_file)})
    assert payload["name"] == "Found Poetry"
    assert payload["points"] == 100.0
    assert payload["submission_types"] == ["online_text_entry", "online_upload"]
    assert payload["allowed_extensions"] == ["pdf", "docx"]
    assert payload["published"] is False
    assert payload["post_to_sis"] is False


def test_payload_build_with_overrides(tmp_path, monkeypatch):
    af_file = tmp_path / "poetry.assignmentforge.json"
    af_file.write_text(SAMPLE_AF_JSON, encoding="utf-8")
    adapter = AssignmentAdapter()
    payload = adapter.build_payload({
        "path": str(af_file),
        "published": True,
        "post_to_sis": True,
        "due_at": "2026-08-01T23:59:00Z",
        "assignment_group_name": "Homework",
    })
    assert payload["published"] is True
    assert payload["post_to_sis"] is True
    assert payload["due_at"] == "2026-08-01T23:59:00Z"
    assert payload["assignment_group_name"] == "Homework"


def test_payload_build_raises_on_missing_path():
    adapter = AssignmentAdapter()
    with pytest.raises(ValueError, match="path is required"):
        adapter.build_payload({})


def test_payload_build_accepts_tiers(tmp_path, monkeypatch):
    af_file = tmp_path / "tiered.assignmentforge.json"
    af_file.write_text(
        """<ASSIGNMENTFORGE_JSON>
{"version":"1.0-json","type":"ASSIGNMENT","title":"Tiered","description":"<p>Hi</p>","tiers":[{"label":"Support","group":"Support"}]}
</ASSIGNMENTFORGE_JSON>""",
        encoding="utf-8",
    )
    adapter = AssignmentAdapter()
    payload = adapter.build_payload({"path": str(af_file)})
    assert payload["tiers"] == [{
        "label": "Support", "group": "Support", "title": "Tiered",
        "description": "<p>Hi</p>",
    }]


def test_payload_build_raises_on_placeholders(tmp_path, monkeypatch):
    af_file = tmp_path / "placeholder.assignmentforge.json"
    af_file.write_text(
        """<ASSIGNMENTFORGE_JSON>
{"version":"1.0-json","type":"ASSIGNMENT","title":"With Placeholder","description":"<p>See {{file:Rubric.pdf}}</p>"}
</ASSIGNMENTFORGE_JSON>""",
        encoding="utf-8",
    )
    adapter = AssignmentAdapter()
    with pytest.raises(ValueError, match="placeholders"):
        adapter.build_payload({"path": str(af_file)})


def test_source_digest_is_deterministic():
    adapter = AssignmentAdapter()
    payload = {"name": "Test", "description": "<p>Body</p>", "points": 100,
               "submission_types": ["online_text_entry"], "published": False,
               "post_to_sis": False}
    d1 = adapter.source_digest(payload)
    d2 = adapter.source_digest(payload)
    assert d1 == d2


# ── Target verification ─────────────────────────────────────────────────

def test_verify_targets_valid(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.config.active_courses",
        _fake_courses,
    )
    adapter = AssignmentAdapter()
    payload = {"name": "Test", "description": "<p>Body</p>", "points": 100,
               "submission_types": ["online_text_entry"], "published": False,
               "post_to_sis": False}
    targets = adapter.verify_targets(payload, [{"course_id": "101"}, {"course_id": "202"}])
    assert len(targets) == 2
    assert targets[0]["course_id"] == "101"
    assert targets[1]["course_id"] == "202"


def test_verify_targets_rejects_unknown_course(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.config.active_courses",
        _fake_courses,
    )
    adapter = AssignmentAdapter()
    payload = {"name": "Test", "description": "<p>Body</p>", "points": 100,
               "submission_types": ["online_text_entry"], "published": False,
               "post_to_sis": False}
    with pytest.raises(ValueError, match="not in active courses"):
        adapter.verify_targets(payload, [{"course_id": "999"}])


# ── Baseline / drift ────────────────────────────────────────────────────

def test_capture_baseline_no_existing(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.canvas_client.canvas_get",
        _fakecanvas_get,
    )
    adapter = AssignmentAdapter()
    payload = {"name": "New Assignment", "description": "<p>Body</p>", "points": 100,
               "submission_types": ["online_text_entry"], "published": False,
               "post_to_sis": False}
    baseline = adapter.capture_baseline(payload, {"course_id": "42"})
    assert baseline["existing_assignment"] is None


def test_capture_baseline_finds_existing(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.canvas_client.canvas_get",
        _fakecanvas_get,
    )
    adapter = AssignmentAdapter()
    payload = {"name": "Existing Quiz", "description": "<p>Body</p>", "points": 100,
               "submission_types": ["online_text_entry"], "published": False,
               "post_to_sis": False}
    baseline = adapter.capture_baseline(payload, {"course_id": "42"})
    assert baseline["existing_assignment"] is not None
    assert baseline["existing_assignment"]["id"] == "999"


def test_drift_detected_when_existing_found():
    adapter = AssignmentAdapter()
    assert adapter.check_drift(
        {"name": "Existing Quiz"},
        {"course_id": "42"},
        {"existing_assignment": {"id": "999", "name": "Existing Quiz"}},
    ) is True


def test_no_drift_when_no_existing():
    adapter = AssignmentAdapter()
    assert adapter.check_drift(
        {"name": "New Quiz"},
        {"course_id": "42"},
        {"existing_assignment": None},
    ) is False


# ── Freeze review ───────────────────────────────────────────────────────

def test_freeze_review(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.config.active_courses",
        _fake_courses,
    )
    adapter = AssignmentAdapter()
    payload = {"name": "Found Poetry", "description": "<h2>Found Poetry</h2><p>Create a poem.</p>",
               "points": 100, "submission_types": ["online_text_entry"],
               "published": True, "post_to_sis": False}
    review = adapter.freeze_review(payload, {"course_id": "101"}, {"existing_assignment": None})
    assert review["course_name"] == "Algebra 1"
    assert review["assignment_name"] == "Found Poetry"
    assert review["points"] == 100
    assert review["baseline_has_existing"] is False


# ── Execute ──────────────────────────────────────────────────────────────

def test_execute_creates_assignment(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.canvas_client._canvas_send",
        _fake_canvas_send,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.canvas_client.canvas_get",
        _fakecanvas_get,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.config.active_courses",
        _fake_courses,
    )

    adapter = AssignmentAdapter()
    payload = {"name": "Found Poetry", "description": "<h2>Found Poetry</h2><p>Create a poem.</p>",
               "points": 100, "submission_types": ["online_text_entry"],
               "published": True, "post_to_sis": False}

    op = models.new_operation(
        operation_id="op-af-execute",
        kind="content.assignment",
        source_ref=None,
        source_digest=adapter.source_digest(payload),
        normalized_payload=payload,
        targets=[
            models.new_target(
                target_key=adapter.target_key(payload, "42"),
                idempotency_key=adapter.idempotency_key(payload, "42"),
                course_id="42",
            )
        ],
    )
    operations.create_operation(op)

    target = op["targets"][0]
    baseline = adapter.capture_baseline(payload, target)
    assert baseline["existing_assignment"] is None

    from api.operation_ledger.executor import ExecutionContext
    from api.operation_ledger import claims

    claim = claims.acquire_claim(
        target_key=target["target_key"],
        operation_id=op["operation_id"],
        payload_digest=models.sha256_dict(payload),
    )

    context = ExecutionContext(
        operation_id=op["operation_id"],
        target_key=target["target_key"],
        claim=claim,
    )

    result = adapter.execute(payload, target, baseline, claim, context)
    assert result["state"] == "applied"
    assert result["returned_object_id"] == "24680"
    assert "assignments/24680" in (result.get("returned_object_url") or "")


def test_execute_handles_canvas_error(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)

    def fail_send(method, path, payload, timeout=30):
        return None, "HTTP 400: bad request"

    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.canvas_client._canvas_send",
        fail_send,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.canvas_client.canvas_get",
        _fakecanvas_get,
    )

    adapter = AssignmentAdapter()
    payload = {"name": "Fail Assignment", "description": "<p>Body</p>", "points": 100,
               "submission_types": ["online_text_entry"], "published": False,
               "post_to_sis": False}

    op = models.new_operation(
        operation_id="op-af-fail",
        kind="content.assignment",
        source_ref=None,
        source_digest=adapter.source_digest(payload),
        normalized_payload=payload,
        targets=[
            models.new_target(
                target_key=adapter.target_key(payload, "42"),
                idempotency_key=adapter.idempotency_key(payload, "42"),
                course_id="42",
            )
        ],
    )
    operations.create_operation(op)

    target = op["targets"][0]
    baseline = adapter.capture_baseline(payload, target)

    from api.operation_ledger.executor import ExecutionContext
    from api.operation_ledger import claims

    claim = claims.acquire_claim(
        target_key=target["target_key"],
        operation_id=op["operation_id"],
        payload_digest=models.sha256_dict(payload),
    )

    context = ExecutionContext(
        operation_id=op["operation_id"],
        target_key=target["target_key"],
        claim=claim,
    )

    result = adapter.execute(payload, target, baseline, claim, context)
    assert result["state"] == "failed"
    assert result["error_code"] == "canvas_rejected"


# ── Reconcile ────────────────────────────────────────────────────────────

def test_reconcile_finds_assignment(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.canvas_client.canvas_get",
        _fakecanvas_get,
    )
    adapter = AssignmentAdapter()
    result = adapter.reconcile(
        {"name": "Found Poetry"},
        {"course_id": "42", "returned_object_id": "24680"},
        {},
    )
    assert result["state"] == "applied"
    assert result["returned_object_id"] == "24680"


# ── Retry / reversal ────────────────────────────────────────────────────

def test_retry_selector_picks_unresolved():
    adapter = AssignmentAdapter()
    operation = {
        "targets": [
            {"target_key": "tk-1", "state": "applied"},
            {"target_key": "tk-2", "state": "failed"},
            {"target_key": "tk-3", "state": "sent_unknown"},
            {"target_key": "tk-4", "state": "skipped"},
        ]
    }
    selected = adapter.retry_selector(operation)
    keys = {t["target_key"] for t in selected}
    assert "tk-1" not in keys
    assert "tk-2" in keys
    assert "tk-3" in keys
    assert "tk-4" not in keys




# ── Full pipeline ────────────────────────────────────────────────────────

def test_pipeline_with_mocks(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.config.active_courses",
        _fake_courses,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.canvas_client.canvas_get",
        _fakecanvas_get,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.canvas_client._canvas_send",
        _fake_canvas_send,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.canvas_client.canvas_get_all",
        _fakecanvas_get_all,
    )

    af_file = tmp_path / "poetry.assignmentforge.json"
    af_file.write_text(SAMPLE_AF_JSON, encoding="utf-8")

    adapter = registry.get_adapter("content.assignment")
    assert adapter is not None

    # 1. Build payload from file
    payload = adapter.build_payload({
        "path": str(af_file),
        "published": True,
    })
    assert payload["name"] == "Found Poetry"
    assert payload["points"] == 100.0

    # 2. Verify targets
    targets = adapter.verify_targets(payload, [
        {"course_id": "101"},
        {"course_id": "202"},
    ])
    assert len(targets) == 2

    # 3. Capture baselines
    bl1 = adapter.capture_baseline(payload, targets[0])
    assert bl1["existing_assignment"] is None

    # 4. Freeze review
    r1 = adapter.freeze_review(payload, targets[0], bl1)
    assert r1["course_name"] == "Algebra 1"
    assert r1["assignment_name"] == "Found Poetry"

    # 5. No drift
    assert adapter.check_drift(payload, targets[0], bl1) is False


# ── Module attachment ────────────────────────────────────────────────────

def test_payload_build_with_module(tmp_path, monkeypatch):
    af_file = tmp_path / "poetry.assignmentforge.json"
    af_file.write_text(SAMPLE_AF_JSON, encoding="utf-8")
    adapter = AssignmentAdapter()
    payload = adapter.build_payload({
        "path": str(af_file),
        "module_name": "Unit 1",
    })
    assert payload["module_name"] == "Unit 1"


def test_freeze_review_shows_dependencies(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.config.active_courses",
        _fake_courses,
    )
    af_file = tmp_path / "poetry.assignmentforge.json"
    af_file.write_text(SAMPLE_AF_JSON, encoding="utf-8")
    adapter = AssignmentAdapter()
    payload = adapter.build_payload({
        "path": str(af_file),
        "module_name": "Unit 1",
    })
    review = adapter.freeze_review(payload, {"course_id": "101"}, {"existing_assignment": None})
    deps = review.get("dependencies", [])
    assert len(deps) == 1
    assert deps[0]["type"] == "module"
    assert deps[0]["name"] == "Unit 1"


def test_execute_with_module(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.canvas_client._canvas_send",
        _fake_canvas_send,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.canvas_client.canvas_get",
        _fakecanvas_get,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.canvas_client.canvas_get_all",
        lambda path, params=None, timeout=30: (
            ([{"id": 77, "name": "Unit 1"}], None)
            if "modules" in path else ([], None)
        ),
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.config.active_courses",
        _fake_courses,
    )

    adapter = AssignmentAdapter()
    payload = {"name": "Found Poetry", "description": "<h2>Found Poetry</h2><p>Create a poem.</p>",
               "points": 100, "submission_types": ["online_text_entry"],
               "published": True, "post_to_sis": False,
               "module_name": "Unit 1"}

    op = models.new_operation(
        operation_id="op-af-module",
        kind="content.assignment",
        source_ref=None,
        source_digest=adapter.source_digest(payload),
        normalized_payload=payload,
        targets=[
            models.new_target(
                target_key=adapter.target_key(payload, "42"),
                idempotency_key=adapter.idempotency_key(payload, "42"),
                course_id="42",
            )
        ],
    )
    operations.create_operation(op)

    target = op["targets"][0]
    baseline = adapter.capture_baseline(payload, target)

    from api.operation_ledger.executor import ExecutionContext
    from api.operation_ledger import claims

    claim = claims.acquire_claim(
        target_key=target["target_key"],
        operation_id=op["operation_id"],
        payload_digest=models.sha256_dict(payload),
    )
    context = ExecutionContext(
        operation_id=op["operation_id"],
        target_key=target["target_key"],
        claim=claim,
    )

    result = adapter.execute(payload, target, baseline, claim, context)
    assert result["state"] == "applied"
    assert result["returned_object_id"] == "24680"
# ── Autoscore scheduling ────────────────────────────────────────────────────

def test_payload_build_with_autoscore(tmp_path, monkeypatch):
    af_file = tmp_path / "poetry.assignmentforge.json"
    af_file.write_text(SAMPLE_AF_JSON, encoding="utf-8")
    adapter = AssignmentAdapter()
    payload = adapter.build_payload({
        "path": str(af_file),
        "autoscore_schedule": True,
        "autoscore_auto_push": False,
        "due_at": "2026-08-01T23:59:00Z",
    })
    assert payload.get("autoscore_schedule") is True
    assert "autoscore_auto_push" not in payload


def test_payload_build_rejects_autoscore_without_due_date(tmp_path):
    af_file = tmp_path / "poetry.assignmentforge.json"
    af_file.write_text(SAMPLE_AF_JSON, encoding="utf-8")
    with pytest.raises(ValueError, match="due_at is required"):
        AssignmentAdapter().build_payload({
            "path": str(af_file),
            "autoscore_schedule": True,
        })


def test_freeze_review_shows_autoscore(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.config.active_courses",
        _fake_courses,
    )
    af_file = tmp_path / "poetry.assignmentforge.json"
    af_file.write_text(SAMPLE_AF_JSON, encoding="utf-8")
    adapter = AssignmentAdapter()
    payload = adapter.build_payload({
        "path": str(af_file),
        "autoscore_schedule": True,
        "due_at": "2026-08-01T23:59:00Z",
    })
    review = adapter.freeze_review(payload, {"course_id": "101"}, {"existing_assignment": None})
    ascore = review.get("autoscore", {})
    assert ascore.get("scheduled") is True


def test_execute_with_autoscore_schedule(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.canvas_client._canvas_send",
        _fake_canvas_send,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.canvas_client.canvas_get",
        _fakecanvas_get,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.config.active_courses",
        _fake_courses,
    )
    jobs = {}

    class FakeQueue:
        @staticmethod
        def make_job_id(course_id, assignment_id):
            return f"{course_id}_{assignment_id}"

        @staticmethod
        def upsert_job(**kwargs):
            job_id = FakeQueue.make_job_id(
                kwargs["course_id"], kwargs["assignment_id"]
            )
            jobs[job_id] = {"job_id": job_id, **kwargs}
            return jobs[job_id]

    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment._autoscore_queue",
        lambda: FakeQueue,
    )

    adapter = AssignmentAdapter()
    payload = {"name": "Found Poetry", "description": "<h2>Found Poetry</h2><p>Create a poem.</p>",
               "points": 100, "submission_types": ["online_text_entry"],
               "published": True, "post_to_sis": False,
               "due_at": "2026-08-01T23:59:00Z",
               "autoscore_schedule": True}

    op = models.new_operation(
        operation_id="op-af-autoscore",
        kind="content.assignment",
        source_ref=None,
        source_digest=adapter.source_digest(payload),
        normalized_payload=payload,
        targets=[
            models.new_target(
                target_key=adapter.target_key(payload, "42"),
                idempotency_key=adapter.idempotency_key(payload, "42"),
                course_id="42",
            )
        ],
    )
    operations.create_operation(op)

    target = op["targets"][0]
    baseline = adapter.capture_baseline(payload, target)

    from api.operation_ledger.executor import ExecutionContext
    from api.operation_ledger import claims

    claim = claims.acquire_claim(
        target_key=target["target_key"],
        operation_id=op["operation_id"],
        payload_digest=models.sha256_dict(payload),
    )
    context = ExecutionContext(
        operation_id=op["operation_id"],
        target_key=target["target_key"],
        claim=claim,
    )

    result = adapter.execute(payload, target, baseline, claim, context)
    assert result["state"] == "applied"
    assert result["returned_object_id"] == "24680"
    schedule = next(s for s in result["steps"] if s["step_key"] == "schedule_autoscore")
    assert schedule["state"] == "applied"
    assert schedule["returned_object_id"] == "42_24680"
    assert list(jobs) == ["42_24680"]
    assert jobs["42_24680"]["course_name"] == "42"


def test_autoscore_failure_is_partial_and_retry_upserts_once(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.canvas_client._canvas_send",
        _fake_canvas_send,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.canvas_client.canvas_get",
        _fakecanvas_get,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment.config.active_courses",
        lambda: [{"id": 42, "name": "Fictional Course"}],
    )
    calls = []
    jobs = {}

    class FlakyQueue:
        @staticmethod
        def make_job_id(course_id, assignment_id):
            return f"{course_id}_{assignment_id}"

        @staticmethod
        def upsert_job(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise OSError("synthetic queue failure")
            job_id = FlakyQueue.make_job_id(
                kwargs["course_id"], kwargs["assignment_id"]
            )
            jobs[job_id] = {"job_id": job_id, **kwargs}
            return jobs[job_id]

    monkeypatch.setattr(
        "api.operation_ledger.adapters.assignment._autoscore_queue",
        lambda: FlakyQueue,
    )
    adapter = AssignmentAdapter()
    payload = {
        "name": "Found Poetry",
        "description": "<p>Create a poem.</p>",
        "points": 100,
        "submission_types": ["online_text_entry"],
        "published": False,
        "post_to_sis": False,
        "due_at": "2026-08-01T23:59:00Z",
        "autoscore_schedule": True,
    }
    target = models.new_target(
        target_key=adapter.target_key(payload, "42"),
        idempotency_key=adapter.idempotency_key(payload, "42"),
        course_id="42",
        baseline={"existing_assignment": None},
    )
    op = models.new_operation(
        operation_id="op-af-autoscore-retry",
        kind=adapter.kind,
        source_ref=None,
        source_digest=adapter.source_digest(payload),
        normalized_payload=payload,
        targets=[target],
    )
    operations.create_operation(op)
    batch = batches.freeze_batch(
        [op["operation_id"]],
        {op["operation_id"]: [adapter.freeze_review(payload, target, target["baseline"])]},
    )
    operations.set_operation_review(op["operation_id"], batch)

    first = executor.apply_operation(
        op["operation_id"], batch["batch_id"], batch["review_digest"]
    )
    assert first["status"] == "partial"
    stored = operations.get_operation(op["operation_id"])
    assert stored["targets"][0]["state"] == "partial"
    assert stored["targets"][0]["returned_object_id"] == "24680"
    assert stored["targets"][0]["error_code"] == "autoscore_queue_failed"

    retried = executor.retry_operation(op["operation_id"])
    assert retried["status"] == "applied"
    stored = operations.get_operation(op["operation_id"])
    assert stored["targets"][0]["error_code"] is None
    assert stored["targets"][0]["private_diagnostic"] is None
    assert len(calls) == 2
    assert list(jobs) == ["42_24680"]
    assert calls[0]["assignment_id"] == calls[1]["assignment_id"] == "24680"
    assert calls[0]["course_name"] == calls[1]["course_name"] == "Fictional Course"
    schedule = next(
        step for step in stored["targets"][0]["steps"]
        if step["step_key"] == "schedule_autoscore"
    )
    assert schedule["state"] == "applied"
    assert schedule["returned_object_id"] == "42_24680"

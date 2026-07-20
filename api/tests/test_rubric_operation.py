"""Tests for the RubricForge operation adapter.

Patterns follow test_assignment_operation.py: private-root redirection,
mock Canvas API, and adapter lifecycle verification.
"""
import json

import pytest

from api.operation_ledger import (
    models, operations, paths, registry,
)
from api.operation_ledger.adapters.rubric import (
    RubricAdapter,
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


SAMPLE_RF_JSON = """<RUBRICFORGE_JSON>
{
  "version": "1.0-json",
  "type": "RUBRIC",
  "title": "ELA Writing Rubric",
  "total_points": 30,
  "student_page": {
    "title": "How your writing is scored",
    "tagline": "This rubric helps you understand how your writing is evaluated."
  },
  "criteria": [
    {
      "name": "Focus & Organization",
      "points": 10,
      "use_range": false,
      "ratings": [
        {"label": "Advanced", "points": 10, "description": "Clear focus", "student_description": "Your writing stays on topic."},
        {"label": "Proficient", "points": 7, "description": "Mostly focused", "student_description": "Mostly on topic."},
        {"label": "Developing", "points": 3, "description": "Some focus", "student_description": "Sometimes off topic."},
        {"label": "Beginning", "points": 0, "description": "No focus", "student_description": "Hard to follow."}
      ]
    },
    {
      "name": "Evidence",
      "points": 20,
      "use_range": false,
      "ratings": [
        {"label": "Advanced", "points": 20, "description": "Strong evidence", "student_description": "You used strong evidence."},
        {"label": "Proficient", "points": 14, "description": "Good evidence", "student_description": "Good evidence."},
        {"label": "Developing", "points": 7, "description": "Some evidence", "student_description": "Some evidence."},
        {"label": "Beginning", "points": 0, "description": "No evidence", "student_description": "No evidence."}
      ]
    }
  ]
}
</RUBRICFORGE_JSON>"""


def _fake_canvas_get(path, params=None, timeout=20):
    if "rubrics/789" in path:
        return {"id": 789, "title": "ELA Writing Rubric",
                "html_url": "https://c/42/rubrics/789"}, None
    if "rubrics" in path and "search_term" in (params or {}):
        search = (params or {}).get("search_term", "").lower()
        if "existing" in search:
            return [{"id": 999, "title": "Existing Rubric"}], None
        return [], None
    return None, None


def _fake_canvas_send(method, path, payload, timeout=30):
    return {
        "id": 789,
        "title": "ELA Writing Rubric",
        "html_url": "https://canvas.invalid/courses/42/rubrics/789",
    }, None


# ── Protocol conformance ─────────────────────────────────────────────────

def test_adapter_is_registered():
    adapter = registry.get_adapter("content.rubric")
    assert adapter is not None
    assert adapter.kind == "content.rubric"


def test_payload_build_from_file(tmp_path, monkeypatch):
    rf_file = tmp_path / "writing.rubricforge.json"
    rf_file.write_text(SAMPLE_RF_JSON, encoding="utf-8")
    adapter = RubricAdapter()
    payload = adapter.build_payload({"path": str(rf_file)})
    assert payload["title"] == "ELA Writing Rubric"
    assert payload["total_points"] == 30
    assert len(payload["criteria"]) == 2
    assert payload["student_page_title"] == "How your writing is scored"


def test_payload_build_raises_on_missing_path():
    adapter = RubricAdapter()
    with pytest.raises(ValueError, match="path is required"):
        adapter.build_payload({})


def test_source_digest_is_deterministic():
    adapter = RubricAdapter()
    payload = {"title": "Test", "total_points": 10, "criteria": []}
    d1 = adapter.source_digest(payload)
    d2 = adapter.source_digest(payload)
    assert d1 == d2


# ── Target verification ─────────────────────────────────────────────────

def test_verify_targets_valid(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.rubric.config.active_courses",
        _fake_courses,
    )
    adapter = RubricAdapter()
    payload = {"title": "Test", "total_points": 10, "criteria": []}
    targets = adapter.verify_targets(payload, [{"course_id": "101"}, {"course_id": "202"}])
    assert len(targets) == 2


def test_verify_targets_rejects_unknown_course(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.rubric.config.active_courses",
        _fake_courses,
    )
    adapter = RubricAdapter()
    payload = {"title": "Test", "total_points": 10, "criteria": []}
    with pytest.raises(ValueError, match="not in active courses"):
        adapter.verify_targets(payload, [{"course_id": "999"}])


# ── Baseline / drift ────────────────────────────────────────────────────

def test_capture_baseline_no_existing(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.rubric.canvas_client._canvas_get",
        _fake_canvas_get,
    )
    adapter = RubricAdapter()
    payload = {"title": "New Rubric", "total_points": 10, "criteria": []}
    baseline = adapter.capture_baseline(payload, {"course_id": "42"})
    assert baseline["existing_rubric"] is None


def test_capture_baseline_finds_existing(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.rubric.canvas_client._canvas_get",
        _fake_canvas_get,
    )
    adapter = RubricAdapter()
    payload = {"title": "Existing Rubric", "total_points": 10, "criteria": []}
    baseline = adapter.capture_baseline(payload, {"course_id": "42"})
    assert baseline["existing_rubric"] is not None
    assert baseline["existing_rubric"]["id"] == "999"


def test_drift_detected_when_existing_found():
    adapter = RubricAdapter()
    assert adapter.check_drift(
        {"title": "Existing Rubric"},
        {"course_id": "42"},
        {"existing_rubric": {"id": "999", "title": "Existing Rubric"}},
    ) is True


def test_no_drift_when_no_existing():
    adapter = RubricAdapter()
    assert adapter.check_drift(
        {"title": "New Rubric"},
        {"course_id": "42"},
        {"existing_rubric": None},
    ) is False


# ── Freeze review ───────────────────────────────────────────────────────

def test_freeze_review(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.rubric.config.active_courses",
        _fake_courses,
    )
    adapter = RubricAdapter()
    payload = {"title": "ELA Writing Rubric", "total_points": 30,
               "criteria": [{"name": "Focus"}, {"name": "Evidence"},
                            {"name": "Conventions"}]}
    review = adapter.freeze_review(payload, {"course_id": "101"},
                                    {"existing_rubric": None})
    assert review["course_name"] == "Algebra 1"
    assert review["rubric_title"] == "ELA Writing Rubric"
    assert review["criteria_count"] == 3


# ── Execute ──────────────────────────────────────────────────────────────

def test_execute_creates_rubric(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "api.operation_ledger.adapters.rubric.canvas_client._canvas_send",
        _fake_canvas_send,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.rubric.canvas_client._canvas_get",
        _fake_canvas_get,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.rubric.config.active_courses",
        _fake_courses,
    )

    adapter = RubricAdapter()
    payload = {"title": "ELA Writing Rubric", "total_points": 30,
               "criteria": [{"name": "Focus", "points": 10,
                             "ratings": [{"label": "A", "points": 10, "description": "X",
                                          "student_description": "Y"},
                                         {"label": "B", "points": 0, "description": "Z",
                                          "student_description": "W"}]}]}

    op = models.new_operation(
        operation_id="op-rf-execute",
        kind="content.rubric",
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
    assert result["returned_object_id"] == "789"
    assert "rubrics/789" in (result.get("returned_object_url") or "")


def test_execute_handles_canvas_error(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)

    def fail_send(method, path, payload, timeout=30):
        return None, "HTTP 400: bad request"

    monkeypatch.setattr(
        "api.operation_ledger.adapters.rubric.canvas_client._canvas_send",
        fail_send,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.rubric.canvas_client._canvas_get",
        _fake_canvas_get,
    )

    adapter = RubricAdapter()
    payload = {"title": "Fail Rubric", "total_points": 10,
               "criteria": [{"name": "C1", "points": 10,
                             "ratings": [{"label": "A", "points": 10, "description": "X",
                                          "student_description": "Y"},
                                         {"label": "B", "points": 0, "description": "Z",
                                          "student_description": "W"}]}]}

    op = models.new_operation(
        operation_id="op-rf-fail",
        kind="content.rubric",
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

def test_reconcile_finds_rubric(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.rubric.canvas_client._canvas_get",
        _fake_canvas_get,
    )
    adapter = RubricAdapter()
    result = adapter.reconcile(
        {"title": "ELA Writing Rubric"},
        {"course_id": "42", "returned_object_id": "789"},
        {},
    )
    assert result["state"] == "applied"
    assert result["returned_object_id"] == "789"


# ── Retry / reversal ────────────────────────────────────────────────────

def test_retry_selector_picks_unresolved():
    adapter = RubricAdapter()
    operation = {
        "targets": [
            {"target_key": "tk-1", "state": "applied"},
            {"target_key": "tk-2", "state": "failed"},
            {"target_key": "tk-3", "state": "sent_unknown"},
        ]
    }
    selected = adapter.retry_selector(operation)
    keys = {t["target_key"] for t in selected}
    assert "tk-1" not in keys
    assert "tk-2" in keys
    assert "tk-3" in keys




# ── Full pipeline ────────────────────────────────────────────────────────

def test_pipeline_with_mocks(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "api.operation_ledger.adapters.rubric.config.active_courses",
        _fake_courses,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.rubric.canvas_client._canvas_get",
        _fake_canvas_get,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.rubric.canvas_client._canvas_send",
        _fake_canvas_send,
    )

    rf_file = tmp_path / "writing.rubricforge.json"
    rf_file.write_text(SAMPLE_RF_JSON, encoding="utf-8")

    adapter = registry.get_adapter("content.rubric")
    assert adapter is not None

    # 1. Build payload from file
    payload = adapter.build_payload({"path": str(rf_file)})
    assert payload["title"] == "ELA Writing Rubric"
    assert payload["total_points"] == 30
    assert len(payload["criteria"]) == 2

    # 2. Verify targets
    targets = adapter.verify_targets(payload, [
        {"course_id": "101"},
        {"course_id": "202"},
    ])
    assert len(targets) == 2

    # 3. Capture baselines
    bl1 = adapter.capture_baseline(payload, targets[0])
    assert bl1["existing_rubric"] is None

    # 4. Freeze review
    r1 = adapter.freeze_review(payload, targets[0], bl1)
    assert r1["course_name"] == "Algebra 1"
    assert r1["rubric_title"] == "ELA Writing Rubric"

    # 5. No drift
    assert adapter.check_drift(payload, targets[0], bl1) is False
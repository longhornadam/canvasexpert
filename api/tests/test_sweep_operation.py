"""Tests for the sweep operation adapter."""
import pytest
from api.operation_ledger import models, operations, paths, registry
from api.operation_ledger.adapters.sweep import SweepAdapter

def _root(tmp_path, monkeypatch):
    root = tmp_path / "local-private"
    monkeypatch.setattr(paths, "private_root", lambda: root)
    return root

def _fake_courses():
    return [{"id": 101, "name": "Algebra 1"}]

# ── Protocol conformance ─────────────────────────────────────────────────

def test_adapter_is_registered():
    adapter = registry.get_adapter("gradebook.sweep")
    assert adapter is not None
    assert adapter.kind == "gradebook.sweep"

def test_payload_build():
    adapter = SweepAdapter()
    payload = adapter.build_payload({"skip_weekends": True, "holidays": ["2026-01-01"]})
    assert payload["settings"]["skip_weekends"] is True
    assert "2026-01-01" in payload["settings"]["holidays"]

def test_payload_build_defaults():
    adapter = SweepAdapter()
    payload = adapter.build_payload({})
    assert payload["settings"]["skip_weekends"] is True
    assert payload["settings"]["honor_extra_time"] is True

def test_source_digest_deterministic():
    adapter = SweepAdapter()
    p = {"settings": {"skip_weekends": True, "holidays": []}}
    assert adapter.source_digest(p) == adapter.source_digest(p)

def test_verify_targets_valid(monkeypatch):
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.config.active_courses", _fake_courses)
    adapter = SweepAdapter()
    t = adapter.verify_targets({"settings": {}}, [{"course_id": "101"}])
    assert len(t) == 1

def test_verify_targets_rejects_unknown(monkeypatch):
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.config.active_courses", _fake_courses)
    adapter = SweepAdapter()
    with pytest.raises(ValueError, match="not in active courses"):
        adapter.verify_targets({"settings": {}}, [{"course_id": "999"}])

def test_freeze_review(monkeypatch):
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.config.active_courses", _fake_courses)
    adapter = SweepAdapter()
    r = adapter.freeze_review({"settings": {}}, {"course_id": "101"},
                               {"entries": [{"student_name": "A", "assignment_name": "B",
                                              "school_days": 2, "seconds_override": 172800}],
                                "skipped": []})
    assert r["course_name"] == "Algebra 1"
    assert r["entry_count"] == 1

def test_baseline_canvas_error_detects_drift(monkeypatch):
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.canvas_client._canvas_get_all",
                        lambda *a, **kw: ([], None))
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.config.get_combined_calendar_for_range",
                        lambda: {"no_count_dates": []})
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.config.get_extra_time",
                        lambda course_id: [])
    adapter = SweepAdapter()
    assert adapter.check_drift({}, {"course_id": "42"}, {"canvas_error": "timeout"}) is True
    assert adapter.check_drift({}, {"course_id": "42"}, {"entries": []}) is False

def test_retry_selector():
    adapter = SweepAdapter()
    sel = adapter.retry_selector({"targets": [
        {"target_key": "a", "state": "applied"},
        {"target_key": "b", "state": "failed"},
    ]})
    assert [s["target_key"] for s in sel] == ["b"]

def test_reversal_unsupported():
    adapter = SweepAdapter()
    assert adapter.reversal_descriptor({}, {})["supported"] is False

# ── Execute with canvas mocks ────────────────────────────────────────────

FAKE_ASSIGNMENTS = [{"id": 10, "name": "Essay 1", "published": True, "due_at": "2026-06-01T23:59:00Z"}]
FAKE_SUBMISSIONS = [{
    "assignment_id": 10, "user_id": 1,
    "submitted_at": "2026-06-05T12:00:00Z",
    "workflow_state": "late",
}]
FAKE_STUDENTS = [{"id": 1, "sortable_name": "Smith, John"}]

def _mock_canvas_get_all(path, params=None, timeout=30):
    if "assignments" in path and "submissions" not in path:
        return FAKE_ASSIGNMENTS, None
    if "submissions" in path:
        return FAKE_SUBMISSIONS, None
    if "users" in path:
        return FAKE_STUDENTS, None
    return [], None

def _mock_canvas_send(method, path, payload, timeout=30):
    return {"ok": True}, None

def test_execute_applies_sweep(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.canvas_client._canvas_get_all", _mock_canvas_get_all)
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.canvas_client._canvas_send", _mock_canvas_send)
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.config.active_courses", _fake_courses)
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.config.get_combined_calendar_for_range",
                        lambda: {"no_count_dates": []})
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.config.get_extra_time",
                        lambda course_id: [])

    adapter = SweepAdapter()
    payload = adapter.build_payload({"skip_weekends": True})
    op = models.new_operation(
        operation_id="op-sw-execute",
        kind="gradebook.sweep", source_ref=None,
        source_digest=adapter.source_digest(payload),
        normalized_payload=payload,
        targets=[models.new_target(
            target_key=adapter.target_key(payload, "42"),
            idempotency_key=adapter.idempotency_key(payload, "42"),
            course_id="42")])
    operations.create_operation(op)
    target = op["targets"][0]
    baseline = adapter.capture_baseline(payload, target)
    assert baseline["entry_count"] > 0

    from api.operation_ledger.executor import ExecutionContext
    from api.operation_ledger import claims
    claim = claims.acquire_claim(
        target_key=target["target_key"], operation_id=op["operation_id"],
        payload_digest=models.sha256_dict(payload))
    context = ExecutionContext(operation_id=op["operation_id"], target_key=target["target_key"], claim=claim)
    result = adapter.execute(payload, target, baseline, claim, context)
    assert result["state"] in ("applied", "partial")

def test_execute_no_late_subs(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    def _no_late(path, params=None, timeout=30):
        if "assignments" in path and "submissions" not in path:
            return [{"id": 10, "name": "Essay 1", "published": True, "due_at": "2026-06-01T23:59:00Z"}], None
        if "submissions" in path:
            return [], None  # no submissions at all
        if "users" in path:
            return [{"id": 1, "sortable_name": "Smith, John"}], None
        return [], None
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.canvas_client._canvas_get_all", _no_late)
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.canvas_client._canvas_send", _mock_canvas_send)
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.config.active_courses", _fake_courses)
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.config.get_combined_calendar_for_range",
                        lambda: {"no_count_dates": []})
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.config.get_extra_time",
                        lambda course_id: [])

    adapter = SweepAdapter()
    payload = adapter.build_payload({"skip_weekends": True})
    baseline = adapter.capture_baseline(payload, {"course_id": "42"})
    assert baseline["entry_count"] == 0

def test_execute_handles_canvas_error(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    def _fail(path, params=None, timeout=30):
        return None, "HTTP 500"
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.canvas_client._canvas_get_all", _fail)
    adapter = SweepAdapter()
    payload = {"settings": {"skip_weekends": True, "holidays": []}}
    op = models.new_operation(
        operation_id="op-sw-fail",
        kind="gradebook.sweep", source_ref=None,
        source_digest=adapter.source_digest(payload),
        normalized_payload=payload,
        targets=[models.new_target(
            target_key=adapter.target_key(payload, "42"),
            idempotency_key=adapter.idempotency_key(payload, "42"),
            course_id="42")])
    operations.create_operation(op)
    target = op["targets"][0]
    baseline = {"canvas_error": "HTTP 500"}
    from api.operation_ledger.executor import ExecutionContext
    from api.operation_ledger import claims
    claim = claims.acquire_claim(
        target_key=target["target_key"], operation_id=op["operation_id"],
        payload_digest=models.sha256_dict(payload))
    context = ExecutionContext(operation_id=op["operation_id"], target_key=target["target_key"], claim=claim)
    result = adapter.execute(payload, target, baseline, claim, context)
    assert result["state"] == "failed"

def test_pipeline_with_mocks(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.canvas_client._canvas_get_all", _mock_canvas_get_all)
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.canvas_client._canvas_send", _mock_canvas_send)
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.config.active_courses", _fake_courses)
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.config.get_combined_calendar_for_range",
                        lambda: {"no_count_dates": []})
    monkeypatch.setattr("api.operation_ledger.adapters.sweep.config.get_extra_time",
                        lambda course_id: [])

    adapter = registry.get_adapter("gradebook.sweep")
    assert adapter is not None

    # 1. Build
    payload = adapter.build_payload({"skip_weekends": True, "honor_extra_time": True})
    assert payload["settings"]["skip_weekends"] is True

    # 2. Verify
    targets = adapter.verify_targets(payload, [{"course_id": "101"}])
    assert len(targets) == 1

    # 3. Baseline
    bl = adapter.capture_baseline(payload, targets[0])
    assert bl["entry_count"] >= 0

    # 4. Review
    r = adapter.freeze_review(payload, targets[0], bl)
    assert r["course_name"] == "Algebra 1"
"""Tests for the extension operation adapter."""
import json
import pytest
from api.operation_ledger import models, operations, paths, registry
from api.operation_ledger.adapters.extension import ExtensionAdapter

def _root(tmp_path, monkeypatch):
    root = tmp_path / "local-private"
    monkeypatch.setattr(paths, "private_root", lambda: root)
    return root

def _fake_courses():
    return [{"id": 101, "name": "Algebra 1"}]

# ── Protocol ─────────────────────────────────────────────────────────────

def test_adapter_is_registered():
    a = registry.get_adapter("gradebook.extension")
    assert a is not None
    assert a.kind == "gradebook.extension"

def test_payload_build():
    a = ExtensionAdapter()
    p = a.build_payload({"assignment_id": "10", "student_ids": ["1", "2"], "days": 3})
    assert p["assignment_id"] == "10"
    assert "1" in p["student_ids"]
    assert p["days"] == 3

def test_payload_build_from_json_string():
    a = ExtensionAdapter()
    p = a.build_payload({"assignment_id": "10", "student_ids": '["1","2"]', "days": 1})
    assert len(p["student_ids"]) == 2

def test_payload_build_raises_no_assignment():
    a = ExtensionAdapter()
    with pytest.raises(ValueError, match="assignment_id"):
        a.build_payload({"student_ids": ["1"]})

def test_payload_build_raises_no_students():
    a = ExtensionAdapter()
    with pytest.raises(ValueError, match="at least one student_id"):
        a.build_payload({"assignment_id": "10", "student_ids": []})

def test_source_digest_deterministic():
    a = ExtensionAdapter()
    p = {"assignment_id": "10", "student_ids": ["1", "2"], "days": 3,
         "skip_weekends": True, "holidays": []}
    assert a.source_digest(p) == a.source_digest(p)

def test_verify_targets_valid(monkeypatch):
    monkeypatch.setattr("api.operation_ledger.adapters.extension.config.active_courses", _fake_courses)
    a = ExtensionAdapter()
    t = a.verify_targets({"assignment_id": "10", "student_ids": ["1"]}, [{"course_id": "101"}])
    assert len(t) == 1

def test_verify_targets_rejects_unknown(monkeypatch):
    monkeypatch.setattr("api.operation_ledger.adapters.extension.config.active_courses", _fake_courses)
    a = ExtensionAdapter()
    with pytest.raises(ValueError, match="not in active"):
        a.verify_targets({"assignment_id": "10", "student_ids": ["1"]}, [{"course_id": "999"}])

# ── Baseline / drift ────────────────────────────────────────────────────

def test_capture_baseline_fetches_assignment_and_overrides(monkeypatch):
    calls = []
    def fake_get(path, params=None, timeout=20):
        calls.append(path)
        if "overrides" in path:
            return [{"id": 5, "student_ids": [1], "due_at": "2026-07-15T23:59:00Z"}], None
        if "assignments" in path:
            return {"id": 10, "name": "Essay", "due_at": "2026-07-10T23:59:00Z"}, None
        return None, None
    monkeypatch.setattr("api.operation_ledger.adapters.extension.canvas_client._canvas_get", fake_get)
    a = ExtensionAdapter()
    bl = a.capture_baseline({"assignment_id": "10"}, {"course_id": "42"})
    assert bl["assignment"] is not None
    assert len(bl["existing_overrides"]) == 1

def test_drift_detected_when_due_changed(monkeypatch):
    calls = []
    def fake_get(path, **kw):
        calls.append(path)
        return {"id": 10, "name": "Essay", "due_at": "2026-07-15T23:59:00Z"}, None
    monkeypatch.setattr("api.operation_ledger.adapters.extension.canvas_client._canvas_get", fake_get)
    a = ExtensionAdapter()
    # Baseline had due_at 2026-07-10, now it's 2026-07-15
    dr = a.check_drift({"assignment_id": "10"}, {"course_id": "42"},
                        {"assignment": {"due_at": "2026-07-10T23:59:00Z"}})
    assert dr is True

# ── Freeze review ───────────────────────────────────────────────────────

def test_freeze_review(monkeypatch):
    monkeypatch.setattr("api.operation_ledger.adapters.extension.config.active_courses", _fake_courses)
    a = ExtensionAdapter()
    r = a.freeze_review({"assignment_id": "10", "student_ids": ["1", "2"], "days": 3},
                         {"course_id": "101"},
                         {"assignment": {"name": "Essay", "due_at": "2026-07-10T23:59:00Z"},
                          "existing_overrides": []})
    assert r["course_name"] == "Algebra 1"
    assert r["assignment_name"] == "Essay"
    assert r["student_count"] == 2

# ── Execute ─────────────────────────────────────────────────────────────

def test_execute_creates_new_override(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    calls = []
    def fake_get(path, params=None, timeout=20):
        calls.append(path)
        if "overrides" in path:
            return [], None  # no existing overrides
        if "assignments" in path:
            return {"id": 10, "name": "Essay", "due_at": "2026-07-10T23:59:00Z"}, None
        return None, None
    monkeypatch.setattr("api.operation_ledger.adapters.extension.canvas_client._canvas_get", fake_get)
    def fake_send(method, path, payload, timeout=30):
        return {"id": 99, "student_ids": [1], "due_at": "2026-07-15T23:59:00Z"}, None
    monkeypatch.setattr("api.operation_ledger.adapters.extension.canvas_client._canvas_send", fake_send)
    monkeypatch.setattr("api.operation_ledger.adapters.extension.config.active_courses", _fake_courses)
    monkeypatch.setattr("api.operation_ledger.adapters.extension.config.get_combined_calendar_for_range",
                        lambda: {"no_count_dates": []})

    a = ExtensionAdapter()
    p = {"assignment_id": "10", "student_ids": ["1"], "days": 3,
         "skip_weekends": True, "holidays": []}
    op = models.new_operation(
        operation_id="op-ext-exec", kind="gradebook.extension",
        source_ref=None, source_digest=a.source_digest(p),
        normalized_payload=p,
        targets=[models.new_target(target_key=a.target_key(p, "42"),
                                    idempotency_key=a.idempotency_key(p, "42"),
                                    course_id="42")])
    operations.create_operation(op)
    target = op["targets"][0]
    baseline = a.capture_baseline(p, target)
    from api.operation_ledger.executor import ExecutionContext
    from api.operation_ledger import claims
    claim = claims.acquire_claim(target_key=target["target_key"],
                                  operation_id=op["operation_id"],
                                  payload_digest=models.sha256_dict(p))
    ctx = ExecutionContext(operation_id=op["operation_id"], target_key=target["target_key"], claim=claim)
    result = a.execute(p, target, baseline, claim, ctx)
    assert result["state"] == "applied"

def test_execute_handles_canvas_error(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    def fail_get(path, params=None, timeout=20):
        return {"id": 10, "name": "Essay", "due_at": "2026-07-10T23:59:00Z"}, None
    monkeypatch.setattr("api.operation_ledger.adapters.extension.canvas_client._canvas_get", fail_get)
    def fail_send(method, path, payload, timeout=30):
        return None, "HTTP 400: bad request"
    monkeypatch.setattr("api.operation_ledger.adapters.extension.canvas_client._canvas_send", fail_send)
    monkeypatch.setattr("api.operation_ledger.adapters.extension.config.get_combined_calendar_for_range",
                        lambda: {"no_count_dates": []})
    a = ExtensionAdapter()
    p = {"assignment_id": "10", "student_ids": ["1"], "days": 1,
         "skip_weekends": True, "holidays": []}
    op = models.new_operation(
        operation_id="op-ext-fail", kind="gradebook.extension",
        source_ref=None, source_digest=a.source_digest(p),
        normalized_payload=p,
        targets=[models.new_target(target_key=a.target_key(p, "42"),
                                    idempotency_key=a.idempotency_key(p, "42"), course_id="42")])
    operations.create_operation(op)
    target = op["targets"][0]
    baseline = a.capture_baseline(p, target)
    from api.operation_ledger.executor import ExecutionContext
    from api.operation_ledger import claims
    claim = claims.acquire_claim(target_key=target["target_key"],
                                  operation_id=op["operation_id"],
                                  payload_digest=models.sha256_dict(p))
    ctx = ExecutionContext(operation_id=op["operation_id"], target_key=target["target_key"], claim=claim)
    result = a.execute(p, target, baseline, claim, ctx)
    assert result["state"] == "partial"

# ── Reconcile / retry / reversal ────────────────────────────────────────

def test_reconcile_finds_override(monkeypatch):
    def fake_get(path, params=None, timeout=20):
        if "overrides" in path:
            return [{"id": 99, "student_ids": [1], "due_at": "2026-07-15T23:59:00Z"}], None
        return None, None
    monkeypatch.setattr("api.operation_ledger.adapters.extension.canvas_client._canvas_get", fake_get)
    a = ExtensionAdapter()
    # Set up a target with an outbound marker so reconcile knows work was done
    from api.operation_ledger import models as m
    step = m.new_step("apply_extension")
    step["outbound_started_at"] = "2026-07-11T00:00:00Z"
    r = a.reconcile({"student_ids": ["1"]}, {"course_id": "42", "steps": [step]}, {})
    assert r["state"] == "applied"

def test_retry_selector():
    a = ExtensionAdapter()
    sel = a.retry_selector({"targets": [
        {"target_key": "a", "state": "applied"},
        {"target_key": "b", "state": "failed"},
    ]})
    assert [s["target_key"] for s in sel] == ["b"]

def test_reversal_supported_with_overrides():
    a = ExtensionAdapter()
    d = a.reversal_descriptor({}, {"baseline": {"existing_overrides": [{"id": 5}]}})
    assert d["supported"] is True

def test_reversal_unsupported():
    a = ExtensionAdapter()
    d = a.reversal_descriptor({}, {"baseline": {"existing_overrides": []}})
    assert d["supported"] is False

def test_pipeline(monkeypatch):
    monkeypatch.setattr("api.operation_ledger.adapters.extension.config.active_courses", _fake_courses)
    monkeypatch.setattr("api.operation_ledger.adapters.extension.config.get_combined_calendar_for_range",
                        lambda: {"no_count_dates": []})
    a = registry.get_adapter("gradebook.extension")
    p = a.build_payload({"assignment_id": "10", "student_ids": ["1", "2"], "days": 3})
    assert p["assignment_id"] == "10"
    targets = a.verify_targets(p, [{"course_id": "101"}])
    assert len(targets) == 1
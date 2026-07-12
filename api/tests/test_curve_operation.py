"""Tests for the curve operation adapter."""
import pytest
from api.operation_ledger import models, operations, paths, registry
from api.operation_ledger.adapters.curve import CurveAdapter

def _root(tmp_path, monkeypatch):
    root = tmp_path / "local-private"
    monkeypatch.setattr(paths, "private_root", lambda: root)
    return root

def _fake_courses():
    return [{"id": 101, "name": "Algebra 1"}]

# ── Protocol ─────────────────────────────────────────────────────────────

def test_adapter_is_registered():
    a = registry.get_adapter("gradebook.curve")
    assert a is not None
    assert a.kind == "gradebook.curve"

def test_payload_build():
    a = CurveAdapter()
    p = a.build_payload({"assignment_id": "10", "curve_type": "flat_bump",
                          "settings": {"bump": 5}})
    assert p["assignment_id"] == "10"
    assert p["curve_type"] == "flat_bump"
    assert p["settings"]["bump"] == 5

def test_payload_build_from_json_string():
    a = CurveAdapter()
    p = a.build_payload({"assignment_id": "10", "curve_type": "flat_bump",
                          "settings": '{"bump": 5}'})
    assert p["settings"]["bump"] == 5

def test_payload_build_raises_no_assignment():
    a = CurveAdapter()
    with pytest.raises(ValueError, match="assignment_id"):
        a.build_payload({"curve_type": "flat_bump"})

def test_payload_build_raises_no_type():
    a = CurveAdapter()
    with pytest.raises(ValueError, match="curve_type"):
        a.build_payload({"assignment_id": "10"})

def test_source_digest_deterministic():
    a = CurveAdapter()
    p = {"assignment_id": "10", "curve_type": "flat_bump", "settings": {"bump": 5}}
    assert a.source_digest(p) == a.source_digest(p)

def test_verify_targets_valid(monkeypatch):
    monkeypatch.setattr("api.operation_ledger.adapters.curve.config.active_courses", _fake_courses)
    a = CurveAdapter()
    t = a.verify_targets({"assignment_id": "10", "curve_type": "flat_bump"},
                          [{"course_id": "101"}])
    assert len(t) == 1

def test_verify_targets_rejects_unknown(monkeypatch):
    monkeypatch.setattr("api.operation_ledger.adapters.curve.config.active_courses", _fake_courses)
    a = CurveAdapter()
    with pytest.raises(ValueError, match="not in active"):
        a.verify_targets({}, [{"course_id": "999"}])

# ── Baseline / drift ────────────────────────────────────────────────────

def test_capture_baseline_returns_scored(monkeypatch):
    def fake_assign(cid, aid):
        return {"id": 10, "name": "Quiz", "points_possible": 100}, None
    def fake_students(cid):
        return [{"id": 1, "sortable_name": "Smith, John"}], None
    def fake_subs(cid, aid):
        return [{"user_id": 1, "score": 80, "workflow_state": "graded"}], None
    monkeypatch.setattr("api.operation_ledger.adapters.curve._assignment", fake_assign)
    monkeypatch.setattr("api.operation_ledger.adapters.curve._course_students", fake_students)
    monkeypatch.setattr("api.operation_ledger.adapters.curve._assignment_submissions", fake_subs)
    a = CurveAdapter()
    bl = a.capture_baseline({"assignment_id": "10"}, {"course_id": "42"})
    assert len(bl["scored_students"]) == 1
    assert bl["scored_students"][0]["score"] == 80

def test_drift_detected(monkeypatch):
    def fake_subs(cid, aid):
        return [{"user_id": 1, "score": 90, "workflow_state": "graded"}], None
    monkeypatch.setattr("api.operation_ledger.adapters.curve._assignment_submissions", fake_subs)
    a = CurveAdapter()
    bl = {"scored_students": [{"user_id": "1", "score": 80}]}
    assert a.check_drift({}, {"course_id": "42"}, bl) is True

# ── Freeze review ───────────────────────────────────────────────────────

def test_freeze_review(monkeypatch):
    monkeypatch.setattr("api.operation_ledger.adapters.curve.config.active_courses", _fake_courses)
    a = CurveAdapter()
    r = a.freeze_review({"assignment_id": "10", "curve_type": "flat_bump"},
                         {"course_id": "101"},
                         {"assignment": {"name": "Quiz", "points_possible": 100},
                          "scored_students": [{"user_id": "1", "student_name": "Smith, John", "score": 80}]})
    assert r["course_name"] == "Algebra 1"
    assert r["assignment_name"] == "Quiz"
    assert r["student_count"] == 1

# ── Execute ─────────────────────────────────────────────────────────────

def test_execute_curves_assignment(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    def fake_assign(cid, aid):
        return {"id": 10, "name": "Quiz", "points_possible": 100}, None
    def fake_students(cid):
        return [{"id": 1, "sortable_name": "Smith, John"}], None
    def fake_subs(cid, aid):
        return [{"user_id": 1, "score": 80, "workflow_state": "graded"}], None
    monkeypatch.setattr("api.operation_ledger.adapters.curve._assignment", fake_assign)
    monkeypatch.setattr("api.operation_ledger.adapters.curve._course_students", fake_students)
    monkeypatch.setattr("api.operation_ledger.adapters.curve._assignment_submissions", fake_subs)
    def fake_send(method, path, payload, timeout=30):
        return {"ok": True}, None
    monkeypatch.setattr("api.operation_ledger.adapters.curve.canvas_client._canvas_send", fake_send)
    monkeypatch.setattr("api.operation_ledger.adapters.curve.config.active_courses", _fake_courses)
    # Mock curve event persistence
    monkeypatch.setattr("api.operation_ledger.adapters.curve._load_curve_events", lambda: [])
    monkeypatch.setattr("api.operation_ledger.adapters.curve._save_curve_events", lambda e: None)

    a = CurveAdapter()
    p = {"assignment_id": "10", "curve_type": "flat_bump", "settings": {"bump": 5}}
    op = models.new_operation(
        operation_id="op-cv-exec", kind="gradebook.curve",
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
    assert result["state"] == "applied"

def test_retry_selector():
    a = CurveAdapter()
    sel = a.retry_selector({"targets": [
        {"target_key": "a", "state": "applied"},
        {"target_key": "b", "state": "failed"},
    ]})
    assert sel[0]["target_key"] == "b"

def test_reversal_supported():
    a = CurveAdapter()
    d = a.reversal_descriptor({}, {"baseline": {"scored_students": [{"user_id": "1", "score": 80}]}})
    assert d["supported"] is True

def test_reversal_unsupported():
    a = CurveAdapter()
    d = a.reversal_descriptor({}, {"baseline": {"scored_students": []}})
    assert d["supported"] is False

def test_pipeline(monkeypatch):
    monkeypatch.setattr("api.operation_ledger.adapters.curve.config.active_courses", _fake_courses)
    a = registry.get_adapter("gradebook.curve")
    p = a.build_payload({"assignment_id": "10", "curve_type": "flat_bump", "settings": {"bump": 5}})
    assert p["assignment_id"] == "10"
    targets = a.verify_targets(p, [{"course_id": "101"}])
    assert len(targets) == 1
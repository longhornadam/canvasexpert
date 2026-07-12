"""Tests for roster membership adapter."""
import pytest
from api.operation_ledger import models, operations, paths, registry
from api.operation_ledger.adapters.roster_membership import MembershipAdapter

def _root(tmp_path, monkeypatch):
    root = tmp_path / "local-private"
    monkeypatch.setattr(paths, "private_root", lambda: root)
    return root

def _fake_courses():
    return [{"id": 101, "name": "Algebra 1"}]

def test_adapter_is_registered():
    a = registry.get_adapter("roster.membership")
    assert a is not None
    assert a.kind == "roster.membership"

def test_payload_build():
    a = MembershipAdapter()
    p = a.build_payload({"group_id": "10", "student_ids": ["1", "2"], "action": "add"})
    assert p["group_id"] == "10"
    assert "1" in p["student_ids"]
    assert p["action"] == "add"

def test_payload_build_remove():
    a = MembershipAdapter()
    p = a.build_payload({"group_id": "10", "student_ids": ["1"], "action": "remove"})
    assert p["action"] == "remove"

def test_payload_raises_no_group():
    a = MembershipAdapter()
    with pytest.raises(ValueError):
        a.build_payload({"student_ids": ["1"]})

def test_payload_raises_bad_action():
    a = MembershipAdapter()
    with pytest.raises(ValueError):
        a.build_payload({"group_id": "10", "student_ids": ["1"], "action": "rename"})

def test_verify_targets(monkeypatch):
    monkeypatch.setattr("api.operation_ledger.adapters.roster_membership.config.active_courses", _fake_courses)
    a = MembershipAdapter()
    t = a.verify_targets({"group_id": "10", "student_ids": ["1"]}, [{"course_id": "101"}])
    assert len(t) == 1

def test_freeze_review(monkeypatch):
    monkeypatch.setattr("api.operation_ledger.adapters.roster_membership.config.active_courses", _fake_courses)
    a = MembershipAdapter()
    r = a.freeze_review({"group_id": "10", "student_ids": ["1", "2"], "action": "add"},
                         {"course_id": "101"}, {})
    assert r["course_name"] == "Algebra 1"
    assert r["student_count"] == 2

def test_execute_adds_members(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    calls = []
    def fake_send(method, path, payload, timeout=30):
        calls.append((method, path))
        return {"id": 99, "user_id": payload.get("user_id")}, None
    monkeypatch.setattr("api.operation_ledger.adapters.roster_membership.canvas_client._canvas_send", fake_send)
    a = MembershipAdapter()
    p = {"group_id": "10", "student_ids": ["1", "2"], "action": "add"}
    op = models.new_operation(operation_id="op-mem-exec", kind="roster.membership",
        source_ref=None, source_digest=a.source_digest(p), normalized_payload=p,
        targets=[models.new_target(target_key=a.target_key(p, "42"),
            idempotency_key=a.idempotency_key(p, "42"), course_id="42")])
    operations.create_operation(op)
    target = op["targets"][0]
    baseline = {"existing_memberships": []}
    from api.operation_ledger.executor import ExecutionContext
    from api.operation_ledger import claims
    claim = claims.acquire_claim(target_key=target["target_key"], operation_id=op["operation_id"],
                                  payload_digest=models.sha256_dict(p))
    ctx = ExecutionContext(operation_id=op["operation_id"], target_key=target["target_key"], claim=claim)
    result = a.execute(p, target, baseline, claim, ctx)
    assert result["state"] == "applied"
    assert len(calls) == 2

def test_execute_removes_members(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    calls = []
    def fake_send(method, path, payload, timeout=30):
        calls.append((method, path))
        return {}, None
    monkeypatch.setattr("api.operation_ledger.adapters.roster_membership.canvas_client._canvas_send", fake_send)
    a = MembershipAdapter()
    p = {"group_id": "10", "student_ids": ["1"], "action": "remove"}
    op = models.new_operation(operation_id="op-mem-rem", kind="roster.membership",
        source_ref=None, source_digest=a.source_digest(p), normalized_payload=p,
        targets=[models.new_target(target_key=a.target_key(p, "42"),
            idempotency_key=a.idempotency_key(p, "42"), course_id="42")])
    operations.create_operation(op)
    target = op["targets"][0]
    baseline = {"existing_memberships": [{"user_id": 1, "id": 5}]}
    from api.operation_ledger.executor import ExecutionContext
    from api.operation_ledger import claims
    claim = claims.acquire_claim(target_key=target["target_key"], operation_id=op["operation_id"],
                                  payload_digest=models.sha256_dict(p))
    ctx = ExecutionContext(operation_id=op["operation_id"], target_key=target["target_key"], claim=claim)
    result = a.execute(p, target, baseline, claim, ctx)
    assert result["state"] == "applied"

def test_retry_selector():
    a = MembershipAdapter()
    sel = a.retry_selector({"targets": [{"target_key": "a", "state": "failed"}]})
    assert len(sel) == 1

def test_reversal_unsupported():
    a = MembershipAdapter()
    assert a.reversal_descriptor({}, {})["supported"] is False
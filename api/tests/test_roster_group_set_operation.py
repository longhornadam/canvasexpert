"""Tests for roster group-set adapter."""
import pytest
from api.operation_ledger import models, operations, paths, registry
from api.operation_ledger.adapters.roster_group_set import GroupSetAdapter

def _root(tmp_path, monkeypatch):
    root = tmp_path / "local-private"
    monkeypatch.setattr(paths, "private_root", lambda: root)
    return root

def _fake_courses():
    return [{"id": 101, "name": "Algebra 1"}]

def test_adapter_is_registered():
    a = registry.get_adapter("roster.group_set")
    assert a is not None
    assert a.kind == "roster.group_set"

def test_payload_build():
    a = GroupSetAdapter()
    p = a.build_payload({"name": "Table Groups", "group_names": ["Alpha", "Beta", "Gamma"]})
    assert p["name"] == "Table Groups"
    assert len(p["group_names"]) == 3

def test_payload_build_raises_no_name():
    a = GroupSetAdapter()
    with pytest.raises(ValueError, match="group set name"):
        a.build_payload({"group_names": ["A"]})

def test_payload_build_raises_no_groups():
    a = GroupSetAdapter()
    with pytest.raises(ValueError, match="group name"):
        a.build_payload({"name": "Test"})

def test_source_digest_deterministic():
    a = GroupSetAdapter()
    p = {"name": "Test", "group_names": ["A", "B"]}
    assert a.source_digest(p) == a.source_digest(p)

def test_verify_targets(monkeypatch):
    monkeypatch.setattr("api.operation_ledger.adapters.roster_group_set.config.active_courses", _fake_courses)
    a = GroupSetAdapter()
    t = a.verify_targets({"name": "T", "group_names": ["A"]}, [{"course_id": "101"}])
    assert len(t) == 1

def test_verify_rejects_unknown(monkeypatch):
    monkeypatch.setattr("api.operation_ledger.adapters.roster_group_set.config.active_courses", _fake_courses)
    a = GroupSetAdapter()
    with pytest.raises(ValueError, match="not in active"):
        a.verify_targets({}, [{"course_id": "999"}])

def test_freeze_review(monkeypatch):
    monkeypatch.setattr("api.operation_ledger.adapters.roster_group_set.config.active_courses", _fake_courses)
    a = GroupSetAdapter()
    r = a.freeze_review({"name": "Tables", "group_names": ["A", "B"]}, {"course_id": "101"}, {})
    assert r["course_name"] == "Algebra 1"
    assert r["group_count"] == 2

def test_reversal_unsupported():
    a = GroupSetAdapter()
    assert a.reversal_descriptor({}, {})["supported"] is False

def test_retry_selector():
    a = GroupSetAdapter()
    sel = a.retry_selector({"targets": [{"target_key": "a", "state": "failed"}]})
    assert len(sel) == 1

def test_execute_creates_groups(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    calls = []
    def fake_send(method, path, payload, timeout=30):
        calls.append((method, path))
        if "group_categories" in path:
            return {"id": 55, "name": payload.get("name")}, None
        if "groups" in path:
            return {"id": 99, "name": payload.get("name")}, None
        return None, None
    monkeypatch.setattr("api.operation_ledger.adapters.roster_group_set.canvas_client._canvas_send", fake_send)
    monkeypatch.setattr("api.operation_ledger.adapters.roster_group_set.config.active_courses", _fake_courses)

    a = GroupSetAdapter()
    p = {"name": "Tables", "group_names": ["Alpha", "Beta"]}
    op = models.new_operation(operation_id="op-gs-exec", kind="roster.group_set",
        source_ref=None, source_digest=a.source_digest(p), normalized_payload=p,
        targets=[models.new_target(target_key=a.target_key(p, "42"),
            idempotency_key=a.idempotency_key(p, "42"), course_id="42")])
    operations.create_operation(op)
    target = op["targets"][0]
    baseline = {"existing_categories": []}
    from api.operation_ledger.executor import ExecutionContext
    from api.operation_ledger import claims
    claim = claims.acquire_claim(target_key=target["target_key"], operation_id=op["operation_id"],
                                  payload_digest=models.sha256_dict(p))
    ctx = ExecutionContext(operation_id=op["operation_id"], target_key=target["target_key"], claim=claim)
    result = a.execute(p, target, baseline, claim, ctx)
    assert result["state"] == "applied"
    assert len(calls) == 3  # 1 category + 2 groups

def test_execute_handles_error(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    def fail_send(method, path, payload, timeout=30):
        return None, "HTTP 400"
    monkeypatch.setattr("api.operation_ledger.adapters.roster_group_set.canvas_client._canvas_send", fail_send)
    a = GroupSetAdapter()
    p = {"name": "Tables", "group_names": ["Alpha"]}
    op = models.new_operation(operation_id="op-gs-fail", kind="roster.group_set",
        source_ref=None, source_digest=a.source_digest(p), normalized_payload=p,
        targets=[models.new_target(target_key=a.target_key(p, "42"),
            idempotency_key=a.idempotency_key(p, "42"), course_id="42")])
    operations.create_operation(op)
    target = op["targets"][0]
    baseline = {"existing_categories": []}
    from api.operation_ledger.executor import ExecutionContext
    from api.operation_ledger import claims
    claim = claims.acquire_claim(target_key=target["target_key"], operation_id=op["operation_id"],
                                  payload_digest=models.sha256_dict(p))
    ctx = ExecutionContext(operation_id=op["operation_id"], target_key=target["target_key"], claim=claim)
    result = a.execute(p, target, baseline, claim, ctx)
    assert result["state"] == "failed"
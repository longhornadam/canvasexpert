"""Tests for the late-policy operation adapter.

Patterns follow test_assignment_operation.py: private-root redirection,
mock Canvas API, and adapter lifecycle verification.
"""
import pytest

from api.operation_ledger import (
    models, operations, paths, registry,
)
from api.operation_ledger.adapters.late_policy import (
    LatePolicyAdapter,
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


# ── Canvas mock helpers ──────────────────────────────────────────────────

def _existing_policy():
    return {
        "late_policy": {
            "late_submission_deduction_enabled": True,
            "late_submission_deduction": 10.0,
            "late_submission_interval": "day",
            "late_submission_minimum_percent_enabled": True,
            "late_submission_minimum_percent": 50.0,
            "missing_submission_deduction_enabled": False,
            "missing_submission_deduction": 100.0,
        }
    }


def _make_canvas_get(existing=False):
    def _get(path, params=None, timeout=20):
        if "late_policy" in path:
            if existing:
                return _existing_policy(), None
            return {}, "HTTP 404: not found"
        return None, None
    return _get


def _fake_canvas_send(method, path, payload, timeout=30):
    if "late_policy" in path:
        return {"late_policy": payload.get("late_policy", {})}, None
    return None, None


# ── Protocol conformance ─────────────────────────────────────────────────

def test_adapter_is_registered():
    adapter = registry.get_adapter("gradebook.late_policy")
    assert adapter is not None
    assert adapter.kind == "gradebook.late_policy"


def test_payload_build_minimal():
    adapter = LatePolicyAdapter()
    payload = adapter.build_payload({
        "late_submission_deduction_enabled": True,
        "late_submission_deduction": 10,
    })
    assert payload["settings"]["late_submission_deduction_enabled"] is True
    assert payload["settings"]["late_submission_deduction"] == 10.0


def test_payload_build_full():
    adapter = LatePolicyAdapter()
    payload = adapter.build_payload({
        "late_submission_deduction_enabled": True,
        "late_submission_deduction": 10,
        "late_submission_interval": "hour",
        "late_submission_minimum_percent_enabled": True,
        "late_submission_minimum_percent": 50,
        "missing_submission_deduction_enabled": True,
        "missing_submission_deduction": 30,
    })
    s = payload["settings"]
    assert s["late_submission_deduction"] == 10.0
    assert s["late_submission_interval"] == "hour"
    assert s["missing_submission_deduction"] == 30.0


def test_payload_build_raises_on_invalid_interval():
    adapter = LatePolicyAdapter()
    with pytest.raises(ValueError, match="late_submission_interval"):
        adapter.build_payload({"late_submission_interval": "week"})


def test_payload_build_raises_on_out_of_range():
    adapter = LatePolicyAdapter()
    with pytest.raises(ValueError, match="must be between 0 and 100"):
        adapter.build_payload({"late_submission_deduction": 150})


def test_payload_build_raises_on_empty():
    adapter = LatePolicyAdapter()
    with pytest.raises(ValueError, match="at least one policy setting"):
        adapter.build_payload({})


def test_source_digest_is_deterministic():
    adapter = LatePolicyAdapter()
    payload = {"settings": {"late_submission_deduction": 10}}
    d1 = adapter.source_digest(payload)
    d2 = adapter.source_digest(payload)
    assert d1 == d2


# ── Target verification ─────────────────────────────────────────────────

def test_verify_targets_valid(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.late_policy.config.active_courses",
        _fake_courses,
    )
    adapter = LatePolicyAdapter()
    payload = {"settings": {"late_submission_deduction": 10}}
    targets = adapter.verify_targets(payload, [{"course_id": "101"}, {"course_id": "202"}])
    assert len(targets) == 2


def test_verify_targets_rejects_unknown_course(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.late_policy.config.active_courses",
        _fake_courses,
    )
    adapter = LatePolicyAdapter()
    payload = {"settings": {"late_submission_deduction": 10}}
    with pytest.raises(ValueError, match="not in active courses"):
        adapter.verify_targets(payload, [{"course_id": "999"}])


# ── Baseline / drift ────────────────────────────────────────────────────

def test_capture_baseline_no_existing(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.late_policy.canvas_client._canvas_get",
        _make_canvas_get(existing=False),
    )
    adapter = LatePolicyAdapter()
    baseline = adapter.capture_baseline({}, {"course_id": "42"})
    assert baseline["policy"] is None
    assert baseline["snapshot_complete"] is False


def test_capture_baseline_with_existing(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.late_policy.canvas_client._canvas_get",
        _make_canvas_get(existing=True),
    )
    adapter = LatePolicyAdapter()
    baseline = adapter.capture_baseline({}, {"course_id": "42"})
    assert baseline["policy"] is not None
    assert baseline["snapshot_complete"] is True
    assert baseline["policy"]["late_submission_deduction"] == 10.0


def test_drift_never_detected_for_late_policy():
    adapter = LatePolicyAdapter()
    # Late policy is idempotent — setting same values again is fine
    assert adapter.check_drift({}, {}, {"policy": {}}) is False
    assert adapter.check_drift({}, {}, {"canvas_error": "timeout"}) is True


# ── Freeze review ───────────────────────────────────────────────────────

def test_freeze_review(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.late_policy.config.active_courses",
        _fake_courses,
    )
    adapter = LatePolicyAdapter()
    payload = {"settings": {"late_submission_deduction": 10}}
    review = adapter.freeze_review(payload, {"course_id": "101"},
                                    {"policy": None, "snapshot_complete": False})
    assert review["course_name"] == "Algebra 1"
    assert review["settings"]["late_submission_deduction"] == 10
    assert review["baseline_snapshot_complete"] is False


# ── Execute ──────────────────────────────────────────────────────────────

def test_execute_creates_policy(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "api.operation_ledger.adapters.late_policy.canvas_client._canvas_send",
        _fake_canvas_send,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.late_policy.canvas_client._canvas_get",
        _make_canvas_get(existing=False),
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.late_policy.config.active_courses",
        _fake_courses,
    )

    adapter = LatePolicyAdapter()
    payload = {"settings": {"late_submission_deduction": 10,
                            "late_submission_deduction_enabled": True}}

    op = models.new_operation(
        operation_id="op-lp-execute",
        kind="gradebook.late_policy",
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


def test_execute_updates_existing_policy(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "api.operation_ledger.adapters.late_policy.canvas_client._canvas_send",
        _fake_canvas_send,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.late_policy.canvas_client._canvas_get",
        _make_canvas_get(existing=True),
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.late_policy.config.active_courses",
        _fake_courses,
    )

    adapter = LatePolicyAdapter()
    payload = {"settings": {"late_submission_deduction": 20,
                            "late_submission_deduction_enabled": True}}

    op = models.new_operation(
        operation_id="op-lp-update",
        kind="gradebook.late_policy",
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


def test_execute_handles_canvas_error(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)

    def fail_send(method, path, payload, timeout=30):
        return None, "HTTP 400: bad request"

    monkeypatch.setattr(
        "api.operation_ledger.adapters.late_policy.canvas_client._canvas_send",
        fail_send,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.late_policy.canvas_client._canvas_get",
        _make_canvas_get(existing=False),
    )

    adapter = LatePolicyAdapter()
    payload = {"settings": {"late_submission_deduction": 10}}

    op = models.new_operation(
        operation_id="op-lp-fail",
        kind="gradebook.late_policy",
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

def test_reconcile_finds_policy(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.late_policy.canvas_client._canvas_get",
        lambda path, params=None, timeout=20: (
            _existing_policy(), None
        ) if "late_policy" in path else (None, None),
    )
    adapter = LatePolicyAdapter()
    result = adapter.reconcile(
        {"settings": {"late_submission_deduction": 10,
                      "late_submission_deduction_enabled": True}},
        {"course_id": "42"},
        {},
    )
    assert result["state"] == "applied"


def test_reconcile_no_policy(monkeypatch):
    monkeypatch.setattr(
        "api.operation_ledger.adapters.late_policy.canvas_client._canvas_get",
        _make_canvas_get(existing=False),
    )
    adapter = LatePolicyAdapter()
    result = adapter.reconcile(
        {"settings": {"late_submission_deduction": 10}},
        {"course_id": "42"},
        {},
    )
    # No outbound marker, no policy → pending
    assert result["state"] == "pending"


# ── Retry / reversal ────────────────────────────────────────────────────

def test_retry_selector_picks_unresolved():
    adapter = LatePolicyAdapter()
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


def test_reversal_descriptor_supported():
    adapter = LatePolicyAdapter()
    baseline = {"policy": {"late_submission_deduction": 5}, "snapshot_complete": True}
    desc = adapter.reversal_descriptor(
        {"settings": {"late_submission_deduction": 10}},
        {"baseline": baseline},
    )
    assert desc["supported"] is True
    assert desc["method"] == "restore_snapshot"
    assert desc["snapshot"]["late_submission_deduction"] == 5


def test_reversal_descriptor_unsupported():
    adapter = LatePolicyAdapter()
    baseline = {"policy": None, "snapshot_complete": False}
    desc = adapter.reversal_descriptor(
        {"settings": {"late_submission_deduction": 10}},
        {"baseline": baseline},
    )
    assert desc["supported"] is False


# ── Full pipeline ────────────────────────────────────────────────────────

def test_pipeline_with_mocks(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "api.operation_ledger.adapters.late_policy.config.active_courses",
        _fake_courses,
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.late_policy.canvas_client._canvas_get",
        _make_canvas_get(existing=False),
    )
    monkeypatch.setattr(
        "api.operation_ledger.adapters.late_policy.canvas_client._canvas_send",
        _fake_canvas_send,
    )

    adapter = registry.get_adapter("gradebook.late_policy")
    assert adapter is not None

    # 1. Build payload
    payload = adapter.build_payload({
        "late_submission_deduction_enabled": True,
        "late_submission_deduction": 10,
        "late_submission_minimum_percent_enabled": True,
        "late_submission_minimum_percent": 50,
    })
    assert payload["settings"]["late_submission_deduction"] == 10.0

    # 2. Verify targets
    targets = adapter.verify_targets(payload, [
        {"course_id": "101"},
    ])
    assert len(targets) == 1

    # 3. Capture baseline
    bl = adapter.capture_baseline(payload, targets[0])
    assert bl["policy"] is None

    # 4. Freeze review
    r = adapter.freeze_review(payload, targets[0], bl)
    assert r["course_name"] == "Algebra 1"
    assert r["settings"]["late_submission_deduction"] == 10.0
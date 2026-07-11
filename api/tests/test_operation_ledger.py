"""Operation-ledger schema, atomicity, concurrency, and corruption tests.

Mirrors the patterns from test_receipt_store.py: path redirect via monkeypatch,
atomic-failure preservation, concurrent claim acquisition, corrupt-file quarantine,
lease expiry detection, and stale-claim recovery.
"""
import copy
import json
import multiprocessing
import os
import threading
import time

import pytest

from api.operation_ledger import claims, executor, models, operations, paths, storage


def _root(tmp_path, monkeypatch):
    root = tmp_path / "local-private"
    monkeypatch.setattr(paths, "private_root", lambda: root)
    return root


def _make_operation(operation_id="op-test1", targets=None):
    """Build a minimal valid operation for testing."""
    if targets is None:
        targets = [models.new_target(
            target_key="tk-1", idempotency_key="ik-1", course_id="101")]
    return models.new_operation(
        operation_id=operation_id,
        kind="content.page",
        source_ref={"type": "workspace_relative", "value": "Pages/test.pageforge.json"},
        source_digest="abc123",
        normalized_payload={"title": "Test", "body": "<p>Hi</p>", "published": False},
        targets=targets,
    )


def _spawn_claim_worker(root, barrier, result_queue):
    """Top-level worker for portable spawn-based claim contention evidence."""
    os.environ["LOCALAPPDATA"] = root
    from api.operation_ledger import claims
    barrier.wait()
    try:
        claim = claims.acquire_claim(
            target_key="spawn-target",
            operation_id="op-spawn",
            payload_digest="spawn-digest",
        )
        result_queue.put(("acquired", claim["claim_id"]))
    except claims.ClaimConflictError:
        result_queue.put(("conflicted", None))


# ── Operation round-trip ────────────────────────────────────────────────

def test_operation_round_trip_preserves_all_fields(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    op = _make_operation()
    created = operations.create_operation(op)
    assert created["operation_id"] == "op-test1"
    assert created["kind"] == "content.page"
    assert created["status"] == "prepared"
    assert created["source_digest"] == "abc123"
    assert len(created["targets"]) == 1

    fetched = operations.get_operation("op-test1")
    assert fetched["operation_id"] == "op-test1"
    assert fetched["normalized_payload"]["title"] == "Test"
    assert fetched["targets"][0]["target_key"] == "tk-1"


def test_list_operations_returns_all(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    operations.create_operation(_make_operation("op-a"))
    operations.create_operation(_make_operation("op-b"))
    ops = operations.list_operations()
    assert len(ops) == 2
    assert {o["operation_id"] for o in ops} == {"op-a", "op-b"}


def test_list_operations_pii_minimized(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    operations.create_operation(_make_operation("op-pii"))
    minimized = operations.list_operations_pii_minimized()
    assert len(minimized) == 1
    m = minimized[0]
    assert m["operation_id"] == "op-pii"
    assert m["kind"] == "content.page"
    assert m["status"] == "prepared"
    assert m["target_count"] == 1
    # No course IDs, no payload, no target details
    text = json.dumps(minimized)
    assert "101" not in text  # course_id should not appear
    assert "normalized_payload" not in text
    assert "targets" not in text


# ── Target state transitions ────────────────────────────────────────────

def test_valid_target_state_transitions():
    assert models.validate_target_state_transition("pending", "claimed")
    assert models.validate_target_state_transition("claimed", "applied")
    assert models.validate_target_state_transition("claimed", "sent_unknown")
    assert models.validate_target_state_transition("claimed", "failed")
    assert models.validate_target_state_transition("sent_unknown", "applied")
    assert models.validate_target_state_transition("sent_unknown", "pending")


def test_invalid_target_state_transitions():
    assert not models.validate_target_state_transition("pending", "applied")
    assert not models.validate_target_state_transition("applied", "pending")
    assert not models.validate_target_state_transition("skipped", "pending")
    assert not models.validate_target_state_transition("applied", "failed")


def test_operation_status_transitions():
    assert models.validate_operation_status_transition("working", "prepared")
    assert models.validate_operation_status_transition("prepared", "reviewed")
    assert models.validate_operation_status_transition("reviewed", "applying")
    assert models.validate_operation_status_transition("applying", "applied")
    assert models.validate_operation_status_transition("attention", "applying")
    assert not models.validate_operation_status_transition("applied", "applying")
    assert not models.validate_operation_status_transition("prepared", "applied")


# ── Invalid kind rejected ───────────────────────────────────────────────

def test_unknown_kind_rejected():
    from api.operation_ledger import registry
    with pytest.raises(ValueError, match="unknown operation kind"):
        registry.get_adapter("content.nonexistent")


# ── Concurrent claim acquisition ────────────────────────────────────────

def test_concurrent_claim_acquisition(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    # Create an operation with a target
    operations.create_operation(_make_operation("op-concurrent"))

    results = {"acquired": [], "conflicted": []}

    def try_acquire(index):
        try:
            claim = claims.acquire_claim(
                target_key="tk-1",
                operation_id="op-concurrent",
                payload_digest="digest-1",
            )
            results["acquired"].append(index)
        except claims.ClaimConflictError:
            results["conflicted"].append(index)

    threads = [threading.Thread(target=try_acquire, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly one thread should acquire the claim
    assert len(results["acquired"]) == 1
    assert len(results["conflicted"]) == 7


def test_spawned_processes_race_for_one_claim(tmp_path, monkeypatch):
    """The shared adjacent lock serializes claims across spawned processes."""
    root = _root(tmp_path, monkeypatch)
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(2)
    result_queue = ctx.Queue()
    processes = [ctx.Process(target=_spawn_claim_worker,
                             args=(str(root), barrier, result_queue)) for _ in range(2)]
    for process in processes:
        process.start()
    results = [result_queue.get(timeout=20) for _ in processes]
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0
    assert [result[0] for result in results].count("acquired") == 1
    assert [result[0] for result in results].count("conflicted") == 1


# ── Atomic failure preserves previous document ──────────────────────────

def test_atomic_failure_preserves_previous_operations(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    operations.create_operation(_make_operation("op-before"))
    before = paths.operations_file().read_text(encoding="utf-8")

    monkeypatch.setattr(storage.os, "replace",
                        lambda *_: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        operations.create_operation(_make_operation("op-after"))

    assert paths.operations_file().read_text(encoding="utf-8") == before


# ── Corrupt operations file quarantined ─────────────────────────────────

def test_corrupt_operations_file_quarantined(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    path = paths.operations_file()
    path.parent.mkdir(parents=True)
    path.write_text("not json", encoding="utf-8")
    assert operations.list_operations() == []
    assert list((root / "quarantine").glob("*.corrupt"))


def test_unknown_version_operations_quarantined(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    path = paths.operations_file()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 99, "operations": []}), encoding="utf-8")
    assert operations.list_operations() == []
    assert list((root / "quarantine").glob("*.corrupt"))


# ── Lease expiry detection ──────────────────────────────────────────────

def test_lease_expiry_detection(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    # Create a claim with an expired lease
    claim = models.new_claim(
        claim_id="tk-1:attempt-1",
        target_key="tk-1",
        operation_id="op-lease",
        attempt_id="attempt-1",
        owner_pid=99999,  # different PID
        owner_started_at="2020-01-01T00:00:00+00:00",
        payload_digest="digest",
    )
    # Manually expire the lease
    claim["lease_expires_at"] = "2020-01-01T00:00:01+00:00"
    storage.upsert_claim(claim)

    expired = claims.detect_expired_claims()
    assert len(expired) == 1
    assert expired[0]["claim_id"] == "tk-1:attempt-1"
    assert expired[0]["state"] == "expired"


def test_active_claim_not_expired(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    claim = models.new_claim(
        claim_id="tk-active:attempt-1",
        target_key="tk-active",
        operation_id="op-active",
        attempt_id="attempt-1",
        owner_pid=99999,
        owner_started_at="2020-01-01T00:00:00+00:00",
        payload_digest="digest",
    )
    # Lease is in the future (5 minutes from now by default)
    storage.upsert_claim(claim)

    expired = claims.detect_expired_claims()
    # A different PID is not evidence of death while the lease is valid.
    assert expired == []


def test_expired_claim_requires_recovery_before_acquisition(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    claim = models.new_claim(
        claim_id="tk-expired:attempt-old", target_key="tk-expired",
        operation_id="op-expired", attempt_id="attempt-old", owner_pid=1,
        owner_started_at="2020-01-01T00:00:00+00:00", payload_digest="digest")
    claim["lease_expires_at"] = "2020-01-01T00:00:01+00:00"
    storage.upsert_claim(claim)
    with pytest.raises(claims.ClaimConflictError):
        claims.acquire_claim(target_key="tk-expired", operation_id="op-expired",
                             payload_digest="new-digest")
    assert storage.find_claim(claim["claim_id"])["state"] == "claimed"
    claims.detect_expired_claims()
    with pytest.raises(claims.ClaimConflictError):
        claims.acquire_claim(target_key="tk-expired", operation_id="op-expired",
                             payload_digest="new-digest")
    claims.mark_reconciled(claim["claim_id"])
    replacement = claims.acquire_claim(target_key="tk-expired", operation_id="op-expired",
                                       payload_digest="new-digest")
    assert replacement["state"] == "claimed"


def test_concurrent_operation_target_mutations_preserve_updates(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    targets = [models.new_target(target_key=f"tk-{i}", idempotency_key=f"ik-{i}",
                                 course_id=str(i)) for i in range(2)]
    operations.create_operation(_make_operation("op-mutations", targets))

    def update(index):
        operations.update_target("op-mutations", f"tk-{index}",
                                 lambda target: {**target, "error_code": f"error-{index}"})

    threads = [threading.Thread(target=update, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    stored = operations.get_operation("op-mutations")
    assert {target["error_code"] for target in stored["targets"]} == {"error-0", "error-1"}


def test_stale_worker_cannot_checkpoint_after_recovery_fencing(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    operation = _make_operation("op-fence")
    operations.create_operation(operation)
    target = operation["targets"][0]
    claim = claims.acquire_claim(target_key=target["target_key"],
                                 operation_id=operation["operation_id"],
                                 payload_digest="digest")
    executor._update_target_claimed(operation["operation_id"], target["target_key"],
                                     claim, {"existing_page": None})
    context = executor.ExecutionContext(operation_id=operation["operation_id"],
                                        target_key=target["target_key"], claim=claim)
    stored_claim = storage.find_claim(claim["claim_id"])
    stored_claim["lease_expires_at"] = "2020-01-01T00:00:01+00:00"
    storage.upsert_claim(stored_claim)
    claims.detect_expired_claims()
    before = operations.get_operation(operation["operation_id"])
    with pytest.raises(executor.LostClaimError):
        context.before_send("create_page", "digest")
    after = operations.get_operation(operation["operation_id"])
    assert after["targets"] == before["targets"]


# ── Stale claim recovery ────────────────────────────────────────────────

def test_stale_claim_marked_expired_on_recovery(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    # Create a stale claim (expired lease)
    claim = models.new_claim(
        claim_id="tk-stale:attempt-old",
        target_key="tk-stale",
        operation_id="op-stale",
        attempt_id="attempt-old",
        owner_pid=99999,
        owner_started_at="2020-01-01T00:00:00+00:00",
        payload_digest="digest",
    )
    claim["lease_expires_at"] = "2020-01-01T00:00:01+00:00"
    storage.upsert_claim(claim)

    expired = claims.detect_expired_claims()
    assert any(c["claim_id"] == "tk-stale:attempt-old" for c in expired)


# ── Compute operation status from targets ───────────────────────────────

def test_compute_status_all_applied():
    targets = [{"state": "applied"}, {"state": "applied"}]
    assert models.compute_operation_status(targets) == "applied"


def test_compute_status_mixed_applied_skipped():
    targets = [{"state": "applied"}, {"state": "skipped"}]
    assert models.compute_operation_status(targets) == "applied"


def test_compute_status_partial():
    targets = [{"state": "applied"}, {"state": "failed"}]
    assert models.compute_operation_status(targets) == "partial"


def test_compute_status_attention():
    targets = [{"state": "applied"}, {"state": "sent_unknown"}]
    assert models.compute_operation_status(targets) == "attention"


def test_compute_status_all_failed():
    targets = [{"state": "failed"}, {"state": "failed"}]
    assert models.compute_operation_status(targets) == "failed"


# ── Registry ────────────────────────────────────────────────────────────

def test_page_adapter_registered():
    from api.operation_ledger import registry
    assert registry.is_registered("content.page")
    adapter = registry.get_adapter("content.page")
    assert adapter.kind == "content.page"


def test_known_kinds_includes_page():
    from api.operation_ledger import registry
    assert "content.page" in registry.known_kinds()

"""Curve-event storage relocation and migration tests."""

import hashlib
import json
import os
import threading

import pytest

from api.operation_ledger import paths, storage
from api.webui import gradebook_service as service


@pytest.fixture
def isolated_curve_storage(tmp_path, monkeypatch):
    private_root = tmp_path / "private"
    legacy_path = tmp_path / "legacy" / "curve_events.json"
    monkeypatch.setattr(paths, "private_root", lambda: private_root)
    monkeypatch.setattr(service, "CURVE_EVENTS_PATH", str(legacy_path))
    return private_root, legacy_path


def _events():
    return [{
        "id": "curve-opaque-1",
        "course_id": "course-opaque-1",
        "assignment_id": "assignment-opaque-1",
        "assignment_name": "Synthetic Assignment",
        "curve_type": "flat_bump",
        "curve_settings": {"bump": 1},
        "applied_at": "2026-07-11T12:00:00",
        "reverted": False,
        "students": [{"user_id": "student-opaque-1", "changed": True}],
    }]


def _write_legacy(path, events, raw=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw if raw is not None else json.dumps(
        {"events": events}, indent=2, ensure_ascii=False).encode("utf-8"))


def _error(call):
    with pytest.raises(service.CurveEventStorageError) as raised:
        call()
    assert str(raised.value) == service.CURVE_EVENT_STORAGE_ERROR
    return raised.value


def test_new_only_read_and_write(isolated_curve_storage):
    private_root, legacy_path = isolated_curve_storage
    events = _events()

    service._save_curve_events(events)

    assert service._load_curve_events() == events
    assert not legacy_path.exists()
    assert json.loads(paths.curve_events_file().read_text(encoding="utf-8")) == {
        "version": 1, "events": events,
    }
    assert private_root.exists()


def test_legacy_only_migration_preserves_values_and_verifies_backup(isolated_curve_storage):
    private_root, legacy_path = isolated_curve_storage
    events = _events()
    raw = b'{"events": [{"id": "curve-opaque-1", "course_id": "course-opaque-1", "assignment_id": "assignment-opaque-1", "applied_at": "2026-07-11T12:00:00", "reverted": false, "students": [{"user_id": "student-opaque-1", "changed": true}], "extra": [1, "opaque"]}]}'
    _write_legacy(legacy_path, events, raw=raw)

    assert service._load_curve_events() == json.loads(raw)["events"]
    backups = list((private_root / "migration-backups").glob("curve_events.*.json"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == raw
    assert hashlib.sha256(backups[0].read_bytes()).hexdigest()[:16] == hashlib.sha256(raw).hexdigest()[:16]
    assert not legacy_path.exists()
    assert json.loads(paths.curve_events_file().read_text(encoding="utf-8"))["events"] == json.loads(raw)["events"]


def test_new_wins_and_leaves_legacy_untouched(isolated_curve_storage):
    private_root, legacy_path = isolated_curve_storage
    live_events = _events()
    legacy_raw = b"not json and must not be read"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_bytes(legacy_raw)
    storage.atomic_write_json(paths.curve_events_file(), {"version": 1, "events": live_events})

    assert service._load_curve_events() == live_events
    assert legacy_path.read_bytes() == legacy_raw
    assert list((private_root / "migration-backups").glob("*")) == []


@pytest.mark.parametrize("raw", [
    b"not json",
    b"[]",
    b"{}",
    b'{"events": {}}',
    b'{"events": [{"id": "only-id"}]}',
])
def test_malformed_legacy_is_redacted_and_preserved(isolated_curve_storage, raw):
    _, legacy_path = isolated_curve_storage
    _write_legacy(legacy_path, [], raw=raw)

    _error(service._load_curve_events)

    assert legacy_path.read_bytes() == raw
    assert not paths.curve_events_file().exists()


def test_checksum_mismatch_preserves_source_and_removes_new_record(isolated_curve_storage, monkeypatch):
    _, legacy_path = isolated_curve_storage
    events = _events()
    _write_legacy(legacy_path, events)
    original = storage.atomic_write_bytes

    def corrupt_backup(path, payload):
        original(path, payload)
        if os.path.basename(str(path)).startswith("curve_events."):
            path.write_bytes(payload + b"corruption")

    monkeypatch.setattr(storage, "atomic_write_bytes", corrupt_backup)
    _error(service._load_curve_events)

    assert legacy_path.exists()
    assert not paths.curve_events_file().exists()


def test_backup_write_failure_preserves_source(isolated_curve_storage, monkeypatch):
    _, legacy_path = isolated_curve_storage
    _write_legacy(legacy_path, _events())
    monkeypatch.setattr(storage, "atomic_write_bytes", lambda *_: (_ for _ in ()).throw(OSError("private failure")))

    _error(service._load_curve_events)

    assert legacy_path.exists()
    assert not paths.curve_events_file().exists()


def test_new_write_failure_preserves_source(isolated_curve_storage, monkeypatch):
    _, legacy_path = isolated_curve_storage
    _write_legacy(legacy_path, _events())
    monkeypatch.setattr(storage, "atomic_write_json", lambda *_: (_ for _ in ()).throw(OSError("private failure")))

    _error(service._load_curve_events)

    assert legacy_path.exists()
    assert not paths.curve_events_file().exists()


def test_reread_mismatch_preserves_source_and_removes_new_record(isolated_curve_storage, monkeypatch):
    _, legacy_path = isolated_curve_storage
    _write_legacy(legacy_path, _events())
    monkeypatch.setattr(service, "_read_versioned_curve_events", lambda _: [])

    _error(service._load_curve_events)

    assert legacy_path.exists()
    assert not paths.curve_events_file().exists()


def test_delete_failure_preserves_source_and_removes_new_record(isolated_curve_storage, monkeypatch):
    _, legacy_path = isolated_curve_storage
    _write_legacy(legacy_path, _events())
    original_unlink = service.os.unlink

    def fail_legacy_delete(path):
        if os.path.abspath(str(path)) == os.path.abspath(str(legacy_path)):
            raise OSError("legacy delete failure")
        return original_unlink(path)

    monkeypatch.setattr(service.os, "unlink", fail_legacy_delete)
    _error(service._load_curve_events)

    assert legacy_path.exists()
    assert not paths.curve_events_file().exists()


def test_concurrent_first_access_migrates_once(isolated_curve_storage):
    private_root, legacy_path = isolated_curve_storage
    events = _events()
    _write_legacy(legacy_path, events)
    results, failures = [], []

    def load():
        try:
            results.append(service._load_curve_events())
        except Exception as exc:  # pragma: no cover - assertion below reports it
            failures.append(exc)

    threads = [threading.Thread(target=load) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    assert results == [events] * 8
    assert len(list((private_root / "migration-backups").glob("curve_events.*.json"))) == 1
    assert json.loads(paths.curve_events_file().read_text(encoding="utf-8"))["events"] == events
    assert not legacy_path.exists()

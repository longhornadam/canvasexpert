import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from api.work_registry import storage, suppressions
from api.work_registry.models import (
    RegistryValidationError,
    material_version,
    stable_fingerprint,
    validate_job,
    validate_registry_document,
    validate_source_ref,
    validate_suppressions,
)


def _job(status="attention", origin="detected"):
    source = {"type": "canvas_finding", "value": "finding-1"}
    courses = ["course-1"]
    assignment = "assignment-1"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "job_id": "job-1",
        "fingerprint": stable_fingerprint("grade.debt", source, courses, assignment),
        "material_version": material_version({"kind": "grade.debt", "counts": {"total": 1, "pending": 1, "affected": 0}}),
        "origin": origin,
        "kind": "grade.debt",
        "status": status,
        "title": "Work item",
        "course_ids": courses,
        "focused_course_id": "course-1",
        "assignment_id": assignment,
        "resumable_url": "/powergrader",
        "source_ref": source,
        "counts": {"total": 1, "pending": 1, "affected": 0},
        "attention_reason": "Work needs attention" if status == "attention" else "",
        "created_at": now,
        "updated_at": now,
        "completed_at": "",
    }


def _registry(job=None):
    return {"version": 1, "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "jobs": [job or _job()]}


def test_strict_models_reject_unknown_values_and_private_facts():
    job = _job()
    validate_job(job)
    with pytest.raises(RegistryValidationError):
        validate_job({**job, "status": "running"})
    with pytest.raises(RegistryValidationError):
        validate_job({**job, "resumable_url": "https://example.invalid/work"})
    with pytest.raises(RegistryValidationError):
        validate_job({**job, "focused_course_id": "course-2"})
    with pytest.raises(RegistryValidationError):
        validate_source_ref({"type": "canvas_finding", "value": r"C:\private\record.json"})
    with pytest.raises(RegistryValidationError):
        material_version({"student_id": "synthetic-id"})
    with pytest.raises(RegistryValidationError):
        validate_registry_document({"version": 2, "updated_at": _registry()["updated_at"], "jobs": []})
    with pytest.raises(RegistryValidationError):
        validate_suppressions({"version": 1, "items": [{"fingerprint": "x"}]})


def test_fingerprints_are_stable_and_material_changes_digest():
    source = {"type": "powergrader_session", "value": "session-1"}
    first = stable_fingerprint("grade.powergrader", source, ["course-1"], "assignment-1")
    reordered = stable_fingerprint("grade.powergrader", source, ["course-1"], "assignment-1")
    assert first == reordered
    assert first == first.lower() and len(first) == 64
    assert material_version({"status": "in_progress", "counts": {"total": 1, "pending": 1, "affected": 0}}) != material_version({"status": "completed", "counts": {"total": 1, "pending": 0, "affected": 0}})


def test_storage_empty_round_trip_atomic_replace_and_no_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.workspace, "workspace_root", lambda: str(tmp_path / "workspace"))
    assert storage.read_registry()["jobs"] == []
    assert storage.write_registry(_registry())["ok"] is True
    path = tmp_path / "workspace" / "_system" / "workbench" / "registry.v1.json"
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1
    assert not list(path.parent.glob("*.tmp"))

    monkeypatch.setattr(storage.workspace, "workspace_root", lambda: None)
    assert storage.read_registry()["jobs"] == []
    assert storage.write_registry(_registry()) == {"ok": False, "error": "workspace_not_configured"}
    assert not (Path.cwd() / "_system").exists()


def test_storage_quarantines_corrupt_document_and_concurrent_writes(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    monkeypatch.setattr(storage.workspace, "workspace_root", lambda: str(root))
    path = root / "_system" / "workbench" / "registry.v1.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not-json", encoding="utf-8")
    assert storage.read_registry()["jobs"] == []
    assert list((path.parent / "quarantine").glob("registry.v1.json.*.corrupt"))

    errors = []
    def write():
        try:
            storage.write_registry(_registry())
        except Exception as exc:  # pragma: no cover - diagnostic assertion
            errors.append(exc)
    threads = [threading.Thread(target=write) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    validate_registry_document(storage.read_registry())


def test_suppression_identity_resurfaces_after_material_change(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.workspace, "workspace_root", lambda: str(tmp_path / "workspace"))
    job = _job()
    assert suppressions.ignore(job)["ok"] is True
    assert suppressions.is_suppressed(job)
    changed = {**job, "material_version": material_version({"status": "completed"})}
    assert not suppressions.is_suppressed(changed)
    assert suppressions.clear_for_material_change(changed)["ok"] is True
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert suppressions.snooze(changed, future)["ok"] is True
    assert suppressions.is_suppressed(changed)
    with pytest.raises(ValueError):
        suppressions.snooze(changed, "2020-01-01T00:00:00+00:00")

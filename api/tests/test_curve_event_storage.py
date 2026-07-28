"""Curve-event storage: the private ledger file is the only home.

This file used to be test_curve_event_migration.py and carried nine tests for a
one-time relocation of curve_events.json out of the app folder and into the
machine-local private ledger. That migration deleted its own source on success,
the legacy filename is gitignored so it never ships, and there is no legacy file
on the one machine this app runs on. It could not fire again, so per
docs/reference/project-state.md ("anything guarding a pre-existing user's data
is dead code for a population of zero") the migration and its tests are gone.

What remains is the property that outlived it: curve events round-trip through
the versioned private file, and a missing file reads as no events rather than
as an error.
"""

import json

import pytest

from api.operation_ledger import paths
from api.webui import gradebook_service as service


@pytest.fixture
def isolated_curve_storage(tmp_path, monkeypatch):
    private_root = tmp_path / "private"
    monkeypatch.setattr(paths, "private_root", lambda: private_root)
    return private_root


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


def test_events_round_trip_through_the_versioned_private_file(
        isolated_curve_storage):
    private_root = isolated_curve_storage
    events = _events()

    service._save_curve_events(events)

    assert service._load_curve_events() == events
    assert json.loads(paths.curve_events_file().read_text(encoding="utf-8")) == {
        "version": 1, "events": events,
    }
    assert private_root.exists()


def test_no_file_reads_as_no_events(isolated_curve_storage):
    """A teacher who has never curved anything is not an error state."""
    assert not paths.curve_events_file().exists()
    assert service._load_curve_events() == []


def test_a_corrupt_private_file_is_a_storage_error_not_silent_data_loss(
        isolated_curve_storage):
    service._save_curve_events(_events())
    paths.curve_events_file().write_text("{not json", encoding="utf-8")

    with pytest.raises(service.CurveEventStorageError) as raised:
        service._load_curve_events()
    assert str(raised.value) == service.CURVE_EVENT_STORAGE_ERROR

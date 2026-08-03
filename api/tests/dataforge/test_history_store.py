"""The longitudinal snapshot store: canvas_id alongside the pseudonym on
write, and read-time pseudonym resolution from the vault.

save_snapshot() is the write side: every student row it builds carries a
canvas_id field, resolved by the caller (see views._process_file) before the
snapshot is ever handed here. resolve_student_pseudonym() is the read side,
used by profile_export.build_profile to relabel a canvas_id-keyed group with
whatever the vault currently says that student's pseudonym is.
"""

import json

from api.dataforge import history_store


class _Paths:
    """Minimal stand-in for paths.Paths; only history_dir is needed here."""

    def __init__(self, tmp_path):
        self.history_dir = tmp_path / "history"


def _result(students):
    return {
        "descriptive": "fall-benchmark",
        "assessment_name": "Fall Benchmark",
        "grade": "7",
        "type": "STAAR",
        "breakdown_type": "learning_standard",
        "standards": [{"code": "7.9(D)"}],
        "tier_students": students,
    }


# --- write side: save_snapshot carries canvas_id ---------------------------


def test_save_snapshot_carries_canvas_id_alongside_the_pseudonym(tmp_path):
    paths = _Paths(tmp_path)
    history_store.save_snapshot(paths, _result([
        {"n": "Sparky McGee", "pct": 82.0, "missed": {}, "canvas_id": "canvas-1"},
    ]))

    saved = history_store.list_snapshots(paths)
    assert saved[0]["students"] == [
        {
            "n": "Sparky McGee", "pct": 82.0, "app": None, "met": None,
            "mas": None, "missed": {}, "canvas_id": "canvas-1",
        },
    ]


def test_save_snapshot_defaults_canvas_id_to_empty_when_absent(tmp_path):
    """A row with no canvas_id (identity off, or no vault match for that
    student) must not silently drop the field: every row is shaped the same,
    and an empty string means unresolved rather than missing."""
    paths = _Paths(tmp_path)
    history_store.save_snapshot(paths, _result([
        {"n": "Sparky McGee", "pct": 82.0, "missed": {}},
    ]))

    saved = history_store.list_snapshots(paths)
    assert saved[0]["students"][0]["canvas_id"] == ""


# --- read side: resolve_student_pseudonym ----------------------------------


class _FakeIdentity:
    """Minimal stand-in exposing only the one method this helper calls."""

    def __init__(self, mapping):
        self._mapping = mapping

    def pseudonym_for_canvas_id(self, canvas_id):
        return self._mapping.get(canvas_id, "")


def test_resolve_student_pseudonym_prefers_the_current_vault_name():
    identity = _FakeIdentity({"canvas-1": "Newname Renamed"})
    student = {"n": "Sparky McGee", "canvas_id": "canvas-1"}
    assert history_store.resolve_student_pseudonym(student, identity) == "Newname Renamed"


def test_resolve_student_pseudonym_falls_back_without_a_vault_match():
    """The vault has no entry for this canvas_id (an edge case, since
    canvas_id is the vault's own key) -- degrade to the stored label rather
    than erroring or dropping the row."""
    identity = _FakeIdentity({})
    student = {"n": "Sparky McGee", "canvas_id": "canvas-1"}
    assert history_store.resolve_student_pseudonym(student, identity) == "Sparky McGee"


def test_resolve_student_pseudonym_falls_back_with_no_identity_supplied():
    student = {"n": "Sparky McGee", "canvas_id": "canvas-1"}
    assert history_store.resolve_student_pseudonym(student, None) == "Sparky McGee"


def test_resolve_student_pseudonym_with_no_canvas_id_uses_the_stored_name():
    """A row that was never linked (a prior-year student, or a snapshot not
    yet backfilled) has only the stored pseudonym to go on, even with an
    identity available that happens to know that canvas_id under a different
    row."""
    identity = _FakeIdentity({"canvas-1": "Should Not Be Used"})
    student = {"n": "Sparky McGee"}
    assert history_store.resolve_student_pseudonym(student, identity) == "Sparky McGee"

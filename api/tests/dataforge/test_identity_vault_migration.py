import csv
import json

import pytest

from api.dataforge import identity
from api.feedback_vault import Vault


class Paths:
    def __init__(self, root):
        self.history_dir = root / "history"
        self.anon_map = root / "anonymize_map.csv"
        self.history_dir.mkdir()


def _vault(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "by_canvas_id": {
            "canvas-1": {
                "pseudonym": "Sparky McGee", "pseudo_first": "Sparky", "pseudo_last": "McGee",
                "real_name": "Synthetic One", "sis_id": "SIS-1", "nicknames": [],
            },
        }
    }), encoding="utf-8")
    return Vault(str(path))


def _legacy_map(path):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["real_name", "anon_name", "real_id", "anon_id"])
        writer.writeheader()
        writer.writerow({"real_name": "Synthetic One", "anon_name": "Student_101", "real_id": "SIS-1", "anon_id": "ID_101"})
        writer.writerow({"real_name": "Past Student", "anon_name": "Student_202", "real_id": "SIS-old", "anon_id": "ID_202"})


def test_rekey_plan_requires_exactly_one_vault_sis_match():
    plan = identity.build_rekey_plan(
        {"Student_101": "SIS-1", "Student_202": "SIS-old"},
        [{"sis_id": "SIS-1", "pseudonym": "Sparky McGee"}],
    )
    assert plan == {"rekey": {"Student_101": "Sparky McGee"}, "unmatched": ["Student_202"]}

    with pytest.raises(identity.IdentityMigrationError, match="ambiguous"):
        identity.build_rekey_plan(
            {"Student_101": "SIS-1"},
            [{"sis_id": "SIS-1", "pseudonym": "One"}, {"sis_id": "SIS-1", "pseudonym": "Two"}],
        )


def test_migration_rekeys_named_rows_preserves_unmatched_scores_and_is_idempotent(tmp_path):
    paths = Paths(tmp_path)
    _legacy_map(paths.anon_map)
    (paths.history_dir / "synthetic.json").write_text(json.dumps({
        "id": "synthetic", "students": [
            {"n": "Student_101", "pct": 82, "app": "y"},
            {"n": "Student_202", "pct": 44, "app": "n"},
        ],
    }), encoding="utf-8")
    vault = _vault(tmp_path / "vault" / "vault.json")

    report = identity.migrate_legacy_state(paths, vault=vault)
    migrated = json.loads((paths.history_dir / "synthetic.json").read_text(encoding="utf-8"))
    assert report["migrated"] is True
    assert report["migrated_students"] == 1
    assert report["anonymous_students"] == 1
    assert migrated["identity_format"] == "identity_vault.v1"
    assert migrated["students"] == [
        {"n": "Sparky McGee", "pct": 82, "app": "y", "identity_state": "identity_vault"},
        {"n": "", "pct": 44, "app": "n", "identity_state": "anonymous_aggregate"},
    ]
    assert not paths.anon_map.exists()
    assert identity.migrate_legacy_state(paths, vault=vault)["migrated"] is False


def test_vault_identity_never_invents_a_pseudonym_for_an_unenrolled_student(tmp_path):
    vault = _vault(tmp_path / "vault" / "vault.json")
    provider = identity.VaultIdentity(vault)
    assert provider.map_student("Synthetic One", "SIS-1") == ("Sparky McGee", "")
    assert provider.map_student("Past Student", "SIS-old") == ("", "")
    assert provider.linked_students() == {"Sparky McGee": "SIS-1"}


def test_vault_identity_resolves_canvas_id_both_directions(tmp_path):
    vault = _vault(tmp_path / "vault" / "vault.json")
    provider = identity.VaultIdentity(vault)
    assert provider.canvas_id_for_student("Synthetic One", "SIS-1") == "canvas-1"
    assert provider.canvas_id_for_student("Past Student", "SIS-old") == ""
    assert provider.pseudonym_for_canvas_id("canvas-1") == "Sparky McGee"
    assert provider.pseudonym_for_canvas_id("canvas-does-not-exist") == ""
    assert provider.canvas_id_map() == {"Sparky McGee": "canvas-1"}


# --- backfilling canvas_id onto existing history rows ---------------------


def test_backfill_links_rows_whose_stored_pseudonym_still_matches_the_vault(tmp_path):
    paths = Paths(tmp_path)
    (paths.history_dir / "fall.json").write_text(json.dumps({
        "id": "fall", "students": [{"n": "Sparky McGee", "pct": 82.0}],
    }), encoding="utf-8")

    report = identity.backfill_canvas_ids(paths, {"Sparky McGee": "canvas-1"})
    updated = json.loads((paths.history_dir / "fall.json").read_text(encoding="utf-8"))

    assert report == {"snapshots": 1, "linked_students": 1, "unresolved_students": 0}
    assert updated["students"] == [{"n": "Sparky McGee", "pct": 82.0, "canvas_id": "canvas-1"}]


def test_backfill_is_idempotent(tmp_path):
    paths = Paths(tmp_path)
    (paths.history_dir / "fall.json").write_text(json.dumps({
        "id": "fall", "students": [{"n": "Sparky McGee", "pct": 82.0}],
    }), encoding="utf-8")

    canvas_id_map = {"Sparky McGee": "canvas-1"}
    first = identity.backfill_canvas_ids(paths, canvas_id_map)
    second = identity.backfill_canvas_ids(paths, canvas_id_map)

    assert first == {"snapshots": 1, "linked_students": 1, "unresolved_students": 0}
    assert second == {"snapshots": 1, "linked_students": 0, "unresolved_students": 0}, (
        "a row that already carries a canvas_id must be left alone the second time through"
    )


def test_backfill_leaves_unresolvable_rows_anonymous(tmp_path):
    """Locked decision: a prior-year student with no Canvas enrollment has no
    vault entry and no pseudonym to resolve. Their row keeps its score data
    but must not get an invented canvas_id."""
    paths = Paths(tmp_path)
    (paths.history_dir / "snap.json").write_text(json.dumps({
        "id": "snap", "students": [
            {"n": "Sparky McGee", "pct": 82.0},
            {"n": "Prior Year Student", "pct": 44.0},
        ],
    }), encoding="utf-8")

    report = identity.backfill_canvas_ids(paths, {"Sparky McGee": "canvas-1"})
    updated = json.loads((paths.history_dir / "snap.json").read_text(encoding="utf-8"))

    assert report == {"snapshots": 1, "linked_students": 1, "unresolved_students": 1}
    assert updated["students"] == [
        {"n": "Sparky McGee", "pct": 82.0, "canvas_id": "canvas-1"},
        {"n": "Prior Year Student", "pct": 44.0},
    ]


def test_backfill_cannot_repair_a_row_whose_pseudonym_was_already_renamed_away(tmp_path):
    """Order matters, and this is why: the backfill can only resolve a row
    whose stored pseudonym is still a live key in the vault. That is true for
    every row today, because no student has been renamed yet. The moment a
    rename happens, that student's OLD pseudonym is gone from the vault
    entirely, so any of their rows still missing a canvas_id at that point can
    no longer be linked automatically. Not a bug to fix later: an inherent
    limit of having used a pseudonym-only key before canvas_id existed.
    """
    paths = Paths(tmp_path)
    (paths.history_dir / "old.json").write_text(json.dumps({
        "id": "old", "students": [{"n": "Sparky McGee", "pct": 82.0}],
    }), encoding="utf-8")

    # The vault now only knows the NEW pseudonym: the rename already happened
    # before this backfill ran.
    report = identity.backfill_canvas_ids(paths, {"Newname Renamed": "canvas-1"})
    updated = json.loads((paths.history_dir / "old.json").read_text(encoding="utf-8"))

    assert report == {"snapshots": 1, "linked_students": 0, "unresolved_students": 1}
    assert updated["students"][0].get("canvas_id", "") == ""


def test_backfill_is_atomic_a_bad_snapshot_leaves_every_file_untouched(tmp_path):
    paths = Paths(tmp_path)
    good = paths.history_dir / "good.json"
    bad = paths.history_dir / "zzz_bad.json"
    good_original = json.dumps({"id": "good", "students": [{"n": "Sparky McGee", "pct": 82.0}]})
    good.write_text(good_original, encoding="utf-8")
    # Sorts after "good.json", so a failure here proves the FIRST file's
    # already-staged temp gets rolled back too, not just files after it.
    bad.write_text(json.dumps({"id": "bad", "students": "not-a-list"}), encoding="utf-8")

    with pytest.raises(identity.IdentityMigrationError):
        identity.backfill_canvas_ids(paths, {"Sparky McGee": "canvas-1"})

    assert good.read_text(encoding="utf-8") == good_original, "the good file must not be rewritten"
    assert not list(paths.history_dir.glob("*.vault-migration.tmp")), (
        "no staged temp file may survive a failed migration"
    )

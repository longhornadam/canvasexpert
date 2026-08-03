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

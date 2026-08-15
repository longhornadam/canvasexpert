"""Slice 4 acceptance examples for the pseudonymous CanvasMirror boundary."""

import json
from pathlib import Path

from api.feedback_vault import Vault
from api.mirror import store


COURSE = "privacy-course"


def _user(user_id="900001", name="Ada Lovelace"):
    return {
        "id": user_id,
        "name": name,
        "sortable_name": name,
        "short_name": "Ada",
        "sis_user_id": "SIS-900001",
        "enrollments": [{"course_section_id": "800001"}],
    }


def test_mirror_files_are_pseudonym_keyed_and_scrub_free_text_at_write(tmp_path):
    store.write_roster(COURSE, [_user()], {"800001": "Period 1"}, root=str(tmp_path))
    store.merge_submissions(COURSE, "700001", [{
        "assignment_id": "700001",
        "user_id": "900001",
        "body": "Ada Lovelace wrote this response.",
        "submission_comments": [{"author_id": "900099", "comment": "Ada needs revision."}],
    }], root=str(tmp_path), replace=True)

    roster_raw = json.loads(Path(store.roster_path(COURSE, str(tmp_path))).read_text())
    submission_raw = json.loads(
        Path(store.submission_path(COURSE, "700001", str(tmp_path))).read_text()
    )
    roster_text = json.dumps(roster_raw)
    submission_text = json.dumps(submission_raw)

    assert "900001" not in roster_raw["students"]
    pseudonym = next(iter(roster_raw["students"]))
    assert pseudonym != "900001"
    assert "Ada Lovelace" not in roster_text
    assert "SIS-900001" not in roster_text
    assert "900001" not in submission_text
    assert "900099" not in submission_text
    assert "Ada Lovelace" not in submission_text
    assert submission_raw["submissions"][pseudonym]["current"]["user_id"] == pseudonym
    assert pseudonym in submission_raw["submissions"][pseudonym]["current"]["body"]


def test_pseudonym_assignment_is_deterministic_and_probes_vault_collisions(tmp_path):
    first = Vault(str(tmp_path / "first.json"))
    second = Vault(str(tmp_path / "second.json"))
    assert first.get_or_assign("900001", "Ada Lovelace") == second.get_or_assign(
        "900001", "Ada Lovelace"
    )

    first.remember_identity("900002", "Alan Turing")
    assigned = first.get_or_assign("900002")
    assert assigned != first.get_or_assign("900001")


def test_mcp_server_serialization_has_a_structural_last_mile_gate(tmp_path, monkeypatch):
    from api.mcp_server import server, tools

    vault = Vault(str(tmp_path / "vault.json"))
    vault.get_or_assign("900001", "Ada Lovelace")
    vault.save()
    monkeypatch.setattr(tools, "_vault_factory", lambda: Vault(str(tmp_path / "vault.json")))

    result = json.loads(server._compact({"ok": True, "student": {"user_id": "900001"}}))

    assert result["ok"] is False
    assert "900001" not in json.dumps(result)

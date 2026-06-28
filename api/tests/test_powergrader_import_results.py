import json
import sys
from pathlib import Path

from api.feedback_vault import Vault

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.powergrader.import_results import import_results_into_session


def _bundle(first_pseudonym, second_pseudonym):
    return {
        "contract_version": "1.0",
        "quiz_title": "Fictional Essay",
        "students": [
            {
                "pseudonym": first_pseudonym,
                "responses": [{
                    "item_id": "101",
                    "prompt": "",
                    "response": "A safe fictional response.",
                    "possible": 2,
                }],
            },
            {
                "pseudonym": second_pseudonym,
                "responses": [{
                    "item_id": "202",
                    "prompt": "",
                    "response": "Another safe fictional response.",
                    "possible": 2,
                }],
            },
        ],
    }


def _result(pseudonym, item_id, feedback="Clear evidence."):
    return [{
        "pseudonym": pseudonym,
        "item_id": item_id,
        "score": 2,
        "feedback": feedback,
        "disclosure": "Drafted by Sage (AI), reviewed by your teacher.",
    }]


def _session(tmp_path, vault):
    first = vault.get_or_assign("9001", "Ada Lovelace", "5001")
    second = vault.get_or_assign("9002", "Alan Turing", "5002")
    vault.save()
    safe_bundle = tmp_path / "safe_bundle.json"
    safe_bundle.write_text(json.dumps(_bundle(first, second)), encoding="utf-8")
    return {
        "session_id": "sid",
        "privacy_artifacts": {"safe_bundle": str(safe_bundle)},
        "students": [
            {"user_id": "9001", "real_name": "Ada Lovelace", "ai_score": None, "ai_feedback": None},
            {"user_id": "9002", "real_name": "Alan Turing", "ai_score": None, "ai_feedback": None},
        ],
        "copilot_packet": {
            "batches": [
                {
                    "batch_id": "batch-01",
                    "status": "pending",
                    "expected_results": [{"pseudonym": first, "item_id": "101"}],
                },
                {
                    "batch_id": "batch-02",
                    "status": "pending",
                    "expected_results": [{"pseudonym": second, "item_id": "202"}],
                },
            ],
        },
    }, first, second


def _run_import(session, vault, results, batch_id=""):
    saved = {}
    payload, status = import_results_into_session(
        "sid",
        json.dumps(results),
        batch_id=batch_id,
        load_session=lambda session_id: session,
        save_session=lambda s: saved.update(s),
        vault_factory=lambda: vault,
    )
    return payload, status, saved


def test_batch_import_updates_only_matching_batch(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    session, first, second = _session(tmp_path, vault)

    payload, status, saved = _run_import(session, vault, _result(first, "101"), "batch-01")

    assert status == 200
    assert payload["ok"] is True
    assert payload["batch_status"] == "imported"
    assert saved["students"][0]["ai_score"] == 2
    assert "Clear evidence" in saved["students"][0]["ai_feedback"]
    assert saved["students"][1]["ai_score"] is None
    assert saved["copilot_packet"]["batches"][0]["status"] == "imported"
    assert saved["copilot_packet"]["batches"][1]["status"] == "pending"


def test_wrong_batch_paste_fails_without_updates(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    session, first, second = _session(tmp_path, vault)

    payload, status, saved = _run_import(session, vault, _result(second, "202"), "batch-01")

    assert status == 200
    assert payload["ok"] is False
    assert "do not belong to this Copilot batch" in payload["error"]
    assert saved == {}
    assert session["students"][0]["ai_score"] is None
    assert session["students"][1]["ai_score"] is None
    assert session["copilot_packet"]["batches"][0]["status"] == "pending"
    assert session["copilot_packet"]["batches"][1]["status"] == "pending"


def test_batch_reimport_updates_feedback_and_keeps_imported(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    session, first, second = _session(tmp_path, vault)

    payload, status, saved = _run_import(session, vault, _result(first, "101", "Original feedback."), "batch-01")
    assert status == 200
    assert payload["ok"] is True
    assert saved["copilot_packet"]["batches"][0]["status"] == "imported"

    payload, status, saved = _run_import(session, vault, _result(first, "101", "Revised feedback."), "batch-01")

    assert status == 200
    assert payload["ok"] is True
    assert saved["copilot_packet"]["batches"][0]["status"] == "imported"
    assert "Revised feedback" in saved["students"][0]["ai_feedback"]
    assert saved["copilot_packet"]["batches"][1]["status"] == "pending"


def test_partial_batch_import_marks_partial_and_warns(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    session, first, second = _session(tmp_path, vault)
    session["copilot_packet"]["batches"][0]["expected_results"].append(
        {"pseudonym": second, "item_id": "202"}
    )

    payload, status, saved = _run_import(session, vault, _result(first, "101"), "batch-01")

    assert status == 200
    assert payload["ok"] is True
    assert payload["batch_status"] == "partial"
    assert saved["copilot_packet"]["batches"][0]["status"] == "partial"
    assert any("no result for" in warning for warning in payload["validation"]["warnings"])


def test_legacy_import_without_copilot_packet_still_works(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    session, first, second = _session(tmp_path, vault)
    session.pop("copilot_packet")

    payload, status, saved = _run_import(session, vault, _result(first, "101"))

    assert status == 200
    assert payload["ok"] is True
    assert "batch_id" not in payload
    assert saved["students"][0]["ai_score"] == 2
    assert "Clear evidence" in saved["students"][0]["ai_feedback"]
    assert saved["students"][1]["ai_score"] is None

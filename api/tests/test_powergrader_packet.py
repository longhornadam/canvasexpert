import json
import sys
import zipfile
from pathlib import Path

from api.feedback_vault import Vault

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.webui.routes import powergrader


def _bundle(pseudonym="Sparky McGee"):
    return {
        "contract_version": "1.0",
        "quiz_title": "Essay",
        "shared_context": {
            "assignment_description": "Read the passage.",
            "materials": [{"title": "Passage", "source": "pasted", "text": "A short passage."}],
        },
        "students": [{
            "pseudonym": pseudonym,
            "responses": [{
                "item_id": "42",
                "prompt": "",
                "response": "I think the theme is courage.",
                "possible": 2,
            }],
        }],
    }


def test_build_safe_ai_packet_writes_teacher_facing_zip(tmp_path):
    safe_dir = tmp_path / "SAFE"
    safe_dir.mkdir()
    how_to = safe_dir / "Essay__HOW-TO-SCORE.txt"
    how_to.write_text("Score by the rubric.", encoding="utf-8")
    student_txt = safe_dir / "Sparky-McGee__SAFE.txt"
    student_txt.write_text("Pseudonym: Sparky McGee", encoding="utf-8")

    info = powergrader._build_safe_ai_packet(
        "Essay",
        str(safe_dir),
        {"how_to_score": str(how_to), "student_txts": [str(student_txt)]},
        _bundle(),
    )

    assert info["packet_name"].startswith("Safe AI Packet - Essay")
    assert info["packet_zip"].endswith(".zip")
    with zipfile.ZipFile(info["packet_zip"]) as zf:
        names = set(zf.namelist())
    assert "START HERE - Instructions for your AI.txt" in names
    assert "Student Responses.json" in names
    assert "Student Responses - readable.txt" in names
    assert "Source Materials.txt" in names
    assert "Paste Results Back Here - Format.txt" in names


def test_import_results_updates_session_ai_suggestions(tmp_path, monkeypatch):
    vault = Vault(str(tmp_path / "vault.json"))
    pseudonym = vault.get_or_assign("9001", "Ada Lovelace", "5001")
    safe_bundle = tmp_path / "bundle.json"
    safe_bundle.write_text(json.dumps(_bundle(pseudonym)), encoding="utf-8")
    session = {
        "session_id": "sid",
        "privacy_artifacts": {"safe_bundle": str(safe_bundle)},
        "students": [{
            "user_id": "9001",
            "real_name": "Ada Lovelace",
            "ai_score": None,
            "ai_feedback": None,
        }],
    }
    saved = {}

    monkeypatch.setattr(powergrader, "_load_session", lambda session_id: session)
    monkeypatch.setattr(powergrader, "_save_session", lambda s: saved.update(s))
    monkeypatch.setattr(powergrader, "_vault", lambda: vault)

    result_json = json.dumps([{
        "pseudonym": pseudonym,
        "item_id": "42",
        "score": 2,
        "feedback": "Strong theme evidence.",
        "disclosure": "Drafted by Sage (AI), reviewed by your teacher.",
    }])
    response = powergrader.pg_import_results("sid", results=result_json)
    data = json.loads(response.body)

    assert data["ok"] is True
    assert data["updated"] == 1
    assert saved["students"][0]["ai_score"] == 2
    assert "Strong theme evidence" in saved["students"][0]["ai_feedback"]

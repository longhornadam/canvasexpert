"""Offline tests for FeedbackExpert Phase A: pseudonym vault + pipeline.

No live Canvas, no LLM key, no PII (synthetic NQ fixture + temp dirs). Validates
stable pseudonyms, lossless real->pseudo->real round-trips, that no identity leaks
into the LLM bundle, and the drop-folder process/re-identify steps.
"""
import json
import os
import shutil

from api.feedback_vault import Vault
from api import feedback_pipeline as fp
from api.nq_report import parse_student_analysis_file

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures",
                       "student_analysis_sample.csv")


def test_vault_stable_assign_reverse_and_persist(tmp_path):
    vpath = str(tmp_path / "vault.json")
    v = Vault(vpath)
    p1 = v.get_or_assign("9001", "Ada Lovelace", "5001")
    p2 = v.get_or_assign("9002", "Alan Turing", "5002")
    assert p1 == "S001" and p2 == "S002"
    assert v.get_or_assign("9001") == "S001"          # stable on re-sight
    assert v.reverse("S002")["real_name"] == "Alan Turing"
    v.save()
    # Reload: pseudonyms and reverse mapping survive.
    v2 = Vault(vpath)
    assert v2.get_or_assign("9001") == "S001"
    assert v2.reverse("S001")["canvas_id"] == "9001"


def test_pseudonymize_leaks_no_identity(tmp_path):
    parsed = parse_student_analysis_file(FIXTURE)
    v = Vault(str(tmp_path / "vault.json"))
    bundle = fp.pseudonymize(parsed, v, "THG Ch1-9")
    blob = json.dumps(bundle)
    for leak in ["Ada Lovelace", "Alan Turing", "Grace Hopper", "9001", "5001", "SEC-A"]:
        assert leak not in blob                        # no names/ids/sections leave
    assert {s["pseudonym"] for s in bundle["students"]} == {"S001", "S002", "S003"}
    # constructed responses only, with scale but not the earned score
    r0 = bundle["students"][0]["responses"][0]
    assert "possible" in r0 and "prompt" in r0 and "response" in r0


def test_round_trip_reidentify(tmp_path):
    parsed = parse_student_analysis_file(FIXTURE)
    v = Vault(str(tmp_path / "vault.json"))
    fp.pseudonymize(parsed, v, "THG")                  # populates the vault
    results = [{"pseudonym": "S001", "item_id": "1003", "score": 9,
                "feedback": "Strong evidence. — drafted by AI", "disclosure": "AI-assisted"},
               {"pseudonym": "S999", "item_id": "x", "score": 0, "feedback": "?"}]
    rows = fp.reidentify(results, v)
    assert rows[0]["real_name"] == "Ada Lovelace" and rows[0]["canvas_id"] == "9001"
    assert rows[0]["resolved"] is True
    assert rows[1]["resolved"] is False                # unknown pseudonym flagged, not dropped


def test_process_inbox_and_reidentify_dir(tmp_path):
    inbox = tmp_path / "1_Inbox"; inbox.mkdir()
    forllm = tmp_path / "2_ForLLM"
    archive = tmp_path / "_archive"
    fromllm = tmp_path / "3_FromLLM"; fromllm.mkdir()
    toenter = tmp_path / "4_ToEnter"
    vpath = str(tmp_path / "_vault" / "vault.json")
    shutil.copy(FIXTURE, str(inbox / "THG Test.csv"))

    v = Vault(vpath)
    log = list(fp.process_inbox(str(inbox), str(forllm), str(archive), v, "Sage"))
    assert any(line.startswith("✓") for line in log)
    assert (forllm / "THG Test__bundle.json").exists()
    assert (forllm / "THG Test__HOW-TO-SCORE.txt").exists()
    assert os.path.exists(vpath)                        # vault saved
    assert not list(inbox.glob("*.csv"))               # original archived
    assert (archive / "THG Test.csv").exists()

    # Simulate an LLM results drop, then re-identify.
    (fromllm / "THG Test__results.json").write_text(json.dumps([
        {"pseudonym": "S001", "item_id": "1003", "score": 9,
         "feedback": "Nice. Drafted by Sage (AI), reviewed by your teacher.",
         "disclosure": "Drafted by Sage (AI)."}]), encoding="utf-8")
    v2 = Vault(vpath)
    log2 = list(fp.reidentify_dir(str(fromllm), str(toenter), v2))
    assert any(line.startswith("✓") for line in log2)
    out = (toenter / "THG Test__results__to-enter.csv").read_text(encoding="utf-8")
    assert "Ada Lovelace" in out and "Sage" in out

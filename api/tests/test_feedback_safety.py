"""Offline tests for the outbound PII safety scan (the red/green send gate)."""
import os

from api import feedback_pipeline as fp
from api import feedback_safety as safety
from api.feedback_vault import Vault
from api.nq_report import parse_student_analysis_file

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures",
                       "student_analysis_sample.csv")


def test_clean_bundle_is_green(tmp_path):
    parsed = parse_student_analysis_file(FIXTURE)
    v = Vault(str(tmp_path / "vault.json"))
    bundle = fp.pseudonymize(parsed, v, "THG")
    verdict = safety.scan_payload(bundle, v)
    assert verdict["green"] is True
    assert verdict["hard"] == []
    assert verdict["soft"] == []          # fixture essays contain no roster names


def test_raw_parsed_data_is_hard_blocked(tmp_path):
    parsed = parse_student_analysis_file(FIXTURE)
    v = Vault(str(tmp_path / "vault.json"))
    fp.pseudonymize(parsed, v, "THG")     # populate vault with names/ids
    # Scanning the RAW parsed structure (has name/canvas_id/sis_id keys) must block.
    verdict = safety.scan_payload(parsed, v)
    assert verdict["green"] is False
    assert any("name" in h for h in verdict["hard"])


def test_known_name_in_freetext_is_soft_not_blocking(tmp_path):
    v = Vault(str(tmp_path / "vault.json"))
    v.get_or_assign("9001", "Ada Lovelace", "5001")
    bundle = {"students": [{"pseudonym": "S001", "responses": [
        {"item_id": "1", "prompt": "Reflect.", "response": "I worked with Ada Lovelace today."}]}]}
    verdict = safety.scan_payload(bundle, v)
    assert verdict["green"] is True       # soft flags do not block
    assert verdict["soft"] and verdict["soft"][0]["name"] == "Ada Lovelace"


def test_real_id_as_value_is_hard_blocked(tmp_path):
    v = Vault(str(tmp_path / "vault.json"))
    v.get_or_assign("9001", "Ada Lovelace", "5001")
    payload = {"students": [{"pseudonym": "S001", "responses": [
        {"item_id": "x", "note": "9001"}]}]}   # canvas id leaked as a value
    verdict = safety.scan_payload(payload, v)
    assert verdict["green"] is False
    assert any("9001" in h for h in verdict["hard"])

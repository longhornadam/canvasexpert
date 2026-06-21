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
from api import feedback_safety as safety
from api import openrouter_client as orc
from api.nq_report import parse_student_analysis_file

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures",
                       "student_analysis_sample.csv")


def test_vault_stable_assign_reverse_and_persist(tmp_path):
    vpath = str(tmp_path / "vault.json")
    v = Vault(vpath)
    p1 = v.get_or_assign("9001", "Ada Lovelace", "5001")
    p2 = v.get_or_assign("9002", "Alan Turing", "5002")
    assert p1 != p2                                    # distinct fake names
    assert v.get_or_assign("9001") == p1               # stable on re-sight
    assert v.reverse(p2)["real_name"] == "Alan Turing"
    v.save()
    # Reload: pseudonyms and reverse mapping survive.
    v2 = Vault(vpath)
    assert v2.get_or_assign("9001") == p1
    assert v2.reverse(p1)["canvas_id"] == "9001"


def test_pseudonymize_leaks_no_identity(tmp_path):
    parsed = parse_student_analysis_file(FIXTURE)
    v = Vault(str(tmp_path / "vault.json"))
    bundle = fp.pseudonymize(parsed, v, "THG Ch1-9")
    blob = json.dumps(bundle)
    for leak in ["Ada Lovelace", "Alan Turing", "Grace Hopper", "9001", "5001", "SEC-A"]:
        assert leak not in blob                        # no names/ids/sections leave
    # All 3 fixture students have written responses
    assert len(bundle["students"]) == 3
    # constructed responses only, with scale but not the earned score
    r0 = bundle["students"][0]["responses"][0]
    assert "possible" in r0 and "prompt" in r0 and "response" in r0


def test_round_trip_reidentify(tmp_path):
    parsed = parse_student_analysis_file(FIXTURE)
    v = Vault(str(tmp_path / "vault.json"))
    fp.pseudonymize(parsed, v, "THG")                  # populates the vault
    p1 = v.get_or_assign("9001")                        # capture assigned pseudonyms
    results = [{"pseudonym": p1, "item_id": "1003", "score": 9,
                "feedback": "Strong evidence. — drafted by AI", "disclosure": "AI-assisted"},
               {"pseudonym": "S999", "item_id": "x", "score": 0, "feedback": "?"}]
    rows = fp.reidentify(results, v)
    assert rows[0]["real_name"] == "Ada Lovelace" and rows[0]["canvas_id"] == "9001"
    assert rows[0]["resolved"] is True
    assert rows[1]["resolved"] is False                # unknown pseudonym flagged, not dropped


def test_process_inbox_and_reidentify_dir(tmp_path):
    inbox = tmp_path / "PRIVATE"; inbox.mkdir()
    forllm = tmp_path / "SAFE"
    archive = tmp_path / "_system" / "archive"
    fromllm = tmp_path / "SAFE"
    toenter = tmp_path / "PRIVATE"
    vpath = str(tmp_path / "_system" / "vault" / "vault.json")
    shutil.copy(FIXTURE, str(inbox / "THG Test.csv"))

    v = Vault(vpath)
    log = list(fp.process_inbox(str(inbox), str(forllm), str(archive), v, "Sage"))
    assert any(line.startswith("✓") for line in log)
    assert (forllm / "THG Test__bundle.json").exists()
    assert (forllm / "THG Test__HOW-TO-SCORE.txt").exists()
    assert os.path.exists(vpath)                        # vault saved
    assert not list(inbox.glob("*.csv"))               # original archived
    assert (archive / "THG Test.csv").exists()

    # Simulate an LLM results drop — use the actual pseudonym from the vault
    entries = v.entries()
    first_pseudo = entries[0]["pseudonym"] if entries else "S001"

    (fromllm / "THG Test__results.json").write_text(json.dumps([
        {"pseudonym": first_pseudo, "item_id": "1003", "score": 9,
         "feedback": "Nice. Drafted by Sage (AI), reviewed by your teacher.",
         "disclosure": "Drafted by Sage (AI)."}]), encoding="utf-8")
    v2 = Vault(vpath)
    log2 = list(fp.reidentify_dir(str(fromllm), str(toenter), v2))
    assert any(line.startswith("✓") for line in log2)
    out = (toenter / "THG Test__results__to-enter.csv").read_text(encoding="utf-8")
    assert "Ada Lovelace" in out and "Sage" in out


# --------------------------------------------------------------------------
# Phase B: assignment-API submissions path (pseudonymize_submissions)
# --------------------------------------------------------------------------

def _submissions_fixture():
    """Synthetic Canvas submissions (include[]=assignment,user). All fictional."""
    assignment = {"id": 4242, "name": "Essay 1", "points_possible": 10,
                  "description": "<p>Write about courage.</p>"}
    return [
        {"user_id": 9001, "body": "<p>Courage is acting despite fear.</p>",
         "score": None, "submitted_at": "2026-06-01T10:00:00Z",
         "assignment": assignment, "user": {"name": "Ada Lovelace", "sis_user_id": "5001"}},
        {"user_id": 9002, "body": "I think bravery matters.",
         "score": None, "submitted_at": "2026-06-02T10:00:00Z",
         "assignment": assignment, "user": {"name": "Alan Turing", "sis_user_id": "5002"}},
        {"user_id": 9003, "body": "",  # no text, no attachments -> skipped
         "score": None, "submitted_at": "2026-06-02T10:00:00Z",
         "assignment": assignment, "user": {"name": "Grace Hopper", "sis_user_id": "5003"}},
    ]


def test_pseudonymize_submissions_captures_names_and_leaks_nothing(tmp_path):
    v = Vault(str(tmp_path / "vault.json"))
    bundle = fp.pseudonymize_submissions(_submissions_fixture(), v, "Essay 1")
    # The empty submission is dropped; the two with text remain.
    assert len(bundle["students"]) == 2
    # Capture the pseudo we got
    pseudo = bundle["students"][0]["pseudonym"]
    blob = json.dumps(bundle)
    for leak in ["Ada Lovelace", "Alan Turing", "9001", "9002", "5001", "5002"]:
        assert leak not in blob                       # no names/ids leave in the bundle
    # …but the vault learned the real identities (so re-identify can resolve them).
    assert v.reverse(pseudo)["real_name"] in ("Ada Lovelace", "Alan Turing")
    assert bundle["students"][1]["pseudonym"] != pseudo
    r0 = bundle["students"][0]["responses"][0]
    assert r0["possible"] == 10 and r0["response"] == "Courage is acting despite fear."


def test_pseudonymize_submissions_is_safety_green(tmp_path):
    v = Vault(str(tmp_path / "vault.json"))
    bundle = fp.pseudonymize_submissions(_submissions_fixture(), v, "Essay 1")
    verdict = safety.scan_payload(bundle, v)
    assert verdict["green"] is True and not verdict["hard"]


def test_pseudonymize_submissions_keeps_latest_attempt(tmp_path):
    a = {"id": 1, "name": "A", "points_possible": 5, "description": "x"}
    subs = [
        {"user_id": 7, "body": "first draft", "submitted_at": "2026-06-01T00:00:00Z",
         "assignment": a, "user": {"name": "Kit Fox", "sis_user_id": "1"}},
        {"user_id": 7, "body": "FINAL draft", "submitted_at": "2026-06-05T00:00:00Z",
         "assignment": a, "user": {"name": "Kit Fox", "sis_user_id": "1"}},
    ]
    v = Vault(str(tmp_path / "vault.json"))
    bundle = fp.pseudonymize_submissions(subs, v, "A")
    assert len(bundle["students"]) == 1
    assert bundle["students"][0]["responses"][0]["response"] == "FINAL draft"


def test_submissions_round_trip_reidentify(tmp_path):
    v = Vault(str(tmp_path / "vault.json"))
    fp.pseudonymize_submissions(_submissions_fixture(), v, "Essay 1")
    # Find the pseudonym for Alan Turing (user_id 9002)
    alan_pseudo = None
    for e in v.entries():
        if e["real_name"] == "Alan Turing":
            alan_pseudo = e["pseudonym"]
            break
    assert alan_pseudo is not None, "Alan Turing should be in vault"
    rows = fp.reidentify([{"pseudonym": alan_pseudo, "item_id": "4242", "score": 8,
                           "feedback": "Good. — Sage (AI)", "disclosure": "AI"}], v)
    assert rows[0]["resolved"] and rows[0]["real_name"] == "Alan Turing"
    assert rows[0]["sis_id"] == "5002"


# --------------------------------------------------------------------------
# Phase C seam: the Feedback Scoring Contract (validate_results)
# docs/contracts/feedback-scoring-contract.md
# --------------------------------------------------------------------------

def _score_like_an_llm(bundle):
    """Stand in for the scoring LLM: emit one contract-conforming result per
    response in the bundle (Glows/Grows/Next, signed, with disclosure). This is
    the self-test — proving the contract is concrete enough to author against."""
    out = []
    for s in bundle["students"]:
        for r in s["responses"]:
            out.append({
                "pseudonym": s["pseudonym"],
                "item_id": r["item_id"],
                "score": (r["possible"] or 10) - 1,
                "feedback": ("Glows: clear thesis; concrete example.\n"
                             "Grows: connect the middle back to the prompt.\n"
                             "Next step: add one cited quote.\n"
                             "— Sage (AI teaching assistant)"),
                "disclosure": "Drafted by Sage (AI), reviewed by your teacher.",
            })
    return {"contract_version": "1.0", "results": out}


def test_self_authored_results_conform_to_contract(tmp_path):
    parsed = parse_student_analysis_file(FIXTURE)
    v = Vault(str(tmp_path / "vault.json"))
    bundle = fp.pseudonymize(parsed, v, "THG")

    payload = _score_like_an_llm(bundle)               # I act as the LLM here
    verdict = fp.validate_results(payload, bundle, v)
    assert verdict["ok"], verdict["errors"]
    assert verdict["warnings"] == []                   # full coverage, in-range scores

    rows = fp.reidentify(payload["results"], v)        # push-ready, re-identified
    assert rows and all(r["resolved"] for r in rows)
    assert all(r["feedback"].endswith("(AI teaching assistant)") for r in rows)


# --------------------------------------------------------------------------
# Review fixes (2026-06-21): roster-safe fake names, preferred-name capture,
# and the per-student verify gate on SAFE output.
# --------------------------------------------------------------------------

def test_pseudonymize_submissions_fake_names_avoid_roster(tmp_path):
    """The guided flow must assign fake names disjoint from real roster tokens even
    without a prior Name Manager sync (regression: roster_names was not passed)."""
    v = Vault(str(tmp_path / "vault.json"))
    fp.pseudonymize_submissions(_submissions_fixture(), v, "Essay 1")
    roster_tokens = {"ada", "lovelace", "alan", "turing", "grace", "hopper"}
    for e in v.entries():
        assert e["pseudo_first"].lower() not in roster_tokens
        assert e["pseudo_last"].lower() not in roster_tokens


def test_upsert_roster_captures_preferred_name_as_nickname(tmp_path):
    """A student's Canvas short_name (preferred name) must be recorded as a nickname
    so the scrub removes it — the top leak vector (legal 'Joseph', goes by 'Joey')."""
    from api.webui.routes.names import _upsert_roster
    from api import feedback_scrub as scrub
    from api.webui import config

    v = Vault(str(tmp_path / "vault.json"))
    users = [{"id": 8801, "name": "Joseph Smith", "sortable_name": "Smith, Joseph",
              "short_name": "Joey", "sis_user_id": "7001"}]
    _upsert_roster(v, users)

    entry = v.entries()[0]
    assert "Joey" in entry["nicknames"], "short_name should be captured as a nickname"

    rmap = scrub.build_replacement_map(v.entries(), config.active_protected_names())
    scrubbed = scrub.scrub_text("Joey wrote a great essay about Joey.", rmap)
    assert "Joey" not in scrubbed                      # preferred name is gone
    assert scrub.verify_clean(scrubbed, v) == []


def test_write_safe_and_private_excludes_unscrubbed_student(tmp_path):
    """If a real identifier survives scrubbing, that student is pulled from SAFE
    (kept in PRIVATE), never written into a 'safe' file."""
    v = Vault(str(tmp_path / "vault.json"))
    # A vault entry with a real name but NO pseudonym -> no scrub rule is built for
    # it, so a mention of "Ghost" cannot be scrubbed but verify_clean still flags it.
    v._by_id["999"] = {"pseudonym": "", "pseudo_first": "", "pseudo_last": "",
                       "real_name": "Ghost", "sis_id": "", "nicknames": [],
                       "first_seen": ""}
    bundle = fp.pseudonymize_submissions(_submissions_fixture(), v, "Essay 1")
    # Inject an un-scrubbable real name into the first student's response.
    bundle["students"][0]["responses"][0]["response"] += " I worked with Ghost."

    safe_dir = tmp_path / "SAFE"
    priv_dir = tmp_path / "PRIVATE"
    result = fp.write_safe_and_private(bundle, v, str(safe_dir), str(priv_dir))

    assert result["excluded"], "the student mentioning 'Ghost' must be excluded"
    # The excluded student's SAFE .txt is not written; SAFE has fewer students.
    assert result["safe_students"] == len(bundle["students"]) - 1
    safe_blob = (safe_dir / f"{fp._safe('Essay 1')}__bundle.json").read_text(encoding="utf-8")
    assert "Ghost" not in safe_blob                    # nothing un-scrubbed reached SAFE


def test_validate_results_catches_violations(tmp_path):
    parsed = parse_student_analysis_file(FIXTURE)
    v = Vault(str(tmp_path / "vault.json"))
    bundle = fp.pseudonymize(parsed, v, "THG")
    bad = [
        {"pseudonym": "S001", "item_id": "does-not-exist", "score": "high", "feedback": ""},
        {"item_id": "x", "score": 5, "feedback": "ok"},          # no pseudonym
        {"pseudonym": "S404", "item_id": "y", "score": 1, "feedback": "ok"},  # not in vault
    ]
    out = fp.validate_results(bad, bundle, v)
    assert out["ok"] is False
    blob = " | ".join(out["errors"])
    assert "'score' must be a number" in blob
    assert "non-empty text" in blob
    assert "not in the vault" in blob
    assert "not in the bundle" in blob


def test_validate_results_warns_on_partial_coverage(tmp_path):
    parsed = parse_student_analysis_file(FIXTURE)
    v = Vault(str(tmp_path / "vault.json"))
    bundle = fp.pseudonymize(parsed, v, "THG")
    full = _score_like_an_llm(bundle)["results"]
    out = fp.validate_results(full[:1], bundle, v)      # only the first student scored
    assert out["ok"] is True                            # not a hard error…
    assert any("left unscored" in w for w in out["warnings"])  # …but flagged for review


def test_build_request_injects_feedback_pattern():
    bundle = {"students": []}
    pattern = {"id": "basic", "name": "Glows & Grows (Basic)",
               "glows": {"min": 2, "max": 3}, "grows": {"min": 1, "max": 2},
               "strategy_sentences": {"min": 2, "max": 3}, "sign_with_persona": True}
    body = orc.build_request(bundle, "", {"name": "Sage"}, "x/y", feedback_pattern=pattern)
    system = body["messages"][0]["content"]
    assert "Glows & Grows (Basic)" in system
    assert "2–3 Glows" in system and "1–2 Grows" in system
    assert "Sage" in system

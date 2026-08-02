"""Tests for scoring packet MCP surface: build_packet, list_scoring_sessions, get_scoring_packet, stage_scores.

Vault is isolated to tmp_path per test. Fabricated data uses generic names
("Learner One") and large made-up Canvas IDs, never real pseudonyms
(pseudonym assignment is random). No PRIVATE bundles touched, no real workspace
files written. Uses monkeypatch to bind seams (session store, vault, etc.).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from datetime import datetime

import pytest

# Setup sys.path for api/ imports (same as test_mcp_server_tools.py)
_API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_API_DIR)
for _path in (_API_DIR, _REPO_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from api import feedback_vault
from api.mcp_server import tools
from api.powergrader import scoring_packet, session_store as real_session_store
from api.webui import config, workspace


def _use_vault(monkeypatch, tmp_path) -> str:
    vault_path = str(tmp_path / "vault.json")
    monkeypatch.setattr(tools, "_vault_factory", lambda: feedback_vault.Vault(vault_path))
    return vault_path


def _set_active_courses(monkeypatch, course_ids):
    monkeypatch.setattr(
        tools.config, "active_courses",
        lambda: [{"id": cid, "name": f"Course {cid}"} for cid in course_ids],
    )


def _fake_session(session_id: str, course_id: str, assignment_name: str = "Quiz 1",
                  total_students: int = 3, mode: str = "fast") -> dict:
    """Build a fake session dict for testing."""
    return {
        "session_id": session_id,
        "course_id": course_id,
        "assignment_name": assignment_name,
        "assignment_id": "700010",
        "created": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "persona": {"name": "Test TA"},
        "rubric_text": "Grade strictly by this rubric.",
        "students": [{"user_id": f"900{i:03d}"} for i in range(1, total_students + 1)],
        "privacy_artifacts": {},
    }


def _fake_safe_bundle(students: int = 3, items: int = 2,
                       pseudonyms: list[str] | None = None) -> dict:
    """Build a fake SAFE bundle with pseudonymized student responses.

    If pseudonyms is provided, use those. Otherwise generate generic ones.
    """
    if pseudonyms is None:
        pseudonyms = [f"Student-{s}" for s in range(1, students + 1)]

    students_list = []
    for s in range(students):
        responses = []
        for i in range(1, items + 1):
            responses.append({
                "item_id": f"item-{i}",
                "prompt": f"Question {i}: Explain your answer.",
                "response": f"{pseudonyms[s]} answer to question {i}. This is a longer response to test token counting.",
                "possible": 10,
                "submitted_at": datetime.now().isoformat(),
            })
        students_list.append({
            "pseudonym": pseudonyms[s],
            "responses": responses,
        })
    return {
        "contract_version": "1.0",
        "quiz_title": "Test Quiz",
        "students": students_list,
    }


# --- build_packet tests -----

def test_build_packet_happy_path(tmp_path):
    """build_packet returns packet_digest, items, students, paging info."""
    session = _fake_session("s1", "c1")
    bundle = _fake_safe_bundle(students=3, items=2)

    result = scoring_packet.build_packet(
        session=session,
        safe_bundle=bundle,
        offset=0,
        limit=10,
        include_context=True,
    )

    assert result["ok"] is True
    assert "packet_digest" in result
    assert result["total"] == 3  # 3 students
    assert result["returned"] == 6  # 3 students * 2 items = 6 rows
    assert "next_offset" not in result  # final page
    assert result["included_context"] is True
    assert "contract" in result  # context includes contract
    assert "items" in result
    assert "students" in result
    assert len(result["items"]["rows"]) == 2  # 2 items
    assert len(result["students"]["rows"]) == 6  # 3 students * 2 items


def test_build_packet_paging(tmp_path):
    """build_packet respects offset/limit, computes next_offset correctly."""
    session = _fake_session("s1", "c1")
    bundle = _fake_safe_bundle(students=10, items=1)

    # Page 1: offset 0, limit 3
    page1 = scoring_packet.build_packet(
        session=session,
        safe_bundle=bundle,
        offset=0,
        limit=3,
        include_context=False,
    )

    assert page1["returned"] == 3
    assert page1["next_offset"] == 3
    assert "next_offset" in page1

    # Page 2: offset 3, limit 3
    page2 = scoring_packet.build_packet(
        session=session,
        safe_bundle=bundle,
        offset=3,
        limit=3,
        include_context=False,
    )

    assert page2["returned"] == 3
    assert page2["next_offset"] == 6

    # Final page: offset 9, limit 3 (only 1 student left)
    page3 = scoring_packet.build_packet(
        session=session,
        safe_bundle=bundle,
        offset=9,
        limit=3,
        include_context=False,
    )

    assert page3["returned"] == 1
    assert "next_offset" not in page3  # final


def test_build_packet_context_toggle(tmp_path):
    """include_context=True adds contract/rubric, False omits them."""
    session = _fake_session("s1", "c1")
    bundle = _fake_safe_bundle(students=1, items=1)

    with_context = scoring_packet.build_packet(
        session=session,
        safe_bundle=bundle,
        include_context=True,
    )

    without_context = scoring_packet.build_packet(
        session=session,
        safe_bundle=bundle,
        include_context=False,
    )

    assert with_context["included_context"] is True
    assert without_context["included_context"] is False

    # With context should have contract
    assert "contract" in with_context
    # Without context should not have contract
    assert "contract" not in without_context


def test_build_packet_no_media_entries(tmp_path):
    """build_packet drops media entries from responses."""
    session = _fake_session("s1", "c1")
    bundle = _fake_safe_bundle(students=1, items=1)

    # Add media to the response
    bundle["students"][0]["responses"][0]["media"] = [
        {"filename": "image.png", "local_path": "path/to/image.png"}
    ]

    result = scoring_packet.build_packet(
        session=session,
        safe_bundle=bundle,
        include_context=False,
    )

    # Response text should still be there
    assert result["students"]["rows"][0][2]  # pseudonym, item_id, text

    # But media should never appear in the payload
    payload_json = json.dumps(result)
    assert "image.png" not in payload_json
    assert "media" not in payload_json


def test_build_packet_held_students(tmp_path):
    """build_packet reports held students (no text responses)."""
    session = _fake_session("s1", "c1")
    bundle = _fake_safe_bundle(students=2, items=1)

    # Remove text from student 1 (attachment-only)
    bundle["students"][0]["responses"][0].pop("response", None)

    result = scoring_packet.build_packet(
        session=session,
        safe_bundle=bundle,
        include_context=False,
    )

    # Student 0 should be held
    assert result["held"] == 1
    assert "Student-1" in result["held_pseudonyms"]

    # Only student 1 should be in results
    assert result["returned"] == 1


def test_build_packet_oversize_guard(tmp_path, monkeypatch):
    """build_packet refuses if projected payload > 25k tokens."""
    session = _fake_session("s1", "c1")
    bundle = _fake_safe_bundle(students=100, items=1)

    # Mock estimate_text_tokens to return a large number
    def mock_estimate(text: str) -> int:
        return 30_000  # Over the 25k limit

    monkeypatch.setattr("api.powergrader.scoring_packet.source_materials.estimate_text_tokens",
                       mock_estimate)

    with pytest.raises(OverflowError) as exc_info:
        scoring_packet.build_packet(
            session=session,
            safe_bundle=bundle,
            limit=10,
        )

    assert "25,000" in str(exc_info.value)
    assert "limit=" in str(exc_info.value)


def test_build_packet_no_truncation(tmp_path):
    """build_packet returns full response text (no 2000 char truncation)."""
    session = _fake_session("s1", "c1")
    long_response = "A" * 3000  # Longer than default truncation limit
    bundle = _fake_safe_bundle(students=1, items=1)
    bundle["students"][0]["responses"][0]["response"] = long_response

    result = scoring_packet.build_packet(
        session=session,
        safe_bundle=bundle,
        include_context=False,
    )

    # Full text should be present
    assert result["students"]["rows"][0][2] == long_response


# --- list_scoring_sessions tests -----

def test_list_scoring_sessions_filters_to_current_courses(monkeypatch):
    """list_scoring_sessions returns only sessions with SAFE bundle in Current courses."""
    _set_active_courses(monkeypatch, ["111"])  # Only "111" is current

    # Mock list_session_summaries to return sessions in both current and previous courses
    mock_sessions = [
        {
            "session_id": "s1",
            "assignment_name": "Quiz 1",
            "course_id": "111",  # Current
            "created": "2026-01-01T00:00:00Z",
            "mode": "fast",
            "mode_label": "Score myself",
            "total": 5,
            "approved": 3,
            "students": [
                {"ai_score": 8},
                {"ai_score": 9},
                {},  # Not scored
            ],
        },
        {
            "session_id": "s2",
            "assignment_name": "Essay",
            "course_id": "222",  # Previous (not current)
            "created": "2026-01-02T00:00:00Z",
            "mode": "packet",
            "mode_label": "Score with AI chat",
            "total": 10,
            "approved": 5,
            "students": [{"ai_score": 7}],
        },
    ]

    monkeypatch.setattr(
        "api.powergrader.session_store.list_session_summaries",
        lambda: mock_sessions,
    )

    result = tools.list_scoring_sessions()

    assert result["ok"] is True
    assert len(result["sessions"]["rows"]) == 1  # Only s1 (course 111)
    assert result["sessions"]["rows"][0][0] == "s1"  # session_id
    assert result["sessions"]["rows"][0][2] == "111"  # course_id


def test_list_scoring_sessions_columns(monkeypatch):
    """list_scoring_sessions returns correct columns and counts scored students."""
    _set_active_courses(monkeypatch, ["111"])

    mock_sessions = [
        {
            "session_id": "s1",
            "assignment_name": "Quiz",
            "course_id": "111",
            "created": "2026-01-01T00:00:00Z",
            "mode": "fast",
            "mode_label": "Score myself",
            "total": 5,
            "approved": 2,
            "students": [
                {"ai_score": 8},
                {"ai_score": 9},
                {"ai_score": 10},
                {},  # Not scored
            ],
        },
    ]

    monkeypatch.setattr(
        "api.powergrader.session_store.list_session_summaries",
        lambda: mock_sessions,
    )

    result = tools.list_scoring_sessions()

    columns = result["sessions"]["columns"]
    row = result["sessions"]["rows"][0]

    assert columns == ("session_id", "assignment_name", "course_id", "created",
                       "mode_label", "total", "scored", "approved")
    assert row[0] == "s1"  # session_id
    assert row[1] == "Quiz"  # assignment_name
    assert row[2] == "111"  # course_id
    assert row[4] == "Score myself"  # mode_label
    assert row[5] == 5  # total
    assert row[6] == 3  # scored (count of ai_score > 0)
    assert row[7] == 2  # approved


# --- get_scoring_packet MCP tool tests -----

def test_get_scoring_packet_missing_session(monkeypatch, tmp_path):
    """get_scoring_packet returns error when session not found."""
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])

    monkeypatch.setattr(
        "api.powergrader.session_store.load_session",
        lambda sid: None,  # Session not found
    )

    result = tools.get_scoring_packet("nonexistent")

    assert result["ok"] is False
    assert "Session not found" in result["error"]


def test_get_scoring_packet_non_current_course(monkeypatch, tmp_path):
    """get_scoring_packet rejects non-Current courses."""
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])  # Only 111 is current

    session = _fake_session("s1", "222")  # Course 222 is not current
    monkeypatch.setattr(
        "api.powergrader.session_store.load_session",
        lambda sid: session,
    )

    result = tools.get_scoring_packet("s1")

    assert result["ok"] is False
    assert "not a Current course" in result["error"]


def test_get_scoring_packet_missing_bundle(monkeypatch, tmp_path):
    """get_scoring_packet returns error when SAFE bundle is missing."""
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])

    session = _fake_session("s1", "111")
    # No safe_bundle in privacy_artifacts

    monkeypatch.setattr(
        "api.powergrader.session_store.load_session",
        lambda sid: session,
    )

    result = tools.get_scoring_packet("s1")

    assert result["ok"] is False
    assert "Safe AI Packet student response bundle is missing" in result["error"]


def test_get_scoring_packet_happy_path(monkeypatch, tmp_path):
    """get_scoring_packet returns packet with items and students."""
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])

    session = _fake_session("s1", "111")
    bundle = _fake_safe_bundle(students=3, items=2)

    # Mock bundle file
    bundle_path = str(tmp_path / "bundle.json")
    with open(bundle_path, "w") as f:
        json.dump(bundle, f)

    session["privacy_artifacts"]["safe_bundle"] = f"workspace:/{bundle_path}"

    def mock_extended_path(p):
        if "workspace:" in p:
            return p.replace("workspace:/", "")
        return p

    monkeypatch.setattr(
        "api.webui.workspace.extended_path",
        mock_extended_path,
    )

    monkeypatch.setattr(
        "api.powergrader.session_store.load_session",
        lambda sid: session,
    )

    # Add vault with pseudonym mappings
    vault = feedback_vault.Vault(str(tmp_path / "vault.json"))
    # Register students by their Canvas IDs; get_or_assign returns the pseudonym
    vault.get_or_assign("900001", real_name="Learner One")
    vault.get_or_assign("900002", real_name="Learner Two")
    vault.get_or_assign("900003", real_name="Learner Three")
    vault.save()

    monkeypatch.setattr(tools, "_vault_factory", lambda: vault)

    result = tools.get_scoring_packet("s1", limit=10, include_context=True)

    assert result["ok"] is True
    assert "packet_digest" in result
    assert "items" in result
    assert "students" in result
    assert result["included_context"] is True


# --- stage_scores MCP tool tests -----

def test_stage_scores_missing_session(monkeypatch, tmp_path):
    """stage_scores returns error when session not found."""
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])

    monkeypatch.setattr(
        "api.powergrader.session_store.load_session",
        lambda sid: None,
    )

    result = tools.stage_scores("nonexistent", [], "dummy-digest")

    assert result["ok"] is False
    assert "Session not found" in result["error"]


def test_stage_scores_non_current_course(monkeypatch, tmp_path):
    """stage_scores rejects non-Current courses."""
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])

    session = _fake_session("s1", "222")  # Not current
    monkeypatch.setattr(
        "api.powergrader.session_store.load_session",
        lambda sid: session,
    )

    result = tools.stage_scores("s1", [], "dummy-digest")

    assert result["ok"] is False
    assert "not a Current course" in result["error"]


def test_stage_scores_stale_digest(monkeypatch, tmp_path):
    """stage_scores refuses if digest doesn't match current bundle state."""
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])

    session = _fake_session("s1", "111")
    bundle = _fake_safe_bundle(students=1, items=1)

    bundle_path = str(tmp_path / "bundle.json")
    with open(bundle_path, "w") as f:
        json.dump(bundle, f)

    session["privacy_artifacts"]["safe_bundle"] = f"workspace:/{bundle_path}"

    def mock_extended_path(p):
        if "workspace:" in p:
            return p.replace("workspace:/", "")
        return p

    monkeypatch.setattr("api.webui.workspace.extended_path", mock_extended_path)
    monkeypatch.setattr("api.powergrader.session_store.load_session", lambda sid: session)

    # Try with stale digest
    result = tools.stage_scores("s1", [], "wrong-digest")

    assert result["ok"] is False
    assert "digest mismatch" in result["error"].lower()


def test_stage_scores_partial_staging(monkeypatch, tmp_path):
    """stage_scores merges partial results without blocking on unscored students."""
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])

    session = _fake_session("s1", "111", total_students=3)
    bundle = _fake_safe_bundle(students=3, items=1)

    bundle_path = str(tmp_path / "bundle.json")
    with open(bundle_path, "w") as f:
        json.dump(bundle, f)

    session["privacy_artifacts"]["safe_bundle"] = f"workspace:/{bundle_path}"

    def mock_extended_path(p):
        if "workspace:" in p:
            return p.replace("workspace:/", "")
        return p

    monkeypatch.setattr("api.webui.workspace.extended_path", mock_extended_path)

    # Setup vault
    vault_path = str(tmp_path / "vault.json")
    vault = feedback_vault.Vault(vault_path)
    vault.add("Student-1", "Learner One")
    vault.add("Student-2", "Learner Two")
    vault.add("Student-3", "Learner Three")
    vault.save()

    monkeypatch.setattr(tools, "_vault_factory", lambda: vault)

    # Mock session store to track saves
    saved_sessions = {}

    def mock_load(sid):
        return saved_sessions.get(sid) or session

    def mock_save(s):
        saved_sessions[s["session_id"]] = s

    monkeypatch.setattr("api.powergrader.session_store.load_session", mock_load)
    monkeypatch.setattr("api.powergrader.session_store.save_session", mock_save)

    # Compute current digest
    digest_source = {
        "bundle": json.loads(json.dumps(bundle)),
        "session_id": session["session_id"],
    }
    current_digest = scoring_packet._canonical_digest(digest_source)

    # Score only 2 of 3 students
    results = [
        {"pseudonym": "Student-1", "item_id": "item-1", "score": 8, "feedback": "Good"},
        {"pseudonym": "Student-2", "item_id": "item-1", "score": 9, "feedback": "Excellent"},
        # Student-3 not scored
    ]

    result = tools.stage_scores("s1", results, current_digest)

    assert result["ok"] is True
    assert result["updated"] == 2  # Only 2 updated
    assert result["unresolved"] == 1  # 1 missing


# --- Integration: bundle write and no auto-push -----

def test_stage_scores_records_arrival_marker(monkeypatch, tmp_path):
    """stage_scores records assistant_staged timestamp on success."""
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])

    session = _fake_session("s1", "111", total_students=1)
    bundle = _fake_safe_bundle(students=1, items=1)

    bundle_path = str(tmp_path / "bundle.json")
    with open(bundle_path, "w") as f:
        json.dump(bundle, f)

    session["privacy_artifacts"]["safe_bundle"] = f"workspace:/{bundle_path}"

    def mock_extended_path(p):
        if "workspace:" in p:
            return p.replace("workspace:/", "")
        return p

    monkeypatch.setattr("api.webui.workspace.extended_path", mock_extended_path)

    vault_path = str(tmp_path / "vault.json")
    vault = feedback_vault.Vault(vault_path)
    vault.add("Student-1", "Learner One")
    vault.save()

    monkeypatch.setattr(tools, "_vault_factory", lambda: vault)

    saved_sessions = {}

    def mock_load(sid):
        return saved_sessions.get(sid) or session

    def mock_save(s):
        saved_sessions[s["session_id"]] = s

    monkeypatch.setattr("api.powergrader.session_store.load_session", mock_load)
    monkeypatch.setattr("api.powergrader.session_store.save_session", mock_save)

    digest_source = {
        "bundle": json.loads(json.dumps(bundle)),
        "session_id": session["session_id"],
    }
    current_digest = scoring_packet._canonical_digest(digest_source)

    results = [
        {"pseudonym": "Student-1", "item_id": "item-1", "score": 8, "feedback": "Good"},
    ]

    result = tools.stage_scores("s1", results, current_digest)

    assert result["ok"] is True

    # Verify assistant_staged was recorded
    saved = saved_sessions.get("s1")
    assert saved is not None
    assert "assistant_staged" in saved
    assert saved["assistant_staged"]["updated"] == 1
    assert "ts" in saved["assistant_staged"]

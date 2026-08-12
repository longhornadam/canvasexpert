"""Tests for the scoring packet MCP surface.

Covers build_packet plus the three tools: list_scoring_sessions,
get_scoring_packet, stage_scores.

Everything is fabricated and confined to tmp_path: the vault, the session, and
the SAFE bundle. Real names here are invented ("Real Student 1") and Canvas ids
are made up, so nothing touches a teacher's workspace or a PRIVATE bundle.
Pseudonyms are pinned with set_pseudonym because assignment is random and these
tests need to name a pseudonym in a bundle and have it resolve back.
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
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
from api.powergrader import scoring_packet, session_builder

_ORDINALS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven"]


def _seed_vault(monkeypatch, tmp_path, count: int = 3) -> list[dict]:
    """Vault holding ``count`` students, each with a pinned one-word pseudonym.

    Returns [{canvas_id, real_name, pseudonym}] and binds the tool layer's
    vault factory to it.
    """
    vault = feedback_vault.Vault(str(tmp_path / "vault.json"))
    people = []
    for i in range(1, count + 1):
        canvas_id = f"90000{i}"
        real_name = f"Real Student {i}"
        pseudonym = feedback_vault._REGISTRY_WORDS[i]
        vault.get_or_assign(canvas_id, real_name=real_name)
        vault.set_pseudonym(canvas_id, pseudonym)
        people.append({
            "canvas_id": canvas_id,
            "real_name": real_name,
            "pseudonym": pseudonym,
        })
    vault.save()
    monkeypatch.setattr(tools, "_vault_factory", lambda: vault)
    return people


def _set_active_courses(monkeypatch, course_ids):
    monkeypatch.setattr(
        tools.config, "active_courses",
        lambda: [{"id": cid, "name": f"Course {cid}"} for cid in course_ids],
    )


def _fake_session(session_id: str, course_id: str, people: list[dict] | None = None,
                  assignment_name: str = "Quiz 1", mode: str = "fast") -> dict:
    people = people or []
    return {
        "session_id": session_id,
        "course_id": course_id,
        "assignment_name": assignment_name,
        "assignment_id": "700010",
        "created": "2026-01-01T08:00:00",
        "mode": mode,
        "rubric_name": "Test Rubric",
        "persona_id": "test-persona",
        "students": [{"user_id": p["canvas_id"], "status": "pending"} for p in people],
        "privacy_artifacts": {},
    }


@pytest.fixture(autouse=True)
def _stub_declared_context(monkeypatch):
    monkeypatch.setattr(
        tools.config,
        "get_persona",
        lambda _persona_id: {"name": "Test TA", "signoff_policy": "none"},
    )
    monkeypatch.setattr(
        "api.powergrader.context.load_rubric_text",
        lambda _rubric_name: "Grade strictly by this rubric.",
    )


def _fake_safe_bundle(people: list[dict], items: int = 2) -> dict:
    students_list = []
    for person in people:
        students_list.append({
            "pseudonym": person["pseudonym"],
            "responses": [
                {
                    "item_id": f"item-{i}",
                    "prompt": f"Question {i}: explain your answer.",
                    "response": f"An answer to question {i} with enough words to be scorable.",
                    "possible": 10,
                }
                for i in range(1, items + 1)
            ],
        })
    return {
        "contract_version": "1.0",
        "quiz_title": "Test Quiz",
        "students": students_list,
    }


def _attach_bundle(session: dict, tmp_path, bundle: dict, name: str = "bundle.json") -> str:
    """Write the bundle to disk and point the session at it.

    Uses a real absolute path: extended_path is a no-op below the Windows path
    ceiling, so no seam needs mocking here.
    """
    path = str(tmp_path / name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bundle, f)
    session.setdefault("privacy_artifacts", {})["safe_bundle"] = path
    return path


def _bind_session_store(monkeypatch, sessions: dict) -> dict:
    """Bind load/save against an in-memory session map. Returns the map."""
    monkeypatch.setattr("api.powergrader.session_store.load_session",
                        lambda sid: sessions.get(sid))
    monkeypatch.setattr("api.powergrader.session_store.save_session",
                        lambda s: sessions.__setitem__(s["session_id"], s))
    return sessions


# --- build_packet -----------------------------------------------------------

def test_build_packet_happy_path():
    people = [{"pseudonym": f"Learner {_ORDINALS[i]}"} for i in (1, 2, 3)]
    result = scoring_packet.build_packet(
        session=_fake_session("s1", "c1"),
        safe_bundle=_fake_safe_bundle(people, items=2),
        include_context=True,
    )

    assert result["ok"] is True
    assert result["packet_digest"]
    assert result["total"] == 6          # 3 students x 2 items, counted in rows
    assert result["students_total"] == 3  # people, tracked separately
    assert result["returned"] == 6
    assert "next_offset" not in result
    assert result["included_context"] is True
    assert "contract" in result
    assert len(result["items"]) == 2
    assert len(result["students"]) == 6


def test_build_packet_rows_are_dicts_not_a_table():
    """The projection must stay dict-rows so the safety scan can walk into it.

    Tabulating here would bury every response string inside a list, where
    feedback_safety's key-based walk cannot reach it.
    """
    result = scoring_packet.build_packet(
        session=_fake_session("s1", "c1"),
        safe_bundle=_fake_safe_bundle([{"pseudonym": "Quartz"}], items=1),
        include_context=False,
    )

    assert isinstance(result["students"], list)
    assert isinstance(result["students"][0], dict)
    assert set(result["students"][0]) == {"pseudonym", "item_id", "text"}
    assert isinstance(result["items"], list)
    assert isinstance(result["items"][0], dict)


def test_build_packet_paging_counts_rows_not_students():
    """total, offset, limit and next_offset all count response rows.

    A multi-item quiz gives one student several rows. When total counted
    students while paging walked rows, a caller looping until offset >= total
    stopped early and silently skipped most of the class.
    """
    people = [{"pseudonym": f"Learner {_ORDINALS[i]}"} for i in (1, 2, 3)]
    bundle = _fake_safe_bundle(people, items=4)  # 12 rows, 3 students

    first = scoring_packet.build_packet(session=_fake_session("s1", "c1"),
                                        safe_bundle=bundle, offset=0, limit=10,
                                        include_context=False)

    assert first["total"] == 12
    assert first["students_total"] == 3
    assert first["returned"] == 10
    assert first["returned"] <= first["total"]
    assert first["next_offset"] == 10

    # Walking next_offset must reach every row exactly once.
    seen, offset = [], 0
    while offset is not None:
        page = scoring_packet.build_packet(session=_fake_session("s1", "c1"),
                                           safe_bundle=bundle, offset=offset, limit=5,
                                           include_context=False)
        seen.extend((r["pseudonym"], r["item_id"]) for r in page["students"])
        offset = page.get("next_offset")

    assert len(seen) == 12
    assert len(set(seen)) == 12


def test_build_packet_final_page_has_no_next_offset():
    people = [{"pseudonym": f"Learner {_ORDINALS[i]}"} for i in (1, 2, 3)]
    bundle = _fake_safe_bundle(people, items=1)  # 3 rows

    page = scoring_packet.build_packet(session=_fake_session("s1", "c1"),
                                       safe_bundle=bundle, offset=2, limit=3,
                                       include_context=False)

    assert page["returned"] == 1
    assert "next_offset" not in page


def test_build_packet_context_toggle():
    bundle = _fake_safe_bundle([{"pseudonym": "Quartz"}], items=1)

    with_context = scoring_packet.build_packet(session=_fake_session("s1", "c1"),
                                               safe_bundle=bundle, include_context=True)
    without = scoring_packet.build_packet(session=_fake_session("s1", "c1"),
                                          safe_bundle=bundle, include_context=False)

    assert with_context["included_context"] is True
    assert "contract" in with_context
    assert without["included_context"] is False
    assert "contract" not in without


def test_build_packet_drops_media():
    bundle = _fake_safe_bundle([{"pseudonym": "Quartz"}], items=1)
    bundle["students"][0]["responses"][0]["media"] = [
        {"filename": "image.png", "local_path": "path/to/image.png"}
    ]

    result = scoring_packet.build_packet(session=_fake_session("s1", "c1"),
                                         safe_bundle=bundle, include_context=False)

    assert result["students"][0]["text"]
    payload_json = json.dumps(result)
    assert "image.png" not in payload_json
    assert "media" not in payload_json


def test_build_packet_projects_safe_oral_reading_as_text_without_media_transport_fields():
    bundle = _fake_safe_bundle([{"pseudonym": "Quartz"}], items=1)
    bundle["students"][0]["responses"][0]["response"] = ""
    bundle["students"][0]["responses"][0]["oral_reading"] = {
        "version": "1.0", "status": "needs_review", "evidence_digest": "e" * 64,
        "passage_digest": "p" * 64, "passage": "read this passage", "transcript": "read this passage",
        "metrics": {"accuracy": 1.0, "wcpm": 90}, "uncertainty": ["low_confidence"],
        "difference_candidates": [{"kind": "substitution", "expected": "read", "observed": "reed"}],
        "candidate_counts_only": True,
    }

    result = scoring_packet.build_packet(session=_fake_session("s1", "c1"), safe_bundle=bundle, include_context=True)

    payload = json.dumps(result)
    assert result["total"] == 1
    assert "Oral-reading evidence" in result["students"][0]["text"]
    assert "All counts below are candidates" in result["students"][0]["text"]
    assert "pronunciation" in result["contract"]
    for forbidden in ("canonical_path", "word_events", "audio/", "http://", "https://"):
        assert forbidden not in payload


def test_build_packet_counts_each_held_response_once():
    """A media-only response is one held response, not two.

    It used to be counted in both the per-response branch and the
    whole-student fallback, so a single held submission reported held == 2.
    """
    bundle = _fake_safe_bundle([{"pseudonym": "Quartz"}], items=1)
    bundle["students"][0]["responses"][0]["response"] = ""
    bundle["students"][0]["responses"][0]["media"] = [{"filename": "essay.docx"}]

    result = scoring_packet.build_packet(session=_fake_session("s1", "c1"),
                                         safe_bundle=bundle, include_context=False)

    assert result["held"] == 1
    assert result["held_pseudonyms"] == ["Quartz"]
    assert result["total"] == 0
    assert result["returned"] == 0


def test_build_packet_held_never_exceeds_responses_present():
    """Held count stays within the responses that exist, mixed cases included."""
    people = [{"pseudonym": f"Learner {_ORDINALS[i]}"} for i in (1, 2)]
    bundle = _fake_safe_bundle(people, items=2)
    bundle["students"][0]["responses"][0]["response"] = ""          # empty, no media
    bundle["students"][1]["responses"][0]["response"] = ""          # empty, with media
    bundle["students"][1]["responses"][0]["media"] = [{"filename": "a.png"}]

    result = scoring_packet.build_packet(session=_fake_session("s1", "c1"),
                                         safe_bundle=bundle, include_context=False)

    assert result["held"] == 2
    assert result["held"] + result["total"] == 4  # every response classified once
    assert sorted(result["held_pseudonyms"]) == ["Learner One", "Learner Two"]


def test_build_packet_keeps_full_text():
    long_response = "A" * 3000
    bundle = _fake_safe_bundle([{"pseudonym": "Quartz"}], items=1)
    bundle["students"][0]["responses"][0]["response"] = long_response

    result = scoring_packet.build_packet(session=_fake_session("s1", "c1"),
                                         safe_bundle=bundle, include_context=False)

    assert result["students"][0]["text"] == long_response


def test_build_packet_oversize_guard_suggests_a_workable_limit(monkeypatch):
    """Over budget the page is refused, and the retry offered has to be smaller."""
    people = [{"pseudonym": f"Learner {_ORDINALS[i]}"} for i in (1, 2, 3)]
    monkeypatch.setattr(
        "api.powergrader.scoring_packet.source_materials.estimate_text_tokens",
        lambda text: 75_000,
    )

    with pytest.raises(scoring_packet.PacketTooLarge) as exc:
        scoring_packet.build_packet(session=_fake_session("s1", "c1"),
                                    safe_bundle=_fake_safe_bundle(people, items=1),
                                    limit=12)

    message = str(exc.value)
    assert "25,000" in message
    # 12 * 25000 // 75000 == 4: proportional to the overshoot, not limit - 2.
    assert "limit=4" in message


def test_build_packet_oversize_guard_on_a_single_response(monkeypatch):
    """At limit=1 there is no smaller page to suggest, so say something else."""
    monkeypatch.setattr(
        "api.powergrader.scoring_packet.source_materials.estimate_text_tokens",
        lambda text: 40_000,
    )

    with pytest.raises(scoring_packet.PacketTooLarge) as exc:
        scoring_packet.build_packet(session=_fake_session("s1", "c1"),
                                    safe_bundle=_fake_safe_bundle(
                                        [{"pseudonym": "Quartz"}], items=1),
                                    limit=1)

    assert "limit=" not in str(exc.value)
    assert "include_context=false" in str(exc.value)


def test_packet_digest_is_shared_by_both_sides():
    """build_packet and the staging guard must derive the same digest."""
    bundle = _fake_safe_bundle([{"pseudonym": "Quartz"}], items=1)
    packet = scoring_packet.build_packet(session=_fake_session("s1", "c1"),
                                         safe_bundle=bundle, include_context=False)

    assert packet["packet_digest"] == scoring_packet.packet_digest("s1", bundle)


# --- list_scoring_sessions --------------------------------------------------

def _summary(session_id, course_id, **over):
    base = {
        "session_id": session_id,
        "assignment_name": "Quiz",
        "course_id": course_id,
        "assignment_id": "700010",
        "created": "2026-01-01T00:00:00",
        "mode": "fast",
        "mode_label": "Score myself",
        "total": 4,
        "approved": 2,
    }
    base.update(over)
    return base


def test_list_scoring_sessions_filters_to_current_courses(monkeypatch, tmp_path):
    people = _seed_vault(monkeypatch, tmp_path, count=1)
    _set_active_courses(monkeypatch, ["111"])

    current = _fake_session("s1", "111", people)
    _attach_bundle(current, tmp_path, _fake_safe_bundle(people, items=1), "b1.json")
    previous = _fake_session("s2", "222", people)
    _attach_bundle(previous, tmp_path, _fake_safe_bundle(people, items=1), "b2.json")

    _bind_session_store(monkeypatch, {"s1": current, "s2": previous})
    monkeypatch.setattr("api.powergrader.session_store.list_session_summaries",
                        lambda: [_summary("s1", "111"), _summary("s2", "222")])

    result = tools.list_scoring_sessions()

    assert result["ok"] is True
    assert [row[0] for row in result["sessions"]["rows"]] == ["s1"]


def test_list_scoring_sessions_skips_sessions_without_a_bundle(monkeypatch, tmp_path):
    """A session whose bundle is gone is left out, not offered and then refused."""
    people = _seed_vault(monkeypatch, tmp_path, count=1)
    _set_active_courses(monkeypatch, ["111"])

    with_bundle = _fake_session("s1", "111", people)
    _attach_bundle(with_bundle, tmp_path, _fake_safe_bundle(people, items=1))
    without_bundle = _fake_session("s2", "111", people)
    vanished = _fake_session("s3", "111", people)
    vanished["privacy_artifacts"]["safe_bundle"] = str(tmp_path / "not-there.json")

    _bind_session_store(monkeypatch, {"s1": with_bundle, "s2": without_bundle,
                                      "s3": vanished})
    monkeypatch.setattr(
        "api.powergrader.session_store.list_session_summaries",
        lambda: [_summary("s1", "111"), _summary("s2", "111"), _summary("s3", "111")],
    )

    result = tools.list_scoring_sessions()

    assert [row[0] for row in result["sessions"]["rows"]] == ["s1"]


def test_list_scoring_sessions_counts_scored_students(monkeypatch, tmp_path):
    """scored is read off the session's own students.

    The summary dict has never carried a students key, so counting over it
    reported 0 scored for every session no matter how much had been graded.
    """
    people = _seed_vault(monkeypatch, tmp_path, count=3)
    _set_active_courses(monkeypatch, ["111"])

    session = _fake_session("s1", "111", people)
    _attach_bundle(session, tmp_path, _fake_safe_bundle(people, items=1))
    session["students"][0]["ai_score"] = 8
    session["students"][1]["ai_score"] = 0   # a zero is a score, not an absence
    # third student left unscored

    _bind_session_store(monkeypatch, {"s1": session})
    monkeypatch.setattr("api.powergrader.session_store.list_session_summaries",
                        lambda: [_summary("s1", "111", total=3, approved=1)])

    result = tools.list_scoring_sessions()
    row = result["sessions"]["rows"][0]

    assert list(result["sessions"]["columns"]) == [
        "session_id", "assignment_name", "course_id", "created",
        "mode_label", "total", "scored", "approved",
        "assignment_id", "newer_session_exists", "staged_at",
    ]
    assert row[0] == "s1"
    assert row[4] == "Score myself"
    assert row[5] == 3   # total
    assert row[6] == 2   # scored
    assert row[7] == 1   # approved
    assert row[8] == "700010"
    assert row[9] is False
    assert row[10] is None


def test_scoring_session_freshness_marks_older_runs_and_packets(monkeypatch, tmp_path):
    people = _seed_vault(monkeypatch, tmp_path, count=1)
    _set_active_courses(monkeypatch, ["111"])
    old = _fake_session("old", "111", people)
    old["created"] = "2026-01-01T08:00:00"
    new = _fake_session("new", "111", people)
    new["created"] = "2026-01-02T08:00:00"
    _attach_bundle(old, tmp_path, _fake_safe_bundle(people, items=1), "old.json")
    _attach_bundle(new, tmp_path, _fake_safe_bundle(people, items=1), "new.json")
    _bind_session_store(monkeypatch, {"old": old, "new": new})
    monkeypatch.setattr(
        "api.powergrader.session_store.list_session_summaries",
        lambda: [_summary("new", "111", created=new["created"]),
                 _summary("old", "111", created=old["created"])],
    )

    result = tools.list_scoring_sessions()
    rows = {row[0]: row for row in result["sessions"]["rows"]}
    assert rows["old"][9] is True
    assert rows["new"][9] is False

    packet = tools.get_scoring_packet("old")
    assert packet["ok"] is True
    assert packet["newer_session_exists"] is True


# --- get_scoring_packet -----------------------------------------------------

def test_get_scoring_packet_missing_session(monkeypatch, tmp_path):
    _seed_vault(monkeypatch, tmp_path, count=1)
    _set_active_courses(monkeypatch, ["111"])
    _bind_session_store(monkeypatch, {})

    result = tools.get_scoring_packet("nonexistent")

    assert result["ok"] is False
    assert "Session not found" in result["error"]


def test_get_scoring_packet_non_current_course(monkeypatch, tmp_path):
    people = _seed_vault(monkeypatch, tmp_path, count=1)
    _set_active_courses(monkeypatch, ["111"])
    _bind_session_store(monkeypatch, {"s1": _fake_session("s1", "222", people)})

    result = tools.get_scoring_packet("s1")

    assert result["ok"] is False
    assert "not a Current course" in result["error"]


def test_get_scoring_packet_missing_bundle(monkeypatch, tmp_path):
    people = _seed_vault(monkeypatch, tmp_path, count=1)
    _set_active_courses(monkeypatch, ["111"])
    _bind_session_store(monkeypatch, {"s1": _fake_session("s1", "111", people)})

    result = tools.get_scoring_packet("s1")

    assert result["ok"] is False
    assert "Safe AI Packet student response bundle is missing" in result["error"]


def test_get_scoring_packet_happy_path(monkeypatch, tmp_path):
    people = _seed_vault(monkeypatch, tmp_path, count=3)
    _set_active_courses(monkeypatch, ["111"])

    session = _fake_session("s1", "111", people)
    _attach_bundle(session, tmp_path, _fake_safe_bundle(people, items=2))
    _bind_session_store(monkeypatch, {"s1": session})

    result = tools.get_scoring_packet("s1", limit=10, include_context=True)

    assert result["ok"] is True
    assert result["packet_digest"]
    assert result["included_context"] is True
    # Tabulated on the way out, after the gate has walked the dict rows.
    assert list(result["students"]["columns"]) == ["pseudonym", "item_id", "text"]
    assert list(result["items"]["columns"]) == ["item_id", "prompt", "possible"]
    assert len(result["students"]["rows"]) == 6
    assert result["total"] == 6
    assert result["students_total"] == 3

    without_context = tools.get_scoring_packet("s1", include_context=False)
    assert without_context["ok"] is True
    assert "contract" not in without_context
    assert "rubric" not in without_context


def test_get_scoring_packet_resolves_declared_rubric_and_persona(monkeypatch, tmp_path):
    people = _seed_vault(monkeypatch, tmp_path, count=1)
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(
        "api.powergrader.context.load_rubric_text",
        lambda name: "3 pts: uses a loop" if name == "Test Rubric" else "",
    )
    monkeypatch.setattr(
        tools.config,
        "get_persona",
        lambda persona_id: {
            "name": "Packet TA",
            "signoff_policy": "ai_disclosure",
            "signoff_text": "Drafted by {name} (AI), reviewed by your teacher.",
        },
    )

    session = _fake_session("s1", "111", people)
    _attach_bundle(session, tmp_path, _fake_safe_bundle(people, items=1))
    _bind_session_store(monkeypatch, {"s1": session})

    result = tools.get_scoring_packet("s1")

    assert result["ok"] is True
    assert result["rubric"] == {"name": "Test Rubric", "included": True}
    assert "3 pts: uses a loop" in result["contract"]
    assert "Packet TA" in result["contract"]
    assert "Drafted by Packet TA (AI), reviewed by your teacher." in result["contract"]


def test_get_scoring_packet_reports_missing_declared_rubric(monkeypatch, tmp_path):
    people = _seed_vault(monkeypatch, tmp_path, count=1)
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr("api.powergrader.context.load_rubric_text", lambda _name: "")

    session = _fake_session("s1", "111", people)
    _attach_bundle(session, tmp_path, _fake_safe_bundle(people, items=1))
    _bind_session_store(monkeypatch, {"s1": session})

    result = tools.get_scoring_packet("s1")

    assert result["ok"] is True
    assert result["rubric"] == {"name": "Test Rubric", "included": False}
    assert "attached as Knowledge" not in result["contract"]
    assert "No scoring rubric was provided" in result["contract"]


def test_get_scoring_packet_preserves_legacy_inline_context(monkeypatch, tmp_path):
    people = _seed_vault(monkeypatch, tmp_path, count=1)
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(
        "api.powergrader.context.load_rubric_text",
        lambda _name: pytest.fail("legacy rubric should not be resolved"),
    )
    monkeypatch.setattr(
        tools.config,
        "get_persona",
        lambda _persona_id: pytest.fail("legacy persona should not be resolved"),
    )

    session = _fake_session("s1", "111", people)
    session["rubric_text"] = "Legacy rubric text"
    session["persona"] = {
        "name": "Legacy TA",
        "signoff_policy": "ai_disclosure",
        "signoff_text": "Drafted by {name} (AI), reviewed by your teacher.",
    }
    _attach_bundle(session, tmp_path, _fake_safe_bundle(people, items=1))
    _bind_session_store(monkeypatch, {"s1": session})

    result = tools.get_scoring_packet("s1")

    assert result["ok"] is True
    assert result["rubric"] == {"name": "Test Rubric", "included": True}
    assert "Legacy rubric text" in result["contract"]
    assert "Legacy TA" in result["contract"]


def test_session_builder_keeps_rubric_read_time_only():
    session = session_builder.build_session(
        session_id="s1",
        course_id="c1",
        assignment_id="a1",
        assignment_name="Essay 1",
        points_possible=10,
        mode="packet",
        rubric_name="Test Rubric",
        persona_id="test-persona",
        selected_model="",
    )

    assert session["rubric_name"] == "Test Rubric"
    assert session["persona_id"] == "test-persona"
    assert "rubric_text" not in session


def test_get_scoring_packet_gate_sees_student_response_text(monkeypatch, tmp_path):
    """A real Canvas id inside a response has to block the whole payload.

    This is the regression for gating after tabulation: once rows are
    {columns, rows}, every cell sits inside a list, and feedback_safety's walk
    only visits dict keys. The scan came back green on anything.
    """
    people = _seed_vault(monkeypatch, tmp_path, count=1)
    _set_active_courses(monkeypatch, ["111"])

    bundle = _fake_safe_bundle(people, items=1)
    bundle["students"][0]["responses"][0]["response"] = (
        f"My student number is {people[0]['canvas_id']} in case that helps."
    )

    session = _fake_session("s1", "111", people)
    _attach_bundle(session, tmp_path, bundle)
    _bind_session_store(monkeypatch, {"s1": session})

    result = tools.get_scoring_packet("s1")

    assert result["ok"] is False
    assert "Safety scan blocked" in result["error"]
    # The refusal must not carry the id it caught.
    assert people[0]["canvas_id"] not in json.dumps(result)


def test_get_scoring_packet_refuses_an_oversize_page(monkeypatch, tmp_path):
    people = _seed_vault(monkeypatch, tmp_path, count=3)
    _set_active_courses(monkeypatch, ["111"])

    session = _fake_session("s1", "111", people)
    _attach_bundle(session, tmp_path, _fake_safe_bundle(people, items=2))
    _bind_session_store(monkeypatch, {"s1": session})
    monkeypatch.setattr(
        "api.powergrader.scoring_packet.source_materials.estimate_text_tokens",
        lambda text: 50_000,
    )

    result = tools.get_scoring_packet("s1", limit=6)

    assert result["ok"] is False
    assert "limit=3" in result["error"]


# --- stage_scores -----------------------------------------------------------

def _scored(person, item_id="item-1", score=8, feedback="Clear reasoning."):
    return {"pseudonym": person["pseudonym"], "item_id": item_id,
            "score": score, "feedback": feedback}


def test_stage_scores_missing_session(monkeypatch, tmp_path):
    _seed_vault(monkeypatch, tmp_path, count=1)
    _set_active_courses(monkeypatch, ["111"])
    _bind_session_store(monkeypatch, {})

    result = tools.stage_scores("nonexistent", [], "dummy-digest")

    assert result["ok"] is False
    assert "Session not found" in result["error"]


def test_stage_scores_non_current_course(monkeypatch, tmp_path):
    people = _seed_vault(monkeypatch, tmp_path, count=1)
    _set_active_courses(monkeypatch, ["111"])
    _bind_session_store(monkeypatch, {"s1": _fake_session("s1", "222", people)})

    result = tools.stage_scores("s1", [], "dummy-digest")

    assert result["ok"] is False
    assert "not a Current course" in result["error"]


def test_stage_scores_stale_digest(monkeypatch, tmp_path):
    people = _seed_vault(monkeypatch, tmp_path, count=1)
    _set_active_courses(monkeypatch, ["111"])

    session = _fake_session("s1", "111", people)
    _attach_bundle(session, tmp_path, _fake_safe_bundle(people, items=1))
    _bind_session_store(monkeypatch, {"s1": session})

    result = tools.stage_scores("s1", [_scored(people[0])], "wrong-digest")

    assert result["ok"] is False
    assert "digest mismatch" in result["error"].lower()
    assert session["students"][0].get("ai_score") is None


def test_stage_scores_partial_staging(monkeypatch, tmp_path):
    """Scoring some of the class updates those students and leaves the rest alone."""
    people = _seed_vault(monkeypatch, tmp_path, count=3)
    _set_active_courses(monkeypatch, ["111"])

    bundle = _fake_safe_bundle(people, items=1)
    session = _fake_session("s1", "111", people)
    _attach_bundle(session, tmp_path, bundle)
    sessions = _bind_session_store(monkeypatch, {"s1": session})

    digest = scoring_packet.packet_digest("s1", bundle)
    result = tools.stage_scores(
        "s1", [_scored(people[0], score=8), _scored(people[1], score=9)], digest)

    assert result["ok"] is True
    assert result["updated"] == 2
    assert result["unresolved"] == 0

    students = sessions["s1"]["students"]
    assert students[0]["ai_score"] == 8
    assert students[1]["ai_score"] == 9
    assert students[2].get("ai_score") is None      # untouched
    assert any("left unscored" in w for w in result["validation"]["warnings"])


def test_stage_scores_reports_unresolved_pseudonyms(monkeypatch, tmp_path):
    people = _seed_vault(monkeypatch, tmp_path, count=2)
    _set_active_courses(monkeypatch, ["111"])

    bundle = _fake_safe_bundle(people, items=1)
    session = _fake_session("s1", "111", people)
    _attach_bundle(session, tmp_path, bundle)
    _bind_session_store(monkeypatch, {"s1": session})

    stranger = {"pseudonym": "Quartz"}
    result = tools.stage_scores("s1", [_scored(people[0]), _scored(stranger)],
                                scoring_packet.packet_digest("s1", bundle))

    assert result["ok"] is False
    assert any("not in the vault" in e for e in result["validation"]["errors"])


def test_stage_scores_never_returns_canvas_ids(monkeypatch, tmp_path):
    """The import payload carries updated_user_ids; the tool must not pass it on."""
    people = _seed_vault(monkeypatch, tmp_path, count=2)
    _set_active_courses(monkeypatch, ["111"])

    bundle = _fake_safe_bundle(people, items=1)
    session = _fake_session("s1", "111", people)
    _attach_bundle(session, tmp_path, bundle)
    _bind_session_store(monkeypatch, {"s1": session})

    result = tools.stage_scores("s1", [_scored(people[0]), _scored(people[1])],
                                scoring_packet.packet_digest("s1", bundle))

    assert result["ok"] is True
    assert "updated_user_ids" not in result
    serialized = json.dumps(result)
    for person in people:
        assert person["canvas_id"] not in serialized
        assert person["real_name"] not in serialized


def test_stage_scores_invalidates_a_pending_push_review(monkeypatch, tmp_path):
    """A review previewed against the old scores must not survive staging.

    It was computed from the scores being replaced, so leaving it in place
    would let the teacher push a review of numbers that no longer exist.
    """
    people = _seed_vault(monkeypatch, tmp_path, count=1)
    _set_active_courses(monkeypatch, ["111"])

    bundle = _fake_safe_bundle(people, items=1)
    session = _fake_session("s1", "111", people)
    _attach_bundle(session, tmp_path, bundle)
    session["pending_push_review"] = {"stale": True}
    session["pending_new_quiz_review"] = {"stale": True}
    sessions = _bind_session_store(monkeypatch, {"s1": session})

    result = tools.stage_scores("s1", [_scored(people[0])],
                                scoring_packet.packet_digest("s1", bundle))

    assert result["ok"] is True
    assert "pending_push_review" not in sessions["s1"]
    assert "pending_new_quiz_review" not in sessions["s1"]


def test_stage_scores_holds_the_session_lock(monkeypatch, tmp_path):
    """Staging takes the same lock the web UI's import route takes.

    Without it an assistant staging over MCP and a teacher working the queue
    can interleave a read-modify-write and lose one of the two writes.
    """
    people = _seed_vault(monkeypatch, tmp_path, count=1)
    _set_active_courses(monkeypatch, ["111"])

    bundle = _fake_safe_bundle(people, items=1)
    session = _fake_session("s1", "111", people)
    _attach_bundle(session, tmp_path, bundle)
    sessions = _bind_session_store(monkeypatch, {"s1": session})

    events = []

    @contextlib.contextmanager
    def recording_lock(session_id):
        events.append(("acquire", session_id))
        try:
            yield
        finally:
            events.append(("release", session_id))

    monkeypatch.setattr("api.powergrader.session_store.session_lock", recording_lock)
    monkeypatch.setattr(
        "api.powergrader.session_store.save_session",
        lambda s: (events.append(("save", s["session_id"])),
                   sessions.__setitem__(s["session_id"], s))[1],
    )

    result = tools.stage_scores("s1", [_scored(people[0])],
                                scoring_packet.packet_digest("s1", bundle))

    assert result["ok"] is True
    assert events[0] == ("acquire", "s1")
    assert events[-1] == ("release", "s1")
    assert ("save", "s1") in events           # every write happened inside it

    # import_results_into_session takes the lock again on its own, exactly as
    # it does under the web UI route. The lock is reentrant, and the outer
    # hold is what keeps the digest check and the import in one atomic span.
    depth = 0
    for kind, _ in events:
        depth += {"acquire": 1, "release": -1}.get(kind, 0)
        assert depth >= 1 or kind == "release"
    assert depth == 0


def test_stage_scores_does_not_push_to_canvas(monkeypatch, tmp_path):
    """Auto-post stays off this path even when the session has it enabled."""
    people = _seed_vault(monkeypatch, tmp_path, count=1)
    _set_active_courses(monkeypatch, ["111"])

    bundle = _fake_safe_bundle(people, items=1)
    session = _fake_session("s1", "111", people)
    _attach_bundle(session, tmp_path, bundle)
    session["auto_post"] = {"enabled": True}
    sessions = _bind_session_store(monkeypatch, {"s1": session})

    def _explode(*a, **kw):
        raise AssertionError("stage_scores must never reach Canvas")

    monkeypatch.setattr(
        "api.powergrader.interactive_autopush.run_interactive_autopush", _explode)

    result = tools.stage_scores("s1", [_scored(people[0])],
                                scoring_packet.packet_digest("s1", bundle))

    assert result["ok"] is True
    assert sessions["s1"]["students"][0]["ai_score"] == 8
    assert not sessions["s1"]["students"][0].get("posted")


def test_stage_scores_records_arrival_marker(monkeypatch, tmp_path):
    people = _seed_vault(monkeypatch, tmp_path, count=1)
    _set_active_courses(monkeypatch, ["111"])

    bundle = _fake_safe_bundle(people, items=1)
    session = _fake_session("s1", "111", people)
    _attach_bundle(session, tmp_path, bundle)
    sessions = _bind_session_store(monkeypatch, {"s1": session})

    result = tools.stage_scores("s1", [_scored(people[0])],
                                scoring_packet.packet_digest("s1", bundle))

    assert result["ok"] is True
    marker = sessions["s1"].get("assistant_staged")
    assert marker is not None
    assert marker["updated"] == 1
    datetime.fromisoformat(marker["staged_at"])  # parses, so it is a real timestamp
    assert result["staged_at"] == marker["staged_at"]
    assert result["scored"] == 1


def test_get_packet_then_stage_round_trip(monkeypatch, tmp_path):
    """The digest handed out by get_scoring_packet is accepted by stage_scores."""
    people = _seed_vault(monkeypatch, tmp_path, count=2)
    _set_active_courses(monkeypatch, ["111"])

    session = _fake_session("s1", "111", people)
    _attach_bundle(session, tmp_path, _fake_safe_bundle(people, items=1))
    sessions = _bind_session_store(monkeypatch, {"s1": session})

    packet = tools.get_scoring_packet("s1")
    assert packet["ok"] is True

    scored = [
        {"pseudonym": row[0], "item_id": row[1], "score": 7, "feedback": "Solid."}
        for row in packet["students"]["rows"]
    ]
    result = tools.stage_scores("s1", scored, packet["packet_digest"])

    assert result["ok"] is True
    assert result["updated"] == 2
    assert all(st["ai_score"] == 7 for st in sessions["s1"]["students"])

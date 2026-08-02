"""Offline tests for the read-only MCP server's tool implementations.

Vault is isolated to ``tmp_path`` per test (never the real global vault).
Fabricated data uses generic names ("Learner One") and large made-up Canvas
IDs, never a specific pseudonym assertion (pseudonym assignment is random).
Worktree-independent: paths are computed from ``__file__``, never hardcoded.

Mirrors the monkeypatch-module-level-fetchers pattern from
``api/tests/test_gradebook_routes.py``.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# api/mcp_server/pseudonym.py reaches api.webui.routes.names, which (like the
# rest of the webui package) imports sibling top-level api/ modules with bare
# names ("import feedback_scrub"). That only resolves once the api/ directory
# itself is on sys.path -- normally guaranteed by api/mcp_server/__main__.py's
# bootstrap at runtime. Standalone test collection needs the same bootstrap.
_API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_API_DIR)
for _path in (_API_DIR, _REPO_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from api import feedback_safety, feedback_scrub, gradebook_queries, roster_service, runtime_paths
from api.feedback_vault import Vault
from api.mcp_server import pseudonym, tools
from api.mirror import store as mirror_store
from api.webui import canvas_client, workspace

FIXTURE_USERS = [
    {
        "id": 900001,
        "name": "Learner One",
        "sortable_name": "One, Learner",
        "short_name": "Lee",
        "sis_user_id": "SIS-900001",
        "enrollments": [{"course_section_id": 800001}],
    },
    {
        "id": 900002,
        "name": "Learner Two",
        "sortable_name": "Two, Learner",
        "short_name": "Learner Two",
        "sis_user_id": "SIS-900002",
        "enrollments": [{"course_section_id": 800002}],
    },
]
SECTION_MAP = {"800001": "Period 1", "800002": "Period 2"}

GRADEBOOK_STUDENTS = [
    {"id": 900001, "name": "Learner One", "sortable_name": "One, Learner"},
    {"id": 900002, "name": "Learner Two", "sortable_name": "Two, Learner"},
]
GRADEBOOK_ASSIGNMENTS = [{
    "id": 700010, "name": "Quiz 1", "due_at": "2026-07-01T23:59:00Z",
    "points_possible": 10, "html_url": "https://example.invalid/quiz-1",
    "published": True,
}]
GRADEBOOK_SUBS = [
    {"assignment_id": 700010, "user_id": 900001, "workflow_state": "graded",
     "score": 9, "submitted_at": "2026-07-01T20:00:00Z"},
    {"assignment_id": 700010, "user_id": 900002, "workflow_state": "submitted",
     "submitted_at": "2026-07-01T21:00:00Z"},
]

_LEAKS = [
    "Learner One", "Learner Two", "One, Learner", "Two, Learner", "Lee",
    "900001", "900002", "SIS-900001", "SIS-900002",
]


def _assert_no_leaks(payload: dict):
    dumped = json.dumps(payload)
    for leak in _LEAKS:
        assert leak not in dumped, f"{leak!r} leaked into payload: {dumped}"


def _rows(table: dict) -> list[dict]:
    """Re-expand a token-lean {columns, rows} table into per-row dicts."""
    return [dict(zip(table["columns"], row)) for row in table["rows"]]


def _use_vault(monkeypatch, tmp_path) -> str:
    vault_path = str(tmp_path / "vault.json")
    monkeypatch.setattr(tools, "_vault_factory", lambda: Vault(vault_path))
    return vault_path


def _set_active_courses(monkeypatch, course_ids):
    monkeypatch.setattr(
        tools.config, "active_courses",
        lambda: [{"id": cid, "name": f"Course {cid}"} for cid in course_ids],
    )


def _set_previous_course(monkeypatch, course_id="111"):
    _set_active_courses(monkeypatch, ["222"])
    monkeypatch.setattr(
        tools.config, "saved_courses",
        lambda: [{"id": course_id, "name": f"Course {course_id}", "active": False}],
    )


# --- list_courses (no course_id, no student data -> no gates) --------------

def test_list_courses_happy(monkeypatch):
    monkeypatch.setattr(tools.config, "saved_courses", lambda: [
        {"id": "111", "name": "Algebra I", "nickname": "", "active": True},
        {"id": "222", "name": "Geometry", "nickname": "Geo Honors", "active": False},
    ])
    monkeypatch.setattr(
        tools.mirror_store, "read_course_context",
        lambda cid: {"lifecycle": "current" if cid == "111" else "concluded"},
    )
    result = tools.list_courses()
    assert result == {"ok": True, "courses": [
        {"course_id": "111", "course_name": "Algebra I", "active": True,
         "lifecycle": "current"},
        {"course_id": "222", "course_name": "Geo Honors", "active": False,
         "lifecycle": "concluded"},
    ]}


def test_list_courses_empty(monkeypatch):
    monkeypatch.setattr(tools.config, "saved_courses", lambda: [])
    assert tools.list_courses() == {"ok": True, "courses": []}


# --- course gating (shared by every course_id tool) -------------------------

def test_course_gate_check_rejects_non_current_course(monkeypatch):
    monkeypatch.setattr(tools.config, "active_courses", lambda: [{"id": "111"}])
    assert tools._course_gate_check("999") is not None
    assert tools._course_gate_check("111") is None


def test_get_roster_rejects_non_current_course(monkeypatch, tmp_path):
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["222"])
    result = tools.get_roster("111")
    assert result["ok"] is False
    assert "not a Current course" in result["error"]


def test_student_tools_fail_closed_when_workspace_unresolved(monkeypatch):
    """When the workspace (and thus the identity vault) can't be resolved, the
    student-data tools must refuse rather than scatter the vault to a stray path.
    No _vault_factory override here: this exercises the real _default_vault."""
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(workspace, "identity_vault_dir", lambda *a, **k: None)
    for result in (
        tools.get_roster("111"),
        tools.get_seating_context("111", "Period 1"),
        tools.get_submissions("111", "700010"),
        tools.get_gradebook_snapshot("111"),
    ):
        assert result["ok"] is False
        assert "workspace" in result["error"].lower()


# --- get_course_assignments (disk-only catalog, no student data) -----------

def _catalog_document(assignment_records, module_records):
    scope = {"state": "current", "last_success_at": "2026-07-01T00:00:00Z",
             "last_attempt_at": "2026-07-01T00:00:00Z", "error_code": ""}
    return {
        "course_id": "111",
        "course_name": "Test Course",
        "updated_at": "2026-07-01T00:00:00Z",
        "assignments": {**scope, "records": assignment_records},
        "modules": {**scope, "records": module_records},
    }


def test_get_course_assignments_happy(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    document = _catalog_document(
        {"700010": {"id": 700010, "name": "Quiz 1", "description_text": "desc",
                    "points_possible": 10, "due_at": "2026-07-01T23:59:00Z",
                    "published": True}},
        [],
    )
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": document, "source": "canonical", "warnings": []})

    result = tools.get_course_assignments("111")
    assert result["ok"] is True
    assert result["course_name"] == "Test Course"
    assert _rows(result["assignments"]) == [{
        "id": 700010, "title": "Quiz 1", "description_text": "desc",
        "due_at": "2026-07-01T23:59:00Z", "points_possible": 10, "published": True,
    }]


def test_get_course_assignments_uses_catalog_read_scope(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    document = _catalog_document(
        {"700010": {"id": 700010, "name": "Quiz 1", "description_text": "desc",
                    "points_possible": 10, "due_at": "", "published": True}},
        [],
    )
    read_result = {"catalog": document, "source": "canonical", "warnings": []}
    calls = []
    monkeypatch.setattr(tools, "read_catalog", lambda course_id: read_result)

    def catalog_assignments(course_id, *, catalog_reader=None):
        calls.append(course_id)
        assert catalog_reader(course_id) is read_result
        return {
            "source": "catalog", "records": list(document["assignments"]["records"].values()),
        }

    monkeypatch.setattr(tools.read_service, "catalog_assignments", catalog_assignments)

    assert tools.get_course_assignments("111")["ok"] is True
    assert calls == ["111"]


def test_get_course_assignments_trims_long_descriptions(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    long_description = "word " * 200  # 1000 chars, well past the preview cut
    document = _catalog_document(
        {"700010": {"id": 700010, "name": "Quiz 1",
                    "description_text": long_description,
                    "points_possible": 10, "due_at": "2026-07-01T23:59:00Z",
                    "published": True}},
        [],
    )
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": document, "source": "canonical", "warnings": []})

    preview = _rows(tools.get_course_assignments("111")["assignments"])[0]["description_text"]
    assert len(preview) < len(long_description)
    assert preview.startswith(long_description[:tools._DESCRIPTION_PREVIEW_CHARS])
    assert "truncated" in preview

    full = _rows(tools.get_course_assignments("111", full_descriptions=True)
                 ["assignments"])[0]["description_text"]
    assert full == long_description


def test_get_course_assignments_empty(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    document = _catalog_document({}, [{"id": 1, "name": "Module 1", "position": 1, "items": []}])
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": document, "source": "canonical", "warnings": []})

    result = tools.get_course_assignments("111")
    assert result["ok"] is True
    assert result["course_id"] == "111"
    assert result["course_name"] == "Test Course"
    assert result["assignments"]["rows"] == []


def test_get_course_assignments_catalog_missing(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": None, "source": "none", "warnings": []})

    result = tools.get_course_assignments("111")
    assert result["ok"] is False
    assert "refresh" in result["error"].lower()


def test_get_course_assignments_accepts_previous_course(monkeypatch):
    _set_previous_course(monkeypatch)
    document = _catalog_document(
        {"700010": {"id": 700010, "name": "Quiz 1", "description_text": "desc"}},
        [],
    )
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": document, "source": "canonical", "warnings": []})
    result = tools.get_course_assignments("111")
    assert result["ok"] is True


# --- get_modules (disk-only catalog, no student data, no vault/gate) --------

MODULE_FIXTURE = [
    {"id": "1", "name": "Unit 1", "position": 1, "items": [
        {"id": "10", "type": "Assignment", "title": "Essay 1", "position": 1, "content_id": "700010"},
        {"id": "11", "type": "Quiz", "title": "Quiz 1", "position": 2, "content_id": "700020"},
    ]},
    {"id": "2", "name": "Unit 2", "position": 2, "items": []},
]


def _module_catalog_document(module_records, *, state="current"):
    module_scope = {"state": state, "last_success_at": "2026-07-01T00:00:00Z",
                    "last_attempt_at": "2026-07-01T00:00:00Z", "error_code": ""}
    assignment_scope = {"state": "current", "last_success_at": "2026-07-01T00:00:00Z",
                        "last_attempt_at": "2026-07-01T00:00:00Z", "error_code": ""}
    return {
        "course_id": "111",
        "course_name": "Test Course",
        "updated_at": "2026-07-01T00:00:00Z",
        "assignments": {**assignment_scope, "records": {}},
        "modules": {**module_scope, "records": module_records},
    }


def test_get_modules_happy_returns_table(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    document = _module_catalog_document(MODULE_FIXTURE)
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": document, "source": "canonical", "warnings": []})
    # Fixture's last_success_at is weeks before "now" -- widen the serve-age
    # window so this test's real focus (module row content) isn't coupled to
    # the freshness threshold, which is covered separately below.
    monkeypatch.setattr(tools.mirror_queries, "_serve_max_age_hours", lambda: 10**9)

    result = tools.get_modules("111")
    assert result["ok"] is True
    assert result["course_id"] == "111"
    assert result["course_name"] == "Test Course"
    assert result["source"] == "catalog"
    assert result["synced_at"] == "2026-07-01T00:00:00Z"
    assert result["state"] == "current"
    assert result["modules_state_detail"] == "cataloged"
    assert result["modules"]["columns"] == ["id", "name", "position", "item_count"]
    assert _rows(result["modules"]) == [
        {"id": "1", "name": "Unit 1", "position": 1, "item_count": 2},
        {"id": "2", "name": "Unit 2", "position": 2, "item_count": 0},
    ]


def test_get_modules_include_items_true_nests_item_tables(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    document = _module_catalog_document(MODULE_FIXTURE)
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": document, "source": "canonical", "warnings": []})

    result = tools.get_modules("111", include_items=True)
    assert result["ok"] is True
    assert result["modules"]["columns"] == ["id", "name", "position", "item_count", "items"]
    rows = _rows(result["modules"])
    assert rows[0]["items"]["columns"] == ["id", "type", "title", "position"]
    assert _rows(rows[0]["items"]) == [
        {"id": "10", "type": "Assignment", "title": "Essay 1", "position": 1},
        {"id": "11", "type": "Quiz", "title": "Quiz 1", "position": 2},
    ]
    assert rows[1]["items"]["rows"] == []


def test_get_modules_include_items_false_omits_items_column(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    document = _module_catalog_document(MODULE_FIXTURE)
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": document, "source": "canonical", "warnings": []})

    result = tools.get_modules("111", include_items=False)
    assert "items" not in result["modules"]["columns"]
    assert all("items" not in row for row in _rows(result["modules"]))


def test_get_modules_accepts_previous_course(monkeypatch):
    _set_previous_course(monkeypatch)
    document = _module_catalog_document([])
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": document, "source": "canonical", "warnings": []})
    monkeypatch.setattr(tools.mirror_queries, "_serve_max_age_hours", lambda: 10**9)
    result = tools.get_modules("111")
    assert result["ok"] is True


def test_get_modules_catalog_missing(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": None, "source": "none", "warnings": []})

    result = tools.get_modules("111")
    assert result["ok"] is False
    assert "refresh" in result["error"].lower()


def test_get_modules_stale_returns_labeled_records_not_refusal(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    document = _module_catalog_document(MODULE_FIXTURE, state="stale")
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": document, "source": "canonical", "warnings": []})

    result = tools.get_modules("111")
    assert result["ok"] is True
    assert result["state"] == "stale"
    assert result["source"] == "catalog"
    assert len(_rows(result["modules"])) == 2


def test_get_modules_marks_state_stale_past_serve_window(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    document = _module_catalog_document(MODULE_FIXTURE)  # state="current", synced weeks ago
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": document, "source": "canonical", "warnings": []})
    monkeypatch.setattr(tools.mirror_queries, "_serve_max_age_hours", lambda: 6.0)

    result = tools.get_modules("111")
    assert result["ok"] is True
    assert result["state"] == "stale"
    assert len(_rows(result["modules"])) == 2


def test_get_modules_state_current_when_within_serve_window(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    document = _module_catalog_document(MODULE_FIXTURE)  # state="current", synced weeks ago
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": document, "source": "canonical", "warnings": []})
    monkeypatch.setattr(tools.mirror_queries, "_serve_max_age_hours", lambda: 10**9)

    result = tools.get_modules("111")
    assert result["ok"] is True
    assert result["state"] == "current"


def test_get_modules_never_cataloged_detail(monkeypatch):
    """When modules scope has never been successfully cataloged (state=unavailable,
    no last_success_at), modules_state_detail says never_cataloged."""
    _set_active_courses(monkeypatch, ["111"])
    document = _module_catalog_document([])
    document["modules"]["state"] = "unavailable"
    document["modules"]["last_success_at"] = ""
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": document, "source": "canonical", "warnings": []})
    monkeypatch.setattr(tools.mirror_queries, "_serve_max_age_hours", lambda: 10**9)

    result = tools.get_modules("111")
    assert result["ok"] is True
    assert result["modules_state_detail"] == "never_cataloged"
    assert result["modules"]["rows"] == []


def test_get_modules_empty_but_cataloged_detail(monkeypatch):
    """When modules scope has been cataloged (has last_success_at) but has zero
    records, modules_state_detail says cataloged — the course genuinely has no
    modules."""
    _set_active_courses(monkeypatch, ["111"])
    document = _module_catalog_document([])  # state="current" with last_success_at
    monkeypatch.setattr(tools, "read_catalog",
                        lambda course_id: {"catalog": document, "source": "canonical", "warnings": []})
    monkeypatch.setattr(tools.mirror_queries, "_serve_max_age_hours", lambda: 10**9)

    result = tools.get_modules("111")
    assert result["ok"] is True
    assert result["modules_state_detail"] == "cataloged"
    assert result["modules"]["rows"] == []


# --- list_sections (no student data -> no vault, no safety gate) ------------

def test_list_sections_happy(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(
        tools.mirror_store, "read_roster",
        lambda cid: {"sections": {"800001": "Period 1", "800002": "Period 2"}},
    )
    result = tools.list_sections("111")
    assert result["ok"] is True
    assert result["course_id"] == "111"
    rows = _rows(result["sections"])
    assert rows == [
        {"section_id": "800001", "section_name": "Period 1"},
        {"section_id": "800002", "section_name": "Period 2"},
    ]


def test_list_sections_empty(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(
        tools.mirror_store, "read_roster",
        lambda cid: {"sections": {}},
    )
    result = tools.list_sections("111")
    assert result["ok"] is True
    assert result["sections"]["rows"] == []


def test_list_sections_roster_missing(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(tools.mirror_store, "read_roster", lambda cid: None)
    result = tools.list_sections("111")
    assert result["ok"] is False
    assert "mirror" in result["error"].lower()


def test_list_sections_accepts_previous_course(monkeypatch):
    _set_previous_course(monkeypatch)
    monkeypatch.setattr(
        tools.mirror_store, "read_roster",
        lambda cid: {"sections": {"800001": "Period 1"}},
    )
    result = tools.list_sections("111")
    assert result["ok"] is True


# --- get_authoring_contract (no course_id, no student data -> no gates) -----

def test_get_authoring_contract_each_kind_returns_nonempty_contract_text():
    for kind in ("quiz", "assignment", "page", "rubric"):
        result = tools.get_authoring_contract(kind)
        assert result["ok"] is True
        assert result["kind"] == kind
        assert isinstance(result["contract"], str)
        assert len(result["contract"]) > 0


def test_get_authoring_contract_unknown_kind_returns_structured_error():
    result = tools.get_authoring_contract("essay")
    assert result == {
        "ok": False,
        "error": ("unknown kind 'essay'; expected one of: "
                  "quiz, assignment, page, rubric, deck, schedule, learning_objective"),
    }


def test_get_authoring_contract_missing_file_returns_structured_error(monkeypatch):
    monkeypatch.setitem(tools._CONTRACT_FILES, "quiz", "NoSuchFile_Base.md")
    result = tools.get_authoring_contract("quiz")
    assert result["ok"] is False
    assert "quiz" in result["error"]


def test_get_authoring_contract_matches_the_one_canonical_repo_file():
    """Each kind has exactly one repository file under api/default_docs/AI
    Authoring/; the MCP tool must return that file's bytes exactly (plus the
    staging appendix for non-deck kinds), never a regenerated or forked copy."""
    for kind, filename in tools._CONTRACT_FILES.items():
        canonical_path = os.path.join(
            tools.REPO_ROOT, "api", "default_docs", "AI Authoring", filename)
        with open(canonical_path, encoding="utf-8") as f:
            canonical_text = f.read()
        result = tools.get_authoring_contract(kind)
        assert result["ok"] is True
        # Deck has no staging appendix; others do
        if kind == "deck":
            assert result["contract"] == canonical_text
        else:
            assert result["contract"].startswith(canonical_text)


def test_get_authoring_contract_schedule_is_direct_write_without_staging_appendix():
    canonical_path = os.path.join(
        tools.REPO_ROOT, "api", "default_docs", "AI Authoring", "Author a Class Schedule.txt"
    )
    with open(canonical_path, encoding="utf-8") as handle:
        canonical_text = handle.read()
    result = tools.get_authoring_contract("schedule")
    assert result == {"ok": True, "kind": "schedule", "contract": canonical_text}
    assert "Staging this for the teacher" not in result["contract"]



def test_download_contract_route_returns_the_same_bytes_as_the_mcp_tool():
    from api.webui.routes import library

    kind_by_download_name = {
        "QuizForge_Base": "quiz",
        "AssignmentForge_Base": "assignment",
        "PageForge_Base": "page",
        "RubricForge_Base": "rubric",
    }
    for download_name, kind in kind_by_download_name.items():
        response = library.api_download_contract(download_name)
        with open(response.path, encoding="utf-8") as f:
            downloaded_text = f.read()
        mcp_result = tools.get_authoring_contract(kind)
        assert mcp_result["ok"] is True
        assert mcp_result["contract"].startswith(downloaded_text)


# --- get_product_guide (no course_id, no student data -> no gates) ----------

def test_get_product_guide_defaults_to_the_overview_briefing():
    result = tools.get_product_guide()
    assert result["ok"] is True
    assert result["topic"] == "overview"
    # Every response advertises the other topics, so an assistant learns the
    # writing-timeline / writing-record guides exist without having to guess
    # a topic name.
    assert result["topics"] == ["overview", "writing_timeline", "writing_record"]
    assert "CanvasAgent" in result["guide"]


def test_get_product_guide_writing_timeline_states_the_tracked_rule():
    """The whole point of this guide: an assistant must be able to learn that
    Writing Timeline exists and that tracked means DOCX-only File Upload, the
    exact shape ``writing_timeline.is_tracked_assignment`` classifies."""
    from api.powergrader import writing_timeline

    result = tools.get_product_guide("writing_timeline")
    assert result["ok"] is True
    assert result["topic"] == "writing_timeline"
    guide = result["guide"]
    assert "Writing Timeline" in guide
    assert "not tracked" in guide
    assert '"allowed_extensions": ["docx"]' in guide
    # The rule the guide states must be the rule the code applies.
    assert writing_timeline.is_tracked_assignment(
        {"submission_types": ["online_upload"], "allowed_extensions": ["docx"]}) is True
    assert writing_timeline.is_tracked_assignment(
        {"submission_types": ["online_upload"], "allowed_extensions": ["docx", "pdf"]}) is False


def test_get_product_guide_topic_is_case_and_space_tolerant():
    assert tools.get_product_guide("  Writing_Timeline ")["topic"] == "writing_timeline"


def test_get_product_guide_unknown_topic_returns_structured_error():
    result = tools.get_product_guide("seating")
    assert result == {
        "ok": False,
        "error": ("unknown topic 'seating'; expected one of: "
                  "overview, writing_timeline, writing_record "
                  "(or omit for overview)"),
    }


def test_get_product_guide_writing_record_states_the_tool_and_the_gap():
    """The whole point of this guide: an assistant must learn get_writing_history
    exists and what it does not yet cover, so it never invents a feedback
    section or a rubric that is not there (brief Batch 1, section 8a)."""
    result = tools.get_product_guide("writing_record")
    assert result["ok"] is True
    assert result["topic"] == "writing_record"
    guide = result["guide"]
    assert "get_writing_history" in guide
    assert "not yet" in guide


def test_get_product_guide_writing_record_matches_served_file_bytes():
    """AC7: the topic's text is the same bytes as the served contract file."""
    path = os.path.join(
        tools.REPO_ROOT, "api", "default_docs", "AI Authoring",
        tools._GUIDE_FILES["writing_record"])
    with open(path, encoding="utf-8") as handle:
        expected = handle.read()
    result = tools.get_product_guide("writing_record")
    assert result["ok"] is True
    assert result["guide"] == expected


def test_get_product_guide_missing_file_returns_structured_error(monkeypatch):
    monkeypatch.setitem(tools._GUIDE_FILES, "overview", "NoSuchGuide.txt")
    result = tools.get_product_guide()
    assert result["ok"] is False
    assert "overview" in result["error"]


def test_every_guide_stays_pastable_plain_text():
    """These files are also handed to a chat-only assistant by copy-paste and
    read back on a cp1252 console, so they follow the CanvasAgent text rules:
    ASCII only, no em-dashes or smart punctuation."""
    banned = {"—": "em-dash", "–": "en-dash", "‘": "curly quote",
              "’": "curly apostrophe", "“": "curly quote",
              "”": "curly quote"}
    for topic in tools._GUIDE_FILES:
        guide = tools.get_product_guide(topic)["guide"]
        found = sorted({name for ch, name in banned.items() if ch in guide})
        assert not found, f"{topic} guide contains {found}"
        offenders = sorted({ch for ch in guide if ord(ch) > 127})
        assert not offenders, (
            f"{topic} guide is not ASCII: {[hex(ord(c)) for c in offenders]}")


def test_download_contract_route_serves_the_same_guides_as_the_mcp_tool():
    """One canonical file per guide: the paste-into-a-chat download and the
    connected assistant's tool must never drift apart."""
    from api.webui.routes import library

    for download_name, topic in (("CanvasAgent", "overview"),
                                 ("WritingTimeline", "writing_timeline")):
        response = library.api_download_contract(download_name)
        with open(response.path, encoding="utf-8") as f:
            downloaded_text = f.read()
        mcp_result = tools.get_product_guide(topic)
        assert mcp_result["ok"] is True
        assert mcp_result["guide"] == downloaded_text


# --- list_staged_content (no course_id, no student data -> no gates) -------

def test_list_staged_content_one_kind_lists_label_only(monkeypatch):
    monkeypatch.setattr(
        tools.deps, "list_inbox_files",
        lambda kind: [{"label": "Inbox/Quizzes/draft1.txt",
                       "path": "C:/abs/Inbox/Quizzes/draft1.txt", "source": "inbox"}]
        if kind == "quiz" else [],
    )
    result = tools.list_staged_content("quiz")
    assert result["ok"] is True
    assert result["staged"]["columns"] == ["kind", "label"]
    assert _rows(result["staged"]) == [
        {"kind": "quiz", "label": "Inbox/Quizzes/draft1.txt"},
    ]
    dumped = json.dumps(result)
    assert "C:/abs/Inbox" not in dumped


def test_list_staged_content_empty_inbox_returns_empty_table(monkeypatch):
    monkeypatch.setattr(tools.deps, "list_inbox_files", lambda kind: [])
    result = tools.list_staged_content("quiz")
    assert result["ok"] is True
    assert result["staged"] == {"columns": ["kind", "label"], "rows": []}


def test_list_staged_content_omitting_kind_aggregates_across_kinds(monkeypatch):
    def _fake_list(kind):
        return [{"label": f"{kind}-draft.txt", "path": f"/abs/{kind}", "source": "inbox"}]

    monkeypatch.setattr(tools.deps, "list_inbox_files", _fake_list)
    result = tools.list_staged_content()
    assert result["ok"] is True
    assert _rows(result["staged"]) == [
        {"kind": "quiz", "label": "quiz-draft.txt"},
        {"kind": "assignment", "label": "assignment-draft.txt"},
        {"kind": "page", "label": "page-draft.txt"},
        {"kind": "rubric", "label": "rubric-draft.txt"},
        {"kind": "deck", "label": "deck-draft.txt"},
    ]


def test_list_staged_content_unknown_kind_returns_structured_error():
    result = tools.list_staged_content("essay")
    assert result == {
        "ok": False,
        "error": ("unknown kind 'essay'; expected one of: "
                  "quiz, assignment, page, rubric, deck (or omit for all)"),
    }


def test_list_staged_content_uses_real_inbox_via_workspace(monkeypatch, tmp_path):
    """End-to-end through the real deps.list_inbox_files/runtime_paths.inbox_folder
    seam, same fixture style as api/tests/test_inbox_files.py."""
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    folder = runtime_paths.inbox_folder("assignment")
    txt_path = os.path.join(str(folder), "staged_assignment.txt")
    body = "assignment draft body"
    with open(txt_path, "w", encoding="utf-8") as handle:
        handle.write(body)
    with open(txt_path + ".done", "w", encoding="utf-8") as handle:
        handle.write(str(len(body.encode("utf-8"))))

    result = tools.list_staged_content("assignment")
    assert result["ok"] is True
    rows = _rows(result["staged"])
    assert len(rows) == 1
    assert rows[0]["kind"] == "assignment"
    assert rows[0]["label"].endswith("staged_assignment.txt")


# --- get_roster --------------------------------------------------------------

def test_get_roster_happy(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    mirror_store.write_roster("111", FIXTURE_USERS, SECTION_MAP, root=str(tmp_path))

    result = tools.get_roster("111")
    assert result["ok"] is True
    assert result["source"] == "mirror"
    assert result["roster"]["columns"] == ["pseudonym", "section_names"]
    roster = _rows(result["roster"])
    assert len(roster) == 2
    pseudonyms = {row["pseudonym"] for row in roster}
    assert len(pseudonyms) == 2  # each student gets a distinct pseudonym
    section_sets = {tuple(row["section_names"]) for row in roster}
    assert section_sets == {("Period 1",), ("Period 2",)}
    assert roster == sorted(roster, key=lambda r: r["pseudonym"])  # sorted by pseudonym
    _assert_no_leaks(result)


def test_get_roster_empty(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    mirror_store.write_roster("111", [], {}, root=str(tmp_path))

    result = tools.get_roster("111")
    assert result["ok"] is True
    assert result["roster"]["rows"] == []


def test_get_roster_failure(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    # No mirror seeded at all: refused rather than fetched live.

    assert tools.get_roster("111") == {"ok": False, "error": tools._MIRROR_UNAVAILABLE_ROSTER_ERROR}


# --- get_submissions ----------------------------------------------------------

def test_get_submissions_happy_scrubs_real_name_and_short_name(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    root = str(tmp_path)
    mirror_store.write_roster("111", FIXTURE_USERS, SECTION_MAP, root=root)
    mirror_store.write_assignments("111", [MIRROR_ASSIGNMENT], root=root)
    mirror_store.merge_submissions("111", "700010", [
        {"assignment_id": 700010, "user_id": 900001, "workflow_state": "graded", "score": 9,
         "grade": "9", "submitted_at": "2026-07-01T20:00:00Z", "late": False, "missing": False,
         "excused": False, "body": "<p>Learner One and Lee worked together on this.</p>"},
    ], root=root, replace=True)
    mirror_store.record_pass("111", "full", ok=True, root=root)

    result = tools.get_submissions("111", "700010")
    assert result["ok"] is True
    assert result["assignment"] == {
        "id": "700010", "title": "Essay 1", "points_possible": 10, "due_at": "2026-07-01T23:59:00Z",
    }
    subs = _rows(result["submissions"])
    assert len(subs) == 1
    row = subs[0]
    assert row["workflow_state"] == "graded"
    assert row["score"] == 9
    # Both the legal name ("Learner One") and the short_name nickname ("Lee")
    # come back as the SAME pseudonym -- the whole point of nickname capture.
    pseudo_first = row["pseudonym"].split()[0]
    assert row["pseudonym"] in row["text"]
    assert pseudo_first in row["text"]
    _assert_no_leaks(result)


def _submissions_fixture(monkeypatch, tmp_path, bodies_by_user=None):
    bodies_by_user = bodies_by_user or {
        900001: "<p>First essay body.</p>",
        900002: "<p>Second essay body.</p>",
    }
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    root = str(tmp_path)
    mirror_store.write_roster("111", FIXTURE_USERS, SECTION_MAP, root=root)
    mirror_store.write_assignments("111", [
        {"id": 700010, "name": "Essay 1", "points_possible": 10, "due_at": ""},
    ], root=root)
    mirror_store.merge_submissions("111", "700010", [
        {"assignment_id": 700010, "user_id": uid, "workflow_state": "submitted",
         "submitted_at": "2026-07-01T20:00:00Z", "body": body}
        for uid, body in bodies_by_user.items()
    ], root=root, replace=True)
    mirror_store.record_pass("111", "full", ok=True, root=root)


def test_get_submissions_include_text_false_drops_text_column(monkeypatch, tmp_path):
    _submissions_fixture(monkeypatch, tmp_path)
    result = tools.get_submissions("111", "700010", include_text=False)
    assert result["ok"] is True
    assert "text" not in result["submissions"]["columns"]
    assert len(result["submissions"]["rows"]) == 2
    dumped = json.dumps(result)
    assert "essay body" not in dumped


def test_get_submissions_pseudonyms_filter_narrows_rows(monkeypatch, tmp_path):
    _submissions_fixture(monkeypatch, tmp_path)
    everyone = _rows(tools.get_submissions("111", "700010")["submissions"])
    assert len(everyone) == 2
    target = everyone[0]["pseudonym"]

    # Case-insensitive, tolerant of spaces around the comma.
    filtered = tools.get_submissions("111", "700010", pseudonyms=f" {target.upper()} ,")
    rows = _rows(filtered["submissions"])
    assert [row["pseudonym"] for row in rows] == [target]


def test_get_submissions_max_text_chars_truncates_with_marker(monkeypatch, tmp_path):
    long_body = "<p>" + ("sentence " * 100) + "</p>"  # ~900 chars of text
    _submissions_fixture(monkeypatch, tmp_path, {900001: long_body})

    result = tools.get_submissions("111", "700010", max_text_chars=100)
    row = _rows(result["submissions"])[0]
    assert len(row["text"]) < 200
    assert "truncated" in row["text"]

    untrimmed = tools.get_submissions("111", "700010", max_text_chars=0)
    full_row = _rows(untrimmed["submissions"])[0]
    assert "truncated" not in full_row["text"]
    assert len(full_row["text"]) > 800


def test_get_submissions_empty(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    root = str(tmp_path)
    mirror_store.write_roster("111", FIXTURE_USERS, SECTION_MAP, root=root)
    mirror_store.write_assignments("111", [
        {"id": 700010, "name": "Essay 1", "points_possible": 10, "due_at": ""},
    ], root=root)
    mirror_store.merge_submissions("111", "700010", [], root=root, replace=True)
    mirror_store.record_pass("111", "full", ok=True, root=root)

    result = tools.get_submissions("111", "700010")
    assert result["ok"] is True
    assert result["submissions"]["rows"] == []


def test_get_submissions_failure(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    root = str(tmp_path)
    # Fresh mirror (roster + a DIFFERENT assignment) -- "700010" just isn't in
    # it, a distinct non-staleness error from the mirror-unavailable refusal.
    mirror_store.write_roster("111", FIXTURE_USERS, SECTION_MAP, root=root)
    mirror_store.write_assignments("111", [
        {"id": 700099, "name": "Other Assignment", "points_possible": 10, "due_at": ""},
    ], root=root)
    mirror_store.record_pass("111", "full", ok=True, root=root)

    assert tools.get_submissions("111", "700010") == {
        "ok": False, "error": "No such assignment in this course's local catalog."}


def test_get_submissions_rejects_non_current_course(monkeypatch, tmp_path):
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["222"])
    result = tools.get_submissions("111", "700010")
    assert result["ok"] is False
    assert "not a Current course" in result["error"]


# --- get_writing_history (private per-student store, no course_id) ---------
#
# The daily-writing store (api/dailywriting) has no course concept, so these
# tests bypass the mirror entirely and point tools._dailywriting_repository_factory
# at a real Repository built from the package's own fixtures
# (api/dailywriting/fixtures), exercised through the real ingest pipeline --
# same construction as api/tests/dailywriting/test_dw_store_and_cli.py's
# `repository` fixture. Fixture submission dates (fall 2026) are all in the
# future relative to this test's actual clock, so every test passes an
# explicit since/until rather than relying on the tool's "today" default.


class _DailyWritingFixtureVault:
    """Same minimal surface as
    api/tests/dailywriting/test_dw_outbound_gate.py's ``_FixtureVault``: only
    what ``feedback_safety.scan_payload`` and ``_vault_conflict_check`` read.
    Duplicated rather than imported -- api/tests has no package __init__.py,
    so cross-file imports between test modules are not how this suite works."""

    def __init__(self, section: str = "section_2a"):
        from api.dailywriting.fixtures import loader as dw_loader
        self._entries = dw_loader.vault_entries(section)

    def entries(self):
        return list(self._entries)

    def all_real_identifiers(self):
        names, ids = set(), set()
        for entry in self._entries:
            names.add(entry["real_name"])
            names.update(entry["real_name"].split())
            names.update(entry.get("nicknames", []))
            ids.add(str(entry["canvas_id"]))
            ids.add(str(entry["sis_id"]))
        return names, ids


def _use_dailywriting_vault(monkeypatch):
    monkeypatch.setattr(tools, "_vault_factory", _DailyWritingFixtureVault)


def _build_dailywriting_repo(tmp_path, fixture_numbers):
    """Store fixture evidence through the one retained ingest path."""
    from api.dailywriting.core import ingest as ingest_module
    from api.dailywriting.fixtures import loader as dw_loader
    from api.dailywriting.store.repo import Repository as DWRepository

    repo = DWRepository(tmp_path / "dw-store", resolver=dw_loader.resolver(), vault=None)
    for number in fixture_numbers:
        raw = dw_loader.single(number)
        context = dw_loader.rep(raw["rep_id"])
        submission = ingest_module.ingest(
            submission_id=raw["submission_id"], rep_id=raw["rep_id"],
            pseudonym_id=dw_loader.pseudonym_for(raw["canvas_id"]),
            submitted_at=dw_loader.submitted_at(raw), text=raw["text"],
            context=context, roster_map=dw_loader.roster_map(),
        )
        repo.put_rep(context)
        repo.append_submission(submission)
    return repo


def _use_dailywriting_repo(monkeypatch, repo):
    monkeypatch.setattr(tools, "_dailywriting_repository_factory", lambda: repo)


def test_get_writing_history_projects_evidence_without_identity_or_assessment(monkeypatch, tmp_path):
    from api.dailywriting.fixtures import loader as dw_loader

    repo = _build_dailywriting_repo(tmp_path, [1, 2])
    _use_dailywriting_repo(monkeypatch, repo)
    _use_dailywriting_vault(monkeypatch)
    pseudonym = dw_loader.pseudonym_for("990001")

    result = tools.get_writing_history(pseudonym, since="2026-01-01", until="2026-12-31")
    assert result["ok"] is True
    row = result["submissions"][0]
    assert {"submission_id", "rep_id", "submitted_at", "student_word_count", "assignment_date", "prompt_text", "segments", "flags"} <= set(row)
    dumped = json.dumps(result)
    for forbidden in ("canvas_id", "Marcus Bell", "total", "possible", "tier", "directives", "profile", "observations"):
        assert forbidden not in dumped


def test_get_writing_history_include_text_gates_student_prose(monkeypatch, tmp_path):
    from api.dailywriting.fixtures import loader as dw_loader

    repo = _build_dailywriting_repo(tmp_path, [7])
    _use_dailywriting_repo(monkeypatch, repo)
    _use_dailywriting_vault(monkeypatch)
    pseudonym = dw_loader.pseudonym_for("990004")
    hidden = tools.get_writing_history(pseudonym, since="2026-01-01", until="2026-12-31")
    shown = tools.get_writing_history(pseudonym, since="2026-01-01", until="2026-12-31", include_text=True, max_text_chars=40)
    assert "raw_text" not in json.dumps(hidden)
    assert "raw_text" in shown["submissions"][0]
    assert len(shown["submissions"][0]["raw_text"]) <= 70


def test_get_writing_history_unknown_pseudonym_is_a_structured_refusal(monkeypatch, tmp_path):
    repo = _build_dailywriting_repo(tmp_path, [])
    _use_dailywriting_repo(monkeypatch, repo)
    _use_dailywriting_vault(monkeypatch)
    result = tools.get_writing_history("Not A Real Pseudonym")
    assert result["ok"] is False
    assert "roster" in result["error"].lower()


def test_get_writing_history_scan_payload_can_actually_go_red():
    verdict = feedback_safety.scan_payload({"submissions": [{"canvas_id": "990001"}]}, _DailyWritingFixtureVault())
    assert verdict["green"] is False


def test_get_writing_history_bad_date_and_inverted_window_are_structured_refusals(monkeypatch, tmp_path):
    _use_dailywriting_vault(monkeypatch)
    _use_dailywriting_repo(monkeypatch, _build_dailywriting_repo(tmp_path, []))
    assert tools.get_writing_history("Whoever", since="not-a-date")["ok"] is False
    assert tools.get_writing_history("Whoever", since="2026-12-31", until="2026-01-01")["ok"] is False


def _write_history_raw_submission(repo, *, text):
    from datetime import datetime

    path = repo.root / "submissions" / "2026-09.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": 1, "submissions": [{
        "submission_id": "raw-history", "rep_id": "rep_t1_phones",
        "canvas_id": "990001", "submitted_at": "2026-09-14T09:12:00-05:00",
        "raw_text": text, "student_word_count": len(text.split()),
        "segments": [], "flags": [], "scrub_findings": [],
    }]}), encoding="utf-8")


def test_get_writing_history_truncates_before_the_gate(monkeypatch, tmp_path):
    from api.dailywriting.fixtures import loader as dw_loader

    repo = _build_dailywriting_repo(tmp_path, [])
    repo.put_rep(dw_loader.rep("rep_t1_phones"))
    _use_dailywriting_repo(monkeypatch, repo)
    _use_dailywriting_vault(monkeypatch)
    pseudonym = dw_loader.pseudonym_for("990001")

    _write_history_raw_submission(repo, text=("filler " * 20) + "990001")
    far = tools.get_writing_history(pseudonym, since="2026-01-01", until="2026-12-31", include_text=True, max_text_chars=50)
    assert far["ok"] is True
    assert "990001" not in json.dumps(far)

    _write_history_raw_submission(repo, text="990001 " + ("filler " * 20))
    near = tools.get_writing_history(pseudonym, since="2026-01-01", until="2026-12-31", include_text=True, max_text_chars=50)
    assert near["ok"] is False
    assert near["violations"]


def test_get_writing_history_refuses_on_vault_conflict(monkeypatch, tmp_path):
    repo = _build_dailywriting_repo(tmp_path, [1])
    _use_dailywriting_repo(monkeypatch, repo)
    monkeypatch.setattr(tools, "_vault_factory", type("ConflictVault", (), {"conflicts": lambda self: ["copy"]}))
    result = tools.get_writing_history("Sparky McGee")
    assert result["ok"] is False
    assert set(result) == {"ok", "error"}
    assert "conflict" in result["error"].lower()

# --- typed mirror-first reads (1.0beta-05) ------------------------------------
#
# roster/assignment/submission acquisition now goes through the typed local
# read service (api/mirror/read_service.py) instead of owning mirror
# store/query calls directly. These tests populate a real on-disk mirror
# (workspace root redirected to tmp_path, same fixture style as
# api/tests/test_mirror_reads_helper.py) and prove (a) a fresh mirror serves
# both get_roster and get_submissions with zero live Canvas calls, and (b)
# any one of the three required scopes (roster, assignments, submissions)
# being stale falls the WHOLE submission bundle back to live as one coherent
# read -- never a partial mirror/live mix.

MIRROR_COURSE = "111"
MIRROR_ASSIGNMENT = {
    "id": 700010, "name": "Essay 1", "due_at": "2026-07-01T23:59:00Z",
    "points_possible": 10, "published": True, "html_url": "https://example.invalid/essay",
}
MIRROR_SUBMISSIONS = [
    {"assignment_id": 700010, "user_id": 900001, "workflow_state": "graded",
     "score": 9, "grade": "9", "submitted_at": "2026-07-01T20:00:00Z",
     "late": False, "missing": False, "excused": False,
     "body": "<p>Learner One and Lee worked together on this.</p>"},
    {"assignment_id": 700010, "user_id": 900002, "workflow_state": "submitted",
     "submitted_at": "2026-07-01T21:00:00Z", "body": "<p>Second submission body.</p>"},
]
_STALE_STAMP = "2000-01-01T00:00:00Z"


def _mount_mirror(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))


def _populate_mirror(root, *, roster_at=None, assignments_at=None, submissions_at=None):
    fresh = mirror_store.now_iso()
    roster_at = roster_at or fresh
    assignments_at = assignments_at or fresh
    submissions_at = submissions_at or fresh
    mirror_store.write_roster(MIRROR_COURSE, FIXTURE_USERS, SECTION_MAP,
                              root=root, attempted_at=roster_at)
    mirror_store.write_assignments(MIRROR_COURSE, [MIRROR_ASSIGNMENT],
                                   root=root, attempted_at=assignments_at)
    mirror_store.merge_submissions(MIRROR_COURSE, "700010", MIRROR_SUBMISSIONS,
                                   root=root, attempted_at=submissions_at, replace=True)
    mirror_store.record_pass(MIRROR_COURSE, "full", ok=True,
                             attempted_at=submissions_at, root=root)


def _explode_live(*_args, **_kwargs):
    raise AssertionError("live Canvas read attempted")


def _forbid_live_reads(monkeypatch):
    """Make any HTTP read reaching Canvas fail the test.

    Patches the seams inside ``canvas_client`` rather than a wrapper
    re-exported into ``tools``, so a read that arrives by any route --
    including a helper that lazily imports ``_canvas_get_all`` at call time,
    the way ``roster_service`` does -- still trips this. ``_canvas_headers``
    is covered alongside the physical GET because every read consults it
    first and bails early when no token is saved; without it the tripwire
    would quietly stop working on a machine with no Canvas token.
    """
    monkeypatch.setattr(canvas_client, "_canvas_headers", _explode_live)
    monkeypatch.setattr(canvas_client, "_physical_get", _explode_live)


def test_get_roster_serves_fresh_typed_mirror_with_zero_live_calls(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, [MIRROR_COURSE])
    _populate_mirror(str(tmp_path))
    _forbid_live_reads(monkeypatch)

    result = tools.get_roster(MIRROR_COURSE)
    assert result["ok"] is True
    assert result["source"] == "mirror"
    assert result["synced_at"]
    roster = _rows(result["roster"])
    assert len(roster) == 2
    section_sets = {tuple(row["section_names"]) for row in roster}
    assert section_sets == {("Period 1",), ("Period 2",)}
    _assert_no_leaks(result)


# --- get_seating_context ----------------------------------------------------

def _set_seating_context(monkeypatch, *, settings=None, matrix=None, relationships=None):
    monkeypatch.setattr(tools.config, "get_roster_student_settings", lambda course_id: settings or {})
    monkeypatch.setattr(tools.config, "get_roster_score_matrix", lambda course_id: matrix or {})
    monkeypatch.setattr(tools.config, "get_roster_relationships", lambda course_id: relationships or {})
    monkeypatch.setattr(tools.config, "active_protected_names", lambda: set())


def test_get_seating_context_is_mirror_only_pseudonymized_and_scrubbed(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    vault_path = _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, [MIRROR_COURSE])
    users = [dict(FIXTURE_USERS[0]), dict(FIXTURE_USERS[1])]
    users[1]["enrollments"] = [{"course_section_id": 800001}]
    mirror_store.write_roster(MIRROR_COURSE, users, {"800001": "Period 1"}, root=str(tmp_path))
    _set_seating_context(
        monkeypatch,
        settings={
            "900001": {"seating_context": {
                "front_row": "required", "near_teacher": "none",
                "private_note": "private only", "ai_context_note": "Lee needs a calm start.",
            }},
            "900002": {"seating_context": {
                "front_row": "none", "near_teacher": "preferred",
                "private_note": "private only", "ai_context_note": "",
            }},
        },
        matrix={
            "columns": [{"id": "score-writing", "label": "Learner One writing"}],
            "values_by_section": {"800001": {
                "900001": {"score-writing": 4}, "900002": {"score-writing": 3},
            }},
        },
        relationships={"by_section": {"800001": [{
            "student_a": "900001", "student_b": "900002",
            "type": "keep_apart", "reason": "private local reason",
        }]}},
    )
    _forbid_live_reads(monkeypatch)

    result = tools.get_seating_context(MIRROR_COURSE, "Period 1")

    assert result["ok"] is True
    assert result["source"] == "mirror+local"
    assert len(result["students"]) == 2
    assert result["students"] == sorted(result["students"], key=lambda item: item["pseudonym"])
    assert all(set(item) == {"pseudonym", "supports", "scores", "ai_context_note"}
               for item in result["students"])
    assert all(item["scores"] for item in result["students"])
    assert len(result["relationships"]) == 1
    assert set(result["relationships"][0]) == {"type", "students"}
    assert result["relationships"][0]["students"] == sorted(result["relationships"][0]["students"])
    assert "private local reason" not in json.dumps(result)
    assert "private only" not in json.dumps(result)
    _assert_no_leaks(result)
    assert feedback_safety.scan_payload(result, Vault(vault_path))["green"] is True


def test_get_seating_context_withholds_missing_or_ambiguous_section(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, [MIRROR_COURSE])
    mirror_store.write_roster(
        MIRROR_COURSE, FIXTURE_USERS,
        {"800001": "Period", "800002": "Period"}, root=str(tmp_path),
    )
    _set_seating_context(monkeypatch)

    for section_name in ("Missing", "Period"):
        result = tools.get_seating_context(MIRROR_COURSE, section_name)
        assert result["ok"] is False
        assert set(result) == {"ok", "error"}
        assert "800001" not in result["error"] and "800002" not in result["error"]


def test_get_seating_context_refuses_stale_mirror_and_vault_conflict(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, [MIRROR_COURSE])
    mirror_store.write_roster(
        MIRROR_COURSE, FIXTURE_USERS, SECTION_MAP,
        root=str(tmp_path), attempted_at=_STALE_STAMP,
    )
    _set_seating_context(monkeypatch)
    _forbid_live_reads(monkeypatch)
    assert tools.get_seating_context(MIRROR_COURSE, "Period 1") == {
        "ok": False, "error": tools._MIRROR_UNAVAILABLE_ROSTER_ERROR,
    }

    class ConflictedVault:
        def conflicts(self):
            return ["vault conflict.json"]

    monkeypatch.setattr(tools, "_vault_factory", ConflictedVault)
    result = tools.get_seating_context(MIRROR_COURSE, "Period 1")
    assert result["ok"] is False
    assert "conflict" in result["error"].lower()


def test_get_submissions_serves_fresh_typed_mirror_with_zero_live_calls(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, [MIRROR_COURSE])
    _populate_mirror(str(tmp_path))
    _forbid_live_reads(monkeypatch)

    result = tools.get_submissions(MIRROR_COURSE, "700010")
    assert result["ok"] is True
    assert result["source"] == "mirror"
    assert result["synced_at"]
    assert result["assignment"]["title"] == "Essay 1"
    subs = _rows(result["submissions"])
    assert len(subs) == 2  # locally filtered to just this assignment's rows
    _assert_no_leaks(result)


def test_get_submissions_refuses_when_roster_stale(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, [MIRROR_COURSE])
    _populate_mirror(str(tmp_path), roster_at=_STALE_STAMP)
    monkeypatch.setattr(gradebook_queries, "assignment", _explode_live)
    monkeypatch.setattr(gradebook_queries, "assignment_submissions", _explode_live)
    monkeypatch.setattr(roster_service, "fetch_students", _explode_live)

    assert tools._mirror_submission_bundle(MIRROR_COURSE, "700010") == (None, None)
    result = tools.get_submissions(MIRROR_COURSE, "700010")
    assert result == {"ok": False, "error": tools._MIRROR_UNAVAILABLE_SUBMISSIONS_ERROR}


def test_get_submissions_refuses_when_assignments_stale(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, [MIRROR_COURSE])
    _populate_mirror(str(tmp_path), assignments_at=_STALE_STAMP)
    monkeypatch.setattr(gradebook_queries, "assignment", _explode_live)
    monkeypatch.setattr(gradebook_queries, "assignment_submissions", _explode_live)
    monkeypatch.setattr(roster_service, "fetch_students", _explode_live)

    assert tools._mirror_submission_bundle(MIRROR_COURSE, "700010") == (None, None)
    result = tools.get_submissions(MIRROR_COURSE, "700010")
    assert result == {"ok": False, "error": tools._MIRROR_UNAVAILABLE_SUBMISSIONS_ERROR}


def test_get_submissions_refuses_when_submissions_stale(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, [MIRROR_COURSE])
    _populate_mirror(str(tmp_path), submissions_at=_STALE_STAMP)
    monkeypatch.setattr(gradebook_queries, "assignment", _explode_live)
    monkeypatch.setattr(gradebook_queries, "assignment_submissions", _explode_live)
    monkeypatch.setattr(roster_service, "fetch_students", _explode_live)

    assert tools._mirror_submission_bundle(MIRROR_COURSE, "700010") == (None, None)
    result = tools.get_submissions(MIRROR_COURSE, "700010")
    assert result == {"ok": False, "error": tools._MIRROR_UNAVAILABLE_SUBMISSIONS_ERROR}


# --- get_gradebook_snapshot ---------------------------------------------------

def test_get_gradebook_snapshot_happy(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    root = str(tmp_path)
    mirror_store.write_roster("111", GRADEBOOK_STUDENTS, {}, root=root)
    mirror_store.write_assignments("111", GRADEBOOK_ASSIGNMENTS, root=root)
    mirror_store.merge_submissions("111", "700010", GRADEBOOK_SUBS, root=root, replace=True)
    for pass_name in ("full", "roster"):
        mirror_store.record_pass("111", pass_name, ok=True, root=root)

    result = tools.get_gradebook_snapshot("111")
    assert result["ok"] is True
    assert result["class_avg"] == 90.0
    assert result["student_count"] == 2
    assert _rows(result["assignments"]) == [{
        "id": "700010", "title": "Quiz 1", "due_at": "2026-07-01",
        "points": 10, "submitted": 2, "graded": 1, "missing": 0, "late": 0, "avg_pct": 90,
    }]
    assert result["students"]["columns"] == ["pseudonym", "missing", "late", "ungraded", "pct"]
    assert len(result["students"]["rows"]) == 2
    _assert_no_leaks(result)


def test_get_gradebook_snapshot_empty(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    root = str(tmp_path)
    mirror_store.write_roster("111", [], {}, root=root)
    mirror_store.write_assignments("111", [], root=root)
    mirror_store.merge_submissions("111", "700010", [], root=root, replace=True)
    for pass_name in ("full", "roster"):
        mirror_store.record_pass("111", pass_name, ok=True, root=root)

    result = tools.get_gradebook_snapshot("111")
    assert result["ok"] is True
    assert result["class_avg"] is None
    assert result["student_count"] == 0
    assert result["assignments"]["rows"] == []
    assert result["students"]["rows"] == []


def test_get_gradebook_snapshot_failure(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    # No mirror seeded at all: a whole-course snapshot is refused, never live.

    assert tools.get_gradebook_snapshot("111") == {
        "ok": False, "error": tools._MIRROR_UNAVAILABLE_SNAPSHOT_ERROR}


def test_get_gradebook_snapshot_rejects_non_current_course(monkeypatch, tmp_path):
    _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["222"])
    result = tools.get_gradebook_snapshot("111")
    assert result["ok"] is False
    assert "not a Current course" in result["error"]


# --- pseudonym round trip -----------------------------------------------------

def test_pseudonym_reverse_round_trip(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    vault_path = _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    mirror_store.write_roster("111", FIXTURE_USERS, SECTION_MAP, root=str(tmp_path))

    result = tools.get_roster("111")
    assert result["ok"] is True
    pseudonym_value = _rows(result["roster"])[0]["pseudonym"]

    fresh_vault = Vault(vault_path)  # re-open from disk, not the in-memory instance
    reversed_entry = fresh_vault.reverse(pseudonym_value)
    assert reversed_entry is not None
    assert reversed_entry["real_name"] in {"Learner One", "Learner Two"}
    assert reversed_entry["canvas_id"] in {"900001", "900002"}


# --- no-PII sweep + scan_payload green ---------------------------------------

def test_no_pii_sweep_and_scan_payload_green(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    vault_path = _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    root = str(tmp_path)
    mirror_store.write_roster("111", GRADEBOOK_STUDENTS, {}, root=root)
    mirror_store.write_assignments("111", GRADEBOOK_ASSIGNMENTS, root=root)
    mirror_store.merge_submissions("111", "700010", GRADEBOOK_SUBS, root=root, replace=True)
    for pass_name in ("full", "roster"):
        mirror_store.record_pass("111", pass_name, ok=True, root=root)

    result = tools.get_gradebook_snapshot("111")
    assert result["ok"] is True
    _assert_no_leaks(result)

    fresh_vault = Vault(vault_path)
    verdict = feedback_safety.scan_payload(result, fresh_vault)
    assert verdict["green"] is True
    assert verdict["hard"] == []


def test_no_pii_sweep_scan_payload_green_for_submissions(monkeypatch, tmp_path):
    _mount_mirror(monkeypatch, tmp_path)
    vault_path = _use_vault(monkeypatch, tmp_path)
    _set_active_courses(monkeypatch, ["111"])
    root = str(tmp_path)
    mirror_store.write_roster("111", FIXTURE_USERS, SECTION_MAP, root=root)
    mirror_store.write_assignments("111", [MIRROR_ASSIGNMENT], root=root)
    mirror_store.merge_submissions("111", "700010", [
        {"assignment_id": 700010, "user_id": 900001, "workflow_state": "graded", "score": 9,
         "grade": "9", "submitted_at": "2026-07-01T20:00:00Z", "late": False, "missing": False,
         "excused": False, "body": "<p>Learner One and Lee worked together on this.</p>"},
    ], root=root, replace=True)
    mirror_store.record_pass("111", "full", ok=True, root=root)

    result = tools.get_submissions("111", "700010")
    assert result["ok"] is True

    fresh_vault = Vault(vault_path)
    verdict = feedback_safety.scan_payload(result, fresh_vault)
    assert verdict["green"] is True
    assert verdict["hard"] == []
    assert verdict["soft"] == []  # the scrub caught every roster name; nothing left to flag


# --- gate fail-closed ---------------------------------------------------------

def test_gate_fails_closed_on_leaking_identity_key(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    vault.get_or_assign("900001", "Leaked Real Name", "SIS-900001")

    leaking_payload = {"roster": [{"pseudonym": "Whatever Fake Name", "name": "Leaked Real Name"}]}
    result = pseudonym.gate(leaking_payload, vault)

    assert result["ok"] is False
    assert set(result.keys()) == {"ok", "error", "violations"}
    assert result["violations"]
    dumped = json.dumps(result)
    assert "Leaked Real Name" not in dumped
    assert "SIS-900001" not in dumped


def test_gate_passes_clean_payload_through(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    clean_payload = {"roster": [{"pseudonym": "Whatever Fake Name", "section_names": ["Period 1"]}]}
    result = pseudonym.gate(clean_payload, vault)
    assert result == {"ok": True, **clean_payload}


# --- id-in-free-text through the full gate (proactive scrub + fail-closed backstop) --

def test_gate_after_submission_scrub_lets_id_in_text_through_as_placeholder(tmp_path):
    """A student's real Canvas id typed into a submission body is scrubbed to
    the neutral placeholder by pseudonymize_submission_rows, so the gate sees
    clean text and passes it through -- the raw id never survives."""
    vault = Vault(str(tmp_path / "vault.json"))
    vault.get_or_assign("900123", "Jordan Rivera", "50055")
    subs = [{"user_id": "900123", "workflow_state": "graded", "body":
             "<p>My canvas number is 900123, please grade my essay.</p>"}]
    rows = pseudonym.pseudonymize_submission_rows(vault, subs)
    assert "900123" not in rows[0]["text"]
    assert feedback_scrub.ID_PLACEHOLDER in rows[0]["text"]

    result = pseudonym.gate({"submissions": rows}, vault)
    assert result["ok"] is True


def test_gate_hard_blocks_unscrubbed_id_in_text_field_and_sanitizes_violation(tmp_path):
    """If a >= 5 char real id somehow lands in an un-scrubbed text field of the
    assembled payload (a scrub-pipeline bug), the gate must fail closed, and
    the violation string returned to the MCP client must never contain the
    raw id value -- only _sanitize_violation's generic description."""
    vault = Vault(str(tmp_path / "vault.json"))
    vault.get_or_assign("900456", "Learner Two", "50099")
    leaking_payload = {"submissions": [{"pseudonym": "Whatever Fake Name",
                                        "text": "my canvas number is 900456 today"}]}
    result = pseudonym.gate(leaking_payload, vault)
    assert result["ok"] is False
    dumped = json.dumps(result)
    assert "900456" not in dumped
    for violation in result["violations"]:
        assert "900456" not in violation


# --- refresh_mirror -------------------------------------------------------------

def test_refresh_mirror_accepts_previous_course(monkeypatch):
    _set_previous_course(monkeypatch)
    monkeypatch.setattr(tools, "_enqueue_sync", lambda course_id, scopes=None: "plan-1")
    monkeypatch.setattr(tools, "_wait_for_plan",
                        lambda plan_id, **kwargs: {"state": "succeeded"})
    result = tools.refresh_mirror("111")
    assert result == {
        "ok": True,
        "status": "synced",
        "message": "Mirror refreshed. Re-read the data now.",
    }


def test_refresh_mirror_reports_synced_on_success(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(tools, "_enqueue_sync", lambda course_id, scopes=None: "plan-1")
    monkeypatch.setattr(tools, "_wait_for_plan",
                        lambda plan_id, **kwargs: {"state": "succeeded"})

    result = tools.refresh_mirror("111")
    assert result["ok"] is True
    assert result["status"] == "synced"


def test_refresh_mirror_enqueues_roster_pass(monkeypatch):
    """refresh_mirror must drive a roster pass, not a delta alone — otherwise a
    roster aged past the serve window is unrecoverable through this tool (the
    delta never rewrites the roster file, so get_roster keeps refusing)."""
    _set_active_courses(monkeypatch, ["111"])
    captured = {}
    monkeypatch.setattr(tools, "_enqueue_sync",
                        lambda course_id, scopes=None: captured.update(
                            course_id=course_id, scopes=scopes) or "plan-1")
    monkeypatch.setattr(tools, "_wait_for_plan",
                        lambda plan_id, **kwargs: {"state": "succeeded"})

    result = tools.refresh_mirror("111")
    assert result["ok"] is True
    assert captured["course_id"] == "111"
    assert "roster" in captured["scopes"]
    assert "course.refresh" in captured["scopes"]


def test_refresh_mirror_reports_syncing_while_running(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(tools, "_enqueue_sync", lambda course_id, scopes=None: "plan-1")
    monkeypatch.setattr(tools, "_wait_for_plan",
                        lambda plan_id, **kwargs: {"state": "running"})

    result = tools.refresh_mirror("111")
    assert result["ok"] is True
    assert result["status"] == "syncing"


def test_refresh_mirror_reports_failure(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])
    monkeypatch.setattr(tools, "_enqueue_sync", lambda course_id, scopes=None: "plan-1")
    monkeypatch.setattr(tools, "_wait_for_plan",
                        lambda plan_id, **kwargs: {"state": "failed"})

    result = tools.refresh_mirror("111")
    assert result["ok"] is False
    assert result["status"] == "failed"


def test_refresh_mirror_enqueue_value_error_maps_to_ok_false(monkeypatch):
    _set_active_courses(monkeypatch, ["111"])

    def _raise(course_id, scopes=None):
        raise ValueError("Not a Current course.")

    monkeypatch.setattr(tools, "_enqueue_sync", _raise)

    assert tools.refresh_mirror("111") == {"ok": False, "error": "Not a Current course."}


# --- server wiring -------------------------------------------------------------

def test_server_registers_the_expected_tool_set():
    from api.mcp_server.server import mcp

    tool_names = set(mcp._tool_manager._tools.keys())
    assert tool_names == {
        "list_courses", "list_sections", "get_course_assignments", "get_modules",
        "get_roster", "get_seating_context", "get_submissions",
        "get_writing_history", "get_gradebook_snapshot", "refresh_mirror",
        "get_authoring_contract", "get_product_guide", "list_staged_content",
        "get_bell_schedule", "get_day_schedule", "get_teacher_schedule",
        "save_deck", "save_teacher_schedule",
        "get_school_calendar",
        "preview_school_calendar_replacement", "apply_school_calendar_replacement",
        "preview_school_calendar_change", "apply_school_calendar_change",
        "preview_school_calendar_event_change", "apply_school_calendar_event_change",
        "get_course_pages", "list_learning_objectives", "preview_learning_objective",
            "apply_learning_objective", "delete_learning_objective",
            "list_active_decks", "archive_deck",
            "get_roster_student_settings", "preview_roster_student_change",
            "apply_roster_student_change", "clear_roster_student_field",
        "list_scoring_sessions", "get_scoring_packet", "stage_scores",
        "get_theme_contract", "list_panel_themes", "list_theme_art",
        "preview_panel_theme", "apply_panel_theme", "delete_panel_theme",
        }


def test_server_wrappers_return_compact_json(monkeypatch):
    from api.mcp_server import server

    monkeypatch.setattr(tools.config, "saved_courses", lambda: [
        {"id": "111", "name": "Algebra I", "nickname": "", "active": True},
    ])
    monkeypatch.setattr(
        tools.mirror_store, "read_course_context",
        lambda cid: {"lifecycle": "current"},
    )
    wire = server.list_courses()
    assert isinstance(wire, str)
    assert "\n" not in wire and ": " not in wire and ", " not in wire
    assert json.loads(wire) == tools.list_courses()


# --- save_teacher_schedule (no course_id, no student data -> no gates) ------

def _teacher_schedule_workspace(monkeypatch, tmp_path):
    workspace_root = tmp_path / "workspace"
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(workspace_root))
    monkeypatch.setattr(
        workspace, "library_folder", lambda name: str(workspace_root / "Library" / name)
    )
    smartdecks = workspace_root / "Library" / "SmartDecks"
    calendars = workspace_root / "Library" / "Calendars"
    smartdecks.mkdir(parents=True)
    calendars.mkdir(parents=True)
    (calendars / "Bell Schedule - Example.csv").write_text(
        "period_id,start,end\n"
        "1,08:00,08:45\n"
        "2,08:50,09:35\n"
        "3,09:40,10:25\n"
        "4,10:30,11:15\n"
        "5,11:20,12:05\n"
        "6,12:10,12:55\n"
        "7,13:00,13:45\n"
        "8,13:50,14:35\n",
        encoding="utf-8",
    )
    return smartdecks / "Teacher Schedule.json"


def test_save_teacher_schedule_writes_blocks_and_returns_path(monkeypatch, tmp_path):
    path = _teacher_schedule_workspace(monkeypatch, tmp_path)
    blocks = [{"name": "Algebra", "raw_periods": [1]}]

    result = tools.save_teacher_schedule(blocks)

    assert result == {"ok": True, "count": 1, "path": str(path)}
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["blocks"] == blocks
    assert saved["version"] == "1.0-json"


def test_save_teacher_schedule_preserves_unknown_keys_and_block_order(monkeypatch, tmp_path):
    path = _teacher_schedule_workspace(monkeypatch, tmp_path)
    original = {
        "_comment": "keep this",
        "version": "custom-version",
        "unknown": {"source": "hand"},
        "blocks": [],
    }
    path.write_text(json.dumps(original), encoding="utf-8")
    blocks = [
        {"name": "Later", "raw_periods": [2]},
        {"name": "Earlier", "raw_periods": [1]},
    ]

    result = tools.save_teacher_schedule(blocks)

    assert result["ok"] is True
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["_comment"] == original["_comment"]
    assert saved["version"] == original["version"]
    assert saved["unknown"] == original["unknown"]
    assert saved["blocks"] == blocks


def test_save_teacher_schedule_preserves_course_id(monkeypatch, tmp_path):
    path = _teacher_schedule_workspace(monkeypatch, tmp_path)
    monkeypatch.setattr(tools.config, "active_courses",
                        lambda: [{"id": "9000001", "name": "Algebra", "active": True}])
    blocks = [{
        "name": "Algebra",
        "raw_periods": [1],
        "label": "Math 7",
        "course_id": "9000001",
        "custom": {"keep": True},
    }]

    result = tools.save_teacher_schedule(blocks)

    assert result["ok"] is True
    assert json.loads(path.read_text(encoding="utf-8"))["blocks"] == blocks


def test_save_teacher_schedule_rejects_non_string_course_id(monkeypatch, tmp_path):
    path = _teacher_schedule_workspace(monkeypatch, tmp_path)
    result = tools.save_teacher_schedule([
        {"name": "Algebra", "raw_periods": [1], "course_id": 9000001},
    ])
    assert result == {
        "ok": False,
        "problems": ["block 'Algebra' course_id must be a string"],
    }
    assert not path.exists()


def test_save_teacher_schedule_rejects_invalid_blocks_without_writing(monkeypatch, tmp_path):
    path = _teacher_schedule_workspace(monkeypatch, tmp_path)
    original = '{"_comment":"keep","blocks":[{"name":"Old","raw_periods":[1]}]}'
    path.write_text(original, encoding="utf-8")

    result = tools.save_teacher_schedule([{"name": "", "raw_periods": []}])

    assert result["ok"] is False
    assert result["problems"] == [
        "block at index 0 needs a non-empty string name",
        "block '' must have a non-empty list of ints or non-empty strings for raw_periods",
    ]
    assert path.read_text(encoding="utf-8") == original


def test_save_teacher_schedule_rejects_non_list(monkeypatch, tmp_path):
    _teacher_schedule_workspace(monkeypatch, tmp_path)
    result = tools.save_teacher_schedule({"name": "Algebra"})
    assert result == {"ok": False, "problems": ["blocks must be a list"]}


def test_save_teacher_schedule_rejects_intersecting_duplicate_names(monkeypatch, tmp_path):
    _teacher_schedule_workspace(monkeypatch, tmp_path)
    blocks = [
        {"name": "Shared", "raw_periods": [1]},
        {"name": "Shared", "raw_periods": [2]},
    ]
    result = tools.save_teacher_schedule(blocks)
    assert result["ok"] is False
    assert result["problems"] == ["block 'Shared' must be unique"]


def test_save_teacher_schedule_rejects_duplicate_names_even_when_periods_differ(monkeypatch, tmp_path):
    path = _teacher_schedule_workspace(monkeypatch, tmp_path)
    blocks = [
        {"name": "Shared", "raw_periods": [1]},
        {"name": "Shared", "raw_periods": [2]},
    ]
    result = tools.save_teacher_schedule(blocks)
    assert result == {"ok": False, "problems": ["block 'Shared' must be unique"]}
    assert not path.exists()


def test_save_teacher_schedule_rejects_unknown_period(monkeypatch, tmp_path):
    path = _teacher_schedule_workspace(monkeypatch, tmp_path)
    result = tools.save_teacher_schedule([{"name": "Unknown", "raw_periods": [99]}])
    assert result == {
        "ok": False,
        "problems": ["block 'Unknown': period '99' not found in any bell schedule"],
    }
    assert not path.exists()


def test_server_registers_save_teacher_schedule_wrapper(monkeypatch):
    from api.mcp_server import server

    monkeypatch.setattr(tools, "save_teacher_schedule", lambda blocks: {
        "ok": True, "count": len(blocks), "path": "Teacher Schedule.json",
    })
    wire = server.save_teacher_schedule([{"name": "Algebra", "raw_periods": [1]}])
    assert json.loads(wire) == {
        "ok": True, "count": 1, "path": "Teacher Schedule.json",
    }


def test_server_registers_get_school_calendar_wrapper(monkeypatch):
    from api.mcp_server import server

    monkeypatch.setattr(tools, "get_school_calendar", lambda date_from, date_to: {
        "ok": True, "readiness": {"status": "ready"},
    })
    wire = server.get_school_calendar("2026-08-17", "2026-08-21")
    assert json.loads(wire) == {"ok": True, "readiness": {"status": "ready"}}


def test_server_registers_preview_school_calendar_replacement_wrapper(monkeypatch):
    from api.mcp_server import server

    monkeypatch.setattr(tools, "preview_school_calendar_replacement", lambda *args: {
        "ok": True, "operation": "create", "base_revision": 0,
        "proposed_school_year": "2026-27",
    })
    wire = server.preview_school_calendar_replacement(
        "2026-27", "2026-08-17", "2027-06-04", "ordinary"
    )
    assert json.loads(wire) == {
        "ok": True, "operation": "create", "base_revision": 0,
        "proposed_school_year": "2026-27",
    }


def test_server_registers_apply_school_calendar_replacement_wrapper(monkeypatch):
    from api.mcp_server import server

    monkeypatch.setattr(tools, "apply_school_calendar_replacement",
                        lambda preview, expected_revision: {
        "ok": True, "revision": 1, "school_year": "2026-27",
        "coverage": {"start": "2026-08-17", "end": "2027-06-04"}, "day_count": 292,
    })
    wire = server.apply_school_calendar_replacement({"base_revision": 0}, 0)
    assert json.loads(wire) == {
        "ok": True, "revision": 1, "school_year": "2026-27",
        "coverage": {"start": "2026-08-17", "end": "2027-06-04"}, "day_count": 292,
    }


def test_server_registers_preview_school_calendar_change_wrapper(monkeypatch):
    from api.mcp_server import server

    monkeypatch.setattr(tools, "preview_school_calendar_change", lambda *args: {
        "ok": True, "base_revision": 1, "affected": [], "is_noop": True,
    })
    wire = server.preview_school_calendar_change("no_school", "", "Field day")
    assert json.loads(wire) == {
        "ok": True, "base_revision": 1, "affected": [], "is_noop": True,
    }


def test_server_registers_apply_school_calendar_change_wrapper(monkeypatch):
    from api.mcp_server import server

    monkeypatch.setattr(tools, "apply_school_calendar_change", lambda preview, expected_revision: {
        "ok": True, "revision": expected_revision + 1,
    })
    wire = server.apply_school_calendar_change({"base_revision": 1}, 1)
    assert json.loads(wire) == {"ok": True, "revision": 2}


def test_server_registers_event_calendar_wrappers(monkeypatch):
    from api.mcp_server import server

    monkeypatch.setattr(tools, "preview_school_calendar_event_change", lambda *args: {
        "ok": True, "operation": "event_change", "base_revision": 1,
        "before": None, "after": {"id": "game-1"},
    })
    wire = server.preview_school_calendar_event_change("upsert", {"id": "game-1"})
    assert json.loads(wire)["operation"] == "event_change"
    monkeypatch.setattr(tools, "apply_school_calendar_event_change", lambda preview, expected_revision: {
        "ok": True, "revision": expected_revision + 1,
    })
    wire = server.apply_school_calendar_event_change({"base_revision": 1}, 1)
    assert json.loads(wire) == {"ok": True, "revision": 2}

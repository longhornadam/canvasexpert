"""Landing a staged draft in Canvas from the chat.

The pair is deliberately thin: it resolves one staged label, hands the same
prepare request the push tab hands the adapter, and applies through the same
Operation Ledger executor. What these tests hold down is the boundary around
that -- which drafts it can reach, which options each kind accepts, and what
crosses back out to the client.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from api import content_push, runtime_paths
from api.mcp_server import server, tools
from api.operation_ledger import models
from api.platform_services import config, workspace


@pytest.fixture(autouse=True)
def _workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def _current_course(monkeypatch):
    monkeypatch.setattr(config, "active_courses", lambda: [
        {"id": "course-x", "name": "Invented Course", "active": True},
    ])


def _stage(kind: str, name: str, body: str = "<ENVELOPE>draft</ENVELOPE>") -> str:
    """Drop a marker-gated draft in the per-kind Inbox, as an assistant would."""
    folder = runtime_paths.inbox_folder(kind)
    path = os.path.join(str(folder), f"{name}.txt")
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(body)
    with open(path + ".done", "w", encoding="utf-8") as handle:
        handle.write(str(len(body.encode("utf-8"))))
    return path


class RecordingAdapter:
    """Stands in for one ledger adapter and records what it was handed."""

    def __init__(self, kind="content.page"):
        self.kind = kind
        self.requests = []

    def build_payload(self, request):
        self.requests.append(dict(request))
        return {"title": "Invented Page", "source_path": request.get("path")}

    def source_digest(self, payload):
        return models.sha256_dict(payload)

    def verify_targets(self, payload, targets):
        return [{
            "course_id": targets[0]["course_id"],
            "target_key": "target-key",
            "idempotency_key": "idempotency-key",
        }]

    def capture_baseline(self, payload, target):
        return {"existing_page": None}

    def freeze_review(self, payload, target, baseline):
        return {
            "course_name": "Invented Course",
            "page_title": payload["title"],
            "baseline_has_existing_page": False,
            "dependencies": [{"type": "printable", "path": r"C:\private\packet.pdf"}],
        }


@pytest.fixture
def _adapter(monkeypatch, tmp_path):
    """One recording adapter behind a ledger writing to a temp private root."""
    from api.operation_ledger import paths

    monkeypatch.setattr(paths, "private_root", lambda: tmp_path / "private")
    adapter = RecordingAdapter()
    monkeypatch.setattr(content_push.registry, "get_adapter", lambda _kind: adapter)
    return adapter


# --- delegation ----------------------------------------------------------------

def test_tools_delegate_to_the_shared_use_case(monkeypatch):
    seen = {}

    def preview(course_id, kind, label, **options):
        seen["preview"] = (course_id, kind, label, options)
        return {"ok": True}

    monkeypatch.setattr(content_push, "preview_content_push", preview)
    monkeypatch.setattr(content_push, "apply_content_push",
                        lambda *coordinates: {"ok": True, "coordinates": coordinates})

    result = tools.preview_content_push(
        "course-x", "page", "welcome.txt", published=True, module_name="Unit 3")

    assert seen["preview"][:3] == ("course-x", "page", "welcome.txt")
    assert seen["preview"][3]["published"] is True
    assert seen["preview"][3]["module_name"] == "Unit 3"
    assert result["next"] == tools._NEXT_STEPS["preview_content_push"]

    applied = tools.apply_content_push("op", "batch", "digest")
    assert applied["coordinates"] == ("op", "batch", "digest")
    # A refusal carries no post-call procedure: there is nothing to apply.
    monkeypatch.setattr(content_push, "preview_content_push",
                        lambda *a, **k: {"ok": False, "error": "no"})
    assert "next" not in tools.preview_content_push("course-x", "page", "gone")


# --- what the pair can reach ---------------------------------------------------

def test_preview_freezes_one_staged_draft_for_one_course(_adapter):
    _stage("page", "welcome")

    result = content_push.preview_content_push("course-x", "page", "welcome.txt")

    assert result["ok"] is True
    assert result["kind"] == "page"
    assert result["operation_id"] and result["batch_id"] and result["review_digest"]
    assert result["preview"]["page_title"] == "Invented Page"
    assert _adapter.requests == [{
        "path": os.path.abspath(str(runtime_paths.inbox_folder("page") / "welcome.txt")),
        "published": False,
    }]


def test_preview_never_returns_a_local_path(_adapter):
    """The label goes in, the label comes back; the Inbox path stays home.

    The adapter above returns a printable dependency path that no option on
    this boundary can set, standing in for a future adapter field.
    """
    _stage("page", "welcome")

    result = content_push.preview_content_push("course-x", "page", "welcome")
    serialized = server._compact(result)

    assert result["preview"]["dependencies"] == [{"type": "printable"}]
    assert "packet.pdf" not in serialized
    assert "To Review" not in serialized


def test_a_label_resolves_loosely(_adapter):
    _stage("page", "Welcome Letter")

    assert content_push.preview_content_push(
        "course-x", "page", "welcome letter")["ok"] is True
    assert content_push.preview_content_push(
        "course-x", "page", "Welcome Letter.txt")["ok"] is True


def test_a_label_matching_two_drafts_is_refused_rather_than_guessed(
    _adapter, monkeypatch,
):
    """Two drafts differing only by case cannot coexist on Windows, so this
    stubs the listing rather than the filesystem: the guard has to hold on a
    case-sensitive machine too."""
    monkeypatch.setattr(content_push.deps, "list_inbox_files", lambda _kind: [
        {"label": "Welcome Letter.txt", "path": r"C:\a\Welcome Letter.txt"},
        {"label": "welcome letter.txt", "path": r"C:\a\welcome letter.txt"},
    ])

    result = content_push.preview_content_push("course-x", "page", "welcome letter")

    assert result["ok"] is False
    assert "more than one" in result["error"]
    assert _adapter.requests == []


def test_an_unknown_label_names_what_is_actually_staged(_adapter):
    _stage("page", "welcome")

    result = content_push.preview_content_push("course-x", "page", "farewell")

    assert result["ok"] is False
    assert "welcome.txt" in result["error"]
    assert _adapter.requests == []


def test_an_unstaged_kind_points_back_at_staging(_adapter):
    result = content_push.preview_content_push("course-x", "quiz", "unit-3")

    assert result["ok"] is False
    assert "get_authoring_contract" in result["error"]


def test_a_draft_the_marker_does_not_cover_is_not_reachable(_adapter):
    """Half-synced drafts are invisible to the push, as they are to the push tab."""
    _stage("page", "welcome", body="original body")
    path = str(runtime_paths.inbox_folder("page") / "welcome.txt")
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write("a much longer body than the marker records")

    result = content_push.preview_content_push("course-x", "page", "welcome")

    assert result["ok"] is False
    assert "no page draft is staged" in result["error"]


def test_only_a_current_course_can_be_pushed_to(_adapter):
    _stage("page", "welcome")

    result = content_push.preview_content_push("course-y", "page", "welcome")

    assert result == {"ok": False, "error": "course is not in Current courses"}
    assert _adapter.requests == []


def test_an_unknown_kind_is_refused_before_anything_is_read(_adapter):
    result = content_push.preview_content_push("course-x", "module", "welcome")

    assert result["ok"] is False
    assert "unknown kind 'module'" in result["error"]
    assert _adapter.requests == []


# --- delivery options ----------------------------------------------------------

def test_an_option_a_kind_cannot_carry_is_refused_not_dropped(_adapter):
    _stage("page", "welcome")

    result = content_push.preview_content_push(
        "course-x", "page", "welcome", due_at="2026-09-11T23:59:00Z")

    assert result["ok"] is False
    assert "a page push does not take due_at" in result["error"]
    assert "module_name" in result["error"]
    assert _adapter.requests == []


def test_assignment_options_reach_the_adapter_verbatim(_adapter):
    _stage("assignment", "essay-1")

    content_push.preview_content_push(
        "course-x", "assignment", "essay-1", published=True,
        module_name="Unit 3", assignment_group_name="Essays",
        due_at="2026-09-11T23:59:00Z", post_to_sis=True)

    assert _adapter.requests == [{
        "path": os.path.abspath(
            str(runtime_paths.inbox_folder("assignment") / "essay-1.txt")),
        "published": True,
        "post_to_sis": True,
        "module_name": "Unit 3",
        "assignment_group_name": "Essays",
        "due_at": "2026-09-11T23:59:00Z",
    }]


def test_a_quiz_carries_its_options_as_push_settings(_adapter):
    _stage("quiz", "unit-3-check")

    content_push.preview_content_push(
        "course-x", "quiz", "unit-3-check", published=True,
        due_at="2026-09-11T23:59:00Z")

    request = _adapter.requests[0]
    assert request["mode"] == "whole"
    assert request["settings"] == {
        "published": True, "due_at": "2026-09-11T23:59:00Z",
    }


def test_a_draft_stays_unpublished_unless_asked(_adapter):
    _stage("rubric", "essay-rubric")

    content_push.preview_content_push("course-x", "rubric", "essay-rubric")

    assert _adapter.requests[0]["published"] is False


# --- apply ---------------------------------------------------------------------

def test_apply_lands_only_a_content_operation(monkeypatch):
    monkeypatch.setattr(content_push.operations, "get_operation", lambda _id: {
        "operation_id": "op-1", "kind": "gradebook.sis_bridge",
    })

    result = content_push.apply_content_push("op-1", "batch-1", "digest-1")

    assert result == {"ok": False, "error": "content push operation was not found"}


def test_apply_requires_all_three_coordinates():
    assert content_push.apply_content_push("op-1", "", "digest")["ok"] is False
    assert content_push.apply_content_push("", "batch", "digest")["ok"] is False
    assert content_push.apply_content_push("op-1", "batch", "")["ok"] is False


def test_apply_reports_what_landed_without_ledger_internals(monkeypatch):
    monkeypatch.setattr(content_push.operations, "get_operation", lambda _id: {
        "operation_id": "op-1", "kind": "content.page",
    })
    monkeypatch.setattr(content_push.executor, "apply_operation", lambda *_a: {
        "ok": True,
        "operation_id": "op-1",
        "status": "applied",
        "target_results": [{
            "target_key": "target-key",
            "state": "applied",
            "returned_object_id": "9001",
            "returned_object_url": "https://canvas.invalid/courses/1/pages/welcome",
            "error_code": None,
            "private_diagnostic": "KeyError",
            "steps": [{"step_key": "create_page", "state": "applied"}],
        }],
    })

    result = content_push.apply_content_push("op-1", "batch-1", "digest-1")

    assert result == {
        "ok": True,
        "kind": "page",
        "operation_id": "op-1",
        "status": "applied",
        "targets": [{
            "state": "applied",
            "url": "https://canvas.invalid/courses/1/pages/welcome",
        }],
    }
    assert "KeyError" not in server._compact(result)


def test_apply_surfaces_the_unfinished_step_when_a_push_needs_attention(monkeypatch):
    monkeypatch.setattr(content_push.operations, "get_operation", lambda _id: {
        "operation_id": "op-1", "kind": "content.assignment",
    })
    monkeypatch.setattr(content_push.executor, "apply_operation", lambda *_a: {
        "ok": False,
        "operation_id": "op-1",
        "status": "partial",
        "target_results": [{
            "target_key": "target-key",
            "state": "sent_unknown",
            "error_code": "adapter_exception_after_send",
            "steps": [
                {"step_key": "create_assignment", "state": "applied"},
                {"step_key": "attach_module", "state": "sent_unknown",
                 "error_code": "timeout"},
            ],
        }],
    })

    result = content_push.apply_content_push("op-1", "batch-1", "digest-1")

    assert result["ok"] is False
    assert result["kind"] == "assignment"
    assert result["status"] == "partial"
    assert result["targets"] == [{
        "state": "sent_unknown",
        "error_code": "adapter_exception_after_send",
        "unfinished_steps": [{
            "step": "attach_module", "state": "sent_unknown",
            "error_code": "timeout",
        }],
    }]


def test_a_drift_refusal_from_the_executor_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(content_push.operations, "get_operation", lambda _id: {
        "operation_id": "op-1", "kind": "content.page",
    })

    def refuse(*_args):
        raise ValueError("review batch or digest does not match stored review")

    monkeypatch.setattr(content_push.executor, "apply_operation", refuse)

    result = content_push.apply_content_push("op-1", "batch-1", "digest-1")

    assert result["ok"] is False
    assert "does not match stored review" in result["error"]


# --- against the real adapters -------------------------------------------------

@pytest.fixture
def _ledger(monkeypatch, tmp_path):
    """A real ledger over a temp private root, with Canvas reads stubbed empty."""
    from api.operation_ledger import paths
    from api.platform_services import canvas_client

    monkeypatch.setattr(paths, "private_root", lambda: tmp_path / "private")
    monkeypatch.setattr(canvas_client, "canvas_get", lambda *_a, **_k: ([], None))
    return tmp_path


def test_a_real_pageforge_draft_freezes_through_the_real_adapter(_ledger):
    _stage("page", "welcome", body=(
        '<PAGEFORGE_JSON>{"version":"1.0-json","type":"PAGE",'
        '"title":"Welcome to Unit 3","body":"<p>Read this first.</p>"}'
        '</PAGEFORGE_JSON>'
    ))

    result = content_push.preview_content_push(
        "course-x", "page", "welcome", published=True, module_name="Unit 3")

    assert result["ok"] is True
    assert result["preview"] == {
        "course_name": "Invented Course",
        "page_title": "Welcome to Unit 3",
        "published": True,
        "module_name": "Unit 3",
        "baseline_has_existing_page": False,
        "baseline_page_url": None,
    }


def test_a_real_assignmentforge_draft_carries_its_schedule(_ledger):
    _stage("assignment", "essay-1", body=(
        '<ASSIGNMENTFORGE_JSON>{"version":"1.0-json","type":"ASSIGNMENT",'
        '"title":"Essay 1","description":"<p>Write the thing.</p>","points":100}'
        '</ASSIGNMENTFORGE_JSON>'
    ))

    result = content_push.preview_content_push(
        "course-x", "assignment", "essay-1",
        due_at="2026-09-11T23:59:00Z", post_to_sis=True)

    assert result["ok"] is True
    assert result["preview"]["assignment_name"] == "Essay 1"
    assert result["preview"]["points"] == 100
    assert result["preview"]["due_at"] == "2026-09-11T23:59:00Z"
    assert result["preview"]["post_to_sis"] is True
    assert result["preview"]["published"] is False


def test_a_malformed_draft_is_refused_with_the_validator_problem(_ledger):
    _stage("page", "broken", body="no envelope here")

    result = content_push.preview_content_push("course-x", "page", "broken")

    assert result["ok"] is False
    assert "PAGEFORGE_JSON" in result["error"]


def test_the_whole_chain_answers_one_text_block_over_the_protocol(_ledger):
    _stage("page", "welcome", body=(
        '<PAGEFORGE_JSON>{"version":"1.0-json","type":"PAGE",'
        '"title":"Welcome","body":"<p>Hi.</p>"}</PAGEFORGE_JSON>'
    ))

    content = asyncio.run(server.mcp.call_tool("preview_content_push", {
        "course_id": "course-x", "kind": "page", "label": "welcome",
    }))

    assert len(content) == 1
    assert content[0].type == "text"
    payload = json.loads(content[0].text)
    assert payload["ok"] is True
    assert payload["next"] == tools._NEXT_STEPS["preview_content_push"]
    assert payload["preview"]["page_title"] == "Welcome"


def test_the_frozen_operation_is_visible_to_the_teacher_and_applies_once(_ledger):
    """The chat push is not a side channel: it lands in the same ledger the
    push tab's Operations list reads, and the same digest gate guards apply."""
    from api.operation_ledger import operations

    _stage("page", "welcome", body=(
        '<PAGEFORGE_JSON>{"version":"1.0-json","type":"PAGE",'
        '"title":"Welcome","body":"<p>Hi.</p>"}</PAGEFORGE_JSON>'
    ))
    preview = content_push.preview_content_push("course-x", "page", "welcome")

    listed = operations.list_operations_pii_minimized()
    assert [op["operation_id"] for op in listed] == [preview["operation_id"]]
    assert listed[0]["kind"] == "content.page"
    assert listed[0]["status"] == "reviewed"

    wrong_digest = content_push.apply_content_push(
        preview["operation_id"], preview["batch_id"], "not-the-digest")
    assert wrong_digest["ok"] is False
    assert "does not match" in wrong_digest["error"]


# --- the staging contract still says where drafts go ---------------------------

def test_the_staging_appendix_offers_the_push_without_replacing_the_push_tab():
    contract = tools.get_authoring_contract("page")["contract"]

    assert "Canvas Expert push tab" in contract
    assert "preview_content_push" in contract
    assert "apply_content_push" in contract

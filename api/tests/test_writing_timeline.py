from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

import pytest
from docx import Document

from api import feedback_artifacts, feedback_contract, feedback_results, feedback_safety
from api.feedback_vault import Vault
from api.powergrader import autopush_executor, autopush_policy, autoscore_queue
from api.powergrader import session_builder, student_attachments, writing_timeline
from api.webui import workspace
from api.webui.routes import powergrader as powergrader_routes
from api.webui.routes import routines as routines_routes


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _base_docx(body_text: str = "A fictional visible response.") -> bytes:
    document = Document()
    document.add_paragraph(body_text)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _rewrite_docx(base: bytes, replacements: dict[str, bytes], additions: dict[str, bytes] | None = None) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base)) as source, zipfile.ZipFile(
        output, "w", zipfile.ZIP_DEFLATED
    ) as target:
        for info in source.infolist():
            if info.filename in replacements:
                target.writestr(info, replacements[info.filename])
            else:
                target.writestr(info, source.read(info.filename))
        existing = set(source.namelist())
        for name, payload in (additions or {}).items():
            if name not in existing:
                target.writestr(name, payload)
    return output.getvalue()


def _revision_xml(
    kind: str,
    text: str,
    *,
    author: str,
    timestamp: str = "2026-07-27T10:00:00-05:00",
) -> str:
    tag = "ins" if kind == "insertion" else "del"
    text_tag = "t" if kind == "insertion" else "delText"
    return (
        f'<w:{tag} w:author="{author}" w:date="{timestamp}">'
        f"<w:r><w:{text_tag}>{text}</w:{text_tag}></w:r>"
        f"</w:{tag}>"
    )


def _timeline_docx(
    *,
    blocks: list[tuple[str, str, str]] | None = None,
    track_revisions: bool = True,
    protection: str = "none",
    creator: str = "Fictional Learner",
    last_modified: str = "Fictional Learner",
    total_time: str = "37",
    revision: str = "8",
    stories: dict[str, str] | None = None,
    body_text: str = "A fictional visible response.",
    timestamp: str = "2026-07-27T10:00:00-05:00",
) -> bytes:
    base = _base_docx(body_text)
    with zipfile.ZipFile(io.BytesIO(base)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    revision_nodes = "".join(
        _revision_xml(kind, text, author=author, timestamp=timestamp)
        for kind, text, author in (blocks or [])
    )
    document_xml = document_xml.replace("</w:body>", f"<w:p>{revision_nodes}</w:p></w:body>")
    protection_xml = ""
    if protection == "unlocked":
        protection_xml = '<w:documentProtection w:edit="trackedChanges" w:enforcement="0"/>'
    elif protection == "locked":
        protection_xml = '<w:documentProtection w:edit="trackedChanges" w:enforcement="1"/>'
    settings_xml = (
        f'<w:settings xmlns:w="{W_NS}">'
        + ("<w:trackRevisions/>" if track_revisions else "")
        + protection_xml
        + "</w:settings>"
    )
    core_xml = (
        '<cp:coreProperties '
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f"<dc:creator>{creator}</dc:creator>"
        f"<cp:lastModifiedBy>{last_modified}</cp:lastModifiedBy>"
        "</cp:coreProperties>"
    )
    app_xml = (
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
        f"<TotalTime>{total_time}</TotalTime><Revision>{revision}</Revision>"
        "</Properties>"
    )
    story_parts = {}
    for name, inner in (stories or {}).items():
        story_parts[name] = (
            f'<w:hdr xmlns:w="{W_NS}"><w:p>{inner}</w:p></w:hdr>'
        ).encode("utf-8")
    return _rewrite_docx(
        base,
        {
            "word/document.xml": document_xml.encode("utf-8"),
            "word/settings.xml": settings_xml.encode("utf-8"),
            "docProps/core.xml": core_xml.encode("utf-8"),
            "docProps/app.xml": app_xml.encode("utf-8"),
        },
        story_parts,
    )


@pytest.mark.parametrize(
    ("submission_types", "allowed_extensions", "expected"),
    [
        (["online_upload"], ["docx"], True),
        (["ONLINE_UPLOAD"], [".DOCX"], True),
        (["online_upload", "online_text_entry"], ["docx"], False),
        (["online_upload"], ["docx", "pdf"], False),
        (["online_upload"], [], False),
        ([], ["docx"], False),
        (["online_text_entry"], ["docx"], False),
    ],
)
def test_exact_assignment_classification(submission_types, allowed_extensions, expected):
    assert writing_timeline.is_tracked_assignment(
        {
            "submission_types": submission_types,
            "allowed_extensions": allowed_extensions,
        }
    ) is expected


def test_parser_captures_blocks_story_parts_and_stable_largest_three():
    header_revision = _revision_xml(
        "insertion",
        "header words",
        author="Header Workstation",
        timestamp="2026-07-27T17:00:00Z",
    )
    payload = _timeline_docx(
        blocks=[
            ("insertion", "small typed phrase", "Fictional Learner"),
            ("insertion", "x" * 210, "Fictional Learner"),
            ("deletion", "removed words", "Fictional Learner"),
            ("insertion", "y" * 210, "Fictional Learner"),
            ("insertion", "", "Fictional Learner"),
            ("insertion", "z" * 400, "Fictional Learner"),
        ],
        protection="locked",
        stories={"word/header1.xml": header_revision},
    )

    report = writing_timeline.parse_docx(payload)

    assert report["status"] == "available"
    assert report["trail_present"] is True
    assert report["track_revisions_present"] is True
    assert report["tracking_protection_present"] is True
    assert report["tracking_protection_enforced"] is True
    assert report["tracking_lock_present"] is True
    assert report["properties"]["total_time_minutes"] == 37
    assert report["properties"]["revision"] == 8
    assert len(report["blocks"]) == 7
    assert any(block["type"] == "deletion" for block in report["blocks"])
    assert any(block["story_part"] == "word/header1.xml" for block in report["blocks"])
    assert [block["character_count"] for block in report["largest_insertions"]] == [400, 210, 210]
    assert [block["document_order"] for block in report["largest_insertions"][1:]] == [1, 3]
    assert all(block["character_count"] > 0 for block in report["largest_insertions"])
    # Central, not UTC. The fixture's w:date is 10:00-05:00, already Central summer.
    assert report["blocks"][0]["timestamp"] == "2026-07-27T10:00:00-05:00"
    # The header revision's 17:00Z becomes 12:00 CDT rather than staying UTC.
    header_block = next(b for b in report["blocks"] if b["story_part"] == "word/header1.xml")
    assert header_block["timestamp"] == "2026-07-27T12:00:00-05:00"
    assert header_block["raw_timestamp"] == "2026-07-27T17:00:00Z"


@pytest.mark.parametrize(
    ("track_revisions", "protection", "expected_lock"),
    [
        (False, "none", False),
        (True, "none", False),
        (True, "unlocked", False),
        (True, "locked", True),
    ],
)
def test_parser_distinguishes_tracking_setting_and_lock(track_revisions, protection, expected_lock):
    report = writing_timeline.parse_docx(
        _timeline_docx(
            blocks=[],
            track_revisions=track_revisions,
            protection=protection,
        )
    )
    assert report["status"] == "available"
    assert report["trail_present"] is False
    assert report["track_revisions_present"] is track_revisions
    assert report["tracking_lock_present"] is expected_lock


def test_parser_reports_missing_and_malformed_parts_without_crashing():
    malformed_zip = writing_timeline.parse_docx(b"not a zip")
    assert malformed_zip["status"] == "invalid"
    assert malformed_zip["observations"][0]["reason"] == "malformed_zip"

    empty_zip = io.BytesIO()
    with zipfile.ZipFile(empty_zip, "w"):
        pass
    missing = writing_timeline.parse_docx(empty_zip.getvalue())
    assert missing["status"] == "unavailable"
    assert any(item["reason"] == "missing_part" for item in missing["observations"])

    malformed_document = _rewrite_docx(
        _base_docx(),
        {"word/document.xml": b"<w:document"},
    )
    invalid = writing_timeline.parse_docx(malformed_document)
    assert invalid["status"] == "invalid"
    assert any(item["reason"] == "malformed_xml" for item in invalid["observations"])

    malformed_properties = _rewrite_docx(
        _timeline_docx(blocks=[]),
        {
            "docProps/app.xml": (
                '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
                "<TotalTime>not-a-number</TotalTime><Revision>-2</Revision></Properties>"
            ).encode("utf-8"),
            "docProps/core.xml": b"<core",
        },
    )
    partial = writing_timeline.parse_docx(malformed_properties)
    assert partial["status"] == "available"
    assert partial["properties"]["total_time_minutes"] is None
    assert partial["properties"]["revision"] is None
    assert any(item["status"] == "invalid" for item in partial["observations"])


def test_author_categories_require_exact_unique_multiword_roster_match():
    report = writing_timeline.parse_docx(
        _timeline_docx(
            blocks=[
                ("insertion", "one", "Fictional Learner"),
                ("insertion", "two", "Fictional Peer"),
                ("insertion", "three", "Grace"),
                ("insertion", "four", "Shared Lab"),
            ],
            creator="Fictional Learner",
            last_modified="Fictional Peer",
        )
    )
    roster = [
        {"canvas_id": "learner", "real_name": "Fictional Learner"},
        {"canvas_id": "peer", "real_name": "Fictional Peer"},
        {"canvas_id": "grace", "real_name": "Grace Example"},
        {"canvas_id": "lab-1", "real_name": "Shared Lab"},
        {"canvas_id": "lab-2", "real_name": "Shared Lab"},
    ]

    categorized = writing_timeline.categorize_authors(
        report,
        submission_canvas_id="learner",
        roster=roster,
    )

    assert categorized["properties"]["creator_category"] == "submission_author"
    assert categorized["properties"]["last_modified_by_category"] == "other_roster_author"
    assert [block["author_category"] for block in categorized["blocks"]] == [
        "submission_author",
        "other_roster_author",
        "unrecognized_author_present",
        "unrecognized_author_present",
    ]


def test_safe_artifact_strips_raw_office_metadata_and_preserves_only_projection(tmp_path):
    raw_values = {
        "learner": "Fictional Learner",
        "peer": "Fictional Peer",
        "unknown": "Private Lab Profile",
        "header": "Private Header Name",
    }
    header_revision = _revision_xml(
        "insertion",
        "header-only text",
        author=raw_values["header"],
    )
    payload = _timeline_docx(
        blocks=[
            ("insertion", "fictional work", raw_values["learner"]),
            ("deletion", "fictional removal", raw_values["peer"]),
            ("insertion", "more fictional work", raw_values["unknown"]),
        ],
        creator=raw_values["learner"],
        last_modified=raw_values["peer"],
        stories={"word/header1.xml": header_revision},
        body_text="Fictional Learner wrote a visible fictional response.",
    )
    local_file = tmp_path / "private-evidence.docx"
    local_file.write_bytes(payload)
    submission = {
        "user_id": "learner",
        "user": {"name": raw_values["learner"], "sortable_name": raw_values["learner"]},
        "assignment": {
            "id": "assignment-1",
            "description": "Write a fictional response.",
            "points_possible": 10,
        },
        "body": "",
        "expected_attachment_count": 1,
        "attachments": [{
            "filename": "private-evidence.docx",
            "local_path": str(local_file),
            "declared_size": len(payload),
            "actual_size": len(payload),
            "download_status": "downloaded",
            "extraction_status": "extracted",
            "ai_eligible": True,
            "local_only": False,
            "item_id": "assignment-1",
        }],
    }
    peer_roster_row = {
        "user_id": "peer",
        "user": {"name": raw_values["peer"], "sortable_name": raw_values["peer"]},
    }
    student_attachments.attach_writing_timelines(
        [submission],
        roster_submissions=[submission, peer_roster_row],
    )

    vault = Vault(str(tmp_path / "vault.json"))
    bundle = feedback_artifacts.pseudonymize_submissions(
        [submission], vault, "Fictional Assignment"
    )
    safe_dir = tmp_path / "SAFE"
    private_dir = tmp_path / "PRIVATE"
    result = feedback_artifacts.write_safe_and_private(
        bundle,
        vault,
        str(safe_dir),
        str(private_dir),
        submissions=[submission],
    )

    safe = json.loads(Path(result["safe_bundle"]).read_text(encoding="utf-8"))
    private_text = Path(result["private_bundle"]).read_text(encoding="utf-8")
    safe_text = json.dumps(safe)
    for raw in raw_values.values():
        assert raw not in safe_text
    assert str(local_file) not in safe_text
    assert local_file.name not in safe_text
    assert "header-only text" not in safe_text
    assert raw_values["unknown"] in private_text
    assert raw_values["header"] in private_text

    timeline = safe["students"][0]["responses"][0]["writing_timeline"]["documents"][0]
    assert timeline["properties"]["creator_category"] == "submission_author"
    assert timeline["properties"]["last_modified_by_category"] == "other_roster_author"
    # The per-block array is not projected at all: it has no consumer and grows
    # without bound on a heavily tracked document.  Counts carry the volume, and
    # `largest_insertions` carries the per-block author categories.
    assert "blocks" not in timeline
    assert timeline["block_count"] >= 3
    assert timeline["insertion_count"] + timeline["deletion_count"] == timeline["block_count"]
    assert len(timeline["largest_insertions"]) <= 3
    assert {block.get("author_category") for block in timeline["largest_insertions"]} <= {
        "submission_author",
        "other_roster_author",
        "unrecognized_author_present",
    }
    assert feedback_safety.assert_scrubbed(safe, vault)["green"] is True


def test_optional_teacher_observation_round_trips_but_never_enters_write_fields(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    pseudonym = vault.get_or_assign("learner", "Fictional Learner", "")
    bundle = {
        "students": [{
            "pseudonym": pseudonym,
            "responses": [{"item_id": "assignment-1", "possible": 10}],
        }]
    }
    observation = "Several insertion blocks appear across multiple timestamps."
    result = [{
        "pseudonym": pseudonym,
        "item_id": "assignment-1",
        "score": 8,
        "feedback": "Student-facing feedback only.",
        "writing_process_observations": observation,
    }]
    verdict = feedback_results.validate_results(result, bundle, vault)
    assert verdict["ok"] is True
    rows = feedback_results.reidentify(result, vault)
    merged = feedback_results.merge_rows_by_uid(rows)
    assert merged["learner"]["writing_process_observations"] == observation
    assert observation not in merged["learner"]["feedback"]

    missing = [{key: value for key, value in result[0].items() if key != "writing_process_observations"}]
    assert feedback_results.validate_results(missing, bundle, vault)["ok"] is True
    malformed = [{**result[0], "writing_process_observations": 42}]
    assert feedback_results.validate_results(malformed, bundle, vault)["ok"] is False

    student = {
        "user_id": "learner",
        "ai_score": 8,
        "ai_feedback": "Student-facing feedback only.",
        "writing_process_observations": observation,
    }
    payload = autopush_executor._build_canvas_payload(
        {"grade_push_allowed": True, "comment_push_allowed": True},
        {"points_possible": 10},
        student,
        {"score_text": "8"},
    )
    assert payload == {
        "submission": {"posted_grade": "8"},
        "comment": {"text_comment": "Student-facing feedback only."},
    }
    score, feedback = autopush_policy._effective_score_feedback(student, None)
    assert score == 8
    assert feedback == "Student-facing feedback only."
    assert observation not in json.dumps(payload)

    sends = []
    context = {
        "course_id": "course-1",
        "assignment_id": "assignment-1",
        "auto_push": True,
        "status": "session_ready",
        "push_policy": {
            "enabled": True,
            "allow_grade_push": True,
            "allow_comment_push": True,
            "policy_version": 2,
        },
    }
    assignment = {
        "id": "assignment-1",
        "course_id": "course-1",
        "points_possible": 10,
        "grading_type": "points",
        "submission_types": ["online_text_entry"],
        "allowed_extensions": [],
        "group_category_id": None,
    }
    student.update({
        "submission_id": "submission-1",
        "body": "Fictional submitted work.",
        "submission_baseline": {
            "attempt": 1,
            "submitted_at": "2026-07-27T10:00:00Z",
        },
        "posted": False,
        "status": "pending",
    })
    canvas_state = {
        "canvas_state_present": True,
        "user_id": "learner",
        "submission_id": "submission-1",
        "workflow_state": "submitted",
        "attempt": 1,
        "submitted_at": "2026-07-27T10:00:00Z",
        "excused": False,
        "score": None,
        "submission_comments": [],
    }
    summary = autopush_executor.run_autopush_for_session(
        context=context,
        session={"students": [student]},
        assignment=assignment,
        canvas_states_by_user={"learner": canvas_state},
        canvas_send=lambda method, path, body: sends.append(
            {"method": method, "path": path, "body": body}
        ) or {"ok": True},
        receipt_dir=str(tmp_path / "receipts"),
        now="2026-07-27T12:00:00Z",
    )
    assert summary["pushed"] == 1, summary
    assert observation not in json.dumps(sends)
    assert observation not in json.dumps(summary["receipts"])
    receipt_text = " ".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "receipts").glob("*.json")
    )
    assert observation not in receipt_text

    prompt = feedback_contract.build_contract_text()
    assert "observational, teacher-only" in prompt
    assert "must not change the score" in prompt
    assert "penalty recommendation" in prompt


def test_session_builder_keeps_private_timeline_and_teacher_observation():
    report = writing_timeline.categorize_authors(
        writing_timeline.parse_docx(
            _timeline_docx(
                blocks=[("insertion", "fictional work", "Fictional Learner")],
            )
        ),
        submission_canvas_id="learner",
        roster=[{"canvas_id": "learner", "real_name": "Fictional Learner"}],
    )
    students = session_builder.build_students(
        submitted=[{
            "user_id": "learner",
            "user": {"name": "Fictional Learner"},
            "attachments": [{
                "filename": "answer.docx",
                "download_status": "downloaded",
                "extraction_status": "extracted",
                "ai_eligible": True,
                "local_only": False,
                "writing_timeline": report,
            }],
            "expected_attachment_count": 1,
        }],
        ai_by_uid={
            "learner": {
                "score": 8,
                "feedback": "Student-facing only.",
                "writing_process_observations": "Teacher-only observation.",
            }
        },
        roster_settings={},
        tier_map={},
        monitored={},
        extra_time_map={},
    )
    assert students[0]["attachments"][0]["writing_timeline"]["blocks"][0]["author"] == "Fictional Learner"
    assert students[0]["writing_process_observations"] == "Teacher-only observation."


@pytest.mark.parametrize("mode", ["fast", "packet", "assisted"])
def test_pg_start_persists_tracked_classification_and_timeline_in_every_mode(
    mode, monkeypatch, tmp_path
):
    payload = _timeline_docx(
        blocks=[("insertion", "fictional work", "Fictional Learner")],
    )
    local_file = tmp_path / "answer.docx"
    local_file.write_bytes(payload)
    submission = {
        "id": "submission-1",
        "user_id": "learner",
        "user": {"name": "Fictional Learner", "sortable_name": "Fictional Learner"},
        "submission_type": "online_upload",
        "workflow_state": "submitted",
        "attempt": 1,
        "body": "",
        "attachments": [{
            "filename": "answer.docx",
            "local_path": str(local_file),
            "declared_size": len(payload),
            "actual_size": len(payload),
            "download_status": "downloaded",
            "extraction_status": "extracted",
            "ai_eligible": True,
            "local_only": False,
            "item_id": "assignment-1",
        }],
        "expected_attachment_count": 1,
    }
    assignment = {
        "id": "assignment-1",
        "name": "Fictional Assignment",
        "points_possible": 10,
        "submission_types": ["ONLINE_UPLOAD"],
        "allowed_extensions": [".DOCX"],
    }
    saved = {}
    monkeypatch.setattr(powergrader_routes.workspace, "workspace_root", lambda: str(tmp_path))
    monkeypatch.setattr(
        powergrader_routes.assignment_refresh,
        "refresh_assignment",
        lambda *args, **kwargs: ([submission], assignment, {"status": "complete"}),
    )
    monkeypatch.setattr(
        powergrader_routes.ai_workflow,
        "run_ai_workflow",
        lambda **kwargs: {
            "ok": True,
            "privacy_steps": [],
            "privacy_artifacts": {},
            "ai_by_uid": {},
            "ai_item_by_uid": {},
            "ai_failures": {},
            "source_context": {},
        },
    )
    monkeypatch.setattr(powergrader_routes.config, "course_display_name", lambda _course_id: "Fictional Course")
    monkeypatch.setattr(powergrader_routes.config, "get_openrouter_model", lambda: "synthetic/model")
    monkeypatch.setattr(powergrader_routes.config, "has_openrouter_key", lambda: False)
    monkeypatch.setattr(powergrader_routes.config, "get_roster_student_settings", lambda _course_id: {})
    monkeypatch.setattr(powergrader_routes.config, "roster_tier_by_id", lambda _course_id: {})
    monkeypatch.setattr(powergrader_routes.config, "get_monitored_students", lambda: {})
    monkeypatch.setattr(powergrader_routes.config, "get_extra_time", lambda _course_id: [])
    monkeypatch.setattr(powergrader_routes, "_save_session", lambda value: saved.update(value))

    response = powergrader_routes.pg_start(
        course_id="course-1",
        assignment_id="assignment-1",
        mode=mode,
        watch_late="true",
        auto_post="false",
        rubric_name="",
        persona_id="sage",
        feedback_pattern_id="",
        model_id="",
        response_kind="scr",
        source_text="",
        source_files_json="",
        source_uploads=None,
    )

    assert json.loads(response.body)["ok"] is True
    assert saved["writing_timeline_tracked"] is True
    timeline = saved["students"][0]["attachments"][0]["writing_timeline"]
    assert timeline["status"] == "available"
    assert timeline["largest_insertions"][0]["author_category"] == "submission_author"


def test_non_tracked_session_skips_timeline_parsing(monkeypatch, tmp_path):
    payload = _timeline_docx(
        blocks=[("insertion", "fictional work", "Fictional Learner")],
    )
    local_file = tmp_path / "answer.docx"
    local_file.write_bytes(payload)
    submission = {
        "user_id": "learner",
        "user": {"name": "Fictional Learner"},
        "submission_type": "online_upload",
        "workflow_state": "submitted",
        "attachments": [{
            "filename": "answer.docx",
            "local_path": str(local_file),
            "download_status": "downloaded",
            "extraction_status": "extracted",
            "ai_eligible": True,
            "local_only": False,
        }],
    }
    assignment = {
        "name": "Fictional Mixed Assignment",
        "points_possible": 10,
        "submission_types": ["online_upload"],
        "allowed_extensions": ["docx", "pdf"],
    }
    saved = {}
    monkeypatch.setattr(powergrader_routes.workspace, "workspace_root", lambda: str(tmp_path))
    monkeypatch.setattr(
        powergrader_routes.assignment_refresh,
        "refresh_assignment",
        lambda *args, **kwargs: ([submission], assignment, {"status": "complete"}),
    )
    monkeypatch.setattr(
        powergrader_routes.ai_workflow,
        "run_ai_workflow",
        lambda **kwargs: {
            "ok": True,
            "privacy_steps": [],
            "privacy_artifacts": {},
            "ai_by_uid": {},
            "source_context": {},
        },
    )
    monkeypatch.setattr(powergrader_routes.config, "course_display_name", lambda _course_id: "Course")
    monkeypatch.setattr(powergrader_routes.config, "get_openrouter_model", lambda: "synthetic/model")
    monkeypatch.setattr(powergrader_routes.config, "has_openrouter_key", lambda: False)
    monkeypatch.setattr(powergrader_routes.config, "get_roster_student_settings", lambda _course_id: {})
    monkeypatch.setattr(powergrader_routes.config, "roster_tier_by_id", lambda _course_id: {})
    monkeypatch.setattr(powergrader_routes.config, "get_monitored_students", lambda: {})
    monkeypatch.setattr(powergrader_routes.config, "get_extra_time", lambda _course_id: [])
    monkeypatch.setattr(powergrader_routes, "_save_session", lambda value: saved.update(value))

    response = powergrader_routes.pg_start(
        course_id="course-1",
        assignment_id="assignment-1",
        mode="fast",
        watch_late="true",
        auto_post="false",
        rubric_name="",
        persona_id="sage",
        feedback_pattern_id="",
        model_id="",
        response_kind="scr",
        source_text="",
        source_files_json="",
        source_uploads=None,
    )

    assert json.loads(response.body)["ok"] is True
    assert saved["writing_timeline_tracked"] is False
    assert "writing_timeline" not in saved["students"][0]["attachments"][0]


# ---------------------------------------------------------------------------
# Central time, end to end
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("raw", "expected"), [
    # Central Daylight Time, UTC-5.
    ("2026-07-26T23:04:00Z", "2026-07-26T18:04:00-05:00"),
    # Central Standard Time, UTC-6. A fixed offset would get this wrong.
    ("2026-01-15T18:00:00Z", "2026-01-15T12:00:00-06:00"),
    # Already Central: unchanged, not double-shifted.
    ("2026-07-27T10:00:00-05:00", "2026-07-27T10:00:00-05:00"),
    # Word writes w:date in UTC; a bare timestamp is read as UTC, not guessed.
    ("2026-07-26T23:04:00", "2026-07-26T18:04:00-05:00"),
    # Either side of both DST transitions.
    ("2026-03-08T07:30:00Z", "2026-03-08T01:30:00-06:00"),
    ("2026-03-08T08:30:00Z", "2026-03-08T03:30:00-05:00"),
    ("2026-11-01T06:30:00Z", "2026-11-01T01:30:00-05:00"),
    ("2026-11-01T07:30:00Z", "2026-11-01T01:30:00-06:00"),
    # Unusable input stays None rather than inventing a time.
    ("garbage", None),
    ("", None),
    (None, None),
])
def test_timestamps_normalize_to_central_across_dst(raw, expected):
    assert writing_timeline._normalize_timestamp(raw) == expected


def test_normalized_timestamps_are_idempotent():
    """safe_projection re-normalizes an already-normalized value; it must not shift."""
    once = writing_timeline._normalize_timestamp("2026-07-26T23:04:00Z")
    assert writing_timeline._normalize_timestamp(once) == once


def test_missing_tz_database_still_tracks_dst_and_never_yields_utc(monkeypatch):
    """Without tzdata the machine clock is used, and it must still track DST.

    A captured `datetime.now().astimezone().tzinfo` is a FROZEN offset: converting
    through it would report one clock all year and put every timestamp in the
    opposite DST season an hour out. Argument-less `astimezone()` asks the OS per
    instant instead. Falling back to UTC is never acceptable either -- that restores
    the exact misreading Central exists to prevent.

    This test is meaningful only on a Central-configured machine, which is the
    only platform this Windows-only, single-district tool runs on.
    """
    monkeypatch.setattr(writing_timeline, "_central_zone", None)
    monkeypatch.setattr(
        writing_timeline, "ZoneInfo",
        lambda _name: (_ for _ in ()).throw(RuntimeError("no tz database")),
    )
    assert writing_timeline.central_timezone() is None

    summer = writing_timeline._normalize_timestamp("2026-07-26T23:04:00Z")
    winter = writing_timeline._normalize_timestamp("2026-01-15T18:00:00Z")
    frozen = datetime.now().astimezone().utcoffset()

    for value in (summer, winter):
        assert not value.endswith("Z")
        assert "+00:00" not in value
    # The two seasons must NOT share an offset. A frozen-offset fallback would make
    # them identical, which is the bug this guards.
    assert summer[-6:] != winter[-6:], (summer, winter)
    assert summer.endswith("-05:00") and winter.endswith("-06:00")
    # And at least one season must differ from whatever offset is current right now,
    # proving the conversion is per-instant rather than "now".
    assert {summer[-6:], winter[-6:]} != {_offset_text(frozen)}

    monkeypatch.setattr(writing_timeline, "_central_zone", None)


def _offset_text(delta) -> str:
    total = int(delta.total_seconds())
    sign = "-" if total < 0 else "+"
    total = abs(total)
    return f"{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"


def test_safe_projection_timestamps_are_central(tmp_path):
    payload = _timeline_docx(
        blocks=[("insertion", "x" * 120, "Fictional Learner")],
        timestamp="2026-07-26T23:04:00Z",
    )
    report = writing_timeline.categorize_authors(
        writing_timeline.parse_docx(payload),
        submission_canvas_id="learner",
        roster=[{"canvas_id": "learner", "user": {"name": "Fictional Learner"}}],
    )
    projection = writing_timeline.safe_projection(report)
    stamps = [b.get("timestamp") for b in projection["largest_insertions"]]
    assert stamps == ["2026-07-26T18:04:00-05:00"]
    assert not any(str(s).endswith("Z") for s in stamps)


# ---------------------------------------------------------------------------
# Teacher-only observation guard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("observation", [
    "The student likely used AI to write this.",
    "This looks like plagiarism.",
    "Clear evidence of cheating.",
    "The submission was AI-generated.",
    "Someone else wrote this essay.",
    "This student did not write the response.",
    "I recommend a penalty for academic dishonesty.",
    "Give them a zero and report this to the office.",
    "Suspicious editing pattern suggests misconduct.",
    "Probably copied from another source.",
    "This should be investigated as an honor code violation.",
    "Written by an AI, not the student.",
])
def test_integrity_conclusions_never_reach_the_teacher(observation):
    assert (
        writing_timeline.sanitize_process_observation(observation)
        == writing_timeline.OBSERVATION_WITHHELD_NOTICE
    )


@pytest.mark.parametrize("observation", [
    "The revision trail shows steady additions across three sittings.",
    "One insertion accounts for most of the text; the rest are small edits.",
    "Editing time is 42 minutes across 7 revisions.",
    "The document has no revision trail at all.",
    "Most insertions are short and evenly spaced.",
])
def test_process_descriptions_survive_the_guard(observation):
    assert writing_timeline.sanitize_process_observation(observation) == observation


def test_blank_observation_stays_blank():
    assert writing_timeline.sanitize_process_observation(None) == ""
    assert writing_timeline.sanitize_process_observation("   ") == ""


def test_reidentify_replaces_integrity_conclusion_with_notice(tmp_path):
    vault = Vault(str(tmp_path / "vault.json"))
    pseudonym = vault.get_or_assign("learner", "Fictional Learner", "")
    accusation = "This was almost certainly AI-generated; recommend a zero."
    result = [{
        "pseudonym": pseudonym,
        "item_id": "assignment-1",
        "score": 8,
        "feedback": "Student-facing feedback only.",
        "writing_process_observations": accusation,
    }]

    # A prompt rule is not an enforcement boundary: the string is well-typed, so
    # validation passes, and the guard has to catch it on the way to the teacher.
    bundle = {"students": [{
        "pseudonym": pseudonym,
        "responses": [{"item_id": "assignment-1", "possible": 10}],
    }]}
    assert feedback_results.validate_results(result, bundle, vault)["ok"] is True

    merged = feedback_results.merge_rows_by_uid(feedback_results.reidentify(result, vault))
    observation = merged["learner"]["writing_process_observations"]
    assert observation == writing_timeline.OBSERVATION_WITHHELD_NOTICE
    assert "AI-generated" not in observation
    assert "zero" not in observation
    assert merged["learner"]["feedback"] == "Student-facing feedback only."


# ---------------------------------------------------------------------------
# Coverage parity: every path that builds students must attach timelines
# ---------------------------------------------------------------------------

def _tracked_docx_submission(user_id: str, name: str, local_file: Path) -> dict:
    payload = _timeline_docx(blocks=[("insertion", "fictional work", name)])
    local_file.write_bytes(payload)
    return {
        "user_id": user_id,
        "submission_type": "online_upload",
        "workflow_state": "submitted",
        "submitted_at": "2026-09-11T15:20:00Z",
        "cached_due_date": "2026-09-10T23:59:00Z",
        "attempt": 1,
        "body": "",
        "user": {"name": name, "sortable_name": name},
        "assignment": {"id": "assignment-1", "name": "Essay"},
        "attachments": [{
            "filename": "answer.docx",
            "local_path": str(local_file),
            "declared_size": len(payload),
            "actual_size": len(payload),
            "download_status": "downloaded",
            "extraction_status": "extracted",
            "ai_eligible": True,
            "local_only": False,
            "item_id": "assignment-1",
        }],
        "expected_attachment_count": 1,
    }


_TRACKED_ASSIGNMENT = {
    "id": "assignment-1",
    "name": "Essay",
    "description": "<p>Explain the text.</p>",
    "points_possible": 10,
    "submission_types": ["online_upload"],
    "allowed_extensions": ["docx"],
    "grading_type": "points",
    "due_at": "2026-06-28T23:59:00-05:00",
}


def test_late_catchup_attaches_timelines_for_tracked_assignment(monkeypatch, tmp_path):
    """A late submitter must get the same timeline pass as an on-time one."""
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path / "ws"))
    existing = _tracked_docx_submission("1", "Existing Student", tmp_path / "one.docx")
    late = _tracked_docx_submission("2", "Late Student", tmp_path / "two.docx")
    session = {
        "session_id": "sid",
        "course_id": "course-1",
        "assignment_id": "assignment-1",
        "assignment_name": "Essay",
        "assignment_description": "Explain the text.",
        "points_possible": 10,
        "mode": "assisted",
        "model_id": "model-a",
        "response_kind": "scr",
        "rubric_name": "",
        "persona_id": "sage",
        "students": [{"user_id": "1", "real_name": "Existing Student", "status": "pending"}],
        "late_watch": {
            "enabled": True,
            "supported": True,
            "reason": "",
            "initial_missing_user_ids": ["2"],
            "known_user_ids": ["1"],
            "scored_user_ids": [],
            "last_checked": None,
            "last_scored": None,
            "last_summary": "",
            "source_context": {"sentinel": "keep-me"},
            "response_kind": "scr",
        },
        "push_log": [],
    }

    monkeypatch.setattr(powergrader_routes, "_load_session", lambda _sid: session)
    monkeypatch.setattr(powergrader_routes, "_save_session", lambda value: None)
    monkeypatch.setattr(
        powergrader_routes.canvas_fetch, "fetch_submissions",
        lambda course_id, assignment_id: ([existing, late], dict(_TRACKED_ASSIGNMENT), None),
    )
    monkeypatch.setattr(
        powergrader_routes.canvas_fetch, "ingest_ordinary_attachments",
        lambda subs, **kwargs: subs,
    )
    monkeypatch.setattr(
        powergrader_routes.ai_workflow, "run_ai_workflow",
        lambda **kwargs: {
            "ok": True, "error": "", "status_code": 200,
            "privacy_steps": [], "privacy_artifacts": {},
            "ai_by_uid": {}, "ai_item_by_uid": {}, "ai_failures": {},
            "source_context": {}, "copilot_packet": None,
            "packet_zip": None, "budget": None, "debug_path": None,
        },
    )
    for name, value in (
        ("get_roster_student_settings", lambda course_id: {}),
        ("roster_tier_by_id", lambda course_id: {}),
        ("get_monitored_students", lambda: {}),
        ("get_extra_time", lambda course_id: []),
        ("get_openrouter_model", lambda: "model-a"),
        ("has_openrouter_key", lambda: True),
        ("course_display_name", lambda course_id: "Fictional Course"),
    ):
        monkeypatch.setattr(powergrader_routes.config, name, value)
    from api.webui import school_calendar as school_calendar_module
    monkeypatch.setattr(
        school_calendar_module, "resolve_instructional_range",
        lambda date_from, date_to, known_schedule_ids, **kw: {
            "state": "ready", "date_from": date_from, "date_to": date_to,
            "days": {}, "no_count_dates": [],
        })

    response = powergrader_routes.pg_late_score("sid")

    assert json.loads(response.body)["ok"] is True
    assert session["writing_timeline_tracked"] is True
    appended = [st for st in session["students"] if str(st.get("user_id")) == "2"]
    assert len(appended) == 1
    timeline = appended[0]["attachments"][0]["writing_timeline"]
    assert timeline["status"] == "available"
    assert timeline["largest_insertions"][0]["author_category"] == "submission_author"


def test_tracked_assignment_is_autoscore_eligible_like_any_readable_upload():
    """Tracking changes the file format, not whether the content can be scored.

    A tracked assignment is a DOCX-only upload, and `route_bytes` extracts DOCX
    text in full, so it must reach scheduled auto-score on the same terms as a
    .txt upload. The gate is derived from the router's capability precisely so
    these two cannot disagree again.
    """
    assert "docx" in autoscore_queue.READABLE_UPLOAD_EXTS
    assert writing_timeline.is_tracked_assignment(_TRACKED_ASSIGNMENT) is True
    eligibility, reason = autoscore_queue.classify_assignment_for_autoscore(_TRACKED_ASSIGNMENT)
    assert eligibility == "eligible", reason


def test_autoscore_gate_matches_what_the_attachment_router_can_read():
    """The gate must never promise auto-score for work PowerGrader cannot read.

    These were two independent hand-maintained lists and drifted in both
    directions: the gate promised 20 code extensions that `route_bytes` sends to
    local_only (every student held, nothing scored, teacher still charged) while
    excluding `.docx`, which it extracts in full.
    """
    assert autoscore_queue.READABLE_UPLOAD_EXTS == {
        ext.lstrip(".") for ext in student_attachments.AI_TEXT_EXTS
    }
    # And AI_TEXT_EXTS must itself match observed router behavior, or the
    # derivation above just moves the drift one level down.
    payloads = {".docx": _base_docx("A fictional visible response.")}
    for ext in sorted(student_attachments.AI_TEXT_EXTS):
        data = payloads.get(ext, b"fictional content")
        routed = student_attachments.route_bytes(f"work{ext}", data)
        assert routed["ai_eligible"] is True, f"{ext} is gated eligible but routes to local_only"
    for ext in (".java", ".ipynb", ".pdf", ".pptx"):
        assert student_attachments.route_bytes(f"work{ext}", b"x")["ai_eligible"] is False


def test_routine_deps_expose_timeline_modules():
    """Wiring guard: the routines path cannot attach what it was never handed."""
    deps = routines_routes._powergrader_routine_deps()
    assert deps.writing_timeline is writing_timeline
    assert deps.student_attachments is student_attachments


def test_scheduled_routine_attaches_timelines_for_tracked_assignment(monkeypatch, tmp_path):
    """Scheduled autoscore must not produce timeline-free sessions.

    Now reachable end to end: a tracked DOCX assignment is autoscore-eligible.
    """
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path / "ws"))
    monkeypatch.setattr(routines_routes.config, "active_courses", lambda: [{
        "id": "course-1", "name": "Period 1", "nickname": "Period 1", "active": True,
    }])
    submission = _tracked_docx_submission("1", "Sparky McGee", tmp_path / "one.docx")
    job = {
        "job_id": "course-1_assignment-1",
        "course_id": "course-1",
        "course_name": "Period 1",
        "assignment_id": "assignment-1",
        "assignment_name": "Essay",
        "status": "scheduled",
        "eligibility": "eligible",
        "reason": "file upload includes extensions PowerGrader can read as text",
        "due_at": "2026-06-28T23:59:00-05:00",
        "delay_hours": 6,
        "scheduled_at": "2026-06-29T05:59:00-05:00",
        "auto_push": False,
        "push_policy": {
            "enabled": False, "allow_grade_push": True,
            "allow_comment_push": True, "policy_version": 1,
        },
        "assignment": dict(_TRACKED_ASSIGNMENT),
        "settings": {
            "model_id": "model-a", "persona_id": "sage",
            "response_kind": "scr", "rubric_name": "", "watch_late": False,
        },
        "session_id": "",
        "last_error": "",
    }
    queue = {"version": 1, "jobs": [job]}
    saved_sessions = []

    for name, value in (
        ("has_openrouter_key", lambda: True),
        ("get_openrouter_model", lambda: "model-a"),
        ("get_roster_student_settings", lambda course_id: {}),
        ("roster_tier_by_id", lambda course_id: {}),
        ("get_monitored_students", lambda: {}),
        ("get_extra_time", lambda course_id: []),
    ):
        monkeypatch.setattr(routines_routes.config, name, value)
    monkeypatch.setattr(routines_routes.autoscore_queue, "load_queue", lambda: queue)
    monkeypatch.setattr(routines_routes.autoscore_queue, "due_jobs", lambda q, now=None: q["jobs"])
    monkeypatch.setattr(routines_routes.autoscore_queue, "save_queue", lambda q: None)
    monkeypatch.setattr(
        routines_routes.canvas_fetch, "fetch_submissions",
        lambda course_id, assignment_id: ([submission], dict(_TRACKED_ASSIGNMENT), None),
    )
    monkeypatch.setattr(
        routines_routes.canvas_fetch, "ingest_ordinary_attachments",
        lambda subs, **kwargs: subs,
    )
    monkeypatch.setattr(
        routines_routes, "_canvas_send",
        lambda *args, **kwargs: pytest.fail("scheduled autoscore must not write to Canvas"),
    )
    monkeypatch.setattr(
        routines_routes.ai_workflow, "run_ai_workflow",
        lambda **kwargs: {
            "ok": True, "error": "", "status_code": 200,
            "privacy_steps": [], "privacy_artifacts": {},
            "ai_by_uid": {}, "ai_item_by_uid": {}, "ai_failures": {},
            "packet_zip": None, "budget": None, "debug_path": None,
            "copilot_packet": None, "source_context": {"materials": []},
        },
    )
    monkeypatch.setattr(
        routines_routes.session_store, "save_session",
        lambda session: saved_sessions.append(session),
    )

    result = routines_routes._run_routine_powergrader_scheduled_autoscore({"max_jobs": 10})

    assert result["ok"] is True
    assert saved_sessions, result["lines"]
    saved = saved_sessions[-1]
    assert saved["writing_timeline_tracked"] is True
    timeline = saved["students"][0]["attachments"][0]["writing_timeline"]
    assert timeline["status"] == "available"
    assert timeline["largest_insertions"][0]["author_category"] == "submission_author"

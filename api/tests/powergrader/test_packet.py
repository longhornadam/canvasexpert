import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

from api.feedback_vault import Vault

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.platform_services import workspace
from api.webui.routes import powergrader
from api.powergrader import packet, privacy, scoring_packet, session_builder


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

    info = packet.build_safe_ai_packet(
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


@pytest.mark.skipif(os.name != "nt", reason="MAX_PATH 260-char limit is Windows-only")
def test_build_safe_ai_packet_survives_long_windows_path(tmp_path):
    """Regression for the SummerTime Brain Work crash: a deep workspace pushes
    the packet's own file paths past Windows' 260-char MAX_PATH, which used to
    raise FileNotFoundError inside build_safe_ai_packet.  Now the teacher-visible
    budget ensures all paths stay within 230 chars, with extended_path fallback
    for actual I/O on any persistent deep files."""
    # Moderate padding so the packet builder can still work and I/O uses
    # extended_path for any deep writes.
    safe_dir = tmp_path / ("Deep" * 15)
    os.makedirs(safe_dir)

    info = packet.build_safe_ai_packet(
        "Essay",
        str(safe_dir),
        {"how_to_score": "", "student_txts": []},
        _bundle(),
        assignment_id="assignment-1000002",
    )

    # All returned metadata paths within budget
    for key in ("packet_folder", "packet_zip"):
        val = info.get(key, "")
        assert val
        assert len(val) <= workspace.TEACHER_VISIBLE_BUDGET, (
            f"{key} length {len(val)} > {workspace.TEACHER_VISIBLE_BUDGET}"
        )

    instructions = os.path.join(info["packet_folder"], "START HERE - Instructions for your AI.txt")
    assert len(instructions) <= workspace.TEACHER_VISIBLE_BUDGET
    assert os.path.isfile(workspace.extended_path(instructions))
    with zipfile.ZipFile(workspace.extended_path(info["packet_zip"])) as zf:
        assert "START HERE - Instructions for your AI.txt" in set(zf.namelist())


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


def test_oral_reading_import_requires_current_packet_digest(tmp_path, monkeypatch):
    vault = Vault(str(tmp_path / "vault.json"))
    pseudonym = vault.get_or_assign("9001", "Ada Lovelace", "5001")
    bundle = _bundle(pseudonym)
    bundle["students"][0]["responses"][0]["oral_reading"] = {
        "version": "1.0", "status": "complete", "evidence_digest": "e" * 64,
        "passage_digest": "p" * 64, "passage": "read this", "transcript": "read this",
        "metrics": {"accuracy": 1.0, "wcpm": 90}, "uncertainty": [], "difference_candidates": [],
    }
    safe_bundle = tmp_path / "bundle.json"
    safe_bundle.write_text(json.dumps(bundle), encoding="utf-8")
    session = {
        "session_id": "sid", "privacy_artifacts": {"safe_bundle": str(safe_bundle)},
        "students": [{"user_id": "9001", "real_name": "Ada Lovelace", "ai_score": None, "ai_feedback": None}],
    }
    saved = {}
    monkeypatch.setattr(powergrader, "_load_session", lambda _session_id: session)
    monkeypatch.setattr(powergrader, "_save_session", lambda value: saved.update(value))
    monkeypatch.setattr(powergrader, "_vault", lambda: vault)
    result = {"pseudonym": pseudonym, "item_id": "42", "score": 2, "feedback": "Strong evidence."}

    missing = json.loads(powergrader.pg_import_results("sid", results=json.dumps([result])).body)
    digest = scoring_packet.packet_digest("sid", bundle)
    accepted = json.loads(powergrader.pg_import_results(
        "sid", results=json.dumps({"packet_digest": digest, "results": [result]})
    ).body)

    assert missing["ok"] is False and "packet_digest" in missing["error"]
    assert accepted["ok"] is True
    assert saved["students"][0]["ai_score"] == 2


def test_openrouter_debug_file_omits_key_and_records_response(tmp_path):
    exc = powergrader.orc.OpenRouterResponseError(
        "OpenRouter scoring returned non-JSON response (HTTP 200): <html>bad</html>",
        context="OpenRouter scoring",
        status_code="200",
        response_snippet="<html>bad</html>",
    )

    path = privacy.write_openrouter_debug_file(
        str(tmp_path),
        "Essay Debug",
        session_id="sid",
        course_id="course",
        assignment_id="assignment",
        model_id="deepseek/deepseek-v4-flash",
        safe_students=24,
        packet_info={"packet_zip": str(tmp_path / "packet.zip")},
        budget={"estimated_cost": 0.01},
        privacy_steps=[{"id": "llm_send", "status": "failed"}],
        exc=exc,
    )

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = json.dumps(data)
    assert data["openrouter"]["model_id"] == "deepseek/deepseek-v4-flash"
    assert data["openrouter"]["safe_student_count"] == 24
    assert data["exception"]["status_code"] == "200"
    assert data["exception"]["response_snippet"] == "<html>bad</html>"
    assert "api_key" not in raw.lower()
    assert "bearer" not in raw.lower()


def test_build_session_stores_copilot_packet_metadata():
    copilot_packet = {
        "version": 1,
        "packet_type": "copilot_batches",
        "batch_count": 2,
        "batches": [],
    }

    session = session_builder.build_session(
        session_id="sid",
        course_id="course",
        assignment_id="assignment",
        assignment_name="Essay",
        points_possible=10,
        mode="packet",
        rubric_name="",
        persona_id="sage",
        selected_model="",
        privacy_steps=[],
        privacy_artifacts={},
        students=[],
        mode_label="Score with AI chat",
        copilot_packet=copilot_packet,
    )

    assert session["copilot_packet"] == copilot_packet


def _deep_bundle(pseudonym="Sparky McGee", attachment_bundle=False):
    """Create a bundle with 120-char fictional labels for deep path testing."""
    bundle = {
        "contract_version": "1.0",
        "quiz_title": "A" * 120,
        "shared_context": {
            "assignment_description": "Read the passage. " * 10,
            "materials": [{"title": "A" * 120, "source": "pasted", "text": "A short passage."}],
        },
        "students": [{
            "pseudonym": pseudonym,
            "responses": [{
                "item_id": "42",
                "prompt": "",
                "response": "I think the theme is courage. " * 20,
                "possible": 2,
            }],
        }],
    }
    if attachment_bundle:
        bundle["students"][0]["local_attachments"] = []
        bundle["students"][0]["_expected_attachment_count"] = 0
    return bundle


def test_packet_workflow_compact_fallback_deep_workspace(tmp_path, monkeypatch):
    """Build the complete packet workflow under a deep synthetic root (80-char
    padded) with 120-char fictional labels.  Assert every returned path is plain
    and at most 230 characters.  Verify compact folder names match the locked spec."""
    # Pad the root so it alone is deep enough to force the compact packet
    # layout (the normal "Safe AI Packet - <name>" layout must overflow the
    # 230-char budget, while the compact "Packet-<hash>" layout must still
    # fit) -- computed dynamically since pytest's own tmp_path length varies
    # considerably by machine/username.
    padding = max(1, 150 - len(str(tmp_path)))
    deep_root = tmp_path / ("D" * padding)
    deep_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(deep_root))
    workspace.ensure_workspace()

    safe_dir = str(deep_root / "For AI" / "run")
    private_dir = str(deep_root / "Student Work" / "Grading Keys" / "private")
    os.makedirs(workspace.extended_path(safe_dir), exist_ok=True)
    os.makedirs(workspace.extended_path(private_dir), exist_ok=True)

    bundle = _deep_bundle("Sparky McGee")
    write_result = {
        "safe_bundle": os.path.join(safe_dir, "bundle.json"),
        "safe_students": 1,
        "private_bundle": os.path.join(private_dir, "private.json"),
        "who_is_who": os.path.join(private_dir, "who-is-who.csv"),
        "how_to_score": os.path.join(safe_dir, "how-to-score.txt"),
        "student_txts": [],
        "shared_context": None,
        "shared_context_excluded": False,
        "attachment_only": [],
        "excluded": [],
        "log": [],
    }
    # Write the how-to-score file
    Path(write_result["how_to_score"]).write_text("Score by the rubric.", encoding="utf-8")

    # Build the packet - should use compact layout automatically
    info = packet.build_safe_ai_packet(
        "A" * 120,
        safe_dir,
        write_result,
        bundle,
        assignment_id="assignment-1000002",
    )

    # Check all returned paths are plain and <= 230
    for key in ("packet_zip", "packet_folder"):
        val = info.get(key, "")
        assert val, f"{key} should not be empty"
        assert len(val) <= workspace.TEACHER_VISIBLE_BUDGET, (
            f"{key} length {len(val)} > {workspace.TEACHER_VISIBLE_BUDGET}"
        )
        assert not val.startswith("\\\\?\\"), f"{key} should not use extended path prefix"

    # Verify compact packet folder name
    assert info["packet_name"].startswith("Packet-"), (
        f"Expected compact name starting with 'Packet-', got {info['packet_name']}"
    )

    # Read packet contents
    packet_dir = info["packet_folder"]
    packet_files = os.listdir(workspace.extended_path(packet_dir))
    assert "START HERE - Instructions for your AI.txt" in packet_files
    assert "Student Responses.json" in packet_files

    # Verify ZIP exists and has expected entries
    assert os.path.isfile(workspace.extended_path(info["packet_zip"]))
    with zipfile.ZipFile(workspace.extended_path(info["packet_zip"])) as zf:
        names = set(zf.namelist())
        assert "START HERE - Instructions for your AI.txt" in names
        assert "Student Responses.json" in names


def test_packet_workflow_normal_layout_short_root(tmp_path, monkeypatch):
    """Under a short synthetic root, the readable normal layout is used."""
    monkeypatch.setattr(workspace, "workspace_root", lambda: str(tmp_path))
    workspace.ensure_workspace()

    safe_dir = str(tmp_path / "AI Packets (Pseudonymized)" / "run")
    private_dir = str(tmp_path / "Courses" / "private")
    os.makedirs(workspace.extended_path(safe_dir), exist_ok=True)
    os.makedirs(workspace.extended_path(private_dir), exist_ok=True)

    bundle = _bundle("Sparky McGee")
    write_result = {
        "safe_bundle": os.path.join(safe_dir, "Essay__bundle.json"),
        "safe_students": 1,
        "private_bundle": os.path.join(private_dir, "Essay__PRIVATE.json"),
        "who_is_who": os.path.join(private_dir, "Essay__who-is-who.csv"),
        "how_to_score": os.path.join(safe_dir, "Essay__HOW-TO-SCORE.txt"),
        "student_txts": [],
        "shared_context": None,
        "shared_context_excluded": False,
        "attachment_only": [],
        "excluded": [],
        "log": [],
    }
    Path(write_result["how_to_score"]).write_text("Score by the rubric.", encoding="utf-8")

    info = packet.build_safe_ai_packet("Essay", safe_dir, write_result, bundle)

    # Normal layout: readable name
    assert info["packet_name"].startswith("Safe AI Packet - Essay")
    # All paths <= budget
    for key in ("packet_zip", "packet_folder"):
        val = info.get(key, "")
        assert val
        assert len(val) <= workspace.TEACHER_VISIBLE_BUDGET


def test_packet_workflow_budget_exception_stops_before_writes(tmp_path, monkeypatch):
    """A root so deep that even the compact deepest path exceeds 230 raises
    the dedicated exception before any directory/file is written."""
    # Pad dynamically so the base path alone already exceeds the budget,
    # regardless of how long pytest's own tmp_path happens to be on this
    # machine (username length varies the base considerably).
    padding = max(60, (workspace.TEACHER_VISIBLE_BUDGET + 50) - len(str(tmp_path)))
    very_deep = tmp_path / ("X" * padding)
    os.makedirs(workspace.extended_path(str(very_deep)), exist_ok=True)
    safe_dir = str(very_deep / "SAFE")
    os.makedirs(workspace.extended_path(safe_dir), exist_ok=True)

    bundle = _deep_bundle("Sparky McGee")
    write_result = {
        "safe_bundle": os.path.join(safe_dir, "bundle.json"),
        "safe_students": 1,
        "private_bundle": os.path.join(safe_dir, "private.json"),
        "who_is_who": os.path.join(safe_dir, "who-is-who.csv"),
        "how_to_score": "",
        "student_txts": [],
        "shared_context": None,
        "shared_context_excluded": False,
        "attachment_only": [],
        "excluded": [],
        "log": [],
    }

    with pytest.raises(workspace.TeacherVisiblePathBudgetError):
        packet.build_safe_ai_packet(
            "A" * 120,
            safe_dir,
            write_result,
            bundle,
            assignment_id="assignment-1000002",
        )

    # No packet files should have been written to safe_dir (the exception
    # fires before any packet directory or file is created)
    assert not any(f.startswith("Packet-") or f.startswith("Safe AI Packet")
                   for f in os.listdir(workspace.extended_path(safe_dir)))


# ── Path budget: probe/validator convergence and fail-closed preflight ──────
#
# Regression cover for the 2026-09-10 field failure: start_scoring_session died
# with "Packet child path exceeds budget (248 > 230)" *after* the flat SAFE
# artifacts were written, stranding them with no registered session.


def test_compactness_probe_uses_the_longest_validated_child():
    """LAW: the child that decides readable-vs-compact is the longest child the
    validator will check.

    These were two hand-maintained lists. The probe measured a 22-character
    name while the validator checked a 41-character one, so a packet folder
    could pass the probe by one character and fail validation by eighteen.
    Asserted over the shared list so a newly added packet file cannot
    reintroduce the gap.
    """
    write_result = {"student_txts": [os.path.join("x", "Sparky McGee - responses.txt")]}
    children = packet.packet_child_names(write_result)

    assert packet.longest_packet_child(write_result) == max(children, key=len)
    for child in children:
        assert len(child) <= len(packet.longest_packet_child(write_result))


def test_packet_builds_at_the_measured_failing_depth(tmp_path):
    """EXAMPLE: the exact shape that failed in the field now builds.

    The real packet dir was 206 characters, which projected 229 against the
    22-char probe child (fits, stay readable) and 248 against the real 41-char
    child (raise). With the probe corrected, this selects the compact layout
    and succeeds.
    """
    longest = packet.longest_packet_child()
    readable = packet.safe_ai_packet_name("Fictional Unit Quiz", assignment_id="900002")
    compact = packet.safe_ai_packet_name(
        "Fictional Unit Quiz", assignment_id="900002", compact=True)

    # Every base depth where the readable folder cannot hold its longest child
    # but the compact one can. The old probe mis-decided only across part of
    # this band -- deeper than that it happened to pick compact for the wrong
    # reason -- so the band is swept rather than sampled at one depth.
    floor = workspace.TEACHER_VISIBLE_BUDGET - len(readable) - len(longest) - 2
    ceiling = workspace.TEACHER_VISIBLE_BUDGET - len(compact) - len(longest) - 2
    if ceiling - len(str(tmp_path)) - 1 < 1:
        pytest.skip("temp path already deeper than the readable/compact window")

    for depth in range(max(floor + 1, len(str(tmp_path)) + 2), ceiling + 1):
        base = tmp_path / f"d{depth}"
        base.mkdir()
        safe_dir = base / ("g" * (depth - len(str(base)) - 1))
        safe_dir.mkdir()
        assert len(str(safe_dir)) == depth

        how_to = safe_dir / "HOW-TO.txt"
        how_to.write_text("score it", encoding="utf-8")
        write_result = {"how_to_score": str(how_to), "student_txts": []}

        info = packet.build_safe_ai_packet(
            "Fictional Unit Quiz", str(safe_dir), write_result, _bundle(),
            assignment_id="900002",
        )

        assert os.path.isdir(workspace.extended_path(info["packet_folder"]))
        for child in packet.PACKET_FIXED_CHILDREN:
            projected = os.path.join(info["packet_folder"], child)
            assert len(projected) <= workspace.TEACHER_VISIBLE_BUDGET, (depth, child)


def test_preflight_passes_when_the_packet_fits(tmp_path):
    assert packet.preflight_packet_budget(str(tmp_path), "Essay", "42") is None


def test_preflight_refuses_and_writes_nothing_when_even_compact_overflows(tmp_path):
    """LAW: a budget failure leaves nothing on disk.

    The orphaned-packet bug: artifacts were written first and the budget
    checked second, so the failure stranded them.
    """
    deep = tmp_path
    while len(str(deep)) < workspace.TEACHER_VISIBLE_BUDGET:
        deep = deep / ("h" * 40)
    before = sorted(p for p in tmp_path.rglob("*"))

    message = packet.preflight_packet_budget(str(deep), "Fictional Unit Quiz", "900002")

    assert message and "Nothing was written" in message
    assert sorted(p for p in tmp_path.rglob("*")) == before

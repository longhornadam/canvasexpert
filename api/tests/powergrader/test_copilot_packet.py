import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.platform_services import workspace
from api.powergrader.copilot_packet import build_copilot_batches


def _bundle(students):
    return {
        "contract_version": "1.0",
        "quiz_title": "Fictional Essay",
        "shared_context": {
            "assignment_description": "Explain how the imagined character changes.",
            "materials": [{
                "title": "Class Passage",
                "source": "teacher paste",
                "text": "The passage describes a fictional classroom discussion.",
            }],
        },
        "students": students,
    }


def _student(pseudonym, item_id, response):
    return {
        "pseudonym": pseudonym,
        "responses": [{
            "item_id": item_id,
            "prompt": "",
            "response": response,
            "possible": 2,
        }],
    }


def _upload_files(batch):
    return sorted(Path(batch["folder"]).glob("*.md"))


def test_build_copilot_batches_creates_one_small_batch(tmp_path):
    bundle = _bundle([
        _student("Sparky McGee", "42", "The character becomes braver."),
        _student("Nova Bright", "43", "The character learns to listen."),
    ])

    info = build_copilot_batches(
        assignment_name="Fictional Essay",
        safe_dir=str(tmp_path),
        llm_bundle=bundle,
        rubric_text="Score for claim and evidence.",
        persona={"name": "Sage", "personality": "Be concise and supportive."},
    )

    assert info["batch_count"] == 1
    assert Path(info["packet_folder"]).is_absolute()
    assert Path(info["readme_path"]).is_file()
    assert Path(info["readme_path"]).name == "README - Copilot Steps.md"
    readme = Path(info["readme_path"]).read_text(encoding="utf-8")
    assert "This is one PowerGrader session. Do not start a new PowerGrader session for each batch." in readme
    assert "Paste results into the matching batch import box." in readme
    upload_files = _upload_files(info["batches"][0])
    assert len(upload_files) == 3
    assert [path.name[:4] for path in upload_files] == ["01 -", "02 -", "03 -"]
    assert sorted(path.name[:4] for path in upload_files).count("01 -") == 1
    assert sorted(path.name[:4] for path in upload_files).count("02 -") == 1
    assert sorted(path.name[:4] for path in upload_files).count("03 -") == 1

    combined = "\n".join(path.read_text(encoding="utf-8") for path in upload_files)
    assert "Sparky McGee" in combined
    assert "Nova Bright" in combined
    assert "Item ID: 42" in combined
    assert "Item ID: 43" in combined
    assert "Ada Lovelace" not in combined
    assert "Alan Turing" not in combined


def test_copilot_metadata_uses_batch_folders_not_zip(tmp_path):
    info = build_copilot_batches(
        assignment_name="Folder Based Essay",
        safe_dir=str(tmp_path),
        llm_bundle=_bundle([
            _student("River Vale", "701", "A safe response."),
        ]),
        rubric_text="Score for evidence.",
        persona={"name": "Sage"},
    )

    assert "packet_zip" not in info
    assert Path(info["packet_folder"]).is_dir()
    assert Path(info["readme_path"]).is_file()
    for batch in info["batches"]:
        assert Path(batch["folder"]).is_dir()
        assert all(Path(path).is_file() for path in batch["files"].values())
        upload_files = _upload_files(batch)
        assert len(upload_files) == 3
        assert sum(1 for path in upload_files if path.name.startswith("01 -")) == 1
        assert sum(1 for path in upload_files if path.name.startswith("02 -")) == 1
        assert sum(1 for path in upload_files if path.name.startswith("03 -")) == 1


def test_build_copilot_batches_forces_multiple_batches(tmp_path):
    students = [
        _student(f"Fictional Learner {index}", str(100 + index), "safe response " * 120)
        for index in range(1, 6)
    ]

    info = build_copilot_batches(
        assignment_name="Long Fictional Essay",
        safe_dir=str(tmp_path),
        llm_bundle=_bundle(students),
        rubric_text="Score each response.",
        persona={"name": "Sage"},
        effective_context_tokens=33_000,
    )

    assert info["batch_count"] > 1
    seen = []
    for batch in info["batches"]:
        assert len(_upload_files(batch)) == 3
        seen.extend((entry["pseudonym"], entry["item_id"]) for entry in batch["expected_results"])

    expected = [(student["pseudonym"], student["responses"][0]["item_id"]) for student in students]
    assert sorted(seen) == sorted(expected)
    assert len(seen) == len(set(seen))


def test_build_copilot_batches_warns_for_oversized_single_student(tmp_path):
    info = build_copilot_batches(
        assignment_name="Oversized Fictional Essay",
        safe_dir=str(tmp_path),
        llm_bundle=_bundle([
            _student("Atlas Reed", "501", "large safe response " * 5000),
        ]),
        rubric_text="Score carefully.",
        persona={"name": "Sage"},
        effective_context_tokens=33_000,
    )

    assert info["batch_count"] == 1
    batch = info["batches"][0]
    assert batch["student_count"] == 1
    assert batch["expected_results"] == [{"pseudonym": "Atlas Reed", "item_id": "501"}]
    assert batch["warnings"]
    assert "larger than the target Copilot budget" in batch["warnings"][0]


def test_build_copilot_batches_compact_layout_deep_workspace(tmp_path, monkeypatch):
    """In a deep workspace, Copilot batches use compact layout with short names."""
    # Pad the root to simulate a deep workspace
    padding = max(1, 80 - len(str(tmp_path)))
    deep_root = tmp_path / ("D" * padding)
    deep_root.mkdir(parents=True, exist_ok=True)

    bundle = _bundle([
        _student("Sparky McGee", "42", "The character becomes braver."),
        _student("Nova Bright", "43", "The character learns to listen."),
    ])

    info = build_copilot_batches(
        assignment_name="A" * 120,
        safe_dir=str(deep_root),
        llm_bundle=bundle,
        rubric_text="Score for claim and evidence.",
        persona={"name": "Sage", "personality": "Be concise and supportive."},
        assignment_id="assignment-1000002",
    )

    # Verify compact layout: batches under "Batches" not "Copilot Batches"
    assert "Batches" in info["packet_folder"] or "Batches" in str(info["batches"][0]["folder"])
    # All returned paths must be <= budget
    assert len(info["packet_folder"]) <= workspace.TEACHER_VISIBLE_BUDGET
    for batch in info["batches"]:
        assert len(batch["folder"]) <= workspace.TEACHER_VISIBLE_BUDGET
        for fpath in batch["files"].values():
            assert len(fpath) <= workspace.TEACHER_VISIBLE_BUDGET, (
                f"Batch file path {fpath} ({len(fpath)}) exceeds budget"
            )
    # Check compact file names
    batch = info["batches"][0]
    info_file = os.path.basename(batch["files"]["assignment_info"])
    assert info_file == "01-info.md", f"Expected 01-info.md, got {info_file}"
    rubric_file = os.path.basename(batch["files"]["rubric_persona"])
    assert rubric_file == "02-rubric.md", f"Expected 02-rubric.md, got {rubric_file}"
    work_file = os.path.basename(batch["files"]["student_work"])
    assert work_file == "03-work.md", f"Expected 03-work.md, got {work_file}"


def test_build_copilot_batches_normal_layout_short_root(tmp_path):
    """Under a short root, Copilot batches use the normal readable layout."""
    bundle = _bundle([
        _student("Sparky McGee", "42", "A short response."),
    ])

    info = build_copilot_batches(
        assignment_name="Short Essay",
        safe_dir=str(tmp_path),
        llm_bundle=bundle,
        rubric_text="Score.",
        persona={"name": "Sage"},
    )

    # Normal layout: readable names
    batch = info["batches"][0]
    info_file = os.path.basename(batch["files"]["assignment_info"])
    assert info_file.startswith("01 -"), f"Expected readable name, got {info_file}"
    # All paths must be <= budget
    assert len(info["packet_folder"]) <= workspace.TEACHER_VISIBLE_BUDGET
    for fpath in batch["files"].values():
        assert len(fpath) <= workspace.TEACHER_VISIBLE_BUDGET


def test_build_copilot_batches_budget_exception(tmp_path):
    """A path so deep that even compact layout exceeds the budget raises an error."""
    very_deep = tmp_path / ("X" * 90)
    os.makedirs(workspace.extended_path(str(very_deep)), exist_ok=True)

    bundle = _bundle([
        _student("Sparky", "42", "Response."),
    ])

    with pytest.raises(workspace.TeacherVisiblePathBudgetError):
        build_copilot_batches(
            assignment_name="A" * 120,
            safe_dir=str(very_deep),
            llm_bundle=bundle,
            rubric_text="Score.",
            persona={"name": "Sage"},
            assignment_id="assignment-1000002",
        )


def test_two_assignments_share_prefix_have_distinct_compact_paths(tmp_path):
    """Two different assignment labels sharing a readable prefix but having
    different stable IDs produce distinct, deterministic compact paths."""
    bundle = _bundle([_student("A", "1", "Response.")])

    info1 = build_copilot_batches(
        assignment_name="Fictional Research Essay - Section A",
        safe_dir=str(tmp_path),
        llm_bundle=bundle,
        rubric_text="Score.",
        persona={"name": "Sage"},
        assignment_id="assignment-1001",
    )
    info2 = build_copilot_batches(
        assignment_name="Fictional Research Essay - Section B",
        safe_dir=str(tmp_path),
        llm_bundle=bundle,
        rubric_text="Score.",
        persona={"name": "Sage"},
        assignment_id="assignment-1002",
    )

    # Normal layout: different names
    assert info1["packet_folder"] != info2["packet_folder"]

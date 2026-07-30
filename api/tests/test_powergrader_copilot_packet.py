import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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

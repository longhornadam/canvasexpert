from pathlib import Path

from api.webui import ai_ta


def test_build_library_writes_expected_files(tmp_path):
    target = tmp_path / "AI-TA"

    first = ai_ta.build_library(target)
    # Top-level names (files only)
    names = sorted(p.name for p in target.iterdir() if p.is_file())

    assert len(names) >= 7
    assert "START HERE - What is Canvas Expert.txt" in names
    assert "Author a Quiz (QuizForge).txt" in names
    assert "Author an Assignment (AssignmentForge).txt" in names
    assert "Author a Page (PageForge).txt" in names
    assert "Author a Rubric (RubricForge).txt" in names
    assert "Author a TA (TAForge).txt" in names
    assert "_about this folder.txt" in names
    assert "Score with - ELA 7 Standard Writing Rubric.txt" in names

    for path in target.iterdir():
        if path.is_dir():
            continue
        text = path.read_text(encoding="utf-8")
        assert text.strip()
        assert "{KIND}" not in text
        assert "{TAG}" not in text

    quiz_text = (target / "Author a Quiz (QuizForge).txt").read_text(encoding="utf-8")
    assert "PASTE THIS WHOLE FILE" in quiz_text
    assert "STIMULUS is for actual content students must reference" in quiz_text

    score_text = (target / "Score with - ELA 7 Standard Writing Rubric.txt").read_text(encoding="utf-8")
    assert "Conventions & Language" in score_text

    sentinel = target / "START HERE - What is Canvas Expert.txt"
    sentinel.write_text(sentinel.read_text(encoding="utf-8") + "\nSENTINEL\n", encoding="utf-8")

    second = ai_ta.build_library(target)
    names2 = sorted(p.name for p in target.iterdir() if p.is_file())

    assert names2 == names
    # first / second return paths across both flat files and toolkit subdir
    assert "SENTINEL" in sentinel.read_text(encoding="utf-8")


def test_toolkit_subfolder_created(tmp_path):
    target = tmp_path / "AI-TA"
    ai_ta.build_library(target)

    toolkit = target / "MagicSchool Toolkit"
    assert toolkit.is_dir(), "MagicSchool Toolkit subfolder should be created"

    toolkit_names = {p.name for p in toolkit.iterdir()}
    # Each tool should have INSTRUCTIONS and SETUP files
    for tool in ["Quiz Author", "Assignment Author", "Page Author", "Rubric Author", "Essay Scorer"]:
        assert f"{tool} — INSTRUCTIONS.txt" in toolkit_names, f"Missing INSTRUCTIONS for {tool}"
        assert f"{tool} — SETUP.txt" in toolkit_names, f"Missing SETUP for {tool}"

    # Essay Scorer instructions mention Knowledge
    scorer_instr = (toolkit / "Essay Scorer — INSTRUCTIONS.txt").read_text(encoding="utf-8")
    assert "attached as Knowledge" in scorer_instr

    # Quiz Author should have knowledge copies in the toolkit
    quiz_knowledge = [n for n in toolkit_names if "KNOWLEDGE" in n]
    assert len(quiz_knowledge) >= 1, "Quiz Author should have at least one knowledge file"


def test_build_library_seeds_repo_default_docs_first(tmp_path, monkeypatch):
    default_ai_ta = tmp_path / "default_docs" / "AI-TA"
    default_toolkit = default_ai_ta / "MagicSchool Toolkit"
    default_toolkit.mkdir(parents=True)

    (default_ai_ta / "START HERE - What is Canvas Expert.txt").write_text(
        "repo start here\n", encoding="utf-8"
    )
    (default_toolkit / "Quiz Author — INSTRUCTIONS.txt").write_text(
        "repo toolkit instructions\n", encoding="utf-8"
    )

    monkeypatch.setattr(ai_ta, "DEFAULT_AI_TA_DIR", str(default_ai_ta))

    target = tmp_path / "seeded"
    ai_ta.build_library(target)

    assert (target / "START HERE - What is Canvas Expert.txt").read_text(encoding="utf-8") == "repo start here\n"
    assert (target / "MagicSchool Toolkit" / "Quiz Author — INSTRUCTIONS.txt").read_text(encoding="utf-8") == "repo toolkit instructions\n"

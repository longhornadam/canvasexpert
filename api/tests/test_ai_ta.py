from pathlib import Path

from api.webui import ai_ta


def test_build_library_writes_expected_files(tmp_path):
    target = tmp_path / "AI Authoring"

    first = ai_ta.build_library(target)
    # Top-level names (files only)
    names = sorted(p.name for p in target.iterdir() if p.is_file())

    assert len(names) >= 7
    assert "START HERE - Canvas Expert.txt" in names
    assert "Author a Quiz (QuizForge).txt" in names
    assert "Author an Assignment (AssignmentForge).txt" in names
    assert "Author a Page (PageForge).txt" in names
    assert "Author a Rubric (RubricForge).txt" in names
    assert "About This Folder.txt" in names
    assert "Score with - ELA 7 Standard Writing Rubric.txt" in names

    for path in target.iterdir():
        if path.is_dir():
            continue
        text = path.read_text(encoding="utf-8")
        assert text.strip()
        assert "{KIND}" not in text
        assert "{TAG}" not in text

    quiz_text = (target / "Author a Quiz (QuizForge).txt").read_text(encoding="utf-8")
    # Preamble stripped: the file IS the contract, with no teacher-paste framing.
    assert "PASTE THIS WHOLE FILE" not in quiz_text
    assert quiz_text.lstrip().startswith("# QuizForge")
    assert "STIMULUS is for actual content students must reference" in quiz_text

    score_text = (target / "Score with - ELA 7 Standard Writing Rubric.txt").read_text(encoding="utf-8")
    assert "Conventions & Language" in score_text

    sentinel = target / "START HERE - Canvas Expert.txt"
    sentinel.write_text(sentinel.read_text(encoding="utf-8") + "\nSENTINEL\n", encoding="utf-8")

    second = ai_ta.build_library(target)
    names2 = sorted(p.name for p in target.iterdir() if p.is_file())

    assert names2 == names
    # first / second return paths across both flat files and toolkit subdir
    assert "SENTINEL" in sentinel.read_text(encoding="utf-8")


def test_toolkit_subfolder_created(tmp_path):
    target = tmp_path / "AI Authoring"
    ai_ta.build_library(target)

    toolkit = target / "MagicSchool Toolkit"
    assert toolkit.is_dir(), "MagicSchool Toolkit subfolder should be created"

    toolkit_names = {p.name for p in toolkit.iterdir()}
    # Every tool has a SETUP recipe; only Essay Scorer has its own INSTRUCTIONS
    # file (the other four point at the canonical "Author a ..." file instead
    # of duplicating it, per the single-canonical-source rule).
    for tool in ["Quiz Author", "Assignment Author", "Page Author", "Rubric Author", "Essay Scorer"]:
        assert f"{tool} — SETUP.txt" in toolkit_names, f"Missing SETUP for {tool}"
    assert "Essay Scorer — INSTRUCTIONS.txt" in toolkit_names
    for tool in ["Quiz Author", "Assignment Author", "Page Author", "Rubric Author"]:
        assert f"{tool} — INSTRUCTIONS.txt" not in toolkit_names, (
            f"{tool} should not duplicate the canonical authoring file in the toolkit"
        )

    # No copied knowledge files -- the toolkit only ever held Quiz Author's.
    assert not any("KNOWLEDGE" in n for n in toolkit_names)

    # Essay Scorer instructions mention Knowledge
    scorer_instr = (toolkit / "Essay Scorer — INSTRUCTIONS.txt").read_text(encoding="utf-8")
    assert "attached as Knowledge" in scorer_instr

    # Quiz Author's setup recipe points at the canonical file and the Reference folder.
    quiz_setup = (toolkit / "Quiz Author — SETUP.txt").read_text(encoding="utf-8")
    assert "../Author a Quiz (QuizForge).txt" in quiz_setup
    assert "../Reference/QuizForge_example_quiz.txt" in quiz_setup
    assert "../Reference/QF_MOD_ELA_Question_Design.md" in quiz_setup


def test_build_library_seeds_repo_default_docs_first(tmp_path, monkeypatch):
    default_ai_ta = tmp_path / "default_docs" / "AI Authoring"
    default_toolkit = default_ai_ta / "MagicSchool Toolkit"
    default_toolkit.mkdir(parents=True)

    (default_ai_ta / "START HERE - Canvas Expert.txt").write_text(
        "repo start here\n", encoding="utf-8"
    )
    (default_toolkit / "Essay Scorer — INSTRUCTIONS.txt").write_text(
        "repo toolkit instructions\n", encoding="utf-8"
    )

    monkeypatch.setattr(ai_ta, "DEFAULT_AI_TA_DIR", str(default_ai_ta))

    target = tmp_path / "seeded"
    ai_ta.build_library(target)

    assert (target / "START HERE - Canvas Expert.txt").read_text(encoding="utf-8") == "repo start here\n"
    assert (target / "MagicSchool Toolkit" / "Essay Scorer — INSTRUCTIONS.txt").read_text(encoding="utf-8") == "repo toolkit instructions\n"

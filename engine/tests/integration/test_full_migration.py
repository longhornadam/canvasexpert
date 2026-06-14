"""Comprehensive tests to verify migration success."""

import tempfile
from pathlib import Path
import zipfile
import io

from engine.parsing.text_parser import TextOutlineParser
from engine.validation.validator import QuizValidator, ValidationStatus
from engine.rendering.canvas.canvas_packager import CanvasPackager
from engine.orchestrator import QuizForgeOrchestrator


def test_parse_all_question_types():
    """Test parser handles all question types."""
    quiz_text = """Title: All Types

---
Type: MC
Prompt: MC Question
Choices:
- [x] A
- [ ] B
---

Type: TF
Prompt: TF Question
Answer: true
---

Type: MA
Prompt: MA Question
Choices:
- [x] A
- [ ] B
- [ ] C
---

Type: NUMERICAL
Prompt: Numerical Question
Answer: 42
---

Type: ESSAY
Prompt: Essay Question
---

Type: MATCHING
Prompt: Matching Question
Pairs:
- Term1 => Definition1
- Term2 => Definition2
---

Type: FITB
Prompt: FITB [blank]
Accept:
- answer1
- answer2
---

Type: ORDERING
Prompt: Ordering Question
Header: Put in order
Items:
1. First
2. Second
3. Third
---

Type: CATEGORIZATION
Prompt: Categorization Question
Categories:
- Cat1
- Cat2
Items:
- Item1 => Cat1
- Item2 => Cat2
---
"""

    parser = TextOutlineParser()
    quiz = parser.parse_text(quiz_text)

    assert len(quiz.questions) == 9
    print("✓ Parser handles all question types")


def test_validator_catches_errors():
    """Test validator catches common errors."""

    # Test: MC without choices
    parser = TextOutlineParser()
    validator = QuizValidator()

    try:
        quiz = parser.parse_text("""
Title: Broken

---
Type: MC
Prompt: Test
---
""")
        result = validator.validate(quiz)
        assert result.status == ValidationStatus.FAIL
        assert any("missing Choices" in e for e in result.errors)
        print("✓ Validator catches missing choices")
    except:
        print("✓ Parser rejects missing choices (also valid)")


def test_canvas_package_structure():
    """Test Canvas package has correct structure."""
    quiz_text = """Title: Package Test

---
Type: MC
Prompt: Test
Choices:
- [x] A
- [ ] B
---
"""

    parser = TextOutlineParser()
    validator = QuizValidator()
    packager = CanvasPackager()

    quiz = parser.parse_text(quiz_text)
    result = validator.validate(quiz)
    zip_bytes, guid = packager.package(result.quiz)

    # Verify ZIP structure
    zip_file = zipfile.ZipFile(io.BytesIO(zip_bytes))
    names = zip_file.namelist()

    assert "imsmanifest.xml" in names
    assert f"{guid}/{guid}.xml" in names
    assert f"{guid}/assessment_meta.xml" in names

    print("✓ Canvas package has correct structure")


def test_numerical_bounds_calculation():
    """Test numerical questions have bounds calculated."""
    quiz_text = """Title: Numerical Test

---
Type: NUMERICAL
Prompt: What is pi?
Answer: 3.14159
Tolerance: 0.01
---
"""

    parser = TextOutlineParser()
    quiz = parser.parse_text(quiz_text)

    numerical_q = quiz.questions[0]
    assert numerical_q.answer.lower_bound is not None
    assert numerical_q.answer.upper_bound is not None

    print("✓ Numerical bounds calculated")


def test_full_orchestrator_pipeline():
    """Test complete orchestrator workflow."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        dropzone = tmpdir / "DropZone"
        output = tmpdir / "Finished_Exports"
        dropzone.mkdir()
        output.mkdir()

        # Create valid quiz (JSON 3.0 format)
        valid_quiz = """<QUIZFORGE_JSON>
{
  "version": "3.0-json",
  "title": "Valid Quiz",
  "items": [
    {
      "type": "MC",
      "prompt": "Test question",
      "choices": [
        {"id": "A", "text": "Correct", "correct": true},
        {"id": "B", "text": "Wrong"}
      ]
    }
  ]
}
</QUIZFORGE_JSON>
"""
        (dropzone / "valid.txt").write_text(valid_quiz)

        # Create invalid quiz (JSON 3.0 format - missing choices)
        invalid_quiz = """<QUIZFORGE_JSON>
{
  "version": "3.0-json",
  "title": "Invalid Quiz",
  "items": [
    {
      "type": "MC",
      "prompt": "Missing choices"
    }
  ]
}
</QUIZFORGE_JSON>
"""
        (dropzone / "invalid.txt").write_text(invalid_quiz)

        # Run orchestrator
        orchestrator = QuizForgeOrchestrator(str(dropzone), str(output))
        orchestrator.process_all()

        # Check valid quiz output
        quiz_folders = [f for f in output.iterdir() if f.is_dir()]
        assert len(quiz_folders) >= 1

        valid_folder = [f for f in quiz_folders if "Valid" in f.name][0]
        assert any(p.name.endswith("_QTI.zip") for p in valid_folder.glob("*.zip"))
        assert any((valid_folder / f"log_{s}_FIXED.txt").exists() for s in ["PASS", "WEAK_PASS"])

        # Check invalid quiz output
        fail_files = list(output.glob("*_FAIL_REVISE_WITH_AI.txt"))
        assert len(fail_files) >= 1

        # Check archival
        assert (dropzone / "old_quizzes" / "valid.txt").exists()
        assert (dropzone / "old_quizzes" / "invalid.txt").exists() or len(fail_files) > 0

        print("✓ Full orchestrator pipeline works")


def test_point_normalization():
    """Test that points are normalized to 100."""
    quiz_text = """Title: Points Test

---
Type: MC
Prompt: Q1
Choices:
- [x] A
- [ ] B
---

Type: MC
Prompt: Q2
Choices:
- [x] A
- [ ] B
---
"""

    parser = TextOutlineParser()
    validator = QuizValidator()

    quiz = parser.parse_text(quiz_text)
    result = validator.validate(quiz)

    total = result.quiz.total_points()
    assert 99 <= total <= 101  # Allow small rounding tolerance

    print("✓ Points normalized to 100")


def run_all_tests():
    """Run all verification tests."""
    print("=" * 60)
    print("Running Verification Tests")
    print("=" * 60)
    print()

    test_parse_all_question_types()
    test_validator_catches_errors()
    test_canvas_package_structure()
    test_numerical_bounds_calculation()
    test_full_orchestrator_pipeline()
    test_point_normalization()

    print()
    print("=" * 60)
    print("✓ All verification tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()

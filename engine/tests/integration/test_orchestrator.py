"""Integration test for full orchestrator pipeline."""

import tempfile
import shutil
from pathlib import Path

import pytest

from engine.orchestrator import QuizForgeOrchestrator


# JSON 3.0 format sample quiz (default SPEC_MODE)
SAMPLE_QUIZ = """<QUIZFORGE_JSON>
{
  "version": "3.0-json",
  "title": "Integration Test Quiz",
  "items": [
    {
      "type": "MC",
      "prompt": "What is 2+2?",
      "choices": [
        {"id": "A", "text": "4", "correct": true},
        {"id": "B", "text": "3"},
        {"id": "C", "text": "5"}
      ]
    },
    {
      "type": "TF",
      "prompt": "Python is a programming language.",
      "answer": true
    }
  ]
}
</QUIZFORGE_JSON>
"""


@pytest.mark.parametrize("extension", [".txt", ".json", ".md"])
def test_full_pipeline(extension):
    """Test complete pipeline with temporary directories and multiple extensions."""
    
    # Create temporary directories
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        dropzone = tmpdir / "DropZone"
        output = tmpdir / "Finished_Exports"
        dropzone.mkdir()
        output.mkdir()
        
        # Create a sample quiz file
        quiz_file = dropzone / f"test_quiz{extension}"
        quiz_file.write_text(SAMPLE_QUIZ)
        
        # Run orchestrator
        orchestrator = QuizForgeOrchestrator(
            dropzone_path=str(dropzone),
            output_path=str(output)
        )
        orchestrator.process_all()
        
        # Verify outputs
        # Should have created a quiz folder
        quiz_folders = list(output.glob("*"))
        assert len(quiz_folders) == 1, f"Expected 1 folder, found {len(quiz_folders)}"
        
        quiz_folder = quiz_folders[0]
        
        # Should have .zip file
        zip_files = list(quiz_folder.glob("*.zip"))
        assert len(zip_files) == 1, "Expected Canvas ZIP file"
        
        # Should have log file
        log_files = list(quiz_folder.glob("log_*.txt"))
        assert len(log_files) == 1, "Expected log file"
        
        # Original file should be archived
        assert not quiz_file.exists(), "Original file should be moved"
        archived = dropzone / "old_quizzes" / f"test_quiz{extension}"
        assert archived.exists(), "File should be archived"
        
        print(f"Full pipeline test passed for {extension}")


if __name__ == "__main__":
    test_full_pipeline()

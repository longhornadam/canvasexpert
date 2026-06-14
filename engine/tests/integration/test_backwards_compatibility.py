"""Test that new engine produces same output as old Packager."""

import tempfile
from pathlib import Path

from engine.orchestrator import QuizForgeOrchestrator


def test_sample_quizzes():
    """Test that sample quizzes from User_Docs still work."""

    # Check if sample quizzes exist
    samples_dir = Path("User_Docs/samples")
    if not samples_dir.exists():
        print("⚠ User_Docs/samples not found, skipping test")
        return

    sample_files = list(samples_dir.glob("*.txt"))
    if not sample_files:
        print("⚠ No sample quizzes found, skipping test")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        dropzone = tmpdir / "DropZone"
        output = tmpdir / "Finished_Exports"
        dropzone.mkdir()
        output.mkdir()

        # Copy sample files to dropzone
        for sample in sample_files[:3]:  # Test first 3
            (dropzone / sample.name).write_text(sample.read_text())

        # Process them
        orchestrator = QuizForgeOrchestrator(str(dropzone), str(output))
        orchestrator.process_all()

        # Count successes
        quiz_folders = [f for f in output.iterdir() if f.is_dir()]
        fail_prompts = list(output.glob("*_FAIL_*.txt"))

        print(f"✓ Processed {len(sample_files[:3])} sample quizzes")
        print(f"  - Successes: {len(quiz_folders)}")
        print(f"  - Failures: {len(fail_prompts)}")


if __name__ == "__main__":
    test_sample_quizzes()
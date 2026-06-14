"""Manual test for orchestrator."""

from pathlib import Path
from engine.orchestrator import QuizForgeOrchestrator


def setup_test_environment():
    """Create test quiz in DropZone."""
    dropzone = Path("DropZone")
    dropzone.mkdir(exist_ok=True)
    
    sample = """Title: Manual Test Quiz

---
Type: MC
Prompt: What is the capital of Texas?
Choices:
- [x] Austin
- [ ] Houston
- [ ] Dallas
- [ ] San Antonio
---

Type: NUMERICAL
Prompt: What is 10 * 10?
Answer: 100
---
"""
    
    test_file = dropzone / "manual_test.txt"
    test_file.write_text(sample)
    print(f"Created: {test_file}")
    print()


if __name__ == "__main__":
    # Setup
    setup_test_environment()
    
    # Run orchestrator
    orchestrator = QuizForgeOrchestrator(
        dropzone_path="DropZone",
        output_path="Finished_Exports"
    )
    
    print("Running orchestrator...")
    print()
    orchestrator.process_all()
    print()
    print("✓ Check Finished_Exports/ for output")
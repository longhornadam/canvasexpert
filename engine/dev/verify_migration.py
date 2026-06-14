"""Final migration verification script."""

import sys
from pathlib import Path


def verify_structure():
    """Verify new structure exists."""
    required = [
        "engine/core/quiz.py",
        "engine/core/questions.py",
        "engine/core/answers.py",
        "engine/parsing/text_parser.py",
        "engine/validation/validator.py",
        "engine/rendering/canvas/canvas_packager.py",
        "engine/orchestrator.py",
        "run_quizforge.bat",
        "run_quizforge.sh",
    ]

    missing = []
    for path in required:
        if not Path(path).exists():
            missing.append(path)

    if missing:
        print("✗ Missing files:")
        for path in missing:
            print(f"  - {path}")
        return False

    print("✓ All required files present")
    return True


def verify_imports():
    """Verify new imports work."""
    try:
        from engine.core.quiz import Quiz
        from engine.core.questions import MCQuestion, NumericalQuestion
        from engine.core.answers import NumericalAnswer
        from engine.parsing.text_parser import TextOutlineParser
        from engine.validation.validator import QuizValidator
        from engine.rendering.canvas.canvas_packager import CanvasPackager
        from engine.orchestrator import QuizForgeOrchestrator

        print("✓ All imports successful")
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False


def verify_old_deprecated():
    """Verify old structure is marked deprecated."""
    old_path = Path("Packager")
    old_deprecated_path = Path("Packager_OLD")

    if old_path.exists() and not (old_path / "DEPRECATED.md").exists():
        print("⚠ Warning: Packager/ exists but not marked deprecated")
        print("  Run: Create Packager/DEPRECATED.md")
        return False

    if old_deprecated_path.exists():
        print("✓ Old structure archived as Packager_OLD/")
    elif not old_path.exists():
        print("✓ Old Packager/ directory removed")
    else:
        print("✓ Packager/ marked deprecated")

    return True


def verify_documentation():
    """Verify documentation is complete."""
    docs = [
        "engine/docs/ARCHITECTURE.md",
        "engine/docs/MIGRATION_GUIDE.md",
        "README.md",
    ]

    missing = []
    for doc in docs:
        if not Path(doc).exists():
            missing.append(doc)

    if missing:
        print("⚠ Missing documentation:")
        for doc in missing:
            print(f"  - {doc}")
        return False

    print("✓ All documentation present")
    return True


def main():
    """Run all verification checks."""
    print("=" * 60)
    print("QuizForge Migration Verification")
    print("=" * 60)
    print()

    checks = [
        ("Structure", verify_structure),
        ("Imports", verify_imports),
        ("Deprecation", verify_old_deprecated),
        ("Documentation", verify_documentation),
    ]

    results = []
    for name, check in checks:
        print(f"Checking {name}...")
        result = check()
        results.append(result)
        print()

    print("=" * 60)
    if all(results):
        print("✓ Migration complete and verified!")
        print("=" * 60)
        return 0
    else:
        print("✗ Migration verification failed")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
"""Test fail prompt generator."""

from engine.feedback.fail_prompt_generator import generate_fail_prompt


def test_generate_fail_prompt():
    """Test fail prompt generation."""
    original = """Title: Broken Quiz

---
Type: MC
Prompt: What is 2+2?
---
"""
    
    errors = [
        "Question #1: MC question missing Choices field",
        "Question #1: MC question must have at least 2 choices"
    ]
    
    prompt = generate_fail_prompt(
        original_text=original,
        errors=errors,
        quiz_title="Broken Quiz"
    )
    
    assert "ORIGINAL QUIZ" in prompt
    assert original in prompt
    assert "VALIDATION ERRORS" in prompt
    assert "missing Choices field" in prompt
    assert "INSTRUCTIONS FOR REVISION" in prompt


if __name__ == "__main__":
    test_generate_fail_prompt()
    print("✓ Fail prompt generator test passed")
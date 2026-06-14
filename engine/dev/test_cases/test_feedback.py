"""Manual test for feedback generators."""

from engine.parsing.text_parser import TextOutlineParser
from engine.validation.validator import QuizValidator, ValidationStatus
from engine.feedback.log_generator import generate_log
from engine.feedback.fail_prompt_generator import generate_fail_prompt


def test_pass_feedback():
    """Test feedback for passing quiz."""
    parser = TextOutlineParser()
    quiz = parser.parse_text("""
Title: Good Quiz

---
Type: MC
Prompt: What is 2+2?
Choices:
- [x] 4
- [ ] 3
---
""")
    
    validator = QuizValidator()
    result = validator.validate(quiz)
    
    if result.status == ValidationStatus.FAIL:
        print("Unexpected FAIL")
        return
    
    log = generate_log(
        fix_log=result.fix_log,
        warnings=result.warnings,
        quiz_title=result.quiz.title,
        total_points=result.quiz.total_points(),
        question_count=result.quiz.question_count()
    )
    
    print("=== SUCCESS LOG ===")
    print(log)
    print()


def test_fail_feedback():
    """Test feedback for failing quiz."""
    original_text = """Title: Broken Quiz

---
Type: MC
Prompt: What is 2+2?
---
"""
    
    parser = TextOutlineParser()
    try:
        quiz = parser.parse_text(original_text)
        validator = QuizValidator()
        result = validator.validate(quiz)
        
        if result.status == ValidationStatus.FAIL:
            prompt = generate_fail_prompt(
                original_text=original_text,
                errors=result.errors,
                quiz_title=quiz.title
            )
            
            print("=== FAIL PROMPT ===")
            print(prompt)
            print()
    except Exception as e:
        # Parser might fail before validator
        print(f"Parse error (expected): {e}")


if __name__ == "__main__":
    test_pass_feedback()
    test_fail_feedback()
    print("✓ Feedback tests complete")
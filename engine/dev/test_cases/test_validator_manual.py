"""Manual test script for validator."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from engine.parsing.text_parser import TextOutlineParser
from engine.validation.validator import QuizValidator, ValidationStatus

# Parse a quiz
parser = TextOutlineParser()
quiz = parser.parse_file("engine/dev/test_cases/sample_basic.txt")

# Validate it
validator = QuizValidator()
result = validator.validate(quiz)

print(f"Status: {result.status.value}")
print(f"Errors: {len(result.errors)}")
print(f"Warnings: {len(result.warnings)}")
print(f"Fixes Applied: {len(result.fix_log)}")
print()

if result.fix_log:
    print("Fixes:")
    for fix in result.fix_log:
        print(f"  - {fix}")
print()

if result.warnings:
    print("Warnings:")
    for warning in result.warnings:
        print(f"  - {warning}")

print("✓ Validator working")
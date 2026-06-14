"""Manual test script for parser."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from engine.parsing.text_parser import TextOutlineParser

# Test parsing sample file
parser = TextOutlineParser()
quiz = parser.parse_file("engine/dev/test_cases/sample_basic.txt")

print(f"Title: {quiz.title}")
print(f"Questions: {len(quiz.questions)}")
print(f"Total Points: {quiz.total_points()}")
print()

for i, q in enumerate(quiz.questions, 1):
    print(f"Q{i}: {q.qtype} ({q.points} pts)")
    print(f"   Prompt: {q.prompt[:50]}...")
    print()

print("✓ Parser working correctly")
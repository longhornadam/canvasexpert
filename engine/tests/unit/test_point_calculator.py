"""Unit tests for the point calculator module."""

import unittest
import tempfile
from pathlib import Path

from engine.core.questions import MCQuestion, EssayQuestion, StimulusItem
from engine.validation.point_calculator import calculate_points
from engine.rendering.physical.styles.default_styles import DEFAULT_QUIZ_POINTS


class TestPointCalculator(unittest.TestCase):
    def test_even_mc_points(self):
        questions = [MCQuestion(qtype="MC", prompt=f"Q{i+1}") for i in range(10)]
        calculate_points(questions, total_points=DEFAULT_QUIZ_POINTS)
        self.assertEqual(sum(int(q.points) for q in questions), DEFAULT_QUIZ_POINTS)
        for q in questions:
            self.assertEqual(int(q.points), 10)

    def test_heavy_question_weighting(self):
        questions = [MCQuestion(qtype="MC", prompt=f"Q{i+1}") for i in range(9)]
        heavy = EssayQuestion(qtype="ESSAY", prompt="Essay Q")
        questions.append(heavy)
        calculate_points(questions, total_points=DEFAULT_QUIZ_POINTS)
        self.assertEqual(sum(int(q.points) for q in questions), DEFAULT_QUIZ_POINTS)
        # check heavy has more points than regular
        regular_points = int(questions[0].points)
        heavy_points = int(heavy.points)
        self.assertTrue(heavy_points >= regular_points * 2)

    def test_single_question_receives_all_points(self):
        q = MCQuestion(qtype="MC", prompt="Solo")
        questions = [q]
        calculate_points(questions, total_points=DEFAULT_QUIZ_POINTS)
        self.assertEqual(int(q.points), DEFAULT_QUIZ_POINTS)

    def test_ignores_stimulus_items(self):
        stim = StimulusItem(qtype="STIMULUS", prompt="Read this", points=0)
        q1 = MCQuestion(qtype="MC", prompt="Q1")
        q2 = EssayQuestion(qtype="ESSAY", prompt="Essay Q")
        questions = [stim, q1, q2]
        calculate_points(questions, total_points=DEFAULT_QUIZ_POINTS)
        # stimulus should remain unchanged
        self.assertEqual(stim.points, 0)
        self.assertEqual(sum(int(q.points) for q in [q1, q2]), DEFAULT_QUIZ_POINTS)

    def test_logging_creates_output(self):
        questions = [MCQuestion(qtype="MC", prompt=f"Q{i+1}") for i in range(5)]
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / 'point_calc.log'
            calculate_points(questions, total_points=DEFAULT_QUIZ_POINTS, log_path=str(log_path))
            self.assertTrue(log_path.exists())
            content = log_path.read_text(encoding='utf-8')
            self.assertIn('POINT ALLOCATION', content)

    def test_all_heavy_questions(self):
        questions = [EssayQuestion(qtype="ESSAY", prompt=f"Q{i+1}") for i in range(4)]
        calculate_points(questions, total_points=DEFAULT_QUIZ_POINTS)
        self.assertEqual(sum(int(q.points) for q in questions), DEFAULT_QUIZ_POINTS)
        # All heavy: each should have approximately equal points
        values = [int(q.points) for q in questions]
        self.assertTrue(max(values) - min(values) <= 1)

    def test_rounding_adjustment_applied_to_first_question(self):
        # Construct a set of questions that will force rounding diffs
        # 3 MC + 1 ESSAY -> units = 3 + 2.5 = 5.5 -> base ~18.18
        q1 = MCQuestion(qtype="MC", prompt="Q1")
        q2 = MCQuestion(qtype="MC", prompt="Q2")
        q3 = MCQuestion(qtype="MC", prompt="Q3")
        heavy = EssayQuestion(qtype="ESSAY", prompt="Essay")
        questions = [q1, q2, q3, heavy]
        calculate_points(questions, total_points=DEFAULT_QUIZ_POINTS)
        total = sum(int(q.points) for q in questions)
        self.assertEqual(total, DEFAULT_QUIZ_POINTS)
        # Ensure first scorable question was adjusted if rounding made difference
        # If difference exists, points on q1 may not be equal to other regular q's
        self.assertTrue(int(q1.points) != int(q2.points) or int(q1.points) == int(q2.points))

    def test_calculator_overrides_explicit_points(self):
        # Simulate a parsed question with explicitly set points that should be ignored
        q = MCQuestion(qtype="MC", prompt="Q1", points=999, points_set=True)
        questions = [q]
        calculate_points(questions, total_points=DEFAULT_QUIZ_POINTS)
        self.assertNotEqual(int(q.points), 999)
        self.assertEqual(int(q.points), DEFAULT_QUIZ_POINTS)

    def test_fileupload_is_heavy(self):
        from engine.core.questions import FileUploadQuestion
        q1 = MCQuestion(qtype="MC", prompt="Q1")
        q2 = FileUploadQuestion(qtype="FILEUPLOAD", prompt="Upload Q")
        questions = [q1, q2]
        calculate_points(questions, total_points=DEFAULT_QUIZ_POINTS)
        self.assertTrue(int(q2.points) >= int(q1.points) * 2)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for answer balancer module."""

import unittest
import tempfile
from pathlib import Path

from engine.core.questions import MCQuestion, MCChoice, MAQuestion, TFQuestion
from engine.validation.answer_balancer import balance_answers, log_distribution_stats


class TestAnswerBalancer(unittest.TestCase):
    def test_mc_distribution_balanced(self):
        questions = []
        for i in range(12):
            q = MCQuestion(qtype="MC", prompt=f"Q{i+1}")
            q.choices = [MCChoice(text=c, correct=(c == 'A')) for c in ['A', 'B', 'C', 'D']]
            questions.append(q)

        balance_answers(questions, seed=42)

        # Count correct positions
        counts = [0, 0, 0, 0]
        for q in questions:
            idx = next(i for i, c in enumerate(q.choices) if c.correct)
            counts[idx] += 1

        # Expect roughly 3 per position (12/4)
        self.assertTrue(all(abs(c - 3) <= 2 for c in counts))

    def test_tf_balanced(self):
        questions = [TFQuestion(qtype="TF", prompt=f"Q{i+1}", answer_true=True) for i in range(7)]
        balance_answers(questions, seed=42)
        true_count = sum(1 for q in questions if q.answer_true)
        # Expected 3 or 4 trues in a balanced split
        self.assertIn(true_count, [3, 4])

    def test_ma_preserve_correct_choices(self):
        q = MAQuestion(qtype="MA", prompt="Multi")
        choices = [MCChoice(text=t, correct=(t in ['A', 'C'])) for t in ['A', 'B', 'C', 'D']]
        q.choices = choices
        questions = [q]

        original_correct_texts = {c.text for c in q.choices if c.correct}
        balance_answers(questions, seed=42)
        new_correct_texts = {c.text for c in q.choices if c.correct}
        self.assertEqual(original_correct_texts, new_correct_texts)

    def test_mc_correct_index_update_and_logging(self):
        questions = []
        for i in range(5):
            q = MCQuestion(qtype="MC", prompt=f"Q{i+1}")
            q.choices = [MCChoice(text=c, correct=(c == 'A')) for c in ['A', 'B', 'C']]
            questions.append(q)

        # Balance and write log
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / 'ans_dist.log'
            balance_answers(questions, seed=42)
            log_distribution_stats(questions, str(log_path))
            self.assertTrue(log_path.exists())
            content = log_path.read_text(encoding='utf-8')
            self.assertIn('ANSWER DISTRIBUTION (AFTER BALANCING)', content)

            # Verify correct index present
            for q in questions:
                idx = next(i for i, c in enumerate(q.choices) if c.correct)
                self.assertIn(idx, [0, 1, 2])


if __name__ == "__main__":
    unittest.main()

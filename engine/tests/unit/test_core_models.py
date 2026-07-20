"""Unit tests for core domain models."""

import unittest
from decimal import Decimal
from engine.core.quiz import Quiz
from engine.core.questions import (
    Question, MCQuestion, TFQuestion, MAQuestion, EssayQuestion, FileUploadQuestion,
    MatchingQuestion, FITBQuestion, OrderingQuestion, CategorizationQuestion,
    NumericalQuestion, StimulusItem, StimulusEnd, MCChoice, MatchingPair, OrderingItem, CategoryMapping
)
from engine.core.answers import NumericalAnswer

class TestCoreModels(unittest.TestCase):
    def test_quiz_total_points_and_counts(self):
        q1 = MCQuestion(qtype="MC", prompt="Q1", points=5)
        q2 = TFQuestion(qtype="TF", prompt="Q2", points=10)
        stim = StimulusItem(qtype="STIMULUS", prompt="Read this", points=0)
        quiz = Quiz(title="Sample Quiz", questions=[q1, q2, stim])
        self.assertEqual(quiz.total_points(), 15)
        self.assertEqual(quiz.question_count(), 3)
        self.assertEqual(quiz.scorable_count(), 2)
        self.assertEqual(len(quiz.scorable_questions()), 2)

    def test_numerical_answer_validation(self):
        na = NumericalAnswer(answer=Decimal('42'), tolerance_mode="exact", lower_bound=Decimal('42'), upper_bound=Decimal('42'))
        self.assertEqual(na.validate(), [])
        na2 = NumericalAnswer(tolerance_mode="percent_margin", margin_value=None, lower_bound=None, upper_bound=None)
        errors = na2.validate()
        self.assertTrue(any("Percent margin requires tolerance value" in e for e in errors))

    def test_mcquestion_choices(self):
        choices = [MCChoice(text="A", correct=False), MCChoice(text="B", correct=True)]
        q = MCQuestion(qtype="MC", prompt="Pick one", choices=choices)
        self.assertEqual(len(q.choices), 2)
        self.assertTrue(any(c.correct for c in q.choices))

    def test_matching_question(self):
        pairs = [MatchingPair(prompt="Dog", answer="Bark"), MatchingPair(prompt="Cat", answer="Meow")]
        q = MatchingQuestion(qtype="MATCH", prompt="Match animals", pairs=pairs)
        self.assertEqual(len(q.pairs), 2)

    def test_ordering_question(self):
        items = [OrderingItem(text="First", ident="1"), OrderingItem(text="Second", ident="2")]
        q = OrderingQuestion(qtype="ORDER", prompt="Order these", items=items)
        self.assertEqual(len(q.items), 2)

    def test_categorization_question(self):
        items = [CategoryMapping(item_text="Apple", item_ident="1", category_name="Fruit")]
        q = CategorizationQuestion(qtype="CAT", prompt="Categorize", items=items, categories=["Fruit"], category_idents={"Fruit": "cat1"})
        self.assertEqual(len(q.items), 1)
        self.assertIn("Fruit", q.categories)

if __name__ == "__main__":
    unittest.main()

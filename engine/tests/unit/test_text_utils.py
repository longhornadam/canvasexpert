"""Unit tests for the shared filename sanitizer.

safe_filename_component is the one canonical implementation; workspace.py,
folder_creator.py, ai_ta.py, feedback_contract.py, and portfolio.py all
delegate to it instead of each reimplementing their own rules.
"""

import unittest

from engine.utils.text_utils import safe_filename_component


class TestSafeFilenameComponent(unittest.TestCase):
    def test_preserves_spaces_and_ordinary_punctuation(self):
        self.assertEqual(
            safe_filename_component("Unit 3 (Ch. 4-6) Quiz"),
            "Unit 3 (Ch. 4-6) Quiz",
        )

    def test_replaces_windows_illegal_characters(self):
        self.assertEqual(
            safe_filename_component('Essay: "Draft" <v2>'),
            "Essay_ _Draft_ _v2_",
        )

    def test_collapses_whitespace_and_trims_trailing_dots(self):
        self.assertEqual(safe_filename_component("  Quiz   Title.  "), "Quiz Title")

    def test_empty_input_uses_fallback(self):
        self.assertEqual(safe_filename_component("   ", fallback="_unnamed"), "_unnamed")
        self.assertEqual(safe_filename_component("", fallback=""), "")

    def test_guards_reserved_windows_device_names(self):
        self.assertEqual(safe_filename_component("CON"), "CON_")
        self.assertEqual(safe_filename_component("con.txt"), "con.txt_")
        self.assertEqual(safe_filename_component("Constitution"), "Constitution")

    def test_truncates_to_max_len(self):
        result = safe_filename_component("x" * 200, max_len=10)
        self.assertEqual(result, "x" * 10)


class TestDelegatingCallers(unittest.TestCase):
    def test_workspace_safe_component_matches_shared_helper(self):
        from api.platform_services.workspace import safe_component

        self.assertEqual(safe_component("Chapter 5: Quiz"), safe_filename_component("Chapter 5: Quiz"))

    def test_folder_creator_preserves_spaces(self):
        from engine.packaging.folder_creator import sanitize_filename

        self.assertEqual(sanitize_filename("Chapter 5 Quiz"), "Chapter 5 Quiz")
        self.assertEqual(sanitize_filename(""), "")

    def test_ai_ta_sanitize_filename_falls_back_to_rubric(self):
        from api.webui.ai_ta import _sanitize_filename

        self.assertEqual(_sanitize_filename(""), "Rubric")
        self.assertEqual(_sanitize_filename("Essay: Grading"), "Essay_ Grading")

    def test_feedback_contract_and_portfolio_agree(self):
        from api.feedback_contract import safe as feedback_safe
        from api.portfolio import _safe as portfolio_safe

        self.assertEqual(feedback_safe("O'Brien's (Group A) - Essay!"), "O'Brien's (Group A) - Essay!")
        self.assertEqual(feedback_safe("Essay 1"), portfolio_safe("Essay 1"))


if __name__ == "__main__":
    unittest.main()

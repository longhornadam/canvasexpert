"""Correction Document Renderer.

Produces student-facing correction documents in DOCX and HTML formats.

Each MC/MA item with per-choice rationales is rendered as a 4-column table:

    Letter | Choice Text | ✓ / ✗ | Rationale

Per-choice rationale contract: api/default_docs/AI Authoring/Author a Quiz (QuizForge).txt §11 (canonical).

Usage::

    from engine.rendering.correction_doc.renderer import CorrectionDocRenderer
    from engine.spec_engine.packager import package_quiz

    packaged = package_quiz(quiz_payload)
    renderer = CorrectionDocRenderer()

    html_str  = renderer.render_html(packaged)
    docx_bytes = renderer.render_docx(packaged)
"""

from __future__ import annotations

from ...spec_engine.models import PackagedQuiz
from .docx_renderer import (
    _render_docx_item,
    _set_col_widths,
    _shade_cell,
    render_docx_document,
)
from .html_renderer import _escape_html, _render_html_item, render_html_document
from .shared import _build_item_index, _build_rationale_index, _choice_letter, _items_to_render, _strip_html
from .styles import (
    CORRECT_MARK_HEX,
    CORRECT_ROW_BG_HEX,
    HEADER_BG_HEX,
    HEADER_FG_HEX,
    INCORRECT_MARK_HEX,
    INCORRECT_ROW_BG_HEX,
    QUESTION_HDR_HEX,
    _COL_RATIOS,
    _FALLBACK_RATIONALE,
    _PAGE_WIDTH_INCHES,
)

__all__ = [
    "CorrectionDocRenderer",
    "CORRECT_MARK_HEX",
    "CORRECT_ROW_BG_HEX",
    "HEADER_BG_HEX",
    "HEADER_FG_HEX",
    "INCORRECT_MARK_HEX",
    "INCORRECT_ROW_BG_HEX",
    "QUESTION_HDR_HEX",
]


class CorrectionDocRenderer:
    """Render per-choice rationale correction documents."""

    def render_docx(self, quiz: PackagedQuiz) -> bytes:
        return render_docx_document(quiz)

    def render_html(self, quiz: PackagedQuiz) -> str:
        return render_html_document(quiz)

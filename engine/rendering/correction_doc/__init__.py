"""Correction Document renderer package.

Produces student-facing correction documents (DOCX and HTML) from
QuizForge per-choice rationale data.

Public API::

    from engine.rendering.correction_doc import CorrectionDocRenderer
"""

from .renderer import CorrectionDocRenderer

__all__ = ["CorrectionDocRenderer"]

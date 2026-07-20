"""Build the Pandoc reference DOCX for physical print output."""

from __future__ import annotations

from pathlib import Path

from engine.rendering.physical.styles.default_styles import (
    DOCX_BODY_SIZE,
    DOCX_FONT_FAMILY,
    DOCX_HEADING_SIZE,
    DOCX_LINE_SPACING,
    DOCX_MARGIN_BOTTOM,
    DOCX_MARGIN_LEFT,
    DOCX_MARGIN_RIGHT,
    DOCX_MARGIN_TOP,
    DOCX_SMALL_SIZE,
    DOCX_TITLE_SIZE,
)


def build_reference_docx(out_path: str) -> str:
    """Create a Pandoc reference doc matching the legacy physical styles."""

    from docx import Document
    from docx.enum.style import WD_STYLE_TYPE
    from docx.shared import Inches, Pt

    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    doc = Document()
    for section in doc.sections:
        section.top_margin = Inches(DOCX_MARGIN_TOP)
        section.bottom_margin = Inches(DOCX_MARGIN_BOTTOM)
        section.left_margin = Inches(DOCX_MARGIN_LEFT)
        section.right_margin = Inches(DOCX_MARGIN_RIGHT)

    styles = doc.styles
    _set_font(styles["Normal"], DOCX_FONT_FAMILY, DOCX_BODY_SIZE)
    styles["Normal"].paragraph_format.line_spacing = DOCX_LINE_SPACING

    _set_font(styles["Title"], DOCX_FONT_FAMILY, DOCX_TITLE_SIZE, bold=True)
    _set_font(styles["Heading 1"], DOCX_FONT_FAMILY, DOCX_TITLE_SIZE, bold=True)
    _set_font(styles["Heading 2"], DOCX_FONT_FAMILY, DOCX_HEADING_SIZE, bold=True)
    _set_font(styles["Heading 3"], DOCX_FONT_FAMILY, DOCX_BODY_SIZE, bold=True)

    if "Print Small" not in styles:
        small = styles.add_style("Print Small", WD_STYLE_TYPE.PARAGRAPH)
    else:
        small = styles["Print Small"]
    _set_font(small, DOCX_FONT_FAMILY, DOCX_SMALL_SIZE)

    doc.add_paragraph("Reference document for CanvasExpert physical print output.")
    doc.save(str(output))
    return str(output)


def _set_font(style, family: str, size: int, *, bold: bool = False) -> None:
    from docx.shared import Pt

    style.font.name = family
    style.font.size = Pt(size)
    style.font.bold = bold
